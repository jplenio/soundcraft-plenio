"""MusicXML import: the files Plenio's *Export MusicXML* writes, brought back - also after a script or a text
editor changed them (feature request 2026-10-22: export, put the lyrics on their notes or change notes in bulk
by a script, import the file again).

It reads **Plenio's own MusicXML only**, the inverse of ``musicxml.export_musicxml``, and refuses any other
file with the reason - a general MusicXML reader for what notation programs write is not the aim (the owner's
condition: only compatible files):

- the file says it was written by Plenio (``<software>``), has the two parts *Vocal* and *Instrument*, one
  voice each, and in every bar what the exporter writes: attributes (divisions, key, time, clef), the
  rehearsal marks and the tempo, chord symbols (``<harmony>``), notes and rests with ties, the lyrics;
  presentation a program may add (stems, beams, accidentals, print and layout hints) is passed over;
- chords inside a part (``<chord/>``), grace notes, tuplets, ``<backup>``/``<forward>``, a second voice, a
  bar that does not hold its meter, a DOCTYPE with declarations of its own - the file is refused, with the
  bar and what is wrong;
- the score comes back as the canonical model (``canonical``): the tempo, the meters, the keys, the sections
  (their names as the export kept them), the line groups, both voices and the chord symbols;
- the lyrics: the syllables under the Vocal notes give the words and the note each word starts on. When the
  words are the sheet's lyrics (``lyrics``), those stay as they are - tags, directions and spelling included -
  and every line gets a span with its words' notes (``lyric_layout``: the line is sung exactly there). When
  the words differ, the lyrics are written anew from the file: its line and block ends (``<end-line/>``,
  ``<end-paragraph/>``, the block tags in ``<lyric name>``) or, without them, a line per phrase and a block
  per section.

Pure: text in, model out; parsing with the standard library (no entity expansion, no external DTD).
"""

from __future__ import annotations

import json
import re
import unicodedata
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from fractions import Fraction

from ...third_party import yue2_abc_tools as upstream
from .. import lyrics as lyrics_rules
from .. import syllables
from ..errors import PlenioValidationError
from . import canonical as c
from . import lyric_layout
from .canonical import ChordSymbol, KeyChange, Note, Score, Section
from .musicxml import _KINDS, LAYOUT_FIELD, SECTIONS_FIELD, SOFTWARE

MAX_BYTES = 8 * 1024 * 1024
PARTS = (("P1", "Vocal", "vocal"), ("P2", "Instrument", "ins"))
_STEPS = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
_ACCIDENTALS = {-2: "bb", -1: "b", 0: "", 1: "#", 2: "##"}
_KIND_TEXT = {kind: text for text, (kind, _shown) in reversed(list(_KINDS.items()))}
"""A ``<kind>`` without its ``text`` attribute: the suffix the export writes for it."""
_PASSED_OVER = frozenset(
    {
        "print",
        "barline",
        "sound",
        "bookmark",
        "link",
        "listening",
        "figured-bass",
        "grouping",
        "attributes-clef",
    }
)
"""Measure children that are presentation only."""
_NOTE_PRESENTATION = frozenset(
    {
        "type",
        "dot",
        "accidental",
        "stem",
        "notehead",
        "beam",
        "staff",
        "instrument",
        "play",
        "listen",
        "footnote",
    }
)
_ATTRIBUTE_PRESENTATION = frozenset({"clef", "staves", "staff-details", "measure-style", "instruments"})
_LYRIC_PASSED_OVER = frozenset({"extend", "elision", "footnote", "level"})


@dataclass(frozen=True)
class MusicXmlImport:
    score: Score
    lyrics: str | None
    """The lyrics to keep with the score (``None``: the file has none - the sheet's stay as they are)."""
    spans: tuple[tuple[int, ...], ...]
    """Every lyrics line's span with its words' onsets (``lyric_layout``)."""
    report: tuple[str, ...]


@dataclass
class _Syllable:
    onset: int
    syllabic: str
    text: str
    end_line: bool
    end_block: bool
    tag: str


@dataclass
class _Word:
    text: str
    onsets: list[int]
    """The notes its syllables are sung on (the first: where the word starts)."""
    parts: list[str] = field(default_factory=list)
    """The file's syllables of the word, one per onset."""
    tag: str = ""
    end_line: bool = False
    end_block: bool = False


