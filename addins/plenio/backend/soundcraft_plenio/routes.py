"""The routes SoundCraft's Plenio add-in needs beyond Plenio's own and its Song API, under ``/scp/v1``.

Everything that makes songs goes through Plenio's Song API (``/plenio/api/v1``) unchanged; these routes
only answer what that API does not: which add-in and Plenio this is, and which model files the YuE2
templates need, where they are and where a missing one goes (SoundCraft downloads them itself).

MiniMax is not part of the add-in: its model files and template are left out of every answer.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any

BASE = "/scp/v1"
WRAPPER_VERSION = "0.1.0"
PACKAGE_ROOT = Path(__file__).resolve().parent
VENDOR_ROOT = PACKAGE_ROOT / "plenio_vendor"
MINIMAX = re.compile("minimax", re.IGNORECASE)
TEMPLATES = {"yue2-song": "1 · YuE2 · Song", "yue2-cover": "2 · YuE2 · Cover", "yue2-daw": "5 · YuE2 · DAW"}
"""The Song API's template ids and the catalogue's names for them."""

log = logging.getLogger("soundcraft-plenio")


def vendor_info(text: str) -> dict[str, str]:
    """The ``key = "value"`` lines of ``VENDOR.toml`` (written by ``sync_plenio.py``)."""
    found: dict[str, str] = {}
    for line in text.splitlines():
        match = re.match(r'^([a-z_]+)\s*=\s*"?([^"]*)"?\s*$', line.strip())
        if match:
            found[match.group(1)] = match.group(2)
    return found


def models_answer(
    catalogue: Mapping[str, Any],
    locate: Callable[[str, str], Path | None],
    target: Callable[[str], Path | None],
    readiness: Callable[[Mapping[str, Any], Any, Iterable[str]], list[Any]],
    take_inventory: Callable[[Mapping[str, Any], Callable[[str, str], Path | None]], Any],
) -> dict[str, Any]:
    """The model files of the YuE2 templates, their state and where each goes, and per template what is
    missing. The callables are Plenio's (``plenio.core.models``) and ComfyUI's (``folder_paths``)."""
    kept = {key: model for key, model in catalogue.items() if not MINIMAX.search(model.id) and not MINIMAX.search(model.file)}
    inventory = take_inventory(kept, locate)
    models = []
    for model in kept.values():
        path = locate(model.folder, model.file)
        folder = target(model.folder)
        models.append(
            {
                "id": model.id,
                "file": model.file,
                "folder": model.folder,
                "url": model.url,
                "bytes": model.bytes,
                "licence": model.licence,
                "non_commercial": model.non_commercial,
                "role": model.role,
                "default": model.default,
                "templates": [t for t in model.templates if not MINIMAX.search(t)],
                "optional_templates": [t for t in model.optional_templates if not MINIMAX.search(t)],
                "status": inventory.status(model),
                "path": str(path) if path else None,
                "target": str(folder / model.file) if folder else None,
            }
        )
    templates = {}
    for api_id, name in TEMPLATES.items():
        found = readiness(kept, inventory, [name])
        if not found:
            continue
        ready = found[0]
        templates[api_id] = {
            "name": name,
            "ready": ready.ready,
            "missing": [m.id for m in ready.missing],
            "incomplete": [m.id for m in ready.incomplete],
            "optional_missing": [m.id for m in ready.optional_missing],
            "missing_bytes": ready.missing_bytes,
        }
    return {"models": models, "templates": templates}


def _error(code: str, message: str, status: int) -> Any:
    from aiohttp import web

    return web.json_response({"error": {"code": code, "message": message}}, status=status)


async def info(request: Any) -> Any:
    from aiohttp import web

    from .plenio_vendor.plenio import __version__ as plenio_version

    manifest = VENDOR_ROOT / "VENDOR.toml"
    vendor = vendor_info(manifest.read_text(encoding="utf-8")) if manifest.is_file() else {}
    try:
        from comfyui_version import __version__ as comfyui_version  # type: ignore[import-not-found]
    except ImportError:
        comfyui_version = ""
    return web.json_response(
        {
            "addin": "soundcraft-plenio",
            "wrapper": WRAPPER_VERSION,
            "plenio": plenio_version,
            "vendor_commit": vendor.get("commit", ""),
            "comfyui": comfyui_version,
            "templates": list(TEMPLATES),
            "paths": {"song_api": "/plenio/api/v1", "models": f"{BASE}/models"},
        }
    )


async def models(request: Any) -> Any:
    from aiohttp import web

    import folder_paths  # type: ignore[import-not-found]

    from .plenio_vendor.plenio.core import models as catalogue_module

    def locate(folder: str, file: str) -> Path | None:
        try:
            found = folder_paths.get_full_path(folder, file)
        except KeyError:
            return None
        return Path(found) if found else None

    def target(folder: str) -> Path | None:
        try:
            paths = folder_paths.get_folder_paths(folder)
        except KeyError:
            return None
        return Path(paths[0]) if paths else None

    try:
        catalogue = catalogue_module.load_catalogue(VENDOR_ROOT / "resources" / "models.toml")
        answer = models_answer(catalogue, locate, target, catalogue_module.readiness, catalogue_module.take_inventory)
    except Exception as error:  # a broken catalogue must not take the route down with a 500 page
        log.exception("SoundCraft Plenio: model catalogue")
        return _error("internal", f"the model catalogue could not be read: {error}", 500)
    return web.json_response(answer)


def register(routes: Any) -> None:
    routes.get(BASE)(info)
    routes.get(f"{BASE}/models")(models)
