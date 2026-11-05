"""How well a song came out, measured (owner's request 2026-10-29): what can be told from its sound and its record
without listening - a hint where to listen first, never the verdict. Every song can also be rated by ear (the
player); this rating is shown beside it as a pre-fill, faded.

From the sound (:func:`measure_audio`, numpy only):

- **chords**: how well the notes that sound fit a major or a minor chord, frame by frame (their pitch classes against
  the 24 triads);
- **clashes**: how strongly notes a semitone apart sound together - notes rubbing against each other (the energy of
  the neighbouring semitones against the notes' own, 0.5 clean, 0.9 rough);
- **key**: how clearly the song keeps to one key (its pitch classes against the Krumhansl-Kessler profiles);
- **beat**: how steady the beat is (the onsets' self-similarity at the strongest tempo between 60 and 200 BPM);
- **ending**: whether it ends - fading, or on a last chord - or stops in the middle of the sound;
- **gaps**: silent holes inside the song, where a model lost its thread;
- **clipping**: samples at full scale.

From the record (:func:`measure_record`): the lyrics as written in the singing (the share of written words heard),
the loudness against the master's aim, the true peak against its ceiling, the dynamics, the length against the
length asked for, and the Song Sheet's warnings.

:func:`rate` weighs what was measured into 0 to 5 stars in halves. What could not be measured - an instrumental's
lyrics, a song exported before its singing was heard - is left out of the weighing, not counted against the song.
The scales were set on the spread of every measure over 366 songs made with Plenio and the share of the written
words heard in about a hundred more (only their measures, never their content); over the 366 they give 1.5 to 5
stars, 3.5 in the middle.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

QUALITY_VERSION = 1
MAX_SECONDS = 420.0
"""At most the first seven minutes are measured (every Plenio song is shorter)."""
CHUNK = 96
"""Frames transformed at once (bounded memory for a long song)."""

# the major and minor key profiles of Krumhansl and Kessler (1982), from C
_MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])


@dataclass
class Part:
    """One measure: what it is, what was found (as said to a listener), its score 0..1 (``None``: not measured
    here) and its weight: in how good it sounds, or for what went wrong the stars it takes off at most."""

    key: str
    label: str
    value: str
    score: float | None
    weight: float
    note: str = ""


def _triads() -> np.ndarray:
    """The 24 major and minor triads as unit vectors over the 12 pitch classes."""
    rows = []
    for third in (4, 3):
        for root in range(12):
            row = np.zeros(12)
            row[[root, (root + third) % 12, (root + 7) % 12]] = 1.0
            rows.append(row / np.linalg.norm(row))
    return np.array(rows)


TRIADS = _triads()


def _mono(samples: np.ndarray) -> np.ndarray:
    data = np.asarray(samples, dtype=np.float32)
    if data.ndim == 2:
        data = data.mean(axis=0 if data.shape[0] <= 8 else 1)
    return np.ascontiguousarray(data.reshape(-1))


def _spectra(x: np.ndarray, n_fft: int, hop: int) -> Iterator[np.ndarray]:
    """Magnitude spectra of ``x`` (Hann window), a chunk of frames at a time."""
    window = np.hanning(n_fft).astype(np.float32)
    count = 1 + max(0, (len(x) - n_fft) // hop)
    if len(x) < n_fft:
        x = np.pad(x, (0, n_fft - len(x)))
    offsets = np.arange(n_fft)
    for start in range(0, count, CHUNK):
        index = np.arange(start, min(count, start + CHUNK))[:, None] * hop + offsets[None, :]
        yield np.abs(np.fft.rfft(x[index] * window, axis=1)).astype(np.float32)


def _chroma(x: np.ndarray, rate: int) -> np.ndarray:
    """Frames x 12: the energy of each pitch class (80 Hz - 5 kHz), about ten frames a second."""
    n_fft = 1 << max(10, round(math.log2(rate * 0.17)))
    hop = n_fft // 2
    freqs = np.fft.rfftfreq(n_fft, 1.0 / rate)
    used = (freqs >= 80.0) & (freqs <= 5000.0)
    classes = np.full(len(freqs), -1)
    classes[used] = np.round(12 * np.log2(freqs[used] / 440.0) + 69).astype(int) % 12
    mapping = np.zeros((len(freqs), 12), dtype=np.float32)
    mapping[used, classes[used]] = 1.0
    return np.concatenate([spec @ mapping for spec in _spectra(x, n_fft, hop)], axis=0)


def _onsets(x: np.ndarray, rate: int) -> tuple[np.ndarray, float]:
    """The onset strength (spectral flux of the log spectrum) and its frames per second."""
    factor = max(1, round(rate / 11025))
    small = x[: len(x) - len(x) % factor].reshape(-1, factor).mean(axis=1) if factor > 1 else x
    flux = []
    previous: np.ndarray | None = None
    for spec in _spectra(small, 1024, 256):
        logs = np.log1p(100.0 * spec)
        stacked = logs if previous is None else np.vstack([previous, logs])
        diff = np.maximum(0.0, np.diff(stacked, axis=0)).sum(axis=1)
        flux.append(diff if previous is not None else np.concatenate([[0.0], diff]))
        previous = logs[-1:]
    return np.concatenate(flux).astype(np.float64), rate / factor / 256


def _beat(onsets: np.ndarray, fps: float) -> float:
    """How strongly the onsets repeat at one tempo (60-200 BPM): the autocorrelation's highest peak, 0..1."""
    if len(onsets) < fps * 8:
        return 0.0
    width = max(1, int(fps))
    trend = np.convolve(onsets, np.ones(width) / width, mode="same")
    e = onsets - trend
    e -= e.mean()
    n = len(e)
    spectrum = np.fft.rfft(e, 2 * n)
    acf = np.fft.irfft(spectrum * np.conj(spectrum))[:n]
    if acf[0] <= 0:
        return 0.0
    acf /= acf[0]
    low, high = int(fps * 0.3), min(n - 1, int(fps * 1.0) + 1)
    return float(np.clip(acf[low:high].max(), 0.0, 1.0)) if high > low else 0.0


