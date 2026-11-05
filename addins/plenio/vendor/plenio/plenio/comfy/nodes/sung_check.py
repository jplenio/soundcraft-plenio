"""Check Sung Words, retired (owner's rule 2026-10-24): it corrected misheard words in the lyrics *as sung*
after Export Release, in every template of Plenio 1.2.0. The lyrics as sung now stay as heard; misheard words are corrected
only in a cover's transcribed original lyrics, before the render (*Fix Misheard Words*, ``heard_check``).

The two nodes stay, deprecated and doing nothing, so a workflow saved with the block - a release record's own
workflow, opened again with *Continue a Plenio song* - still runs: Compose asks nothing, Apply hands the record
on unchanged and asks no writer."""

from __future__ import annotations

import json
from typing import Any

from comfy_api.latest import io

from ...core.heard_check import ANSWER_SCHEMA
from ...core.reports import Report, Status
from ..types import ReportType

RECORD_TOOLTIP = "The release record Export Release wrote (its 'record' output)."
RETIRED = (
    "Check Sung Words is retired: the lyrics as sung stay as heard (a cover's original lyrics are checked for "
    "misheard words before the render). Delete the block from this workflow."
)


class PlenioComposeSungCheck(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="PlenioComposeSungCheck",
            display_name="Compose Sung Check (retired)",
            category="Plenio/Lyrics",
            description=RETIRED,
            is_deprecated=True,
            inputs=[
                io.String.Input("record", force_input=True, tooltip=RECORD_TOOLTIP),
                io.String.Input("language", optional=True, default="", tooltip="Not used."),
            ],
            outputs=[
                io.String.Output(display_name="prompt", tooltip="Empty: nothing is asked."),
                io.String.Output(display_name="schema", tooltip="The answer's JSON schema, for Local LLM."),
            ],
        )

    @classmethod
    def execute(cls, record: str, language: str = "") -> io.NodeOutput:
        return io.NodeOutput("", json.dumps(ANSWER_SCHEMA))


class PlenioApplySungCheck(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="PlenioApplySungCheck",
            display_name="Apply Sung Check (retired)",
            category="Plenio/Lyrics",
            description=RETIRED,
            is_deprecated=True,
            inputs=[
                io.String.Input("record", force_input=True, tooltip=RECORD_TOOLTIP),
                io.String.Input("answer", optional=True, lazy=True, force_input=True, tooltip="Never asked."),
                io.String.Input("language", optional=True, default="", tooltip="Not used."),
            ],
            outputs=[
                io.String.Output(display_name="record", tooltip="The release record, unchanged."),
                ReportType.Output(display_name="report", tooltip="That nothing was checked."),
            ],
            is_output_node=True,
        )

    @classmethod
    def check_lazy_status(cls, **_inputs: Any) -> list[str]:
        return []

    @classmethod
    def execute(cls, record: str, answer: str | None = None, language: str = "") -> io.NodeOutput:
        report = Report(
            "sung_check", Status.SKIPPED, "Sung words: not checked - Check Sung Words is retired", (RETIRED,)
        )
        ui = {"plenio_summary": [{"status": Status.SKIPPED.value, "markdown": f"**{RETIRED}**"}]}
        return io.NodeOutput(record, report, ui=ui)
