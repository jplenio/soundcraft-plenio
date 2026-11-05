"""Where the Plenio Player reads songs and keeps the listener's state - the same for every way it starts (by
hand, from its launcher files, from ComfyUI), so playlists and settings are always the same ones."""

from __future__ import annotations

import os
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[2]


def default_folders() -> list[Path]:
    """``PLENIO_PLAYER_FOLDER`` (several separated like ``PATH``), else ComfyUI's output folder when Plenio
    sits in ``ComfyUI/custom_nodes``, else the current folder."""
    configured = os.environ.get("PLENIO_PLAYER_FOLDER", "").strip()
    if configured:
        return [Path(p) for p in configured.split(os.pathsep) if p.strip()]
    output = PACKAGE_ROOT.parent.parent / "output"  # ComfyUI/custom_nodes/<pack> -> ComfyUI/output
    if PACKAGE_ROOT.parent.name == "custom_nodes" and output.is_dir():
        return [output]
    return [Path.cwd()]


def state_dir() -> Path:
    """``PLENIO_PLAYER_STATE``, else ``~/.plenio/player``: the playlists, favourites, plays and settings, the
    library cache, the waveforms and the log of a player started from ComfyUI."""
    base = os.environ.get("PLENIO_PLAYER_STATE", "").strip()
    return Path(base) if base else Path.home() / ".plenio" / "player"
