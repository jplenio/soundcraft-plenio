"""Lyrics ASR: engines, settings, results (``plenio.asr/1``) and the on-disk result cache.

The ASR itself runs in a worker process (``plenio.workers.asr``). This module is
pure: it describes what to run and stores what came back.

Engines (owner's decision 2026-10-22): **Qwen3-ASR 1.7B** hears the words and **Qwen3-ForcedAligner 0.6B**
places them on the audio - exact word times, the reference of the subtitle study - in the eleven languages
the aligner knows. **faster-whisper large-v3** stays as the fallback for every other language (and as a
choice in Transcribe Lyrics, so workflows saved with it keep running); the switch is named in the result.

Reproducibility (yue2-cover-design section 5.3): an edited lyrics document stays
valid only while its ASR draft is unchanged, so every result is cached on disk
under a key made of the source audio hash, the vocal regions, the engine, the
model revision and the settings. The cache - not the decoder - guarantees that a
ComfyUI restart gives the same draft.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .alignment import AsrWord, words_from
from .errors import PlenioUserError
from .files import atomic_write_text
from .hashing import sha256_json

ASR_SCHEMA = "plenio.asr/1"
CACHE_VERSION = 2
"""2: Qwen3 hears a song in pieces of 20 s (``workers.asr.PIECE_S``) - a result of one long piece is not used."""


@dataclass(frozen=True)
class AsrEngine:
    id: str
    label: str
    asset_id: str
    """Catalogue id of the model folder (``resources/assets.toml``)."""
    worker: str
    licence: str
    environment: str = "host"
    """``host`` = ComfyUI's Python; otherwise the name of an isolated package folder."""
    aligner_asset_id: str = ""
    """Catalogue id of the forced aligner that times the heard words (empty: the ASR times them itself)."""
    timed_languages: frozenset[str] = frozenset()
    """Language codes the engine can time; empty = every language it hears."""
    fallback: str = ""
    """The engine (label) for a language this one cannot time."""
    vram_bytes: int = 4 * 2**30
    """What the worker asks ComfyUI to free on the GPU before it starts."""


QWEN3_LANGUAGES = {
    "Chinese": "zh",
    "English": "en",
    "Cantonese": "yue",
    "Arabic": "ar",
    "German": "de",
    "French": "fr",
    "Spanish": "es",
    "Portuguese": "pt",
    "Indonesian": "id",
    "Italian": "it",
    "Korean": "ko",
    "Russian": "ru",
    "Thai": "th",
    "Vietnamese": "vi",
    "Japanese": "ja",
    "Turkish": "tr",
    "Hindi": "hi",
    "Malay": "ms",
    "Dutch": "nl",
    "Swedish": "sv",
    "Danish": "da",
    "Finnish": "fi",
    "Polish": "pl",
    "Czech": "cs",
    "Filipino": "fil",
    "Persian": "fa",
    "Greek": "el",
    "Hungarian": "hu",
    "Macedonian": "mk",
    "Romanian": "ro",
}
"""The languages Qwen3-ASR hears (its model card), by the name it answers with, and their codes."""
ALIGNER_LANGUAGES = frozenset({"zh", "en", "yue", "fr", "de", "it", "ja", "ko", "pt", "ru", "es"})
"""The languages Qwen3-ForcedAligner can time (its model card)."""

QWEN3 = "Qwen3-ASR 1.7B"
WHISPER = "faster-whisper large-v3"
ENGINES: dict[str, AsrEngine] = {
    QWEN3: AsrEngine(
        "qwen3-asr-1.7b",
        QWEN3,
        "qwen3-asr-1.7b-hf",
        "plenio.workers.asr",
        "Apache-2.0 (Qwen3-ASR-1.7B, Qwen3-ForcedAligner-0.6B; inference code from transformers 5.17)",
        aligner_asset_id="qwen3-forcedaligner-0.6b-hf",
        timed_languages=ALIGNER_LANGUAGES,
        fallback=WHISPER,
        vram_bytes=5 * 2**30,
    ),
    WHISPER: AsrEngine(
        "faster-whisper-large-v3",
        WHISPER,
        "faster-whisper-large-v3",
        "plenio.workers.asr",
        "MIT (faster-whisper, CTranslate2, Whisper weights)",
    ),
}
DEFAULT_ENGINE = QWEN3