@dataclass
class _Part:
    meters: list[tuple[int, int]] = field(default_factory=list)
    notes: list[Note] = field(default_factory=list)
    keys: dict[int, str] = field(default_factory=dict)
    sections: dict[int, str] = field(default_factory=dict)
    chords: dict[int, str] = field(default_factory=dict)
    syllables: list[_Syllable] = field(default_factory=list)
    tempo: int | None = None
    divisions: int | None = None


def _refuse(message: str, *, where: str = "musicxml", hint: str | None = None) -> PlenioValidationError:
    error = PlenioValidationError(
        message,
        hint=hint,
        diagnostics=[{"severity": "error", "message": message, "where": where}],
    )
    return error


NOT_PLENIO = (
    "Plenio imports only MusicXML that its own Export MusicXML wrote (changed by a script or a text editor is "
    "fine); a notation program writes the file anew in its own way. For other files use Import MIDI…."
)


def _parse(text: str) -> ET.Element:
    if len(text.encode("utf-8")) > MAX_BYTES:
        raise _refuse(f"The MusicXML file is too large ({MAX_BYTES // 2**20} MB at most).")
    if re.search(r"<!ENTITY", text, re.IGNORECASE) or re.search(r"<!DOCTYPE[^>]*\[", text, re.IGNORECASE):
        raise _refuse(
            "The MusicXML file declares entities of its own; Plenio's export never does.", hint=NOT_PLENIO
        )
    try:
        root = ET.fromstring(text)
    except ET.ParseError as error:
        raise _refuse(f"The file is no well-formed XML ({error}).", hint=NOT_PLENIO) from error
    if root.tag != "score-partwise":
        raise _refuse(f"The file is no MusicXML score (its root is <{root.tag}>).", hint=NOT_PLENIO)
    software = " ".join((root.findtext("identification/encoding/software") or "").split())
    if SOFTWARE not in software:
        raise _refuse(
            f"This MusicXML file was written by {software or 'an unknown program'}, not by Plenio.",
            hint=NOT_PLENIO,
        )
    return root


def _int(element: ET.Element | None, what: str, bar: int) -> int:
    text = (element.text or "").strip() if element is not None else ""
    try:
        return int(text)
    except ValueError:
        raise _refuse(f"Bar {bar}: {what} {text!r} is no whole number.", where=f"bar {bar}") from None


def _key_name(element: ET.Element, bar: int) -> str:
    fifths = _int(element.find("fifths"), "the key's fifths", bar)
    minor = (element.findtext("mode") or "major").strip() == "minor"
    for name, value in upstream.KEYS.items():
        if value == fifths and name.endswith("m") == minor:
            return str(name)
    raise _refuse(f"Bar {bar}: no key has {fifths} fifths.", where=f"bar {bar}")


def _chord_name(element: ET.Element, bar: int) -> str:
    step = (element.findtext("root/root-step") or "").strip()
    alter = int(float(element.findtext("root/root-alter") or 0))
    kind = element.find("kind")
    suffix = kind.get("text") if kind is not None and kind.get("text") is not None else None
    if suffix is None:
        suffix = _KIND_TEXT.get((kind.text or "").strip() if kind is not None else "major", None)
    bass = (element.findtext("bass/bass-step") or "").strip()
    bass_alter = int(float(element.findtext("bass/bass-alter") or 0))
    name = f"{step}{_ACCIDENTALS.get(alter, '?')}{suffix if suffix is not None else '?'}" + (
        f"/{bass}{_ACCIDENTALS.get(bass_alter, '?')}" if bass else ""
    )
    if upstream.CHORD.fullmatch(name) is None:
        raise _refuse(f"Bar {bar}: the chord symbol {name!r} is not one Plenio writes.", where=f"bar {bar}")
    return name


def _pitch(element: ET.Element, bar: int) -> int:
    step = (element.findtext("step") or "").strip()
    if step not in _STEPS:
        raise _refuse(f"Bar {bar}: the pitch step {step!r} is unknown.", where=f"bar {bar}")
    alter = float(element.findtext("alter") or 0)
    if alter != int(alter):
        raise _refuse(
            f"Bar {bar}: a microtone ({alter:+g}) cannot be written in the score.", where=f"bar {bar}"
        )
    octave = _int(element.find("octave"), "the octave", bar)
    midi = (octave + 1) * 12 + _STEPS[step] + int(alter)
    if not 0 <= midi <= 127:
        raise _refuse(f"Bar {bar}: the pitch lies outside the MIDI range.", where=f"bar {bar}")
    return midi


