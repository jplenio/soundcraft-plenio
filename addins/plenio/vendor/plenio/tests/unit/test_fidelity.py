"""Lyrics fidelity: one take, or the best of two or three (owner's request 2026-10-24)."""

from __future__ import annotations

import pytest

from plenio.core.brief import build_cover_brief, build_song_brief
from plenio.core.errors import PlenioUserError
from plenio.core.fidelity import (
    FIDELITY_OPTIONS,
    HIGH,
    HIGHEST,
    STANDARD,
    TARGET,
    Choice,
    best,
    fidelity_level,
    needs_another,
)


def test_the_choices_and_their_levels() -> None:
    assert list(FIDELITY_OPTIONS.values()) == [STANDARD, HIGH, HIGHEST]
    assert fidelity_level("high - best of 2 takes") == HIGH
    assert fidelity_level("highest") == HIGHEST
    assert fidelity_level("") == fidelity_level(None) == STANDARD  # an older workflow: one take
    with pytest.raises(PlenioUserError):
        fidelity_level("best of 9")


def test_a_further_take_only_while_the_best_so_far_is_below_96_percent() -> None:
    assert TARGET == 0.96
    assert not needs_another(STANDARD, [0.4])
    # high: the second take only when the first sang less than 96 %
    assert (
        needs_another(HIGH, [0.95]) and not needs_another(HIGH, [TARGET]) and not needs_another(HIGH, [0.99])
    )
    assert not needs_another(HIGH, [0.5, 0.6])  # two at most
    # highest: the same after the first, a third only when neither of the two reached 96 %
    assert needs_another(HIGHEST, [0.80]) and not needs_another(HIGHEST, [0.97])
    assert needs_another(HIGHEST, [0.80, 0.95])
    assert not needs_another(HIGHEST, [0.80, TARGET])
    assert not needs_another(HIGHEST, [0.5, 0.6, 0.7])  # three at most
    assert needs_another(HIGH, [float("nan")])  # a take not heard: another one


def test_the_take_that_sings_most_is_kept_the_first_at_a_tie() -> None:
    assert best([0.8, 0.93, 0.9]) == 1
    assert best([0.9, 0.9]) == 0
    choice = Choice(HIGH, (0.81, 0.94), 1)
    assert choice.text == (
        "Lyrics fidelity high: take 2 of 2 kept - 94% of the lyrics heard as written (take 1: 81%, take 2: 94%)"
    )
    assert choice.to_dict() == {"level": HIGH, "takes": 2, "kept": 2, "scores": [0.81, 0.94]}


def test_the_brief_keeps_the_fidelity_for_sung_songs_only() -> None:
    sung = build_song_brief({"genre": "pop", "fidelity": "highest - best of 3 takes"})
    assert sung.fidelity == HIGHEST and sung.fingerprint != build_song_brief({"genre": "pop"}).fingerprint
    assert (
        build_song_brief({"genre": "pop", "vocals": "instrumental", "fidelity": "high"}).fidelity == STANDARD
    )
    assert (
        build_cover_brief({"genre": "jazz", "vocals": "original lyrics", "fidelity": "high"}).fidelity == HIGH
    )
    assert build_cover_brief({"genre": "jazz", "fidelity": "high"}).fidelity == STANDARD  # instrumental
