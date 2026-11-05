"""LoRAs for YuE2 (GitHub issue 2026-10-28: "please add a LoRA node"), on ComfyUI's own LoRA patching.

YuE2 has two halves in ComfyUI: its planner - the language model that writes the score and the music's tokens -
sits in the CLIP slot, the acoustic model that renders them in the MODEL slot. A LoRA trained on the planner
("AR") shapes the plan (structure, melody, genre), one trained on the acoustic model ("NAR") the sound. Which
half a file is for is read from its weights, so one strength per LoRA is enough.

Two layouts are read:

* ComfyUI's own (``text_encoders.model.layers.N.self_attn.qkv_proj.lora_up.weight`` ...): fused ``qkv_proj``
  and ``gate_up_proj``, as ComfyUI's YuE2 has them - what ComfyUI's LoraLoader reads too.
* the original one of m-a-p's YuE2 code (``model.layers.N.self_attn.q_proj.lora_A`` ..., the acoustic half as
  ``nar_self_attn`` / ``nar_mlp``): separate q, k, v and gate, up projections. They are joined here exactly -
  the fused projection's LoRA is the block-diagonal one of the separate LoRAs (rank 3r / 2r), whose product is
  the separate deltas stacked - so they work without converting the file first.

Nothing a LoRA brings can break the run: a file that cannot be read, a weight of another model or of another
shape, a value that is not finite - each is left out and said; the rest applies. With every slot empty the
model and the CLIP pass through untouched: the run is the one it was without the node.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

LOG = logging.getLogger(__name__)

NONE = "none"
SLOTS = 4
STRENGTH_RANGE = (-4.0, 4.0)

# the projections ComfyUI's YuE2 fuses (comfy/ldm/yue2/model.py: hidden 2048, 16 heads and 8 key-value heads of
# 128, intermediate 6144), in the order of the fused weight's rows
FUSED: dict[str, tuple[tuple[str, int], ...]] = {
    "self_attn.qkv_proj": (("q", 2048), ("k", 1024), ("v", 1024)),
    "mlp.gate_up_proj": (("gate", 6144), ("up", 6144)),
}
_PART_OF = {part: (fused, index) for fused, parts in FUSED.items() for index, (part, _) in enumerate(parts)}
_ORIGINAL = re.compile(
    r"^(?P<prefix>.*?)layers\.(?P<layer>\d+)\.(?P<nar>nar_)?(?P<block>self_attn|mlp)\."
    r"(?P<part>q|k|v|o|gate|up|down)_proj\.(?P<kind>lora_A|lora_B|lora_down|lora_up|alpha)(?:\.weight)?$"
)
_LATENT = re.compile(
    r"^(?P<prefix>.*?)(?P<name>vae2llm|llm2vae)\.(?P<kind>lora_A|lora_B|lora_down|lora_up|alpha)(?:\.weight)?$"
)
DOWN, UP = ("lora_A", "lora_down"), ("lora_B", "lora_up")


@dataclass
class Applied:
    """What one LoRA did: how many of its weights went where, what was left out and why."""

    name: str
    strength: float
    layout: str = ""
    plan: int = 0
    sound: int = 0
    weights: int = 0
    left_out: list[str] = field(default_factory=list)
    error: str = ""

    def line(self) -> str:
        if self.error:
            return f"{self.name}: left out - {self.error}"
        halves = [f"{n} for the {where}" for n, where in ((self.plan, "plan"), (self.sound, "sound")) if n]
        text = f"{self.name} at {self.strength:g}: " + (", ".join(halves) or "no weight of this model")
        if self.layout == "original":
            text += " (original YuE2 layout, joined for ComfyUI)"
        if self.left_out:
            text += f"; left out: {'; '.join(self.left_out)}"
        return text

    @property
    def used(self) -> bool:
        return not self.error and (self.plan + self.sound) > 0


def _first_line(error: BaseException) -> str:
    """An error's first line (safetensors adds the file's whole path and advice below it)."""
    return (str(error).strip().splitlines() or [""])[0]


def _scale_from_config(path: Path) -> float | None:
    """``alpha / rank`` of the original layout's ``adapter_config.json`` beside the file (or ``<name>.json``)."""
    for candidate in (path.with_suffix(".json"), path.parent / "adapter_config.json"):
        try:
            config = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        rank, alpha = config.get("rank") or config.get("r"), config.get("alpha") or config.get("lora_alpha")
        if isinstance(rank, (int, float)) and isinstance(alpha, (int, float)) and rank > 0:
            return float(alpha) / float(rank)
    return None


