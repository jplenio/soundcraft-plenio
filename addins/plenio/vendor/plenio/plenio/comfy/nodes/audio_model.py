"""Load Audio Model: a super-resolution or separation model for HQ 2, Refine and Separate Stems (experimental)."""

from __future__ import annotations

from typing import Any

from comfy_api.latest import io

from ...core.errors import PlenioModelError
from ...core.models import AUDIO_MODEL_FOLDERS
from .. import audio_models, host
from ..types import AudioModelType


class PlenioAudioModelLoader(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="PlenioAudioModelLoader",
            display_name="Load Audio Model",
            category="Plenio/Audio",
            is_experimental=True,
            description=(
                "Loads a super-resolution model (for HQ 2 · Regenerate Highs and Refine) from models/audio_sr "
                "or a separation model (for Separate Stems) from models/audio_separation. A file of another "
                "architecture is refused with a message; Refine's 'resample only' engine needs no model at all."
            ),
            inputs=[
                io.DynamicCombo.Input(
                    "kind",
                    options=[
                        io.DynamicCombo.Option(
                            kind,
                            [
                                io.Combo.Input(
                                    "model",
                                    options=host.model_files(folder),
                                    tooltip=f"A model file in models/{folder}.",
                                )
                            ],
                        )
                        for kind, folder in AUDIO_MODEL_FOLDERS.items()
                    ],
                    tooltip=(
                        "super-resolution: for HQ 2 · Regenerate Highs and Refine (48 kHz); separation: for "
                        "Separate Stems."
                    ),
                )
            ],
            outputs=[
                AudioModelType.Output(
                    display_name="model",
                    tooltip="The loaded model, for HQ 2 and Refine (super-resolution) or Separate Stems.",
                )
            ],
        )

    @classmethod
    def validate_inputs(cls, **kwargs: Any) -> bool | str:
        # ComfyUI then leaves the file list to this node: a model file that is not installed is no error
        # until the model is needed - HQ 2 with HQ mastering off never asks for it (lazy), and execute says
        # where the file goes.
        kind = kwargs.get("kind")
        name = str(kind.get("kind", "")) if isinstance(kind, dict) else str(kind or "")
        if name and name not in AUDIO_MODEL_FOLDERS:
            return f"Unknown model kind {name!r}; use one of {list(AUDIO_MODEL_FOLDERS)}."
        return True

    @classmethod
    def execute(cls, kind: dict[str, Any]) -> io.NodeOutput:
        name = str(kind.get("kind", ""))
        file = str(kind.get("model", "") or "")
        folder = AUDIO_MODEL_FOLDERS.get(name, "")
        path = host.locate_model(folder, file) if file else None
        if path is None:
            raise PlenioModelError(
                f"The {name} model {file or '(none)'} is not in models/{folder}.",
                hint="Download it with the missing-model dialog, or put it into that folder and refresh.",
            )
        return io.NodeOutput(audio_models.load(name, file, path))
