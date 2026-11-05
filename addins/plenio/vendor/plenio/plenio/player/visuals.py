"""The listener's own Plenio Drop presets: JSON files in the player's visuals folder (``visuals`` in the
state folder). The page reads them (and again while they are edited), and saves a copy of a preset there
to edit. The page checks and runs them; a preset is data the page's own formula language reads, never
script, so a file someone shares can draw and nothing else.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

FILE_LIMIT = 256 * 1024
COUNT_LIMIT = 200
README = """Plenio Drop presets
===================

Every .json file here is a visual of your own in the Plenio Player (Visuals: My presets). The player reads
the folder again every few seconds: save a file and the visual changes on screen.

Start from a copy: in the player, Visuals > Plenio Drop > Edit a copy. The format, every parameter, the
music's names and the functions are in the guide: docs/user/concepts/player-visuals.md, online at
https://github.com/jplenio/Plenio-Music-Production-System/blob/main/docs/user/concepts/player-visuals.md
"""


def visuals_dir(state_dir: Path) -> Path:
    return state_dir / "visuals"


def list_presets(folder: Path) -> list[dict[str, Any]]:
    """The preset files (name, text, time of the last change); files too large or not UTF-8 are left
    out."""
    if not folder.is_dir():
        return []
    found: list[dict[str, Any]] = []
    for path in sorted(folder.glob("*.json"), key=lambda p: p.name.lower())[:COUNT_LIMIT]:
        try:
            if not path.is_file() or path.stat().st_size > FILE_LIMIT:
                continue
            found.append(
                {
                    "name": path.name,
                    "text": path.read_text(encoding="utf-8"),
                    "mtime": path.stat().st_mtime,
                }
            )
        except (OSError, UnicodeDecodeError):
            continue
    return found


def file_name(name: str) -> str:
    """A preset's name as a file name: ``Nebula Swirl (my copy)`` -> ``nebula-swirl-my-copy.json``."""
    stem = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:60] or "preset"
    return f"{stem}.json"


def save_copy(folder: Path, name: str, text: str) -> Path:
    """Save a preset under a name of its own (``-2``, ``-3`` ... when taken); never overwrites a file."""
    if len(text.encode("utf-8")) > FILE_LIMIT:
        raise ValueError("the preset is too large")
    folder.mkdir(parents=True, exist_ok=True)
    readme = folder / "README.txt"
    if not readme.exists():
        readme.write_text(README, encoding="utf-8")
    base = file_name(name)
    target = folder / base
    count = 1
    while target.exists():
        count += 1
        target = folder / f"{base.removesuffix('.json')}-{count}.json"
    with target.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    return target


def open_folder(folder: Path) -> None:
    """Show the visuals folder in the system's file manager, with a README on what goes there."""
    folder.mkdir(parents=True, exist_ok=True)
    readme = folder / "README.txt"
    if not readme.exists():
        readme.write_text(README, encoding="utf-8")
    show_folder(folder)


def show_folder(folder: Path, select: Path | None = None) -> None:
    """Show a folder of the player's in the system's file manager (made when it is not there yet), with
    ``select`` - a file in it - chosen where the file manager can.

    On Windows Explorer is started as a program of its own: ``os.startfile`` asks the shell to open the
    folder, and in a player started from ComfyUI (a background process without a window) that did nothing at
    all (owner's report 2026-10-16)."""
    folder.mkdir(parents=True, exist_ok=True)
    chosen = (
        select
        if select is not None and select.parent.resolve() == folder.resolve() and select.is_file()
        else None
    )
    if sys.platform == "win32":
        windir = Path(os.environ.get("WINDIR") or os.environ.get("SystemRoot") or "C:\\Windows")
        explorer = windir / "explorer.exe"
        program = str(explorer) if explorer.is_file() else "explorer.exe"
        shown = chosen.resolve() if chosen else folder.resolve()
        if '"' in str(
            shown
        ):  # no Windows name holds one: nothing slips out of the quotes below as an argument
            raise OSError(f"no folder to show: {shown.name}")
        # Explorer reads /select,"path" - the quotes round the path only (a list of arguments would quote
        # the whole "/select,path", and Explorer then opens Documents instead)
        target = f'/select,"{shown}"' if chosen else f'"{shown}"'
        subprocess.Popen(f'"{program}" {target}')  # noqa: S603 - Explorer with our own folder
    elif sys.platform == "darwin":
        subprocess.Popen(["open", "-R", str(chosen)] if chosen else ["open", str(folder)])  # noqa: S603, S607
    else:
        subprocess.Popen(["xdg-open", str(folder)])  # noqa: S603, S607
