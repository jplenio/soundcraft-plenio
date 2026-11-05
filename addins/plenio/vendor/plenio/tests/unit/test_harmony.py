"""The harmony guard of the creative modes (``plenio.core.arrangement.harmony``; owner's request 2026-10-08,
``docs/design/harmony-and-lyrics-fit.md``): keys, the genre's chord vocabulary, how a chord carries the
melody, the repair of a writer's chords and the measures of a score."""

from __future__ import annotations

import math
from dataclasses import replace
from pathlib import Path

import pytest

from plenio.core.arrangement import harmony
from plenio.core.score import canonical as c

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = c.from_abc((ROOT / "tests" / "fixtures" / "abc" / "upstream-score.abc").read_text(encoding="utf-8"))
"""C major, 4/4, L:1/16: verse C G Am F, chorus C F G C, a sung melody in eighths."""


def vocab(key: str = "C", genre: str = "pop", closeness: int = 70, qualities: tuple[str, ...] | None = None):
    family = harmony.genre_of(genre)
    return harmony.vocabulary(
        harmony.key_of(key), family, qualities or family.qualities, closeness=closeness, tensions="colour"
    )


# --- chords and keys ----------------------------------------------------------------------------


def test_chord_tones() -> None:
    assert harmony.tones("C") == {0, 4, 7}
    assert harmony.tones("F#m7b5") == {6, 9, 0, 4}
    assert harmony.tones("C/E") == {0, 4, 7}
    assert harmony.tones("Am/G") == {9, 0, 4, 7}
    with pytest.raises(ValueError):
        harmony.tones("Hm")


def test_the_key_of_a_section() -> None:
    assert harmony.section_key(FIXTURE, 0, 4).name == "C"
    # a transcribed key that the notes clearly contradict gives way: the same melody written under K:F#
    wrong = replace(FIXTURE, keys=(c.KeyChange(0, "F#", "header"),))
    assert harmony.section_key(wrong, 0, 8).name in ("C", "Am")
    # the relative minor has the same notes: the score's own name stays
    relative = replace(FIXTURE, keys=(c.KeyChange(0, "Am", "header"),))
    assert harmony.section_key(relative, 0, 8).name == "Am"


def test_genre_words() -> None:
    assert harmony.genre_of("dreamy indie pop").family == "rock"  # indie is listed under rock
    assert harmony.genre_of("synth-pop, 80s").family == "edm"
    assert harmony.genre_of("neo soul with jazz chords").family == "jazz"  # jazz is checked first
    assert harmony.genre_of("").family == "pop"
    assert harmony.genre_of("popcorn music").family == "pop"  # no word inside a word


# --- the vocabulary -------------------------------------------------------------------------------


def test_the_vocabulary_of_a_key() -> None:
    v = vocab("C")
    assert {v.kind(n) for n in ("C", "Dm", "Em", "F", "G", "Am", "G7", "Fmaj7")} == {"diatonic"}
    assert v.kind("Bb") == "borrowed" and v.kind("Fm") == "borrowed" and v.kind("Ab") == "borrowed"
    assert v.kind("E7") == "secondary" and v.resolves_to("E7") == 9  # V of vi
    assert v.kind("C#") is None and v.kind("F#m") is None and v.kind("Ebm") is None
    assert v.kind("Cdim7") is None  # not a pop quality
    minor = vocab("Am")
    assert minor.kind("E") == "diatonic" and minor.kind("E7") == "diatonic"  # V of harmonic minor
    assert minor.kind("G") == "diatonic" and minor.kind("F") == "diatonic"


def test_the_palette_offered_to_the_writer() -> None:
    text = vocab("B").palette()
    assert text.startswith("B, C#m, D#m, E, F#, G#m")  # spelled in the key, not Db or Ab
    assert "borrowed, typical in pop: A, Em, G" in text


def test_low_closeness_drops_the_key_test_not_the_melody_test() -> None:
    free = vocab("C", closeness=20, qualities=("", "m", "7", "dim", "aug"))
    assert free.free and free.kind("C#") == "borrowed" and free.kind("Caug") == "borrowed"


# --- the melody under a chord ---------------------------------------------------------------------


