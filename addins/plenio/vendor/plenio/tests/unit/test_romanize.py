"""Heard words in the lyrics' Latin letters (owner's report 2026-10-24: Bollywood songs written in romanized
Hindi were heard in Devanagari - every line sung, and not one word paired)."""

from __future__ import annotations

from plenio.core import subtitles as s
from plenio.core.alignment import AsrWord
from plenio.core.romanize import fold, in_lyrics_script, romanize, script


def heard(text: str, start: float = 1.0) -> list[AsrWord]:
    return [
        AsrWord(start + 0.5 * k, start + 0.5 * k + 0.4, word, 0.9, 0) for k, word in enumerate(text.split())
    ]


def test_devanagari_is_written_as_hinglish_is() -> None:
    assert romanize("दिल") == "dil"
    assert romanize("नज़र") == "nazar"  # the inherent vowel at the word's end is not sung
    assert romanize("सुहानी") == "suhaanee"
    assert romanize("मुंबई") == "mumbaee"  # the nasal before b is an m
    assert romanize("प्यार") == "pyaar"  # the virama joins the consonants
    assert romanize("है") == "hai"


def test_other_scripts() -> None:
    assert romanize("사랑해") == "saranghae"
    assert (
        romanize("さくら") == "sakura"
        and romanize("ちょっと") == "chotto"
        and romanize("ラーメン") == "raamen"
    )
    assert romanize("любовь") == "lyubov"
    assert romanize("αγάπη") == "agapi"
    assert romanize("love") == "love" and romanize("爱") == "爱"


def test_fold_makes_spellings_of_one_word_alike() -> None:
    assert fold("raasta") == fold("rasta")
    assert fold("nazar") == fold("najar")
    assert fold("mein") == fold("men")
    assert fold("bhari") == fold("bari")
    assert fold("suhaanee") == fold("suhani")


def test_only_latin_lyrics_heard_in_a_script_of_its_own_are_romanized() -> None:
    hindi = heard("दिल से दिल तक")
    words, romanized = in_lyrics_script("[Verse]\nDil se dil tak", hindi)
    assert romanized and [w.word for w in words] == ["dil", "se", "dil", "tak"]
    assert words[0].start == hindi[0].start
    # lyrics in their own script, or heard in Latin letters: nothing changes
    assert in_lyrics_script("[Verse]\nदिल से दिल तक", hindi) == (hindi, False)
    assert in_lyrics_script("[Verse]\n君の名前", heard("きみ の なまえ")) == (heard("きみ の なまえ"), False)
    english = heard("hold on")
    assert in_lyrics_script("[Chorus]\nhold on", english) == (english, False)
    assert script("[Verse]\n君の名前を呼ぶ") != "latin"


def test_romanized_hindi_pairs_with_the_lyrics_and_keeps_their_spelling() -> None:
    lyrics = "[Verse]\nDil se dil tak\nYeh raat suhani hai\n\n[Chorus]\nMera pyaar tera"
    words, romanized = in_lyrics_script(lyrics, heard("दिल से दिल तक ये रात सुहानी है मेरा प्यार तेरा"))
    before = s.time_sung(
        lyrics, heard("दिल से दिल तक ये रात सुहानी है मेरा प्यार तेरा"), duration=20.0, timing=s.ALIGNED
    )
    assert before is not None and before.written_heard == 0.0
    sung = s.time_sung(lyrics, words, duration=20.0, timing=s.ALIGNED, romanized=romanized)
    assert sung is not None and sung.written_heard == 1.0 and sung.extra_words == 0
    # a word that pairs is shown as the lyrics spell it
    assert sung.text.splitlines()[1] == "Dil se dil tak"
    timed = s.time_lyrics(lyrics, words, duration=20.0, timing=s.ALIGNED, romanized=romanized)
    assert timed.matched == 1.0
