"""A one-voice stem as notes - the bass and the vocals of a separated song, for a DAW (a user's request of
2026-10-22: "export even more MIDI tracks ... bass or other lead instruments").

The pitch comes from the YIN tracker of ``core.audio.pitch`` (the curve Sung Pitch shows), in the stem's
range (``RANGES``); the notes start where the pitch moves to another semitone and where the stem's band
gets a new attack (the log-spectral flux has a peak - a bass plays a note again, a singer starts a new
syllable on the same pitch). A note shorter than ``MIN_NOTE_S`` is left out; its velocity follows its level.

The notes stay where the recording has them - no grid: a YuE2 render runs a little ahead of or behind its
score, and the stems in a DAW are at the recording's times too. Measured on five renders (pop, electronic,
rock, hip-hop, singer-songwriter; ``docs/test-reports/2026-10-22-stems-midi.md``): 93-100 % of the bass
notes' time is on a tone of the score's chord there. Only one voice at a time: the drums and the *other* stem
(guitars, keys, pads - several notes at once) are no material for it.

Pure NumPy and SciPy, no model.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from ..dependencies import require
from ..files import atomic_write_bytes
from ..release import plan_release, safe_filename
from ..score.midi import STEM_PROGRAMS, stem_midi
from . import pitch
from .stems import SavedStems

RANGES: dict[str, tuple[float, float]] = {"bass": (35.0, 400.0), "vocals": (70.0, 1000.0)}
"""The stems that are transcribed and their pitch range (Hz): a five-string bass's low B is 31 Hz, its top
note about 400 Hz; the voices from a low bass to a high soprano."""
MIN_NOTE_S = 0.07
SAME_NOTE = 0.75
"""Semitones the pitch may wander inside one note (vibrato, a slide's start)."""
ONSET_FFT = 2048
ONSET_SPREAD_S = 0.25
"""The median the flux is measured against: half a second around each moment."""
ONSET_SHARE = 0.3
"""A peak of the flux above this share of the song's strongest attacks (99th percentile) starts a note."""
ONSET_GAP_S = 0.08
FRAME_S = pitch.HOP / pitch.RATE


@dataclass(frozen=True)
class StemNote:
    start: float
    """Seconds into the stem."""
    end: float
    pitch: int
    """MIDI number."""
    velocity: int


def _attacks(mono: np.ndarray, low: float, high: float) -> set[int]:
    """The frames (10 ms) where the band ``low`` ... ``high`` Hz gets a new attack."""
    count = len(mono) // pitch.HOP + 1
    padded = np.pad(mono, (ONSET_FFT // 2, ONSET_FFT))
    window = np.hanning(ONSET_FFT)
    freqs = np.fft.rfftfreq(ONSET_FFT, 1 / pitch.RATE)
    band = (freqs >= low) & (freqs <= high)
    logs = np.zeros((count, int(band.sum())))
    for start in range(0, count, 1024):
        index = (
            np.arange(ONSET_FFT)[None, :] + pitch.HOP * np.arange(start, min(count, start + 1024))[:, None]
        )
        logs[start : start + len(index)] = np.log1p(
            100 * np.abs(np.fft.rfft(padded[index] * window, axis=1))[:, band]
        )
    flux = np.maximum(np.diff(logs, axis=0, prepend=logs[:1]), 0.0).sum(axis=1)
    strength = flux - require("scipy.ndimage").median_filter(
        flux, size=max(3, int(2 * ONSET_SPREAD_S / FRAME_S) | 1), mode="nearest"
    )
    threshold = ONSET_SHARE * float(np.percentile(strength, 99)) if len(strength) else 0.0
    gap = max(1, round(ONSET_GAP_S / FRAME_S))
    found: set[int] = set()
    last = -gap
    for i in range(1, len(strength) - 1):
        if (
            strength[i] > threshold
            and strength[i] >= strength[i - 1]
            and strength[i] >= strength[i + 1]
            and i - last >= gap
        ):
            found.add(i)
            last = i
    return found


def stem_notes(samples: Any, sample_rate: Any, kind: str) -> tuple[StemNote, ...]:
    """The notes of a one-voice stem (``kind``: a key of ``RANGES``), in time order."""
    low, high = RANGES[kind]
    mono = pitch.mono_16k(samples, sample_rate)
    if len(mono) < pitch.FRAME:
        return ()
    midi, rms = pitch.curve(mono, low, high)
    attacks = _attacks(mono, low * 0.9, high * 4)
    loud = float(np.percentile(rms, 95)) or 1e-9
    notes: list[StemNote] = []
    first = -1
    values: list[float] = []

    def close(stop: int) -> None:
        if first >= 0 and (stop - first) * FRAME_S >= MIN_NOTE_S:
            level = float(np.sqrt(np.mean(rms[first:stop] ** 2)))
            velocity = int(np.clip(40 + 60 * level / loud, 30, 120))
            notes.append(
                StemNote(
                    round(first * FRAME_S, 3),
                    round(stop * FRAME_S, 3),
                    int(round(float(np.median(values)))),
                    velocity,
                )
            )

    for i, value in enumerate(midi):
        voiced = bool(np.isfinite(value))
        if first >= 0 and voiced and i not in attacks and abs(value - float(np.median(values))) < SAME_NOTE:
            values.append(float(value))
            continue
        close(i)
        first, values = (i, [float(value)]) if voiced else (-1, [])
    close(len(midi))
    return tuple(notes)


def write_stem_midi(
    folder: Path, saved: SavedStems, *, tempo: float, meter: tuple[int, int] = (4, 4), number: bool
) -> list[tuple[str, Path, int]]:
    """The saved strips of one voice - the bass and the vocals (``transcribe.RANGES``) - as MIDI files next to
    their FLAC: ``<strip>.mid`` (``<strip> take N.mid`` for a batch), the notes where the stem plays them at
    ``tempo``. ``number``: a file that exists gets `` (2)`` ... Returns ``(strip, path, notes)`` per file."""
    written: list[tuple[str, Path, int]] = []
    batch = len(saved.takes) > 1
    for index, take in enumerate(saved.takes):
        for name, signal in take:
            kind = name.strip().lower()
            if kind not in RANGES:
                continue
            notes = stem_notes(signal, saved.rate, kind)
            label = safe_filename(name) + (f" take {index + 1}" if batch else "")
            base = plan_release(folder, label, [".mid"], collision="number" if number else "overwrite")
            target = base.with_name(base.name + ".mid")
            data = stem_midi(
                [(n.start, n.end, n.pitch, n.velocity) for n in notes],
                tempo=tempo,
                meter=meter,
                name=f"{name} (from the stem)",
                program=STEM_PROGRAMS.get(kind),
            )
            atomic_write_bytes(target, data)
            written.append((name, target, len(notes)))
    return written