def test_fit_cost_forbids_accented_avoid_notes() -> None:
    beat = FIXTURE.units_per_quarter
    key = harmony.key_of("C")
    verse = harmony.pieces(FIXTURE, FIXTURE.vocal, FIXTURE.starts[0], FIXTURE.starts[1])  # E G A G E D C
    assert harmony.fit_cost(verse, "C", key=key, tensions=frozenset({2, 9}), beat=beat) < 1
    second = harmony.pieces(FIXTURE, FIXTURE.vocal, FIXTURE.starts[1], FIXTURE.starts[2])  # D E G E D C D
    assert harmony.fit_cost(second, "C#", key=key, tensions=frozenset(), beat=beat) == math.inf  # D over C#
    assert harmony.fit_cost(verse, None, key=key, tensions=frozenset(), beat=beat) == 0


def test_the_blue_third_clashes_outside_blues_and_rock() -> None:
    e_major = harmony.tones("E")  # E G# B; G is its blue third
    assert harmony.clashing(7, e_major, 4, frozenset({2, 9}))
    assert not harmony.clashing(7, e_major, 4, harmony.genre_of("blues rock").tensions)
    assert not harmony.clashing(7, harmony.tones("Em"), 4, frozenset())  # a chord tone of E minor


def test_avoid_notes_below_a_major_seventh_and_beside_the_fifth() -> None:
    """CLAUDE_AUFTRAG 2026-10-14, bug 2: b7 against maj7 and the tritone next to the fifth went unnoticed."""
    c_major, c_maj7, c_minor = harmony.tones("C"), harmony.tones("Cmaj7"), harmony.tones("Cm")
    assert harmony.is_avoid(6, c_major, 0)  # F# over C: #4 a half step under the fifth
    assert not harmony.is_avoid(6, c_major)  # without the root only the half step above a chord tone counts
    assert harmony.is_avoid(10, c_maj7, 0)  # Bb against B
    assert not harmony.is_avoid(10, harmony.tones("C7"), 0)  # a chord tone of C7
    assert not harmony.is_avoid(9, harmony.tones("C7"), 0)  # the 13th of a dominant stays free
    assert harmony.is_avoid(4, c_minor, 0)  # E over Cm: a half step above its third
    assert not harmony.is_avoid(6, harmony.tones("Caug"), 0)  # no perfect fifth to grind against
    assert harmony.is_avoid(3, harmony.tones("Am"), 9)  # D# over Am
    assert harmony.clashing(6, c_major, 0, frozenset({2, 9}))


def test_the_blue_third_is_short_over_a_triad_and_free_over_a_dominant_seventh() -> None:
    """Owner's decision 2026-10-15: an accented or held minor third over a major triad clashes in every genre; over
    a dominant seventh chord (the blues' I7, where it is the #9) the genres that take it keep it."""
    rock = harmony.genre_of("rock").tensions
    blues = harmony.genre_of("blues").tensions
    assert not harmony.clashing(3, harmony.tones("C"), 0, rock)  # a short passing blue note
    assert harmony.clashing(3, harmony.tones("C"), 0, rock, accented=True)
    assert not harmony.clashing(3, harmony.tones("C7"), 0, blues, accented=True)
    assert harmony.clashing(3, harmony.tones("C7"), 0, frozenset({2, 9}), accented=True)  # pop: never
    beat = FIXTURE.units_per_quarter
    held = [harmony.Piece(0, 4 * beat, 63, True)]  # Eb held for a bar
    key = harmony.key_of("C")
    assert harmony.fit_cost(held, "C", key=key, tensions=rock, beat=beat) == math.inf
    assert harmony.fit_cost(held, "C7", key=key, tensions=blues, beat=beat) < 1


def test_a_soft_fit_lets_an_accented_clash_cost() -> None:
    beat = FIXTURE.units_per_quarter
    key = harmony.key_of("C")
    second = harmony.pieces(FIXTURE, FIXTURE.vocal, FIXTURE.starts[1], FIXTURE.starts[2])  # D E G E D C D
    soft = harmony.fit_cost(second, "C#", key=key, tensions=frozenset(), beat=beat, soft=True)
    assert soft != math.inf and soft >= harmony.ACCENTED_CLASH


# --- the repair -------------------------------------------------------------------------------------


