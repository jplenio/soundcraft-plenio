"""The tutorial as a video: activate, make a song, its take and stems, a second take, a cover, an import.

    python addins/plenio/tools/media/make_tutorial.py <tour folder> <out.mp4> [seconds,seconds,...]

Chapters of a tour's real frames and shots (examples/plenio_tour.rs, plenio_shot.rs), a camera that moves to
the part of the window each step is about, and a caption for every step; under it the tour's cover, quietly.
With seconds, only those frames are written, as PNG beside the video. The music is a YuE2 song, so the video
is CC BY-NC 4.0, like the teaser. Needs what make_teaser.py needs.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import soundfile as sf
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_teaser as mt  # noqa: E402

FPS = 30
W, H = 1920, 1080
URL = "github.com/jplenio/soundcraft-plenio"

# Views of a 2000 x 1250 frame (pixels): where the camera looks.
FULL = (0, 0, 2000, 1250)
MENU = (300, 0, 1300, 640)
CENTER = (420, 200, 1580, 1050)
STUDIO = (420, 40, 1580, 720)
DIALOG = (500, 30, 1500, 1250)
INSPECTOR = (1180, 60, 2000, 1010)
TEMPO = (200, 120, 1440, 720)


@dataclass
class Shot:
    source: str  # "step:n" (the n-th run of a step in the tour's frames) or "shot:name"
    keep: int  # frames of the run to play (1: its last)
    each: float  # seconds per frame
    caption: str
    view: tuple


CHAPTERS = [
    ("Activate", "once, with the models' licences", [
        Shot("menu:0", 1, 3.0, "Open the Plenio menu: Activate Plenio Add-in…", MENU),
        Shot("activate:0", 1, 4.5, "Accept the models' licences (YuE2 is CC BY-NC 4.0: non-commercial), then Activate", CENTER),
        Shot("shot:03-studio", 1, 4.5, "The studio starts: a ComfyUI of the add-in's own, with Plenio, on the models you have", STUDIO),
    ]),
    ("Make a song", "a style, your words, Make the Song", [
        Shot("menu:1", 1, 2.5, "Plenio › New Song…", MENU),
        Shot("dialog:0", 1, 3.0, "The New Song dialog: style, vocals, length, language, title", DIALOG),
        Shot("style:0", 2, 2.2, "Search Plenio's 250 styles and pick one: here Synth pop", DIALOG),
        Shot("lyrics:0", 14, 0.45, "Tick My own lyrics and write them: the buttons insert YuE2's section tags", DIALOG),
        Shot("dialog:1", 1, 3.2, "Tick Split every take into stems right away, and every take comes with its stems", DIALOG),
        Shot("more:0", 1, 3.6, "More options: every other field of Plenio's Song API, the style's values as hints", DIALOG),
    ]),
    ("The take", "on its tracks, in time, with its stems", [
        Shot("making:0", 16, 0.42, "Make the Song: the inspector follows the studio (five minutes, here faster)", INSPECTOR),
        Shot("take:0", 1, 4.2, "The take on its tracks: sections, lyrics where they are sung, the song, the score as MIDI", FULL),
        Shot("stems:0", 5, 0.5, "And right away its stems: vocals, drums, bass, other and the rest", FULL),
        Shot("shot:11-stems", 1, 4.2, "Every bar has its own tempo, measured in the audio: the metronome stays on the music", TEMPO),
    ]),
    ("Make it again", "words, notes, the brief, or a new take", [
        Shot("shot:12-take-2-making", 1, 3.6, "Change words, notes or the brief, and Generate makes what you changed; unchanged: a new take", INSPECTOR),
        Shot("again:0", 10, 0.35, "Each take lands on a playlist of its own", INSPECTOR),
        Shot("shot:13-song", 1, 4.2, "Choose between takes in the inspector: the tracks, the lyrics and the tempo map follow", FULL),
    ]),
    ("Cover a song", "any recording, in another style", [
        Shot("cover-dialog:0", 1, 4.4, "Select the recording's track, Plenio › New Cover from Selected Track…, pick a target style", DIALOG),
        Shot("cover:0", 10, 0.35, "The cover is made: the melody, the form and the tempo of the original stay", INSPECTOR),
        Shot("shot:15-cover", 1, 4.6, "Late-night jazz: the cover in a folder of its own, the original beside it", FULL),
    ]),
    ("Bring a song in", "from a FLAC Plenio made", [
        Shot("shot:16-import-menu", 1, 3.0, "Plenio › Import Plenio Song… and choose the FLAC: it carries the whole song", MENU),
        Shot("import:0", 6, 0.4, "Plenio reads the song's record", FULL),
        Shot("shot:17-imported", 1, 4.4, "It comes in with its take, lyrics, score and tempo map, ready to change and make again", FULL),
    ]),
]
CARD = 2.6
INTRO = 5.0
OUTRO = 5.5
MOVE = 0.6


def runs(frames: list[Path]) -> dict[str, list[list[Path]]]:
    out: dict[str, list[list[Path]]] = {}
    last = None
    for f in frames:
        step = f.stem.split("-", 1)[-1]
        if step != last:
            out.setdefault(step, []).append([])
        out[step][-1].append(f)
        last = step
    return out


def pictures(tour: Path, shot: Shot, by_step: dict) -> list[Path]:
    kind, _, name = shot.source.partition(":")
    if kind == "shot":
        p = tour / "shots" / f"{name}.png"
        return [p] if p.is_file() else []
    step, _, n = shot.source.rpartition(":")
    found = by_step.get(step, [])
    if int(n) >= len(found):
        return []
    run = found[int(n)]
    if shot.keep == 1:
        return [run[-1]]
    if len(run) <= shot.keep:
        return run
    return [run[round(i * (len(run) - 1) / (shot.keep - 1))] for i in range(shot.keep)]


@dataclass
class Segment:
    start: float
    end: float
    kind: str  # intro, card, shot, outro
    chapter: int = 0
    picture: Path | None = None
    caption: str = ""
    view: tuple = FULL


def plan(tour: Path) -> list[Segment]:
    by_step = runs(sorted((tour / "frames").glob("*.png")))
    segs = [Segment(0.0, INTRO, "intro")]
    t = INTRO
    for c, (title, _, shots) in enumerate(CHAPTERS):
        segs.append(Segment(t, t + CARD, "card", c))
        t += CARD
        for shot in shots:
            for p in pictures(tour, shot, by_step):
                segs.append(Segment(t, t + shot.each, "shot", c, p, shot.caption, shot.view))
                t += shot.each
    segs.append(Segment(t, t + OUTRO, "outro"))
    return segs


def view_at(segs: list[Segment], i: int, t: float) -> tuple:
    """The camera: the view of the shot, moving from the last shot's view over its first moments."""
    seg = segs[i]
    prev = next((s for s in reversed(segs[:i]) if s.kind == "shot"), None)
    if prev is None or prev.view == seg.view or prev.chapter != seg.chapter:
        return seg.view
    u = mt.ease((t - seg.start) / MOVE)
    return tuple(a + (b - a) * u for a, b in zip(prev.view, seg.view))