@dataclass(frozen=True)
class AsrSettings:
    engine: str = DEFAULT_ENGINE
    language: str = ""
    """Empty = detect."""
    device: str = "auto"
    beam_size: int = 5
    seed: int = 0
    regions: tuple[tuple[float, float], ...] = ()
    """Only these (start, end) spans are transcribed; empty = the whole audio."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "engine": self.engine,
            "language": self.language,
            "beam_size": self.beam_size,
            "seed": self.seed,
            "regions": [[round(a, 2), round(b, 2)] for a, b in self.regions],
        }


@dataclass(frozen=True)
class AsrResult:
    engine: str
    model: str
    language: str
    language_probability: float
    segments: tuple[dict[str, Any], ...]
    words: tuple[AsrWord, ...]
    device: str = ""
    seconds: float = 0.0
    settings: Mapping[str, Any] = field(default_factory=dict)
    cached: bool = False

    @property
    def text(self) -> str:
        return " ".join(str(s.get("text", "")).strip() for s in self.segments).strip()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": ASR_SCHEMA,
            "engine": self.engine,
            "model": self.model,
            "language": self.language,
            "language_probability": round(self.language_probability, 4),
            "device": self.device,
            "seconds": round(self.seconds, 2),
            "settings": dict(self.settings),
            "segments": list(self.segments),
            "words": [w.to_dict() for w in self.words],
        }


def result_from_dict(data: Mapping[str, Any], *, cached: bool = False) -> AsrResult:
    if data.get("schema") != ASR_SCHEMA:
        raise PlenioUserError(f"Unsupported ASR result schema {data.get('schema')!r}.")
    return AsrResult(
        engine=str(data["engine"]),
        model=str(data.get("model", "")),
        language=str(data.get("language") or ""),
        language_probability=float(data.get("language_probability") or 0.0),
        segments=tuple(dict(s) for s in data.get("segments", [])),
        words=tuple(words_from(data.get("words", []))),
        device=str(data.get("device", "")),
        seconds=float(data.get("seconds", 0.0)),
        settings=dict(data.get("settings", {})),
        cached=cached,
    )


def engine_for(label: str) -> AsrEngine:
    try:
        return ENGINES[label]
    except KeyError as error:
        raise PlenioUserError(
            f"Unknown ASR engine {label!r}.", hint=f"Choose one of {sorted(ENGINES)}."
        ) from error


def can_time(engine: AsrEngine, language: str) -> bool:
    """Can ``engine`` time words in ``language`` (a code; empty = not known yet)?"""
    return not engine.timed_languages or not language or language in engine.timed_languages


def fallback_note(engine: AsrEngine, language: str) -> str:
    """The line a result carries when ``engine`` handed a language it cannot time to its fallback."""
    return (
        f"{engine.label} cannot time {language!r} words (its aligner knows "
        f"{', '.join(sorted(engine.timed_languages))}): transcribed with {engine.fallback} instead"
    )


def cache_key(source_sha256: str, settings: AsrSettings, model_revision: str) -> str:
    return sha256_json(
        {
            "cache": CACHE_VERSION,
            "source": source_sha256,
            "model_revision": model_revision,
            **settings.to_dict(),
        }
    )


class AsrCache:
    """``<folder>/<key>.json``; a missing or unreadable entry is simply a cache miss."""

    def __init__(self, folder: Path):
        self.folder = folder

    def path(self, key: str) -> Path:
        return self.folder / f"{key}.json"

    def get(self, key: str) -> AsrResult | None:
        path = self.path(key)
        if not path.is_file():
            return None
        try:
            return result_from_dict(json.loads(path.read_text(encoding="utf-8")), cached=True)
        except (OSError, ValueError, KeyError, PlenioUserError):
            return None

    def put(self, key: str, result: AsrResult) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        atomic_write_text(self.path(key), json.dumps(result.to_dict(), ensure_ascii=False))


class AsrNotes:
    """Editor notes of lyrics drafts (``<folder>/<draft sha256>.json``): unsure and left-out words.

    The Song Sheet editor looks a note up by the hash of the draft it shows, so the note needs no
    graph connection and survives ComfyUI's cache (a cached node does not resend its UI output).
    """

    def __init__(self, folder: Path):
        self.folder = folder

    @staticmethod
    def _valid(draft_sha256: str) -> bool:
        return len(draft_sha256) == 64 and all(c in "0123456789abcdef" for c in draft_sha256)

    def put(self, note: Mapping[str, Any]) -> None:
        key = str(note.get("draft_sha256", ""))
        if not self._valid(key):
            raise PlenioUserError(f"Invalid draft hash {key!r} for an ASR note.")
        self.folder.mkdir(parents=True, exist_ok=True)
        atomic_write_text(self.folder / f"{key}.json", json.dumps(dict(note), ensure_ascii=False))

    def get(self, draft_sha256: str) -> dict[str, Any] | None:
        if not self._valid(draft_sha256):
            return None
        path = self.folder / f"{draft_sha256}.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return data if isinstance(data, dict) else None


WEAK_SEGMENT_MAX_WORDS = 3
WEAK_SEGMENT_LOGPROB = -0.7
WEAK_SEGMENT_WORD_P = 0.2
"""A Whisper stock phrase at the end of a clip ("Thank you." in the Phase 4B cover run: 2 words,
avg_logprob -0.86 against -0.10 to -0.35 for the sung lines, one word at p 0.04)."""


def weak_segments(result: AsrResult) -> set[int]:
    """Indices of segments that look like a decoder invention rather than singing.

    Whisper-specific (it needs ``avg_logprob``): a segment of at most three words whose average
    log probability is below -0.7 and which contains a word below p 0.2. Other engines report no
    ``avg_logprob`` and are not filtered.
    """
    weak: set[int] = set()
    for index, segment in enumerate(result.segments):
        logprob = segment.get("avg_logprob")
        if logprob is None or float(logprob) >= WEAK_SEGMENT_LOGPROB:
            continue
        words = [w for w in result.words if w.segment == index]
        if 0 < len(words) <= WEAK_SEGMENT_MAX_WORDS and min(w.p for w in words) < WEAK_SEGMENT_WORD_P:
            weak.add(index)
    return weak


STEM_MARGIN = 0.02
"""How much more confident the ASR must hear a cover's vocal stem than its mix - the mean natural log of the kept
words' probabilities - for the lyrics to be taken from the stem (owner 2026-10-24: the vocal stem only where it
hears better). Measured on 15 of the owner's songs (their lyrics as the reference): the stem heard better in 4,
worse in 8 (separation artefacts) - word error 28.9 % from the mix, 30.0 % from the stem; the more confident
hearing with this margin was the better one in 13 of 15 - 27.3 % (choosing the better one every time: 26.7 %)."""


def confidence(words: Sequence[AsrWord]) -> float | None:
    """How sure the ASR was of what it heard: the mean natural log of the words' probabilities (None: none)."""
    if not words:
        return None
    return sum(math.log(max(w.p, 1e-4)) for w in words) / len(words)


def prefer_stem(mix: Sequence[AsrWord], stem: Sequence[AsrWord]) -> bool:
    """Whether the vocal stem was heard more confidently than the mix, by ``STEM_MARGIN``."""
    heard_mix, heard_stem = confidence(mix), confidence(stem)
    if heard_stem is None:
        return False
    return heard_mix is None or heard_stem > heard_mix + STEM_MARGIN