def _windows_rms(x: np.ndarray, rate: int, seconds: float = 0.05) -> np.ndarray:
    size = max(1, int(rate * seconds))
    usable = len(x) - len(x) % size
    if usable <= 0:
        return np.zeros(1)
    rms: np.ndarray = np.sqrt(np.mean(x[:usable].reshape(-1, size) ** 2, axis=1) + 1e-12)
    return rms


def measure_audio(samples: np.ndarray, rate: int) -> dict[str, float]:
    """The measures of a song's sound (``samples``: channels x samples or samples, -1..1)."""
    whole = np.asarray(samples, dtype=np.float32)
    clipped = float(np.mean(np.abs(whole) >= 0.999)) if whole.size else 0.0
    x = _mono(whole)[: int(rate * MAX_SECONDS)]
    out: dict[str, float] = {"seconds": len(x) / rate, "clipped": clipped}
    if len(x) < rate * 4:
        return out
    # the notes: frames with sound, their pitch classes
    chroma = _chroma(x, rate)
    energy = chroma.sum(axis=1)
    sounding = chroma[energy > 0.1 * np.percentile(energy, 90)] if energy.size else chroma
    if len(sounding):
        unit = sounding / (np.linalg.norm(sounding, axis=1, keepdims=True) + 1e-9)
        out["chords"] = float(np.mean((unit @ TRIADS.T).max(axis=1)))
        share = sounding / (sounding.sum(axis=1, keepdims=True) + 1e-9)
        rubbing = (share * np.roll(share, -1, axis=1)).sum(axis=1) / ((share**2).sum(axis=1) + 1e-9)
        out["clashes"] = float(np.median(rubbing))
        profile = share.mean(axis=0)
        best = -1.0
        for keys in (_MAJOR, _MINOR):
            for shift in range(12):
                best = max(best, float(np.corrcoef(profile, np.roll(keys, shift))[0, 1]))
        out["key"] = best
    # the beat
    onsets, fps = _onsets(x, rate)
    out["beat"] = _beat(onsets, fps)
    # the end, and holes inside
    rms = _windows_rms(x, rate)
    loud = rms[rms > 1e-4]
    median = float(np.median(loud)) if loud.size else 0.0
    if median > 0:
        last = rms[-max(1, int(0.3 / 0.05)) :]
        out["ending"] = float(np.mean(last) / median)
        quiet = rms < 0.02 * median
        inner = slice(int(len(rms) * 0.05), int(len(rms) * 0.95))
        gaps = 0
        run = 0
        for silent in quiet[inner]:
            run = run + 1 if silent else 0
            if run == int(1.5 / 0.05):
                gaps += 1
        out["gaps"] = float(gaps)
    return out


