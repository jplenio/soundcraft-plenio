"""Music not made with Plenio, for the Plenio Player (owner's request 2026-10-16): in a folder chosen with
*also other music*, every audio file that no release record owns is a song too - clearly marked as other
music, and with what its file has: the audio, its tags (title, artist, album, genre, year), an embedded or a
folder cover, its lyrics from the tags, and timed lyrics from an ``.lrc`` or ``.srt`` file of the same name.
No notation, no brief, no measured syllables, no *Open in ComfyUI*: that needs a release record.

The tags are read with PyAV (ComfyUI's Python has it); without it the file's name is the title.
"""

from __future__ import annotations

import hashlib
import re
import time
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

AUDIO_SUFFIXES = {".flac", ".mp3", ".wav", ".ogg", ".oga", ".opus", ".m4a", ".aac"}
COVER_NAMES = ("cover.jpg", "cover.jpeg", "cover.png", "folder.jpg", "folder.jpeg", "folder.png", "front.jpg")
_LRC_TIME = re.compile(r"\[(\d+):(\d+(?:[.:]\d+)?)\]")
_LRC_WORD = re.compile(r"<(\d+):(\d+(?:[.:]\d+)?)>")


def plenio_owned(songs: Iterable[Any]) -> tuple[set[Path], dict[Path, set[str]]]:
    """The files the release records' songs own, and per folder the records' names (``River`` of
    ``River.plenio.json``): Export Release names every file of a song after it."""
    owned: set[Path] = set()
    stems: dict[Path, set[str]] = {}
    for song in songs:
        for kind, path in song.files.items():
            if kind != "stems":
                owned.add(Path(path).resolve())
        folder = song.record.parent.resolve()
        stems.setdefault(folder, set()).add(song.record.name.removesuffix(".plenio.json"))
    return owned, stems


def is_plenio_file(path: Path, owned: set[Path], stems: Mapping[Path, set[str]]) -> bool:
    """A file of a Plenio song: listed by its record, named after it (``River.flac``, ``River (original).flac``,
    ``River take 2.flac``) or in its stems folder (``River-stems``)."""
    resolved = path.resolve()
    if resolved in owned:
        return True
    for stem in stems.get(resolved.parent, ()):
        rest = path.name[len(stem) :]
        if path.name.startswith(stem) and rest[:1] in (".", " ", "(", "-"):
            return True
    parent = resolved.parent
    return parent.name.endswith("-stems") and parent.name[: -len("-stems")] in stems.get(parent.parent, set())


def open_media(av: Any, path: Path) -> Any:
    """Open an audio file with PyAV for its tags and pictures. Before PyAV 19 the tags are read with
    ``metadata_errors="ignore"`` (else a tag that is not UTF-8 raised); PyAV 19 removed that argument - passing
    it raised, and a file showed no tags at all - and always reads them as UTF-8 with ``surrogateescape``,
    which :func:`tag_text` cleans."""
    if int(str(av.__version__).split(".")[0]) < 19:
        return av.open(str(path), metadata_errors="ignore")
    return av.open(str(path))


def tag_text(value: object) -> str:
    """A tag's text as valid UTF-8: bytes that are not UTF-8 (PyAV 19 hands them over as surrogates) are
    dropped, as ``metadata_errors="ignore"`` did - a surrogate would break the page's JSON."""
    text = str(value)
    try:
        return text.encode("utf-8", "surrogateescape").decode("utf-8", "ignore")
    except UnicodeEncodeError:
        return text.encode("utf-8", "ignore").decode("utf-8")


