"""Where every bar of a score lies in its take: the audio is the master, and the session's tempo map follows it.

A YuE2 render keeps no steady tempo: against the best straight line its beats wander by a quarter of a second in
the median song and by a second in the worst (measured on the owner's songs), slowly and smoothly. No single
tempo, however exact, keeps a metronome on such a take. So every pulse of the score is looked for in the audio:
dynamic programming over the audio's onsets, near where the song's warp puts the pulse, with steady intervals.

Onsets alone find the pulse but not which pulse it is: on the owner's songs they often lay whole beats off, with
the score's notes no longer on the music. Two things say which it is: the pitch classes the score has on each
pulse against those of the audio there, and the sung words where they were measured.

Only numpy here, and only the arrays the caller gives: :func:`find_bars` needs neither ComfyUI nor Plenio.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

SAMPLE_RATE = 22050
HOP = 128
FRAMES_PER_SECOND = SAMPLE_RATE / HOP
WINDOW = 256
"""Short: with 1024 samples the same clicks came out from 39 ms early to 52 ms late by their sound; with these
they come out alike, whatever the sound."""
ONSET_OFFSET = 0.0065
"""A frame's time is its window's start and an onset shows as soon as it enters the window: measured on kicks,
snares and noise bursts, this much early, with a spread of 1.5 ms."""
BAND_SECONDS = 2.5
"""How far from the warp's straight line a pulse is looked for (the worst wander measured: about a second)."""
INTERVAL = 0.14
"""How far one interval between pulses may differ from what is expected there, as a share of it."""
FIRST_TIGHTNESS, THEN_TIGHTNESS = 300.0, 800.0
"""The cost of an uneven interval: looser for the first pass, tighter once the song's own tempo is known."""
HARMONY_WEIGHT = 16.0
"""What a full match of pitch classes is worth, against onsets of unit variance. On 240 of the owner's songs, 4 to
32: from 11 songs to 4 whose notes match the music clearly worse than on the straight line, with hardly any change
in how exactly the pulses lie (they come from the onsets: a match of pitch classes is broad in time)."""
SUNG_WEIGHT = 1.0
"""What being half a beat away from where the singing puts a pulse costs at most."""
LINE_PULL = 0.05
"""What a whole pulse away from the warp's line costs: too little to stop the real wander (a second, in a song's
hundreds of pulses, is outweighed by their onsets), enough that a steady rhythm, the same a beat later, stays
where the song was measured to lie."""
SMOOTH_PULSES = 4
"""A pulse's time comes from the pulses this near: without the jitter of single onsets."""
TEMPO_SWING = 0.25
"""How far a bar's tempo may lie from the score's and still be believed."""
MATCH_MARGIN = 0.05
"""How much worse than the straight line the map's notes may match the music and still be believed."""


def onset_envelope(samples: Any) -> Any:
    """Spectral flux of log magnitudes in four bands, at ``FRAMES_PER_SECOND``, of unit variance."""
    import numpy as np

    count = 1 + (len(samples) - WINDOW) // HOP
    if count <= 1:
        return np.zeros(0, dtype=np.float32)
    window = np.hanning(WINDOW).astype(np.float32)
    bins = np.fft.rfftfreq(WINDOW, 1 / SAMPLE_RATE)
    bands = [((30, 200), 1.5), ((200, 800), 0.75), ((800, 3000), 1.0), ((3000, 10000), 1.0)]
    masks = [((bins >= low) & (bins < high), weight) for (low, high), weight in bands]
    envelope = np.zeros(count, dtype=np.float32)
    previous = None
    # in blocks, so that a long song does not need a large array at once
    for start in range(0, count, 2048):
        stop = min(count, start + 2048)
        index = np.arange(WINDOW)[None, :] + HOP * np.arange(start, stop)[:, None]
        magnitude = np.log1p(30 * np.abs(np.fft.rfft(samples[index] * window[None, :], axis=1)))
        before = np.vstack([magnitude[:1] if previous is None else previous[None, :], magnitude[:-1]])
        flux = np.maximum(0, magnitude - before)
        envelope[start:stop] = sum(weight * flux[:, mask].mean(axis=1) for mask, weight in masks)
        previous = magnitude[-1]
    # without the slow level: a local mean over about three seconds
    width = int(3 * FRAMES_PER_SECOND) | 1
    envelope = np.maximum(envelope - np.convolve(envelope, np.ones(width) / width, mode="same"), 0)
    return envelope / max(1e-9, float(envelope.std()))