def _read_part(element: ET.Element, name: str, lead: bool, report: list[str]) -> _Part:
    part = _Part()
    start = 0  # the bar's onset (units: divisions, which are the score's L)
    meter: tuple[int, int] | None = None
    open_note: Note | None = None  # the note a tie may carry on
    for index, measure in enumerate(element.findall("measure")):
        bar = index + 1
        where = f"bar {bar}"
        position = 0
        for child in measure:
            tag = child.tag
            if tag == "attributes":
                for item in child:
                    if item.tag == "divisions":
                        value = _int(item, "divisions", bar)
                        if (4 * value) & (4 * value - 1) or not 1 <= 4 * value <= c.MAX_UNIT:
                            raise _refuse(
                                f"{value} divisions a quarter cannot be a score unit (a power of two up to "
                                f"{c.MAX_UNIT // 4}).",
                                where=where,
                            )
                        if part.divisions is not None and value != part.divisions:
                            raise _refuse(
                                f"Bar {bar}: the divisions change; Plenio's export keeps one.", where=where
                            )
                        part.divisions = value
                    elif item.tag == "key":
                        part.keys[start + position] = _key_name(item, bar)
                    elif item.tag == "time":
                        if position:
                            raise _refuse(f"Bar {bar}: the meter changes inside the bar.", where=where)
                        meter = (
                            _int(item.find("beats"), "the beats", bar),
                            _int(item.find("beat-type"), "the beat type", bar),
                        )
                    elif item.tag not in _ATTRIBUTE_PRESENTATION:
                        raise _refuse(
                            f"Bar {bar}: <{item.tag}> in the attributes is not Plenio's.", where=where
                        )
            elif tag == "direction":
                for kind in child.iter():
                    if kind.tag == "rehearsal" and lead:
                        label = " ".join((kind.text or "").split())
                        if label:
                            if position:
                                report.append(f"the section {label!r} moved to the start of bar {bar}")
                            part.sections[index] = label
                    elif kind.tag == "per-minute" and lead and part.tempo is None:
                        part.tempo = round(float(kind.text or 0)) or None
                    elif kind.tag == "sound" and kind.get("tempo") and lead and part.tempo is None:
                        part.tempo = round(float(kind.get("tempo") or 0)) or None
                    elif kind.tag in ("words", "dynamics", "wedge", "pedal", "octave-shift", "segno", "coda"):
                        raise _refuse(f"Bar {bar}: a <{kind.tag}> direction is not Plenio's.", where=where)
            elif tag == "harmony":
                if not lead:
                    raise _refuse(
                        f"Bar {bar}: the {name} part has chord symbols; Plenio writes them over the Vocal.",
                        where=where,
                    )
                offset = int(float(child.findtext("offset") or 0))
                part.chords[start + position + offset] = _chord_name(child, bar)
            elif tag == "note":
                for unwanted in ("chord", "grace", "cue", "time-modification"):
                    if child.find(unwanted) is not None:
                        raise _refuse(
                            f"Bar {bar}: the {name} part has a <{unwanted}> note; Plenio's voices are single "
                            "lines in whole units.",
                            where=where,
                        )
                voice = (child.findtext("voice") or "1").strip()
                if voice != "1":
                    raise _refuse(f"Bar {bar}: the {name} part has a second voice ({voice}).", where=where)
                for item in child:
                    known = {
                        "pitch",
                        "rest",
                        "duration",
                        "tie",
                        "voice",
                        "notations",
                        "lyric",
                        *_NOTE_PRESENTATION,
                    }
                    if item.tag not in known:
                        raise _refuse(f"Bar {bar}: <{item.tag}> in a note is not Plenio's.", where=where)
                duration = _int(child.find("duration"), "a duration", bar)
                if duration < 1:
                    raise _refuse(f"Bar {bar}: a note of no length.", where=where)
                onset = start + position
                pitch_element = child.find("pitch")
                ties = {t.get("type") for t in child.findall("tie")}
                if pitch_element is not None:
                    pitch = _pitch(pitch_element, bar)
                    if (
                        "stop" in ties
                        and open_note is not None
                        and open_note.end == onset
                        and open_note.pitch == pitch
                    ):
                        # a tied piece: the sounding note goes on
                        open_note = Note(open_note.onset, open_note.duration + duration, pitch)
                        part.notes[-1] = open_note
                    else:
                        if "stop" in ties:
                            report.append(
                                f"bar {bar}: a tie in the {name} part had no note to carry on - a new note"
                            )
                        open_note = Note(onset, duration, pitch)
                        part.notes.append(open_note)
                        if lead:
                            part.syllables += _lyrics_of(child, onset, bar, report)
                    if "start" not in ties:
                        open_note = None
                else:
                    open_note = None
                position += duration
            elif tag in ("backup", "forward"):
                raise _refuse(f"Bar {bar}: <{tag}> - the {name} part has more than one voice.", where=where)
            elif tag not in _PASSED_OVER:
                raise _refuse(f"Bar {bar}: <{tag}> is not Plenio's MusicXML.", where=where)
        if meter is None:
            raise _refuse("The first bar has no meter (<time>).", where="bar 1")
        if part.divisions is None:
            raise _refuse("The first bar has no <divisions>.", where="bar 1")
        length = Fraction(meter[0] * 4 * part.divisions, meter[1])
        if length.denominator != 1:
            raise _refuse(
                f"Bar {bar}: the meter {meter[0]}/{meter[1]} is no whole number of divisions.", where=where
            )
        if position != length:
            raise _refuse(
                f"Bar {bar} of the {name} part holds {Fraction(position, part.divisions)} quarters, its meter "
                f"{meter[0]}/{meter[1]} {Fraction(int(length), part.divisions)}.",
                where=where,
            )
        part.meters.append(meter)
        start += int(length)
    return part


