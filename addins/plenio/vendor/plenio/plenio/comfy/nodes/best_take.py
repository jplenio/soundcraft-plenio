"""Best Take: the brief's lyrics fidelity - one take, or the take of two or three that sings most of its lyrics
(owner's request 2026-10-24, ``core.fidelity``).

The second and third takes are lazy inputs: their renders run only when this node asks for them - with
*standard* never, with *high* the second only when the first sang less than 96 % of the lyrics' words as
written, with *highest* also the third when neither of the first two reached 96 %. Each take is heard by the lyrics ASR (the same hearing Export
Release uses, kept in its cache) and scored like the release record's *as sung*: the share of the lyrics'
words heard as written.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from comfy_api.latest import io

from ...core import romanize
from ...core import subtitles as subtitle_rules
from ...core.asr import AsrSettings, weak_segments
from ...core.errors import PlenioCancelledError, PlenioError
from ...core.fidelity import STANDARD, Choice, best, needs_another
from ...core.reports import Report, Status
from .. import host
from ..lyrics_asr import run_asr
from ..types import Brief, ReportType
from .export import asr_language

LOG = logging.getLogger(__name__)
LATER = ("second", "third")
_SCORES: dict[str, float] = {}
"""Share of the lyrics heard, by take, lyrics and language: the lazy check and the run hear a take once."""


def level_of(brief: Any, lyrics: str) -> str:
    """The fidelity to apply: the brief's, standard without a brief, for an instrumental or without sung lyrics."""
    level = str(getattr(brief, "fidelity", STANDARD) or STANDARD)
    if brief is None or getattr(brief, "instrumental", False) or not subtitle_rules.sung_lines(lyrics or ""):
        return STANDARD
    return level


def score(audio: Any, lyrics: str, brief: Any) -> float:
    """The share of ``lyrics``' words the take sings as written, as heard (0 when nothing pairs)."""
    language = asr_language(brief, lyrics)
    sha = host.audio_sha256(audio)
    key = hashlib.sha256(f"{sha}\0{language}\0{lyrics}".encode()).hexdigest()
    if key in _SCORES:
        return _SCORES[key]
    samples, rate, seconds = host.audio_facts(audio)
    progress = host.Progress()
    try:
        result = run_asr(audio, AsrSettings(language=language), sha, progress)
    finally:
        progress.update(1.0)
    weak = weak_segments(result)
    words = [w for w in result.words if w.segment not in weak]
    words, romanized = romanize.in_lyrics_script(lyrics, words)
    sung = subtitle_rules.time_sung(
        lyrics, words, duration=seconds, timing=subtitle_rules.timing_for(result.engine), romanized=romanized
    )
    _SCORES[key] = sung.written_heard if sung is not None else 0.0
    return _SCORES[key]


class PlenioBestTake(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="PlenioBestTake",
            # the summary is re-sent on every run, also when the node is cached (ComfyUI keeps its UI)
            has_intermediate_output=True,
            display_name="Best Take · lyrics fidelity",
            category="Plenio/Audio analysis",
            description=(
                "The brief's lyrics fidelity. standard: the first take. high: a second take when the first sang less "
                "than 96 % of the words as written, and the take that sings more of the lyrics is kept. highest: a "
                "third take too, when neither reached 96 %. The takes are heard by the lyrics ASR; the later ones render only when asked for - "
                "higher fidelity makes the generation take longer."
            ),
            inputs=[
                io.Audio.Input("take", tooltip="The first take."),
                io.String.Input(
                    "lyrics",
                    force_input=True,
                    tooltip="The lyrics the takes sing (the final lyrics of the Song Sheet).",
                ),
                Brief.Input(
                    "brief",
                    optional=True,
                    tooltip="Song Brief or Cover Brief: its lyrics fidelity (without one: the first take).",
                ),
                io.Audio.Input(
                    "second",
                    optional=True,
                    lazy=True,
                    tooltip="A second take (the next seed): rendered only when the first sang under 96 % of the lyrics.",
                ),
                io.Audio.Input(
                    "third",
                    optional=True,
                    lazy=True,
                    tooltip="A third take: rendered only with highest fidelity, when neither take sang 96 % of the lyrics.",
                ),
            ],
            outputs=[
                io.Audio.Output(display_name="audio", tooltip="The take that sings most of its lyrics."),
                ReportType.Output(
                    display_name="report", tooltip="Each take's share of the lyrics heard, and the one kept."
                ),
            ],
        )

    @classmethod
    def check_lazy_status(
        cls,
        take: Any = None,
        lyrics: str | None = None,
        brief: Any = None,
        second: Any = None,
        third: Any = None,
    ) -> list[str]:
        level = level_of(brief, lyrics or "")
        if take is None or level == STANDARD or third is not None:
            return []
        takes = [take] if second is None else [take, second]
        try:
            scores = [score(t, lyrics or "", brief) for t in takes]
        except PlenioCancelledError:
            host.raise_if_interrupted()
            raise
        except Exception:  # noqa: BLE001 - execute keeps the first take and says why
            LOG.exception("Plenio Best Take: the takes could not be heard")
            return []
        if not needs_another(level, scores):
            return []
        return ["second"] if second is None else ["third"]

    @classmethod
    def execute(
        cls, take: Any, lyrics: str, brief: Any = None, second: Any = None, third: Any = None
    ) -> io.NodeOutput:
        level = level_of(brief, lyrics)
        takes = [take, *(t for t in (second, third) if t is not None)] if level != STANDARD else [take]
        if level == STANDARD:
            summary = "Lyrics fidelity standard: one take"
            report = Report(
                "best_take", Status.OK, summary + ".", (), {"level": STANDARD, "takes": 1, "kept": 1}
            )
            return io.NodeOutput(take, report, ui={"plenio_summary": [{"status": "ok", "markdown": summary}]})
        try:
            scores = [score(t, lyrics, brief) for t in takes]
        except PlenioCancelledError:
            host.raise_if_interrupted()
            raise
        except PlenioError as error:
            summary = f"Lyrics fidelity {level}: the takes could not be heard ({error.message}) - the first take is kept"
            report = Report(
                "best_take",
                Status.WARNING,
                summary + ".",
                (),
                {"level": level, "takes": len(takes), "kept": 1},
            )
            return io.NodeOutput(
                take, report, ui={"plenio_summary": [{"status": "warning", "markdown": f"**{summary}**"}]}
            )
        choice = Choice(level, tuple(scores), best(scores))
        report = Report("best_take", Status.OK, choice.text + ".", (), choice.to_dict())
        return io.NodeOutput(
            takes[choice.kept], report, ui={"plenio_summary": [{"status": "ok", "markdown": choice.text}]}
        )
