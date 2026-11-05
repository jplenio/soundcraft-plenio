"""Misheard words in a cover's original lyrics, before the render (owner's rule 2026-10-24: only there - never
lyrics the user wrote, never a generated song's). Transcribe Lyrics writes what the lyrics ASR heard in the
source; a word it misheard would be sung by the cover as heard. The writer model reads the draft, with the words
the ASR was unsure of marked, and names the words it is sure were misheard, each with the word that was most
likely sung. A correction is taken only when it is sure enough (``MIN_SURE`` for a marked word,
``MIN_SURE_CLEAR`` for one the ASR heard clearly), sounds like what was heard (``SOUND_ALIKE``) and has as many
syllables; the Song Sheet lists every correction with the word heard, so the user can take it back.

    lines, words = draft_words(draft, heard_lines)
    prompt = check_prompt(lines, words, language, song)
    fixes, refused = parse_answer(answer, lines, words, language)
    fixed = corrected(draft, fixes)

Pure: no model, no files.
"""

from __future__ import annotations

import difflib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from . import subtitles as sub
from .syllables import count_word

MIN_SURE = 0.8
"""How sure the writer must be that a word the ASR marked unsure was misheard (0 to 1)."""
MIN_SURE_CLEAR = 0.9
"""How sure for a word the ASR heard clearly: such a word is misheard less often."""
LOW_CONFIDENCE = 0.5
"""A heard word below this probability is marked unsure (``alignment.LOW_CONFIDENCE``)."""
SOUND_ALIKE = 0.6
"""How alike a correction must sound to the words heard (0 to 1, the letters compared): a misheard word sounds
like the sung one; a word that fits better but sounds otherwise is a rewrite, not a correction. Measured with
Gemma 4 E4B on 20 of the owner's songs: at 0.5 it also took *it* -> *this* and *not* -> *and*; at 0.6 the
corrections taken were misheard words (*Zingway* -> *Sing way*, *in'cause* -> *because*, *willing down* ->
*feeling down*)."""
MAX_HEARD = 4
"""Words in a row one correction may replace."""
CJK_SHARE = 0.3
"""A draft with this share of Chinese or Japanese characters is not checked: a misheard character cannot be told
by its letters, and in the measurement the writer swapped characters at will (*tears* -> *bitter cold*)."""
MAX_LINES = 200
SCHEMA_VERSION = "plenio.heard_check/1"
ANSWER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "fixes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "line": {"type": "integer"},
                    "heard": {"type": "string"},
                    "word": {"type": "string"},
                    "sure": {"type": "number"},
                },
                "required": ["line", "heard", "word", "sure"],
            },
        }
    },
    "required": ["fixes"],
}


@dataclass(frozen=True)
class Word:
    """A word of the draft's sung lines."""

    line: int
    """The sung line (0-based)."""
    start: int
    end: int
    """Where it is in the line."""
    text: str
    unsure: bool = False
    """The ASR heard it with a probability below ``LOW_CONFIDENCE``."""


@dataclass(frozen=True)
class Fix:
    line: int
    start: int
    end: int
    """The words' place in the line."""
    heard: str
    word: str
    sure: float
    unsure: bool

    def to_record(self) -> dict[str, Any]:
        return {
            "line": self.line + 1,
            "heard": self.heard,
            "word": self.word,
            "sure": round(self.sure, 2),
            "unsure": self.unsure,
        }


def not_checked(draft: str) -> str:
    """Why a draft is not checked at all (``""``: it is)."""
    rows = (draft or "").split("\n")
    letters = [c for n in sung_rows(draft) for c in rows[n] if c.isalpha()]
    if not letters:
        return "the draft has no sung words"
    if sum(1 for c in letters if sub._CJK_CHAR.match(c)) >= CJK_SHARE * len(letters):
        return "Chinese and Japanese lyrics are not checked (a misheard character cannot be told by its sound here)"
    return ""


def is_sung(row: str) -> bool:
    """A row of the draft that is sung: not a section tag, a direction or empty."""
    return bool(sub.normalize(row)) and not sub._DIRECTION.match(row)


def sung_rows(draft: str) -> list[int]:
    """The draft's rows (by index in ``draft.split("\\n")``) that are sung lines, in order."""
    return [n for n, row in enumerate((draft or "").split("\n")) if is_sung(row)]


def _joined(tokens: Sequence[str]) -> str:
    """The line ``alignment.join_tokens`` makes of heard words: a word starting with '-' or an apostrophe
    attaches to the one before."""
    out = ""
    for token in tokens:
        if out and not token.startswith(("-", "'")):
            out += " "
        out += token
    return out


def _spans(tokens: Sequence[str]) -> list[tuple[int, int]]:
    """Where each heard word stands in the line ``_joined`` makes of them."""
    spans, at = [], 0
    for k, token in enumerate(tokens):
        if k and not token.startswith(("-", "'")):
            at += 1
        spans.append((at, at + len(token)))
        at += len(token)
    return spans


