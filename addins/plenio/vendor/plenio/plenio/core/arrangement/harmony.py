"""Harmony that holds: keys, a genre's chord vocabulary, how well a chord carries the melody, the repair of
a writer's chords and the measures of a finished score (``docs/design/harmony-and-lyrics-fit.md``).

The writer plans chords per bar; this module decides which of them may stand. A chord stands when it
belongs to the section's key or to the genre's usual borrowings (or is a dominant that resolves), and when
it carries the melody of its whole bar: every note is weighed by its length and its beat, and a note a
half step above a chord tone on a strong beat or held for a beat (an *avoid note*) is not allowed. Where the
writer's chord does not stand, ``repair`` chooses per section the cheapest fitting path - the writer's
chord where it fits, the original chord or a close in-key chord where not.

Measured before this guard (2026-10-08): out-of-key chords in 6 % of a cover's new chords, single chords
a half step off the key in songs; the tests and ``tools/studies/harmony_check.py`` keep the measures.
Pure: no ComfyUI, no I/O.
"""

from __future__ import annotations

import math
import random
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from ...third_party import yue2_abc_tools as upstream
from ..score import canonical as c
from ..score.model import CHORD_INTERVALS
from ..score.native import _key_tonic, _spell

_NATURAL = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
_CHORD = re.compile(r"^([A-G])(#|b)?(.*?)(?:/([A-G])(#|b)?)?$")
MAJOR_SCALE = (0, 2, 4, 5, 7, 9, 11)
MINOR_SCALE = (0, 2, 3, 5, 7, 8, 10)
KK_MAJOR = (6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88)
KK_MINOR = (6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17)
"""Krumhansl-Kessler key profiles (stability of the twelve pitch classes in a major / minor key)."""
KEY_CONFIRM = 0.15
"""A section keeps the score's key unless another key correlates clearly better (transcribed keys of
covers can be wrong; the score's own key wins any near tie)."""


# --- chords -------------------------------------------------------------------------------------


def parse_chord(name: str) -> tuple[int, str, int | None]:
    """``(root pitch class, quality, bass pitch class or None)`` of a chord symbol YuE2 reads."""
    match = _CHORD.match(name.strip())
    if match is None:
        raise ValueError(f"not a chord symbol: {name!r}")
    letter, accidental, quality, bass_letter, bass_accidental = match.groups()
    root = (_NATURAL[letter] + {"#": 1, "b": -1}.get(accidental or "", 0)) % 12
    bass = None
    if bass_letter:
        bass = (_NATURAL[bass_letter] + {"#": 1, "b": -1}.get(bass_accidental or "", 0)) % 12
    if quality not in CHORD_INTERVALS:
        raise ValueError(f"unknown chord quality in {name!r}")
    return root, quality, bass


def tones(name: str) -> frozenset[int]:
    """The pitch classes of a chord symbol (a slash bass included)."""
    root, quality, bass = parse_chord(name)
    classes = {(root + i) % 12 for i in CHORD_INTERVALS[quality]}
    if bass is not None:
        classes.add(bass)
    return frozenset(classes)


def chord_name(root: int, quality: str, key: str) -> str:
    """A chord spelled for ``key`` (C#m in A major, Dbm in Bbm ...)."""
    letter, alteration = _spell(root % 12, key)
    return letter + ("#" * alteration if alteration > 0 else "b" * -alteration) + quality


# --- keys -------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Key:
    tonic: int
    minor: bool
    name: str

    @property
    def scale(self) -> tuple[int, ...]:
        steps = MINOR_SCALE if self.minor else MAJOR_SCALE
        return tuple((self.tonic + s) % 12 for s in steps)


def key_of(name: str) -> Key:
    tonic, minor = _key_tonic(name)
    return Key(tonic, minor, name)


def _key_name(tonic: int, minor: bool) -> str:
    names: list[str] = [str(k) for k in upstream.KEYS if _key_tonic(k) == (tonic, minor)]
    return min(names, key=lambda k: abs(int(upstream.KEYS[k])))


def _correlation(a: Sequence[float], b: Sequence[float]) -> float:
    mean_a, mean_b = sum(a) / len(a), sum(b) / len(b)
    num = sum((x - mean_a) * (y - mean_b) for x, y in zip(a, b, strict=True))
    den = math.sqrt(sum((x - mean_a) ** 2 for x in a) * sum((y - mean_b) ** 2 for y in b))
    return num / den if den else 0.0


def key_scores(weights: Sequence[float]) -> dict[tuple[int, bool], float]:
    """The correlation of a pitch-class profile with all 24 keys."""
    result: dict[tuple[int, bool], float] = {}
    for tonic in range(12):
        for minor, profile in ((False, KK_MAJOR), (True, KK_MINOR)):
            rotated = [profile[(pc - tonic) % 12] for pc in range(12)]
            result[(tonic, minor)] = _correlation(weights, rotated)
    return result


def section_key(score: c.Score, first: int, end: int) -> Key:
    """The key of measures ``first`` to ``end``: the score's own key, unless the section's notes and chords
    clearly belong to another one (``KEY_CONFIRM``)."""
    start, stop = score.starts[first], score.starts[end] if end < score.measure_count else score.total
    written = key_of(score.key_at(start))
    weights = [0.0] * 12
    for note in (*score.vocal, *score.ins):
        overlap = min(note.end, stop) - max(note.onset, start)
        if overlap > 0:
            weights[note.pitch % 12] += overlap
    chords = [ch for ch in score.chords if start <= ch.onset < stop]
    for i, ch in enumerate(chords):
        length = (chords[i + 1].onset if i + 1 < len(chords) else stop) - ch.onset
        try:
            for pc in tones(ch.name):
                weights[pc] += length / 2
        except ValueError:
            continue
    if sum(weights) == 0:
        return written
    scores = key_scores(weights)
    best = max(scores, key=lambda k: scores[k])
    relative = (written.tonic + (3 if written.minor else 9)) % 12, not written.minor
    if best == relative or scores[best] - scores[(written.tonic, written.minor)] <= KEY_CONFIRM:
        return written  # a relative key has the same notes: the score's own name stays
    try:
        return Key(best[0], best[1], _key_name(*best))
    except ValueError:
        return written


