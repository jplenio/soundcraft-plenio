"""Parse Song Draft: robust parsing and deterministic format enforcement of an LLM answer."""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any

from comfy_api.latest import io

from ...core.diagnostics import Finding, summarize
from ...core.release import release_titles
from ...core.reports import Report, Status
from ...core.writing import draft_findings, parse_draft
from .. import host
from ..types import ReportType, Request

TAKEN_EVERY = 120.0
"""Seconds the titles of the songs in ``output/plenio`` are kept before they are read again."""
_taken: tuple[float, frozenset[str]] = (-TAKEN_EVERY, frozenset())
_picked: deque[str] = deque(maxlen=500)
"""Titles this server picked (a song of a series not exported yet has its title too)."""
_lock = threading.Lock()


def _read_taken() -> None:
    global _taken
    try:
        found = release_titles(host.output_directory() / "plenio")
    except Exception:  # noqa: BLE001 - no output folder (headless tests): nothing is taken
        found = set()
    with _lock:
        _taken = (time.monotonic(), frozenset(found))


def taken_titles() -> set[str]:
    """Titles songs have already: the release records below ``output/plenio`` and the titles picked since
    ComfyUI started - so the writer's proposals that a song has are passed over (owner's request 2026-10-23:
    the same titles came again and again). The folder is read in the background, every two minutes at most
    (2 300 records: 0.1 s, but up to 20 s from a cold disk), so a run never waits for it."""
    global _taken
    with _lock:
        stale = time.monotonic() - _taken[0] > TAKEN_EVERY
        if stale:
            _taken = (time.monotonic(), _taken[1])  # one reading at a time
        known = {*_taken[1], *_picked}
    if stale:
        threading.Thread(target=_read_taken, daemon=True).start()
    return known


class PlenioParseDraft(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="PlenioParseDraft",
            # the summary is re-sent on every run, also when the node is cached (ComfyUI keeps its UI)
            has_intermediate_output=True,
            display_name="Parse Song Draft",
            category="Plenio/Writing",
            description=(
                "Extracts title, style, lyrics and artwork prompt from the writing model's answer and enforces the "
                "format (one-line style, [Tag] sections, tags only for instrumentals). Every change is reported. "
                "Of the titles the writer proposes it picks one at random - none a song in output/plenio has "
                "already, while others are left."
            ),
            inputs=[
                io.String.Input(
                    "text",
                    force_input=True,
                    tooltip="The writing model's answer (Generate Text or Local LLM).",
                ),
                Request.Input(
                    "request",
                    tooltip="From Compose Writing Prompt: what was asked, so the answer is checked against it.",
                ),
            ],
            outputs=[
                io.String.Output(display_name="title", tooltip="Song title draft."),
                io.String.Output(display_name="style", tooltip="Style draft."),
                io.String.Output(display_name="lyrics", tooltip="Lyrics draft."),
                io.String.Output(display_name="artwork_prompt", tooltip="Cover image prompt draft."),
                ReportType.Output(display_name="report", tooltip="What was parsed and enforced."),
            ],
        )

    @classmethod
    def execute(cls, text: str, request: Any) -> io.NodeOutput:
        draft = parse_draft(text, request, taken_titles())
        if not request.fixed_title:
            with _lock:
                _picked.append(draft.title)
        findings = draft_findings(draft, request)
        if any(f["severity"] == "error" for f in findings):
            status = Status.ERROR
        elif draft.enforcements or any(f["severity"] != "info" for f in findings):
            status = Status.WARNING
        else:
            status = Status.OK
        summary = f"Draft '{draft.title}': {len(draft.enforcements)} enforcement(s), checks: " + summarize(
            [Finding(f["severity"], f["message"], f["where"]) for f in findings]
        )
        report = Report(
            "song_draft",
            status,
            summary,
            tuple(draft.enforcements),
            {"draft": draft.to_dict(), "findings": findings, "request": request.to_dict()},
        )
        lines = [
            f"**{draft.title}**",
            "",
            *[f"- {note}" for note in draft.enforcements],
            *[f"- {f['severity']}: {f['message']}" for f in findings],
        ]
        return io.NodeOutput(
            draft.title,
            draft.style,
            draft.lyrics,
            draft.artwork_prompt,
            report,
            ui={"plenio_summary": [{"status": status.value, "markdown": "\n".join(lines)}]},
        )