def is_original(state: Mapping[str, Any]) -> bool:
    """The original layout: separate q, k, v or gate, up projections (ComfyUI's YuE2 has them fused)."""
    for key in state:
        match = _ORIGINAL.match(key)
        if match and match["part"] in _PART_OF:
            return True
        if match and (match["nar"] or match["kind"] in ("lora_A", "lora_B")):
            return True
        if _LATENT.match(key) and not key.startswith(("diffusion_model.", "text_encoders.")):
            return True
    return False


def join_original(state: Mapping[str, Any], scale: float = 1.0) -> tuple[dict[str, Any], list[str]]:
    """The original layout in ComfyUI's: each module's ``alpha / rank`` (else ``scale``) folded into its up
    weights, q/k/v and gate/up joined block-diagonally into the fused projection. Returns the new state and what
    could not be joined."""
    import torch

    modules: dict[str, dict[str, Any]] = {}
    problems: list[str] = []
    for key, tensor in state.items():
        match = _ORIGINAL.match(key)
        if match:
            # the acoustic half: nar_self_attn / nar_mlp, ComfyUI's diffusion_model, or a prefix that says so
            nar = (
                bool(match["nar"]) or "diffusion_model" in match["prefix"] or "nar" in match["prefix"].lower()
            )
            branch = "diffusion_model" if nar else "text_encoders"
            module = f"{branch}.model.layers.{int(match['layer'])}.{match['block']}.{match['part']}"
            kind = match["kind"]
        else:
            latent = _LATENT.match(key)
            if latent is None:
                continue
            module = f"diffusion_model.{latent['name']}"
            kind = latent["kind"]
        slot = "down" if kind in DOWN else "up" if kind in UP else "alpha"
        modules.setdefault(module, {})[slot] = tensor
    # each module's delta as (down, up) with its own scale in the up weights
    pairs: dict[str, tuple[Any, Any]] = {}
    for module, parts in modules.items():
        down, up = parts.get("down"), parts.get("up")
        if down is None or up is None or down.dim() != 2 or up.dim() != 2 or up.shape[1] != down.shape[0]:
            problems.append(f"{module}: no matching pair of weights")
            continue
        alpha = parts.get("alpha")
        own = float(alpha.item()) / down.shape[0] if alpha is not None and alpha.numel() == 1 else scale
        pairs[module] = (down.float(), up.float() * own)
    out: dict[str, Any] = {}
    grouped: dict[str, dict[str, tuple[Any, Any]]] = {}
    for module, pair in pairs.items():
        stem, part = module.rsplit(".", 1)
        if part in ("vae2llm", "llm2vae"):
            name = module
        else:
            block = stem.rsplit(".", 1)[1]  # self_attn | mlp
            if part in _PART_OF and _PART_OF[part][0].startswith(block + "."):
                fused = f"{stem.rsplit('.', 1)[0]}.{_PART_OF[part][0]}"
                grouped.setdefault(fused, {})[part] = pair
                continue
            name = f"{stem}.{part}_proj"
        down, up = pair
        out[f"{name}.lora_down.weight"] = down
        out[f"{name}.lora_up.weight"] = up
        out[f"{name}.alpha"] = torch.tensor(float(down.shape[0]))  # the scale is in the up weights already
    for fused, parts in grouped.items():
        layout = FUSED[".".join(fused.rsplit(".", 2)[-2:])]
        sizes = dict(layout)
        wrong = [p for p, (_, up) in parts.items() if up.shape[0] != sizes[p]]
        if wrong:
            problems.append(f"{fused}: {', '.join(wrong)} of another size than YuE2's")
            continue
        downs = [parts[p][0] for p, _ in layout if p in parts]
        rank = sum(d.shape[0] for d in downs)
        up = torch.zeros(sum(size for _, size in layout), rank)
        row = column = 0
        for part, size in layout:
            if part in parts:
                d, u = parts[part]
                up[row : row + size, column : column + d.shape[0]] = u
                column += d.shape[0]
            row += size
        out[f"{fused}.lora_down.weight"] = torch.cat(downs, dim=0)
        out[f"{fused}.lora_up.weight"] = up
        out[f"{fused}.alpha"] = torch.tensor(float(rank))
    return out, problems