def _lyrics_of(note: ET.Element, onset: int, bar: int, report: list[str]) -> list[_Syllable]:
    found = []
    for lyric in note.findall("lyric"):
        if (lyric.get("number") or "1") != "1":
            report.append(
                f"bar {bar}: a lyric of verse {lyric.get('number')} was left out (Plenio sings one verse)"
            )
            continue
        for item in lyric:
            if item.tag not in {"syllabic", "text", "end-line", "end-paragraph", *_LYRIC_PASSED_OVER}:
                raise _refuse(f"Bar {bar}: <{item.tag}> in a lyric is not Plenio's.", where=f"bar {bar}")
        text = " ".join("".join(t.text or "" for t in lyric.findall("text")).split())
        if not text:
            continue
        found.append(
            _Syllable(
                onset,
                (lyric.findtext("syllabic") or "single").strip(),
                text,
                lyric.find("end-line") is not None,
                lyric.find("end-paragraph") is not None,
                " ".join((lyric.get("name") or "").split()),
            )
        )
    return found


def _words(found: Sequence[_Syllable]) -> list[_Word]:
    """The words of the syllables in order: a syllable that goes on (``begin``/``middle``) joins the next; words
    joined on one note (``in the``) are words of their own on that note."""
    words: list[_Word] = []
    open_word: _Word | None = None
    for syllable in sorted(found, key=lambda s: s.onset):
        tokens = syllable.text.split()
        for index, token in enumerate(tokens):
            if index == 0 and open_word is not None and syllable.syllabic in ("middle", "end"):
                open_word.text += token
                open_word.onsets.append(syllable.onset)
                open_word.parts.append(token)
            else:
                if open_word is not None:
                    words.append(open_word)
                open_word = _Word(token, [syllable.onset], [token], tag=syllable.tag if index == 0 else "")
            if index < len(tokens) - 1:
                words.append(open_word)
                open_word = None
        if syllable.syllabic in ("single", "end") and open_word is not None:
            words.append(open_word)
            open_word = None
        last = open_word if open_word is not None else (words[-1] if words else None)
        if last is not None:
            last.end_line |= syllable.end_line or syllable.end_block
            last.end_block |= syllable.end_block
    if open_word is not None:
        words.append(open_word)
    return words


def _normal(word: str) -> str:
    return re.sub(r"[\W_]+", "", unicodedata.normalize("NFKC", word).casefold())


@dataclass(frozen=True)
class _Keyed:
    """A lyrics line with the file's words it is sung with."""

    block: int
    line: int
    text: str
    words: Sequence[_Word]


