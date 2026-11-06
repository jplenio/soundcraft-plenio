"""The routes SoundCraft's Plenio add-in needs beyond Plenio's own and its Song API, under ``/scp/v1``.

Everything that makes songs goes through Plenio's Song API (``/plenio/api/v1``) unchanged; these routes
only answer what that API does not: which add-in and Plenio this is, and which model files the YuE2
templates need, where they are and where a missing one goes (SoundCraft downloads them itself), the
stems of a take, and where every bar of a score lies in its take (a song without words).

MiniMax is not part of the add-in: its model files and template are left out of every answer.
"""

from __future__ import annotations

import logging
import math
import re
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any

BASE = "/scp/v1"
WRAPPER_VERSION = "0.4.1"
MAX_ANCHORS = 20_000
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
            "paths": {"song_api": "/plenio/api/v1", "models": f"{BASE}/models", "stems": f"{BASE}/stems", "beats": f"{BASE}/beats"},
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




SEPARATION_MODEL = "bs-roformer-4stem"
"""The catalogue's separation model (BS-RoFormer, four stems)."""
_separators: dict[str, Any] = {}
"""Loaded separators by file: loaded once, kept while the studio runs."""


def inside(path: Path, root: Path) -> bool:
    """Whether ``path`` lies inside ``root`` (both resolved): the stems route reads and writes nowhere else."""
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def read_audio(path: Path) -> tuple[Any, int]:
    """An audio file as float32 ``[channels, frames]`` at its own rate (PyAV, which ComfyUI brings)."""
    import av
    import numpy as np

    with av.open(str(path)) as container:
        stream = container.streams.audio[0]
        rate = int(stream.rate)
        layout = stream.layout.name if stream.layout is not None else "stereo"
        resampler = av.AudioResampler(format="fltp", layout=layout, rate=rate)
        chunks = []
        for frame in container.decode(stream):
            chunks.extend(f.to_ndarray() for f in resampler.resample(frame))
        chunks.extend(f.to_ndarray() for f in resampler.resample(None))
    if not chunks:
        raise ValueError(f"{path.name} holds no audio")
    return np.concatenate(chunks, axis=1).astype(np.float32), rate


def separate_file(source: Path, target: Path, separator: Any) -> dict[str, Any]:
    """Split ``source`` into Plenio's stems plus the rest (their sum is the source again) and write each
    as FLAC into ``target``."""
    from .plenio_vendor.plenio.core.audio.stems import REST, make_stems
    from .plenio_vendor.plenio.core.release import write_audio

    samples, rate = read_audio(source)
    stems = make_stems(samples, rate, separator.separate(samples, rate), source=getattr(separator, "name", ""))
    target.mkdir(parents=True, exist_ok=True)
    files = {}
    for name, signal in [*zip(stems.names, stems.stems, strict=True), (REST, stems.residual)]:
        path = target / f"{name}.flac"
        write_audio(path, signal, rate, "flac")
        files[name] = str(path)
    return {"rate": rate, "stems": files, "order": [*stems.names, REST]}


async def stems(request: Any) -> Any:
    import asyncio

    from aiohttp import web

    import folder_paths  # type: ignore[import-not-found]

    from .plenio_vendor.plenio.comfy import audio_models
    from .plenio_vendor.plenio.core import models as catalogue_module

    try:
        data = await request.json()
    except ValueError:
        return _error("bad_request", "the body is not JSON", 400)
    output = Path(folder_paths.get_output_directory())
    source = Path(str(data.get("file") or ""))
    if not source.is_file() or not inside(source, output):
        return _error("not_found", "the take must be a file of this studio's output folder", 404)
    catalogue = catalogue_module.load_catalogue(VENDOR_ROOT / "resources" / "models.toml")
    model = catalogue.get(SEPARATION_MODEL)
    found = folder_paths.get_full_path(model.folder, model.file) if model else None
    if not found:
        return _error("missing_model", "the separation model (BS-RoFormer) is not installed", 409)

    def work() -> dict[str, Any]:
        separator = _separators.get(found)
        if separator is None:
            separator = audio_models.load("separation", model.file, Path(found)).engine
            _separators[found] = separator
        return separate_file(source, source.parent / f"{source.stem}-stems", separator)

    try:
        answer = await asyncio.to_thread(work)
    except Exception as error:
        log.exception("SoundCraft Plenio: stems")
        return _error("internal", f"the stems were not made: {error}", 500)
    return web.json_response(answer)


def warp_of(value: Any) -> list[float] | None:
    """A warp from a request: ``[a, b]`` of finite numbers, or nothing."""
    if not isinstance(value, list) or len(value) != 2:
        return None
    if not all(isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) for x in value):
        return None
    return [float(value[0]), float(value[1])]


def anchors_of(value: Any) -> list[list[float]]:
    """Sung syllables from a request: pairs ``[t_audio, t_score]`` of finite numbers; others fall out."""
    if not isinstance(value, list):
        return []
    return [pair for pair in map(warp_of, value[:MAX_ANCHORS]) if pair is not None]


async def beats(request: Any) -> Any:
    """Where every bar of a score lies in its take, from the music (``beats.py``). Without a warp, Plenio's
    estimate of where the score sits comes first, as its Player makes it. A second or so of CPU; no model."""
    import asyncio

    from aiohttp import web

    import folder_paths  # type: ignore[import-not-found]

    from . import beats as beat_map
    from .plenio_vendor.plenio.core.score import canonical
    from .plenio_vendor.plenio.player import align

    try:
        data = await request.json()
    except ValueError:
        return _error("bad_request", "the body is not JSON", 400)
    output = Path(folder_paths.get_output_directory())
    source = Path(str(data.get("file") or ""))
    score = data.get("score")
    if not source.is_file() or not inside(source, output):
        return _error("not_found", "the take must be a file of this studio's output folder", 404)
    if not isinstance(score, str) or not score.strip():
        return _error("bad_request", "`score` (the take's ABC) is required", 400)
    warp, anchors = warp_of(data.get("warp")), anchors_of(data.get("anchors"))
    try:
        answer = await asyncio.to_thread(beat_map.measure, source, score, warp, anchors, align, canonical)
    except Exception as error:
        log.exception("SoundCraft Plenio: beats")
        return _error("internal", f"the bars of the take were not found: {error}", 500)
    return web.json_response(answer)


def register(routes: Any) -> None:
    routes.get(BASE)(info)
    routes.get(f"{BASE}/models")(models)
    routes.post(f"{BASE}/stems")(stems)
    routes.post(f"{BASE}/beats")(beats)