def _weights_of(patch: Any) -> tuple[Any, Any] | None:
    """A LoRA patch's up and down weights (ComfyUI's ``LoRAAdapter``, or the older ``("lora", (...))``)."""
    weights = getattr(patch, "weights", None)
    if weights is None and isinstance(patch, tuple) and len(patch) == 2 and patch[0] == "lora":
        weights = patch[1]
    if isinstance(weights, tuple) and len(weights) >= 2:
        return weights[0], weights[1]
    return None


def _shape_of(state: Mapping[str, Any], key: Any) -> tuple[int, ...] | None:
    target = key[0] if isinstance(key, tuple) else key
    tensor = state.get(target)
    return tuple(tensor.shape) if tensor is not None else None


def apply(model: Any, clip: Any, chosen: list[tuple[str, float]]) -> tuple[Any, Any, list[Applied]]:
    """Apply the LoRAs ``chosen`` (file name in ``models/loras``, strength) to YuE2's model and CLIP. Returns
    the patched model and CLIP (the same objects when nothing applied) and what each LoRA did."""
    import torch

    from . import host

    results: list[Applied] = []
    key_map = host.lora_key_map(model, clip)
    model_state = model.model.state_dict() if model is not None else {}
    clip_state = clip.cond_stage_model.state_dict() if clip is not None else {}
    new_model, new_clip = model, clip
    for name, strength in chosen:
        result = Applied(name, strength)
        results.append(result)
        path = host.model_file("loras", name)
        if path is None:
            result.error = "not found in models/loras"
            continue
        try:
            state = host.read_weights(path)
        except Exception as error:  # noqa: BLE001 - a broken file is left out, the run goes on
            result.error = f"cannot be read ({type(error).__name__}: {_first_line(error)})"
            continue
        result.layout = "comfyui"
        if is_original(state):
            try:
                state, problems = join_original(state, _scale_from_config(path) or 1.0)
            except Exception as error:  # noqa: BLE001
                result.error = (
                    f"its original layout cannot be joined ({type(error).__name__}: {_first_line(error)})"
                )
                continue
            result.layout = "original"
            result.left_out.extend(problems)
        try:
            patches = host.lora_patches(state, key_map)
        except Exception as error:  # noqa: BLE001
            result.error = f"cannot be loaded ({type(error).__name__}: {_first_line(error)})"
            continue
        for_model: dict[Any, Any] = {}
        for_clip: dict[Any, Any] = {}
        odd = unfinite = 0
        for key, patch in patches.items():
            target = key[0] if isinstance(key, tuple) else key
            in_model = target in model_state
            shape = _shape_of(model_state if in_model else clip_state, key)
            if shape is None:
                continue
            weights = _weights_of(patch)
            if weights is not None:
                up, down = weights
                if not (
                    isinstance(key, tuple) or (len(shape) == 2 and (up.shape[0], down.shape[-1]) == shape)
                ):
                    odd += 1
                    continue
                if not (torch.isfinite(up).all() and torch.isfinite(down).all()):
                    unfinite += 1
                    continue
            (for_model if in_model else for_clip)[key] = patch
        if odd:
            result.left_out.append(f"{odd} weight(s) of another shape than this model's")
        if unfinite:
            result.left_out.append(f"{unfinite} weight(s) with values that are not numbers")
        result.weights = len(patches)
        if for_model and new_model is not None:
            if new_model is model:
                new_model = model.clone()
            result.sound = len(set(new_model.add_patches(for_model, strength)))
        if for_clip and new_clip is not None:
            if new_clip is clip:
                new_clip = clip.clone()
            result.plan = len(set(new_clip.add_patches(for_clip, strength)))
        if not result.used:
            result.error = (
                "none of its weights belongs to YuE2 (a LoRA for another model?)"
                if not patches
                else "none of its weights could be applied"
                + (f" ({'; '.join(result.left_out)})" if result.left_out else "")
            )
            result.left_out = []
    return new_model, new_clip, results
