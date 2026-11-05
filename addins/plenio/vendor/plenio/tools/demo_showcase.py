"""Add songs and song videos to the demo page's showcase (``docs/demo-showcase.js``; how: docs/demo-showcase.md).

    python tools/demo_showcase.py add <song.flac | song.plenio.json> [--soundcloud URL] [--youtube URL] [--audio]
                                      [--no-lyrics] [--note TEXT]
    python tools/demo_showcase.py add-video <YouTube URL or id> --title TITLE [--genre GENRE] [--note TEXT]
    python tools/demo_showcase.py list
    python tools/demo_showcase.py remove <id>

A song needs something to play: a SoundCloud or YouTube link, or ``--audio``, which copies the MP3 Export Release
wrote beside the FLAC into ``docs/assets/showcase/`` (or encodes one from the FLAC, as Export does). Its cover goes there too, 640 pixels square. Only what the
song's page in the player shows is copied - the title, genre, language, length, tempo, key, the style, the lyrics
(unless ``--no-lyrics``) and how it was made (when, how long, on which graphics card); not the prompts, the seeds,
the paths or the record itself. New entries come first; the page shows them in this order.
"""

from __future__ import annotations

import argparse
import datetime
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any

PROJECT = Path(__file__).resolve().parents[1]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

DOCS = PROJECT / "docs"
DATA = DOCS / "demo-showcase.js"
ASSETS = "assets/showcase"
VARIABLE = "window.PLENIO_SHOWCASE = "
HEADER = (
    "// The demo page's showcase: song videos and new songs. Written by tools/demo_showcase.py - add, list and remove\n"
    "// entries with it (docs/demo-showcase.md); the page shows them newest first.\n"
)
PLAYLIST = "https://www.youtube.com/playlist?list=PLBZzzh1IMZzk"
COVER_SIZE = 640
YOUTUBE_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
YOUTUBE_URL = re.compile(r"(?:youtu\.be/|[?&]v=|/shorts/|/embed/|/live/)([A-Za-z0-9_-]{11})")
SOUNDCLOUD = re.compile(r"^https://(?:www\.|on\.)?soundcloud\.com/\S+$")


class ShowcaseError(Exception):
    """Something the command cannot do as asked - said in a sentence for the console."""


def load(path: Path = DATA) -> dict[str, Any]:
    """The showcase as the page reads it (an empty one when the file does not exist yet)."""
    if not path.exists():
        return {"playlist": PLAYLIST, "entries": []}
    text = path.read_text(encoding="utf-8")
    start = text.find(VARIABLE)
    if start < 0:
        raise ShowcaseError(f"{path.name} does not set {VARIABLE.strip(' =')}.")
    body = text[start + len(VARIABLE) :].strip()
    data = json.loads(body.removesuffix(";"))
    data.setdefault("entries", [])
    return data


def save(data: dict[str, Any], path: Path = DATA) -> None:
    text = HEADER + VARIABLE + json.dumps(data, ensure_ascii=False, indent=2) + ";\n"
    path.write_text(text, encoding="utf-8", newline="\n")  # LF on every system, as the repository keeps it


def youtube_id(text: str) -> str:
    """The video id of a YouTube link (watch, youtu.be, shorts, embed, live) or of a bare id."""
    text = text.strip()
    if YOUTUBE_ID.match(text):
        return text
    found = YOUTUBE_URL.search(text)
    if not found:
        raise ShowcaseError(f"Not a YouTube video link: {text}")
    return found.group(1)


def slug(title: str, taken: set[str]) -> str:
    """An id from the title, unique in the showcase: ``neon-midnight``, ``neon-midnight-2`` ..."""
    base = re.sub(r"[^a-z0-9]+", "-", title.casefold()).strip("-") or "song"
    candidate, n = base, 2
    while candidate in taken:
        candidate, n = f"{base}-{n}", n + 1
    return candidate


def read_song(path: Path) -> tuple[dict[str, Any], dict[str, Path]]:
    """The song's summary as the player's library makes it, and its files beside it - from its release record, the
    ``.plenio.json`` or the one its FLAC carries."""
    from plenio.core.release import read_project
    from plenio.player.library import RECORD_SUFFIX, summarize

    if path.name.endswith(RECORD_SUFFIX):
        record_path = path
        record = json.loads(path.read_text(encoding="utf-8"))
    elif path.suffix.lower() == ".flac":
        record_path = path.with_name(path.stem + RECORD_SUFFIX)
        record = (
            json.loads(record_path.read_text(encoding="utf-8"))
            if record_path.exists()
            else read_project(path)
        )
        if record is None:
            raise ShowcaseError(f"{path.name} carries no Plenio release record - was it exported by Plenio?")
    else:
        raise ShowcaseError(f"Give the song's FLAC or its .plenio.json, not {path.name}.")
    song = summarize(record, record_path, record_path.parent)
    return song.summary, song.files


