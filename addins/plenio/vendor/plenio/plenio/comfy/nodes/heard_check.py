"""Fix Misheard Words: misheard words in a cover's original lyrics, corrected by the writer model before the
render (owner's rule 2026-10-24, ``core.heard_check``). Between Transcribe Lyrics and the Song Sheet: Compose asks
about the draft, the words the ASR was unsure of marked; Apply takes the corrections that hold and hands the draft
on. Only for a Cover Brief with *original lyrics* - lyrics the user writes, new lyrics and generated songs are
never corrected."""

from __future__ import annotations

import json
from typing import Any

from comfy_api.latest import io

from ...core import heard_check as rules
from ...core.brief import CoverBrief
from ...core.hashing import sha256_text
from ...core.reports import Report, Status
from ...core.sheet.resolve import normalize_document
from ..lyrics_asr import asr_notes
from ..types import Brief, ReportType

LYRICS_TOOLTIP = "The lyrics draft Transcribe Lyrics made from the source's singing (its 'lyrics' output)."
REPORT_TOOLTIP = "Transcribe Lyrics' report: which words it heard unsure (they are marked for the writer)."
BRIEF_TOOLTIP = "The Cover Brief: only original lyrics are checked; its title names the song for the writer."
LANGUAGE_TOOLTIP = "The language Transcribe Lyrics heard (its 'language' output)."


def _heard_lines(report: Any, lyrics: str) -> list[Any] | None:
    """The heard words of the draft's lines, when the report is the draft's own."""
    data = getattr(report, "data", None) or {}
    alignment = data.get("alignment") if isinstance(data, dict) else None
    if not isinstance(alignment, dict) or alignment.get("lyrics") != lyrics:
        return None
    lines = alignment.get("heard_lines")
    return lines if isinstance(lines, list) else None


def _why_not(brief: Any, lyrics: str) -> str:
    """Why a draft is not checked (``""``: it is)."""
    if not isinstance(brief, CoverBrief):
        return "only a cover's original lyrics are checked (no Cover Brief connected)"
    if not brief.use_source_lyrics:
        return "only original lyrics are checked (the brief asks for new lyrics or an instrumental)"
    return rules.not_checked(lyrics)


def _song(brief: Any) -> str:
    title = str(getattr(brief, "title", "") or "").strip()
    return title[: -len("-cover")].strip() if title.lower().endswith("-cover") else title


def _language(brief: Any, heard: str) -> str:
    given = str(getattr(brief, "language", "") or "").strip()
    return given if given and given.lower() != "auto" else (heard or "").strip()


class PlenioComposeHeardCheck(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="PlenioComposeHeardCheck",
            display_name="Compose Misheard Check",
            category="Plenio/Lyrics",
            description=(
                "The question about a cover's transcribed original lyrics: the draft, its lines numbered, the words "
                "the ASR was unsure of marked. Connect it to a writer (Generate Text or Local LLM, which also takes "
                "the schema) and the answer to Apply Misheard Check."
            ),
            inputs=[
                io.String.Input("lyrics", force_input=True, tooltip=LYRICS_TOOLTIP),
                ReportType.Input("report", optional=True, tooltip=REPORT_TOOLTIP),
                Brief.Input("brief", optional=True, tooltip=BRIEF_TOOLTIP),
                io.String.Input("language", optional=True, force_input=True, tooltip=LANGUAGE_TOOLTIP),
            ],
            outputs=[
                io.String.Output(display_name="prompt", tooltip="The question for the writer model."),
                io.String.Output(display_name="schema", tooltip="The answer's JSON schema, for Local LLM."),
            ],
        )

    @classmethod
    def execute(cls, lyrics: str, report: Any = None, brief: Any = None, language: str = "") -> io.NodeOutput:
        schema = json.dumps(rules.ANSWER_SCHEMA)
        if _why_not(brief, lyrics):
            return io.NodeOutput("", schema)
        lines, words = rules.draft_words(lyrics, _heard_lines(report, lyrics))
        prompt = rules.check_prompt(lines, words, _language(brief, language), _song(brief))
        return io.NodeOutput(prompt, schema)


