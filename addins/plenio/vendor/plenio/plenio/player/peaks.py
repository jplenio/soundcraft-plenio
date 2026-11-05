"""The waveform of a song for the player's seek bar: peak levels in equal slices, decoded once (PyAV and
numpy, which ComfyUI's Python has) and kept in the player's cache folder."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

SLICES = 900


def peaks(audio: Path, cache: Path, slices: int = SLICES) -> list[float] | None:
    """Peak levels 0..1 (``None`` when the audio cannot be decoded here: the page then draws none)."""
    stat = audio.stat()
    stamp = f"{audio}|{stat.st_size}|{int(stat.st_mtime)}|{slices}"
    key = cache / f"{hashlib.sha1(stamp.encode()).hexdigest()[:16]}.json"
    if key.exists():
        try:
            return list(json.loads(key.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            pass
    try:
        import av
        import numpy as np
    except ImportError:
        return None
    chunks: list[np.ndarray] = []
    try:
        with av.open(str(audio)) as container:
            stream = container.streams.audio[0]
            resampler = av.AudioResampler(format="flt", layout="mono", rate=8000)
            for frame in container.decode(stream):
                for out in resampler.resample(frame):
                    chunks.append(np.abs(out.to_ndarray().reshape(-1)))
    except Exception:  # noqa: BLE001 - an unreadable file has no waveform
        return None
    if not chunks:
        return None
    data = np.concatenate(chunks)
    edges = np.linspace(0, len(data), slices + 1).astype(int)
    levels = np.array([data[a:b].max() if b > a else 0.0 for a, b in zip(edges[:-1], edges[1:], strict=True)])
    top = float(levels.max()) or 1.0
    result = [round(float(v / top), 3) for v in levels]
    try:
        cache.mkdir(parents=True, exist_ok=True)
        key.write_text(json.dumps(result), encoding="utf-8")
    except OSError:
        pass
    return result