def pulses_of(meters: Sequence[tuple[int, int]]) -> tuple[Any, Any]:
    """The score's pulses in quarter notes, and the index of each measure's first pulse (one value more: the
    end). A pulse is what is felt: quarters over x/4, three eighths where eighths come in threes, else eighths."""
    import numpy as np

    at = 0.0
    pulses: list[float] = []
    firsts: list[int] = []
    for numerator, denominator in meters:
        length = numerator * 4 / denominator
        if denominator == 8 and numerator % 3 == 0:
            step = 1.5
        else:
            step = 4 / denominator
        firsts.append(len(pulses))
        count = max(1, round(length / step))
        pulses.extend(at + k * length / count for k in range(count))
        at += length
    firsts.append(len(pulses))
    pulses.append(at)
    return np.array(pulses), np.array(firsts)


class _Emission:
    """What a pulse at a frame is worth: the onset there, the pitch classes of the pulse, the singing."""

    def __init__(self, envelope: Any, harmony: Any, wanted: Any, sung: Any) -> None:
        import numpy as np

        self.envelope = envelope
        self.wanted = wanted
        self.sung = sung
        self.sums = None
        if harmony is not None and wanted is not None and len(harmony):
            frames = np.minimum((np.arange(len(envelope)) / FRAMES_PER_SECOND * harmony.rate).astype(int), len(harmony.chroma) - 1)
            self.sums = np.vstack([np.zeros((1, 12)), np.cumsum(harmony.chroma[frames].astype(np.float64), axis=0)])

    def at(self, pulse: int, low: int, high: int, length: float) -> Any:
        import numpy as np

        centre = (low + high - 1) / 2
        out = -LINE_PULL * ((np.arange(low, high) - centre) / (length * FRAMES_PER_SECOND)) ** 2
        a, b = max(0, low), min(len(self.envelope), high)
        if b > a:
            out[a - low : b - low] += self.envelope[a:b]
        if self.sums is not None and self.wanted[pulse].any():
            frames = np.arange(low, high)
            end = frames + max(1, int(length * FRAMES_PER_SECOND))
            have = self.sums[np.clip(end, 0, len(self.sums) - 1)] - self.sums[np.clip(frames, 0, len(self.sums) - 1)]
            norm = np.linalg.norm(have, axis=1)
            norm[norm == 0] = 1
            out += HARMONY_WEIGHT * (have @ self.wanted[pulse]) / norm
        if self.sung is not None and not np.isnan(self.sung[pulse]):
            distance = (np.arange(low, high) / FRAMES_PER_SECOND - self.sung[pulse]) / (0.5 * length)
            out -= SUNG_WEIGHT * np.minimum(1.0, distance**2)
        return out


def _path(emission: _Emission, line: Any, intervals: Any, tightness: float) -> Any:
    """The best time for every pulse, near ``line``, its intervals near ``intervals``."""
    import numpy as np

    band = int(BAND_SECONDS * FRAMES_PER_SECOND)
    size = 2 * band + 1
    centres = np.round(line * FRAMES_PER_SECOND).astype(np.int64)
    best = emission.at(0, int(centres[0]) - band, int(centres[0]) + band + 1, float(intervals[1]))
    back = np.zeros((len(line), size), dtype=np.int32)
    for j in range(1, len(line)):
        expected = float(intervals[j]) * FRAMES_PER_SECOND
        steps = np.arange(max(1, int(expected * (1 - INTERVAL))), int(expected * (1 + INTERVAL)) + 2)
        cost = -tightness * np.log(steps / expected) ** 2
        moved = int(centres[j] - centres[j - 1])
        candidates = np.full((len(steps), size), -np.inf)
        for i, step in enumerate(steps):
            # frame f at this pulse came from frame f - step: index k here is index k + moved - step there
            shift = moved - int(step)
            if shift >= size or shift <= -size:
                continue
            if shift >= 0:
                candidates[i, : size - shift] = best[shift:] + cost[i]
            else:
                candidates[i, -shift:] = best[:shift] + cost[i]
        which = candidates.argmax(axis=0)
        best = candidates[which, np.arange(size)] + emission.at(j, int(centres[j]) - band, int(centres[j]) + band + 1, float(intervals[j]))
        back[j] = steps[which]
    k = int(best.argmax())
    frames = np.zeros(len(line), dtype=np.int64)
    for j in range(len(line) - 1, -1, -1):
        frames[j] = int(centres[j]) - band + k
        if j:
            k = int(np.clip(k + int(centres[j] - centres[j - 1]) - int(back[j, k]), 0, size - 1))
    return frames / FRAMES_PER_SECOND