def probe(path: Path) -> dict[str, Any]:
    """The file's tags (lower-case names), its length in seconds, and whether it carries a picture."""
    try:
        import av
    except ImportError:
        return {}
    try:
        with open_media(av, path) as container:
            tags: dict[str, str] = {}
            for key, value in (container.metadata or {}).items():
                tags.setdefault(tag_text(key).lower(), tag_text(value))
            picture = False
            seconds = container.duration / 1_000_000 if container.duration else 0.0
            for stream in container.streams:
                if stream.type == "audio":
                    # Ogg and Opus keep their tags on the stream
                    for key, value in (stream.metadata or {}).items():
                        tags.setdefault(tag_text(key).lower(), tag_text(value))
                    if not seconds and stream.duration and stream.time_base:
                        seconds = float(stream.duration * stream.time_base)
                elif stream.type == "video":
                    attached = getattr(getattr(av, "stream", None), "Disposition", None)
                    flag = getattr(attached, "attached_pic", None)
                    disposition = getattr(stream, "disposition", 0)
                    picture = picture or (
                        bool(disposition & flag) if flag is not None else stream.frames <= 1
                    )
            return {"tags": tags, "seconds": round(float(seconds), 3), "picture": picture}
    except Exception:  # noqa: BLE001 - a file PyAV cannot read is still listed by its name
        return {}


def lyrics_of(tags: Mapping[str, str]) -> str:
    for key, value in tags.items():
        if (key.startswith("lyrics") or key.startswith("unsyncedlyrics")) and str(value).strip():
            return str(value).replace("\r\n", "\n").strip()
    return ""


def sidecars(path: Path) -> dict[str, Path]:
    """Files beside the audio that belong to it: timed lyrics (``.lrc``, ``.srt``) and a cover of the same
    name, else the folder's cover."""
    found: dict[str, Path] = {}
    for suffix in (".lrc", ".srt"):
        candidate = path.with_suffix(suffix)
        if candidate.is_file():
            found["lines"] = candidate
            break
    for suffix in (".jpg", ".jpeg", ".png"):
        candidate = path.with_suffix(suffix)
        if candidate.is_file():
            found["cover"] = candidate
            break
    else:
        for name in COVER_NAMES:
            candidate = path.parent / name
            if candidate.is_file():
                found["cover"] = candidate
                break
    return found


def _seconds(minutes: str, rest: str) -> float:
    return int(minutes) * 60 + float(rest.replace(":", "."))


def parse_lrc(text: str) -> list[dict[str, Any]]:
    """Timed lines of an LRC file (``[01:23.45]words``; several times before a line repeat it). Word times of
    enhanced LRC (``<01:23.45>word``) become the line's units, so it lights up word by word."""
    entries: list[tuple[float, str, list[tuple[float, int]]]] = []
    for raw in text.splitlines():
        times = list(_LRC_TIME.finditer(raw))
        if not times:
            continue
        body = raw[times[-1].end() :].lstrip()
        # each word time with the length of the text before it
        marks: list[tuple[float, int]] = []
        plain = ""
        position = 0
        for match in _LRC_WORD.finditer(body):
            plain += body[position : match.start()]
            marks.append((_seconds(match.group(1), match.group(2)), len(plain.rstrip())))
            position = match.end()
        plain = (plain + body[position:]).rstrip()
        if not plain.strip():
            continue
        for match in times:
            entries.append((_seconds(match.group(1), match.group(2)), plain, marks))
    entries.sort(key=lambda e: e[0])
    lines = []
    for k, (start, words, marks) in enumerate(entries):
        end = entries[k + 1][0] if k + 1 < len(entries) else start + 4.0
        units = [[round(start, 3), len(words)]]
        if marks:
            if marks[0][1] > 0:
                marks = [(start, 0), *marks]
            # from a word's time the line shows up to the end of that word: the next word's start
            cuts = [cut for _, cut in marks[1:]] + [len(words)]
            units = [[round(t, 3), cut] for (t, _), cut in zip(marks, cuts, strict=True) if cut > 0]
        lines.append(
            {
                "text": words,
                "start": round(start, 3),
                "end": round(max(end - 0.05, start + 0.3), 3),
                "units": units,
            }
        )
    return lines