def draft_words(
    draft: str, heard_lines: Sequence[Sequence[Sequence[Any]]] | None = None
) -> tuple[list[str], list[Word]]:
    """The draft's sung lines and their words. ``heard_lines`` - the heard words of the draft's lines in order,
    each as ``[word, p]``, as Transcribe Lyrics reports them - marks the words heard below ``LOW_CONFIDENCE``; a
    line no heard line makes (the draft was changed) has none marked."""
    rows = (draft or "").split("\n")
    lines = [rows[n] for n in sung_rows(draft)]
    heard_rows = [list(line) for line in heard_lines or ()]
    words: list[Word] = []
    at = 0
    for n, text in enumerate(lines):
        low: list[tuple[int, int]] = []
        for k in range(at, len(heard_rows)):
            tokens = [str(item[0]) for item in heard_rows[k]]
            if _joined(tokens) == text:
                low = [
                    s
                    for s, item in zip(_spans(tokens), heard_rows[k], strict=True)
                    if float(item[1]) < LOW_CONFIDENCE
                ]
                at = k + 1
                break
        for m in sub._TOKEN.finditer(text):
            if not sub.normalize(m.group(0)):
                continue
            unsure = any(a < m.end() and m.start() < z for a, z in low)
            words.append(Word(n, m.start(), m.end(), m.group(0), unsure))
    return lines, words


def check_prompt(lines: Sequence[str], words: Sequence[Word], language: str = "", song: str = "") -> str:
    """The question for the writer model: the lyrics as heard, numbered, the unsure words in brackets."""
    marked = {(w.line, w.start): w for w in words if w.unsure}
    rows = []
    for n, text in enumerate(lines[:MAX_LINES]):
        out, at = "", 0
        for (line, start), w in sorted(marked.items()):
            if line == n and start >= at:
                out += text[at:start] + f"[{w.text}]"
                at = w.end
        rows.append(f"{n + 1}: {out + text[at:]}")
    song_line = f' of a recording called "{song}"' if song else ""
    language_line = f" The song is sung in {language}." if language else ""
    return (
        f"A speech recognizer wrote down the lyrics{song_line}.{language_line} It sometimes mishears a sung "
        "word as another one that sounds alike, so a line can contain a word that makes no sense there. The words "
        "in [brackets] are those the recognizer was unsure of.\n\n"
        "The lyrics as heard:\n" + "\n".join(rows) + "\n\n"
        "Find the words that were most likely MISHEARD and give what was most likely sung: it must fit the line's "
        "meaning and grammar, sound like what was heard and have the same number of syllables. Change nothing "
        "else - words that make sense as heard stay, also unusual ones, names, slang, repetitions and ad-libs. "
        "Do not improve or rewrite the lyrics.\n\n"
        'Answer with JSON only: {"fixes": [{"line": 4, "heard": "doun", "word": "down", "sure": 0.9}]} - '
        '"line" is the number before the line, "heard" the word (or the few words in a row) exactly as it stands '
        'in that line, "word" what replaces it, "sure" how likely it was misheard (0 to 1). List only what you '
        f"are sure of: a word in brackets {MIN_SURE} or more, any other {MIN_SURE_CLEAR} or more. None: "
        '{"fixes": []}.'
    )


def _json(text: str) -> Any:
    clean = re.sub(r"<think>.*?</think>", "", text or "", flags=re.DOTALL)
    start, end = clean.find("{"), clean.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(clean[start : end + 1])
    except ValueError:
        return None


def syllables(text: str, language: str = "") -> int:
    """Syllables of a word or a few words: a Chinese or Japanese character is one."""
    cjk = len(sub._CJK_CHAR.findall(text))
    rest = sub._CJK_CHAR.sub(" ", text)
    return cjk + sum(count_word(w, language) for w in re.findall(r"[^\W\d_][\w'’-]*", rest))


_DOUBLE = re.compile(r"(.)\1+")


def sound(text: str) -> str:
    """The letters as a misheard word shares them: case, accents, spaces and doubled letters folded."""
    letters = "".join(c for c in sub.normalize(text) if not c.isdigit())
    return _DOUBLE.sub(r"\1", letters)


def alike(heard: str, word: str) -> float:
    """How alike two words sound, 0 to 1: their letters, and their consonants alone (vowels are what a
    recognizer confuses most)."""
    a, b = sound(heard), sound(word)
    if not a or not b:
        return 0.0
    whole = difflib.SequenceMatcher(a=a, b=b).ratio()
    vowels = re.compile(r"[aeiouyäöüàáâèéêìíîòóôùúûæøå]")
    ca, cb = vowels.sub("", a), vowels.sub("", b)
    skeleton = difflib.SequenceMatcher(a=ca, b=cb).ratio() if ca and cb else 0.0
    return max(whole, skeleton)


