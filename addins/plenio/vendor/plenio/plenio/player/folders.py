"""The folders the Plenio Player reads (owner's request 2026-10-16: several, chosen in its Settings), kept in
``library.json`` in its state folder - and the folder browser its Settings page chooses them with.

With a ``library.json`` its folders win over ``--folder`` and the default (ComfyUI's output folder), so the
player started from ComfyUI reads the folders chosen in Settings too. Each folder can also take *other
music*: audio files not from Plenio (``plenio.player.other``).
"""

from __future__ import annotations

import json
import os
import string
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CONFIG = "library.json"
MAX_FOLDERS = 50
HIDDEN = {"$recycle.bin", "system volume information", "$windows.~ws", "$winreagent", "recovery"}


@dataclass(frozen=True)
class Folder:
    path: Path
    other: bool = False

    def as_json(self) -> dict[str, Any]:
        return {"path": str(self.path), "other": self.other}


def load(state_dir: Path) -> list[Folder] | None:
    """The folders chosen in Settings; ``None`` when none were chosen (the start's folders hold)."""
    path = state_dir / CONFIG
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return [Folder(Path(f["path"]), bool(f.get("other"))) for f in data.get("folders") or []]
    except (OSError, ValueError, KeyError, TypeError):
        return None


def save(state_dir: Path, folders: list[Folder]) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_dir / CONFIG
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps({"folders": [f.as_json() for f in folders]}, indent=2), encoding="utf-8")
    temp.replace(path)


def forget(state_dir: Path) -> None:
    """Back to the folders the player starts with."""
    (state_dir / CONFIG).unlink(missing_ok=True)


def validate(raw: Any) -> list[Folder]:
    """The folders of a request: absolute paths of existing folders, each once. Raises ``ValueError`` naming
    the first that is not."""
    if not isinstance(raw, list) or not raw:
        raise ValueError("choose at least one folder")
    if len(raw) > MAX_FOLDERS:
        raise ValueError(f"at most {MAX_FOLDERS} folders")
    folders: list[Folder] = []
    seen: set[Path] = set()
    for item in raw:
        text = item.get("path") if isinstance(item, dict) else None
        if not isinstance(text, str) or not text.strip():
            raise ValueError("every folder needs a path")
        path = Path(text.strip()).expanduser()
        if not path.is_absolute():
            raise ValueError(f"{text}: not a full path (one that starts at a drive or at /)")
        if not path.is_dir():
            raise ValueError(f"{text}: no such folder")
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        folders.append(Folder(resolved, bool(item.get("other"))))
    return folders


def places() -> list[dict[str, str]]:
    """Where browsing starts: the home folder, its music folder, and the drives (Windows) or ``/``."""
    found: list[dict[str, str]] = []
    home = Path.home()
    found.append({"name": "Home", "path": str(home)})
    for name in ("Music", "Musik"):
        if (home / name).is_dir():
            found.append({"name": name, "path": str(home / name)})
            break
    if sys.platform == "win32":
        for letter in string.ascii_uppercase:
            drive = f"{letter}:\\"
            if os.path.exists(drive):
                found.append({"name": f"{letter}:", "path": drive})
    else:
        found.append({"name": "/", "path": "/"})
    return found


def list_dirs(path: str | None) -> dict[str, Any]:
    """The subfolders of ``path`` (names and paths, never files), its parent, and the places to start from."""
    answer: dict[str, Any] = {"path": None, "parent": None, "dirs": [], "places": places(), "error": ""}
    if not path:
        return answer
    folder = Path(path).expanduser()
    if not folder.is_absolute() or not folder.is_dir():
        answer["error"] = f"{path}: no such folder"
        return answer
    folder = folder.resolve()
    answer["path"] = str(folder)
    answer["parent"] = str(folder.parent) if folder.parent != folder else None
    try:
        names = []
        with os.scandir(folder) as entries:
            for entry in entries:
                try:
                    if entry.is_dir() and entry.name.lower() not in HIDDEN and not entry.name.startswith("."):
                        names.append(entry.name)
                except OSError:
                    continue
        answer["dirs"] = [
            {"name": name, "path": str(folder / name)} for name in sorted(names, key=str.lower)[:2000]
        ]
    except OSError as error:
        answer["error"] = f"{folder}: {error.strerror or error}"
    return answer