def _line_end(score: Score, words: Sequence[_Word], until: int, sung: set[int]) -> int:
    """Where a line ends: its last syllable's note, held on over the notes that follow it in its phrase and no
    syllable takes (up to ``until``, the next line's start)."""
    notes = sorted(score.vocal, key=lambda n: n.onset)
    last = max(words[-1].onsets)
    index = next(k for k, n in enumerate(notes) if n.onset == last)
    end = notes[index].end
    gap = lyric_layout.phrase_gap(score)
    for note in notes[index + 1 :]:
        if note.onset >= until or note.onset in sung or note.onset - end >= gap:
            break
        end = note.end
    return end


def _syllable_onsets(text: str, language: str, words: Sequence[_Word]) -> list[int] | None:
    """The onset of every syllable of ``text`` as the layout splits it (``syllables_of``): where the file's
    syllables of each word are runs of the layout's (``ev`` + ``ery`` for ``ev-er-y``) - else ``None``."""
    found: list[int] = []
    layout_words = lyric_layout.words_of(text, language)
    if len(layout_words) != len(words):
        return None
    for pieces, word in zip(layout_words, words, strict=True):
        index = 0
        for part, onset in zip(word.parts, word.onsets, strict=True):
            target, got, first = _normal(part), "", index
            while index < len(pieces) and len(got) < len(target):
                got += _normal(pieces[index][0])
                index += 1
            if got != target or index == first:
                return None
            found += [onset] * (index - first)
        if index != len(pieces):
            return None
    return found


def _spans(score: Score, keyed: Sequence[_Keyed], language: str) -> list[tuple[int, ...]]:
    """A span per line: from its first word to the end of its last note, with the onsets of its syllables
    (of its words, where the file splits a word other than the layout)."""
    sung = {onset for line in keyed for word in line.words for onset in word.onsets}
    spans: list[tuple[int, ...]] = []
    for k, line in enumerate(keyed):
        until = keyed[k + 1].words[0].onsets[0] if k + 1 < len(keyed) else score.total
        onsets = _syllable_onsets(line.text, language, line.words) or [w.onsets[0] for w in line.words]
        end = _line_end(score, line.words, until, sung)
        spans.append((line.words[0].onsets[0], end, line.block, line.line, *onsets))
    return spans


def _section_tag(score: Score, onset: int) -> str:
    measure = score.measure_at(onset)
    label = next((s.label for s in reversed(score.sections) if s.measure <= measure), "")
    return " ".join(word.capitalize() for word in label.split()) or "Verse"


def _section_of(score: Score, onset: int) -> int:
    measure = score.measure_at(onset)
    return max((s.measure for s in score.sections if s.measure <= measure), default=0)


def _rebuild(score: Score, words: Sequence[_Word]) -> tuple[str, list[_Keyed], str]:
    """Lyrics written from the file's words: its line and block ends (and block tags), or a line per phrase and
    a block per section; the lines with their words, and how they were found."""
    marked = any(w.end_line for w in words)
    lines: list[list[_Word]] = []
    if marked:
        for word in words:
            if not lines or lines[-1][-1].end_line:
                lines.append([])
            lines[-1].append(word)
    else:
        notes = sorted(score.vocal, key=lambda n: n.onset)
        heads = {phrase[0].onset for phrase in lyric_layout._phrases(notes, lyric_layout.phrase_gap(score))}
        for word in words:
            if not lines or word.onsets[0] in heads:
                lines.append([])
            lines[-1].append(word)
    ends = any(w.end_block for w in words)
    tags = any(w.tag for w in words)
    blocks: list[list[list[_Word]]] = []
    for line in lines:
        if not blocks:
            opens = True
        elif ends:
            opens = blocks[-1][-1][-1].end_block
        elif tags:
            opens = bool(line[0].tag)
        else:
            opens = _section_of(score, line[0].onsets[0]) != _section_of(score, blocks[-1][-1][0].onsets[0])
        if opens:
            blocks.append([])
        blocks[-1].append(line)
    text: list[str] = []
    keyed: list[_Keyed] = []
    for b, block in enumerate(blocks):
        first = block[0][0]
        text.append(f"[{first.tag or _section_tag(score, first.onsets[0])}]")
        for j, line in enumerate(block):
            written = " ".join(w.text for w in line)
            text.append(written)
            keyed.append(_Keyed(b, j, written, line))
        text.append("")
    how = (
        "its line and block ends"
        if marked
        else "a line per phrase, a block per section (the file marks no line ends)"
    )
    return "\n".join(text).strip() + "\n", keyed, how