class PlenioApplyHeardCheck(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="PlenioApplyHeardCheck",
            # the summary is re-sent on every run, also when the node is cached (ComfyUI keeps its UI)
            has_intermediate_output=True,
            display_name="Apply Misheard Check",
            category="Plenio/Lyrics",
            description=(
                "Corrects misheard words in a cover's transcribed original lyrics, before the render: of the writer "
                f"model's corrections it takes those that are sure enough ({rules.MIN_SURE:.0%} for a word the ASR "
                f"was unsure of, {rules.MIN_SURE_CLEAR:.0%} for any other), sound like what was heard and have as "
                "many syllables. The Song Sheet lists each one with the word heard. Lyrics that are not a cover's "
                "original lyrics pass unchanged and ask no writer."
            ),
            inputs=[
                io.String.Input("lyrics", force_input=True, tooltip=LYRICS_TOOLTIP),
                io.String.Input(
                    "answer",
                    optional=True,
                    lazy=True,
                    force_input=True,
                    tooltip="The writer model's answer (asked only for a cover's original lyrics).",
                ),
                ReportType.Input("report", optional=True, tooltip=REPORT_TOOLTIP),
                Brief.Input("brief", optional=True, tooltip=BRIEF_TOOLTIP),
                io.String.Input("language", optional=True, force_input=True, tooltip=LANGUAGE_TOOLTIP),
            ],
            outputs=[
                io.String.Output(
                    display_name="lyrics", tooltip="The draft, with the misheard words corrected."
                ),
                ReportType.Output(display_name="report", tooltip="What was corrected, and why not the rest."),
            ],
        )

    @classmethod
    def check_lazy_status(
        cls, lyrics: str = "", answer: str | None = None, brief: Any = None, **_: Any
    ) -> list[str]:
        return ["answer"] if answer is None and not _why_not(brief, lyrics) else []

    @classmethod
    def execute(
        cls, lyrics: str, answer: str | None = None, report: Any = None, brief: Any = None, language: str = ""
    ) -> io.NodeOutput:
        def done(
            text: str, status: Status, summary: str, notes: list[str], data: dict[str, Any]
        ) -> io.NodeOutput:
            out = Report(
                "heard_check", status, summary, tuple(notes), {"schema": rules.SCHEMA_VERSION, **data}
            )
            lines = "\n".join(f"- {note}" for note in notes)
            markdown = f"**{summary}**" + (f"\n{lines}" if lines else "")
            return io.NodeOutput(
                text, out, ui={"plenio_summary": [{"status": status.value, "markdown": markdown}]}
            )

        why = _why_not(brief, lyrics)
        if why:
            return done(lyrics, Status.SKIPPED, f"Misheard words: not checked - {why}", [], {})
        lines, words = rules.draft_words(lyrics, _heard_lines(report, lyrics))
        fixes, refused = rules.parse_answer(answer or "", lines, words, _language(brief, language))
        fixed = rules.corrected(lyrics, fixes)
        corrections = [f.to_record() for f in fixes]
        if fixes:
            _note_for(fixed, report, lyrics, fixes)
        marked = sum(1 for w in words if w.unsure)
        changed = [f"'{f.heard}' -> '{f.word}' (line {f.line + 1}, {f.sure:.0%} sure)" for f in fixes]
        summary = (
            f"Misheard words: {len(fixes)} corrected ({marked} word(s) the ASR was unsure of)"
            if fixes
            else f"Misheard words: none found ({marked} word(s) the ASR was unsure of)"
        )
        notes = [*changed, *(f"not taken: {why}" for why in refused)]
        return done(
            fixed, Status.OK, summary, notes, {"corrected": corrections, "refused": refused, "unsure": marked}
        )


def _note_for(fixed: str, report: Any, draft: str, fixes: list[rules.Fix]) -> None:
    """The Song Sheet's note for the corrected draft (it finds a note by its draft's hash): Transcribe Lyrics' note
    with the corrections - the words heard stay visible beside them."""
    data = getattr(report, "data", None) or {}
    note = {
        "draft_sha256": sha256_text(normalize_document(fixed)),
        "engine": str(data.get("engine") or ""),
        "language": str(data.get("language") or ""),
        "low_confidence": [],
        "left_out": [],
        "corrected": [{"heard": f.heard, "word": f.word} for f in fixes],
    }
    own = asr_notes().get(sha256_text(normalize_document(draft)))
    if own:
        fixed_words = {f.heard for f in fixes}
        note.update(
            engine=own.get("engine", note["engine"]),
            language=own.get("language", note["language"]),
            low_confidence=[w for w in own.get("low_confidence") or [] if w not in fixed_words],
            left_out=list(own.get("left_out") or []),
        )
    asr_notes().put(note)