# --- genres --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Genre:
    family: str
    words: tuple[str, ...]
    qualities: tuple[str, ...]
    """The chord qualities typical of the family (a subset of YuE2's)."""
    borrowed_major: tuple[tuple[int, str], ...] = ()
    """Chords outside a major key that the family uses: (root above the tonic, quality)."""
    borrowed_minor: tuple[tuple[int, str], ...] = ()
    secondary: bool = False
    """Dominants of other degrees (V/V, V/vi ...) when they resolve."""
    tensions: frozenset[int] = field(default_factory=frozenset)
    """Intervals above the root a melody note may take freely over a chord (9th = 2, 6th/13th = 9, 11th = 5)."""


_POP_BORROWED = ((10, ""), (5, "m"), (8, ""))  # bVII, iv, bVI
GENRES = (
    Genre(
        "metal",
        ("metal", "metalcore", "djent", "doom", "thrash", "hardcore", "grunge"),
        ("", "m", "sus2", "sus4", "dim"),
        ((10, ""), (8, ""), (3, ""), (1, "")),
        ((1, ""), (5, ""), (7, "")),
        False,
        frozenset({2, 3}),
    ),
    Genre(
        "jazz",
        ("jazz", "swing", "bossa", "bebop", "lounge", "big band", "smooth jazz"),
        tuple(CHORD_INTERVALS),
        ((10, "7"), (5, "m6"), (8, "maj7"), (1, "7")),
        ((7, "7"), (1, "maj7"), (5, "7")),
        True,
        frozenset({2, 5, 9}),
    ),
    Genre(
        "blues",
        ("blues", "boogie"),
        ("", "m", "7", "m7", "6", "dim7"),
        ((10, ""), (3, "7"), (5, "7")),
        ((7, "7"), (5, "7")),
        True,
        frozenset({3, 9}),
    ),
    Genre(
        "soul",
        ("r&b", "rnb", "soul", "neo-soul", "neo soul", "funk", "gospel", "motown", "disco"),
        ("", "m", "7", "maj7", "m7", "6", "m6", "sus2", "sus4", "7sus4", "dim7", "m7b5"),
        ((10, ""), (5, "m7"), (8, "maj7"), (3, "maj7")),
        ((7, "7"), (5, "7")),
        True,
        frozenset({2, 9}),
    ),
    Genre(
        "edm",
        (
            "edm",
            "house",
            "techno",
            "trance",
            "dubstep",
            "drum and bass",
            "dnb",
            "electro",
            "synthwave",
            "synth-pop",
            "synthpop",
            "dance",
            "club",
            "eurodance",
            "future bass",
            "hardstyle",
            "garage",
        ),
        ("", "m", "sus2", "sus4", "maj7", "m7"),
        ((10, ""), (8, ""), (3, "")),
        ((7, ""), (5, "")),
        False,
        frozenset({2}),
    ),
    Genre(
        "hip hop",
        ("hip hop", "hip-hop", "rap", "trap", "drill", "lo-fi", "lofi", "boom bap"),
        ("", "m", "m7", "maj7", "7", "sus2"),
        ((10, ""), (8, "maj7"), (5, "m7")),
        ((7, "7"), (1, "maj7")),
        False,
        frozenset({2, 9}),
    ),
    Genre(
        "latin",
        ("latin", "reggaeton", "salsa", "bachata", "tango", "cumbia", "flamenco", "samba"),
        ("", "m", "7", "m7", "sus4"),
        ((10, ""), (5, "m")),
        ((7, "7"), (1, ""), (5, "")),
        True,
        frozenset({2}),
    ),
    Genre(
        "cinematic",
        (
            "cinematic",
            "orchestral",
            "epic",
            "film score",
            "soundtrack",
            "ambient",
            "classical",
            "neoclassical",
            "trailer",
        ),
        ("", "m", "sus2", "sus4", "maj7", "m7", "aug", "m(maj7)", "dim"),
        ((10, ""), (8, ""), (5, "m"), (3, "")),
        ((7, ""), (1, ""), (5, "")),
        True,
        frozenset({2}),
    ),
    Genre(
        "folk",
        ("folk", "acoustic", "country", "americana", "bluegrass", "singer-songwriter", "celtic", "ballad"),
        ("", "m", "sus2", "sus4", "7", "6"),
        ((10, ""), (5, "m")),
        ((7, ""), (7, "7")),
        True,
        frozenset({2, 9}),
    ),
    Genre(
        "rock",
        ("rock", "punk", "indie", "alternative", "garage rock", "britpop", "emo", "shoegaze"),
        ("", "m", "sus2", "sus4", "7"),
        ((10, ""), (8, ""), (3, ""), (5, "")),
        ((7, ""), (5, "")),
        False,
        frozenset({2, 3}),
    ),
    Genre(
        "pop",
        ("pop",),
        ("", "m", "sus2", "sus4", "7", "maj7", "m7", "6", "7sus4"),
        _POP_BORROWED,
        ((7, ""), (7, "7"), (5, "")),
        True,
        frozenset({2, 9}),
    ),
)
"""Genre families, matched in this order by the first family whose word appears in the genre and style
text (``pop`` when none does). Hand-made from common practice - no dataset with an unclear licence."""


def genre_of(text: str) -> Genre:
    lowered = f" {text.lower()} "
    for genre in GENRES:
        if any(re.search(rf"(?<![a-z]){re.escape(word)}(?![a-z])", lowered) for word in genre.words):
            return genre
    return GENRES[-1]


# --- the vocabulary of a section ------------------------------------------------------------------


