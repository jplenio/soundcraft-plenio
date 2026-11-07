"""Make the README's and the tutorial's pictures from a tour (examples/plenio_tour.rs).

    python addins/plenio/tools/media/make_media.py <tour folder>

The tour leaves `shots/` (named screenshots, 2000 x 1250 px) and `frames/` (every frame, numbered, with
the step in the name). This crops and scales the shots into docs/media and docs/media/tutorial, and puts
the frames together into the animation docs/media/tour.gif. Needs Pillow.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

MEDIA = Path(__file__).resolve().parents[2] / "docs" / "media"

# Regions of a 2000 x 1250 shot (pixels): where the add-in's windows open.
FULL = None
MENU = (380, 0, 1180, 300)
MENU_LONG = (380, 0, 1180, 600)
CENTER = (450, 230, 1550, 1020)
STUDIO = (440, 60, 1560, 660)
DIALOG = (560, 50, 1440, 1250)
TEMPO = (220, 140, 1430, 700)

# shot -> (output, region, width or None to keep the pixels)
SHOTS = {
    "01-menu-inactive": ("tutorial/01-menu.png", MENU, None),
    "02-activate": ("tutorial/02-activate.png", CENTER, None),
    "03-studio": ("tutorial/03-studio.png", STUDIO, None),
    "05-new-song": ("tutorial/05-new-song.png", DIALOG, 800),
    "06-new-song-style": ("tutorial/06-style.png", DIALOG, 800),
    "07-new-song-filled": ("tutorial/07-lyrics.png", DIALOG, 800),
    "08-new-song-more-options": ("tutorial/08-more-options.png", DIALOG, 800),
    "09-making": ("tutorial/09-making.png", FULL, 1400),
    "10-take-1": ("tutorial/10-take.png", FULL, 1400),
    "11-stems": ("tutorial/11-stems.png", FULL, 1400),
    "12-take-2-making": ("tutorial/12-again.png", FULL, 1400),
    "13-song": ("tutorial/13-song.png", FULL, 1400),
    "14-new-cover": ("tutorial/14-new-cover.png", DIALOG, 800),
    "15-cover": ("tutorial/15-cover.png", FULL, 1400),
    "16-import-menu": ("tutorial/16-import.png", MENU_LONG, None),
    "17-imported": ("tutorial/17-imported.png", FULL, 1400),
}
# The README's pictures.
README = {
    "13-song": ("hero.png", FULL, 1600),
    "07-new-song-filled": ("new-song.png", DIALOG, 760),
    "11-stems": ("tempo-map.png", TEMPO, None),
    "15-cover": ("cover.png", FULL, 1400),
}

# The animation: per step of the tour, how long each of its frames stays (ms) and how many are kept
# (1: its last frame; more: spread evenly over the step). Steps come in the order the tour took them.
GIF_WIDTH = 1000
STEPS = {
    "menu": (1200, 1),
    "dialog": (1100, 1),
    "style": (900, 2),
    "lyrics": (260, 40),
    "more": (1600, 1),
    "making": (170, 18),
    "take": (1300, 1),
    "stems": (220, 6),
    "again": (170, 8),
    "hero": (3200, 1),
}


def save_png(img: Image.Image, path: Path) -> None:
    """A screenshot as a small PNG: 256 colours are plenty for a UI, and keep it crisp."""
    path.parent.mkdir(parents=True, exist_ok=True)
    quantized = img.convert("RGB").quantize(colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    quantized.save(path, optimize=True)
    print(f"{path.relative_to(MEDIA)}: {img.size[0]} x {img.size[1]}, {path.stat().st_size // 1024} kB")


def shape(img: Image.Image, region, width) -> Image.Image:
    if region:
        img = img.crop(region)
    if width and img.size[0] != width:
        img = img.resize((width, round(img.size[1] * width / img.size[0])), Image.Resampling.LANCZOS)
    return img


def stills(tour: Path) -> None:
    for table in (SHOTS, README):
        for name, (out, region, width) in table.items():
            source = tour / "shots" / f"{name}.png"
            if not source.is_file():
                print(f"missing shot: {name}")
                continue
            save_png(shape(Image.open(source), region, width), MEDIA / out)


def runs(frames: list[Path]) -> list[tuple[str, list[Path]]]:
    """The frames as the tour took them, in runs of one step each."""
    out: list[tuple[str, list[Path]]] = []
    for f in frames:
        step = f.stem.split("-", 1)[-1]
        if out and out[-1][0] == step:
            out[-1][1].append(f)
        else:
            out.append((step, [f]))
    return out


def keep(run: list[Path], n: int) -> list[Path]:
    if n == 1:
        return [run[-1]]
    if len(run) <= n:
        return run
    return [run[round(i * (len(run) - 1) / (n - 1))] for i in range(n)]


def animation(tour: Path) -> None:
    frames = sorted((tour / "frames").glob("*.png"))
    # From the menu that opens the New Song dialog to the finished song.
    first = next((i for i, f in enumerate(frames) if f.stem.endswith("-dialog")), 0)
    last = next((i for i, f in enumerate(frames) if f.stem.endswith("-hero")), len(frames) - 1)
    images, durations = [], []
    for step, run in runs(frames[max(0, first - 1) : last + 1]):
        if step not in STEPS:
            continue
        ms, n = STEPS[step]
        for f in keep(run, n):
            img = Image.open(f).convert("RGB")
            images.append(img.resize((GIF_WIDTH, round(img.size[1] * GIF_WIDTH / img.size[0])), Image.Resampling.LANCZOS))
            durations.append(ms)
    if not images:
        print("no frames for the animation")
        return
    # One palette for all frames: no flicker between them, and smaller deltas.
    palette = images[-1].quantize(colors=255, method=Image.Quantize.MEDIANCUT)
    gif = [im.quantize(palette=palette, dither=Image.Dither.NONE) for im in images]
    out = MEDIA / "tour.gif"
    gif[0].save(out, save_all=True, append_images=gif[1:], duration=durations, loop=0, optimize=True, disposal=1)
    print(f"tour.gif: {len(gif)} frames, {sum(durations) / 1000:.1f} s, {out.stat().st_size // 1024} kB")


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    tour = Path(sys.argv[1])
    stills(tour)
    animation(tour)


if __name__ == "__main__":
    main()
