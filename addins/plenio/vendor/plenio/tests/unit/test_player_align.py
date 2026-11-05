"""The notation of a song follows the music (owner's reports 2026-10-16: it ran a bar behind; 2026-10-23: it
raced through an instrumental part and waited at the lyrics): the player finds where the score sits in the
recording from their pitch classes, and the score's path through it."""

from __future__ import annotations

import json
from fractions import Fraction
from pathlib import Path

import pytest

from plenio.player.align import cached_follow, estimate, follow, score_to_audio
from plenio.player.library import Library, song_detail

av = pytest.importorskip("av")
np = pytest.importorskip("numpy")

# sixteen bars of native two-voice ABC: a chord a bar (arpeggiated below) that does not come round again
# soon, a melody over it
ARPEGGIOS = ["C,4E,4G,4C4", "A,,4C,4E,4A,4", "F,,4A,,4C,4F,4", "G,,4B,,4D,4G,4"]
ARPEGGIOS += ["E,,4G,,4B,,4E,4", "D,4F,4A,4D4", "B,,,4D,4F,4B,4", "C,4E,4A,4C4"]
MELODY = ["c4e4g4e4", "a4c'4e'4c'4", "f4a4c'4a4", "g4b4d'4b4", "e4g4b4g4", "d4f4a4f4", "B4d4f4d4", "c4e4a4e4"]


def score_text() -> str:
    head = (
        "X:1\nT:\nM:4/4\nL:1/16\nQ:1/4=100\n"
        'V: Vocal clef=treble name="Vocal Melody" snm="Vocal"\n'
        'V: Ins clef=treble name="Ins Melody" snm="Inst."\nK:C\n'
    )
    blocks = []
    for k in range(4):
        bars = [(k * 4 + j) % 8 for j in range(4)]
        blocks.append("V: Vocal\n" + "|".join(MELODY[b] for b in bars) + "|\n")
        blocks.append("V: Ins\n" + "|".join(ARPEGGIOS[b] for b in bars) + "|\n")
    return head + "".join(blocks)


def render(path: Path, shift: float, left_out: tuple[float, float] | None = None) -> None:
    """The score played by sine voices, ``shift`` seconds late, into a FLAC - without the notes in the score
    seconds ``left_out`` (a take that leaves out part of its plan)."""
    from plenio.core.score import canonical

    score = canonical.from_abc(score_text())
    rate = 22050
    length = score.seconds(score.total) + shift + 2
    out = np.zeros(int(rate * length), dtype=np.float32)
    for note in [*score.vocal, *score.ins]:
        start = score.seconds(note.onset) + shift
        if left_out is not None:
            if left_out[0] <= score.seconds(note.onset) < left_out[1]:
                continue
            if score.seconds(note.onset) >= left_out[1]:
                start -= left_out[1] - left_out[0]
        seconds = score.seconds(note.duration)
        t = np.arange(int(rate * seconds)) / rate
        freq = 440 * 2 ** ((note.pitch - 69) / 12)
        tone = sum(np.sin(2 * np.pi * freq * k * t) / k for k in (1, 2, 3)) * np.exp(-t * 1.5) * 0.08
        a = int(start * rate)
        out[a : a + len(tone)] += tone[: len(out) - a].astype(np.float32)
    with av.open(str(path), "w") as container:
        stream = container.add_stream("flac", rate=rate)
        stream.layout = "mono"
        frame = av.AudioFrame.from_ndarray(out[None, :], format="flt", layout="mono")
        frame.sample_rate = rate
        frame.pts = 0
        frame.time_base = Fraction(1, rate)
        for packet in [*stream.encode(frame), *stream.encode(None)]:
            container.mux(packet)


def test_the_score_is_found_in_its_recording(tmp_path: Path) -> None:
    render(tmp_path / "late.flac", 1.4)
    found = estimate(tmp_path / "late.flac", score_text())
    assert found is not None
    assert found["warp"][1] == pytest.approx(1.4, abs=0.15)
    assert len(found["anchors"]) >= 2
    for audio, score in found["anchors"]:
        assert audio - score == pytest.approx(1.4, abs=0.2)
    render(tmp_path / "early.flac", 0.0)
    assert estimate(tmp_path / "early.flac", score_text())["warp"][1] == pytest.approx(0.0, abs=0.15)


