"""Audio HQ 1-3: stereo cleanup, regenerated highs and de-reverb before the EQ (``core.audio.hq``)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any

from comfy_api.latest import io

from ...core.audio import hq
from ...core.errors import PlenioUserError
from ...core.reports import Report, Status
from .. import audio_models, host
from ..types import AudioModelType, Brief, FinishSwitch, ReportType

PRESET_TOOLTIP = (
    "auto: the profile that fits the song's genre (from the connected brief; standard without one). standard, "
    "gentle, strong and wide are the same four profiles in HQ 1, 2 and 3; custom shows the fields."
)
BRIEF_TOOLTIP = "Optional: Song Brief or Cover Brief - its genre chooses the profile for 'auto'."


def _preset(custom: list[Any]) -> Any:
    return io.DynamicCombo.Input(
        "preset",
        options=[
            *[io.DynamicCombo.Option(name, []) for name in hq.PRESETS if name != hq.CUSTOM],
            io.DynamicCombo.Option(hq.CUSTOM, custom),
        ],
        tooltip=PRESET_TOOLTIP,
    )


def _choice(preset: dict[str, Any] | None) -> str:
    # an unknown preset name never arrives: ComfyUI drops a DynamicCombo value it has no option for
    if preset is None:
        raise PlenioUserError("The preset is missing or unknown.", hint=f"Choose one of {list(hq.PRESETS)}.")
    name = str(preset.get("preset", hq.AUTO))
    if name not in hq.PRESETS:
        raise PlenioUserError(f"Unknown preset {name!r}.", hint=f"Use one of {list(hq.PRESETS)}.")
    return name


def _db(value: Any, unit: str = "dB") -> str:
    return "-" if value is None else f"{value:+.1f} {unit}"


HQ_MASTERING_TOOLTIP = hq.HQ_MASTERING_HINT


class PlenioHQMastering(io.ComfyNode):
    """The templates' switch for the highest mastering quality (owner's request 2026-10-22): at the start of
    the workflow, beside the brief, wired only into *Plenio · Master* - so switching it runs the mastering again,
    not the song. The page draws it as a card, with the Cover Art switch beside it (2026-10-23,
    ``frontend/src/extension/finishSwitch.ts``)."""

    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="PlenioHQMastering",
            display_name="HQ Mastering & Cover Art",
            category="Plenio/Mastering",
            description=(
                "Two switches at the start of a template. HQ mastering: on, HQ 2 · Regenerate Highs (UniverSR) "
                "runs in Plenio · Master - less AI shimmer and fewer artifacts, about twice the time; off (default; "
                "on in Enhance & Master), UniverSR is neither run nor needed. "
                "Cover Art (on by default): paints the song's cover - off, the template's cover nodes are bypassed."
            ),
            inputs=[
                FinishSwitch.Input(
                    "hq_mastering",
                    display_name="HQ mastering",
                    default=False,
                    tooltip=HQ_MASTERING_TOOLTIP,
                )
            ],
            outputs=[
                io.Boolean.Output(
                    display_name="hq_mastering",
                    tooltip="Into Plenio · Master (HQ 2 · Regenerate Highs): on lets UniverSR run.",
                )
            ],
        )

    @classmethod
    def execute(cls, hq_mastering: Any = False) -> io.NodeOutput:
        # a widget of its own: ComfyUI does not convert its value (a client may send "false")
        return io.NodeOutput(hq_mastering is True or str(hq_mastering).strip().lower() in ("true", "1", "on"))


def _finish(
    kind: str,
    title: str,
    reports: list[dict[str, Any]],
    detail: Callable[[dict[str, Any]], str],
    results: list[Any],
    rate: int,
) -> io.NodeOutput:
    first = reports[0]
    profile = first["profile"] or "custom"
    why = "" if first["chosen_by"] in ("preset", "custom") else f" ({first['chosen_by']})"
    skipped = all(report.get("skipped") for report in reports)
    shown = "skipped" if skipped else detail(first)
    summary = f"{title}: {profile}{why} - {shown}; {first['seconds']:.1f} s"
    notes = [note for report in reports for note in report["notes"]]
    if first["provisional"]:
        notes.append(f"the '{profile}' values are provisional (not listening-tested yet)")
    status = (
        Status.SKIPPED if skipped else Status.WARNING if any(r.get("skipped") for r in reports) else Status.OK
    )
    record = Report(kind, status, summary, tuple(dict.fromkeys(notes)), {"items": reports})
    markdown = "\n".join([f"**{summary}**", *[f"- note: {n}" for n in dict.fromkeys(notes)]])
    return io.NodeOutput(
        host.make_audio(results, rate),
        record,
        ui={"plenio_summary": [{"status": status.value, "markdown": markdown}]},
    )


class PlenioHQStereoCleanup(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        standard = hq.STEREO_PROFILES[hq.STANDARD]
        return io.Schema(
            node_id="PlenioHQStereoCleanup",
            display_name="HQ 1 · Stereo Cleanup",
            category="Plenio/Mastering",
            has_intermediate_output=True,
            description=(
                "Mid/side cleanup before the EQ: a high-cut and a spectral cleanup of the side signal above 2 kHz "
                "(the unsteady stereo shimmer of AI renders at the edge of the image) and a little 2nd/3rd "
                "harmonic warmth above 400 Hz (2x oversampled). The middle - voice, kick, snare, bass - is not "
                "filtered. Same rate and length, no normalisation."
            ),
            inputs=[
                io.Audio.Input("audio", tooltip="The song (every item of a batch)."),
                _preset(
                    [
                        io.Float.Input(
                            "side_highcut_hz",
                            default=standard.side_highcut_hz,
                            min=4000.0,
                            max=20000.0,
                            step=250.0,
                            tooltip="Above this the side signal is cut (Hz, zero-phase).",
                        ),
                        io.Float.Input(
                            "side_cleanup",
                            default=standard.side_cleanup,
                            min=0.0,
                            max=1.0,
                            step=0.05,
                            tooltip="0 off ... 1 strongest: the high-cut's share and the cleanup of the side's "
                            "diffuse highs.",
                        ),
                        io.Float.Input(
                            "warmth",
                            default=standard.warmth,
                            min=0.0,
                            max=0.8,
                            step=0.02,
                            tooltip="0 off ... 0.8: saturation above 400 Hz (2nd and 3rd harmonics).",
                        ),
                    ]
                ),
                Brief.Input("brief", optional=True, tooltip=BRIEF_TOOLTIP),
            ],
            outputs=[
                io.Audio.Output(display_name="audio", tooltip="The cleaned song (same rate and length)."),
                ReportType.Output(
                    display_name="report", tooltip="Profile, settings and the side level before/after."
                ),
            ],
        )

    @classmethod
    def execute(
        cls, audio: dict[str, Any], preset: dict[str, Any] | None = None, brief: Any = None
    ) -> io.NodeOutput:
        name = _choice(preset)
        preset = preset or {}
        custom = hq.StereoCleanup(
            float(preset.get("side_highcut_hz", hq.StereoCleanup.side_highcut_hz)),
            float(preset.get("side_cleanup", hq.StereoCleanup.side_cleanup)),
            float(preset.get("warmth", hq.StereoCleanup.warmth)),
        )
        settings, profile, why = hq.resolve(name, brief, hq.STEREO_PROFILES, custom)
        items, rate = host.audio_items(audio)
        results, reports = [], []
        for item in items:
            out, report = hq.stereo_cleanup(
                item, rate, settings, preset=name, profile=profile, why=why, cancel=host.raise_if_interrupted
            )
            results.append(out)
            reports.append(report)

        def detail(report: dict[str, Any]) -> str:
            s = report["settings"]
            side = report["side_change_db"].get("10500-20000 Hz")
            return (
                f"side high-cut {s['side_highcut_hz'] / 1000:g} kHz, cleanup {s['side_cleanup']:.0%}, warmth "
                f"{s['warmth']:g}; side above 10.5 kHz {_db(side)}"
            )

        return _finish("hq_stereo_cleanup", "HQ 1 · Stereo Cleanup", reports, detail, results, rate)


class PlenioHQRegenerateHighs(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        standard = hq.REGENERATE_PROFILES[hq.STANDARD]
        return io.Schema(
            node_id="PlenioHQRegenerateHighs",
            display_name="HQ 2 · Regenerate Highs",
            category="Plenio/Mastering",
            has_intermediate_output=True,
            description=(
                "Erase and regenerate: a super-resolution model generates new highs from the song without its "
                "top octaves; above the crossover they replace a share of the original's highs, following the "
                "original's level. Below the crossover the song stays as it is. Same rate and length."
            ),
            inputs=[
                io.Audio.Input("audio", tooltip="The song (every item of a batch)."),
                io.Boolean.Input(
                    "hq_mastering",
                    display_name="HQ mastering",
                    default=True,
                    optional=True,  # an API prompt without it runs the stage, as before
                    label_on="on - UniverSR regenerates the highs",
                    label_off="off - the song passes unchanged",
                    tooltip="Off: skipped, the model is not even loaded. In the templates the HQ Mastering switch "
                    "at the start sets it (off by default, on in Enhance & Master): on, fewer AI shimmer and "
                    "artifacts, about twice the time.",
                ),
                # lazy: with HQ mastering off the loader never runs (and a missing model file is no error)
                AudioModelType.Input("model", lazy=True, tooltip="Load Audio Model (super-resolution)."),
                _preset(
                    [
                        io.Float.Input(
                            "from_hz",
                            default=standard.from_hz,
                            min=4500.0,
                            max=20000.0,
                            step=100.0,
                            tooltip="New highs from (Hz): the crossover. The model sees the song up to its "
                            "nearest input edge below it (UniverSR: 4, 6, 8 or 12 kHz).",
                        ),
                        io.Float.Input(
                            "new_share",
                            default=standard.new_share,
                            min=0.0,
                            max=1.0,
                            step=0.05,
                            tooltip="Share of the new highs above the crossover; the rest stays the original's.",
                        ),
                        io.Float.Input(
                            "level_match",
                            default=standard.level_match,
                            min=0.3,
                            max=1.5,
                            step=0.05,
                            tooltip="The new highs follow the original's level (40 ms envelope) times this.",
                        ),
                    ]
                ),
                Brief.Input("brief", optional=True, tooltip=BRIEF_TOOLTIP),
                io.Int.Input(
                    "seed",
                    default=0,
                    min=0,
                    max=2**32 - 1,
                    optional=True,
                    # fixed, not randomize: a new seed on every queue would re-run the model and change the song
                    control_after_generate=io.ControlAfterGenerate.fixed,
                    tooltip="Seed of the model: the same seed gives the same highs.",
                ),
                io.Int.Input(
                    "model_steps",
                    default=4,
                    min=2,
                    max=8,
                    optional=True,
                    advanced=True,
                    tooltip="UniverSR's flow steps: 4 (default) about 1.5 s per second of music on an RTX 5060 "
                    "Ti, 3 about 1.1 s, 2 about 0.75 s - fewer steps, other and quieter highs.",
                ),
            ],
            outputs=[
                io.Audio.Output(
                    display_name="audio", tooltip="The song with new highs (same rate and length)."
                ),
                ReportType.Output(
                    display_name="report", tooltip="Profile, engine and its input edge, levels before/after."
                ),
            ],
        )

    @classmethod
    def check_lazy_status(cls, hq_mastering: bool = True, model: Any = None, **_others: Any) -> list[str]:
        """The model only when HQ mastering is on."""
        return ["model"] if hq_mastering and model is None else []

    @classmethod
    def execute(
        cls,
        audio: dict[str, Any],
        hq_mastering: bool = True,
        model: Any = None,
        preset: dict[str, Any] | None = None,
        brief: Any = None,
        seed: int = 0,
        model_steps: int = 4,
    ) -> io.NodeOutput:
        if not hq_mastering:
            summary = "HQ 2 · Regenerate Highs: off - HQ mastering is off, UniverSR did not run"
            record = Report(
                "hq_regenerate_highs",
                Status.SKIPPED,
                summary,
                ("the song passes unchanged; switch HQ mastering on for fewer AI shimmer and artifacts",),
                {"items": [], "hq_mastering": False},
            )
            return io.NodeOutput(
                audio, record, ui={"plenio_summary": [{"status": "skipped", "markdown": f"**{summary}**"}]}
            )
        name = _choice(preset)
        preset = preset or {}
        custom = hq.RegenerateHighs(
            float(preset.get("from_hz", hq.RegenerateHighs.from_hz)),
            float(preset.get("new_share", hq.RegenerateHighs.new_share)),
            float(preset.get("level_match", hq.RegenerateHighs.level_match)),
        )
        settings, profile, why = hq.resolve(name, brief, hq.REGENERATE_PROFILES, custom)
        settings = replace(settings, seed=int(seed))
        engine = audio_models.require(model, "super-resolution", "HQ 2 · Regenerate Highs")
        if hasattr(engine, "with_steps"):
            engine = engine.with_steps(int(model_steps))
        items, rate = host.audio_items(audio)
        results, reports = [], []
        try:
            for item in items:
                out, report = hq.regenerate_highs(
                    item,
                    rate,
                    engine,
                    settings,
                    preset=name,
                    profile=profile,
                    why=why,
                    cancel=host.raise_if_interrupted,
                )
                results.append(out)
                reports.append(report)
        finally:
            if hasattr(engine, "release"):
                engine.release()

        def detail(report: dict[str, Any]) -> str:
            s = report["settings"]
            return (
                f"{report['engine']} from {report['engine_edge_hz'] / 1000:g} kHz"
                + (f" ({report['engine_steps']} steps)" if report.get("engine_steps") else "")
                + ", new highs from "
                f"{s['from_hz'] / 1000:g} kHz ({s['new_share']:.0%}, level {s['level_match']:g}); highs "
                f"{_db(report['highs_change_db'])}, their side {_db(report['side_change_db'])}"
            )

        return _finish("hq_regenerate_highs", "HQ 2 · Regenerate Highs", reports, detail, results, rate)


class PlenioHQDeReverb(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        standard = hq.DEREVERB_PROFILES[hq.STANDARD]
        return io.Schema(
            node_id="PlenioHQDeReverb",
            display_name="HQ 3 · De-Reverb",
            category="Plenio/Mastering",
            is_experimental=True,
            has_intermediate_output=True,
            description=(
                "Takes the short metallic room after syllables and hits out above 600 Hz (late-envelope "
                "subtraction) and smooths the phase above 2 kHz (phase lock). Also lowers the highs by a few dB - "
                "bypassed in the templates. Same rate and length."
            ),
            inputs=[
                io.Audio.Input("audio", tooltip="The song (every item of a batch)."),
                _preset(
                    [
                        io.Float.Input(
                            "dereverb",
                            default=standard.dereverb,
                            min=0.0,
                            max=1.0,
                            step=0.05,
                            tooltip="0 off ... 1: how much of the late, diffuse room above 600 Hz is taken out.",
                        ),
                        io.Float.Input(
                            "phase_lock",
                            default=standard.phase_lock,
                            min=0.0,
                            max=1.0,
                            step=0.05,
                            tooltip="0 off ... 1: how far the phase above 2 kHz follows its strong "
                            "neighbours.",
                        ),
                    ]
                ),
                Brief.Input("brief", optional=True, tooltip=BRIEF_TOOLTIP),
            ],
            outputs=[
                io.Audio.Output(display_name="audio", tooltip="The drier song (same rate and length)."),
                ReportType.Output(
                    display_name="report", tooltip="Profile, settings and the highs before/after."
                ),
            ],
        )

    @classmethod
    def execute(
        cls, audio: dict[str, Any], preset: dict[str, Any] | None = None, brief: Any = None
    ) -> io.NodeOutput:
        name = _choice(preset)
        preset = preset or {}
        custom = hq.DeReverb(
            float(preset.get("dereverb", hq.DeReverb.dereverb)),
            float(preset.get("phase_lock", hq.DeReverb.phase_lock)),
        )
        settings, profile, why = hq.resolve(name, brief, hq.DEREVERB_PROFILES, custom)
        items, rate = host.audio_items(audio)
        results, reports = [], []
        for item in items:
            out, report = hq.dereverb(
                item, rate, settings, preset=name, profile=profile, why=why, cancel=host.raise_if_interrupted
            )
            results.append(out)
            reports.append(report)

        def detail(report: dict[str, Any]) -> str:
            s = report["settings"]
            return (
                f"de-reverb {s['dereverb']:.0%}, phase lock {s['phase_lock']:.0%}; highs above 3.2 kHz "
                f"{_db(report['highs_change_db'])}"
            )

        return _finish("hq_dereverb", "HQ 3 · De-Reverb", reports, detail, results, rate)


__all__ = ["PlenioHQDeReverb", "PlenioHQRegenerateHighs", "PlenioHQStereoCleanup"]
