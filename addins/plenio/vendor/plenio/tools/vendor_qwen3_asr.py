"""Vendor Qwen3-ASR's inference code from transformers >= 5.13 into ``plenio/third_party/qwen3_asr``.

Qwen3-ASR and Qwen3-ForcedAligner (the ``-hf`` checkpoints) are native in transformers from 5.13 on; ComfyUI
ships an older 5.x. This tool copies the model's four modules of an installed transformers (Apache-2.0) and
makes them run on the host's version without touching it:

- relative imports become absolute (``from ...x import`` -> ``from transformers.x import``);
- the few helpers the older transformers lacks are copied unchanged into ``_compat.py``;
- three small patches at the end of a module, each saying why (embeddings lookup, the audio features after the
  prefill, the multimodal processor call).

``NOTICE.md`` records the version, the SHA-256 of every upstream and vendored file and these changes. Re-run it
after choosing another transformers version, then run the tests (``tests/unit/test_qwen3_asr_vendor.py``):

    <python> tools/vendor_qwen3_asr.py --source <site-packages>/transformers
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import re
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
TARGET = PROJECT / "plenio" / "third_party" / "qwen3_asr"
FILES = (
    "configuration_qwen3_asr.py",
    "feature_extraction_qwen3_asr.py",
    "modeling_qwen3_asr.py",
    "processing_qwen3_asr.py",
)
MISSING = {
    "get_max_seqlen": "utils.generic",
    "prepare_prompt_input": "processing_utils",
    "make_audio_chat_template_content": "audio_utils",
    "make_list_of_audio_chat_template": "audio_utils",
    "prepare_language_inputs": "audio_utils",
    "resolve_language": "audio_utils",
    "is_nagisa_available": "utils.import_utils",
    "is_soynlp_available": "utils.import_utils",
    "GenericForTokenClassification": "modeling_layers",
}
"""Names transformers 5.5 lacks (or has in an older form), and the 5.17 module they are copied from."""

COMPAT_HEADER = '''"""Helpers of transformers {version} that older 5.x releases lack, copied unchanged (Apache-2.0).

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