def _find(words_in_line: Sequence[Word], heard: str, used: set[tuple[int, int]]) -> list[Word] | None:
    """The first run of words in a line that reads ``heard`` (folded), not taken yet."""
    wanted = [sub.normalize(t) for t in sub._TOKEN.findall(heard) if sub.normalize(t)]
    if not wanted or len(wanted) > MAX_HEARD:
        return None
    for i in range(len(words_in_line) - len(wanted) + 1):
        run = list(words_in_line[i : i + len(wanted)])
        if [sub.normalize(w.text) for w in run] == wanted and not any((w.line, w.start) in used for w in run):
            return run
    return None


def _changed(run: list[Word], word: str) -> tuple[list[Word], str]:
    """The words a correction really changes, and what replaces them: the words it keeps at either end are left
    out (*I'm not the only* -> *We're not the only* changes *I'm* to *We're*)."""
    new = word.split()
    while run and new and sub.normalize(run[0].text) == sub.normalize(new[0]):
        run, new = run[1:], new[1:]
    while run and new and sub.normalize(run[-1].text) == sub.normalize(new[-1]):
        run, new = run[:-1], new[:-1]
    return run, " ".join(new)


_TWICE = re.compile(r"\b(\w+)[\s,]+\1\b", re.IGNORECASE)


def parse_answer(
    answer: str, lines: Sequence[str], words: Sequence[Word], language: str = ""
) -> tuple[list[Fix], list[str]]:
    """The fixes the writer named that hold, and why the others were not taken."""
    data = _json(answer)
    if not isinstance(data, Mapping) or not isinstance(data.get("fixes"), list):
        return [], ["the writer's answer had no fixes list"]
    by_line: dict[int, list[Word]] = {}
    for w in words:
        by_line.setdefault(w.line, []).append(w)
    fixes: list[Fix] = []
    refused: list[str] = []
    used: set[tuple[int, int]] = set()
    for item in data["fixes"]:
        if not isinstance(item, Mapping):
            continue
        try:
            line = int(item.get("line", 0)) - 1
            sure = float(item.get("sure", 0))
        except (TypeError, ValueError):
            continue
        heard, word = str(item.get("heard", "")).strip(), str(item.get("word", "")).strip()
        run = _find(by_line.get(line, []), heard, used)
        if run is None:
            refused.append(f"'{heard}' (line {line + 1}) is not in that line")
            continue
        text = lines[line]
        if not word or not re.fullmatch(r"[^\W\d_][\w'’ -]*", word):
            refused.append(f"'{heard}' -> '{word}' (line {line + 1}): not a word")
            continue
        span, word = _changed(run, word)
        if not span or not word:
            if span or word:
                refused.append(f"'{heard}' -> '{word}' (line {line + 1}): adds or drops words")
            continue
        first, last = span[0], span[-1]
        unsure = any(w.unsure for w in span)
        was = text[first.start : last.end]
        if sure < (MIN_SURE if unsure else MIN_SURE_CLEAR):
            continue  # not sure enough: it stays as heard
        if len(word.split()) > len(span) + 2:
            refused.append(f"'{was}' -> '{word}' (line {line + 1}): not a word")
        elif syllables(word, language) != syllables(was, language):
            refused.append(
                f"'{was}' -> '{word}' (line {line + 1}): {syllables(word, language)} syllables, "
                f"{syllables(was, language)} heard"
            )
        elif alike(was, word) < SOUND_ALIKE:
            refused.append(f"'{was}' -> '{word}' (line {line + 1}): does not sound like what was heard")
        elif _doubles(text, first.start, last.end, word):
            refused.append(f"'{was}' -> '{word}' (line {line + 1}): a word twice in a row")
        else:
            used.update((w.line, w.start) for w in span)
            fixes.append(Fix(line, first.start, last.end, was, _cased(was, word), sure, unsure))
    return fixes, refused


def _cased(heard: str, word: str) -> str:
    """The correction with the heard word's capital at the start of a line kept."""
    if heard[:1].isupper() and word[:1].islower():
        return word[:1].upper() + word[1:]
    return word


def _doubles(line: str, start: int, end: int, word: str) -> bool:
    """A correction that puts a word twice in a row where the line had none."""
    after = line[:start] + word + line[end:]
    return bool(_TWICE.search(after)) and not _TWICE.search(line)


def corrected(draft: str, fixes: Sequence[Fix]) -> str:
    """The draft with the fixes in its sung lines (everything else - tags, blank lines - as it was)."""
    rows = (draft or "").split("\n")
    where = sung_rows(draft)
    for fix in sorted(fixes, key=lambda f: (f.line, -f.start)):  # from a line's end: the places before stay
        if 0 <= fix.line < len(where):
            n = where[fix.line]
            rows[n] = rows[n][: fix.start] + fix.word + rows[n][fix.end :]
    return "\n".join(rows)