def _merge(current: str, words: Sequence[_Word]) -> tuple[list[_Keyed], int] | None:
    """The sheet's lyrics lines with the file's words when the words are the sheet's - lines the file sings
    nowhere (no note sang them when it was exported) left out, and counted; ``None`` when the words are
    others."""
    parsed = lyrics_rules.parse_lyrics(current)
    language = syllables.guess_language(current)
    keyed: list[_Keyed] = []
    left = cursor = 0
    for b, block in enumerate(parsed.sections):
        for j, line in enumerate(block.lines):
            if lyric_layout._DIRECTION.match(line):
                continue
            mine = [_normal("".join(p for p, _end in w)) for w in lyric_layout.words_of(line, language)]
            if not mine:
                continue
            theirs = words[cursor : cursor + len(mine)]
            if [_normal(w.text) for w in theirs] == mine:
                keyed.append(_Keyed(b, j, line, theirs))
                cursor += len(mine)
            else:
                left += 1
    return (keyed, left) if keyed and cursor == len(words) else None


def _layout(
    root: ET.Element, meters: Sequence[tuple[int, int]], sections: dict[int, str], current: Score | None
) -> tuple[int, ...]:
    required = {0, *sections, *(i for i in range(1, len(meters)) if meters[i] != meters[i - 1])}

    def fits(candidate: Sequence[int]) -> bool:
        firsts, at = set(), 0
        for count in candidate:
            firsts.add(at)
            at += count
        return (
            sum(candidate) == len(meters)
            and all(1 <= v <= c.MAX_GROUP for v in candidate)
            and required <= firsts
        )

    kept = _field(root, LAYOUT_FIELD).split()
    if kept and all(v.isdigit() for v in kept) and fits([int(v) for v in kept]):
        return tuple(int(v) for v in kept)
    if current is not None and fits(current.layout):
        return current.layout
    starts = sorted(required)
    layout: list[int] = []
    for index, first in enumerate(starts):
        span = (starts[index + 1] if index + 1 < len(starts) else len(meters)) - first
        while span > c.MAX_GROUP:
            layout.append(c.MAX_GROUP)
            span -= c.MAX_GROUP
        layout.append(span)
    return tuple(layout)


def _field(root: ET.Element, name: str) -> str:
    for item in root.findall("identification/miscellaneous/miscellaneous-field"):
        if item.get("name") == name:
            return item.text or ""
    return ""


def _labels(root: ET.Element, shown: dict[int, str], current: Score | None) -> dict[int, str]:
    """The section names: as the export kept them where the rehearsal mark still shows them, else as the
    current score has them there (in another case), else the mark in lower case."""
    try:
        kept = {int(m): str(label) for m, label in json.loads(_field(root, SECTIONS_FIELD) or "[]")}
    except (ValueError, TypeError):
        kept = {}
    mine = {s.measure: s.label for s in current.sections} if current is not None else {}
    labels: dict[int, str] = {}
    for measure, mark in shown.items():
        for candidate in (kept.get(measure), mine.get(measure)):
            if (
                candidate
                and " ".join(w.capitalize() for w in candidate.split()) == mark
                or (candidate and candidate.casefold() == mark.casefold())
            ):
                labels[measure] = candidate
                break
        else:
            labels[measure] = mark.lower()
    return labels