@dataclass(frozen=True)
class Vocabulary:
    """The chords a section may use: its key, the genre (narrowed or widened by the mode), the closeness."""

    key: Key
    genre: Genre
    qualities: tuple[str, ...]
    slash: bool = False
    free: bool = False
    """Low closeness: any chord of the qualities may stand when it carries the melody (no key test)."""
    tensions: frozenset[int] = frozenset()
    """Intervals above the root a melody note may take cheaply (the genre's, widened by the closeness)."""

    def _allowed_tones(self, root: int) -> set[int]:
        allowed = set(self.key.scale)
        if self.key.minor and (root - self.key.tonic) % 12 in (7, 11):  # V and vii of harmonic minor
            allowed.add((self.key.tonic + 11) % 12)
        return allowed

    def kind(self, name: str) -> str | None:
        """``diatonic``, ``borrowed``, ``secondary`` (a dominant that must resolve) or ``None`` (not allowed)."""
        try:
            root, quality, bass = parse_chord(name)
        except ValueError:
            return None
        if quality not in self.qualities or (bass is not None and not self.slash):
            return None
        chord = {(root + i) % 12 for i in CHORD_INTERVALS[quality]}
        if bass is not None:
            chord.add(bass)
        if chord <= self._allowed_tones(root):
            return "diatonic"
        offset = (root - self.key.tonic) % 12
        borrowed = self.genre.borrowed_minor if self.key.minor else self.genre.borrowed_major
        if (offset, quality) in borrowed or (offset, "") in borrowed and quality in ("sus2", "sus4"):
            return "borrowed"
        if self.genre.secondary and quality in ("", "7") and self.resolves_to(name) is not None:
            return "secondary"
        if self.free:
            return "borrowed"
        return None

    def resolves_to(self, name: str) -> int | None:
        """The root a secondary dominant leads to (a fifth below, a diatonic major or minor chord)."""
        root, quality, _ = parse_chord(name)
        target = (root + 5) % 12
        if quality not in ("", "7") or target == self.key.tonic and not self.key.minor:
            return None  # V of I is diatonic anyway
        if target not in self.key.scale:
            return None
        degree = self.key.scale.index(target)
        diminished = 6 if not self.key.minor else 1  # vii in major, ii in minor
        return None if degree == diminished else target

    def diatonic(self) -> list[str]:
        """Every chord of the key in the allowed qualities (roots on the scale)."""
        found = []
        for root in self.key.scale:
            for quality in self.qualities:
                name = chord_name(root, quality, self.key.name)
                if self.kind(name) == "diatonic":
                    found.append(name)
        return found

    def palette(self) -> str:
        """The chords to offer the writer: the key's triads (and sevenths when allowed), then the
        genre's borrowings."""
        plain = [n for n in self.diatonic() if parse_chord(n)[1] in ("", "m", "dim")]
        sevenths = [n for n in self.diatonic() if parse_chord(n)[1] in ("7", "maj7", "m7", "m7b5")]
        borrowed = self.genre.borrowed_minor if self.key.minor else self.genre.borrowed_major
        extra = []
        for offset, quality in borrowed:
            if quality in self.qualities:
                extra.append(chord_name(self.key.tonic + offset, quality, self.key.name))
        text = ", ".join(plain)
        if sevenths:
            text += f"; with sevenths: {', '.join(sevenths)}"
        if extra:
            text += f"; borrowed, typical in {self.genre.family}: {', '.join(extra)}"
        return text


TENSIONS = {"strict": frozenset(), "colour": frozenset({2, 9}), "free": frozenset({2, 5, 9})}
"""The melody's tensions a policy level adds to the genre's (``Policy.tensions``)."""


def vocabulary(
    key: Key,
    genre: Genre,
    mode_qualities: Sequence[str],
    *,
    closeness: int,
    slash: bool = False,
    tensions: str = "strict",
) -> Vocabulary:
    """The chords of a section. High closeness keeps to the genre's qualities that the mode allows; low
    closeness (below 40) takes all of the mode's and drops the key test (the melody test stays)."""
    allowed = genre.tensions | TENSIONS.get(tensions, frozenset())
    if closeness >= 40:
        qualities = tuple(q for q in mode_qualities if q in genre.qualities) or genre.qualities
        return Vocabulary(key, genre, qualities, slash=False, tensions=allowed)
    return Vocabulary(key, genre, tuple(mode_qualities), slash=slash, free=True, tensions=allowed)


# --- how a chord carries the melody ----------------------------------------------------------------


@dataclass(frozen=True)
class Piece:
    """A melody note (or its part) under one chord: where it starts, how long, its pitch, its weight."""

    onset: int
    duration: int
    pitch: int
    accented: bool


