"""Qwen3-ASR and Qwen3-ForcedAligner on the host's transformers (vendored from transformers 5.17, see NOTICE.md).

Plenio's glue, not upstream code. Import it only in the ASR worker process: ``register()`` adds the model to
transformers' auto classes of the process that calls it, and the modules import torch and transformers.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

_registered = False


def register() -> None:
    """Make transformers' auto classes resolve the vendored configuration and models (once per process)."""
    global _registered
    if _registered:
        return
    from transformers import AutoConfig, AutoModel

    from .configuration_qwen3_asr import Qwen3ASRConfig, Qwen3ASREncoderConfig
    from .modeling_qwen3_asr import Qwen3ASREncoder, Qwen3ASRModel

    AutoConfig.register("qwen3_asr_encoder", Qwen3ASREncoderConfig, exist_ok=True)
    AutoConfig.register("qwen3_asr", Qwen3ASRConfig, exist_ok=True)
    AutoModel.register(Qwen3ASREncoderConfig, Qwen3ASREncoder, exist_ok=True)
    AutoModel.register(Qwen3ASRConfig, Qwen3ASRModel, exist_ok=True)
    _registered = True


def processor(folder: Path) -> Any:
    """The checkpoint's processor, built from its parts (the feature extractor, the tokenizer, the chat template)."""
    from transformers import AutoTokenizer

    from .feature_extraction_qwen3_asr import Qwen3ASRFeatureExtractor
    from .processing_qwen3_asr import Qwen3ASRProcessor

    template = folder / "chat_template.jinja"
    return Qwen3ASRProcessor(
        Qwen3ASRFeatureExtractor.from_pretrained(str(folder)),
        AutoTokenizer.from_pretrained(str(folder)),
        chat_template=template.read_text(encoding="utf-8") if template.is_file() else None,
    )


def models() -> tuple[Any, Any]:
    """``(ASR model class, forced-aligner model class)``, after ``register()``."""
    register()
    from .modeling_qwen3_asr import Qwen3ASRForConditionalGeneration, Qwen3ASRForTokenClassification

    return Qwen3ASRForConditionalGeneration, Qwen3ASRForTokenClassification


__all__ = ["models", "processor", "register"]
