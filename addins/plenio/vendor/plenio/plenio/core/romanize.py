"""Heard words in the lyrics' script: lyrics written in Latin letters for a language with a script of its own
(Hindi as Hinglish, Korean, Japanese in romaji, Russian, Greek) are heard by the lyrics ASR in that script.

Owner's report 2026-10-24: two Bollywood songs written in romanized Hindi had "completely different" sung
lyrics - the takes sang every line, but Qwen3-ASR wrote them in Devanagari, so not one heard word paired
with a lyrics word (heard 0 %, as many words "extra"). Here the heard words are written in Latin letters the
way such lyrics are usually spelled (an inherent vowel kept inside a Hindi word, dropped at its end), and
both sides are compared in a looser spelling (``fold``: long vowels, aspiration and w/v as one).

Supported: Devanagari, Hangul, Hiragana and Katakana, Cyrillic, Greek. Chinese characters (and the kanji of
Japanese) need a dictionary and stay as heard. Pure; no model.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import replace
from typing import TypeVar

from .alignment import AsrWord

W = TypeVar("W", bound=AsrWord)

# --- Devanagari (Hindi, Marathi, Nepali): spelled as Hinglish is usually written -------------------------

_DEVA_CONSONANTS = {
    "क": "k",
    "ख": "kh",
    "ग": "g",
    "घ": "gh",
    "ङ": "n",
    "च": "ch",
    "छ": "chh",
    "ज": "j",
    "झ": "jh",
    "ञ": "n",
    "ट": "t",
    "ठ": "th",
    "ड": "d",
    "ढ": "dh",
    "ण": "n",
    "त": "t",
    "थ": "th",
    "द": "d",
    "ध": "dh",
    "न": "n",
    "प": "p",
    "फ": "ph",
    "ब": "b",
    "भ": "bh",
    "म": "m",
    "य": "y",
    "र": "r",
    "ल": "l",
    "ळ": "l",
    "व": "v",
    "श": "sh",
    "ष": "sh",
    "स": "s",
    "ह": "h",
    "क़": "q",
    "ख़": "kh",
    "ग़": "gh",
    "ज़": "z",
    "ड़": "r",
    "ढ़": "rh",
    "फ़": "f",
    "य़": "y",
}
_DEVA_VOWELS = {
    "अ": "a",
    "आ": "aa",
    "इ": "i",
    "ई": "ee",
    "उ": "u",
    "ऊ": "oo",
    "ऋ": "ri",
    "ए": "e",
    "ऐ": "ai",
    "ओ": "o",
    "औ": "au",
    "ऑ": "o",
    "ऍ": "e",
}
_DEVA_SIGNS = {
    "ा": "aa",
    "ि": "i",
    "ी": "ee",
    "ु": "u",
    "ू": "oo",
    "ृ": "ri",
    "े": "e",
    "ै": "ai",
    "ो": "o",
    "ौ": "au",
    "ॉ": "o",
    "ॅ": "e",
}
_VIRAMA, _NUKTA, _ANUSVARA, _CHANDRABINDU, _VISARGA = "्", "़", "ं", "ँ", "ः"
_LABIALS = set("पफबभम")


def _devanagari(word: str) -> str:
    text = unicodedata.normalize("NFC", word)
    out: list[str] = []
    i = 0
    while i < len(text):
        ch = text[i]
        if i + 1 < len(text) and text[i + 1] == _NUKTA:
            ch += _NUKTA
            i += 1
        nxt = text[i + 1] if i + 1 < len(text) else ""
        if ch in _DEVA_CONSONANTS:
            out.append(_DEVA_CONSONANTS[ch])
            if nxt in _DEVA_SIGNS:
                out.append(_DEVA_SIGNS[nxt])
                i += 1
            elif nxt == _VIRAMA:
                i += 1
            else:
                out.append("a")  # the inherent vowel (dropped at the word's end below)
        elif ch in _DEVA_VOWELS:
            out.append(_DEVA_VOWELS[ch])
        elif ch in (_ANUSVARA, _CHANDRABINDU):
            out.append("m" if nxt in _LABIALS else "n")
        elif ch == _VISARGA:
            out.append("h")
        elif not ("ऀ" <= ch <= "ॿ"):
            out.append(ch)
        i += 1
    result = "".join(out)
    # schwa deletion at the word's end: नज़र -> nazar, not nazara (a long aa stays)
    if (
        len(result) > 2
        and result.endswith("a")
        and not result.endswith("aa")
        and text[-1] in _DEVA_CONSONANTS
    ):
        result = result[:-1]
    return result


# --- Hangul (Revised Romanization) -----------------------------------------------------------------------

_INITIALS = [
    "g",
    "kk",
    "n",
    "d",
    "tt",
    "r",
    "m",
    "b",
    "pp",
    "s",
    "ss",
    "",
    "j",
    "jj",
    "ch",
    "k",
    "t",
    "p",
    "h",
]
_MEDIALS = [
    "a",
    "ae",
    "ya",
    "yae",
    "eo",
    "e",
    "yeo",
    "ye",
    "o",
    "wa",
    "wae",
    "oe",
    "yo",
    "u",
    "wo",
    "we",
    "wi",
    "yu",
    "eu",
    "ui",
    "i",
]
_FINALS = [
    "",
    "k",
    "k",
    "k",
    "n",
    "n",
    "n",
    "t",
    "l",
    "k",
    "m",
    "l",
    "l",
    "l",
    "p",
    "l",
    "m",
    "p",
    "p",
    "t",
    "t",
    "ng",
    "t",
    "t",
    "k",
    "t",
    "p",
    "t",
]


def _hangul(word: str) -> str:
    out: list[str] = []
    for ch in word:
        code = ord(ch) - 0xAC00
        if 0 <= code < 11172:
            out.append(_INITIALS[code // 588] + _MEDIALS[(code % 588) // 28] + _FINALS[code % 28])
        else:
            out.append(ch)
    return "".join(out)


# --- Kana (Hepburn) ----------------------------------------------------------------------------------------

_KANA = dict(
    zip(
        "あいうえおかきくけこさしすせそたちつてとなにぬねのはひふへほまみむめもやゆよらりるれろわをんがぎぐげござじずぜぞだぢづでどばびぶべぼぱぴぷぺぽぁぃぅぇぉゃゅょゎ",
        "a i u e o ka ki ku ke ko sa shi su se so ta chi tsu te to na ni nu ne no ha hi fu he ho ma mi mu me mo "
        "ya yu yo ra ri ru re ro wa o n ga gi gu ge go za ji zu ze zo da ji zu de do ba bi bu be bo pa pi pu pe po "
        "a i u e o ya yu yo wa".split(),
        strict=True,
    )
)


def _kana(word: str) -> str:
    # katakana as hiragana (the same sounds)
    text = "".join(chr(ord(ch) - 0x60) if "ァ" <= ch <= "ヶ" else ch for ch in word)
    out: list[str] = []
    double = False
    for ch in text:
        if ch in "っッ":
            double = True
            continue
        if ch == "ー":
            if out:
                out.append(out[-1][-1])
            continue
        piece = _KANA.get(ch, ch)
        if ch in "ゃゅょ" and out and out[-1].endswith("i") and len(out[-1]) > 1:
            stem = out.pop()[:-1]
            piece = (stem if stem in ("sh", "ch", "j") else stem + "y") + piece[1:]
        if double and piece and piece[0].isalpha():
            piece = piece[0] + piece
        double = False
        out.append(piece)
    return "".join(out)


# --- Cyrillic and Greek ------------------------------------------------------------------------------------

_CYRILLIC = dict(
    zip(
        "абвгдеёжзийклмнопрстуфхцчшщъыьэюяіїєґ",
        "a b v g d e yo zh z i y k l m n o p r s t u f kh ts ch sh shch _ y _ e yu ya i yi ye g".split(),
        strict=True,
    )
)
_GREEK = dict(
    zip(
        "αβγδεζηθικλμνξοπρσςτυφχψωάέήίόύώϊϋΐΰ",
        "a v g d e z i th i k l m n x o p r s s t y f ch ps o a e i i o y o i y i y".split(),
        strict=True,
    )
)


def _letters(word: str, table: dict[str, str]) -> str:
    out = []
    for ch in word:
        piece = table.get(ch.lower())
        if piece is None:
            out.append(ch)
        elif piece != "_":
            out.append(piece.capitalize() if ch.isupper() else piece)
    return "".join(out)


_SCRIPTS = (
    ("devanagari", re.compile("[ऀ-ॿ]"), _devanagari),
    ("hangul", re.compile("[가-힣]"), _hangul),
    ("kana", re.compile("[ぁ-ゖァ-ー]"), _kana),
    ("cyrillic", re.compile("[Ѐ-ӿ]"), lambda w: _letters(w, _CYRILLIC)),
    ("greek", re.compile("[Ͱ-Ͽ]"), lambda w: _letters(w, _GREEK)),
)
_LATIN = re.compile(r"[A-Za-zÀ-ɏ]")
_LETTER = re.compile(r"[^\W\d_]")


def script(text: str) -> str:
    """The script more than half of ``text``'s letters are in: ``latin``, one of ``_SCRIPTS``' names, ``other``
    (Chinese, Arabic ...); ``mixed`` when none has the majority (Japanese: kanji and kana), ``none``."""
    counts: dict[str, int] = {}
    for ch in text:
        if not _LETTER.match(ch):
            continue
        name = (
            "latin"
            if _LATIN.match(ch)
            else next((n for n, pattern, _f in _SCRIPTS if pattern.match(ch)), "other")
        )
        counts[name] = counts.get(name, 0) + 1
    if not counts:
        return "none"
    best = max(counts, key=lambda name: counts[name])
    return best if 2 * counts[best] > sum(counts.values()) else "mixed"


def romanize(word: str) -> str:
    """``word`` in Latin letters, as far as its script is supported (else as it is)."""
    for _name, pattern, convert in _SCRIPTS:
        if pattern.search(word):
            return convert(word)
    return word


def in_lyrics_script(lyrics: str, heard: Sequence[W]) -> tuple[list[W], bool]:
    """The heard words in Latin letters when the lyrics are written in Latin letters but most heard letters
    are in a supported script of their own; ``(words, romanized)``. The section tags do not count: Japanese
    lyrics with ``[Verse]`` tags are not Latin."""
    if script(re.sub(r"\[[^\]]*\]", " ", lyrics)) != "latin":
        return list(heard), False
    found = script(" ".join(w.word for w in heard))
    if found not in {name for name, _p, _f in _SCRIPTS}:
        return list(heard), False
    return [replace(w, word=romanize(w.word)) for w in heard], True


_FOLDS = (
    (re.compile(r"([bcdgjkptsz])h"), r"\1"),  # aspiration: bhari / bari, khwab / kwab, sh / s
    (re.compile(r"aa+"), "a"),
    (re.compile(r"(ee|ii|y(?=$))"), "i"),
    (re.compile(r"(oo|uu)"), "u"),
    (re.compile(r"(ai|ei|ay)"), "e"),
    (re.compile(r"(au|ou|ow)"), "o"),
    (re.compile(r"w"), "v"),
    (re.compile(r"z"), "j"),
    (re.compile(r"q"), "k"),
    (re.compile(r"f"), "p"),
    (re.compile(r"(.)\1+"), r"\1"),
)


def fold(word: str) -> str:
    """A normalized word in a looser spelling, for comparing romanized words: ``raasta`` and ``rasta``,
    ``nazar`` and ``najar``, ``mein`` and ``men`` become one."""
    for pattern, repl in _FOLDS:
        word = pattern.sub(repl, word)
    return word
