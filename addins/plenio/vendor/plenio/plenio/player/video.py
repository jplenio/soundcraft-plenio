"""A song as a video (owner's request 2026-10-16): the player's page draws every frame - the visual, the lyrics,
the notation, the title - and encodes it as H.264 with the browser's encoder (WebCodecs); it sends the stream
here, and this puts it together with the song's sound into an MP4 in the player's ``videos`` folder.

The video is remuxed, not encoded again (PyAV); the sound is the song's own file - the part chosen, faded in
and out where it is cut - encoded as AAC.
"""

from __future__ import annotations

import json
import re
import secrets
import shutil
import time
from fractions import Fraction
from pathlib import Path
from typing import Any

VIDEO_DIR = "videos"
JOBS_DIR = ".jobs"
MAX_STREAM = 8 * 2**30
"""The largest video stream a job takes (8 GiB: an hour of 4K at 16 Mbit/s)."""
AUDIO_RATE = 48000
AUDIO_BITRATE = 192_000
FADE_IN = 0.4
FADE_OUT = 1.5
_JOB = re.compile(r"^[0-9a-f]{16}$")


def videos_dir(state_dir: Path) -> Path:
    return state_dir / VIDEO_DIR


def file_name(title: str, width: int, height: int, folder: Path) -> Path:
    """``<title> (1920x1080).mp4``, unique in the folder."""
    stem = re.sub(r'[\s<>:"/\\|?*\x00-\x1f]+', " ", title).strip().rstrip(".")[:80] or "song"
    base = f"{stem} ({width}x{height})"
    target = folder / f"{base}.mp4"
    count = 1
    while target.exists():
        count += 1
        target = folder / f"{base} {count}.mp4"
    return target


