"""Where a song's score sits in its recording, for songs without measured times (exported before 1.0.0, or
with subtitle files only): the notation then follows the music instead of running a bar or more behind or
ahead (owner's report 2026-10-16) - a YuE2 render is shifted against its score, 1.7 s in the median song,
and the shift wanders over the song.

The pitch classes (chroma) of the score - its notes, every voice - and of the recording are compared at every
shift from -12 to +20 seconds; the best is the song's offset (``t_audio = t_score + b``). Then stretches of
24 seconds, every 12, each on its own near that offset, give anchors along the song, as the measured
syllables do for a song exported with 1.0.0. Chords and melody change over a song, so the match is clear
where onsets alone repeat with every bar. Kept in the player's cache.

:func:`follow` goes further, for every song with a score: the score's path through the recording, frame by
frame (dynamic time warping over the same pitch classes) - where the take holds, where it leaves out part of
its plan. The notation cursor follows it, through the instrumental parts too (owner's report 2026-10-23: the
cursor raced through an instrumental and waited at the lyrics - the measured syllables are too few and too
uncertain there; in 85 % of the time between syllables more than 4 s apart, the cursor ran over 30 % off the
score's tempo).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

RATE = 20
"""Frames a second."""
SAMPLE_RATE = 22050
WINDOW = 4096
LOWEST, HIGHEST = -12.0, 20.0
MIN_PEAK = 0.2
"""Below this the match is no better than chance: no estimate."""
MIN_LEAD = 1.2
"""The best shift must beat the best other (more than a second away) by this much."""
STRETCH = 24
"""Seconds of score matched on their own, every half of it, to follow where the render drifts."""
DRIFT = 3.0
"""How far a stretch may sit from the whole song's shift."""


def _audio_chroma(path: Path, rate: int = RATE, size: int = WINDOW) -> Any:
    import av
    import numpy as np

    with av.open(str(path)) as container:
        resampler = av.AudioResampler(format="flt", layout="mono", rate=SAMPLE_RATE)
        pieces = [
            f.to_ndarray().reshape(-1)
            for frame in container.decode(container.streams.audio[0])
            for f in resampler.resample(frame)
        ]
    if not pieces:
        return np.zeros((0, 12))
    x = np.concatenate(pieces)
    hop = SAMPLE_RATE // rate
    count = 1 + (len(x) - size) // hop
    if count <= 0:
        return np.zeros((0, 12))
    freqs = np.fft.rfftfreq(size, 1 / SAMPLE_RATE)
    band = (freqs > 55) & (freqs < 2000)
    classes = np.round(12 * np.log2(freqs[band] / 440.0)).astype(int) % 12
    window = np.hanning(size).astype(np.float32)
    chroma = np.zeros((count, 12), dtype=np.float32)
    # in blocks, so that a long song does not need a large array at once
    for start in range(0, count, 512):
        stop = min(count, start + 512)
        index = np.arange(size)[None, :] + hop * np.arange(start, stop)[:, None]
        frames = np.multiply(x[index], window[None, :])
        spectrum = np.log1p(10 * np.abs(np.fft.rfft(frames, axis=1))[:, band])
        for pc in range(12):
            chroma[start:stop, pc] = spectrum[:, classes == pc].sum(axis=1)
    chroma -= chroma.mean(axis=1, keepdims=True)
    norm = np.linalg.norm(chroma, axis=1, keepdims=True)
    return chroma / np.where(norm > 0, norm, 1)


def _score_chroma(score: Any, count: int, rate: int = RATE) -> Any:
    import numpy as np

    chroma = np.zeros((count, 12), dtype=np.float32)
    for notes in (score.vocal, score.ins):
        for note in notes:
            a = int(score.seconds(note.onset) * rate)
            b = max(a + 1, int(score.seconds(note.onset + note.duration) * rate))
            chroma[max(0, a) : min(count, b), (note.pitch - 69) % 12] += 1
    active = chroma.sum(axis=1) > 0
    chroma -= chroma.mean(axis=1, keepdims=True)
    norm = np.linalg.norm(chroma, axis=1, keepdims=True)
    # a new array: the division is float64 (numpy 2.5's stubs refuse it in the float32 one)
    normed = chroma / np.where(norm > 0, norm, 1)
    normed[~active] = 0
    return normed


