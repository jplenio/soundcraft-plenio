"""Instrumental songs get more sections (owner's request 2026-10-12).

YuE2 planned 1-3 sections in 44 % of the owner's 110 instrumental demos - mostly an intro and one *interlude*
of 50-120 bars - although its planner read eight section tags. *prepare from brief* now splits a long section
into parts of 8 or 16 bars at phrase ends and names them by their music, so the arrangement (and the render)
has sections to vary. Only section starts are added; the notes stay.
"""

from __future__ import annotations

from plenio.core.brief import SongBrief
from plenio.core.preparation import LONG_SECTION_BARS, prepare_for_brief, split_long_sections
from plenio.core.score import canonical, native

HEAD = (
    "X:1\nT:\nM:4/4\nL:1/16\nQ:1/4=120\n"
    'V: Vocal clef=treble name="Vocal Melody" snm="Vocal"\nV: Ins clef=treble name="Ins Melody" snm="Inst."\nK:C\n'
)
BARS = {
    "A": "C4D4E4F4|",
    "B": "G4A4B4c4|",
    "C": "c4B4A4G4|",
    "D": "E4E4G4G4|",
    "held": "C16-|",  # a note held into the next bar
    "end": "C16|",
}


def section(label: str, melody: str) -> str:
    """A section whose Ins plays ``melody`` (bar names of ``BARS``, one per bar); the Vocal rests."""
    names = melody.split()
    groups = [names[i : i + 4] for i in range(0, len(names), 4)]  # line groups of four bars, as YuE2 writes
    body = "".join(
        f"V: Vocal\n{'Z|' * len(group)}\nV: Ins\n{''.join(BARS[name] for name in group)}\n"
        for group in groups
    )
    return f"% {label}\n{body}"


def score(*sections: str) -> str:
    return HEAD + "".join(sections)


def labels(text: str) -> list[str]:
    return [s.label for s in native.validate(text).sections]


def starts(text: str) -> list[int]:
    return [s.measure + 1 for s in canonical.from_abc(text).sections]


def part(name: str, bars: int = 8) -> str:
    return " ".join([name] * bars)


def test_a_long_section_is_split_into_parts_named_by_their_music() -> None:
    # an intro and one interlude of 32 bars: A, B, A, C - eight bars each
    text = score(
        section("intro", part("D", 4)),
        section("interlude", " ".join(part(n) for n in "ABAC")),
    )
    change = split_long_sections(text)
    assert labels(change.abc) == ["intro", "interlude", "verse", "interlude", "chorus"]
    assert starts(change.abc) == [1, 5, 13, 21, 29]
    # only section starts were added: the notes, the chords and the length stay
    before, after = canonical.from_abc(text), canonical.from_abc(change.abc)
    assert (before.vocal, before.ins, before.chords) == (after.vocal, after.ins, after.chords)
    assert native.validate(change.abc).duration_s == native.validate(text).duration_s
    assert "the long interlude is split into parts at phrase ends" in change.changes[0]


def test_a_cut_moves_to_a_phrase_end() -> None:
    # bar 8 of the section holds its note into bar 9: the cut goes one bar earlier or later, never inside
    body = " ".join(["A"] * 7 + ["held", "end"] + ["B"] * 15)
    text = score(section("verse", body))
    cuts = starts(split_long_sections(text).abc)
    assert 9 not in cuts and (8 in cuts or 10 in cuts)


def test_short_sections_stay_and_long_ones_get_16_bar_parts() -> None:
    short = score(section("intro", part("D", 4)), section("verse", part("A", LONG_SECTION_BARS)))
    assert split_long_sections(short).abc == short
    # 64 bars: parts of 16 (more than 48 bars) - and one music throughout keeps one name
    long = score(section("intro", part("D", 4)), section("interlude", part("A", 64)))
    split = split_long_sections(long).abc
    assert starts(split) == [1, 5, 21, 37, 53]
    assert labels(split) == ["intro"] + ["interlude"] * 4


def test_a_long_outro_keeps_its_name_on_its_last_part() -> None:
    text = score(section("verse", part("A")), section("outro", " ".join(part(n) for n in "BCD")))
    assert labels(split_long_sections(text).abc) == ["verse", "chorus", "bridge", "outro"]
    assert starts(split_long_sections(text).abc) == [1, 9, 17, 25]


def test_preparation_splits_instrumental_songs_only() -> None:
    # 44 bars at 120 BPM: 88 s, within the length of a short song (no fitting)
    text = score(section("intro", part("D", 4)), section("interlude", " ".join(part(n) for n in "ABACA")))
    instrumental = prepare_for_brief(text, SongBrief(vocals="instrumental", length="short (about 1:30)"))
    assert len(native.validate(instrumental.abc).sections) == 6
    assert any("split into parts" in change for change in instrumental.changes)
    sung = prepare_for_brief(text, SongBrief(length="short (about 1:30)"))
    assert len(native.validate(sung.abc).sections) == 2
