"""How long each step of a long node took, for its summary and ComfyUI's log."""

from __future__ import annotations

import time


class StepClock:
    """How long each step of an export took, in the order they ran - for the node's summary and ComfyUI's log
    (owner's report 2026-10-30: Export Release took minutes, now and then; the vocal stem and the lyrics ASR - a
    worker started anew, its models read again - vary the most)."""

    def __init__(self) -> None:
        self.began = self.last = time.perf_counter()
        self.steps: dict[str, float] = {}
        self.hearing = 0.0
        """Of the lyrics ASR: the seconds its worker heard and timed (loading its models included)."""

    def lap(self, step: str) -> None:
        """The time since the last lap goes to ``step``."""
        now = time.perf_counter()
        self.steps[step] = self.steps.get(step, 0.0) + now - self.last
        self.last = now

    def line(self) -> str:
        """``took 3:17 - vocal stem 1:52, lyrics ASR 52 s (46 s in its worker) ...``; steps under a second left out."""

        def span(seconds: float) -> str:
            return f"{int(seconds // 60)}:{int(seconds % 60):02d}" if seconds >= 60 else f"{seconds:.0f} s"

        parts = []
        for step, seconds in self.steps.items():
            if seconds < 1:
                continue
            inner = f" ({span(self.hearing)} in its worker)" if step == "lyrics ASR" and self.hearing else ""
            parts.append(f"{step} {span(seconds)}{inner}")
        return f"took {span(time.perf_counter() - self.began)}" + (f" - {', '.join(parts)}" if parts else "")