def import_musicxml(text: str, *, lyrics: str | None = None, current: Score | None = None) -> MusicXmlImport:
    """The score (and the lyrics with their places) of a MusicXML file Plenio wrote; ``lyrics`` and
    ``current``: the sheet's lyrics and score now (the lyrics stay when the words are theirs, the line groups
    and section names are kept where they fit)."""
    root = _parse(text)
    listed = [
        (p.get("id"), " ".join((p.findtext("part-name") or "").split()))
        for p in root.findall("part-list/score-part")
    ]
    if listed != [(pid, name) for pid, name, _track in PARTS]:
        raise _refuse(
            "Plenio's MusicXML has the two parts Vocal (P1) and Instrument (P2); this file has "
            + (", ".join(f"{name or '?'} ({pid})" for pid, name in listed) or "none")
            + ".",
            hint=NOT_PLENIO,
        )
    report: list[str] = []
    parts = {}
    for pid, name, track in PARTS:
        element = root.find(f"part[@id='{pid}']")
        if element is None:
            raise _refuse(f"The part {name} ({pid}) has no music.", hint=NOT_PLENIO)
        parts[track] = _read_part(element, name, track == "vocal", report)
    vocal, ins = parts["vocal"], parts["ins"]
    if vocal.meters != ins.meters:
        raise _refuse("The Vocal and the Instrument part have other bars (count or meters).")
    if vocal.divisions != ins.divisions:
        raise _refuse("The Vocal and the Instrument part count in other divisions.")
    divisions = vocal.divisions or 1
    denominator = 4 * divisions
    if denominator & (denominator - 1) or denominator > c.MAX_UNIT:
        raise _refuse(
            f"{divisions} divisions a quarter cannot be a score unit (a power of two up to {c.MAX_UNIT // 4})."
        )
    keys = {**ins.keys, **vocal.keys}
    if 0 not in keys:
        raise _refuse("The first bar has no key.", where="bar 1")
    changes = sorted(keys)  # as the score had them, a change to the same key included
    sections = _labels(root, vocal.sections, current)
    layout = _layout(root, vocal.meters, sections, current)
    starts = [0]
    for numerator, beat in vocal.meters:
        starts.append(starts[-1] + numerator * denominator // beat)
    group_onsets = set()
    at = 0
    for count in layout:
        group_onsets.add(starts[at])
        at += count
    tempo = vocal.tempo
    if tempo is None:
        tempo = current.tempo if current is not None else 100
        report.append(f"the file names no tempo - {tempo} BPM")
    score = Score(
        tempo=tempo,
        unit=Fraction(1, denominator),
        meters=tuple(vocal.meters),
        keys=tuple(
            KeyChange(o, keys[o], "header" if o == 0 else "field" if o in group_onsets else "inline")
            for o in changes
        ),
        sections=tuple(Section(m, sections[m]) for m in sorted(sections)),
        layout=layout,
        vocal=tuple(vocal.notes),
        ins=tuple(ins.notes),
        chords=tuple(ChordSymbol(o, vocal.chords[o]) for o in sorted(vocal.chords)),
    )
    problems = c.problems(score)
    if problems:
        raise PlenioValidationError(
            "The MusicXML file cannot be read as a score.",
            diagnostics=[{"severity": "error", "message": p, "where": "musicxml"} for p in problems],
        )
    report.insert(
        0,
        f"{score.measure_count} bars at {score.tempo} BPM: Vocal {len(score.vocal)} notes, Instrument "
        f"{len(score.ins)} notes, {len(score.chords)} chord symbols, {len(score.sections)} sections",
    )
    words = _words(vocal.syllables)
    if current is not None and current.source is not None:
        # the bars the file leaves as they were keep their text (``canonical.to_abc``)
        score = replace(score, source=current.source)
    if not words:
        report.append("no lyrics in the file: the sheet's lyrics stay and are laid on the notes anew")
        return MusicXmlImport(score, None, (), tuple(report))
    merged = _merge(lyrics, words) if lyrics and lyrics.strip() else None
    if merged is not None:
        keyed, left = merged
        new_lyrics = lyrics or ""
        report.append(f"lyrics: the sheet's words ({len(words)}) - every line on the notes the file gives it")
        if left:
            report.append(
                f"{left} line(s) of the sheet's lyrics have no notes in the file and are not placed"
            )
    else:
        new_lyrics, keyed, how = _rebuild(score, words)
        before = (
            "the sheet's lyrics have other words" if lyrics and lyrics.strip() else "the sheet had no lyrics"
        )
        report.append(
            f"lyrics: written from the file ({len(words)} words, {len(keyed)} lines; {how}) - {before}"
        )
    spans = tuple(_spans(score, keyed, syllables.guess_language(new_lyrics)))
    check = lyric_layout.layout(score, new_lyrics, spans)
    placed = {s.onset for line in check.lines() for s in line.syllables}
    missed = sorted({w.onsets[0] for line in keyed for w in line.words} - placed)
    if missed:
        report.append(
            f"{len(missed)} word(s) could not stand on their notes and follow the line's other words"
        )
    return MusicXmlImport(score, new_lyrics, spans, tuple(report))