_cache: dict[Path, np.ndarray] = {}


def frame_of(path: Path) -> np.ndarray:
    if path not in _cache:
        if len(_cache) > 24:
            _cache.clear()
        _cache[path] = np.asarray(Image.open(path).convert("RGB"), np.float32) / 255.0
    return _cache[path]


def place(canvas: np.ndarray, img: np.ndarray, view: tuple, alpha: float) -> None:
    """Show `view` of the frame as large as fits above the caption, centred, on the sky."""
    x0, y0, x1, y1 = view
    area_h = H - 150
    scale = min((W - 80) / (x1 - x0), area_h / (y1 - y0))
    w, h = (x1 - x0) * scale, (y1 - y0) * scale
    ox, oy = (W - w) / 2, (area_h - h) / 2 + 10
    m = np.array([[scale, 0, ox - x0 * scale], [0, scale, oy - y0 * scale]], np.float32)
    shown = cv2.warpAffine(img, m, (W, H), flags=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0))
    mask = np.zeros((H, W), np.float32)
    cv2.rectangle(mask, (int(ox), int(oy)), (int(ox + w), int(oy + h)), 1.0, -1)
    halo = cv2.GaussianBlur(mask, (0, 0), 18)
    glow = mt.gradient_rgb(W, H) / 255.0
    canvas[:] = canvas * (1 - halo[..., None] * 0.5 * alpha) + glow * halo[..., None] * 0.35 * alpha
    a = mask[..., None] * alpha
    canvas[:] = canvas * (1 - a) + shown * a


def caption(canvas: np.ndarray, seg: Segment, t: float) -> None:
    band = np.zeros((H, W), np.float32)
    band[H - 130 :] = 1.0
    band = cv2.GaussianBlur(band, (0, 0), 20)
    canvas[:] = canvas * (1 - band[..., None] * 0.75)
    title = CHAPTERS[seg.chapter][0].upper()
    mt.text(canvas, f"{seg.chapter + 1} · {title}", "ExtraBold", 26, 60, H - 108, 0.95, fill="gradient", spacing=0.12, anchor="left")
    alpha = min(1.0, (t - seg.start) / 0.25 + 0.6)
    mt.text(canvas, seg.caption, "SemiBold", 38, 60, H - 72, alpha, anchor="left", max_width=W - 120)


