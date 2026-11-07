"""The teaser "Plenio comes to SoundCraft": a song the add-in made, and pictures of the add-in making it.

    python addins/plenio/tools/media/make_teaser.py <tour folder> <out folder> [seconds,seconds,...]

Reads the tour's session (examples/plenio_tour.rs): the active take of its song, its bars as the add-in
measured them, its sung lines and sections, its score's MIDI and stems on the session's tracks, and the
tour's screenshots and frames. Every scene starts on a bar line or a sung line, so the cuts follow the
music. Writes `plenio-comes-to-soundcraft.mp4` (1920 x 1080) and `plenio-comes-to-soundcraft-vertical.mp4`
(1080 x 1920), 30 frames a second. Needs NumPy, OpenCV, Pillow, soundfile and ffmpeg on the PATH; the text
is set in Montserrat (OFL-1.1) when the computer has it.

The music is a YuE2 song: the video is under the model's licence, CC BY-NC 4.0.
"""

from __future__ import annotations

import json
import math
import os
import subprocess
import sys
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
import soundfile as sf
from PIL import Image, ImageDraw, ImageFont

FPS = 30
W, H = 1920, 1080
VW, VH = 1080, 1920
PPQ = 960
AMBER, PINK, VIOLET = (255, 178, 62), (255, 61, 139), (138, 77, 255)
NIGHT = (7, 4, 13)
URL = "github.com/jplenio/soundcraft-plenio"
STEM_COLORS = {"vocals": (255, 178, 62), "drums": (255, 90, 110), "bass": (255, 61, 139), "other": (190, 90, 255), "rest": (120, 110, 255)}

# ---------------------------------------------------------------------------------------------------
# The song, as the session has it


@dataclass
class Line:
    start: float
    end: float
    text: str


@dataclass
class Song:
    audio: Path
    bars: list[float]
    sections: list[tuple[str, float, float]]
    lines: list[Line]
    tempos: list[tuple[float, float]]  # (audio seconds, bpm) per bar
    notes: dict[str, list[tuple[float, float, int]]]  # role -> (start s, end s, pitch), audio seconds
    stems: dict[str, Path]
    title: str
    shots: Path
    frames: Path
    extra: dict = field(default_factory=dict)


def ticks_to_seconds(tempos: list[dict]) -> callable:
    """The session's tempo map as a function from ticks to seconds."""
    points = sorted((int(t["tick"]), float(t["bpm"])) for t in tempos)
    starts = [0.0]
    for (t0, bpm), (t1, _) in zip(points, points[1:]):
        starts.append(starts[-1] + (t1 - t0) / PPQ * 60.0 / bpm)

    def at(tick: float) -> float:
        i = max(0, np.searchsorted([p[0] for p in points], tick, side="right") - 1)
        t0, bpm = points[i]
        return starts[i] + (tick - t0) / PPQ * 60.0 / bpm

    return at


def seconds_to_ticks(tempos: list[dict], rate: int) -> callable:
    at = ticks_to_seconds(tempos)
    grid = np.arange(0, 2_000_000, 120)
    times = np.array([at(t) for t in grid])
    return lambda samples: float(np.interp(samples / rate, times, grid))


def load_song(tour: Path, kind: str = "song") -> Song:
    """The active take of the tour's first song of this kind (`song` or `cover`)."""
    session_file = next((tour / "session").glob("*.scraft"))
    session = json.loads(session_file.read_text(encoding="utf-8"))
    rate = int(session.get("sample_rate", 48000))
    project = session["extensions"]["plenio"]
    project = json.loads(project) if isinstance(project, str) else project
    song = next(s for s in project["songs"] if s["kind"] == kind)
    take = song["takes"][song["active"]]
    at = float(take["audio_at"])
    audio = Path(take["files"]["song"])
    tempo = session["tempo"]["tempos"]
    to_seconds = ticks_to_seconds(tempo)
    to_ticks = seconds_to_ticks(tempo, rate)
    bars = [float(b) for b in take["bars"]["audio"]]
    # The tempo of each bar, as the session's ruler shows it.
    tempos = [(bars[i], 240.0 / max(1e-3, bars[i + 1] - bars[i])) for i in range(len(bars) - 1)]
    notes: dict[str, list[tuple[float, float, int]]] = {}
    stems: dict[str, Path] = {}
    sources = {s["id"]: s for s in session["sources"]}
    roles = {r["track"]: r["role"] for r in song["tracks"]}
    for track in session["tracks"]:
        role = roles.get(track["id"])
        playlists = track.get("playlists") or []
        if not role or not playlists:
            continue
        clips = playlists[min(track.get("active_playlist", 0), len(playlists) - 1)]["clips"]
        for clip in clips:
            content = clip["content"]
            if "Midi" in content and role in ("melody", "accompaniment", "chords"):
                origin = to_ticks(int(clip["start"]))
                for n in content["Midi"]["sequence"]["notes"]:
                    s0 = to_seconds(origin + n["start"]) - at
                    s1 = to_seconds(origin + n["start"] + n["length"]) - at
                    notes.setdefault(role, []).append((s0, s1, int(n["pitch"])))
            if "Audio" in content and role in STEM_COLORS:
                src = sources.get(content["Audio"]["source"])
                if src:
                    path = Path(src["path"])
                    stems[role] = path if path.is_absolute() else session_file.parent / path
    lines = [Line(l["start"] - at, l["end"] - at, " ".join(l["text"].split())) for l in take["lines"]]
    sections = [(s["name"], s["start"] - at, s["end"] - at) for s in take["sections"]]
    return Song(audio, bars, sections, lines, tempos, notes, stems, song["title"], tour / "shots", tour / "frames")


