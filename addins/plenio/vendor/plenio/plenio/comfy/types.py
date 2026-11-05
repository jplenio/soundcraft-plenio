"""Custom IO types of Plenio (target-architecture section 5.1)."""

from __future__ import annotations

from typing import Any

from comfy_api.latest import io

Brief = io.Custom("PLENIO_BRIEF")
Engine = io.Custom("PLENIO_ENGINE")
Request = io.Custom("PLENIO_REQUEST")
ReportType = io.Custom("PLENIO_REPORT")
TimelineType = io.Custom("PLENIO_TIMELINE")
PitchType = io.Custom("PLENIO_PITCH")
AudioModelType = io.Custom("PLENIO_AUDIO_MODEL")
"""A loaded super-resolution or separation model (``audio_models.AudioModel``)."""
StemsType = io.Custom("PLENIO_STEMS")
"""Separated stems plus the residual (``core.audio.stems.Stems``)."""


@io.comfytype(io_type="PLENIO_SHEET_STATE")
class SheetState(io.ComfyTypeIO):
    """Socketless widget holding the Song Sheet state as a JSON string.

    The frontend extension registers the widget for this type through
    ``getCustomWidgets``; the value is serialised with the workflow and arrives
    in ``execute`` unchanged (ComfyUI only converts INT/FLOAT/STRING/BOOLEAN).
    """

    Type = str

    class Input(io.WidgetInput):
        def __init__(
            self, id: str, display_name: str | None = None, tooltip: str | None = None, default: str = ""
        ):
            super().__init__(
                id, display_name, False, tooltip, None, default, True, None, None, None, None, None
            )

        def as_dict(self) -> dict[str, Any]:
            return super().as_dict()


@io.comfytype(io_type="PLENIO_FINISH_SWITCH")
class FinishSwitch(io.ComfyTypeIO):
    """Socketless widget of *HQ Mastering & Cover Art*: the HQ mastering switch (a boolean), drawn by the
    frontend extension as a card with an icon - beside it the Cover Art switch, which bypasses the template's
    cover nodes in the page (owner's request 2026-10-23). The value arrives in ``execute`` unchanged."""

    Type = bool

    class Input(io.WidgetInput):
        def __init__(
            self, id: str, display_name: str | None = None, tooltip: str | None = None, default: bool = False
        ):
            super().__init__(
                id, display_name, False, tooltip, None, default, True, None, None, None, None, None
            )

        def as_dict(self) -> dict[str, Any]:
            return super().as_dict()