def _length_asked(record: Mapping[str, Any]) -> float | None:
    """The length the brief asked for, in seconds (``about 2:30``, ``standard (about 3:00)``)."""
    for node in (record.get("prompt") or {}).values():
        if isinstance(node, Mapping) and node.get("class_type") == "PlenioSongBrief":
            text = str((node.get("inputs") or {}).get("length") or "")
            found = re.search(r"(\d+):(\d\d)", text)
            if found:
                return int(found.group(1)) * 60 + int(found.group(2))
    return None


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def measure_record(record: Mapping[str, Any]) -> dict[str, Any]:
    """The measures a release record holds: the lyrics heard, the loudness, the length, the Song Sheet's warnings."""
    out: dict[str, Any] = {}
    # the share of the written words heard in the singing: the timed singing's, else the take Best Take kept
    for entry in record.get("timing") or []:
        sung = entry.get("sung") if isinstance(entry, Mapping) else None
        if isinstance(sung, Mapping) and isinstance(sung.get("written_heard"), (int, float)):
            out["lyrics"] = float(sung["written_heard"])
    if "lyrics" not in out:
        for report in record.get("reports") or []:
            data = (
                report.get("data")
                if isinstance(report, Mapping) and report.get("kind") == "best_take"
                else None
            )
            scores = data.get("scores") if isinstance(data, Mapping) else None
            kept = data.get("kept") if isinstance(data, Mapping) else None
            if isinstance(scores, list) and isinstance(kept, int) and 1 <= kept <= len(scores):
                if isinstance(scores[kept - 1], (int, float)):
                    out["lyrics"] = float(scores[kept - 1])
    audio = record.get("audio") or {}
    loudness = next((x for x in audio.get("loudness") or [] if isinstance(x, Mapping)), None)
    if loudness:
        for name in ("integrated_lufs", "true_peak_dbtp", "loudness_range_lu"):
            value = loudness.get(name)
            if isinstance(value, (int, float)) and math.isfinite(value):
                out[name] = float(value)
    target = ceiling = None
    warnings = 0
    for report in record.get("reports") or []:
        if not isinstance(report, Mapping):
            continue
        data = report.get("data") or {}
        if not isinstance(data, Mapping):
            continue
        if report.get("kind") == "loudness":
            # the master's aim: its first item's own target, else the number in the choice ("streaming (-14 LUFS, ...")
            items = [i for i in data.get("items") or [] if isinstance(i, Mapping)]
            aim = items[0].get("target") if items else None
            if isinstance(aim, Mapping):
                target = _number(aim.get("integrated_lufs"))
                ceiling = _number(aim.get("ceiling_dbtp"))
            if target is None:
                found = re.search(r"(-?\d+(?:\.\d+)?)\s*LUFS", str(data.get("target") or ""))
                target = float(found.group(1)) if found else None
        if report.get("kind") == "song_sheet":
            warnings += sum(
                1
                for finding in data.get("findings") or []
                if isinstance(finding, Mapping) and finding.get("severity") == "warning"
            )
    if target is not None:
        out["target_lufs"] = target
    if ceiling is not None:
        out["ceiling_dbtp"] = ceiling
    out["warnings"] = warnings
    asked = _length_asked(record)
    seconds = audio.get("seconds")
    if asked and isinstance(seconds, (int, float)) and seconds > 0:
        out["length_asked"] = float(asked)
        out["length"] = float(seconds)
    vocals = next(
        (
            str((n.get("inputs") or {}).get("vocals") or "")
            for n in (record.get("prompt") or {}).values()
            if isinstance(n, Mapping) and n.get("class_type") in ("PlenioSongBrief", "PlenioCoverBrief")
        ),
        "",
    )
    out["instrumental"] = vocals == "instrumental"
    return out


