"""Lyrics fidelity: how closely a take sings its lyrics - one take, or the best of two or three (owner's
request 2026-10-24).

A music model does not always sing its lyrics: it leaves a line out, repeats one, sings other words. In the
owner's 37 sung YuE2 takes of 2026-10-23/24 the median take sang 89 % of its lyrics' words as written (heard
by the lyrics ASR), and one in six less than 75 % - the same documents sang a verse 8 of 65 words in one take
and 64 of 65 in the next. YuE2's own evaluation keeps the better of two takes for the same reason. So:

- **standard**: one take, as before;
- **high**: a second take with the next seed when the first sang less than ``TARGET`` of the words, and the
  take that sings more of the lyrics is kept;
- **highest**: as high, and a third take when neither of the two sang at least ``TARGET`` of the words.

A take that sings ``TARGET`` (96 %) of its lyrics as written is close enough: no further take is rendered after
it (2026-10-25). Each further take costs a render and a hearing: the generation takes up to about twice (high)
or three times (highest) as long. Instrumentals and songs without sung lyrics always take one take. Pure; no audio.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .errors import PlenioUserError

STANDARD, HIGH, HIGHEST = "standard", "high", "highest"
FIDELITY_OPTIONS = {
    "standard": STANDARD,
    "high - best of 2 takes": HIGH,
    "highest - best of 3 takes": HIGHEST,
}
"""The brief's choices (as shown) and the level each stands for."""
FIDELITY_DEFAULT = "standard"
MAX_TAKES = {STANDARD: 1, HIGH: 2, HIGHEST: 3}
TARGET = 0.96
"""A further take only while no take so far sang at least this share of the lyrics' words as written."""
FIDELITY_TOOLTIP = (
    "standard: one take. high: a second take when the first sang under 96 % of the words as written; the "
    "better is kept. highest: a third when neither reached 96 %. Takes longer (up to 2x or 3x)."
)


def fidelity_level(value: object) -> str:
    """``standard``, ``high`` or ``highest`` from a brief's choice (shown text or level; empty: standard)."""
    text = str(value or "").strip()
    if not text:
        return STANDARD
    if text in FIDELITY_OPTIONS:
        return FIDELITY_OPTIONS[text]
    if text in MAX_TAKES:
        return text
    raise PlenioUserError(
        f"Unknown lyrics fidelity {text!r}.", hint=f"Choose one of {list(FIDELITY_OPTIONS)}."
    )


def needs_another(level: str, scores: Sequence[float]) -> bool:
    """Whether one more take is wanted after the takes heard so far (``scores``: each one's share of the
    lyrics' words sung as written)."""
    taken = len(scores)
    if taken >= MAX_TAKES[level]:
        return False
    heard = [s for s in scores if s == s]  # nan: not heard
    return not heard or max(heard) < TARGET


def best(scores: Sequence[float]) -> int:
    """The take to keep: the one that sang most of the lyrics (the earlier one at equal shares)."""
    return max(range(len(scores)), key=lambda index: (scores[index], -index))


@dataclass(frozen=True)
class Choice:
    level: str
    scores: tuple[float, ...]
    """Each take's share of the lyrics' words sung as written (``nan``: not heard)."""
    kept: int
    """0-based."""

    @property
    def text(self) -> str:
        shares = ", ".join(f"take {i + 1}: {s:.0%}" for i, s in enumerate(self.scores))
        if len(self.scores) == 1:
            return f"Lyrics fidelity {self.level}: one take - {self.scores[0]:.0%} of the lyrics heard as written"
        return (
            f"Lyrics fidelity {self.level}: take {self.kept + 1} of {len(self.scores)} kept - "
            f"{self.scores[self.kept]:.0%} of the lyrics heard as written ({shares})"
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "level": self.level,
            "takes": len(self.scores),
            "kept": self.kept + 1,
            "scores": [round(s, 3) for s in self.scores],
        }