'''

PATCHES = {
    "modeling_qwen3_asr.py": """


# --- Plenio patch 1: transformers before 5.13 does not find the language model's embeddings by itself --------


def _get_input_embeddings(self):
    return self.language_model.get_input_embeddings()


def _set_input_embeddings(self, value):
    self.language_model.set_input_embeddings(value)


Qwen3ASRModel.get_input_embeddings = _get_input_embeddings
Qwen3ASRModel.set_input_embeddings = _set_input_embeddings


# --- Plenio patch 2: transformers before 5.13 passes the audio features at every decoding step; 5.17 only at
# the prefill (MULTIMODAL_INPUTS_TO_DROP_OUTSIDE_PREFILL) - drop them once the cache holds the prompt


def _prepare_inputs_for_generation(self, *args, **kwargs):
    inputs = GenerationMixin.prepare_inputs_for_generation(self, *args, **kwargs)
    cache = inputs.get("past_key_values")
    if cache is not None and kwargs.get("use_cache", True) and cache.get_seq_length() > 0:
        inputs.pop("input_features", None)
        inputs.pop("input_features_mask", None)
    return inputs


Qwen3ASRForConditionalGeneration.prepare_inputs_for_generation = _prepare_inputs_for_generation
""",
    "processing_qwen3_asr.py": """


# --- Plenio patch 3: transformers before 5.13 has no multimodal ProcessorMixin.__call__ (text whose audio
# placeholders ``_process_audio`` expands); this is that path of 5.17's ProcessorMixin.__call__, text and audio only


def _multimodal_call(self, audio=None, text=None, **kwargs):
    merged = self._merge_kwargs(
        Qwen3ASRProcessorKwargs, tokenizer_init_kwargs=self.tokenizer.init_kwargs, **kwargs
    )
    if isinstance(text, str):
        text = [text]
    text = list(text)
    audio = make_list_of_audio(audio)
    processed_audio, replacements = self._process_audio(audio, **merged["audio_kwargs"])
    queue = iter(replacements)
    expanded = []
    for item in text:
        pieces = item.split(self.audio_token)
        joined = pieces[0]
        for piece in pieces[1:]:
            joined += next(queue) + piece
        expanded.append(joined)
    text_kwargs = dict(merged["text_kwargs"])
    text_kwargs.pop("return_mm_token_type_ids", None)
    text_inputs = self.tokenizer(expanded, **text_kwargs)
    data = {**text_inputs, **processed_audio}
    data = {k: v for k, v in data.items() if k not in self.unused_input_names}
    return BatchFeature(data, tensor_type=merged["text_kwargs"].get("return_tensors") or "pt")
""",
}
REPLACEMENTS = {
    "processing_qwen3_asr.py": [
        (
            "model_inputs = super().__call__(audio=audio, text=text, **kwargs)",
            "model_inputs = _multimodal_call(self, audio=audio, text=text, **kwargs)  # Plenio patch 3",
        ),
        (
            "from transformers.audio_utils import AudioInput",
            "from transformers.audio_utils import AudioInput, make_list_of_audio",
        ),
    ],
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def definition(source: Path, name: str) -> str:
    text = source.read_text(encoding="utf-8")
    for node in ast.parse(text).body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name == name:
            lines = text.splitlines()
            start = (node.decorator_list[0].lineno if node.decorator_list else node.lineno) - 1
            return "\n".join(lines[start : node.end_lineno]) + "\n"
    raise KeyError(f"{name} not found in {source}")


def absolute_imports(text: str) -> tuple[str, list[str]]:
    changes: list[str] = []

    def fix(match: re.Match[str]) -> str:
        dots, module, names = match.group(1), match.group(2), match.group(3)
        if dots == ".":
            return match.group(0)
        base = "transformers" if dots == "..." else "transformers.models"
        new = f"from {f'{base}.{module}' if module else base} import {names}"
        changes.append(f"`{match.group(0).splitlines()[0]}` -> `{new.splitlines()[0]}`")
        return new

    text = re.sub(r"^from (\.{1,3})([\w.]*) import (\([^)]*\)|[^\n]*)", fix, text, flags=re.M)
    for name, module in MISSING.items():
        pattern = re.compile(
            rf"^from transformers\.(?:models\.)?{re.escape(module)} import (\([^)]*\)|[^\n]*)", re.M
        )

        def split(match: re.Match[str], name: str = name) -> str:
            names = [n.strip() for n in match.group(1).strip("()").replace("\n", " ").split(",") if n.strip()]
            if name not in names:
                return match.group(0)
            kept = [n for n in names if n != name]
            module_path = match.group(0).split(" import ")[0]
            lines = [f"{module_path} import {', '.join(kept)}"] if kept else []
            lines.append(f"from ._compat import {name}")
            changes.append(f"`{name}` from `._compat`")
            return "\n".join(lines)

        text = pattern.sub(split, text)
    return text, changes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", required=True, type=Path, help="an installed transformers package folder")
    args = parser.parse_args()
    source: Path = args.source
    version = re.search(r'__version__ = "([^"]+)"', (source / "__init__.py").read_text(encoding="utf-8"))
    if version is None:
        raise SystemExit(f"no transformers in {source}")
    licence = next(source.parent.glob("transformers-*.dist-info/licenses/LICENSE"), None)
    TARGET.mkdir(parents=True, exist_ok=True)
    rows: list[tuple[str, str, str, str]] = []
    notes: list[str] = []
    for name in FILES:
        upstream = source / "models" / "qwen3_asr" / name
        text, changes = absolute_imports(upstream.read_text(encoding="utf-8"))
        for old, new in REPLACEMENTS.get(name, []):
            if old not in text:
                raise SystemExit(f"{name}: '{old}' not found - the upstream code changed, review the patches")
            text = text.replace(old, new)
            changes.append(f"`{old}` -> `{new}`")
        text += PATCHES.get(name, "")
        (TARGET / name).write_bytes(text.encode("utf-8"))
        rows.append((name, f"transformers/models/qwen3_asr/{name}", sha256(upstream), sha256(TARGET / name)))
        notes += [f"- `{name}`: {change}" for change in dict.fromkeys(changes)]
        if name in PATCHES:
            notes.append(f"- `{name}`: a Plenio patch appended at the end (see its comment)")
    compat = [COMPAT_HEADER.format(version=version.group(1))]
    for name, module in MISSING.items():
        if name.startswith("is_") and name.endswith("_available"):
            package = name[3:-10]
            compat.append(
                f"def {name}() -> bool:\n    return importlib.util.find_spec({package!r}) is not None\n"
            )
        else:
            compat.append(definition(source / (module.replace(".", "/") + ".py"), name))
    (TARGET / "_compat.py").write_bytes("\n\n".join(compat).encode("utf-8"))
    rows.append(
        (
            "_compat.py",
            "copies from `transformers/{" + ",".join(sorted(set(MISSING.values()))) + "}`",
            "-",
            sha256(TARGET / "_compat.py"),
        )
    )
    if licence is not None:
        (TARGET / "LICENSE").write_bytes(licence.read_bytes())
        rows.append(
            ("LICENSE", "transformers' LICENSE (Apache-2.0)", sha256(licence), sha256(TARGET / "LICENSE"))
        )
    table = "\n".join(
        f"| `{a}` | {b if b.startswith('copies') or b.startswith('transformers') else f'`{b}`'} | `{c}` | `{d}` |"
        for a, b, c, d in rows
    )
    notice = f"""# Qwen3-ASR (vendored inference code)

Upstream: the `qwen3_asr` model of [huggingface/transformers](https://github.com/huggingface/transformers)
**{version.group(1)}** (Apache-2.0, see `LICENSE`), written by `tools/vendor_qwen3_asr.py`; do not edit by hand.
Weights: [Qwen/Qwen3-ASR-1.7B-hf](https://huggingface.co/Qwen/Qwen3-ASR-1.7B-hf) and
[Qwen/Qwen3-ForcedAligner-0.6B-hf](https://huggingface.co/Qwen/Qwen3-ForcedAligner-0.6B-hf) (Apache-2.0).

Vendored for Plenio's lyrics ASR (Transcribe Lyrics, the lyrics subtitles of Export Release): transformers
supports the model natively only from 5.13 on, ComfyUI ships an older 5.x, and Plenio installs no packages.
The code runs only in the ASR worker process (`plenio.workers.asr`), never in ComfyUI's process.

## Files

| Path | Upstream | SHA-256 upstream | SHA-256 vendored |
|---|---|---|---|
{table}

## Deliberate changes

{chr(10).join(notes)}
- `_compat.py`: {", ".join(f"`{n}`" for n in MISSING)} copied unchanged from transformers {version.group(1)}
  (`is_*_available` as a plain module check)
- `__init__.py` is Plenio's: it registers the model with transformers' auto classes in the worker and builds the
  processor (the older `ProcessorMixin.from_pretrained` cannot resolve the vendored classes by name)
"""
    (TARGET / "NOTICE.md").write_bytes(notice.encode("utf-8"))
    print(f"vendored transformers {version.group(1)} into {TARGET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