def test_the_score_is_followed_where_the_take_leaves_out_part_of_it(tmp_path: Path) -> None:
    # bars 5 and 6 (9.6 to 14.4 s of score) are not played: after them the take is 4.8 s ahead of its plan
    render(tmp_path / "cut.flac", 1.0, left_out=(9.6, 14.4))
    found = follow(tmp_path / "cut.flac", score_text(), [1.0, 1.0])
    assert found is not None and found["match"] > 0.2
    assert score_to_audio(4.0, found) == pytest.approx(5.0, abs=0.3)
    assert score_to_audio(20.0, found) == pytest.approx(20.0 + 1.0 - 4.8, abs=0.3)
    assert score_to_audio(30.0, found) == pytest.approx(30.0 + 1.0 - 4.8, abs=0.3)
    # the anchors are few: a straight line where the take keeps to the tempo
    assert len(found["anchors"]) < 12
    assert cached_follow(tmp_path / "cut.flac", score_text(), tmp_path / "cache", [1.0, 1.0]) == found
    assert cached_follow(tmp_path / "cut.flac", score_text(), tmp_path / "cache", [1.0, 1.0]) == found


def test_no_estimate_where_score_and_recording_have_nothing_in_common(tmp_path: Path) -> None:
    rate = 22050
    noise = (np.random.default_rng(1).standard_normal(rate * 40) * 0.05).astype(np.float32)
    with av.open(str(tmp_path / "noise.flac"), "w") as container:
        stream = container.add_stream("flac", rate=rate)
        stream.layout = "mono"
        frame = av.AudioFrame.from_ndarray(noise[None, :], format="flt", layout="mono")
        frame.sample_rate = rate
        frame.pts = 0
        frame.time_base = Fraction(1, rate)
        for packet in [*stream.encode(frame), *stream.encode(None)]:
            container.mux(packet)
    assert estimate(tmp_path / "noise.flac", score_text()) is None
    assert estimate(tmp_path / "missing.flac", score_text()) is None
    assert follow(tmp_path / "noise.flac", score_text(), [1.0, 0.0]) is None
    assert follow(tmp_path / "missing.flac", score_text()) is None


def test_a_song_without_measured_times_gets_its_notation_placed_and_kept(tmp_path: Path) -> None:
    folder = tmp_path / "output"
    folder.mkdir()
    render(folder / "Old.flac", 2.0)
    record = {
        "schema": "plenio.release/1",
        "title": "Old",
        "files": [{"name": "Old.flac", "format": "flac"}],
        "documents": {"score": {"text": score_text()}},
    }
    (folder / "Old.plenio.json").write_text(json.dumps(record), encoding="utf-8")
    library = Library([folder])
    library.scan(force=True)
    song = library.song(library.songs()[0]["id"])
    assert song is not None
    assert "estimated" not in song_detail(song)["notation"]  # without a cache: as before
    detail = song_detail(song, cache=tmp_path / "cache")
    assert detail["notation"]["estimated"] is True
    assert detail["notation"]["warp"][1] == pytest.approx(2.0, abs=0.15)
    assert list((tmp_path / "cache" / "align").glob("*.json"))
    # the notation follows the score's path through the music, kept in the cache
    assert detail["notation"]["followed"] is True
    assert (
        detail["notation"]["anchors"]
        == cached_follow(song.files["audio"], score_text(), tmp_path / "cache")["anchors"]
    )
    for audio, score in detail["notation"]["anchors"][1:]:
        assert audio - score == pytest.approx(2.0, abs=0.2)


def test_a_song_with_measured_times_follows_the_music_near_its_warp(tmp_path: Path) -> None:
    folder = tmp_path / "output"
    folder.mkdir()
    render(folder / "New.flac", 1.0, left_out=(9.6, 14.4))
    line = {"text": "la", "start": 2.0, "end": 3.0, "units": [[2.0, 2, 1.0]]}
    record = {
        "schema": "plenio.release/1",
        "title": "New",
        "files": [{"name": "New.flac", "format": "flac"}],
        "documents": {"score": {"text": score_text()}},
        "timing": [{"take": "", "timing": "measured", "warp": [1.0, 1.0], "lines": [line]}],
    }
    (folder / "New.plenio.json").write_text(json.dumps(record), encoding="utf-8")
    library = Library([folder])
    library.scan(force=True)
    song = library.song(library.songs()[0]["id"])
    assert song is not None
    notation = song_detail(song, cache=tmp_path / "cache")["notation"]
    assert notation["followed"] is True and "estimated" not in notation
    assert notation["warp"] == [1.0, 1.0]  # the measured one
    assert score_to_audio(25.0, notation) == pytest.approx(25.0 + 1.0 - 4.8, abs=0.3)