def _match(
    audio: Any, score: Any, low: float, high: float, part: slice | None = None
) -> tuple[float, float, float]:
    """The best shift in seconds (audio later: positive), its match, and the best other one's match."""
    import numpy as np

    if part is not None:
        mask = np.zeros(len(score), dtype=bool)
        mask[part] = True
        score = np.where(mask[:, None], score, 0)
    first, last = round(low * RATE), round(high * RATE)
    values = np.full(last - first + 1, -1.0)
    # the mean over all the score's sounding frames: where a shift moves score off the recording, that part
    # counts as no match - else a shift by a repeated chorus, matching half the song, would win as well
    total = int((np.abs(score).sum(axis=1) > 0).sum())
    if total < RATE * 8:
        return 0.0, -1.0, -1.0
    for k, lag in enumerate(range(first, last + 1)):
        if lag >= 0:
            x, y = audio[lag:], score[: max(0, len(audio) - lag)]
        else:
            x, y = audio[: len(audio) + lag], score[-lag:]
        m = min(len(x), len(y))
        if m <= 0:
            continue
        values[k] = float((x[:m] * y[:m]).sum()) / total
    best = int(np.argmax(values))
    away = np.abs(np.arange(len(values)) - best) > RATE
    other = float(values[away].max()) if away.any() else -1.0
    return (first + best) / RATE, float(values[best]), other


def estimate(audio: Path, score_text: str) -> dict[str, Any] | None:
    """``{"warp": [1, b], "anchors": [[t_audio, t_score], ...], "match": ..., "lead": ...}`` or ``None`` when
    the score and the recording do not match clearly enough. ``b`` is the whole song's shift; the anchors follow
    the render where it drifts (it is no straight line: a YuE2 render runs early here and late there)."""
    try:
        from ..core.score import canonical

        score = canonical.from_abc(score_text)
        recording = _audio_chroma(audio)
    except Exception:  # noqa: BLE001 - a song that cannot be read is followed 1:1
        return None
    if len(recording) < RATE * 20:
        return None
    notes = _score_chroma(score, len(recording) + int(HIGHEST * RATE))
    b, peak, other = _match(recording, notes, LOWEST, HIGHEST)
    if peak < MIN_PEAK or peak < other * MIN_LEAD:
        return None
    # each stretch of the score on its own, near the whole song's shift
    end = int(score.seconds(score.total) * RATE)
    window, step = STRETCH * RATE, STRETCH * RATE // 2
    found: list[tuple[float, float]] = []
    for start in range(0, max(1, end - window // 2), step):
        stop = min(end, start + window)
        shift, match, _ = _match(recording, notes, b - DRIFT, b + DRIFT, slice(start, stop))
        if match >= MIN_PEAK * 0.9:
            found.append(((start + stop) / 2 / RATE, shift))
    # a stretch that disagrees with both neighbours is noise: the middle of the three wins
    anchors: list[list[float]] = []
    for k, (centre, _) in enumerate(found):
        near = sorted(shift for _, shift in found[max(0, k - 1) : k + 2])
        shift = near[len(near) // 2]
        anchors.append([round(centre + shift, 3), round(centre, 3)])
    return {
        "warp": [1.0, round(b, 3)],
        "anchors": anchors,
        "match": round(peak, 3),
        "lead": round(peak / max(other, 1e-6), 2),
    }


def score_to_audio(seconds: float, found: dict[str, Any]) -> float:
    """Score time -> song time by an estimate: between two anchors by interpolation, outside them along the
    warp (the page's ``scoreToAudio``, ``frontend/src/player/timing.ts``)."""
    a, b = (float(x) for x in (found.get("warp") or [1.0, 0.0]))
    anchors: list[tuple[float, float]] = []
    for t, s in found.get("anchors") or []:
        if not anchors or (t > anchors[-1][0] and s > anchors[-1][1]):
            anchors.append((float(t), float(s)))
    if not anchors:
        return a * seconds + b
    if seconds <= anchors[0][1]:
        return anchors[0][0] - (anchors[0][1] - seconds) * a
    if seconds >= anchors[-1][1]:
        return anchors[-1][0] + (seconds - anchors[-1][1]) * a
    for (t0, s0), (t1, s1) in zip(anchors, anchors[1:], strict=False):
        if s0 <= seconds <= s1:
            return t0 + (seconds - s0) / (s1 - s0) * (t1 - t0)
    return a * seconds + b  # not reached: the anchors cover the score between their ends


def cached_estimate(audio: Path, score_text: str, cache: Path) -> dict[str, Any] | None:
    """:func:`estimate`, worked out once per recording and score (``<cache>/align/<key>.json``)."""
    stat = audio.stat()
    key = hashlib.sha1(
        f"{audio.resolve()}|{stat.st_size}|{int(stat.st_mtime)}|{score_text}".encode()
    ).hexdigest()[:16]
    path = cache / "align" / f"{key}.json"
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            known: dict[str, Any] | None = data.get("estimate")
            return known
        except (OSError, ValueError):
            pass
    result = estimate(audio, score_text)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"estimate": result}), encoding="utf-8")
    except OSError:
        pass
    return result