def encode_mp3(flac: Path, mp3: Path, title: str) -> None:
    """The song as an MP3 the way Export Release writes one (LAME VBR V0), for a song exported without it - decoded
    with PyAV, which comes with ComfyUI."""
    import av
    import numpy as np

    from plenio.core.release import write_audio

    chunks = []
    with av.open(str(flac)) as container:
        stream = container.streams.audio[0]
        rate = int(stream.rate)
        layout = "stereo" if stream.channels > 1 else "mono"
        resampler = av.AudioResampler(format="fltp", layout=layout, rate=rate)
        for frame in container.decode(stream):
            chunks += [out.to_ndarray() for out in resampler.resample(frame)]
        chunks += [out.to_ndarray() for out in resampler.resample(None)]
    write_audio(mp3, np.concatenate(chunks, axis=1), rate, "mp3", {"title": title})


def made_of(summary: dict[str, Any]) -> dict[str, Any]:
    """When, how long and on what - only what the record says, without the processor's serial or any path."""
    made = summary.get("made") or {}
    on = made.get("on") or {}
    out: dict[str, Any] = {}
    when = str(made.get("started") or summary.get("created") or "")[:10]
    if when:
        out["date"] = when
    if made.get("seconds"):
        out["seconds"] = round(float(made["seconds"]), 1)
    if on.get("device") == "gpu" and on.get("gpu"):
        out["on"] = str(on["gpu"])
    elif on.get("cpu"):
        out["on"] = f"{on['cpu']} (no graphics card)"
    return out


def song_entry(
    summary: dict[str, Any],
    files: dict[str, Path],
    taken: set[str],
    *,
    soundcloud: str = "",
    youtube: str = "",
    audio: bool = False,
    lyrics: bool = True,
    note: str = "",
    docs: Path = DOCS,
    today: str | None = None,
) -> dict[str, Any]:
    """The showcase entry of a song, its cover (and, with ``audio``, its MP3) copied into the docs."""
    if soundcloud and not SOUNDCLOUD.match(soundcloud.strip()):
        raise ShowcaseError(f"Not a SoundCloud link: {soundcloud}")
    video = youtube_id(youtube) if youtube else ""
    if not (soundcloud or video or audio):
        raise ShowcaseError(
            "Say where the song plays: --soundcloud URL, --youtube URL or --audio (its MP3 is copied)."
        )
    title = str(summary.get("title") or "").strip() or "Untitled"
    entry: dict[str, Any] = {"id": slug(title, taken), "kind": "song", "title": title}
    for key in ("genre", "language", "model"):
        if summary.get(key):
            entry[key] = str(summary[key])
    if summary.get("instrumental"):
        entry["vocals"] = "instrumental"
    if summary.get("seconds"):
        entry["seconds"] = round(float(summary["seconds"]), 1)
    if summary.get("bpm"):
        entry["bpm"] = summary["bpm"]
    if summary.get("score_key"):
        entry["key"] = str(summary["score_key"])
    if summary.get("style"):
        entry["style"] = str(summary["style"])
    if lyrics and summary.get("lyrics") and not summary.get("instrumental"):
        entry["lyrics"] = str(summary["lyrics"])
    made = made_of(summary)
    if made:
        entry["made"] = made
    target = docs / ASSETS
    if files.get("cover") and files["cover"].exists():
        from PIL import Image

        target.mkdir(parents=True, exist_ok=True)
        with Image.open(files["cover"]) as image:
            square = image.convert("RGB")
            side = min(square.size)
            left, top = (square.width - side) // 2, (square.height - side) // 2
            square = square.crop((left, top, left + side, top + side)).resize(
                (COVER_SIZE, COVER_SIZE), Image.Resampling.LANCZOS
            )
            square.save(target / f"{entry['id']}.jpg", quality=86, optimize=True, progressive=True)
        entry["cover"] = f"{ASSETS}/{entry['id']}.jpg"
    if audio:
        target.mkdir(parents=True, exist_ok=True)
        mp3, flac = files.get("audio_mp3"), files.get("audio_flac")
        if mp3 and mp3.exists():
            shutil.copyfile(mp3, target / f"{entry['id']}.mp3")
        elif flac and flac.exists():
            encode_mp3(flac, target / f"{entry['id']}.mp3", title)
        else:
            raise ShowcaseError("No MP3 or FLAC beside this song - give --soundcloud or --youtube instead.")
        entry["audio"] = f"{ASSETS}/{entry['id']}.mp3"
    if soundcloud:
        entry["soundcloud"] = soundcloud.strip()
    if video:
        entry["youtube"] = video
    if note:
        entry["note"] = note.strip()
    entry["added"] = today or datetime.date.today().isoformat()
    return entry


