"""Helpers of transformers 5.17.0 that older 5.x releases lack, copied unchanged (Apache-2.0).

Written by ``tools/vendor_qwen3_asr.py``; do not edit.
"""

from __future__ import annotations

import importlib.util
import re

import numpy as np
import torch
from torch import nn
from transformers.audio_utils import AudioInput, make_list_of_audio
from transformers.cache_utils import Cache
from transformers.configuration_utils import PreTrainedConfig
from transformers.modeling_outputs import BaseModelOutputWithPast, TokenClassifierOutput
from transformers.models.auto import AutoModel
from transformers.processing_utils import Unpack
from transformers.utils import TransformersKwargs, auto_docstring, can_return_tuple
from transformers.utils.generic import is_flash_attention_requested



def get_max_seqlen(
    cu_seqlens: torch.Tensor,
    config: PreTrainedConfig,
    kwargs: dict | None = None,
    kwarg_name: str = "max_seqlen",
) -> int | None:
    """Get the maximum packed sequence length, or pop it from `kwargs` if precomputed.

    Args:
        cu_seqlens: `(num_sequences + 1,)` cumulative sequence boundaries.
        config: model configuration used to determine the attention implementation.
        kwargs: optional caller kwargs containing a precomputed maximum sequence length.
        kwarg_name: key used to pop the precomputed value from `kwargs`.

    Returns:
        Maximum packed sequence length as a Python integer, or `None` when Flash Attention is not requested
        and no precomputed value is provided.
    """
    if kwargs is not None and (max_seqlen := kwargs.pop(kwarg_name, None)) is not None:
        return max_seqlen
    if not is_flash_attention_requested(config):
        return None
    return (cu_seqlens[1:] - cu_seqlens[:-1]).max().item()


def prepare_prompt_input(
    inputs: str | list[str] | None,
    batch_size: int,
    input_name: str = "inputs",
) -> list[str | None]:
    """
    Normalize a string, list of strings, or ``None`` into a list of length ``batch_size``.

    Args:
        inputs (`str`, `list[str]`, or `None`):
            The input to normalize. A single string is broadcast to all batch items; a list must
            match ``batch_size`` exactly; ``None`` produces a list of ``None`` values.
        batch_size (`int`):
            Expected length of the output list.
        input_name (`str`, *optional*, defaults to `"inputs"`):
            Name used in error messages to identify the argument.

    Returns:
        `list[str | None]`: A list of length ``batch_size``.
    """
    if inputs is None:
        return [None] * batch_size
    if isinstance(inputs, str):
        return [inputs] * batch_size
    if isinstance(inputs, (list, tuple)):
        if len(inputs) != batch_size:
            raise ValueError(
                f"Received {len(inputs)} {input_name} for {batch_size} audio sample(s); counts must match."
            )
        return list(inputs)
    raise TypeError(f"`{input_name}` must be a string, a sequence of strings, or `None`.")


def make_audio_chat_template_content(audio_item) -> dict:
    """
    Build a chat-template content dict for a single audio item.

    Args:
        audio_item (`str` or array-like):
            A single audio item. Strings are treated as local paths or URLs; other values (numpy/torch arrays) are
            forwarded directly.

    Returns:
        `dict`: A chat-template content dict, e.g. `{"type": "audio", "path": ...}` for strings or
        `{"type": "audio", "audio": ...}` otherwise.
    """
    if isinstance(audio_item, str):
        return {"type": "audio", "path": audio_item}
    return {"type": "audio", "audio": audio_item}


def make_list_of_audio_chat_template(
    audio: list[AudioInput] | AudioInput | str | list[str],
) -> AudioInput:
    """
    Ensure that the output is a list of audio. Unlike `make_list_of_audio`, this function also accepts a URL string or
    local path, as accepted by chat templates.

    Args:
        audio (`Union[list[AudioInput], AudioInput]`):
            The input audio. Can be a URL string, local path, numpy/torch array,  or a list of these.
    Returns:
        list: A list of audio.
    """

    # Handle string inputs
    if isinstance(audio, str):
        return [audio]
    if isinstance(audio, (list, tuple)) and audio and all(isinstance(a, str) for a in audio):
        return list(audio)

    # Handle numpy/torch array inputs
    return make_list_of_audio(audio)