FOLLOW_RATE = 10
"""Frames a second of the path (20 measured no closer, 2026-10-23)."""
FOLLOW_WINDOW = 5632
"""A quarter of a second: sung onsets matched 75 % against 73 % with ``WINDOW``."""
HOLD = SKIP = 0.5
"""What a frame costs where the take holds (its music goes on, the score not) or leaves out score, against a
frame's mismatch of 0 to 2: a hold or a jump must pay for itself in matching music. Measured on 20 of the
owner's songs against their vocal stems: score vocal notes within 0.15 s of a sung onset 69 % (the measured
syllables) -> 75 %, notes' time on the voice 94 -> 99 %; 0.3 holds too readily, 1.2 no longer finds 5 s cut
out of an instrumental."""
BAND = 40.0
"""How far from the song's warp the path may go (seconds)."""
MIN_MATCH = 0.2
"""The path's mean match below which the score is not followed by the music."""
TOLERANCE = 0.1
"""Score seconds the simplified path may leave the frame-by-frame one."""
FOLLOW_VERSION = 1


def _path(recording: Any, notes: Any, a: float, b: float) -> tuple[Any, float]:
    """The score frame of every recording frame (rising), and the path's mean match where the score sounds.

    Steps: both on; the recording on alone (a hold, ``HOLD``); the score on alone, any length within one frame
    (a jump, ``SKIP`` a frame). Before the score and after it the take waits for free. Only cells within
    ``BAND`` of the warp ``t = a s + b`` are kept for the way back."""
    import numpy as np

    count, length = len(recording), len(notes)
    index = np.arange(length)
    hold_cost = np.full(length, HOLD)
    hold_cost[0] = hold_cost[-1] = 0.0
    centre = (np.arange(count) / FOLLOW_RATE - b) / a * FOLLOW_RATE
    width = int(BAND / a * FOLLOW_RATE) + 1
    low = np.clip(np.floor(centre).astype(int) - width, 0, length - 1)
    span = 2 * width + 2
    held = np.zeros((count, span), dtype=bool)
    source = np.zeros((count, span), dtype=np.int32)
    total = np.full(length, np.inf)
    for i in range(count):
        lo, hi = int(low[i]), min(length, int(low[i]) + span)
        cost = np.full(length, np.inf)
        cost[lo:hi] = 1.0 - notes[lo:hi] @ recording[i]
        if i == 0:
            step = cost + 0.5 * SKIP * index
            hold_here = np.zeros(length, dtype=bool)
        else:
            diagonal = np.concatenate(([np.inf], total[:-1]))
            waiting = total + hold_cost
            hold_here = waiting < diagonal
            step = cost + np.where(hold_here, waiting, diagonal)
        shifted = step - SKIP * index
        best = np.minimum.accumulate(shifted)
        where = np.maximum.accumulate(np.where(shifted <= best, index, 0))
        jump = np.concatenate(([np.inf], best[:-1])) + SKIP * index
        jumped = jump < step
        total = np.where(jumped, jump, step)
        held[i, : hi - lo] = hold_here[lo:hi]
        source[i, : hi - lo] = np.where(jumped, np.concatenate(([0], where[:-1])), index)[lo:hi]
    j = int(np.argmin(total + SKIP * (length - 1 - index)))
    path = np.zeros(count, dtype=np.int32)
    for i in range(count - 1, -1, -1):
        path[i] = j
        k = int(source[i, j - int(low[i])]) if 0 <= j - int(low[i]) < span else j
        if i == 0:
            break
        inside = 0 <= k - int(low[i]) < span
        j = max(0, k if inside and held[i, k - int(low[i])] else k - 1)
    sounding = np.abs(notes[path]).sum(axis=1) > 0
    match = float((recording * notes[path]).sum(axis=1)[sounding].mean()) if sounding.any() else 0.0
    return path, match