def _smooth(x: Any, times: Any, reach: int) -> Any:
    """Each time from a robust straight line through the pulses within ``reach``."""
    import numpy as np

    out = np.zeros(len(times))
    for j in range(len(times)):
        a, b = max(0, j - reach), min(len(times), j + reach + 1)
        xs, ys = x[a:b], times[a:b]
        weight = np.ones(len(xs))
        slope, cut = 0.0, float(times[j])
        for _ in range(3):
            slope, cut = np.polyfit(xs, ys, 1, w=np.sqrt(weight))
            rest = ys - (slope * xs + cut)
            spread = max(0.005, float(np.median(np.abs(rest))))
            weight = 1.0 / np.maximum(1.0, np.abs(rest) / (2.0 * spread))
        out[j] = slope * x[j] + cut
    return out


class Harmony:
    """The audio's pitch classes: ``chroma`` (frames, 12) at ``rate`` frames a second."""

    def __init__(self, chroma: Any, rate: float) -> None:
        self.chroma = chroma
        self.rate = rate

    def __len__(self) -> int:
        return len(self.chroma)


def find_bars(
    envelope: Any,
    meters: Sequence[tuple[int, int]],
    bpm: float,
    warp: Sequence[float],
    harmony: Harmony | None = None,
    wanted: Any = None,
    anchors: Any = None,
) -> Any:
    """The time in the audio of every measure's start and of the score's end (``len(meters) + 1`` values).

    ``warp``: ``t_audio = a t_score + b``, where the song roughly lies. ``wanted``: per pulse of
    :func:`pulses_of`, the score's pitch classes (a unit vector or zeros), or nothing. ``anchors``: measured
    pairs ``[t_audio, t_score]`` of sung words, or nothing.
    """
    import numpy as np

    a, b = float(warp[0]), float(warp[1])
    pulses, firsts = pulses_of(meters)
    score_seconds = pulses * 60.0 / bpm
    line = a * score_seconds + b
    nominal = np.diff(score_seconds, prepend=score_seconds[0] - (score_seconds[1] - score_seconds[0]))
    sung = None
    if anchors is not None and len(anchors):
        sung = np.full(len(pulses), np.nan)
        for j, t in enumerate(score_seconds):
            near = anchors[np.abs(anchors[:, 1] - t) < 10.0]
            if len(near) >= 3:
                sung[j] = a * t + b + float(np.median(near[:, 0] - (a * near[:, 1] + b)))
    emission = _Emission(envelope, harmony, wanted, sung)
    times = _path(emission, line, a * nominal, FIRST_TIGHTNESS)
    for _ in range(2):
        # the song's own tempo where it is: local slopes, smoothed
        slopes = np.gradient(_smooth(score_seconds, times, 8), score_seconds)
        slopes = np.convolve(np.pad(slopes, 8, mode="edge"), np.ones(17) / 17, mode="valid")
        times = _path(emission, line, slopes * nominal, THEN_TIGHTNESS)
    return _smooth(score_seconds, times, SMOOTH_PULSES)[firsts] + ONSET_OFFSET


def believable(bars: Any, meters: Sequence[tuple[int, int]], bpm: float) -> bool:
    """Whether the bars can be true: in order, and no bar's tempo far from the score's."""
    import numpy as np

    bars = np.asarray(bars, dtype=float)
    if len(bars) != len(meters) + 1 or len(bars) < 2 or not np.isfinite(bars).all():
        return False
    lengths = np.diff(bars)
    if (lengths <= 0).any():
        return False
    quarters = np.array([n * 4 / d for n, d in meters])
    tempo = quarters * 60.0 / lengths
    return bool((np.abs(tempo / bpm - 1) <= TEMPO_SWING).all())


