# Qwen3-ASR (vendored inference code)

Upstream: the `qwen3_asr` model of [huggingface/transformers](https://github.com/huggingface/transformers)
**5.17.0** (Apache-2.0, see `LICENSE`), written by `tools/vendor_qwen3_asr.py`; do not edit by hand.
Weights: [Qwen/Qwen3-ASR-1.7B-hf](https://huggingface.co/Qwen/Qwen3-ASR-1.7B-hf) and
[Qwen/Qwen3-ForcedAligner-0.6B-hf](https://huggingface.co/Qwen/Qwen3-ForcedAligner-0.6B-hf) (Apache-2.0).

Vendored for Plenio's lyrics ASR (Transcribe Lyrics, the lyrics subtitles of Export Release): transformers
supports the model natively only from 5.13 on, ComfyUI ships an older 5.x, and Plenio installs no packages.
The code runs only in the ASR worker process (`plenio.workers.asr`), never in ComfyUI's process.

## Files

| Path | Upstream | SHA-256 upstream | SHA-256 vendored |
|---|---|---|---|
| `configuration_qwen3_asr.py` | transformers/models/qwen3_asr/configuration_qwen3_asr.py | `5474a741f0c75c9c5ed176c57620dacbaf7f48b016dc652d58b5f6df381f0924` | `2c7d5e9a299da6fe8c2b1944eccb051fcc5a54eaece1ef974f23a11d2cbfa9a9` |
| `feature_extraction_qwen3_asr.py` | transformers/models/qwen3_asr/feature_extraction_qwen3_asr.py | `95d23cca9645546b9f6a97885eace5c02a95f5048bf3616e03f00041fd993a74` | `d0f5e7add755668ced244ff02dfd625f5a6233ba51d38b8d10a810b564b8036a` |
| `modeling_qwen3_asr.py` | transformers/models/qwen3_asr/modeling_qwen3_asr.py | `62b77cd1eee32d002f0b5c36a2a507df4b093a8891d5890173737d2e08fe8401` | `6d3aed068828186f299c4febe035d64c22aba815829403c67b7727e89a5ea873` |
| `processing_qwen3_asr.py` | transformers/models/qwen3_asr/processing_qwen3_asr.py | `5ff7ace057ae959fb0cd551775cbbfdad8c003eb731bf0f1f39bfc6452ce86fa` | `dbec3f217d267c079488290992e885f228bc2f5cd42fea528843093cd8fae534` |
| `_compat.py` | copies from `transformers/{audio_utils,modeling_layers,processing_utils,utils.generic,utils.import_utils}` | `-` | `51bb144656f868879a86db8e974de4c95d1496308e95d68d34de1e78a9849cd8` |
| `LICENSE` | transformers' LICENSE (Apache-2.0) | `77fd4710def9ec3c0f6225800e0235f15a425abd4a8b03559127fcd782612049` | `77fd4710def9ec3c0f6225800e0235f15a425abd4a8b03559127fcd782612049` |

## Deliberate changes

- `configuration_qwen3_asr.py`: `from ...configuration_utils import PreTrainedConfig` -> `from transformers.configuration_utils import PreTrainedConfig`
- `configuration_qwen3_asr.py`: `from ...utils import auto_docstring` -> `from transformers.utils import auto_docstring`
- `configuration_qwen3_asr.py`: `from ..auto import CONFIG_MAPPING, AutoConfig` -> `from transformers.models.auto import CONFIG_MAPPING, AutoConfig`
- `feature_extraction_qwen3_asr.py`: `from ...audio_utils import mel_filter_bank` -> `from transformers.audio_utils import mel_filter_bank`
- `feature_extraction_qwen3_asr.py`: `from ...feature_extraction_sequence_utils import SequenceFeatureExtractor` -> `from transformers.feature_extraction_sequence_utils import SequenceFeatureExtractor`
- `feature_extraction_qwen3_asr.py`: `from ...feature_extraction_utils import BatchFeature` -> `from transformers.feature_extraction_utils import BatchFeature`
- `feature_extraction_qwen3_asr.py`: `from ...utils import logging` -> `from transformers.utils import logging`
- `feature_extraction_qwen3_asr.py`: `from ...utils.import_utils import is_torch_available, requires` -> `from transformers.utils.import_utils import is_torch_available, requires`
- `modeling_qwen3_asr.py`: `from ... import initialization as init` -> `from transformers import initialization as init`
- `modeling_qwen3_asr.py`: `from ...activations import ACT2FN` -> `from transformers.activations import ACT2FN`
- `modeling_qwen3_asr.py`: `from ...cache_utils import Cache` -> `from transformers.cache_utils import Cache`
- `modeling_qwen3_asr.py`: `from ...generation import GenerationMixin` -> `from transformers.generation import GenerationMixin`
- `modeling_qwen3_asr.py`: `from ...modeling_layers import GenericForTokenClassification, GradientCheckpointingLayer` -> `from transformers.modeling_layers import GenericForTokenClassification, GradientCheckpointingLayer`
- `modeling_qwen3_asr.py`: `from ...modeling_outputs import BaseModelOutputWithPast, BaseModelOutputWithPooling, ModelOutput` -> `from transformers.modeling_outputs import BaseModelOutputWithPast, BaseModelOutputWithPooling, ModelOutput`
- `modeling_qwen3_asr.py`: `from ...modeling_utils import ALL_ATTENTION_FUNCTIONS, PreTrainedModel` -> `from transformers.modeling_utils import ALL_ATTENTION_FUNCTIONS, PreTrainedModel`
- `modeling_qwen3_asr.py`: `from ...processing_utils import Unpack` -> `from transformers.processing_utils import Unpack`
- `modeling_qwen3_asr.py`: `from ...utils import TransformersKwargs, auto_docstring, can_return_tuple, torch_compilable_check` -> `from transformers.utils import TransformersKwargs, auto_docstring, can_return_tuple, torch_compilable_check`
- `modeling_qwen3_asr.py`: `from ...utils.generic import get_max_seqlen, is_flash_attention_requested` -> `from transformers.utils.generic import get_max_seqlen, is_flash_attention_requested`
- `modeling_qwen3_asr.py`: `from ...utils.output_capturing import capture_outputs` -> `from transformers.utils.output_capturing import capture_outputs`
- `modeling_qwen3_asr.py`: `from ..auto import AutoModel` -> `from transformers.models.auto import AutoModel`
- `modeling_qwen3_asr.py`: `get_max_seqlen` from `._compat`
- `modeling_qwen3_asr.py`: `GenericForTokenClassification` from `._compat`
- `modeling_qwen3_asr.py`: a Plenio patch appended at the end (see its comment)
- `processing_qwen3_asr.py`: `from ...audio_utils import (` -> `from transformers.audio_utils import (`
- `processing_qwen3_asr.py`: `from ...feature_extraction_utils import BatchFeature` -> `from transformers.feature_extraction_utils import BatchFeature`
- `processing_qwen3_asr.py`: `from ...processing_utils import ProcessingKwargs, ProcessorMixin, Unpack, prepare_prompt_input` -> `from transformers.processing_utils import ProcessingKwargs, ProcessorMixin, Unpack, prepare_prompt_input`
- `processing_qwen3_asr.py`: `from ...tokenization_utils_base import TextInput` -> `from transformers.tokenization_utils_base import TextInput`
- `processing_qwen3_asr.py`: `from ...utils import auto_docstring` -> `from transformers.utils import auto_docstring`
- `processing_qwen3_asr.py`: `from ...utils.import_utils import is_nagisa_available, is_soynlp_available` -> `from transformers.utils.import_utils import is_nagisa_available, is_soynlp_available`
- `processing_qwen3_asr.py`: `prepare_prompt_input` from `._compat`
- `processing_qwen3_asr.py`: `make_audio_chat_template_content` from `._compat`
- `processing_qwen3_asr.py`: `make_list_of_audio_chat_template` from `._compat`
- `processing_qwen3_asr.py`: `prepare_language_inputs` from `._compat`
- `processing_qwen3_asr.py`: `is_nagisa_available` from `._compat`
- `processing_qwen3_asr.py`: `is_soynlp_available` from `._compat`
- `processing_qwen3_asr.py`: `model_inputs = super().__call__(audio=audio, text=text, **kwargs)` -> `model_inputs = _multimodal_call(self, audio=audio, text=text, **kwargs)  # Plenio patch 3`
- `processing_qwen3_asr.py`: `from transformers.audio_utils import AudioInput` -> `from transformers.audio_utils import AudioInput, make_list_of_audio`
- `processing_qwen3_asr.py`: a Plenio patch appended at the end (see its comment)
- `_compat.py`: `get_max_seqlen`, `prepare_prompt_input`, `make_audio_chat_template_content`, `make_list_of_audio_chat_template`, `prepare_language_inputs`, `resolve_language`, `is_nagisa_available`, `is_soynlp_available`, `GenericForTokenClassification` copied unchanged from transformers 5.17.0
  (`is_*_available` as a plain module check)
- `__init__.py` is Plenio's: it registers the model with transformers' auto classes in the worker and builds the
  processor (the older `ProcessorMixin.from_pretrained` cannot resolve the vendored classes by name)
