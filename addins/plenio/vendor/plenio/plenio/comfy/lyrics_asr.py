"""The lyrics ASR on the host: model folder, result cache and the worker run (Transcribe Lyrics, and Export
Release's lyrics subtitles)."""

from __future__ import annotations

import uuid
from dataclasses import replace
from pathlib import Path
from typing import Any

from ..core.asr import (
    QWEN3_LANGUAGES,
    AsrCache,
    AsrEngine,
    AsrNotes,
    AsrResult,
    AsrSettings,
    cache_key,
    can_time,
    engine_for,
    fallback_note,
    result_from_dict,
)
from ..core.assets import ensure_asset, missing_files
from ..core.errors import PlenioDependencyError, PlenioError, PlenioUserError, PlenioWorkerError
from ..core.workers import WorkerEnv, WorkerLimits, run_worker
from . import host
from .shared import asset_catalogue

LANGUAGES = {
    "en": "English",
    "de": "German",
    "fr": "French",
    "es": "Spanish",
    "it": "Italian",
    "pt": "Portuguese",
    "nl": "Dutch",
    "sv": "Swedish",
    "da": "Danish",
    "no": "Norwegian",
    "fi": "Finnish",
    "pl": "Polish",
    "cs": "Czech",
    "ru": "Russian",
    "uk": "Ukrainian",
    "tr": "Turkish",
    "el": "Greek",
    "ar": "Arabic",
    "hi": "Hindi",
    "ja": "Japanese",
    "ko": "Korean",
    "zh": "Chinese",
}
LANGUAGES.update(
    {code: name for name, code in QWEN3_LANGUAGES.items() if code not in LANGUAGES}
)  # the other languages Qwen3-ASR hears (Cantonese, Indonesian, Thai ...)


def language_code(value: str) -> str:
    """``auto``/empty -> ``""``; a code or an English language name -> its code."""
    text = value.strip()
    if not text or text.lower() == "auto":
        return ""
    if text.lower() in LANGUAGES:
        return text.lower()
    for code, name in LANGUAGES.items():
        if name.lower() == text.lower():
            return code
    raise PlenioUserError(
        f"Unknown lyrics language {value!r}.",
        hint=f"Use 'auto', a language code or one of: {', '.join(LANGUAGES.values())}.",
    )


def model_folder(asset_id: str, progress: host.Progress) -> tuple[Path, str]:
    config = host.load_config()
    asset = asset_catalogue()[asset_id]
    configured = config.asset_paths.get(asset_id)
    if configured is not None:
        if missing_files(asset, configured):
            raise PlenioUserError(
                f"The folder configured for {asset_id} ({configured}) does not hold the expected model files.",
                hint="Fix [asset_paths] in the Plenio config.toml or remove the entry; files: "
                + ", ".join(f.path for f in asset.files),
            )
        return configured, asset.revision
    folder = ensure_asset(
        asset,
        host.asset_root(config),
        config,
        progress=lambda done, total, _message: progress.update(0.3 * done / max(total, 1)),
        is_cancelled=host.is_interrupted,
    )
    return folder, asset.revision


def asr_notes() -> AsrNotes:
    return AsrNotes(host.user_directory() / "plenio" / "cache" / "asr-notes")


def asr_cache() -> AsrCache:
    return AsrCache(host.user_directory() / "plenio" / "cache" / "asr")


def revision(engine: AsrEngine) -> str:
    """The model revision that keys the cache: the ASR's, and the aligner's when there is one."""
    assets = asset_catalogue()
    pinned = assets[engine.asset_id].revision
    return f"{pinned}+{assets[engine.aligner_asset_id].revision}" if engine.aligner_asset_id else pinned


def run_asr(audio: Any, settings: AsrSettings, source_sha256: str, progress: host.Progress) -> AsrResult:
    """The ASR of ``audio`` (a ComfyUI AUDIO), from the cache when the same audio was transcribed with the same
    settings before - also after a restart.

    Qwen3-ASR hands a language its aligner cannot time to its fallback (faster-whisper): before the run when
    the language is given, after it when Qwen3 detected it - and the whole song when Qwen3 cannot run here (a
    package too old or missing) while the fallback can. The result says so (``settings.engine_note``).
    """
    engine = engine_for(settings.engine)
    if engine.fallback and not can_time(engine, settings.language):
        return _with_note(
            _run(audio, replace(settings, engine=engine.fallback), source_sha256, progress),
            fallback_note(engine, settings.language),
        )
    try:
        result = _run(audio, settings, source_sha256, progress)
    except PlenioWorkerError as error:
        if not engine.fallback or error.details.get("type") != PlenioDependencyError.__name__:
            raise
        try:
            heard = _run(audio, replace(settings, engine=engine.fallback), source_sha256, progress)
        except PlenioError:
            raise error from None  # neither can run: what Qwen3 needs is the fix to name
        return _with_note(
            heard, f"{engine.label} could not run ({error.message}): heard by {engine.fallback}"
        )
    if engine.fallback and result.settings.get("timed") is False:
        again = replace(settings, engine=engine.fallback, language=settings.language or result.language)
        return _with_note(_run(audio, again, source_sha256, progress), fallback_note(engine, result.language))
    return result


def _with_note(result: AsrResult, note: str) -> AsrResult:
    return replace(result, settings={**result.settings, "engine_note": note})


def _run(audio: Any, settings: AsrSettings, source_sha256: str, progress: host.Progress) -> AsrResult:
    engine = engine_for(settings.engine)
    cache = asr_cache()
    key = cache_key(source_sha256, settings, revision(engine))
    cached = cache.get(key)
    if cached is not None:
        return cached  # a stored result: no model, no worker, the same draft as before
    model_dir, _revision = model_folder(engine.asset_id, progress)
    aligner_dir = model_folder(engine.aligner_asset_id, progress)[0] if engine.aligner_asset_id else None
    import numpy as np

    config = host.load_config()
    samples = host.mono_16k(audio)
    folder = host.temp_directory() / "plenio"
    folder.mkdir(parents=True, exist_ok=True)
    audio_file = folder / f"asr-{uuid.uuid4().hex}.npy"
    np.save(audio_file, samples)
    try:
        if settings.device != "cpu":
            host.free_memory(engine.vram_bytes)
        data = run_worker(
            engine.worker,
            {
                "engine": engine.id,
                "model_dir": str(model_dir),
                **({"aligner_dir": str(aligner_dir)} if aligner_dir is not None else {}),
                "audio": str(audio_file),
                "language": settings.language,
                "beam_size": settings.beam_size,
                "seed": settings.seed,
                "regions": [[a, b] for a, b in settings.regions],
                "device": settings.device,
            },
            env=WorkerEnv(pythonpath=(host.package_root(),)),
            limits=WorkerLimits(
                timeout_s=config.worker_timeout_s, idle_timeout_s=config.worker_idle_timeout_s
            ),
            on_progress=lambda fraction, _message: progress.update(
                None if fraction is None else 0.3 + 0.7 * fraction
            ),
            is_cancelled=host.is_interrupted,
        )
    finally:
        audio_file.unlink(missing_ok=True)
    result = result_from_dict(data)
    cache.put(key, result)
    return result