def card(canvas: np.ndarray, c: int, u: float) -> None:
    title, sub, _ = CHAPTERS[c]
    a = mt.ease(u / 0.2) * (1 - mt.ease((u - 0.85) / 0.15))
    mt.text(canvas, f"{c + 1}", "Black", 220, W / 2, H * 0.18, a, fill="gradient", glow=16)
    mt.text(canvas, title.upper(), "ExtraBold", 92, W / 2, H * 0.47, a, spacing=0.04)
    mt.text(canvas, sub, "Medium", 36, W / 2, H * 0.6, a * 0.9)


def intro(canvas: np.ndarray, u: float) -> None:
    logo = mt.logo_sprite(mt.ease(u / 0.5), 260)
    mt.paste(canvas, logo, W / 2 - 130, H * 0.1)
    a = mt.ease((u - 0.2) / 0.25)
    mt.text(canvas, "TUTORIAL", "ExtraBold", 40, W / 2, H * 0.42, a, fill="gradient", spacing=0.4)
    mt.text(canvas, "Make, change, cover and bring in a song", "ExtraBold", 72, W / 2, H * 0.5, a)
    mt.text(canvas, "with Plenio in SoundCraft  ·  add-in 0.1.0-alpha", "Medium", 34, W / 2, H * 0.61, a * 0.9)


def outro(canvas: np.ndarray, u: float) -> None:
    a = mt.ease(u / 0.2)
    mt.paste(canvas, mt.logo_sprite(1.0, 200), W / 2 - 100, H * 0.12, a)
    mt.text(canvas, "Every step, with pictures, in the written tutorial", "ExtraBold", 58, W / 2, H * 0.42, a)
    mt.text(canvas, URL, "Bold", 44, W / 2, H * 0.54, a, fill="gradient")
    mt.text(canvas, "addins/plenio/docs/TUTORIAL.md", "Medium", 32, W / 2, H * 0.62, a * 0.9)
    song = "Music: the tour's cover, made with Plenio in SoundCraft (YuE2, CC BY-NC 4.0)"
    mt.text(canvas, song, "Medium", 22, W / 2, H * 0.9, 0.75 * a)
    fade = mt.ease((u - 0.8) / 0.2)
    canvas[:] = canvas * (1 - fade)


def render(tour: Path, out: Path, preview: list[float] | None = None) -> None:
    segs = plan(tour)
    total = segs[-1].end
    cover = mt.load_song(tour, "cover")
    data, rate = sf.read(str(cover.audio), dtype="float32", always_2d=True)
    world = mt.World(cover, mt.envelope(data, rate))
    out.parent.mkdir(parents=True, exist_ok=True)
    clip = out.with_suffix(".wav")
    n = int(total * rate)
    music = np.zeros((n, data.shape[1]), np.float32)
    piece = data[: min(n, len(data))] * (10 ** (-12 / 20))
    music[: len(piece)] = piece
    fin, fout = int(1.5 * rate), int(4.0 * rate)
    music[:fin] *= np.linspace(0, 1, fin)[:, None]
    music[-fout:] *= np.linspace(1, 0, fout)[:, None]
    sf.write(str(clip), music, rate, subtype="PCM_24")
    frames = int(total * FPS)
    print(f"tutorial: {total:.1f} s, {len(segs)} segments, {frames} frames")
    enc = None
    if not preview:
        args = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                "-i", str(clip), "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
                "-movflags", "+faststart", "-shortest", str(out)]
        enc = subprocess.Popen(args, stdin=subprocess.PIPE)
    for k in ([int(s * FPS) for s in preview] if preview else range(frames)):
        t = k / FPS
        i = next((j for j, s in enumerate(segs) if s.start <= t < s.end), len(segs) - 1)
        seg = segs[i]
        u = (t - seg.start) / max(1e-6, seg.end - seg.start)
        canvas = world.draw(t, t, 0.5)
        if seg.kind == "intro":
            intro(canvas, u)
        elif seg.kind == "outro":
            outro(canvas, u)
        elif seg.kind == "card":
            card(canvas, seg.chapter, u)
        elif seg.picture is not None:
            first = i == 0 or segs[i - 1].kind != "shot"
            alpha = mt.ease((t - seg.start) / 0.3) if first else 1.0
            place(canvas, frame_of(seg.picture), view_at(segs, i, t), alpha)
            caption(canvas, seg, t)
        pixels = (np.clip(canvas, 0, 1) * 255).astype(np.uint8)
        if enc:
            enc.stdin.write(pixels.tobytes())
        else:
            Image.fromarray(pixels).save(out.parent / f"tutorial-preview-{t:05.1f}.png")
    if enc:
        enc.stdin.close()
        enc.wait()
    clip.unlink(missing_ok=True)
    print("done")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    at = [float(s) for s in sys.argv[3].split(",")] if len(sys.argv) > 3 else None
    render(Path(sys.argv[1]), Path(sys.argv[2]), at)
