"""Misheard words in a cover's original lyrics, before the render (owner's rule 2026-10-24): the words the ASR
was unsure of are marked for the writer model; only sure corrections that sound like what was heard and have as
many syllables are taken, and the draft keeps everything else."""

from __future__ import annotations

import json

from plenio.core import heard_check as hc
from plenio.core.alignment import AsrWord, align

DRAFT = "[Verse]\nWe walk doun the riverside\nUnder the silver moon\n\n[Chorus]\nHold me clothes tonight"
HEARD = [
    [["We", 0.99], ["walk", 0.97], ["doun", 0.31], ["the", 0.98], ["riverside", 0.9]],
    [["Under", 0.95], ["the", 0.99], ["silver", 0.93], ["moon", 0.96]],
    [["Hold", 0.97], ["me", 0.98], ["clothes", 0.62], ["tonight", 0.95]],
]


def answer(*fixes: dict) -> str:
    return json.dumps({"fixes": list(fixes)})


def test_the_unsure_words_are_marked() -> None:
    lines, words = hc.draft_words(DRAFT, HEARD)
    assert lines == ["We walk doun the riverside", "Under the silver moon", "Hold me clothes tonight"]
    assert [(w.line, w.text) for w in words if w.unsure] == [(0, "doun")]
    prompt = hc.check_prompt(lines, words, "English", "A Feeling With No Address")
    assert "1: We walk [doun] the riverside" in prompt
    assert "3: Hold me clothes tonight" in prompt
    assert '"A Feeling With No Address"' in prompt and "sung in English" in prompt


def test_a_changed_draft_has_no_marks() -> None:
    _lines, words = hc.draft_words(DRAFT.replace("doun", "down"), HEARD)
    assert words[2].text == "down" and not any(w.unsure for w in words)


def test_sure_alike_corrections_with_the_same_syllables_are_taken() -> None:
    lines, words = hc.draft_words(DRAFT, HEARD)
    fixes, refused = hc.parse_answer(
        answer(
            {"line": 1, "heard": "doun", "word": "down", "sure": 0.85},
            {"line": 3, "heard": "clothes", "word": "close", "sure": 0.95},
        ),
        lines,
        words,
        "English",
    )
    assert [(f.line, f.heard, f.word, f.unsure) for f in fixes] == [
        (0, "doun", "down", True),
        (2, "clothes", "close", False),
    ]
    assert refused == []
    fixed = hc.corrected(DRAFT, fixes)
    assert (
        fixed
        == "[Verse]\nWe walk down the riverside\nUnder the silver moon\n\n[Chorus]\nHold me close tonight"
    )


def test_a_clearly_heard_word_needs_more_certainty() -> None:
    lines, words = hc.draft_words(DRAFT, HEARD)
    fixes, _refused = hc.parse_answer(
        answer({"line": 3, "heard": "clothes", "word": "close", "sure": 0.85}), lines, words
    )
    assert fixes == []


def test_rewrites_are_refused() -> None:
    lines, words = hc.draft_words(DRAFT, HEARD)
    fixes, refused = hc.parse_answer(
        answer(
            {"line": 2, "heard": "silver", "word": "golden", "sure": 0.95},  # fits, but does not sound alike
            {"line": 1, "heard": "doun", "word": "beyond", "sure": 0.9},  # another syllable count
            {"line": 2, "heard": "moonlight", "word": "moon", "sure": 0.95},  # not in that line
            {"line": 1, "heard": "riverside", "word": "the river", "sure": 0.99},  # "the the"
        ),
        lines,
        words,
        "English",
    )
    assert fixes == []
    assert len(refused) == 4
    assert "does not sound like" in refused[0] and "syllables" in refused[1]
    assert "not in that line" in refused[2] and "twice" in refused[3]


def test_a_broken_answer_changes_nothing() -> None:
    lines, words = hc.draft_words(DRAFT, HEARD)
    assert hc.parse_answer("I think line 1 says down", lines, words) == (
        [],
        ["the writer's answer had no fixes list"],
    )


def test_a_capital_at_the_start_of_a_line_stays() -> None:
    lines, words = hc.draft_words("[Verse]\nHole me tight", [[["Hole", 0.3], ["me", 0.9], ["tight", 0.9]]])
    fixes, _ = hc.parse_answer(
        answer({"line": 1, "heard": "hole", "word": "hold", "sure": 0.9}), lines, words
    )
    assert hc.corrected("[Verse]\nHole me tight", fixes) == "[Verse]\nHold me tight"


def test_the_alignment_reports_the_heard_words_of_every_line() -> None:
    words = [
        AsrWord(0.0, 0.4, "We", 0.99),
        AsrWord(0.5, 0.9, "walk", 0.4),
        AsrWord(3.0, 3.4, "Under", 0.9),
    ]
    alignment = align(words, [], timeline=None)
    assert alignment.lyrics == "[Verse]\nWe walk\nUnder"
    assert alignment.to_dict()["heard_lines"] == [[["We", 0.99], ["walk", 0.4]], [["Under", 0.9]]]
    _lines, marked = hc.draft_words(alignment.lyrics, alignment.to_dict()["heard_lines"])
    assert [w.text for w in marked if w.unsure] == ["walk"]


def test_only_what_a_correction_changes_counts() -> None:
    draft = "[Verse]\nI'm not the only one"
    lines, words = hc.draft_words(
        draft, [[["I'm", 0.3], ["not", 0.9], ["the", 0.9], ["only", 0.9], ["one", 0.9]]]
    )
    fixes, refused = hc.parse_answer(
        answer({"line": 1, "heard": "I'm not the only", "word": "We're not the only", "sure": 0.95}),
        lines,
        words,
    )
    assert fixes == [] and "does not sound like" in refused[0] and "'I'm' -> 'We're'" in refused[0]


def test_chinese_and_japanese_lyrics_are_not_checked() -> None:
    assert hc.not_checked("[Verse]\n我们 走 在 河边\n月光 下") != ""
    assert hc.not_checked("[Verse]\nWe walk down the riverside") == ""
    assert hc.not_checked("[Verse]\n") != ""
