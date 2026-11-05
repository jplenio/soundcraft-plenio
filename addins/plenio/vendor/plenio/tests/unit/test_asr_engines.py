"""The lyrics ASR engines (owner's decision 2026-10-22): Qwen3-ASR with Qwen3-ForcedAligner by default,
faster-whisper as the fallback for languages the aligner cannot time; the worker's pieces, sentences and word
confidences; the subtitle timing per engine; the vendored inference code as recorded."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from plenio.core import subtitles
from plenio.core.alignment import AsrWord
from plenio.core.asr import (
    ALIGNER_LANGUAGES,
    DEFAULT_ENGINE,
    ENGINES,
    QWEN3,
    QWEN3_LANGUAGES,
    WHISPER,
    AsrResult,
    AsrSettings,
    can_time,
    engine_for,
)
from plenio.workers import asr as worker

ROOT = Path(__file__).resolve().parents[2]


def test_qwen3_is_the_default_and_whisper_its_fallback() -> None:
    assert DEFAULT_ENGINE == QWEN3 == list(ENGINES)[0]  # the first choice of Transcribe Lyrics
    qwen3, whisper = engine_for(QWEN3), engine_for(WHISPER)
    assert qwen3.fallback == WHISPER and qwen3.aligner_asset_id == "qwen3-forcedaligner-0.6b-hf"
    assert can_time(qwen3, "en") and can_time(qwen3, "de") and can_time(qwen3, "")
    assert not can_time(qwen3, "nl") and not can_time(qwen3, "sv")
    assert can_time(whisper, "nl")
    assert ALIGNER_LANGUAGES <= set(QWEN3_LANGUAGES.values())


def test_the_assets_are_pinned_with_the_weights_hashes() -> None:
    from plenio.core.assets import load_catalogue

    assets = load_catalogue(ROOT / "resources" / "assets.toml")
    for asset_id in ("qwen3-asr-1.7b-hf", "qwen3-forcedaligner-0.6b-hf", "faster-whisper-large-v3"):
        asset = assets[asset_id]
        weights = [f for f in asset.files if f.path.endswith((".safetensors", ".bin"))]
        assert weights and all(f.sha256 for f in weights), asset_id
        assert asset.role, asset_id  # the System Check says what it is for
    for engine in ENGINES.values():
        assert engine.asset_id in assets and (
            not engine.aligner_asset_id or engine.aligner_asset_id in assets
        )


# --- the host's fallback -------------------------------------------------------------------------------


def result(engine: str, language: str, timed: bool | None = True) -> AsrResult:
    settings: dict[str, Any] = {} if timed is None else {"timed": timed}
    return AsrResult(engine, "model", language, 0.0, (), (), settings=settings)


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> list[AsrSettings]:
    from plenio.comfy import lyrics_asr

    seen: list[AsrSettings] = []
    answers = {
        QWEN3: lambda s: result(
            "qwen3-asr-1.7b", s.language or "nl", timed=(s.language or "nl") in ALIGNER_LANGUAGES
        ),
        WHISPER: lambda s: result("faster-whisper-large-v3", s.language, timed=None),
    }

    def fake(audio: Any, settings: AsrSettings, source: str, progress: Any) -> AsrResult:
        seen.append(settings)
        return answers[settings.engine](settings)

    monkeypatch.setattr(lyrics_asr, "_run", fake)
    return seen


def test_a_language_the_aligner_knows_runs_qwen3_only(calls: list[AsrSettings]) -> None:
    from plenio.comfy.lyrics_asr import run_asr

    heard = run_asr(None, AsrSettings(language="de"), "sha", SimpleNamespace())
    assert [s.engine for s in calls] == [QWEN3] and heard.engine == "qwen3-asr-1.7b"
    assert "engine_note" not in heard.settings


def test_a_given_language_the_aligner_cannot_time_goes_to_whisper_at_once(calls: list[AsrSettings]) -> None:
    from plenio.comfy.lyrics_asr import run_asr

    heard = run_asr(None, AsrSettings(language="nl"), "sha", SimpleNamespace())
    assert [s.engine for s in calls] == [WHISPER] and heard.engine == "faster-whisper-large-v3"
    assert "cannot time 'nl'" in heard.settings["engine_note"]


def test_a_detected_language_the_aligner_cannot_time_is_heard_again_by_whisper(
    calls: list[AsrSettings],
) -> None:
    from plenio.comfy.lyrics_asr import run_asr

    heard = run_asr(None, AsrSettings(language=""), "sha", SimpleNamespace())
    assert [(s.engine, s.language) for s in calls] == [(QWEN3, ""), (WHISPER, "nl")]
    assert (
        heard.engine == "faster-whisper-large-v3"
        and "Qwen3-ASR 1.7B cannot time 'nl'" in heard.settings["engine_note"]
    )


def test_the_cache_key_names_both_qwen3_models(monkeypatch: pytest.MonkeyPatch) -> None:
    from plenio.comfy import lyrics_asr

    pinned = lyrics_asr.revision(engine_for(QWEN3))
    assert re.fullmatch(r"[0-9a-f]{40}\+[0-9a-f]{40}", pinned)
    assert re.fullmatch(r"[0-9a-f]{40}", lyrics_asr.revision(engine_for(WHISPER)))


# --- the worker's helpers ------------------------------------------------------------------------------


def test_long_spans_are_cut_at_their_quietest_moment() -> None:
    rate = worker.RATE
    audio = np.random.default_rng(1).standard_normal(rate * 600).astype("float32") * 0.1
    quiet = int((worker.PIECE_S - 4.0) * rate)
    audio[quiet : quiet + rate // 10] = 0.0  # 100 ms of silence four seconds before the four-minute mark
    pieces = worker.pieces(audio, [])
    assert all(end - start <= worker.PIECE_S + 1e-6 for start, end in pieces)
    assert pieces[0] == (0.0, pytest.approx(worker.PIECE_S - 4.0, abs=0.11))
    assert pieces[-1][1] == pytest.approx(600.0)
    # regions are kept, a region shorter than half a second is dropped
    assert worker.pieces(audio, [(10.0, 20.0), (30.0, 30.2)]) == [(10.0, 20.0)]


def test_a_song_is_heard_in_short_pieces_with_a_little_of_their_neighbours() -> None:
    """Owner's report 2026-10-23: over a whole song the aligner loses its place - 20-second pieces, each heard
    with OVERLAP_S of its neighbours inside its span."""
    rate = worker.RATE
    audio = np.random.default_rng(2).standard_normal(rate * 70).astype("float32") * 0.1
    heard = worker.heard_pieces(audio, [])
    assert [round(end - start) <= worker.PIECE_S for start, end, _lo, _hi in heard] == [True] * len(heard)
    assert heard[0][2] == 0.0 and heard[0][3] == pytest.approx(heard[0][1] + worker.OVERLAP_S)
    assert heard[1][2] == pytest.approx(heard[1][0] - worker.OVERLAP_S) and heard[-1][3] == pytest.approx(
        70.0
    )
    # a region is heard inside its own bounds
    assert worker.heard_pieces(audio, [(10.0, 15.0)]) == [(10.0, 15.0, 10.0, 15.0)]


def test_a_word_heard_by_both_pieces_at_a_cut_is_kept_once() -> None:
    owns = [(0.0, 20.0), (20.0, 40.0)]
    # both heard "dancing" near the cut, and time it on opposite sides: kept once, by the mean of the two
    # (each alone: the left piece's middle 20.0 is the right one's, the right piece's 19.6 the left one's)
    left = [(18.0, 18.5, "you"), (18.6, 19.0, "can"), (19.6, 20.4, "dancing")]
    right = [(18.6, 19.0, "can"), (19.4, 19.8, "Dancing"), (20.7, 21.5, "queen")]
    keep = worker.owned_words(owns, [left, right])
    assert keep == [[True, True, True], [False, False, True]]
    kept = [
        w
        for words, flags in zip([left, right], keep, strict=True)
        for w, k in zip(words, flags, strict=True)
        if k
    ]
    assert [w[2] for w in kept] == ["you", "can", "dancing", "queen"]
    # a word only one piece heard keeps the side its middle is on; a piece of another span shares nothing
    assert worker.owned_words([(0.0, 20.0), (30.0, 40.0)], [[(19.9, 20.4, "late")], [(29.0, 30.5, "x")]]) == [
        [False],
        [False],
    ]
    assert worker.owned_words([(0.0, 20.0)], [[(19.5, 20.5, "end")]]) == [[True]]


def test_a_sentence_cut_by_a_piece_keeps_the_words_it_kept() -> None:
    assert (
        worker._kept_text("Friday night and the lights are low.", ["and", "the", "lights"])
        == "and the lights"
    )
    assert worker._kept_text("窗台那盆绿萝", ["那", "盆"]) == "那盆"


def test_sentences_follow_the_transcripts_punctuation() -> None:
    transcript = "I held the receiver up to my ear. Static on the hollow, empty chair! And then?"
    words = ["I", "held", "the", "receiver", "up", "to", "my", "ear", "Static", "on", "the", "hollow", "empty", "chair",
             "And", "then"]  # fmt: skip
    assert worker._sentences(transcript, words) == [0] * 8 + [1] * 6 + [2] * 2
    assert worker._sentence_texts(transcript) == [
        "I held the receiver up to my ear.",
        "Static on the hollow, empty chair!",
        "And then?",
    ]


def test_a_words_confidence_is_the_geometric_mean_of_its_tokens() -> None:
    raw = "language English<asr_text>so far away"
    transcript = "so far away"
    offset = raw.index(transcript)
    spans = [(0, 0, offset), (1, offset, offset + 3), (2, offset + 3, offset + 7), (3, offset + 7, offset + 9),
             (4, offset + 9, offset + 12)]  # fmt: skip
    probs = [0.99, 0.9, 0.8, 0.5, 0.2]
    p = worker._word_probabilities(transcript, raw, spans, probs, ["so", "far", "away"])
    assert p[0] == pytest.approx(0.9) and p[1] == pytest.approx(0.8)
    assert p[2] == pytest.approx(np.sqrt(0.5 * 0.2))


# --- subtitles ---------------------------------------------------------------------------------------


def test_aligned_times_are_used_as_they_are_and_whispers_are_corrected() -> None:
    assert subtitles.timing_for("faster-whisper-large-v3") is subtitles.WHISPER
    assert subtitles.timing_for("qwen3-asr-1.7b") is subtitles.ALIGNED
    heard = [
        AsrWord(1.0 + 0.4 * k, 1.3 + 0.4 * k, w, 0.9, 0) for k, w in enumerate("hold on to the light".split())
    ]
    aligned = subtitles.time_heard(heard, duration=10.0, timing=subtitles.ALIGNED)
    whisper = subtitles.time_heard(heard, duration=10.0, timing=subtitles.WHISPER)
    assert aligned.lines[0].start == pytest.approx(1.0)
    assert whisper.lines[0].start == pytest.approx(1.0 + subtitles.LEAD_S)


# --- the vendored inference code ------------------------------------------------------------------------


def test_the_vendored_qwen3_files_are_the_recorded_ones() -> None:
    folder = ROOT / "plenio" / "third_party" / "qwen3_asr"
    notice = (folder / "NOTICE.md").read_text(encoding="utf-8")
    rows = re.findall(r"^\| `([^`]+)` \| .* \| `([0-9a-f]{64})` \|$", notice, flags=re.M)
    assert {name for name, _ in rows} >= {
        "configuration_qwen3_asr.py",
        "feature_extraction_qwen3_asr.py",
        "modeling_qwen3_asr.py",
        "processing_qwen3_asr.py",
        "_compat.py",
        "LICENSE",
    }
    for name, digest in rows:
        assert hashlib.sha256((folder / name).read_bytes()).hexdigest() == digest, (
            f"{name} differs from NOTICE.md - re-run tools/vendor_qwen3_asr.py instead of editing it"
        )
