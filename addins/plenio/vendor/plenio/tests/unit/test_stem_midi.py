"""The bass and the vocals of saved stems as MIDI notes (a user's request 2026-10-22): the notes where the stem
plays them - a note played again on the same pitch is a note of its own, a vibrato is not -, written as a
standard MIDI file at the song's tempo, next to the stem's FLAC."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from plenio.core.audio.stems import SavedStems
from plenio.core.audio.transcribe import stem_notes, write_stem_midi
from plenio.core.score import midi

RATE = 48000


def tone(hz: float, seconds: float, *, vibrato_cents: float = 0.0) -> np.ndarray:
    """A plucked tone: fast attack, slow decay - and a little vibrato when asked."""
    t = np.arange(int(seconds * RATE)) / RATE
    bend = 2 ** (vibrato_cents / 1200 * np.sin(2 * np.pi * 5.5 * t))
    phase = 2 * np.pi * np.cumsum(hz * bend) / RATE
    envelope = np.minimum(1.0, t / 0.005) * np.exp(-t * 1.5)
    return 0.5 * envelope * (np.sin(phase) + 0.3 * np.sin(2 * phase))


def test_a_bass_line_becomes_its_notes_a_repeated_note_twice() -> None:
    line = np.concatenate(
        [tone(55.0, 0.5), tone(55.0, 0.5), tone(73.42, 0.5), np.zeros(int(0.3 * RATE)), tone(82.41, 0.6)]
    )
    notes = stem_notes(np.stack([line, line]), RATE, "bass")
    assert [n.pitch for n in notes] == [33, 33, 38, 40]  # A1 A1 D2 E2
    assert [n.start for n in notes] == pytest.approx([0.0, 0.5, 1.0, 1.8], abs=0.05)
    assert all(30 <= n.velocity <= 120 for n in notes) and all(n.end > n.start for n in notes)


def test_a_sung_note_with_vibrato_stays_one_note() -> None:
    notes = stem_notes(tone(220.0, 1.2, vibrato_cents=40) * 3, RATE, "vocals")
    assert [n.pitch for n in notes] == [57]
    assert notes[0].end - notes[0].start > 1.0
    assert stem_notes(np.zeros((2, RATE)), RATE, "vocals") == ()


def test_the_notes_are_a_midi_file_at_the_songs_tempo() -> None:
    data = midi.stem_midi(
        [(0.0, 0.5, 33, 90), (1.0, 1.25, 38, 100)], tempo=120, name="bass (from the stem)", program=33
    )
    fmt, ppq, tracks = midi._read(data)
    assert fmt == 1 and ppq == midi.STEM_PPQ and [t.name for t in tracks] == ["bass (from the stem)"] * 2
    notes = [(e.tick, e.pitch, e.velocity) for e in tracks[1].events if e.kind == "on"]
    # at 120 BPM a second is two quarters: 960 ticks
    assert notes == [(0, 33, 90), (960, 38, 100)]
    tempo = next(e.data for e in tracks[0].events if e.kind == "meta" and e.meta == 0x51)
    assert int.from_bytes(tempo, "big") == 500_000
    with pytest.raises(Exception, match="cannot be written"):
        midi.stem_midi([], tempo=0, name="x")


def test_only_the_bass_and_the_vocals_are_written_next_to_their_stems(tmp_path: Path) -> None:
    bass = np.concatenate([tone(55.0, 0.5), tone(73.42, 0.5)])
    saved = SavedStems(RATE, ((("bass", np.stack([bass, bass])), ("drums", np.zeros((2, RATE)))),))
    written = write_stem_midi(tmp_path, saved, tempo=96, number=True)
    assert [(name, path.name, count) for name, path, count in written] == [("bass", "bass.mid", 2)]
    again = write_stem_midi(tmp_path, saved, tempo=96, number=True)
    assert again[0][1].name == "bass (2).mid"
    assert midi._read((tmp_path / "bass.mid").read_bytes())[2][1].name == "bass (from the stem)"