def summarize_other(path: Path, root: Path, song_id: str) -> tuple[dict[str, Any], dict[str, Path]]:
    """The library's summary of an audio file not from Plenio, and its files."""
    facts = probe(path)
    tags: dict[str, str] = facts.get("tags") or {}
    extra = sidecars(path)
    stat = path.stat()
    created = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(stat.st_mtime))
    year = re.match(r"\d{4}", tags.get("date") or tags.get("year") or "")
    lyrics = lyrics_of(tags)
    files: dict[str, Path] = {"audio": path, **extra}
    summary: dict[str, Any] = {
        "id": song_id,
        "other": True,
        "title": tags.get("title", "").strip() or path.stem,
        "artist": tags.get("artist", "").strip() or tags.get("album_artist", "").strip(),
        "album": tags.get("album", "").strip(),
        "created": created,
        "year": year.group(0) if year else created[:4],
        "seconds": float(facts.get("seconds") or 0.0),
        "model": "",
        "kind": "other",
        "brief": {},
        "genre": tags.get("genre", "").strip(),
        "mood": "",
        "language": "",
        "vocals": "",
        "instrumental": False,
        "arrangement": "off",
        "template": "",
        "style": "",
        "lyrics": lyrics,
        "loudness": {"lufs": None, "true_peak": None, "range": None},
        "tags": {
            k: v
            for k, v in tags.items()
            if not k.startswith("lyrics") and k not in ("encoder", "encoded_by") and len(str(v)) < 300
        },
        "plenio": "",
        "folder": path.parent.relative_to(root).as_posix() if path.parent.is_relative_to(root) else "",
        "file": path.name,
        "takes_key": "",
        "has": {
            "audio": True,
            "original": False,
            "cover": "cover" in extra or bool(facts.get("picture")),
            "embedded_cover": "cover" not in extra and bool(facts.get("picture")),
            "pdf": False,
            "lines": "lines" in extra,
            "notes": False,
            "stems": False,
            "timing": False,
            "score": False,
        },
        "bpm": None,
        "score_key": "",
        "score_meter": "",
        "seeds": {},
        "writer": "",
    }
    return summary, files


def timed_lines(files: Mapping[str, Path]) -> list[dict[str, Any]]:
    from .library import parse_srt

    path = files.get("lines")
    if not path:
        return []
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix.lower() == ".lrc":
        return parse_lrc(text)
    return [
        {
            "text": cue["text"].replace("\n", " "),
            "start": cue["start"],
            "end": cue["end"],
            "units": [[cue["start"], len(cue["text"])]],
        }
        for cue in parse_srt(text)
    ]


def owned(path: Path, files: Mapping[str, Path]) -> list[Path]:
    """What removing the song moves or deletes: the audio and its own lyrics and cover - never the folder's
    cover, which other songs share."""
    found = [path.resolve()]
    for kind, file in files.items():
        if kind in ("lines", "cover") and file.name not in COVER_NAMES and file.resolve() not in found:
            found.append(file.resolve())
    return [f for f in found if f.is_file()]


def embedded_cover(path: Path, song_id: str, cache: Path) -> Path | None:
    """The picture in the audio file, saved once into the player's cache (``covers/<id>.jpg``)."""
    try:
        import av
    except ImportError:
        return None
    stamp = int(path.stat().st_mtime)
    digest = hashlib.sha1(f"{song_id}|{stamp}".encode()).hexdigest()[:10]
    for suffix in (".jpg", ".png"):
        done = cache / "covers" / f"{digest}{suffix}"
        if done.is_file():
            return done
    try:
        with open_media(av, path) as container:
            for stream in container.streams:
                if stream.type != "video":
                    continue
                for packet in container.demux(stream):
                    data = bytes(packet)
                    if not data:
                        continue
                    suffix = ".png" if data[:4] == b"\x89PNG" else ".jpg"
                    target = cache / "covers" / f"{digest}{suffix}"
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(data)
                    return target
    except Exception:  # noqa: BLE001 - no cover then
        return None
    return None
