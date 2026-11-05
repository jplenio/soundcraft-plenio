"""Fix Misheard Words (owner's rule 2026-10-24): a cover's transcribed original lyrics are checked before the
render - the writer is asked only for a Cover Brief with original lyrics; new lyrics, an instrumental, a Song
Brief or no brief pass unchanged and ask no writer. The Song Sheet's note lists the corrections."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.comfy

DRAFT = "[Verse]\nWe walk doun the riverside\n\n[Chorus]\nHold me close tonight"
HEARD = [
    [["We", 0.99], ["walk", 0.97], ["doun", 0.3], ["the", 0.98], ["riverside", 0.9]],
    [["Hold", 0.97], ["me", 0.98], ["close", 0.9], ["tonight", 0.95]],
]


def node(name: str) -> Any:
    from plenio.comfy import nodes

    return next(n for n in nodes.NODES if n.GET_SCHEMA().node_id == name)


def cover(vocals: str = "original") -> Any:
    from plenio.core.brief import CoverBrief

    return replace(CoverBrief(), vocals=vocals, title="Riverside-cover", language="English")


def transcription(draft: str = DRAFT) -> Any:
    from plenio.core.reports import Report, Status

    return Report(
        "transcribe_lyrics",
        Status.OK,
        "",
        (),
        {"language": "en", "alignment": {"lyrics": draft, "heard_lines": HEARD}},
    )


def test_only_a_covers_original_lyrics_ask_the_writer(comfy_path: Path) -> None:
    from plenio.core.brief import SongBrief

    apply, compose = node("PlenioApplyHeardCheck"), node("PlenioComposeHeardCheck")
    assert apply.check_lazy_status(lyrics=DRAFT, brief=cover()) == ["answer"]
    prompt = compose.execute(lyrics=DRAFT, report=transcription(), brief=cover()).result[0]
    assert "1: We walk [doun] the riverside" in prompt and '"Riverside"' in prompt
    for brief in (cover("new"), cover("instrumental"), SongBrief(), None):
        assert apply.check_lazy_status(lyrics=DRAFT, brief=brief) == []
        assert compose.execute(lyrics=DRAFT, brief=brief).result[0] == ""
        out = apply.execute(lyrics=DRAFT, brief=brief)
        assert out.result[0] == DRAFT and out.result[1].status.value == "skipped"


def test_the_corrections_go_into_the_draft_and_the_sheets_note(
    comfy_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from plenio.comfy.nodes import heard_check
    from plenio.core.asr import AsrNotes
    from plenio.core.hashing import sha256_text
    from plenio.core.sheet.resolve import normalize_document

    notes = AsrNotes(tmp_path / "notes")
    monkeypatch.setattr(heard_check, "asr_notes", lambda: notes)
    notes.put(
        {
            "draft_sha256": sha256_text(normalize_document(DRAFT)),
            "engine": "qwen3",
            "language": "English",
            "low_confidence": ["doun"],
            "left_out": ["thanks"],
        }
    )
    answer = '{"fixes": [{"line": 1, "heard": "doun", "word": "down", "sure": 0.9}, {"line": 2, "heard": "close", "word": "clothes", "sure": 0.7}]}'
    out = node("PlenioApplyHeardCheck").execute(
        lyrics=DRAFT, answer=answer, report=transcription(), brief=cover(), language="English"
    )
    fixed, report = out.result
    assert fixed == DRAFT.replace("doun", "down")
    assert report.status.value == "ok" and report.data["corrected"][0]["word"] == "down"
    note = notes.get(sha256_text(normalize_document(fixed)))
    assert note is not None
    assert note["corrected"] == [{"heard": "doun", "word": "down"}]
    assert note["low_confidence"] == [] and note["left_out"] == ["thanks"]
