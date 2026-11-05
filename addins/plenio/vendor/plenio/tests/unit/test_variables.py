"""Variables in Export Release's tags and file name (owner's request 2026-10-15): ``{name}``, optional parts in
``[...]``, literal braces, unknown names kept and reported."""

from __future__ import annotations

import pytest

from plenio.core import variables as v
from plenio.core.errors import PlenioUserError
from plenio.core.release import expand_pattern

VALUES = {"genre": "indie pop", "mood": "", "language": "English", "title": "Harbour Lights", "year": "2026"}


@pytest.mark.parametrize(
    ("template", "expected"),
    [
        ("Genre: {genre}", "Genre: indie pop"),
        ("Genre: {GENRE}", "Genre: indie pop"),  # any case is read
        ("[Mood: {mood} · ]Language: {language}", "Language: English"),
        ("[Mood: {mood} · ][Language: {language}]", "Language: English"),
        ("{genre}[, {mood}][, sung in {language}]", "indie pop, sung in English"),
        ("[Live] {title}", "[Live] Harbour Lights"),  # brackets without a variable stay text
        ("{{genre}} [x]", "{genre} [x]"),
        ("[outer {genre} [inner {mood}]]", "outer indie pop "),
        ("{key}", ""),  # a variable without a value
        ("open [bracket {genre}", "open [bracket indie pop"),
        ("", ""),
    ],
)
def test_expand(template: str, expected: str) -> None:
    assert v.expand(template, VALUES) == (expected, [])


def test_unknown_names_stay_and_are_reported() -> None:
    assert v.expand("{genre} {genr} {foo}", VALUES) == ("indie pop {genr} {foo}", ["foo", "genr"])
    assert v.unknown_names("{title} [{albm}]") == ["albm"]
    assert "{genre}" in v.unknown_message("The comment", ["genr"])


def test_every_group_has_names_and_the_tags_are_variables() -> None:
    assert {
        "title",
        "lyrics",
        "genre",
        "genre_closeness",
        "date",
        "take_seed",
        "model",
        "plenio_version",
    } <= v.NAMES
    assert v.TAG_VARIABLES == ("artist", "album", "album_artist", "composer", "track")


def test_the_file_name_takes_the_variables_without_their_slashes() -> None:
    values = {"title": "Song", "genre": "rock/pop", "artist": "The Band"}
    assert expand_pattern("{artist} - {title}[ ({genre})]", values) == "The Band - Song (rock-pop)"
    assert expand_pattern("{genre}/{title}", {"genre": "jazz", "title": "Song"}) == "jazz/Song"
    with pytest.raises(PlenioUserError):
        expand_pattern("{titel}", values)