def prepare_language_inputs(
    language: str | list[str] | None,
    batch_size: int,
    code_to_name: dict[str, str],
    allow_broadcast: bool = False,
    return_code: bool = True,
) -> list[str | None]:
    """
    Broadcast and validate a language argument to match ``batch_size``.

    Accepts language codes (e.g. ``"zh"``, ``"en"``) or full names (e.g. ``"Chinese"``, ``"English"``). Each value is
    resolved to its canonical form via [`resolve_language`].

    Args:
        language (`str`, `list[str]`, or `None`):
            The language hint(s). A single value is broadcast to the whole batch; a list must match ``batch_size``
            (unless ``allow_broadcast`` is set). ``None`` disables language hints for the whole batch.
        batch_size (`int`):
            The number of samples in the batch.
        code_to_name (`dict[str, str]`):
            Mapping from language code to full language name for the model's supported languages.
        allow_broadcast (`bool`, *optional*, defaults to `False`):
            Whether a single-element list may be broadcast to the whole batch.
        return_code (`bool`, *optional*, defaults to `True`):
            Whether to return canonical language ``code``s. If ``False``, returns full language ``name``s.

    Returns:
        `list[str | None]`: The resolved language for each sample.
    """
    if language is None:
        return [None] * batch_size
    if isinstance(language, str):
        return [resolve_language(language, code_to_name, return_code)] * batch_size
    if isinstance(language, (list, tuple)):
        if allow_broadcast and len(language) == 1 and batch_size > 1:
            return [resolve_language(language[0], code_to_name, return_code)] * batch_size
        if len(language) != batch_size:
            raise ValueError(f"Got {len(language)} language(s) for {batch_size} sample(s); counts must match.")
        return [resolve_language(lang, code_to_name, return_code) for lang in language]
    raise TypeError("`language` must be a string, a list of strings, or `None`.")


def resolve_language(language: str | None, code_to_name: dict[str, str], return_code: bool = True) -> str | None:
    """
    Map a language code or name to its canonical form, with validation.

    Accepts either a language code (e.g. ``"zh"``, ``"en"``) or a full name (e.g. ``"Chinese"``, ``"English"``) and
    returns the canonical code or name depending on ``return_code``. ``None`` passes through unchanged (auto-detect).

    Args:
        language (`str` or `None`):
            The language code or full name to resolve. ``None`` is returned unchanged.
        code_to_name (`dict[str, str]`):
            Mapping from language code to full language name for the model's supported languages.
        return_code (`bool`, *optional*, defaults to `True`):
            Whether to return the canonical language ``code``. If ``False``, returns the full language ``name``.

    Returns:
        `str` or `None`: The canonical language code or name, or ``None`` if ``language`` is ``None``.

    Raises:
        `ValueError`: If the language is not recognized.
    """
    if language is None:
        return None

    language_lower = language.lower()
    # Try code lookup first, then full-name lookup (both case-insensitive)
    for code, name in code_to_name.items():
        if language_lower == code.lower() or language_lower == name.lower():
            return code if return_code else name

    raise ValueError(
        f"Unsupported language: {language!r}. Use a language code "
        f"(e.g. 'en', 'zh') or full name (e.g. 'English', 'Chinese'). "
        f"Supported codes: {sorted(code_to_name.keys())}. "
        f"Supported names: {sorted(set(code_to_name.values()))}."
    )


def is_nagisa_available() -> bool:
    return importlib.util.find_spec('nagisa') is not None


def is_soynlp_available() -> bool:
    return importlib.util.find_spec('soynlp') is not None


@auto_docstring
class GenericForTokenClassification:
    base_model_prefix = "model"

    def __init__(self, config):
        super().__init__(config)
        self.num_labels = config.num_labels
        # Similar to `self.model = AutoModel.from_config(config)` but allows to change the base model name if needed in the child class
        setattr(self, self.base_model_prefix, AutoModel.from_config(config))
        if getattr(config, "classifier_dropout", None) is not None:
            classifier_dropout = config.classifier_dropout
        elif getattr(config, "hidden_dropout", None) is not None:
            classifier_dropout = config.hidden_dropout
        else:
            classifier_dropout = 0.1
        self.dropout = nn.Dropout(classifier_dropout)
        self.score = nn.Linear(
            config.get_text_config().hidden_size,
            config.num_labels,
            bias=getattr(config, "token_classification_bias", True),
        )

        # Initialize weights and apply final processing
        self.post_init()

    @can_return_tuple
    @auto_docstring
    def forward(
        self,
        input_ids: torch.LongTensor | None = None,
        attention_mask: torch.Tensor | None = None,
        position_ids: torch.LongTensor | None = None,
        past_key_values: Cache | None = None,
        inputs_embeds: torch.FloatTensor | None = None,
        labels: torch.LongTensor | None = None,
        use_cache: bool | None = None,
        **kwargs: Unpack[TransformersKwargs],
    ) -> TokenClassifierOutput:
        outputs: BaseModelOutputWithPast = getattr(self, self.base_model_prefix)(
            input_ids,
            attention_mask=attention_mask,
            position_ids=position_ids,
            past_key_values=past_key_values,
            inputs_embeds=inputs_embeds,
            use_cache=use_cache,
            **kwargs,
        )
        sequence_output = outputs.last_hidden_state
        sequence_output = self.dropout(sequence_output)
        logits = self.score(sequence_output)

        loss = None
        if labels is not None:
            loss = self.loss_function(logits, labels, self.config)

        return TokenClassifierOutput(
            loss=loss,
            logits=logits,
            hidden_states=outputs.hidden_states,
            attentions=outputs.attentions,
        )
