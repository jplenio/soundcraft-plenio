"""Requests of 2026-10-22: covers of one song get titles of their own (as file names do) and the Plenio Player
tells them apart; a song exported without lyrics times says why and follows its score's times instead; a
whole track moves by an octave; the lyrics ASR falls back to faster-whisper when Qwen3-ASR cannot run."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from plenio.core import subtitles
from plenio.core.asr import QWEN3, WHISPER, AsrResult, AsrSettings
from plenio.core.errors import PlenioValidationError, PlenioWorkerError
from plenio.core.release import RecordInput, base_title, build_record, numbered_title, release_titles
from plenio.core.score import canonical as c
from plenio.core.score import lyric_layout, ops
from plenio.player.align import score_to_audio
from plenio.player.library import Library, timing_note

SCORE = (
    "X:1\nT:\nM:4/4\nL:1/8\nQ:1/4=120\n"
    'V: Vocal clef=treble name="Vocal Melody" snm="Vocal"\n'
    'V: Ins clef=treble name="Ins Melody" snm="Inst."\n'
    "K:C\n% verse\nV: Vocal\nCDEF GABc|c8|\nV: Ins\nC8|C8|\n"
)
LYRICS = "[Verse]\nwalking down the river side\n"


# --- titles ---------------------------------------------------------------------------------------------------


def test_a_taken_title_gets_the_first_free_number() -> None:
    assert numbered_title("Yesterday", []) == "Yesterday"
    assert numbered_title("Yesterday", ["yesterday"]) == "Yesterday (2)"
    assert numbered_title("Yesterday", ["Yesterday", "Yesterday (2)", "YESTERDAY (3)"]) == "Yesterday (4)"
    assert base_title("Yesterday (12)") == "Yesterday" and base_title("(2)") == "(2)"
    assert base_title("Song 2") == "Song 2"


def record_json(title: str, created: str = "2026-10-22T10:00:00+0200", **extra: Any) -> str:
    record = build_record(
        RecordInput(
            versions={"plenio": "1.1.0"},
            prompt=None,
            reports=[
                {
                    "kind": "song_sheet",
                    "data": {
                        "documents": {
                            "lyrics": {"text": LYRICS, "sha256": "l1"},
                            "score": {"text": SCORE, "sha256": "s1"},
                        }
                    },
                }
            ],
            files=[],
            audio={"seconds": 8.0},
            title=title,
            licences=[],
            **extra,
        )
    )
    record["created"] = created
    return json.dumps(record, indent=2, ensure_ascii=False)


def test_the_titles_of_a_folder_are_read_from_the_records(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "Night.plenio.json").write_text(record_json("Night"), encoding="utf-8")
    (tmp_path / "a" / "Night (2).plenio.json").write_text(record_json("Night (2)"), encoding="utf-8")
    (tmp_path / "broken.plenio.json").write_text("{", encoding="utf-8")
    assert release_titles(tmp_path) == {"Night", "Night (2)"}
    assert release_titles(tmp_path, recursive=False) == {"Night"}
    assert release_titles(tmp_path / "missing") == set()
    assert numbered_title("Night", release_titles(tmp_path)) == "Night (3)"


def test_the_player_tells_songs_of_one_title_apart(tmp_path: Path) -> None:
    folder = tmp_path / "plenio"
    folder.mkdir()
    (folder / "1.plenio.json").write_text(record_json("Cover", "2026-10-20T10:00:00"), encoding="utf-8")
    (folder / "2.plenio.json").write_text(record_json("Cover", "2026-10-21T10:00:00"), encoding="utf-8")
    (folder / "3.plenio.json").write_text(record_json("Cover (2)", "2026-10-22T10:00:00"), encoding="utf-8")
    (folder / "4.plenio.json").write_text(record_json("Other", "2026-10-22T11:00:00"), encoding="utf-8")
    library = Library([tmp_path], cache=tmp_path / "cache.json")
    songs = {s["file"]: s for s in library.songs()}
    assert songs["1"]["title"] == "Cover" and "recorded_title" not in songs["1"]
    # the second "Cover" may not take "Cover (2)": a song has that title
    assert songs["2"]["title"] == "Cover (3)" and songs["2"]["recorded_title"] == "Cover"
    assert songs["3"]["title"] == "Cover (2)" and songs["4"]["title"] == "Other"
    # takes of one song stay takes of one song
    assert (
        songs["1"]["takes_key"]
        == songs["2"]["takes_key"]
        == songs["3"]["takes_key"]
        != songs["4"]["takes_key"]
    )
    # the cache keeps the titles as recorded: a second library tells them apart the same way
    again = {s["file"]: s["title"] for s in Library([tmp_path], cache=tmp_path / "cache.json").songs()}
    assert again == {k: v["title"] for k, v in songs.items()}


# --- lyrics times -----------------------------------------------------------------------------------------------


def test_the_record_says_why_a_song_has_no_times() -> None:
    off = json.loads(record_json("A", subtitles={"wanted": False, "takes": 0}))
    failed = json.loads(
        record_json(
            "B", subtitles={"wanted": True, "takes": 0, "why": ["the lyrics ASR could not run: offline"]}
        )
    )
    assert off["subtitles"] == {"wanted": False, "takes": 0}
    assert timing_note(off) == "Lyrics subtitles were off when the song was exported."
    assert "the lyrics ASR could not run: offline" in timing_note(failed)
    assert "before songs kept their lyrics times" in timing_note({"versions": {"plenio": "0.7.0"}})
    assert "most often: the lyrics ASR could not run" in timing_note({"versions": {"plenio": "1.0.2"}})


def test_the_score_gives_the_lyrics_times_where_none_were_measured() -> None:
    score = c.from_abc(SCORE)
    layout = lyric_layout.layout(score, LYRICS)
    found = {"warp": [1.0, 1.5], "anchors": [[3.5, 2.0], [5.5, 4.0]]}
    timed = subtitles.time_by_score(
        LYRICS, score=score, layout=layout, duration=8.0, to_audio=lambda at: score_to_audio(at, found)
    )
    assert timed.timing == "estimated" and len(timed.lines) == 1
    line = timed.lines[0]
    # the first note (0.0 s in the score) is 1.5 s into the song; the units carry no score time
    assert line.text == "walking down the river side" and line.start == pytest.approx(1.5)
    assert all(unit.score is None for unit in line.units) and len(line.units) >= 5
    assert timed.to_timing()["lines"][0]["units"][0] == [1.5, 3]  # "wal"


def test_the_score_maps_into_the_song_like_the_page_does() -> None:
    found = {"warp": [1.0, 1.0], "anchors": [[3.0, 2.0], [7.0, 4.0]]}
    assert score_to_audio(1.0, found) == 2.0  # before the first anchor: along the warp's slope
    assert score_to_audio(3.0, found) == 5.0  # between: interpolated
    assert score_to_audio(6.0, found) == 9.0  # after the last
    assert score_to_audio(2.0, {"warp": [1.0, -0.5]}) == 1.5  # no anchors: the warp


# --- a whole track an octave ------------------------------------------------------------------------------------


def test_a_whole_track_moves_by_an_octave_and_the_chords_stay() -> None:
    score = c.from_abc(SCORE.replace("CDEF", '"Am"CDEF'))
    up = ops.apply(score, {"op": "shift_track", "track": "vocal", "semitones": 12})
    assert [n.pitch for n in up.score.vocal] == [n.pitch + 12 for n in score.vocal]
    assert up.score.ins == score.ins and up.score.chords == score.chords and up.score.keys == score.keys
    assert up.changes == ("Vocal: all 9 notes 1 octave up",)
    down = ops.apply(score, {"op": "shift_track", "track": "ins", "semitones": -12})
    assert [n.pitch for n in down.score.ins] == [48, 48] and down.changes == (
        "Instrument: all 2 notes 1 octave down",
    )
    high = score.with_track("ins", [c.Note(0, 8, 120)])
    with pytest.raises(PlenioValidationError, match="outside the MIDI range"):
        ops.apply(high, {"op": "shift_track", "track": "ins", "semitones": 12})
    empty = c.new_score(measures=2)
    assert ops.apply(empty, {"op": "shift_track", "track": "vocal", "semitones": 12}).changes == (
        "the Vocal track has no notes",
    )


# --- the ASR when Qwen3 cannot run ------------------------------------------------------------------------------


def missing_transformers() -> PlenioWorkerError:
    return PlenioWorkerError(
        "Worker plenio.workers.asr failed: the lyrics ASR Qwen3-ASR (transformers 5.5 or newer; found: 4.57)",
        details={"type": "PlenioDependencyError"},
    )


def test_qwen3_that_cannot_run_hands_the_song_to_whisper(monkeypatch: pytest.MonkeyPatch) -> None:
    from plenio.comfy import lyrics_asr

    asked: list[str] = []

    def fake(audio: Any, settings: AsrSettings, source: str, progress: Any) -> AsrResult:
        asked.append(settings.engine)
        if settings.engine == QWEN3:
            raise missing_transformers()
        return AsrResult("faster-whisper-large-v3", "model", "en", 0.9, (), ())

    monkeypatch.setattr(lyrics_asr, "_run", fake)
    heard = lyrics_asr.run_asr(None, AsrSettings(language="en"), "sha", SimpleNamespace())
    assert asked == [QWEN3, WHISPER] and heard.engine == "faster-whisper-large-v3"
    assert "Qwen3-ASR 1.7B could not run" in heard.settings["engine_note"]


def test_when_neither_can_run_the_qwen3_error_says_what_to_install(monkeypatch: pytest.MonkeyPatch) -> None:
    from plenio.comfy import lyrics_asr

    def fake(audio: Any, settings: AsrSettings, source: str, progress: Any) -> AsrResult:
        if settings.engine == QWEN3:
            raise missing_transformers()
        raise PlenioWorkerError("faster-whisper is not installed", details={"type": "PlenioDependencyError"})

    monkeypatch.setattr(lyrics_asr, "_run", fake)
    with pytest.raises(PlenioWorkerError, match="transformers 5.5 or newer"):
        lyrics_asr.run_asr(None, AsrSettings(language="en"), "sha", SimpleNamespace())


def test_other_qwen3_errors_are_not_hidden(monkeypatch: pytest.MonkeyPatch) -> None:
    from plenio.comfy import lyrics_asr

    def fake(audio: Any, settings: AsrSettings, source: str, progress: Any) -> AsrResult:
        raise PlenioWorkerError("out of memory", details={"type": "PlenioModelError"})

    monkeypatch.setattr(lyrics_asr, "_run", fake)
    with pytest.raises(PlenioWorkerError, match="out of memory"):
        lyrics_asr.run_asr(None, AsrSettings(language="en"), "sha", SimpleNamespace())