def test_a_fitting_writer_chord_stands_and_an_out_of_key_one_goes() -> None:
    v = vocab("C")
    bars = harmony.repair(FIXTURE, 0, 4, ["Am", "G", "Db", "F"], FIXTURE.vocal, v)
    chosen = [bar.chords[0][1] if bar.chords else None for bar in bars]
    assert chosen[1] == "G" and chosen[3] == "F"
    assert chosen[2] != "Db" and "bar 3: Db is not a chord of C" in bars[2].note
    assert all(v.kind(name) is not None for name in chosen if name)


def test_a_chord_half_a_step_off_the_key_is_replaced() -> None:
    """Study A1, S1: G#m -> Am in a song in B major (accepted then because only beats 1 and 3 were read)."""
    model = c.from_abc(
        (ROOT / "tests" / "fixtures" / "abc" / "upstream-score.abc").read_text(encoding="utf-8")
    )
    up = c.from_abc(c.to_abc(model))
    bars = harmony.repair(up, 0, 4, ["C", "C#m", "Am", "F"], up.vocal, vocab("C"))
    assert bars[1].chords is None or bars[1].chords[0][1] != "C#m"
    assert bars[1].note.startswith("bar 2: C#m")


def test_keep_leaves_a_bar_alone() -> None:
    bars = harmony.repair(FIXTURE, 0, 4, [None, None, None, None], FIXTURE.vocal, vocab("C"))
    assert all(bar.chords is None and not bar.note for bar in bars)


def test_a_secondary_dominant_must_resolve() -> None:
    v = vocab("C")
    resolving = harmony.repair(FIXTURE, 0, 4, ["C", "E7", "Am", "F"], FIXTURE.vocal, v)
    # C carries bar 3 (E G A C B A G) but does not resolve E7 (F would not carry it: B on beat 3 is its #4)
    stuck = harmony.repair(FIXTURE, 0, 4, ["C", "E7", "C", "F"], FIXTURE.vocal, v)

    def sounding(bars: list[harmony.RepairedBar], i: int, original: str) -> str:
        return bars[i].chords[0][1] if bars[i].chords else original

    assert sounding(resolving, 1, "G") == "E7" and sounding(resolving, 2, "Am") == "Am"
    # E7 -> C does not resolve: either E7 goes, or the bar after it keeps its Am (it resolves there)
    assert sounding(stuck, 1, "G") != "E7" or sounding(stuck, 2, "Am") == "Am"
    assert "does not follow well" in stuck[2].note or "does not follow well" in stuck[1].note


def test_the_melody_weight_lets_the_writers_chords_win() -> None:
    """A cover whose melody follows the chords: at weight 0 the writer's chord stands wherever it is in the
    vocabulary, even over an accented clash (bar 3 sings B on beat 3, the #4 of F)."""
    v = vocab("C")
    strict = harmony.repair(FIXTURE, 0, 4, [None, None, "F", None], FIXTURE.vocal, v)
    free = harmony.repair(FIXTURE, 0, 4, [None, None, "F", None], FIXTURE.vocal, v, melody_weight=0.0)
    assert strict[2].chords is None or strict[2].chords[0][1] != "F"
    assert free[2].chords == ((FIXTURE.starts[2], "F"),) and not free[2].note
    out_of_key = harmony.repair(FIXTURE, 0, 4, [None, "C#", None, None], FIXTURE.vocal, v, melody_weight=0.0)
    assert out_of_key[1].chords is None or out_of_key[1].chords[0][1] != "C#"  # the key test stays


# --- the melody follows the chords ----------------------------------------------------------------------


def _with_chords(*names: tuple[int, str]) -> c.Score:
    return replace(FIXTURE, chords=tuple(c.ChordSymbol(FIXTURE.starts[m], name) for m, name in names))


def test_from_closeness_85_the_melody_stays() -> None:
    score = _with_chords((0, "Bb"))
    notes, moved = harmony.co_adapt_melody(score, 0, 1, score.vocal, closeness=85)
    assert moved == 0 and notes == sorted(score.vocal, key=lambda n: n.onset)