def strong(score: c.Score, onset: int) -> bool:
    measure = score.measure_at(onset)
    start, length = score.starts[measure], score.lengths[measure]
    return onset == start or (score.meters[measure][0] % 2 == 0 and onset == start + length // 2)


def pieces(score: c.Score, notes: Iterable[c.Note], start: int, stop: int) -> list[Piece]:
    """The notes inside ``[start, stop)`` cut to it; accented: on a strong beat or a beat long or more."""
    beat = max(1, score.units_per_quarter)
    found = []
    for note in notes:
        a, b = max(note.onset, start), min(note.end, stop)
        if b <= a:
            continue
        found.append(Piece(a, b - a, note.pitch, strong(score, a) or b - a >= beat))
    return found


def is_avoid(pc: int, chord: frozenset[int], root: int | None = None) -> bool:
    """A note that is not a chord tone and grinds against one: a half step above a chord tone (b9 over the
    root, the 4th over a major third, b6 over the fifth - and so also a major third over a minor chord's
    third). With the chord's ``root`` also a half step under its major seventh (b7 against maj7) and the
    tritone above the root next to its perfect fifth (#4/b5)."""
    if pc in chord:
        return False
    if any((pc - t) % 12 == 1 for t in chord):
        return True
    if root is None:
        return False
    interval = (pc - root) % 12
    if interval == 10 and (root + 11) % 12 in chord:
        return True
    return interval == 6 and (root + 7) % 12 in chord


BLUE_THIRD = 3
"""A minor third over a major chord (a half step under its third): idiomatic where the genre lists it as a
tension (blues, rock, metal) - as a short, unaccented blue note over a major triad, also accented or held over a
dominant seventh chord (the bluesman's I7, where it is the #9) - and a clash elsewhere."""


def clashing(
    pc: int, chord: frozenset[int], root: int, tensions: frozenset[int], *, accented: bool = False
) -> bool:
    """Whether a melody pitch class clashes with a chord: an avoid note, or a blue third where the genre does
    not take it, or (``accented``: on a strong beat or held for a beat) over a major triad without a minor
    seventh."""
    if pc in chord:
        return False
    if is_avoid(pc, chord, root):
        return True
    if (root + 4) % 12 not in chord or (pc - root) % 12 != BLUE_THIRD:
        return False
    if BLUE_THIRD not in tensions:
        return True
    return accented and (root + 10) % 12 not in chord


ACCENTED_CLASH = 1.5
"""The cost per weighted beat of an accented clash where the melody will follow the chords (``fit_cost`` with
``soft``): one and a half times an unaccented one - the note will move, which is heard - but no longer
forbidden."""


def fit_cost(
    melody: Sequence[Piece],
    chord: str | None,
    *,
    key: Key,
    tensions: frozenset[int],
    beat: int,
    soft: bool = False,
) -> float:
    """How badly ``chord`` carries the melody (0 = every note a chord tone; ``inf`` = an accented avoid
    note). Weighed by length (in beats) and accent. ``soft``: an accented clash costs ``ACCENTED_CLASH`` instead
    of ruling the chord out (the melody is adapted to the chords afterwards, ``co_adapt_melody``)."""
    if chord is None or not melody:
        return 0.0
    try:
        chord_tones = tones(chord)
        root = parse_chord(chord)[0]
    except ValueError:
        return math.inf
    cost = 0.0
    for piece in melody:
        pc = piece.pitch % 12
        weight = piece.duration / beat * (1.5 if piece.accented else 1.0)
        if pc in chord_tones:
            continue
        if clashing(pc, chord_tones, root, tensions, accented=piece.accented):
            if piece.accented:
                if not soft:
                    return math.inf
                cost += ACCENTED_CLASH * weight
                continue
            cost += 1.0 * weight
        elif (pc - root) % 12 in tensions:
            cost += 0.15 * weight
        elif pc in key.scale:
            cost += (0.6 if piece.accented else 0.25) * weight
        else:
            cost += 1.0 * weight
    return cost


# --- repairing a section's chords --------------------------------------------------------------------


@dataclass(frozen=True)
class BarChoice:
    """A candidate for one bar: the chords it puts there (``None`` keeps the bar as it is)."""

    chords: tuple[tuple[int, str], ...] | None
    """``(onset, name)`` of the bar's chords; ``None``: the bar keeps its chords."""
    label: str
    intent: float
    """Distance from the writer's chord (0 = the writer's)."""


@dataclass(frozen=True)
class RepairedBar:
    measure: int
    chords: tuple[tuple[int, str], ...] | None
    planned: str | None
    note: str = ""
    """Why the writer's chord did not stand (empty when it did, or nothing was planned)."""


INTENT_SAME_ROOT = 0.4
INTENT_SHARED = 0.6
INTENT_ORIGINAL = 0.8
TRANSITION = {"tritone": 0.6, "chromatic": 0.4, "unresolved": 3.0}


def _shared(a: str, b: str) -> int:
    try:
        return len(tones(a) & tones(b))
    except ValueError:
        return 0


def _transition(previous: str | None, current: str | None, vocab: Vocabulary) -> float:
    if previous is None or current is None or previous == current:
        return 0.0
    try:
        a, _, _ = parse_chord(previous)
        b, _, _ = parse_chord(current)
    except ValueError:
        return 0.0
    cost = 0.0
    if vocab.kind(previous) == "secondary" and vocab.resolves_to(previous) != b:
        cost += TRANSITION["unresolved"]
    step = (b - a) % 12
    if step == 6:
        cost += TRANSITION["tritone"]
    elif step in (1, 11) and vocab.kind(current) != "diatonic":
        cost += TRANSITION["chromatic"]
    return cost


def _last(chords: tuple[tuple[int, str], ...] | None, fallback: str | None) -> str | None:
    return chords[-1][1] if chords else fallback


def repair(
    score: c.Score,
    first: int,
    end: int,
    planned: Sequence[str | None],
    melody: Sequence[c.Note],
    vocab: Vocabulary,
    *,
    weight_intent: float = 1.0,
    melody_weight: float = 1.0,
) -> list[RepairedBar]:
    """The chords of measures ``first`` to ``end`` after the writer's plan (one chord per bar, ``None``
    keeps a bar): per bar the writer's chord when it is in the vocabulary and carries the melody, else the
    cheapest of the original chords, the writer's chord with another quality and in-key chords that share
    two of its tones - chosen together over the section (dynamic programming), so the chords also follow
    each other well and a secondary dominant resolves.

    ``melody_weight`` below 1 (a cover whose melody follows the new chords, ``co_adapt_melody``) weighs the
    melody's fit by that factor and lets an accented clash cost instead of ruling a chord out: at 0 the writer's
    chord stands wherever it belongs to the vocabulary."""
    beat = max(1, score.units_per_quarter)
    tension = vocab.tensions
    soft = melody_weight < 1.0
    melody_weight = max(0.0, min(1.0, melody_weight))

    def fit(melody: Sequence[Piece], name: str | None) -> float:
        cost = fit_cost(melody, name, key=vocab.key, tensions=tension, beat=beat, soft=soft)
        return cost * melody_weight if cost != math.inf else cost

    entering = None
    for ch in score.chords:
        if ch.onset < score.starts[first]:
            entering = ch.name
    candidates: list[list[BarChoice]] = []
    bar_melody: list[list[Piece]] = []
    original_chords: list[tuple[tuple[int, str], ...]] = []
    diatonic = vocab.diatonic()
    for i, measure in enumerate(range(first, end)):
        start, length = score.starts[measure], score.lengths[measure]
        bar_melody.append(pieces(score, melody, start, start + length))
        original_chords.append(
            tuple((ch.onset, ch.name) for ch in score.chords if start <= ch.onset < start + length)
        )
        name = planned[i % len(planned)] if planned else None
        if _entering(score, start) is None and not original_chords[-1]:
            name = None  # a bar without a chord keeps none: a new one would sound on into the bars after it
        options = [BarChoice(None, "original", INTENT_ORIGINAL if name else 0.0)]
        if name is not None:
            options.append(BarChoice(((start, name),), name, 0.0))
            if _stands(name, bar_melody[-1], vocab, beat, length, melody_weight):
                candidates.append(options)  # the writer's chord stands: no alternative is looked for
                continue
            try:
                root, quality, _ = parse_chord(name)
                for q in vocab.qualities:
                    other = chord_name(root, q, vocab.key.name)
                    if other != name and vocab.kind(other) is not None:
                        options.append(BarChoice(((start, other),), other, INTENT_SAME_ROOT))
            except ValueError:
                pass
            for other in diatonic:
                if other != name and _shared(other, name) >= 2:
                    options.append(BarChoice(((start, other),), other, INTENT_SHARED))
        candidates.append(options)

    def bar_cost(i: int, choice: BarChoice) -> float:
        if choice.chords is None:
            sounding = list(original_chords[i])
            if not sounding or sounding[0][0] > score.starts[first + i]:
                previous = _entering(score, score.starts[first + i])
                sounding = [(score.starts[first + i], previous)] if previous else []
            cost = 0.0
            for j, (onset, name) in enumerate(sounding):
                stop = (
                    sounding[j + 1][0]
                    if j + 1 < len(sounding)
                    else score.starts[first + i] + score.lengths[first + i]
                )
                inside = [p for p in bar_melody[i] if onset <= p.onset < stop]
                cost += min(fit(inside, name), 50.0)
            return cost + choice.intent * weight_intent  # the original stays possible even when it clashed
        name = choice.chords[0][1]
        if vocab.kind(name) is None:
            return math.inf
        lost_rhythm = 0.3 if len(original_chords[i]) > 1 else 0.0
        return fit(bar_melody[i], name) + choice.intent * weight_intent + lost_rhythm

    def sounding_name(i: int, choice: BarChoice) -> tuple[str | None, str | None]:
        """The chord a bar starts with and ends with."""
        if choice.chords is None:
            chords = original_chords[i]
            start_name = (
                chords[0][1]
                if chords and chords[0][0] == score.starts[first + i]
                else _entering(score, score.starts[first + i])
            )
            return start_name, _last(chords, start_name)
        return choice.chords[0][1], choice.chords[-1][1]

    # dynamic programming over the bars: the cheapest path of choices, transitions included
    own = [[bar_cost(i, choice) for choice in options] for i, options in enumerate(candidates)]
    ends = [[sounding_name(i, choice) for choice in options] for i, options in enumerate(candidates)]
    best: list[dict[int, tuple[float, int]]] = []
    for i, options in enumerate(candidates):
        layer: dict[int, tuple[float, int]] = {}
        for j in range(len(options)):
            if own[i][j] == math.inf:
                continue
            begin = ends[i][j][0]
            if i == 0:
                layer[j] = (own[i][j] + _transition(entering, begin, vocab), -1)
                continue
            layer[j] = min(
                (total + own[i][j] + _transition(ends[i - 1][k][1], begin, vocab), k)
                for k, (total, _) in best[i - 1].items()
            )
        best.append(layer)  # never empty: keeping the bar ("original") always has a finite cost
    path: list[int] = []
    j = min(best[-1], key=lambda k: best[-1][k][0]) if best else 0
    for i in range(len(best) - 1, -1, -1):
        path.append(j)
        j = best[i][j][1]
    path.reverse()
    result = []
    for i, j in enumerate(path):
        choice = candidates[i][j]
        name = planned[i % len(planned)] if planned else None
        note = ""
        if name is not None and choice.label != name:
            length = score.lengths[first + i]
            why = (
                "does not follow well from the chord before it or into the next"
                if _stands(name, bar_melody[i], vocab, beat, length, melody_weight)
                else _why(name, bar_melody[i], vocab, beat)
            )
            kept = "the bar keeps its chord" if choice.chords is None else f"{choice.label} instead"
            note = f"bar {first + i + 1}: {name} {why}; {kept}"
        result.append(RepairedBar(first + i, choice.chords, name, note))
    return result


ACCEPT_PER_BEAT = 0.3
"""The writer's chord stands when it belongs to the vocabulary, has no accented avoid note and costs at most
this much per beat of its bar (``fit_cost``): about one unaccented passing note per bar."""


def _stands(
    name: str, melody: Sequence[Piece], vocab: Vocabulary, beat: int, length: int, melody_weight: float = 1.0
) -> bool:
    if vocab.kind(name) is None:
        return False
    cost = fit_cost(melody, name, key=vocab.key, tensions=vocab.tensions, beat=beat, soft=melody_weight < 1.0)
    return cost * max(0.0, melody_weight) <= ACCEPT_PER_BEAT * max(1.0, length / beat)


def _entering(score: c.Score, onset: int) -> str | None:
    name = None
    for ch in score.chords:
        if ch.onset > onset:
            break
        name = ch.name
    return name


def _why(name: str, melody: Sequence[Piece], vocab: Vocabulary, beat: int) -> str:
    if vocab.kind(name) is None:
        return f"is not a chord of {vocab.key.name} in {vocab.genre.family}"
    if fit_cost(melody, name, key=vocab.key, tensions=vocab.tensions, beat=beat) == math.inf:
        return "clashes with the melody"
    return "fits the melody less well"


# --- the measures of a score ----------------------------------------------------------------------


HARSH = (1, 11)
"""Pitch-class distances heard as a clash between two voices: a minor second / major seventh (any octave)."""


@dataclass(frozen=True)
class Measures:
    melody_on_chord: float
    """Share of the melody's duration on chord tones (or a tension the genre allows)."""
    accented_avoid: int
    """Melody notes that clash with their chord (``clashing``) on a strong beat or a beat long."""
    clashes: int
    """Moments of an eighth note or longer with Vocal and Ins a minor second / major seventh apart."""
    overlap: float
    """Share of the singing with the instrument line sounding too."""
    chords_in_key: float
    """Share of the chords' duration that belongs to the key (diatonic)."""
    clash_share: float = 0.0
    """Share of the melody's duration on a pitch that clashes with its chord (accented or not) - unlike the
    counts, it does not change when a held note is split."""

    def to_dict(self) -> dict[str, float | int]:
        return {
            "clash_share": round(self.clash_share, 3),
            "melody_on_chord": round(self.melody_on_chord, 3),
            "accented_avoid": self.accented_avoid,
            "clashes": self.clashes,
            "overlap": round(self.overlap, 3),
            "chords_in_key": round(self.chords_in_key, 3),
        }

    def describe(self) -> str:
        return (
            f"melody {self.melody_on_chord:.0%} on chord tones, {self.accented_avoid} accented clash"
            f"{'' if self.accented_avoid == 1 else 'es'} with a chord, {self.clashes} voice clash"
            f"{'' if self.clashes == 1 else 'es'}, chords {self.chords_in_key:.0%} in the key"
        )


def clashes(score: c.Score, a: Sequence[c.Note], b: Sequence[c.Note]) -> int:
    """Moments of an eighth note or longer in which a note of ``a`` and a note of ``b`` sound a minor second /
    major seventh apart - counted as spans of time, so a note split in two is still one clash."""
    eighth = max(1, score.units_per_quarter // 2)
    points = sorted({x for n in (*a, *b) for x in (n.onset, n.end)})
    count = 0
    run = 0
    for s, e in zip(points, points[1:], strict=False):
        upper = [n.pitch for n in a if n.onset <= s < n.end]
        lower = [n.pitch for n in b if n.onset <= s < n.end]
        if any((x - y) % 12 in HARSH for x in upper for y in lower):
            run += e - s
            continue
        if run >= eighth:
            count += 1
        run = 0
    if run >= eighth:
        count += 1
    return count


def measure(
    score: c.Score, melody: Sequence[c.Note], *, tensions: frozenset[int] = frozenset({2, 9})
) -> Measures:
    """The harmony of a score (or of a part: pass the notes of the part as ``melody``)."""
    total = good = bad = 0
    accented = 0
    chords = list(score.chords)
    for i, ch in enumerate(chords):
        stop = chords[i + 1].onset if i + 1 < len(chords) else score.total
        try:
            chord_tones = tones(ch.name)
            root = parse_chord(ch.name)[0]
        except ValueError:
            continue
        for piece in pieces(score, melody, ch.onset, stop):
            total += piece.duration
            pc = piece.pitch % 12
            if pc in chord_tones or (pc - root) % 12 in tensions:
                good += piece.duration
            if clashing(pc, chord_tones, root, tensions, accented=piece.accented):
                bad += piece.duration
                accented += 1 if piece.accented else 0
    sung = sorted(score.vocal, key=lambda n: n.onset)
    line = sorted(score.ins, key=lambda n: n.onset)
    both = sum(max(0, min(n.end, m.end) - max(n.onset, m.onset)) for n in sung for m in line)
    in_key = all_chords = 0
    for i, ch in enumerate(chords):
        stop = chords[i + 1].onset if i + 1 < len(chords) else score.total
        try:
            key = key_of(score.key_at(ch.onset))
            chord_tones = tones(ch.name)
        except (ValueError, KeyError):
            continue
        allowed = set(key.scale)
        if key.minor:
            allowed.add((key.tonic + 11) % 12)
        all_chords += stop - ch.onset
        if chord_tones <= allowed:
            in_key += stop - ch.onset
    return Measures(
        melody_on_chord=good / total if total else 1.0,
        accented_avoid=accented,
        clashes=clashes(score, sung, line),
        overlap=both / max(1, sum(n.duration for n in sung)) if sung else 0.0,
        chords_in_key=in_key / all_chords if all_chords else 1.0,
        clash_share=bad / total if total else 0.0,
    )


# --- a melody that follows new chords ---------------------------------------------------------------


ADAPT_FROM = 85
"""Song flow closeness of a cover below which its melody follows the arrangement's chords (owner's decision
2026-10-15, superseding "the melody always stays"): from ``SNAP_FROM`` the notes that clash with a new chord move
to the nearest note that fits, below it the melody is written anew over the chords. (From 80 a cover keeps its
chords - ``plan.policy`` - so its melody changes only below 80 in practice.)"""
SNAP_FROM = 50
RHYTHM_FROM = 45
"""Below this closeness an instrument line that carries the melody may also get new rhythms (a sung melody keeps
its rhythm: its syllables sit on its notes)."""
RHYTHM_GRIDS = ((0, 2, 4, 6), (0, 3, 6), (0, 2, 3, 4, 6), (0, 4, 6), (0, 1, 2, 4, 6))
"""Onsets in eighths of a 4/4 bar for a new rhythm: four quarters, the pop 3-3-2, a syncopated phrase, a half
and two quarters, two eighths and quarters."""
CONTOURS = ("arch", "wave", "descent")
"""Shapes a phrase of a rewritten melody follows (the arrangement seed picks one for the whole song): a phrase
rising and falling, answered lower (``arch``); up and down twice (``wave``); falling from a high start
(``descent``)."""


def _note_chords(score: c.Score, note: c.Note, beat: int) -> list[tuple[frozenset[int], int, bool]]:
    """``(tones, root, accented)`` of every chord a note sounds under - cut at the chord changes, accented as
    in ``pieces``."""
    points = [note.onset, *(ch.onset for ch in score.chords if note.onset < ch.onset < note.end)]
    found = []
    for i, a in enumerate(points):
        b = points[i + 1] if i + 1 < len(points) else note.end
        name = _entering(score, a)
        if name is None:
            continue
        try:
            found.append((tones(name), parse_chord(name)[0], strong(score, a) or b - a >= beat))
        except ValueError:
            continue
    return found


def _fits_all(
    pitch: int, under: Sequence[tuple[frozenset[int], int, bool]], tensions: frozenset[int]
) -> bool:
    return not any(clashing(pitch % 12, t, r, tensions, accented=a) for t, r, a in under)


def _new_rhythm(
    score: c.Score, first: int, end: int, notes: list[c.Note], *, closeness: int, seed: int
) -> list[c.Note]:
    """``notes`` (one section, sorted) with some 4/4 bars on a new rhythm from ``RHYTHM_GRIDS``: more of them the
    lower the closeness; from 20 the section's first bar keeps its rhythm (the hook). A bar takes its new rhythm
    from its own notes and chord, so a repeated bar is rewritten the same way. Each new note starts with the pitch
    the old line sounded there (``co_adapt_melody`` then chooses the pitches)."""
    beat = score.units_per_quarter
    if beat < 2 or beat % 2:
        return notes
    eighth = beat // 2
    result: list[c.Note] = []
    for m in range(first, end):
        b_start, b_len = score.starts[m], score.lengths[m]
        bar = [n for n in notes if b_start <= n.onset < b_start + b_len]
        if (
            len(bar) < 2
            or score.meters[m] != (4, 4)
            or b_len != 4 * beat
            or any(n.end > b_start + b_len for n in bar)
            or (closeness >= 20 and m == first)
        ):
            result += bar
            continue
        pattern = tuple((n.onset - b_start, n.duration, n.pitch) for n in bar)
        rng = random.Random(f"rhythm:{seed}:{closeness}:{pattern}:{_entering(score, b_start)}")
        if rng.random() >= 0.65 - closeness / 100:
            result += bar
            continue
        grid = rng.choice(RHYTHM_GRIDS)
        begin, finish = bar[0].onset, max(n.end for n in bar)
        onsets = sorted(
            {begin} | {b_start + g * eighth for g in grid if begin < b_start + g * eighth < finish}
        )
        if len(onsets) < 2:
            result += bar
            continue
        for k, onset in enumerate(onsets):
            stop = onsets[k + 1] if k + 1 < len(onsets) else finish
            pitch = [n.pitch for n in bar if n.onset <= onset][-1]
            result.append(c.Note(onset, stop - onset, pitch))
    return result


def _contour(shape: str, t: float, phrase: int) -> float:
    """Where a phrase's melody heads at ``t`` (0 = its first note, 1 = its last), in the section's half range."""
    if shape == "wave":
        return math.sin(2 * math.pi * t) * 0.8
    if shape == "descent":
        return 0.9 - 1.6 * t if phrase % 2 == 0 else 0.4 - 0.9 * t
    # arch: a rising question, a falling answer
    return math.sin(math.pi * t * 0.85) if phrase % 2 == 0 else math.sin(math.pi * t) - 0.6 * t


def _step_cost(step: int) -> float:
    """The cost of a melodic interval (in semitones): steps cheap, a tritone leap almost forbidden."""
    size = abs(step)
    if size == 0:
        return 0.15
    if size <= 2:
        return 0.05 * size
    if size <= 4:
        return 0.2 * size
    if size == 6:
        return 4.0
    if size <= 7:
        return 0.25 * size
    return 2.0 + 0.6 * (size - 7)


def _snapped(
    score: c.Score,
    inside: Sequence[c.Note],
    *,
    low: int,
    high: int,
    scale_pcs: frozenset[int],
    tensions: frozenset[int],
) -> list[c.Note]:
    """The notes that clash with their chord moved to the nearest note that fits: a chord tone within a major
    third when the clash is accented, a scale note within a step when not; a note with no such neighbour stays."""
    beat = max(1, score.units_per_quarter)
    adapted: list[c.Note] = []
    previous: int | None = None
    for note in inside:
        under = _note_chords(score, note, beat)
        pitch = note.pitch
        if under and not _fits_all(pitch, under, tensions):
            accented = any(a for _, _, a in under)
            reach = 4 if accented else 2
            allowed = under[0][0] if accented else scale_pcs | under[0][0]
            options = [
                p
                for p in range(max(low - 2, pitch - reach), min(high + 2, pitch + reach) + 1)
                if p % 12 in allowed and _fits_all(p, under, tensions)
            ]
            if options:
                before = note.pitch if previous is None else previous
                pitch = min(options, key=lambda p: (abs(p - note.pitch), abs(p - before), p))
        adapted.append(note if pitch == note.pitch else c.Note(note.onset, note.duration, pitch))
        previous = pitch
    return adapted


def _rewritten(
    score: c.Score,
    notes: Sequence[c.Note],
    inside: Sequence[c.Note],
    *,
    closeness: int,
    low: int,
    high: int,
    scale_pcs: frozenset[int],
    tensions: frozenset[int],
    seed: int,
) -> list[c.Note]:
    """``notes`` with new pitches chosen together over the section (dynamic programming, see
    ``co_adapt_melody``); ``inside`` are the old notes, whose middle and range the new line keeps.

    Where the new line heads: the phrase's shape (``CONTOURS``) plus the old line's motion around its phrase's
    middle turned upside down (a melodic inversion: the new line moves as busily as the old one, against it)."""
    beat = max(1, score.units_per_quarter)
    keep = closeness / SNAP_FROM  # how much the old line steers the new one: 0.98 at 49, 0 at 0
    centre = sum(n.pitch for n in inside) / len(inside)
    half_range = max(2.0, (high - low) / 2)
    shape = CONTOURS[random.Random(f"contour:{seed}").randrange(len(CONTOURS))]
    bars = [score.measure_at(n.onset) for n in notes]
    phrases: list[
        int
    ] = []  # the phrase of every note: a new one after a rest of a beat, every two bars at most
    for i, note in enumerate(notes):
        new = i > 0 and (
            note.onset - notes[i - 1].end >= beat or (bars[i] - bars[0]) // 2 != (bars[i - 1] - bars[0]) // 2
        )
        phrases.append(phrases[-1] + int(new) if i else 0)
    sizes = [phrases.count(p) for p in range(phrases[-1] + 1)]
    positions = [phrases[:i].count(phrases[i]) for i in range(len(notes))]
    middles = [
        sum(n.pitch for n, p in zip(notes, phrases, strict=True) if p == phrase) / sizes[phrase]
        for phrase in range(len(sizes))
    ]

    layers: list[dict[int, tuple[float, int]]] = []
    for i, note in enumerate(notes):
        under = _note_chords(score, note, beat)
        if not under:  # no chord sounds: the note keeps its pitch
            if not layers:
                layers.append({note.pitch: (0.0, note.pitch)})
                continue
            previous = layers[-1]
            best_previous = min(previous, key=lambda q: previous[q][0])
            layers.append({note.pitch: (previous[best_previous][0], best_previous)})
            continue
        chord_tones, root, _ = under[0]
        accented = any(a for _, _, a in under)
        candidates = (
            [
                p
                for p in range(low, high + 1)
                if _fits_all(p, under, tensions)
                and (p % 12 in chord_tones or (not accented and p % 12 in scale_pcs))
            ]
            or [p for p in range(low, high + 1) if p % 12 in chord_tones]
            or [note.pitch]
        )
        size = sizes[phrases[i]]
        t = positions[i] / (size - 1) if size > 1 else 0.0
        inversion = middles[phrases[i]] - note.pitch
        target = centre + 0.6 * half_range * _contour(shape, t, phrases[i]) + 0.8 * inversion
        phrase_end = positions[i] == size - 1
        old_step = note.pitch - notes[i - 1].pitch if i else 0
        new_phrase = i > 0 and phrases[i] != phrases[i - 1]
        layer: dict[int, tuple[float, int]] = {}
        for p in candidates:
            pc = p % 12
            own = 0.0 if pc in chord_tones else 0.25 if (pc - root) % 12 in tensions else 0.5
            if phrase_end and pc not in chord_tones:
                own += 0.5  # a phrase ends on a chord tone
            if i == len(notes) - 1 and pc != root:
                own += 0.4  # the section on its chord's root
            own += keep * 0.6 * abs(p - note.pitch) + (1 - keep) * 0.35 * abs(p - target)
            if not layers:
                layer[p] = (own, p)
                continue
            best: tuple[float, int] | None = None
            for q, (total, _) in layers[-1].items():
                step = p - q
                move = _step_cost(step) * (0.5 if new_phrase else 1.0)
                if step == 0 and old_step != 0:
                    move += 0.3 * keep + 0.5 * (1 - keep)  # a note repeats where the old line repeated one
                if old_step and step and (step > 0) != (old_step > 0):
                    move += 0.8 * keep  # the old line's up and down, less and less
                option = (total + own + move, q)
                if best is None or option < best:
                    best = option
            assert best is not None
            layer[p] = best
        layers.append(layer)
    chosen = [0] * len(notes)
    pitch = min(layers[-1], key=lambda p: layers[-1][p][0])
    for i in range(len(notes) - 1, -1, -1):
        chosen[i] = pitch
        pitch = layers[i][pitch][1]
    return [n if p == n.pitch else c.Note(n.onset, n.duration, p) for n, p in zip(notes, chosen, strict=True)]


def co_adapt_melody(
    score: c.Score,
    first: int,
    end: int,
    melody: Sequence[c.Note],
    *,
    closeness: int,
    tensions: frozenset[int] = frozenset({2, 9}),
    seed: int = 0,
    allow_rhythm_change: bool = False,
) -> tuple[list[c.Note], int]:
    """The melody (all of its notes; those that start in measures ``first`` to ``end`` change) fitted to the
    chords of ``score`` by the song flow closeness:

    - ``ADAPT_FROM`` and above: unchanged;
    - ``SNAP_FROM`` to ``ADAPT_FROM``: a note that clashes with its chord on a strong beat or held for a beat moves
      to the nearest chord tone, an unaccented clash to the nearest scale note that fits (``_snapped``);
    - below ``SNAP_FROM``: the melody is written anew (``_rewritten``): chord tones on the accents, scale notes
      between them, small steps, phrases that follow a shape (``CONTOURS``) and end on a chord tone - near the old
      pitches and their up and down at 49, free of them at 0; with ``allow_rhythm_change`` below ``RHYTHM_FROM``
      some bars also get a new rhythm (``_new_rhythm``).

    A rewritten melody stays in the melody's own range, a snapped note at most a whole step beyond it; without
    ``allow_rhythm_change`` the onsets and lengths stay (a sung melody keeps its syllables on its notes). Returns the notes, sorted, and how many of them changed."""
    start, stop = score.starts[first], score.starts[end] if end < score.measure_count else score.total
    ordered = sorted(melody, key=lambda n: n.onset)
    inside = [n for n in ordered if start <= n.onset < stop]
    outside = [n for n in ordered if not start <= n.onset < stop]
    if closeness >= ADAPT_FROM or not inside or not score.chords:
        return ordered, 0
    low, high = min(n.pitch for n in ordered), max(n.pitch for n in ordered)
    scale_pcs = frozenset(section_key(score, first, end).scale)
    if closeness >= SNAP_FROM:
        adapted = _snapped(score, inside, low=low, high=high, scale_pcs=scale_pcs, tensions=tensions)
    else:
        notes = list(inside)
        if allow_rhythm_change and closeness < RHYTHM_FROM:
            notes = _new_rhythm(score, first, end, notes, closeness=closeness, seed=seed)
        adapted = _rewritten(
            score,
            notes,
            inside,
            closeness=closeness,
            low=low,
            high=high,
            scale_pcs=scale_pcs,
            tensions=tensions,
            seed=seed,
        )
    if [(n.onset, n.duration) for n in adapted] != [(n.onset, n.duration) for n in inside]:
        changed = len(adapted)  # a new rhythm: every note of the section is new
    else:
        changed = sum(1 for a, b in zip(inside, adapted, strict=True) if a.pitch != b.pitch)
    return sorted([*outside, *adapted], key=lambda n: n.onset), changed
