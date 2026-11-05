"""Transcribe Lyrics hears a cover's vocal stem too (owner 2026-10-24: the stem only where it hears better): the
hearing the ASR is clearly more confident of becomes the draft, and the report says which and how sure."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest

pytestmark = pytest.mark.comfy


def audio(level: float) -> dict[str, Any]:
    import torch

    wave = np.full((1, 2, 16000 * 4), level, dtype=np.float32)
    return {"waveform": torch.from_numpy(wave), "sample_rate": 16000}


def run(monkeypatch: pytest.MonkeyPatch, mix_p: float, stem_p: float) -> Any:
    from plenio.comfy.nodes import transcribe_lyrics as node
    from plenio.core.alignment import AsrWord
    from plenio.core.asr import AsrResult

    def fake_asr(sound: Any, settings: Any, source: str, progress: Any) -> AsrResult:
        stem = float(sound["waveform"][0, 0, 0]) > 0.5
        text = (
            ["We", "walk", "down", "the", "riverside", "tonight"]
            if stem
            else ["We", "walk", "doun", "the", "riverside", "tonight"]
        )
        p = stem_p if stem else mix_p
        words = tuple(AsrWord(0.5 * k, 0.5 * k + 0.4, w, p, 0) for k, w in enumerate(text))
        return AsrResult("qwen3-asr-1.7b", "qwen3", "en", 0.99, (), words)

    monkeypatch.setattr(node, "_run_asr", fake_asr)
    monkeypatch.setattr(node, "asr_notes", lambda: type("Notes", (), {"put": lambda self, note: None})())
    return node.PlenioTranscribeLyrics.execute(
        audio=audio(0.1), engine="qwen3-asr-1.7b", language="English", vocals=audio(0.9)
    )


def test_the_more_confident_hearing_is_kept(comfy_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    out = run(monkeypatch, mix_p=0.6, stem_p=0.95)
    lyrics, _transcript, _language, report = out.result
    assert "down" in lyrics and "doun" not in lyrics
    assert report.data["heard_from"] == "the vocal stem" and "heard from the vocal stem" in report.summary
    out = run(monkeypatch, mix_p=0.9, stem_p=0.91)  # better, but not clearly: the recording stays
    lyrics, _transcript, _language, report = out.result
    assert "doun" in lyrics and report.data["heard_from"] == "the recording"
    assert set(report.data["confidence"]) == {"recording", "vocal stem"}


def test_an_instrumental_cover_hears_nothing_and_does_not_stop(
    comfy_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GitHub issue (1.3.0): an instrumental source with an instrumental Cover Brief stopped the run - "no vocal
    melody" - since Fix Misheard Words reads this node's lyrics for every cover. An instrumental cover skips it."""
    from plenio.comfy.nodes import transcribe_lyrics as node
    from plenio.core.brief import CoverBrief
    from plenio.core.reports import Status

    def no_asr(*_: Any) -> Any:
        raise AssertionError("an instrumental cover runs no ASR")

    monkeypatch.setattr(node, "_run_asr", no_asr)
    out = node.PlenioTranscribeLyrics.execute(
        audio=audio(0.1), engine="qwen3-asr-1.7b", language="auto", brief=CoverBrief(vocals="instrumental")
    )
    lyrics, transcript, language, report = out.result
    assert (lyrics, transcript, language) == ("", "", "")
    assert report.status is Status.SKIPPED and "instrumental" in report.summary