# ---------------------------------------------------------------------------------------------------
# Drawing


FONT_DIRS = [Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft/Windows/Fonts", Path("C:/Windows/Fonts"), Path.home() / ".fonts", Path("/usr/share/fonts")]


@lru_cache(maxsize=None)
def font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    for d in FONT_DIRS:
        for name in (f"Montserrat-{weight}.ttf", "segoeuib.ttf" if weight in ("Bold", "ExtraBold", "Black") else "segoeui.ttf"):
            p = d / name
            if p.is_file():
                return ImageFont.truetype(str(p), size)
    return ImageFont.load_default()


def ease(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return 1 - (1 - x) ** 3


def gradient_rgb(width: int, height: int, colors=(AMBER, PINK, VIOLET)) -> np.ndarray:
    xs = np.linspace(0, 1, width)[None, :, None]
    a, b, c = (np.array(col, np.float32)[None, None, :] for col in colors)
    left = a + (b - a) * np.clip(xs / 0.5, 0, 1)
    right = b + (c - b) * np.clip((xs - 0.5) / 0.5, 0, 1)
    row = np.where(xs < 0.5, left, right)
    return np.repeat(row, height, axis=0)


@lru_cache(maxsize=512)
def text_sprite(text: str, weight: str, size: int, fill: str = "white", spacing: float = 0.0, glow: int = 0) -> np.ndarray:
    """RGBA float32 [0, 1]: the text, white or in Plenio's gradient, with an optional glow."""
    f = font(weight, size)
    chars = list(text)
    extra = size * spacing
    widths = [f.getlength(c) for c in chars]
    width = int(sum(widths) + extra * max(0, len(chars) - 1)) + 4 + 2 * glow
    ascent, descent = f.getmetrics()
    height = ascent + descent + 4 + 2 * glow
    mask = Image.new("L", (width, height), 0)
    d = ImageDraw.Draw(mask)
    x = 2 + glow
    for c, w in zip(chars, widths):
        d.text((x, 2 + glow), c, font=f, fill=255)
        x += w + extra
    m = np.asarray(mask, np.float32) / 255.0
    if fill == "gradient":
        rgb = gradient_rgb(width, height) / 255.0
    else:
        rgb = np.ones((height, width, 3), np.float32)
    out = np.dstack([rgb, m])
    if glow:
        g = cv2.GaussianBlur(m, (0, 0), glow / 2)
        halo = np.dstack([gradient_rgb(width, height) / 255.0, np.clip(g * 1.4, 0, 1)])
        out = over_rgba(halo, out)
    return out


def over_rgba(dst: np.ndarray, src: np.ndarray) -> np.ndarray:
    a = src[..., 3:4]
    rgb = src[..., :3] * a + dst[..., :3] * dst[..., 3:4] * (1 - a)
    alpha = a + dst[..., 3:4] * (1 - a)
    return np.dstack([np.where(alpha > 0, rgb / np.maximum(alpha, 1e-6), 0), alpha])


def paste(frame: np.ndarray, sprite: np.ndarray, x: float, y: float, alpha: float = 1.0, scale: float = 1.0) -> None:
    """Alpha-blend an RGBA sprite onto the float RGB frame, top-left at (x, y)."""
    if alpha <= 0.001:
        return
    if abs(scale - 1.0) > 1e-3:
        sprite = cv2.resize(sprite, (max(1, int(sprite.shape[1] * scale)), max(1, int(sprite.shape[0] * scale))), interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR)
    h, w = sprite.shape[:2]
    x0, y0 = int(round(x)), int(round(y))
    fx0, fy0 = max(0, x0), max(0, y0)
    fx1, fy1 = min(frame.shape[1], x0 + w), min(frame.shape[0], y0 + h)
    if fx1 <= fx0 or fy1 <= fy0:
        return
    s = sprite[fy0 - y0 : fy1 - y0, fx0 - x0 : fx1 - x0]
    a = s[..., 3:4] * alpha
    region = frame[fy0:fy1, fx0:fx1]
    region[:] = region * (1 - a) + s[..., :3] * a


def text(frame: np.ndarray, s: str, weight: str, size: int, cx: float, y: float, alpha=1.0, fill="white", spacing=0.0, glow=0, anchor="center", max_width=None) -> tuple[int, int]:
    sp = text_sprite(s, weight, size, fill, spacing, glow)
    scale = min(1.0, max_width / sp.shape[1]) if max_width else 1.0
    x = cx - sp.shape[1] * scale / 2 if anchor == "center" else cx
    paste(frame, sp, x, y, alpha, scale)
    return int(sp.shape[1] * scale), int(sp.shape[0] * scale)


@lru_cache(maxsize=64)
def picture(path: str, crop: tuple | None = None, width: int | None = None) -> np.ndarray:
    """A screenshot as RGBA float, cropped and scaled, in a rounded frame with a border."""
    img = Image.open(path).convert("RGB")
    if crop:
        img = img.crop(crop)
    if width:
        img = img.resize((width, round(img.size[1] * width / img.size[0])), Image.Resampling.LANCZOS)
    rgb = np.asarray(img, np.float32) / 255.0
    h, w = rgb.shape[:2]
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), radius=18, fill=255)
    a = np.asarray(mask, np.float32) / 255.0
    border = Image.new("L", (w, h), 0)
    ImageDraw.Draw(border).rounded_rectangle((0, 0, w - 1, h - 1), radius=18, outline=255, width=3)
    b = np.asarray(border, np.float32)[..., None] / 255.0
    grad = gradient_rgb(w, h) / 255.0
    rgb = rgb * (1 - b) + grad * b
    return np.dstack([rgb, a])