def _simplified(points: list[tuple[float, float]]) -> list[list[float]]:
    """The fewest points whose lines stay within ``TOLERANCE`` (score seconds) of ``points``."""
    keep = {0, len(points) - 1}
    stack = [(0, len(points) - 1)]
    while stack:
        first, last = stack.pop()
        (t0, s0), (t1, s1) = points[first], points[last]
        worst, at = 0.0, -1
        for k in range(first + 1, last):
            t, s = points[k]
            off = abs(s - (s0 + (t - t0) / (t1 - t0) * (s1 - s0)))
            if off > worst:
                worst, at = off, k
        if worst > TOLERANCE:
            keep.add(at)
            stack += [(first, at), (at, last)]
    return [[round(points[k][0], 2), round(points[k][1], 2)] for k in sorted(keep)]


def follow(audio: Path, score_text: str, warp: Any = None) -> dict[str, Any] | None:
    """``{"warp": [a, b], "anchors": [[t_audio, t_score], ...], "match": ...}``: the score's path through the
    recording, near the warp ``t_audio = a t_score + b`` (the measured one; else the whole song's shift,
    :func:`estimate`). ``None`` when the score cannot be followed by its music."""
    try:
        from ..core.score import canonical

        score = canonical.from_abc(score_text)
        recording = _audio_chroma(audio, FOLLOW_RATE, FOLLOW_WINDOW)
    except Exception:  # noqa: BLE001 - a song that cannot be read is followed as before
        return None
    if len(recording) < FOLLOW_RATE * 20 or score.seconds(score.total) < 20:
        return None
    if warp is None:
        found = estimate(audio, score_text)
        if found is None:
            return None
        warp = found["warp"]
    a, b = (float(x) for x in warp)
    if not 0.5 < a < 2.0:
        return None
    notes = _score_chroma(score, int(score.seconds(score.total) * FOLLOW_RATE) + 1, FOLLOW_RATE)
    path, match = _path(recording, notes, a, b)
    if match < MIN_MATCH:
        return None
    points: list[tuple[float, float]] = []
    for i, j in enumerate(path):
        t, s = i / FOLLOW_RATE, int(j) / FOLLOW_RATE
        if not points or (t > points[-1][0] and s > points[-1][1]):
            points.append((t, s))
    if len(points) < 2:
        return None
    return {"warp": [round(a, 4), round(b, 3)], "anchors": _simplified(points), "match": round(match, 3)}


def cached_follow(audio: Path, score_text: str, cache: Path, warp: Any = None) -> dict[str, Any] | None:
    """:func:`follow`, worked out once per recording, score and warp (``<cache>/align/<key>.json``)."""
    stat = audio.stat()
    key = hashlib.sha1(
        f"follow/{FOLLOW_VERSION}|{audio.resolve()}|{stat.st_size}|{int(stat.st_mtime)}|{warp}|{score_text}".encode()
    ).hexdigest()[:16]
    path = cache / "align" / f"{key}.json"
    if path.is_file():
        try:
            known: dict[str, Any] | None = json.loads(path.read_text(encoding="utf-8")).get("follow")
            return known
        except (OSError, ValueError):
            pass
    result = follow(audio, score_text, warp)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"follow": result}), encoding="utf-8")
    except OSError:
        pass
    return result
