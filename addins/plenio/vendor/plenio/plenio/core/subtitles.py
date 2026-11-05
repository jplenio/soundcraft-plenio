"""Lyrics subtitles (SRT): when each line and each syllable is sung, measured by listening (owner's request
2026-10-15, ``docs/design/subtitles-tags-seeds.md``).

A YuE2 render is shifted against its score (1.7 s in the median song, up to 15 s), so the score's note
times alone are no subtitles. The times are **heard**: the lyrics ASR transcribes the song, its words are
matched to the lyrics, and - with a score - the score is fitted to the heard words and gives every syllable
its note. Since 2026-10-22 the ASR is Qwen3-ASR and **Qwen3-ForcedAligner** times the heard words - the
aligner was the reference of the measurement below, so its times are used as they are (``ALIGNED``) - in
pieces of at most 20 s: over a whole song it loses its place (``workers.asr.PIECE_S``, 2026-10-23).
faster-whisper, the fallback for languages the aligner does not know, starts its words early; its times
get the corrections measured against the aligner on 48 YuE2 songs no choice was made on (``WHISPER``):
median error 0.16 s per word, 82 % within 0.5 s (Whisper alone: 0.34 s, 66 %).

Two files: whole lines (``lines_srt``), and the lines painted on note by note (``notes_srt``: a cue per
syllable or word, showing the line up to what is being sung). SRT styling is not portable (YouTube reads no
markup, DaVinci Resolve has shown tags as text), so nothing here uses tags.

Pure functions; no audio, no model.
"""

from __future__ import annotations

import bisect
import difflib
import re
import statistics
import unicodedata
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from . import lyrics as lyrics_rules
from .alignment import LINE_GAP_S, AsrWord, drop_known_inventions, join_tokens
from .romanize import fold

LEAD_S = 0.3
"""Whisper's word starts come early (0.26 s in the median word, its words being contiguous): added to every
heard start."""
FIRST_WORD_MAX_S = 0.5
"""A line's first word takes the rest before it in Whisper's times (0.7 s early in the median): it starts at
most this long before its end."""
AGREE_S = 0.35
"""The score's time is kept where it is this close to the heard one; farther, the heard time wins."""
SHIFT_SPREAD_S = 0.35
"""A line is shifted by its words' median offset only when they agree within this (median deviation)."""
MAX_SHIFT_S = 6.0
MATCH_SIMILARITY = 0.7
"""How alike a lyrics word and a heard word must be to pair them (``difflib`` ratio)."""
LINE_TAIL_S = 0.25
"""A line's cue stays this long after its last word ends, never into the next line."""
MIN_CUE_S = 0.8
GAP_S = 0.04
"""The least time between two cues."""
WORD_S = 0.3
"""The time a word not heard is given at the edge of a line (between heard words: by letters)."""
WRAP = 42
"""Characters per subtitle row (the common limit); a longer line takes two rows."""
MIN_HEARD_WORDS = 5
"""Without lyrics: fewer heard words than this are no singing (an instrumental's stray ASR words)."""


@dataclass(frozen=True)
class HeardTiming:
    """How heard word starts are corrected before they are used."""

    lead_s: float
    """Added to every heard start."""
    first_word_max_s: float | None
    """A line's first word starts at most this long before its end (``None``: as heard)."""
    stretched_s: float | None = None
    """A line's first word heard more than this before the line's next word (or this long, when the next is not
    heard) took the music before it: its start is not used - the score's time, else the next word's (``None``:
    as heard)."""


STRETCHED_S = 2.0
"""Qwen3-ForcedAligner lets the first word of a piece take the music before it, or puts it at the piece's
start (an export of 2026-10-23: the song's first "I" from 0.0 to 12.0 s, its note at 12.2 s; a "This" at
45.2 s, the rest of its line from 57.9 s). Measured on 20 of the owner's songs: lines starting on voice 95.0 ->
96.9 %, line time on voice 87.6 -> 90.3 %; within a point the same from 1.5 to 4 s."""
WHISPER = HeardTiming(LEAD_S, FIRST_WORD_MAX_S)
ALIGNED = HeardTiming(0.0, None, STRETCHED_S)
"""A forced aligner's times are the measurement's reference: used as they are - but a stretched first word."""


def _stretched(word: AsrWord, after: AsrWord | None, timing: HeardTiming) -> bool:
    """Whether a line's first word took the music before it (``HeardTiming.stretched_s``)."""
    if timing.stretched_s is None:
        return False
    reach = after.start - word.start if after is not None else word.end - word.start
    return reach > timing.stretched_s


def _first_start(word: AsrWord, after: AsrWord | None, timing: HeardTiming) -> float:
    """Where a line made of heard words starts: its first word's start, corrected (``timing``) - a stretched
    first word starts ``WORD_S`` before the next word (or its own end)."""
    start, end = word.start, word.end
    if _stretched(word, after, timing):
        return max(start, (after.start if after is not None else end) - WORD_S)
    cap = timing.first_word_max_s
    return end - cap if cap is not None and end - start > cap else start


