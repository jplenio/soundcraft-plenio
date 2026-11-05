"""YuE2 LoRAs: up to four LoRAs on YuE2's planner (CLIP) and acoustic model (MODEL) - empty, the model as loaded.
The work is ``comfy/loras.py``."""

from __future__ import annotations

from typing import Any

from comfy_api.latest import io

from .. import host
from .. import loras as lora_rules


def _lora_files() -> list[str]:
    try:
        return host.model_files("loras")
    except Exception:  # noqa: BLE001 - the node lists none when ComfyUI's folders cannot be read
        return []


def _slot_inputs() -> list[Any]:
    files = [lora_rules.NONE, *_lora_files()]
    low, high = lora_rules.STRENGTH_RANGE
    inputs: list[Any] = []
    for slot in range(1, lora_rules.SLOTS + 1):
        inputs += [
            io.Combo.Input(
                f"lora_{slot}",
                display_name=f"LoRA {slot}",
                options=files,
                default=lora_rules.NONE,
                optional=True,
                tooltip="A YuE2 LoRA from models/loras - for the plan (AR, the CLIP half) or the sound (NAR, the "
                "MODEL half): the node reads which from its weights. ComfyUI's layout and m-a-p's original one.",
            ),
            io.Float.Input(
                f"strength_{slot}",
                display_name=f"strength {slot}",
                default=1.0,
                min=low,
                max=high,
                step=0.05,
                optional=True,
                tooltip="How strongly it acts: 1 as trained, 0 off. A plan LoRA often sounds best near 0.5, a "
                "sound LoRA near 1 - its card says. Far above its trained strength it sounds broken.",
            ),
        ]
    return inputs


class PlenioLoras(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="PlenioLoras",
            display_name="YuE2 LoRAs",
            category="Plenio/Model",
            description=(
                "Up to four LoRAs for YuE2, each with its strength. A LoRA trained on YuE2's planner shapes the "
                "plan - structure, melody, genre -, one trained on its acoustic model the sound; the node reads "
                "which from the file. A LoRA that does not fit - another model's, a broken file, weights of another "
                "shape - is left out and named in the summary. All slots on none: YuE2 as loaded."
            ),
            inputs=[
                io.Model.Input("model", tooltip="YuE2's MODEL (the acoustic model)."),
                io.Clip.Input("clip", tooltip="YuE2's CLIP (the planner)."),
                *_slot_inputs(),
            ],
            outputs=[
                io.Model.Output(display_name="MODEL", tooltip="YuE2's acoustic model with the sound LoRAs."),
                io.Clip.Output(display_name="CLIP", tooltip="YuE2's planner with the plan LoRAs."),
            ],
        )

    @classmethod
    def execute(cls, model: Any, clip: Any, **slots: Any) -> io.NodeOutput:
        chosen: list[tuple[str, float]] = []
        off: list[str] = []
        for slot in range(1, lora_rules.SLOTS + 1):
            name = str(slots.get(f"lora_{slot}") or lora_rules.NONE)
            if name == lora_rules.NONE:
                continue
            strength = float(slots.get(f"strength_{slot}", 1.0) or 0.0)
            if strength == 0.0:
                off.append(f"{name}: strength 0 - off")
                continue
            chosen.append((name, strength))
        if not chosen:
            markdown = "No LoRA: YuE2 as loaded." + "".join(f"\n- {line}" for line in off)
            return io.NodeOutput(model, clip, ui={"plenio_summary": [{"status": "ok", "markdown": markdown}]})
        new_model, new_clip, results = lora_rules.apply(model, clip, chosen)
        used = [r for r in results if r.used]
        status = "ok" if len(used) == len(results) and not any(r.left_out for r in results) else "warning"
        markdown = "\n".join(
            [
                f"**{len(used)} of {len(results)} LoRA(s) applied**",
                *(f"- {r.line()}" for r in results),
                *(f"- {line}" for line in off),
            ]
        )
        return io.NodeOutput(
            new_model, new_clip, ui={"plenio_summary": [{"status": status, "markdown": markdown}]}
        )