def _load_mono(path: Any) -> Any:
    import av
    import numpy as np

    with av.open(str(path)) as container:
        resampler = av.AudioResampler(format="flt", layout="mono", rate=SAMPLE_RATE)
        pieces = [
            f.to_ndarray().reshape(-1)
            for frame in container.decode(container.streams.audio[0])
            for f in resampler.resample(frame)
        ]
    return np.concatenate(pieces) if pieces else np.zeros(0, dtype=np.float32)


def _beat_chroma(notes: Any, seconds: Any, rate: float) -> Any:
    """The score's pitch classes over each pulse (a unit vector, or zeros where nothing sounds)."""
    import numpy as np

    out = np.zeros((len(seconds), 12), dtype=np.float32)
    for j in range(len(seconds) - 1):
        a, b = int(seconds[j] * rate), int(seconds[j + 1] * rate)
        if b > a and a < len(notes):
            total = notes[a:b].sum(axis=0)
            norm = float(np.linalg.norm(total))
            if norm > 0:
                out[j] = total / norm
    return out


def _match(chroma: Any, notes: Any, rate: float, score_time: Any, audio_time: Any) -> float | None:
    """How well the score's pitch classes lie on the recording's along a path (Plenio's measure)."""
    import numpy as np

    frames = np.round(np.interp(np.arange(len(notes)) / rate, score_time, audio_time) * rate).astype(int)
    use = (frames >= 0) & (frames < len(chroma)) & (np.abs(notes).sum(axis=1) > 0)
    if int(use.sum()) < 100:
        return None
    return float((chroma[frames[use]] * notes[use]).sum(axis=1).mean())


def measure(path: Any, score_text: str, warp: Sequence[float] | None, anchors: Sequence[Sequence[float]] | None, align: Any, canonical: Any) -> dict[str, Any]:
    """The answer of ``/scp/v1/beats`` for the take at ``path``: its bars, or ``None`` for them when the score
    and the music do not meet. ``align`` and ``canonical`` are Plenio's modules (``plenio.player.align`` and
    ``plenio.core.score.canonical``)."""
    import numpy as np

    score = canonical.from_abc(score_text)
    if warp is None:
        found = align.estimate(path, score_text)
        warp = found["warp"] if found else None
    if warp is None:
        return {"warp": None, "bars": None}
    answer: dict[str, Any] = {"warp": [float(warp[0]), float(warp[1])], "bars": None}
    meters = [tuple(m) for m in score.meters]
    if len(meters) < 2:
        return answer
    bpm = float(score.tempo)
    pulses, firsts = pulses_of(meters)
    seconds = pulses * 60.0 / bpm
    envelope = onset_envelope(_load_mono(path))
    if not len(envelope):
        return answer
    chroma = align._audio_chroma(path)
    notes = align._score_chroma(score, int(seconds[-1] * align.RATE) + 1)
    marks = np.array([[float(x[0]), float(x[1])] for x in anchors or []]).reshape(-1, 2)
    bars = find_bars(envelope, meters, bpm, warp, Harmony(chroma, align.RATE), _beat_chroma(notes, seconds, align.RATE), marks)
    if not believable(bars, meters, bpm):
        return answer
    bar_seconds = seconds[firsts]
    straight = float(warp[0]) * bar_seconds + float(warp[1])
    on_map = _match(chroma, notes, align.RATE, bar_seconds, bars)
    on_line = _match(chroma, notes, align.RATE, bar_seconds, straight)
    answer["match"] = {"map": on_map, "line": on_line}
    if on_map is not None and on_line is not None and on_map < on_line - MATCH_MARGIN:
        return answer
    answer["bars"] = {
        "score": [round(float(x), 6) for x in bar_seconds],
        "audio": [round(float(x), 6) for x in bars],
        "meters": [[int(n), int(d)] for n, d in meters],
    }
    return answer