def timing_for(engine: str) -> HeardTiming:
    """The timing correction of an ASR engine id (``AsrResult.engine``)."""
    return WHISPER if engine.startswith("faster-whisper") else ALIGNED


_DIRECTION = re.compile(r"^\s*[\(\[\{<].*[\)\]\}>]\s*$")
_CJK = "\u3040-\u30ff\u31f0-\u31ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uff66-\uff9f"
"""Kana and Han: Chinese and Japanese write no spaces between words, so every such character is a token."""
_TOKEN = re.compile(rf"[{_CJK}][^\s\w{_CJK}]*|[^\s{_CJK}]+")
"""A word - or one Chinese or Japanese character, with the punctuation after it (the owner's songs in Chinese
and Japanese: a whole phrase was one word, and almost nothing of their lyrics was matched to what was heard)."""
_CJK_CHAR = re.compile(f"[{_CJK}]")
_APOSTROPHES = str.maketrans({"’": "'", "‘": "'", "`": "'", "´": "'"})


def split_cjk(words: Sequence[AsrWord]) -> list[AsrWord]:
    """Heard words cut into the lyrics' tokens: a word of several Chinese or Japanese characters (Whisper
    hears them so) becomes one word per character, its time shared out evenly."""
    out: list[AsrWord] = []
    for word in words:
        parts = [m.group(0) for m in _TOKEN.finditer(word.word)]
        if len(parts) <= 1:
            out.append(word)
            continue
        step = (word.end - word.start) / len(parts)
        out += [
            AsrWord(word.start + k * step, word.start + (k + 1) * step, part, word.p, word.segment)
            for k, part in enumerate(parts)
        ]
    return out


def join_words(tokens: Sequence[str]) -> str:
    """Tokens as a line: ``alignment.join_tokens``, with no space next to a Chinese or Japanese character."""
    out = ""
    for token in tokens:
        if out and (_CJK_CHAR.match(token) or _CJK_CHAR.match(out[-1])):
            out += token
        else:
            out = join_tokens([out, token]) if out else token
    return out


def normalize(word: str) -> str:
    """A word as the matching compares it: case, apostrophes, hyphens and punctuation folded."""
    text = unicodedata.normalize("NFKC", word).translate(_APOSTROPHES).lower()
    return re.sub(r"[\W_]+", "", text)


@dataclass(frozen=True)
class Unit:
    """What a cue of the notes file adds: from ``start`` the line is shown up to character ``cut``."""

    start: float
    cut: int
    score: float | None = None
    """Where the syllable's note is in the score (seconds at the score's tempo); ``None`` without a score."""


@dataclass(frozen=True)
class TimedLine:
    text: str
    start: float
    end: float
    units: tuple[Unit, ...]


@dataclass(frozen=True)
class Subtitles:
    lines: tuple[TimedLine, ...]
    timing: str
    """``measured``: the lyrics, timed by listening; ``heard``: no lyrics given - what was heard; ``estimated``:
    the score's times carried into the recording (``time_by_score``, the Plenio Player's guess); ``sung``: what
    a take sings, as heard, laid out like its lyrics (``time_sung``)."""
    untimed: tuple[str, ...] = ()
    """Lyrics lines left out: nothing of them was heard and there was no room for them."""
    matched: float = 0.0
    """The share of the lyrics' words that were heard."""
    notes: tuple[str, ...] = field(default=())
    warp: tuple[float, float] | None = None
    """``(a, b)``: the song against its score, ``t_audio = a * t_score + b`` (``None`` without a score)."""

    def lines_srt(self) -> str:
        return srt([(line.start, line.end, wrapped(line.text)) for line in self.lines])

    def notes_srt(self) -> str:
        cues: list[tuple[float, float, str]] = []
        for line in self.lines:
            units = [
                u
                for k, u in enumerate(line.units)
                if k + 1 == len(line.units) or line.units[k + 1].start > u.start
            ]
            for k, unit in enumerate(units):
                end = units[k + 1].start if k + 1 < len(units) else line.end
                if end - unit.start >= GAP_S:
                    cues.append((unit.start, end, wrapped(line.text, unit.cut)))
        return srt(cues)

    def to_timing(self, take: str = "") -> dict[str, Any]:
        """The times for the release record (the Plenio Player): every line with its units ``[start, cut]``
        - ``[start, cut, score]`` where the syllable has a note - and the warp against the score."""

        def unit(u: Unit) -> list[float | int]:
            return [round(u.start, 3), u.cut] + ([round(u.score, 3)] if u.score is not None else [])

        return {
            "take": take.strip(),
            "timing": self.timing,
            "warp": [round(self.warp[0], 4), round(self.warp[1], 3)] if self.warp else None,
            "lines": [
                {
                    "text": line.text,
                    "start": round(line.start, 3),
                    "end": round(line.end, 3),
                    "units": [unit(u) for u in line.units],
                }
                for line in self.lines
            ],
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "timing": self.timing,
            "lines": len(self.lines),
            "untimed": list(self.untimed),
            "matched": round(self.matched, 3),
        }