def shadowed(frame: np.ndarray, sprite: np.ndarray, x: float, y: float, alpha: float = 1.0, scale: float = 1.0) -> None:
    """A window: a soft neon shadow under it, then the picture."""
    h, w = int(sprite.shape[0] * scale), int(sprite.shape[1] * scale)
    pad = 60
    glow = np.zeros((h + 2 * pad, w + 2 * pad), np.float32)
    cv2.rectangle(glow, (pad, pad), (pad + w, pad + h), 1.0, -1)
    glow = cv2.GaussianBlur(glow, (0, 0), 26)
    halo = np.dstack([gradient_rgb(w + 2 * pad, h + 2 * pad) / 255.0, glow * 0.55])
    paste(frame, halo, x - pad, y - pad + 10, alpha)
    paste(frame, sprite, x, y, alpha, scale)


def fit(sprite: np.ndarray, max_w: int, max_h: int) -> float:
    return min(max_w / sprite.shape[1], max_h / sprite.shape[0], 1.0)


# ---------------------------------------------------------------------------------------------------
# The world: sky, waves and stars, moving with the music


class World:
    def __init__(self, song: Song, envelope: np.ndarray):
        self.song = song
        self.env = envelope
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        sky = np.zeros((H, W, 3), np.float32)
        sky[:] = np.array(NIGHT, np.float32) / 255.0
        for (cx, cy, r, col, k) in ((0.86, 0.1, 0.75, VIOLET, 0.36), (0.08, 0.95, 0.6, PINK, 0.24), (0.55, 0.55, 0.5, AMBER, 0.07)):
            d = np.sqrt(((xx / W - cx) / r) ** 2 + ((yy / H - cy) / (r * 1.2)) ** 2)
            sky += np.clip(1 - d, 0, 1)[..., None] ** 2 * (np.array(col, np.float32) / 255.0) * k
        self.sky = sky
        rng = np.random.default_rng(7)
        self.stars = np.column_stack([rng.uniform(0, W, 260), rng.uniform(0, H, 260), rng.uniform(0.3, 1.0, 260), rng.uniform(4, 22, 260)])

    def level(self, a: float) -> float:
        i = int(max(0, min(len(self.env) - 1, a * FPS)))
        return float(self.env[i])

    def beat(self, a: float) -> float:
        """1 on every beat, falling off over a quarter of it."""
        bars = self.song.bars
        k = np.searchsorted(bars, a) - 1
        if k < 0 or k + 1 >= len(bars):
            return 0.0
        beat_len = (bars[k + 1] - bars[k]) / 4
        phase = ((a - bars[k]) % beat_len) / beat_len
        return math.exp(-phase * 6)

    def draw(self, a: float, t: float, energy: float = 1.0) -> np.ndarray:
        frame = self.sky.copy()
        level = self.level(a)
        pulse = self.beat(a)
        glow = np.zeros((H // 2, W // 2, 3), np.float32)
        sharp = np.zeros((H, W, 3), np.float32)
        xs = np.linspace(0, W, 220)
        for i, (base, amp, speed, width) in enumerate(((0.80, 70, 0.35, 3), (0.84, 50, 0.22, 2), (0.76, 40, 0.5, 2))):
            phase = t * speed + i * 1.7
            ys = H * base + np.sin(xs / W * 5.0 + phase) * amp * (0.6 + 0.8 * level * energy) + np.sin(xs / W * 13.0 - phase * 1.3) * 14
            pts = np.column_stack([xs, ys]).astype(np.int32)
            for j in range(len(pts) - 1):
                u = j / (len(pts) - 1)
                col = np.array(AMBER if u < 0.33 else PINK if u < 0.66 else VIOLET, np.float32) / 255.0
                cv2.line(sharp, tuple(pts[j]), tuple(pts[j + 1]), tuple(float(c) for c in col * (0.55 + 0.45 * pulse)), width, cv2.LINE_AA)
            cv2.polylines(glow, [pts // 2], False, (1.0, 0.35, 0.65), 6, cv2.LINE_AA)
        glow = cv2.GaussianBlur(glow, (0, 0), 10) * (0.25 + 0.5 * pulse * energy)
        frame += cv2.resize(glow, (W, H)) + sharp * 0.9
        # Stars drift up slowly and twinkle with the beat.
        st = self.stars
        ys = (st[:, 1] - t * st[:, 3]) % H
        for (x, y, b, _) in zip(st[:, 0], ys, st[:, 2], st[:, 3]):
            v = b * (0.5 + 0.5 * pulse)
            cv2.circle(frame, (int(x), int(y)), 1, (v, v, v), -1, cv2.LINE_AA)
        return frame


def envelope(audio: np.ndarray, rate: int) -> np.ndarray:
    hop = rate // FPS
    mono = audio.mean(axis=1) if audio.ndim == 2 else audio
    n = len(mono) // hop
    rms = np.sqrt(np.mean(mono[: n * hop].reshape(n, hop) ** 2, axis=1))
    rms = rms / max(1e-9, np.percentile(rms, 98))
    kernel = np.hanning(7) / np.hanning(7).sum()
    return np.clip(np.convolve(rms, kernel, mode="same"), 0, 1.2).astype(np.float32)


# ---------------------------------------------------------------------------------------------------
# Scenes. Each draws onto the frame at audio time `a`; `u` is how far the scene is (0..1).


def frames_of(song: Song, step: str) -> list[Path]:
    return sorted(p for p in song.frames.glob("*.png") if p.stem.split("-", 1)[-1] == step)


DIALOG = (560, 50, 1440, 1250)
INSPECTOR = (1420, 90, 1990, 990)


def scene_open(frame, song, a, u, ctx):
    lines = ["Every song starts as an idea.", "What if your DAW could write it with you?"]
    k = 0 if u < 0.5 else 1
    v = (u * 2) % 1.0
    alpha = ease(v / 0.25) * (1 - ease((v - 0.8) / 0.2))
    text(frame, lines[k], "SemiBold", 60, W / 2, H * 0.40, alpha)


def logo_sprite(progress: float, size: int) -> np.ndarray:
    """The P drawn on as three neon strokes, then the waveform."""
    s = size / 512
    img = np.zeros((size, size, 3), np.float32)
    strokes = [
        [(136, 418), (136, 112), (282, 112), "arc", 120, (282, 352), (212, 352)],
        [(168, 418), (168, 144), (282, 144), "arc", 88, (282, 320), (232, 320)],
        [(200, 418), (200, 176), (282, 176), "arc", 56, (282, 288), (252, 288)],
    ]
    pts_all = []
    for st in strokes:
        pts = [st[0], st[1], st[2]]
        r = st[4]
        cx, cy = 282, st[2][1] + r
        for k in range(1, 41):
            ang = -math.pi / 2 + math.pi * k / 40
            pts.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
        pts.append(st[6])
        pts_all.append(np.array(pts, np.float32))
    bars = [(300, 402, 390), (330, 414, 378), (360, 426, 366), (390, 410, 382), (420, 400, 392)]
    grad = gradient_rgb(size, size) / 255.0
    mask = np.zeros((size, size), np.float32)
    for i, pts in enumerate(pts_all):
        seg = np.sqrt((np.diff(pts, axis=0) ** 2).sum(axis=1))
        total = seg.sum()
        take = min(1.0, max(0.0, progress * 1.4 - i * 0.12)) * total
        acc = 0.0
        for j in range(len(seg)):
            if acc >= take:
                break
            p0, p1 = pts[j], pts[j + 1]
            f = min(1.0, (take - acc) / max(seg[j], 1e-6))
            q = p0 + (p1 - p0) * f
            cv2.line(mask, (int(p0[0] * s), int(p0[1] * s)), (int(q[0] * s), int(q[1] * s)), 1.0, max(2, int(17 * s)), cv2.LINE_AA)
            acc += seg[j]
    wave = max(0.0, min(1.0, (progress - 0.7) / 0.3))
    for k, (x, y0, y1) in enumerate(bars):
        if wave * len(bars) > k:
            cv2.line(mask, (int(x * s), int(y0 * s)), (int(x * s), int(y1 * s)), 1.0, max(2, int(17 * s)), cv2.LINE_AA)
    glow = cv2.GaussianBlur(mask, (0, 0), 9 * s)
    a = np.clip(mask + glow * 0.9, 0, 1)
    img = grad * np.clip(mask + glow, 0, 1)[..., None]
    return np.dstack([img, a])


@lru_cache(maxsize=1)
def logo_small() -> np.ndarray:
    return logo_sprite(1.0, 84)


def scene_logo(frame, song, a, u, ctx):
    size = 360
    logo = logo_sprite(ease(u / 0.6), size)
    paste(frame, logo, W * 0.5 - 470 - size / 2 + 150, H * 0.5 - size / 2 - 40)
    x = W * 0.5 - 130
    alpha = ease((u - 0.25) / 0.3)
    sp = text_sprite("PLENIO", "ExtraBold", 170, spacing=0.04)
    paste(frame, sp, x, H * 0.5 - 200 + (1 - alpha) * 40, alpha)
    sp2 = text_sprite("MUSIC PRODUCTION SYSTEM", "SemiBold", 34, spacing=0.3)
    paste(frame, sp2, x + 6, H * 0.5 + 10, ease((u - 0.4) / 0.3))
    pill_alpha = ease((u - 0.55) / 0.15)
    if pill_alpha > 0:
        pill = text_sprite("FOR SOUNDCRAFT", "Bold", 34, spacing=0.2, glow=10)
        pw, ph = pill.shape[1] + 70, pill.shape[0] + 26
        box = np.zeros((ph + 40, pw + 40, 4), np.float32)
        m = np.zeros((ph + 40, pw + 40), np.float32)
        cv2.rectangle(m, (20, 20), (20 + pw, 20 + ph), 1.0, 4)
        m = cv2.GaussianBlur(m, (0, 0), 1.2)
        g = gradient_rgb(pw + 40, ph + 40) / 255.0
        box = np.dstack([g, np.clip(m * 2 + cv2.GaussianBlur(m, (0, 0), 10) * 2, 0, 1)])
        paste(frame, box, x - 14, H * 0.5 + 70, pill_alpha)
        paste(frame, pill, x - 14 + 20 + 35, H * 0.5 + 70 + 20 + 13, pill_alpha)


def scene_window(frame, sprite, u, side="center", top=150, max_w=1100, max_h=820):
    scale = fit(sprite, max_w, max_h)
    w, h = sprite.shape[1] * scale, sprite.shape[0] * scale
    slide = 1 - ease(u / 0.12)
    x = {"center": (W - w) / 2, "right": W - w - 110, "left": 110}[side]
    shadowed(frame, sprite, x + slide * 120, top + slide * 30, ease(u / 0.1), scale)


def scene_lyrics(frame, song, a, u, ctx):
    typing = frames_of(song, "lyrics") or [song.shots / "07-new-song-filled.png"]
    k = min(len(typing) - 1, int(u * 1.15 * len(typing)))
    scene_window(frame, picture(str(typing[k]), DIALOG, 760), u, "right", top=110, max_h=860)


def scene_style(frame, song, a, u, ctx):
    shot = song.shots / ("06-new-song-style.png" if u < 0.55 else "08-new-song-more-options.png")
    scene_window(frame, picture(str(shot), DIALOG, 760), u if u < 0.55 else (u - 0.55) / 0.45, "right", top=110, max_h=860)


def scene_notes(frame, song, a, u, ctx):
    """The score as neon notes, the melody above the chords, passing a playhead in time with the song."""
    left, right, top, bottom = 140, W - 140, 200, H - 250
    span = 8.0
    t0 = a - span * 0.35
    roles = [("melody", PINK, 0.0, 0.42), ("accompaniment", AMBER, 0.44, 0.66), ("chords", VIOLET, 0.68, 1.0)]
    panel = np.zeros((H, W, 3), np.float32)
    glow = np.zeros((H, W, 3), np.float32)
    for role, col, f0, f1 in roles:
        notes = [n for n in song.notes.get(role, []) if n[1] >= t0 and n[0] <= t0 + span]
        pitches = [n[2] for n in song.notes.get(role, [])] or [60]
        lo, hi = min(pitches) - 1, max(pitches) + 1
        y0, y1 = top + (bottom - top) * f0, top + (bottom - top) * f1
        c = np.array(col, np.float32) / 255.0
        for s0, s1, p in notes:
            x0 = left + (s0 - t0) / span * (right - left)
            x1 = left + (s1 - t0) / span * (right - left)
            y = y1 - (p - lo) / max(1, hi - lo) * (y1 - y0)
            lit = 1.0 if s0 <= a <= s1 else 0.55
            cv2.rectangle(panel, (int(x0), int(y - 6)), (int(max(x0 + 4, x1 - 2)), int(y + 6)), tuple(float(v) for v in c * lit), -1, cv2.LINE_AA)
            if s0 <= a <= s1:
                cv2.rectangle(glow, (int(x0), int(y - 10)), (int(x1), int(y + 10)), tuple(float(v) for v in c), -1)
        text(frame, {"melody": "MELODY", "accompaniment": "INSTRUMENT LINE", "chords": "CHORDS"}[role], "Bold", 22, left, y0 - 4, 0.8, spacing=0.25, anchor="left")
    glow = cv2.GaussianBlur(glow, (0, 0), 14)
    fade = ease(u / 0.1)
    frame[:] = frame + (panel * 0.95 + glow * 0.8) * fade
    px = left + 0.35 * (right - left)
    cv2.line(frame, (int(px), top - 20), (int(px), bottom + 10), (1.0, 1.0, 1.0), 2, cv2.LINE_AA)


def scene_takes(frame, song, a, u, ctx):
    hero = picture(str(song.shots / "13-song.png"), (0, 130, 1430, 600), 1500)
    scene_window(frame, hero, u, "center", top=260, max_w=1500, max_h=520)


def scene_generate(frame, song, a, u, ctx):
    making = frames_of(song, "making") + frames_of(song, "again")
    if not making:
        return
    k = min(len(making) - 1, int(ease(u) * len(making)))
    sprite = picture(str(making[k]), INSPECTOR, 640)
    zoom = 1.0 + 0.18 * ease(u)
    scale = fit(sprite, 900, 820) * zoom
    w, h = sprite.shape[1] * scale, sprite.shape[0] * scale
    shake = (math.sin(a * 40) * 3 * u, math.cos(a * 37) * 3 * u)
    shadowed(frame, sprite, (W - w) / 2 + shake[0] + 330, (H - h) / 2 + shake[1] - 30, ease(u / 0.08), scale)
    if u > 0.9:
        frame[:] = frame + (u - 0.9) / 0.1 * 0.9


def scene_title(frame, song, a, u, ctx):
    pulse = ctx["world"].beat(a)
    size = 150
    for i, line in enumerate(("PLENIO COMES", "TO SOUNDCRAFT")):
        sp = text_sprite(line, "Black", size, fill="gradient", spacing=0.02, glow=18)
        scale = 1.0 + 0.03 * pulse + 0.06 * (1 - ease(u / 0.15))
        paste(frame, sp, W / 2 - sp.shape[1] * scale / 2, H * 0.30 + i * 175 - sp.shape[0] * (scale - 1) / 2, ease(u / 0.05), scale)
    if u < 0.06:
        frame[:] = frame + (1 - u / 0.06) * 0.8


def scene_session(frame, song, a, u, ctx):
    hero = picture(str(song.shots / "13-song.png"), None, 1600)
    scene_window(frame, hero, u, "center", top=120, max_w=1640, max_h=820)
    # A playhead sweeping the visible timeline.
    scale = fit(hero, 1640, 820)
    x0 = (W - hero.shape[1] * scale) / 2 + 395 / 2000 * hero.shape[1] * scale
    x1 = (W - hero.shape[1] * scale) / 2 + 1420 / 2000 * hero.shape[1] * scale
    px = x0 + (x1 - x0) * u
    cv2.line(frame, (int(px), 190), (int(px), 120 + int(hero.shape[0] * scale) - 30), (1.0, 0.9, 0.95), 2, cv2.LINE_AA)


@lru_cache(maxsize=8)
def peaks(path: str, start: float, end: float, n: int) -> np.ndarray:
    rate = sf.info(path).samplerate
    data, _ = sf.read(path, start=int(max(0, start) * rate), stop=int(end * rate), dtype="float32", always_2d=True)
    mono = np.abs(data).max(axis=1)
    if len(mono) < n:
        return np.zeros(n, np.float32)
    k = len(mono) // n
    return mono[: k * n].reshape(n, k).max(axis=1)


def scene_stems(frame, song, a, u, ctx):
    """The take's waveform splits into its stems."""
    t0, t1 = ctx["scene_start"], ctx["scene_end"]
    n = 900
    left, right = 260, W - 160
    mix = peaks(str(song.audio), t0, t1, n)
    split = ease((u - 0.12) / 0.3)
    names = [s for s in ("vocals", "drums", "bass", "other", "rest") if s in song.stems]
    rows = max(1, len(names))
    top, bottom = 190, H - 230
    lane = (bottom - top) / rows
    xs = np.linspace(left, right, n)
    head = int(n * u)
    for i, name in enumerate(names):
        y_split = top + lane * (i + 0.5)
        y = H / 2 + (y_split - H / 2) * split
        data = peaks(str(song.stems[name]), t0, t1, n) if split > 0 else mix
        amp = (lane * 0.42 if split > 0.5 else 160) * (data if split > 0 else mix)
        col = np.array(STEM_COLORS[name], np.float32) / 255.0
        for j in range(0, n, 2):
            lit = 1.0 if j <= head else 0.45
            cv2.line(frame, (int(xs[j]), int(y - amp[j])), (int(xs[j]), int(y + amp[j])), tuple(float(c) for c in col * lit), 2, cv2.LINE_AA)
        text(frame, name.upper(), "Bold", 26, 120, y - 16, split, spacing=0.2, anchor="left")


def scene_tempo(frame, song, a, u, ctx):
    """Bar lines on the waveform with the tempo the add-in measured for each bar."""
    t0 = a - 3.0
    t1 = a + 9.0
    left, right, mid = 140, W - 140, H * 0.5
    data = peaks(str(song.audio), max(0.0, round(ctx["scene_start"] - 3, 1)), ctx["scene_end"] + 9.0, 1400)
    n = len(data)
    span0, span1 = max(0.0, round(ctx["scene_start"] - 3, 1)), ctx["scene_end"] + 9.0
    for j in range(0, n, 2):
        t = span0 + (span1 - span0) * j / n
        if t < t0 or t > t1:
            continue
        x = left + (t - t0) / (t1 - t0) * (right - left)
        amp = data[j] * 150
        lit = 1.0 if t <= a else 0.5
        cv2.line(frame, (int(x), int(mid - amp)), (int(x), int(mid + amp)), (0.55 * lit, 0.85 * lit, 0.8 * lit), 2, cv2.LINE_AA)
    for bar, bpm in song.tempos:
        if t0 <= bar <= t1:
            x = left + (bar - t0) / (t1 - t0) * (right - left)
            cv2.line(frame, (int(x), int(mid - 230)), (int(x), int(mid + 200)), (1.0, 0.24, 0.55), 2, cv2.LINE_AA)
            text(frame, f"{bpm:.2f}", "Bold", 24, x + 8, mid - 262, 0.95, anchor="left")
    px = left + (a - t0) / (t1 - t0) * (right - left)
    cv2.line(frame, (int(px), int(mid - 280)), (int(px), int(mid + 230)), (1.0, 1.0, 1.0), 2, cv2.LINE_AA)


def scene_cover(frame, song, a, u, ctx):
    shot = song.shots / "15-cover.png"
    if not shot.is_file():
        shot = song.shots / "14-new-cover.png"
    scene_window(frame, picture(str(shot), None, 1500), u, "center", top=150, max_w=1500, max_h=780)


def scene_outro(frame, song, a, u, ctx):
    logo = logo_sprite(1.0, 300)
    paste(frame, logo, W / 2 - 150, H * 0.13, ease(u / 0.2))
    text(frame, "PLENIO FOR SOUNDCRAFT", "ExtraBold", 84, W / 2, H * 0.47, ease((u - 0.1) / 0.2), spacing=0.04)
    text(frame, "ALPHA 0.1.0  ·  FREE & OPEN SOURCE  ·  RUNS ON YOUR GPU", "SemiBold", 30, W / 2, H * 0.58, ease((u - 0.2) / 0.2), spacing=0.12)
    text(frame, URL, "Bold", 40, W / 2, H * 0.66, ease((u - 0.3) / 0.2), fill="gradient")
    text(frame, f"Music: \u201c{song.title}\u201d, made with Plenio in SoundCraft (YuE2, CC BY-NC 4.0)", "Medium", 22, W / 2, H * 0.9, 0.75 * ease((u - 0.3) / 0.2))
    fade = ease((u - 0.82) / 0.18)
    frame[:] = frame * (1 - fade)


# ---------------------------------------------------------------------------------------------------
# The timeline: scenes keyed to bars and sung lines


@dataclass
class Scene:
    start: float
    end: float
    draw: callable
    caption: str = ""
    sub: str = ""


def timeline(song: Song) -> tuple[list[Scene], float, float]:
    bars = song.bars
    first_of = lambda name: next(((s, e) for n, s, e in song.sections if n == name), (None, None))
    verse = first_of("verse")
    pre = first_of("pre-chorus")
    chorus = first_of("chorus")
    bar_at = lambda t: int(np.argmin(np.abs(np.array(bars) - t)))
    v0, p0, c0 = bar_at(verse[0]), bar_at(pre[0]), bar_at(chorus[0])
    c1 = bar_at(chorus[1])
    start = bars[max(0, v0 - 4)]
    end_music = bars[min(len(bars) - 1, c1 + 2)]
    in_verse = [l for l in song.lines if verse[0] - 0.5 <= l.start < pre[0] - 0.5]
    in_chorus = [l for l in song.lines if chorus[0] - 0.5 <= l.start < chorus[1]]
    vb = [bars[v0]] + [l.start for l in in_verse[1:4]] + [bars[p0]]
    cb = [bars[c0]] + [l.start for l in in_chorus[1:4]] + [bars[c1]]
    while len(vb) < 5:
        vb.insert(-1, (vb[-2] + vb[-1]) / 2)
    while len(cb) < 5:
        cb.insert(-1, (cb[-2] + cb[-1]) / 2)
    mid_last = (cb[3] + cb[4]) / 2
    scenes = [
        Scene(start, bars[max(0, v0 - 2)], scene_open),
        Scene(bars[max(0, v0 - 2)], bars[v0], scene_logo),
        Scene(vb[0], vb[1], scene_lyrics, "WRITE YOUR WORDS", "or say in a sentence what the song is about"),
        Scene(vb[1], vb[2], scene_style, "PICK A STYLE", "250 of them, and every option of Plenio's Song API"),
        Scene(vb[2], vb[3], scene_notes, "THE SCORE, AS MIDI", "melody · instrument line · chords, on the beat"),
        Scene(vb[3], vb[4], scene_takes, "EVERY TAKE ON ITS OWN PLAYLIST", "lyrics where they are sung, sections on the lane"),
        Scene(bars[p0], bars[c0], scene_generate, "PRESS GENERATE", "YuE2 writes, composes, sings and masters it on your GPU"),
        Scene(cb[0], cb[1], scene_title),
        Scene(cb[1], cb[2], scene_session, "LYRICS · TAKES · SCORE · STEMS", "on real tracks of an open-source DAW"),
        Scene(cb[2], cb[3], scene_stems, "STEMS IN ONE CLICK", "or right away, for every new take"),
        Scene(cb[3], mid_last, scene_tempo, "THE TEMPO FOLLOWS THE AUDIO", "bar by bar - the metronome stays on the music"),
        Scene(mid_last, cb[4], scene_cover, "COVER ANY RECORDING", "in another style, with its words or new ones"),
        Scene(cb[4], end_music, scene_outro),
    ]
    return scenes, start, end_music


# ---------------------------------------------------------------------------------------------------
# Captions and lyrics for each layout


def sung_line(song: Song, a: float):
    for l in song.lines:
        if l.start - 0.15 <= a <= l.end + 0.25:
            return l
    return None


def karaoke(frame: np.ndarray, song: Song, a: float, cx: float, y: float, size: int) -> None:
    line = sung_line(song, a)
    if not line:
        return
    done = min(1.0, max(0.0, (a - line.start) / max(0.3, line.end - line.start)))
    base = text_sprite(line.text, "SemiBold", size)
    lit = text_sprite(line.text, "SemiBold", size, fill="gradient")
    x = cx - base.shape[1] / 2
    alpha = min(1.0, (a - line.start + 0.15) / 0.2, (line.end + 0.25 - a) / 0.2)
    paste(frame, base, x, y, 0.55 * alpha)
    cut = int(base.shape[1] * done)
    if cut > 0:
        paste(frame, lit[:, :cut], x, y, alpha)


def caption(frame: np.ndarray, scene: Scene, u: float, x: float, y: float, title_size: int, sub_size: int, anchor="left", width=None) -> None:
    if not scene.caption:
        return
    alpha = ease(u / 0.12) * (1 - ease((u - 0.92) / 0.08))
    slide = (1 - ease(u / 0.15)) * 30
    _, h = text(frame, scene.caption, "ExtraBold", title_size, x - slide if anchor == "left" else x, y, alpha, fill="gradient", spacing=0.03, anchor=anchor, max_width=width)
    text(frame, scene.sub, "Medium", sub_size, x, y + h + title_size * 0.1, alpha * 0.9, anchor=anchor, max_width=width)


# ---------------------------------------------------------------------------------------------------


def render(tour: Path, out: Path, preview: list[float] | None = None) -> None:
    """Render both videos; with `preview` (seconds into the teaser) only those frames, as PNG."""
    song = load_song(tour)
    scenes, start, end = timeline(song)
    data, rate = sf.read(str(song.audio), dtype="float32", always_2d=True)
    env = envelope(data[int(0 * rate) :], rate)
    world = World(song, env)
    out.mkdir(parents=True, exist_ok=True)
    clip = out / "teaser-audio.wav"
    fade_out = 4.0
    seg = data[int(start * rate) : int(end * rate)].copy()
    n_in, n_out = int(0.25 * rate), int(fade_out * rate)
    seg[:n_in] *= np.linspace(0, 1, n_in)[:, None]
    seg[-n_out:] *= np.linspace(1, 0, n_out)[:, None] ** 1.5
    sf.write(str(clip), seg, rate, subtype="PCM_24")
    total = int((end - start) * FPS)
    print(f"{song.title}: {end - start:.1f} s from {start:.2f} s, {total} frames, {len(scenes)} scenes")

    def encoder(path: Path, w: int, h: int):
        args = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", str(FPS), "-i", "-",
                "-i", str(clip), "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-pix_fmt", "yuv420p", "-profile:v", "high",
                "-c:a", "aac", "-b:a", "256k", "-movflags", "+faststart", "-shortest", str(path)]
        return subprocess.Popen(args, stdin=subprocess.PIPE)

    wide = None if preview else encoder(out / "plenio-comes-to-soundcraft.mp4", W, H)
    tall = None if preview else encoder(out / "plenio-comes-to-soundcraft-vertical.mp4", VW, VH)
    poster_at = None
    for i in ([int(s * FPS) for s in preview] if preview else range(total)):
        a = start + i / FPS
        t = i / FPS
        scene = next((s for s in scenes if s.start <= a < s.end), scenes[-1])
        u = (a - scene.start) / max(1e-6, scene.end - scene.start)
        ctx = {"world": world, "scene_start": scene.start, "scene_end": scene.end}
        energy = 1.6 if scene.draw in (scene_title, scene_generate) else 1.0
        frame = world.draw(a, t, energy)
        base = frame.copy() if scene.draw is scene_title else None
        scene.draw(frame, song, a, u, ctx)
        # The wide layout: caption top left, the sung line at the bottom.
        wide_frame = frame.copy()
        caption(wide_frame, scene, u, 110, 64, 54, 26)
        if scene.draw not in (scene_title, scene_outro, scene_logo, scene_open):
            karaoke(wide_frame, song, a, W / 2, H - 112, 44)
        if preview:
            Image.fromarray((np.clip(wide_frame, 0, 1) * 255).astype(np.uint8)).save(out / f"preview-{i / FPS:05.1f}.png")
        else:
            wide.stdin.write((np.clip(wide_frame, 0, 1) * 255).astype(np.uint8).tobytes())
        # The tall layout: the wide picture in the middle, caption above, lyrics below.
        tall_frame = vertical(frame if base is None else base, world, a, t)
        if base is not None:
            big = logo_sprite(min(1.0, u * 3), 420)
            paste(tall_frame, big, VW / 2 - 210, VH * 0.47 - 210, 1.0, 1.0 + 0.04 * world.beat(a))
        if scene.draw not in (scene_outro, scene_logo, scene_open, scene_title):
            paste(tall_frame, logo_small(), VW / 2 - 300, 96)
            text(tall_frame, "PLENIO FOR SOUNDCRAFT", "ExtraBold", 40, VW / 2 - 300 + 104, 118, 0.95, spacing=0.05, anchor="left")
        if scene.caption:
            caption(tall_frame, scene, u, VW / 2, 420, 66, 32, anchor="center", width=VW - 90)
        elif scene.draw is scene_title:
            for k, line in enumerate(("PLENIO COMES", "TO SOUNDCRAFT")):
                sp = text_sprite(line, "Black", 104, fill="gradient", spacing=0.02, glow=14)
                paste(tall_frame, sp, VW / 2 - sp.shape[1] / 2, 190 + k * 130, ease(u / 0.05))
        if scene.draw not in (scene_title, scene_outro, scene_logo, scene_open):
            karaoke(tall_frame, song, a, VW / 2, 1330, 48)
        if scene.draw not in (scene_outro,):
            text(tall_frame, URL, "Bold", 30, VW / 2, VH - 170, 0.85, fill="gradient")
        if preview:
            Image.fromarray((np.clip(tall_frame, 0, 1) * 255).astype(np.uint8)).save(out / f"preview-{i / FPS:05.1f}-vertical.png")
        else:
            tall.stdin.write((np.clip(tall_frame, 0, 1) * 255).astype(np.uint8).tobytes())
        if scene.draw is scene_title and poster_at is None and u > 0.4:
            poster_at = i
            Image.fromarray((np.clip(wide_frame, 0, 1) * 255).astype(np.uint8)).save(out / "teaser-poster.png")
        if i % 150 == 0:
            print(f"  {i}/{total}")
    for p in (wide, tall):
        if p:
            p.stdin.close()
            p.wait()
    clip.unlink(missing_ok=True)
    print("done")


def vertical(frame: np.ndarray, world: World, a: float, t: float) -> np.ndarray:
    """1080 x 1920: a blurred, darkened sky of the frame behind it, the frame itself in the middle."""
    small = cv2.resize(frame, (VW // 4, VH // 4), interpolation=cv2.INTER_AREA)
    back = cv2.resize(cv2.GaussianBlur(small, (0, 0), 6), (VW, VH)) * 0.6
    pic = cv2.resize(frame, (VW, int(VW * H / W)), interpolation=cv2.INTER_AREA)
    y = int(VH * 0.47) - pic.shape[0] // 2
    back[y : y + pic.shape[0]] = pic
    return back


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    at = [float(s) for s in sys.argv[3].split(",")] if len(sys.argv) > 3 else None
    render(Path(sys.argv[1]), Path(sys.argv[2]), at)