def _scale(value: float, bad: float, good: float) -> float:
    """``value`` from ``bad`` (0) to ``good`` (1), clamped (either may be the larger)."""
    return float(min(1.0, max(0.0, (value - bad) / (good - bad))))


def _clock(seconds: float) -> str:
    seconds = max(0, round(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


def rate(measures: Mapping[str, Any]) -> dict[str, Any]:
    """The stars (0-5 in halves) of what was measured, with every measure's part.

    How good it sounds - the lyrics sung as written, the harmony, the clashes, the key, the beat - gives the stars
    from 1 to 5 (each measure weighed, what was not measured left out); what went wrong - an ending cut off, holes,
    a song much shorter than asked, clipping, a loudness off its aim, no headroom, the Song Sheet's warnings - takes
    stars off. The scales go from how the weaker to how the better songs made with Plenio measure."""
    m = measures
    quality: list[Part] = []
    faults: list[Part] = []
    if "lyrics" in m and not m.get("instrumental"):
        heard = float(m["lyrics"])
        quality.append(
            Part(
                "lyrics",
                "Lyrics sung as written",
                f"{round(heard * 100)} % of the written words heard in the singing",
                _scale(heard, 0.55, 0.95),
                0.4,
            )
        )
    if "chords" in m:
        quality.append(
            Part(
                "chords",
                "Harmony",
                f"the notes fit a chord to {round(m['chords'] * 100)} %",
                _scale(m["chords"], 0.66, 0.78),
                0.2,
                "how well the notes that sound fit a major or a minor chord",
            )
        )
    if "clashes" in m:
        quality.append(
            Part(
                "clashes",
                "Few clashes",
                f"semitone friction {m['clashes']:.2f} (0.5 clean, 0.9 rough)",
                _scale(m["clashes"], 0.88, 0.5),
                0.15,
                "notes rubbing against each other: the fewer, the cleaner the harmony",
            )
        )
    if "key" in m:
        quality.append(
            Part(
                "key",
                "In one key",
                f"{round(m['key'] * 100)} % like one key",
                _scale(m["key"], 0.6, 0.9),
                0.12,
                "how clearly the song keeps to its key",
            )
        )
    if "beat" in m:
        quality.append(
            Part(
                "beat",
                "Steady beat",
                f"{round(m['beat'] * 100)} %",
                _scale(m["beat"], 0.15, 0.6),
                0.13,
                "how evenly the beat goes on (a calm song may have little of it)",
            )
        )
    # what went wrong takes stars off: ``weight`` is the most it takes, at a score of 0
    if "ending" in m:
        faults.append(
            Part(
                "ending",
                "Ending",
                "stops in the middle of the sound" if m["ending"] > 0.4 else "ends",
                _scale(m["ending"], 0.5, 0.1),
                1.0,
                "a song that stops mid-sound was often cut off by the model",
            )
        )
    if "gaps" in m:
        gaps = int(m["gaps"])
        faults.append(
            Part(
                "gaps",
                "No holes",
                "none" if not gaps else f"{gaps} silent {'gap' if gaps == 1 else 'gaps'} inside",
                max(0.0, 1.0 - 0.5 * gaps),
                1.5,
            )
        )
    if "length_asked" in m and "length" in m:
        share = float(m["length"]) / float(m["length_asked"])
        faults.append(
            Part(
                "length",
                "Length",
                f"{_clock(m['length'])} of {_clock(m['length_asked'])} asked",
                _scale(share, 0.5, 0.8),
                1.0,
            )
        )
    if "clipped" in m:
        clipped = float(m["clipped"])
        faults.append(
            Part(
                "clipping",
                "No clipping",
                "none" if clipped < 1e-6 else f"{clipped * 100:.3f} % of the samples",
                _scale(math.log10(max(clipped, 1e-7)), -3.0, -5.0),
                0.5,
            )
        )
    if "integrated_lufs" in m:
        target = float(m.get("target_lufs", -14.0))
        off = abs(float(m["integrated_lufs"]) - target)
        faults.append(
            Part(
                "loudness",
                "Loudness",
                f"{m['integrated_lufs']:.1f} LUFS (aim {target:g})",
                _scale(off, 5.0, 1.0),
                0.5,
            )
        )
    if "true_peak_dbtp" in m:
        peak = float(m["true_peak_dbtp"])
        ceiling = float(m.get("ceiling_dbtp", -1.0))
        faults.append(
            Part(
                "peak",
                "Headroom",
                f"true peak {peak:.1f} dBTP (ceiling {ceiling:g})",
                _scale(peak, ceiling + 1.5, ceiling),
                0.25,
            )
        )
    if "loudness_range_lu" in m:
        lra = float(m["loudness_range_lu"])
        faults.append(
            Part(
                "dynamics",
                "Dynamics",
                f"{lra:.1f} LU of loudness range",
                1.0 if 2.0 <= lra <= 18.0 else 0.5,
                0.25,
            )
        )
    if m.get("warnings"):
        count = int(m["warnings"])
        faults.append(
            Part(
                "warnings",
                "Song Sheet",
                f"{count} {'warning' if count == 1 else 'warnings'}",
                max(0.0, 1.0 - 0.25 * count),
                0.5,
                "what the Song Sheet found in the lyrics and the score before the song was made",
            )
        )
    weight = sum(p.weight for p in quality if p.score is not None)
    if not weight:
        return {
            "version": QUALITY_VERSION,
            "stars": None,
            "score": None,
            "parts": [asdict(p) for p in quality + faults],
        }
    score = sum(p.weight * float(p.score or 0.0) for p in quality if p.score is not None) / weight
    taken = sum(p.weight * (1.0 - float(p.score)) for p in faults if p.score is not None)
    stars = min(5.0, max(0.0, 1.0 + 4.0 * score - taken))
    return {
        "version": QUALITY_VERSION,
        "stars": round(stars * 2) / 2,
        "score": round(score, 3),
        "parts": [{**asdict(p), "kind": "quality"} for p in quality]
        + [{**asdict(p), "kind": "fault"} for p in faults],
    }


def song_quality(
    samples: np.ndarray | None, rate_hz: int, record: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """The measured quality of a song - its sound (``samples`` at ``rate_hz``; ``None``: the record only) and its
    record - with the stars, every measure and its part."""
    measures: dict[str, Any] = dict(measure_record(record)) if record else {}
    if samples is not None:
        measures.update(measure_audio(samples, rate_hz))
    rated = rate(measures)
    rated["measures"] = {k: v for k, v in measures.items() if isinstance(v, (int, float, bool))}
    return rated


def summary_line(quality: Mapping[str, Any]) -> str:
    """One line for a song's details: the stars and the measures that cost the most."""
    stars = quality.get("stars")
    if stars is None:
        return ""
    weak: Sequence[Mapping[str, Any]] = sorted(
        (p for p in quality.get("parts") or [] if p.get("score") is not None and p["score"] < 0.6),
        key=lambda p: p["score"] * p["weight"] - p["weight"],
    )
    tail = f" - weakest: {', '.join(p['label'].lower() for p in weak[:2])}" if weak else ""
    return f"{stars:g} of 5 by measure{tail}"