def test_from_closeness_50_a_clash_moves_to_the_nearest_chord_tone() -> None:
    score = _with_chords((0, "Bb"), (1, "G"), (2, "Am"), (3, "F"))
    notes, moved = harmony.co_adapt_melody(score, 0, 1, score.vocal, closeness=70)
    bar = [n for n in notes if n.onset < score.starts[1]]
    old = [n for n in score.vocal if n.onset < score.starts[1]]
    assert [(n.onset, n.duration) for n in bar] == [(n.onset, n.duration) for n in old]  # the rhythm stays
    # E on beats 1 and 3 is the #4 of Bb: it moves a half step up to F; G, A, D and C fit Bb and stay
    assert [n.pitch for n in bar] == [65, 67, 69, 67, 65, 62, 60] and moved == 2
    assert [n for n in notes if n.onset >= score.starts[1]] == list(
        score.vocal[len(old) :]
    )  # other bars stay


def test_below_closeness_50_the_melody_is_written_anew_over_the_chords() -> None:
    score = _with_chords((0, "Am"), (1, "Em"), (2, "F"), (3, "G"))
    for closeness in (40, 20, 0):
        notes, moved = harmony.co_adapt_melody(score, 0, 4, score.vocal, closeness=closeness, seed=1)
        assert moved > 0
        assert [(n.onset, n.duration) for n in notes] == [(n.onset, n.duration) for n in score.vocal]
        assert all(60 <= n.pitch <= 72 for n in notes)  # the melody's own range
        adapted = replace(score, vocal=tuple(notes))
        inside = [n for n in notes if n.onset < score.starts[4]]
        assert harmony.measure(adapted, inside).accented_avoid == 0
        assert harmony.measure(adapted, inside).clash_share == 0
        again, _ = harmony.co_adapt_melody(score, 0, 4, score.vocal, closeness=closeness, seed=1)
        assert again == notes  # deterministic
    near, _ = harmony.co_adapt_melody(score, 0, 4, score.vocal, closeness=45)
    far, _ = harmony.co_adapt_melody(score, 0, 4, score.vocal, closeness=0)

    def distance(notes: list[c.Note]) -> int:
        return sum(abs(a.pitch - b.pitch) for a, b in zip(notes, score.vocal, strict=True))

    assert distance(near) < distance(far)  # the old line steers less the lower the closeness


def test_an_instrument_melody_may_get_new_rhythms() -> None:
    score = replace(_with_chords((0, "Am"), (1, "Em"), (2, "F"), (3, "G")), vocal=(), ins=FIXTURE.vocal)
    found = False
    for seed in range(4):
        notes, moved = harmony.co_adapt_melody(
            score, 0, 4, score.ins, closeness=10, seed=seed, allow_rhythm_change=True
        )
        assert moved > 0
        for m in range(4):
            start, stop = score.starts[m], score.starts[m + 1]
            old = [n for n in score.ins if start <= n.onset < stop]
            new = [n for n in notes if start <= n.onset < stop]
            assert new[0].onset == old[0].onset and new[-1].end == old[-1].end  # the phrase keeps its span
            found = found or [n.onset for n in new] != [n.onset for n in old]
    assert found
    kept, _ = harmony.co_adapt_melody(score, 0, 4, score.ins, closeness=30, allow_rhythm_change=True)
    first_bar = [(n.onset, n.duration) for n in kept if n.onset < score.starts[1]]
    assert first_bar == [(n.onset, n.duration) for n in score.ins if n.onset < score.starts[1]]  # the hook


# --- measures -------------------------------------------------------------------------------------


def test_measures_of_a_score() -> None:
    plain = harmony.measure(FIXTURE, FIXTURE.vocal)
    assert plain.chords_in_key == 1.0 and plain.clashes == 0 and plain.overlap == 0
    assert 0.7 < plain.melody_on_chord <= 1
    # a line a minor second under every sung note: every moment clashes
    line = tuple(c.Note(n.onset, n.duration, n.pitch - 1) for n in FIXTURE.vocal)
    clashing = harmony.measure(replace(FIXTURE, ins=line), FIXTURE.vocal)
    assert clashing.overlap == 1.0 and clashing.clashes == 1  # one long span of time
    # split notes are not counted twice
    split = tuple(
        part
        for n in line
        for part in (c.Note(n.onset, 1, n.pitch), c.Note(n.onset + 1, n.duration - 1, n.pitch))
    )
    assert harmony.clashes(FIXTURE, FIXTURE.vocal, split) == 1