# --- the SRT text ---------------------------------------------------------------------------


def srt_time(seconds: float) -> str:
    millis = max(0, round(seconds * 1000))
    hours, rest = divmod(millis, 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    secs, millis = divmod(rest, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def srt(cues: Iterable[tuple[float, float, str]]) -> str:
    blocks = [
        f"{index}\n{srt_time(start)} --> {srt_time(end)}\n{text}"
        for index, (start, end, text) in enumerate(cues, start=1)
    ]
    return "\n\n".join(blocks) + "\n" if blocks else ""


def wrap_at(text: str) -> int | None:
    """Where a line longer than ``WRAP`` breaks into two rows: the space nearest the middle, one after a
    comma or full stop preferred (``None``: one row)."""
    if len(text) <= WRAP:
        return None
    spaces = [m.start() for m in re.finditer(r" ", text)]
    if not spaces:
        return None
    middle = len(text) / 2

    def cost(index: int) -> float:
        rows = max(index, len(text) - index - 1)
        return abs(index - middle) - (10 if text[index - 1] in ",;:.!?" else 0) + (50 if rows > WRAP else 0)

    return min(spaces, key=cost)


def wrapped(text: str, cut: int | None = None) -> str:
    """``text`` up to ``cut`` in its rows; the break is chosen for the whole line, so a growing line never
    jumps between rows."""
    shown = text if cut is None else text[:cut]
    split = wrap_at(text)
    if split is None or len(shown) <= split:
        return shown.rstrip()
    return shown[:split].rstrip() + "\n" + shown[split + 1 :].lstrip()


# --- the lyrics ------------------------------------------------------------------------------


@dataclass(frozen=True)
class LyricLine:
    block: int
    line: int
    text: str
    tokens: tuple[tuple[int, int], ...]
    """``(start, end)`` of every word in ``text``."""
    words: tuple[str, ...]
    """The normalised words (empty for a token without letters, which is never matched)."""


def sung_lines(text: str) -> list[LyricLine]:
    """The lyrics' sung lines in order (section tags and directions left out). ``block``/``line`` index
    ``lyrics.parse_lyrics``'s sections as the score's lyric layout does; lines before any tag are block -1."""
    parsed = lyrics_rules.parse_lyrics(text or "")
    blocks: list[tuple[int, Sequence[str]]] = [(-1, parsed.preamble)] if parsed.preamble else []
    blocks += [(b, section.lines) for b, section in enumerate(parsed.sections)]
    found = []
    for b, lines in blocks:
        for j, line in enumerate(lines):
            if _DIRECTION.match(line) or not normalize(line):
                continue
            tokens = tuple((m.start(), m.end()) for m in _TOKEN.finditer(line))
            found.append(LyricLine(b, j, line, tokens, tuple(normalize(line[a:z]) for a, z in tokens)))
    return found


def plain_lyrics(text: str) -> str:
    """The lyrics as players show them: the sung lines, a blank line between sections; tags and directions
    left out."""
    stanzas: list[list[str]] = []
    current = None
    for line in sung_lines(text):
        if line.block != current:
            stanzas.append([])
            current = line.block
        stanzas[-1].append(line.text)
    return "\n\n".join("\n".join(stanza) for stanza in stanzas)


# --- matching and fitting --------------------------------------------------------------------


def match_words(lyric: Sequence[str], heard: Sequence[str]) -> dict[int, int]:
    """Lyrics word index -> heard word index for the words that pair up (Needleman-Wunsch on words: a
    match scores its likeness, a skipped word -0.6)."""
    n, m = len(lyric), len(heard)
    gap = -0.6
    likeness: dict[tuple[str, str], float] = {}

    def like(a: str, b: str) -> float:
        key = (a, b)
        if key not in likeness:
            likeness[key] = 1.0 if a == b else difflib.SequenceMatcher(a=a, b=b).ratio() if a and b else 0.0
        return likeness[key]

    score = [[0.0] * (m + 1) for _ in range(n + 1)]
    back = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        score[i][0], back[i][0] = i * gap, 1
    for j in range(1, m + 1):
        score[0][j], back[0][j] = j * gap, 2
    for i in range(1, n + 1):
        row, above = score[i], score[i - 1]
        for j in range(1, m + 1):
            diagonal = above[j - 1] + 2 * like(lyric[i - 1], heard[j - 1]) - 1
            up, left = above[j] + gap, row[j - 1] + gap
            if diagonal >= up and diagonal >= left:
                row[j], back[i][j] = diagonal, 0
            elif up >= left:
                row[j], back[i][j] = up, 1
            else:
                row[j], back[i][j] = left, 2
    pairs: dict[int, int] = {}
    i, j = n, m
    while i > 0 and j > 0:
        move = back[i][j]
        if move == 0:
            if like(lyric[i - 1], heard[j - 1]) >= MATCH_SIMILARITY:
                pairs[i - 1] = j - 1
            i, j = i - 1, j - 1
        elif move == 1:
            i -= 1
        else:
            j -= 1
    return pairs


def pair_words(lyric: Sequence[str], heard: Sequence[str], *, romanized: bool = False) -> dict[int, int]:
    """``match_words``; words heard in another script and romanized (``romanize.in_lyrics_script``) are
    compared in ``romanize.fold``'s looser spelling - a romanization is one of several spellings."""
    if romanized:
        return match_words([fold(w) for w in lyric], [fold(w) for w in heard])
    return match_words(lyric, heard)


def fit_warp(times: Sequence[float], onsets: Sequence[float]) -> tuple[float, float]:
    """``(a, b)`` with ``t_audio = a * t_score + b``: the warp that puts the heard word starts nearest to the
    score's Vocal onsets (scale 0.92-1.08, shift +-15 s; a grid, then a finer one)."""
    import numpy as np

    marks = np.asarray(sorted(onsets), dtype=float)
    heard = np.asarray(times, dtype=float)
    if len(marks) < 2 or len(heard) < 2:
        return 1.0, 0.0

    def spread(a: float, b: float) -> float:
        x = (heard - b) / a
        i = np.clip(np.searchsorted(marks, x), 1, len(marks) - 1)
        distance = np.minimum(np.abs(x - marks[i - 1]), np.abs(x - marks[i]))
        # a hair towards the smallest shift: a steady rhythm fits as well a beat later or earlier
        return float(np.mean(np.minimum(0.5, distance))) + 0.001 * abs(b) + 0.01 * abs(a - 1)

    coarse = [(1 + da / 100, db / 10) for da in range(-8, 9) for db in range(-150, 151)]
    a0, b0 = min(coarse, key=lambda w: spread(*w))
    fine = [(a0 + da / 1000, b0 + db / 100) for da in range(-10, 11) for db in range(-10, 11)]
    return min(fine, key=lambda w: spread(*w))


def _increasing(times: Mapping[int, float]) -> set[int]:
    """The keys of the longest run of times that never goes backwards (in key order): a word matched to
    another repetition of a chorus falls out."""
    keys = sorted(times)
    tails: list[float] = []
    tail_index: list[int] = []
    previous: list[int] = [-1] * len(keys)
    for position, key in enumerate(keys):
        value = times[key]
        slot = bisect.bisect_right(tails, value)
        if slot == len(tails):
            tails.append(value)
            tail_index.append(position)
        else:
            tails[slot] = value
            tail_index[slot] = position
        previous[position] = tail_index[slot - 1] if slot else -1
    kept: set[int] = set()
    position = tail_index[-1] if tail_index else -1
    while position >= 0:
        kept.add(keys[position])
        position = previous[position]
    return kept


# --- timing ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class ScoreNotes:
    """What the score says about one lyrics line: per word the score time of its first syllable, and the
    syllables (score time, cut in the line's text) - times in seconds at the score's tempo."""

    words: Mapping[int, float]
    syllables: tuple[tuple[float, int], ...]
    end: float | None


def _cuts(text: str, pieces: Sequence[tuple[str, bool]]) -> list[int]:
    """Where each syllable ends in ``text``: after as many letters as the syllables so far hold, and on to the
    end of the word (its punctuation) when the syllable ends a word."""
    letters = [k for k, ch in enumerate(text) if ch.isalnum()]
    cuts: list[int] = []
    count = 0
    for piece, end_of_word in pieces:
        count += sum(1 for ch in piece if ch.isalnum())
        if not letters:
            cuts.append(len(text))
            continue
        cut = letters[min(count, len(letters)) - 1] + 1 if count else 0
        if end_of_word:
            while cut < len(text) and not text[cut].isspace():
                cut += 1
        cuts.append(cut)
    return cuts


def score_notes(score: Any, layout: Any, lines: Sequence[LyricLine]) -> dict[tuple[int, int], ScoreNotes]:
    """Per lyrics line ``(block, line)``: where the score's lyric layout sings it (lines no note sings are
    left out). ``score`` is a ``canonical.Score``, ``layout`` its ``LyricLayout`` of the same lyrics."""
    ends = {note.onset: note.onset + note.duration for note in score.vocal}
    by_key = {(line.block, line.line): line for line in lines}
    found: dict[tuple[int, int], ScoreNotes] = {}
    for placed in layout.lines():
        line = by_key.get((placed.block, placed.line))
        if line is None or not placed.syllables:
            continue
        pieces: list[tuple[str, bool]] = []
        for syllable in placed.syllables:
            # a syllable may hold several words (they share a note)
            parts = syllable.text.split(" ")
            pieces += [(part, k < len(parts) - 1 or syllable.end_of_word) for k, part in enumerate(parts)]
        cuts = _cuts(line.text, pieces)
        times: list[float] = []
        for syllable in placed.syllables:
            times += [score.seconds(syllable.onset)] * len(syllable.text.split(" "))
        # the word of a piece is the one its last letter stands in; the first piece in a word gives its time
        words: dict[int, float] = {}
        starts = [start for start, _end in line.tokens]
        for cut, when in zip(cuts, times, strict=True):
            word = max(0, bisect.bisect_right(starts, max(0, cut - 1)) - 1)
            words.setdefault(word, when)
        last = placed.syllables[-1].onset
        held = max([ends.get(last, last), *(ends.get(h, h) for h in placed.holds)])
        found[(line.block, line.line)] = ScoreNotes(
            words, tuple(zip(times, cuts, strict=True)), score.seconds(held)
        )
    return found


def _heard_starts(
    lines: Sequence[LyricLine], heard: Sequence[AsrWord], pairs: Mapping[int, int], timing: HeardTiming
) -> dict[int, float]:
    first = set()
    index = 0
    for line in lines:
        first.add(index)
        index += len(line.tokens)
    starts = {}
    for word, h in pairs.items():
        start, end = heard[h].start, heard[h].end
        after = heard[pairs[word + 1]] if word + 1 in pairs and word + 1 not in first else None
        if word in first and _stretched(heard[h], after, timing):
            continue  # it took the music before it: the score places it, or the words after it
        cap = timing.first_word_max_s
        if word in first and cap is not None and end - start > cap:
            start = end - cap
        starts[word] = start + timing.lead_s
    return starts


def time_lyrics(
    lyrics: str,
    heard: Sequence[AsrWord],
    *,
    duration: float,
    score: Any = None,
    layout: Any = None,
    timing: HeardTiming = WHISPER,
    romanized: bool = False,
) -> Subtitles:
    """The lyrics' lines with their times, measured from the heard words (and the score's notes when given:
    a ``canonical.Score`` with the ``LyricLayout`` of these lyrics); ``timing`` corrects the heard starts
    (``timing_for`` the engine that heard them); ``romanized``: the heard words were written in the lyrics'
    Latin letters (``romanize.in_lyrics_script``)."""
    lines = sung_lines(lyrics)
    if not lines:
        return Subtitles((), "measured")
    flat = [(n, k) for n, line in enumerate(lines) for k in range(len(line.tokens))]
    lyric_words = [lines[n].words[k] for n, k in flat]
    usable = [w for w in split_cjk(heard) if normalize(w.word)]
    pairs = pair_words(lyric_words, [normalize(w.word) for w in usable], romanized=romanized)
    pairs = {i: j for i, j in pairs.items() if lyric_words[i]}
    heard_at = _heard_starts(lines, usable, pairs, timing)
    times: dict[int, float] = {}
    notes: dict[tuple[int, int], ScoreNotes] = {}
    warp = (1.0, 0.0)
    shifts: dict[int, float] = {}
    if score is not None and layout is not None and score.vocal:
        notes = score_notes(score, layout, lines)
        onsets = [score.seconds(note.onset) for note in score.vocal]
        warp = fit_warp([usable[j].start for j in pairs.values()], onsets)
    a, b = warp
    index = 0
    for n, line in enumerate(lines):
        placed = notes.get((line.block, line.line))
        warped = {index + k: a * t + b for k, t in placed.words.items()} if placed else {}
        offsets = [heard_at[i] - warped[i] for i in warped if i in heard_at and i != index]
        if len(offsets) >= 2:
            middle = statistics.median(offsets)
            if (
                statistics.median(abs(x - middle) for x in offsets) <= SHIFT_SPREAD_S
                and abs(middle) <= MAX_SHIFT_S
            ):
                shifts[n] = middle
        for k in range(len(line.tokens)):
            i = index + k
            on_score = warped[i] + shifts.get(n, 0.0) if i in warped else None
            on_ear = heard_at.get(i)
            if on_score is not None and (on_ear is None or abs(on_score - on_ear) <= AGREE_S):
                times[i] = on_score
            elif on_ear is not None:
                times[i] = on_ear
        index += len(line.tokens)
    # a time that goes backwards is a word paired with another repetition: it is placed between its neighbours
    kept = _increasing(times)
    times = {i: t for i, t in times.items() if i in kept and 0 <= t <= duration}
    timed: list[TimedLine] = []
    untimed: list[str] = []
    index = 0
    starts = _line_starts(lines, times)
    for n, line in enumerate(lines):
        count = len(line.tokens)
        own = {k: times[index + k] for k in range(count) if index + k in times}
        before = timed[-1].end if timed else 0.0
        after = next((s for s in starts[n + 1 :] if s is not None), duration)
        if not own:
            room = after - before - 2 * GAP_S
            if room < max(MIN_CUE_S, 0.2 * count):
                untimed.append(line.text)
                index += count
                continue
            step = min(WORD_S, room / (count + 1))
            own = {k: before + GAP_S + step * (k + 0.5) for k in range(count)}
        word_times = _fill(line, own, before, after)
        placed = notes.get((line.block, line.line))
        units = _units(line, word_times, placed, a)
        start = units[0].start
        end = _line_end(line, word_times, placed, a, b + shifts.get(n, 0.0), usable, pairs, index, timing)
        timed.append(TimedLine(line.text, start, max(end, units[-1].start + 0.2), tuple(units)))
        index += count
    finished = _finish(timed, duration)
    matched = len(pairs) / max(1, sum(1 for w in lyric_words if w))
    return Subtitles(tuple(finished), "measured", tuple(untimed), matched, warp=warp if notes else None)


def _line_starts(lines: Sequence[LyricLine], times: Mapping[int, float]) -> list[float | None]:
    starts: list[float | None] = []
    index = 0
    for line in lines:
        own = [times[index + k] for k in range(len(line.tokens)) if index + k in times]
        starts.append(min(own) if own else None)
        index += len(line.tokens)
    return starts


def _fill(line: LyricLine, own: Mapping[int, float], before: float, after: float) -> list[float]:
    """Every word's time: the heard or scored ones, the others between their neighbours by letters (at the
    edges ``WORD_S`` per word, kept inside the room between the lines)."""
    count = len(line.tokens)
    known = sorted(own)
    result: list[float] = [0.0] * count
    for k in range(count):
        if k in own:
            result[k] = own[k]
            continue
        lower = max((q for q in known if q < k), default=None)
        upper = min((q for q in known if q > k), default=None)
        if lower is not None and upper is not None:
            span = line.tokens[upper][0] - line.tokens[lower][0]
            share = (line.tokens[k][0] - line.tokens[lower][0]) / span if span else 0.5
            result[k] = own[lower] + share * (own[upper] - own[lower])
        elif upper is not None:
            result[k] = max(before + GAP_S, own[upper] - WORD_S * (upper - k))
        elif lower is not None:
            result[k] = min(after - GAP_S, own[lower] + WORD_S * (k - lower))
    for k in range(1, count):
        result[k] = max(result[k], result[k - 1])
    return result


def _units(line: LyricLine, word_times: Sequence[float], placed: ScoreNotes | None, a: float) -> list[Unit]:
    """The cues of the notes file: a syllable per note where the score sings the line (the syllables after a
    word's first keep the score's rhythm), otherwise a word each."""
    if placed is None or not placed.syllables:
        return [Unit(word_times[k], end) for k, (_start, end) in enumerate(line.tokens)]
    units: list[Unit] = []
    starts = [start for start, _end in line.tokens]
    first_score: dict[int, float] = {}
    for when, cut in placed.syllables:
        word = max(0, bisect.bisect_right(starts, max(0, cut - 1)) - 1)
        first_score.setdefault(word, when)
        start = word_times[word] + a * (when - first_score[word])
        if units:
            start = max(start, units[-1].start)
        units.append(Unit(start, cut, when))
    # words the layout put on no note (a short phrase) are shown with the word before them
    if units and units[-1].cut < len(line.text.rstrip()):
        units[-1] = Unit(units[-1].start, len(line.text), units[-1].score)
    return units


def _line_end(
    line: LyricLine,
    word_times: Sequence[float],
    placed: ScoreNotes | None,
    a: float,
    b: float,
    heard: Sequence[AsrWord],
    pairs: Mapping[int, int],
    index: int,
    timing: HeardTiming,
) -> float:
    last = len(line.tokens) - 1
    if placed is not None and placed.end is not None and last in placed.words:
        on_score = a * placed.words[last] + b
        if abs(on_score - word_times[last]) <= AGREE_S:
            return a * placed.end + b
    h = pairs.get(index + last)
    if h is not None and heard[h].end + timing.lead_s > word_times[last]:
        return heard[h].end + timing.lead_s
    return word_times[last] + 2 * WORD_S


def _finish(lines: Sequence[TimedLine], duration: float) -> list[TimedLine]:
    """Cues that never overlap: a line ends ``LINE_TAIL_S`` after its last word, before the next line, and
    lasts at least ``MIN_CUE_S`` where there is room."""
    result: list[TimedLine] = []
    for k, line in enumerate(lines):
        start = line.start
        if result and start < result[-1].end + GAP_S:
            start = result[-1].end + GAP_S
        limit = lines[k + 1].start - GAP_S if k + 1 < len(lines) else duration
        end = min(max(line.end + LINE_TAIL_S, start + MIN_CUE_S), limit)
        if end - start < GAP_S:
            continue
        units = tuple(Unit(min(max(u.start, start), end), u.cut, u.score) for u in line.units)
        result.append(TimedLine(line.text, start, end, units))
    return result


def time_by_score(
    lyrics: str, *, score: Any, layout: Any, duration: float, to_audio: Callable[[float], float]
) -> Subtitles:
    """The lyrics' lines where the score sings them, carried into the recording by ``to_audio`` (score seconds
    -> song seconds) - nothing heard. The Plenio Player's times for a song exported without them (GitHub report
    2026-10-22: "exported without lyrics times"); ``score`` and ``layout`` as for ``time_lyrics``. Lines no
    note sings are left out; the units carry no score time (the times are no measurement of the score)."""
    lines = sung_lines(lyrics)
    if not lines or score is None or layout is None or not score.vocal:
        return Subtitles((), "estimated")
    notes = score_notes(score, layout, lines)
    timed: list[TimedLine] = []
    for line in lines:
        placed = notes.get((line.block, line.line))
        if placed is None or not placed.words:
            continue
        own = {k: to_audio(t) for k, t in placed.words.items()}
        before = timed[-1].end if timed else 0.0
        word_times = _fill(line, own, before, duration)
        units = [Unit(u.start, u.cut) for u in _units(line, word_times, placed, 1.0)]
        last = len(line.tokens) - 1
        end = to_audio(placed.end) if placed.end is not None else word_times[last] + 2 * WORD_S
        timed.append(TimedLine(line.text, units[0].start, max(end, units[-1].start + 0.2), tuple(units)))
    inside = [line for line in timed if 0.0 <= line.start < duration]
    return Subtitles(tuple(_finish(inside, duration)), "estimated")


def time_heard(heard: Sequence[AsrWord], *, duration: float, timing: HeardTiming = WHISPER) -> Subtitles:
    """Subtitles of what was heard, for a song whose lyrics are not known: a line per ASR segment, split at
    pauses longer than ``alignment.LINE_GAP_S``; Whisper's known inventions left out."""
    kept, _dropped = drop_known_inventions([w for w in heard if normalize(w.word)])
    if len(kept) < MIN_HEARD_WORDS:
        return Subtitles((), "heard", notes=("no singing heard",))
    groups: list[list[AsrWord]] = []
    for word in kept:
        if (
            not groups
            or word.segment != groups[-1][-1].segment
            or word.start - groups[-1][-1].end > LINE_GAP_S
        ):
            groups.append([])
        groups[-1].append(word)
    lines: list[TimedLine] = []
    for group in groups:
        text = join_words([w.word for w in group])
        units: list[Unit] = []
        cut = 0
        for k, word in enumerate(group):
            start = _first_start(word, group[1] if len(group) > 1 else None, timing) if k == 0 else word.start
            cut = text.find(word.word, cut) + len(word.word) if word.word in text[cut:] else len(text)
            units.append(Unit(start + timing.lead_s, cut))
        for k in range(1, len(units)):
            units[k] = Unit(max(units[k].start, units[k - 1].start), units[k].cut)
        lines.append(TimedLine(text, units[0].start, group[-1].end + timing.lead_s, tuple(units)))
    return Subtitles(tuple(_finish(lines, duration)), "heard")


# --- what a take sings ------------------------------------------------------------------------


@dataclass(frozen=True)
class SungLyrics:
    """What a take sings, as heard (owner's request 2026-10-23: the lyrics that were wanted and the ones that
    were made, both to follow and both documented): its lines with their times, the text with the lyrics'
    section tags, and how far the take follows its lyrics."""

    subtitles: Subtitles
    text: str
    written_heard: float
    """The share of the lyrics' words that were heard: sung as written."""
    extra_words: int
    """Heard words the lyrics do not have: an ad-lib, a line the music model made up - or a misheard word."""
    not_sung: tuple[str, ...]
    """Lyrics lines of which no word was heard."""
    sections: tuple[dict[str, Any], ...]
    """Per lyrics section: ``{"tag", "words", "heard"}``."""

    def findings(self) -> list[str]:
        """The sections the take did not sing as written."""
        return [
            f"[{s['tag']}] was not sung as written ({s['heard'] / s['words']:.0%} of its words heard)"
            for s in self.sections
            if s["words"] >= NOT_SUNG_MIN_WORDS and s["heard"] < NOT_SUNG_SHARE * s["words"]
        ]

    def to_record(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "lines": self.subtitles.to_timing()["lines"],
            "written_heard": round(self.written_heard, 3),
            "extra_words": self.extra_words,
            "not_sung": list(self.not_sung),
            "sections": [dict(s) for s in self.sections],
        }


SUNG_MAX_CHARS = 64
"""A sung line longer than this - and than its lyrics line by a third - is split at its longest pause (heard
words the lyrics do not have bring no line breaks of their own)."""
SUNG_STANZA_GAP_S = 4.0
"""Words the lyrics do not place: a pause this long starts a new stanza."""
NOT_SUNG_SHARE = 0.4
NOT_SUNG_MIN_WORDS = 4
"""A lyrics section of at least this many words of which fewer than ``NOT_SUNG_SHARE`` were heard counts as
not sung as written."""


def time_sung(
    lyrics: str,
    heard: Sequence[AsrWord],
    *,
    duration: float,
    timing: HeardTiming = WHISPER,
    romanized: bool = False,
) -> SungLyrics | None:
    """What was sung, as heard, laid out like the lyrics where the take sings them: a heard word that pairs
    with a lyrics word (``match_words``, as ``time_lyrics`` pairs them) keeps that word's line - and its
    spelling when it is the same word; heard words the lyrics do not have start a line after a pause. ``None``: no singing heard
    (fewer than ``MIN_HEARD_WORDS`` words). ``romanized``: the heard words were written in the lyrics' Latin
    letters - a word that pairs is shown as the lyrics spell it."""
    kept, _dropped = drop_known_inventions([w for w in split_cjk(heard) if normalize(w.word)])
    if len(kept) < MIN_HEARD_WORDS:
        return None
    lines = sung_lines(lyrics)
    flat = [(n, k) for n, line in enumerate(lines) for k in range(len(line.tokens))]
    lyric_words = [lines[n].words[k] for n, k in flat]
    pairs = {
        i: j
        for i, j in pair_words(lyric_words, [normalize(w.word) for w in kept], romanized=romanized).items()
        if lyric_words[i]
    }
    of_heard = {j: i for i, j in pairs.items()}

    def text_of(j: int) -> str:
        """The lyrics' spelling of the same word (case, apostrophes, punctuation); else the word as heard."""
        i = of_heard.get(j)
        if i is None or (lyric_words[i] != normalize(kept[j].word) and not romanized):
            return kept[j].word.strip()
        n, k = flat[i]
        start, end = lines[n].tokens[k]
        return lines[n].text[start:end]

    groups: list[list[int]] = []
    owners: list[int | None] = []
    """The lyrics line each group sings (its first paired word's), ``None`` for words the lyrics do not have."""
    for j, word in enumerate(kept):
        i = of_heard.get(j)
        gap = word.start - kept[j - 1].end if j else 0.0
        line = flat[i][0] if i is not None else None
        if not groups:
            new = True
        elif i is not None:
            owner = owners[-1]
            new = (
                flat[i][1] == 0
                or (owner is not None and owner != line)
                or (owner is None and gap > LINE_GAP_S)
            )
        else:
            new = gap > LINE_GAP_S
        if new:
            groups.append([])
            owners.append(None)
        groups[-1].append(j)
        if line is not None and owners[-1] is None:
            owners[-1] = line

    def split(group: list[int], limit: float) -> list[list[int]]:
        if len(join_words([text_of(j) for j in group])) <= limit or len(group) < 2:
            return [group]
        cut = max(range(1, len(group)), key=lambda q: kept[group[q]].start - kept[group[q - 1]].end)
        return split(group[:cut], limit) + split(group[cut:], limit)

    laid: list[tuple[list[int], int | None]] = []
    for group, owner in zip(groups, owners, strict=True):
        limit = max(SUNG_MAX_CHARS, 4 / 3 * len(lines[owner].text)) if owner is not None else SUNG_MAX_CHARS
        laid += [(part, owner) for part in split(group, limit)]
    timed: list[TimedLine] = []
    for group, _owner in laid:
        texts = [text_of(j) for j in group]
        text = join_words(texts)
        units: list[Unit] = []
        cut = 0
        for k, (j, piece) in enumerate(zip(group, texts, strict=True)):
            after = kept[group[1]] if len(group) > 1 else None
            start = _first_start(kept[j], after, timing) if k == 0 else kept[j].start
            at = text.find(piece, cut)
            cut = at + len(piece) if at >= 0 else len(text)
            units.append(Unit(max(start + timing.lead_s, units[-1].start if units else 0.0), cut))
        timed.append(TimedLine(text, units[0].start, kept[group[-1]].end + timing.lead_s, tuple(units)))
    # the sections: a group the lyrics place is in its line's section; the others in the section before them
    blocks: list[int | None] = [lines[o].block if o is not None else None for _g, o in laid]
    for k in range(len(blocks)):
        if blocks[k] is None:
            blocks[k] = blocks[k - 1] if k else next((b for b in blocks if b is not None), None)
    tags = {b: section.tag for b, section in enumerate(lyrics_rules.parse_lyrics(lyrics or "").sections)}
    stanzas: list[tuple[int | None, list[str]]] = []
    for k, ((group, _owner), block) in enumerate(zip(laid, blocks, strict=True)):
        pause = kept[group[0]].start - kept[laid[k - 1][0][-1]].end if k else 0.0
        if not stanzas or block != stanzas[-1][0] or (block is None and pause > SUNG_STANZA_GAP_S):
            stanzas.append((block, []))
        stanzas[-1][1].append(timed[k].text)
    text = "\n\n".join(
        "\n".join(([f"[{tags[b]}]"] if b is not None and b in tags else []) + rows) for b, rows in stanzas
    )
    heard_lines = {flat[i][0] for i in pairs}
    sections: dict[int, dict[str, Any]] = {}
    for i, (n, _k) in enumerate(flat):
        block = lines[n].block
        if block in tags and lyric_words[i]:
            entry = sections.setdefault(block, {"tag": tags[block], "words": 0, "heard": 0})
            entry["words"] += 1
            entry["heard"] += i in pairs
    written = sum(1 for w in lyric_words if w)
    return SungLyrics(
        Subtitles(tuple(_finish(timed, duration)), "sung", matched=len(pairs) / max(1, written)),
        text,
        len(pairs) / written if written else 0.0,
        len(kept) - len(pairs),
        tuple(line.text for n, line in enumerate(lines) if n not in heard_lines),
        tuple(sections[b] for b in sorted(sections)),
    )