class VideoJobs:
    """The videos being made: a folder per job with what the page sent so far."""

    def __init__(self, folder: Path):
        self.folder = folder

    def _job(self, job: str) -> Path:
        if not _JOB.match(job):
            raise KeyError(job)
        path = self.folder / JOBS_DIR / job
        if not (path / "meta.json").is_file():
            raise KeyError(job)
        return path

    def start(self, meta: dict[str, Any]) -> str:
        """A new job (``meta``: the audio file, the part, the frame rate and size, the title)."""
        job = secrets.token_hex(8)
        path = self.folder / JOBS_DIR / job
        path.mkdir(parents=True)
        (path / "meta.json").write_text(json.dumps({**meta, "started": time.time()}), encoding="utf-8")
        (path / "video.h264").write_bytes(b"")
        self.clean(keep=job)
        return job

    def append(self, job: str, data: bytes) -> int:
        """Append a piece of the H.264 stream (Annex B, as the page's encoder writes it); the size so far."""
        stream = self._job(job) / "video.h264"
        if stream.stat().st_size + len(data) > MAX_STREAM:
            raise ValueError("the video is too large")
        with stream.open("ab") as handle:
            handle.write(data)
        return stream.stat().st_size

    def cancel(self, job: str) -> None:
        shutil.rmtree(self._job(job), ignore_errors=True)

    def clean(self, keep: str = "", older: float = 6 * 3600) -> None:
        """Jobs left over (a page closed while it rendered) go after a few hours."""
        root = self.folder / JOBS_DIR
        for path in root.iterdir() if root.is_dir() else []:
            if path.name != keep and time.time() - path.stat().st_mtime > older:
                shutil.rmtree(path, ignore_errors=True)

    def finish(self, job: str, frames: int) -> Path:
        """Put the video and the song's sound together into the MP4; the job's folder goes."""
        path = self._job(job)
        meta = json.loads((path / "meta.json").read_text(encoding="utf-8"))
        target = file_name(
            str(meta.get("title") or "song"), int(meta["width"]), int(meta["height"]), self.folder
        )
        partial = target.with_suffix(".part")
        try:
            mux(
                path / "video.h264",
                Path(meta["audio"]),
                partial,
                fps=int(meta["fps"]),
                start=float(meta.get("start") or 0.0),
                length=float(meta["length"]),
                frames=frames,
                audio_bitrate=int(meta.get("audio_bitrate") or AUDIO_BITRATE),
            )
            partial.replace(target)
        finally:
            partial.unlink(missing_ok=True)
            shutil.rmtree(path, ignore_errors=True)
        return target

    def listing(self) -> list[dict[str, Any]]:
        if not self.folder.is_dir():
            return []
        files = sorted(self.folder.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
        return [{"name": p.name, "size": p.stat().st_size, "mtime": p.stat().st_mtime} for p in files]

    def file(self, name: str) -> Path | None:
        """A finished video by its name (nothing outside the folder)."""
        candidate = (self.folder / name).resolve()
        if candidate.parent != self.folder.resolve() or candidate.suffix != ".mp4" or not candidate.is_file():
            return None
        return candidate


def mux(
    stream: Path,
    audio: Path,
    target: Path,
    *,
    fps: int,
    start: float,
    length: float,
    frames: int,
    audio_bitrate: int = AUDIO_BITRATE,
) -> None:
    """The H.264 stream (frame ``k`` at ``k / fps``) and ``length`` seconds of ``audio`` from ``start`` into an
    MP4, the sound as AAC at ``audio_bitrate``. The sound fades in when the part starts inside the song, and out at
    its end when it is cut."""
    import av
    import numpy as np

    tick = Fraction(1, fps * 1000)
    with (
        av.open(str(stream), format="h264", options={"framerate": str(fps)}) as video_in,
        av.open(str(audio)) as audio_in,
        av.open(str(target), "w", format="mp4", options={"movflags": "+faststart"}) as out,
    ):
        vin = video_in.streams.video[0]
        vout = out.add_stream_from_template(vin)
        vout.time_base = tick
        ain = audio_in.streams.audio[0]
        aout = out.add_stream("aac", rate=AUDIO_RATE)
        aout.layout = "stereo"
        aout.bit_rate = audio_bitrate
        k = 0
        for packet in video_in.demux(vin):
            if packet.size == 0:
                continue
            if frames and k >= frames:
                break
            packet.stream = vout
            packet.pts = packet.dts = k * 1000
            packet.duration = 1000
            packet.time_base = tick
            out.mux(packet)
            k += 1
        base = ain.time_base or Fraction(1, AUDIO_RATE)
        song_seconds = float(ain.duration * base) if ain.duration else 0.0
        if not song_seconds and audio_in.duration:
            song_seconds = audio_in.duration / 1_000_000
        end = start + length
        cut_end = song_seconds and end < song_seconds - 0.05
        fmt = aout.codec_context.format.name if aout.codec_context.format else "fltp"
        resampler = av.AudioResampler(format=fmt, layout="stereo", rate=AUDIO_RATE)
        if start > 0:
            audio_in.seek(int(max(0.0, start - 1.0) / base), stream=ain)
        written = 0
        total = int(round(length * AUDIO_RATE))
        # where the resampled sound is in the song, counted on from the first frame decoded (after the seek)
        position: int | None = None
        for frame in audio_in.decode(ain):
            if position is None:
                position = int(round(float(frame.pts * base) * AUDIO_RATE)) if frame.pts is not None else 0
            for piece in resampler.resample(frame):
                at = position / AUDIO_RATE
                position += piece.samples
                data = piece.to_ndarray().astype(np.float32)
                planar = data.shape[0] == 2
                samples = data if planar else data.reshape(-1, 2).T
                # keep [start, end)
                first = max(0, int(round((start - at) * AUDIO_RATE)))
                samples = samples[:, first:]
                samples = samples[:, : max(0, total - written)]
                if samples.shape[1] == 0:
                    continue
                times = (written + np.arange(samples.shape[1])) / AUDIO_RATE
                gain = np.ones_like(times)
                if start > 0:
                    gain = np.minimum(gain, times / FADE_IN)
                if cut_end:
                    gain = np.minimum(gain, (length - times) / FADE_OUT)
                samples = (samples * np.clip(gain, 0.0, 1.0)).astype(np.float32)
                out_frame = av.AudioFrame.from_ndarray(
                    np.ascontiguousarray(samples if planar else samples.T.reshape(1, -1)),
                    format=fmt,
                    layout="stereo",
                )
                out_frame.sample_rate = AUDIO_RATE
                out_frame.pts = written
                out_frame.time_base = Fraction(1, AUDIO_RATE)
                written += samples.shape[1]
                for packet in aout.encode(out_frame):
                    out.mux(packet)
            if written >= total:
                break
        for packet in aout.encode(None):
            out.mux(packet)