def video_entry(
    link: str, title: str, taken: set[str], *, genre: str = "", note: str = "", today: str | None = None
) -> dict[str, Any]:
    """A song video on YouTube: its id, title and genre (the page shows YouTube's own picture of it)."""
    title = title.strip()
    if not title:
        raise ShowcaseError("Give the video's title: --title.")
    entry: dict[str, Any] = {"id": slug(title, taken), "kind": "video", "title": title}
    if genre.strip():
        entry["genre"] = genre.strip()
    entry["youtube"] = youtube_id(link)
    if note.strip():
        entry["note"] = note.strip()
    entry["added"] = today or datetime.date.today().isoformat()
    return entry


def remove(data: dict[str, Any], entry_id: str, docs: Path = DOCS) -> dict[str, Any]:
    """Takes the entry out and deletes the files it copied into the docs."""
    for entry in data["entries"]:
        if entry.get("id") == entry_id:
            data["entries"].remove(entry)
            for key in ("cover", "audio"):
                value = str(entry.get(key) or "")
                if value.startswith(f"{ASSETS}/"):
                    (docs / value).unlink(missing_ok=True)
            return entry
    raise ShowcaseError(f"No entry {entry_id} - `list` shows the ids.")


def describe(entry: dict[str, Any]) -> str:
    plays = ", ".join(
        part
        for part in (
            f"YouTube {entry['youtube']}" if entry.get("youtube") else "",
            "SoundCloud" if entry.get("soundcloud") else "",
            "MP3" if entry.get("audio") else "",
        )
        if part
    )
    genre = f" · {entry['genre']}" if entry.get("genre") else ""
    return f"{entry['id']:<36} {entry.get('kind', 'song'):<5} {entry.get('title', '')}{genre} ({plays})"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    add = commands.add_parser("add", help="add a song from its FLAC or its .plenio.json")
    add.add_argument("song", type=Path)
    add.add_argument("--soundcloud", default="", help="the song on SoundCloud")
    add.add_argument("--youtube", default="", help="the song's video on YouTube")
    add.add_argument(
        "--audio", action="store_true", help="copy the song's MP3 into the docs and play it there"
    )
    add.add_argument("--no-lyrics", action="store_true", help="leave the lyrics out")
    add.add_argument("--note", default="", help="a line about the song, shown on its card")
    video = commands.add_parser("add-video", help="add a song video on YouTube")
    video.add_argument("link")
    video.add_argument("--title", required=True)
    video.add_argument("--genre", default="")
    video.add_argument("--note", default="")
    commands.add_parser("list", help="the entries, newest first")
    drop = commands.add_parser("remove", help="take an entry out (and the files it copied)")
    drop.add_argument("id")
    args = parser.parse_args(argv)
    try:
        data = load()
        taken = {str(e.get("id")) for e in data["entries"]}
        if args.command == "add":
            summary, files = read_song(args.song)
            entry = song_entry(
                summary,
                files,
                taken,
                soundcloud=args.soundcloud,
                youtube=args.youtube,
                audio=args.audio,
                lyrics=not args.no_lyrics,
                note=args.note,
            )
        elif args.command == "add-video":
            entry = video_entry(args.link, args.title, taken, genre=args.genre, note=args.note)
        elif args.command == "remove":
            gone = remove(data, args.id)
            save(data)
            print(f"removed {gone['id']} ({gone.get('title', '')})")
            return 0
        else:
            for item in data["entries"]:
                print(describe(item))
            print(f"{len(data['entries'])} entries in {DATA.relative_to(PROJECT).as_posix()}")
            return 0
        data["entries"].insert(0, entry)
        save(data)
        print(f"added {describe(entry)}")
        print(
            "Commit docs/demo-showcase.js and docs/assets/showcase/ - the page shows it once GitHub Pages has the commit."
        )
        return 0
    except ShowcaseError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
