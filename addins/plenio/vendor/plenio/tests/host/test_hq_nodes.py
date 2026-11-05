"""Audio HQ 1-3 in a real ComfyUI server: the chain with a fake super-resolution model, *auto* following a
real Song Brief, *custom* fields, and refused input. The real model and the listening are the owner's."""

from __future__ import annotations

from typing import Any

import pytest

from harness import ComfyServer, ExecutionFailedError, Log
from plenio.core.audio import hq

pytestmark = pytest.mark.host

SECONDS, RATE = 3.0, 48000


def events(log: Log, node: str) -> list[dict[str, Any]]:
    return [e for e in log.events() if e["node"] == node]


def chain(
    stereo: dict[str, Any] | None = None,
    highs: dict[str, Any] | None = None,
    dereverb: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "1": {
            "class_type": "PlenioTestFakeAudio",
            "inputs": {"seconds": SECONDS, "variant": 2, "rate": RATE, "broadband": True},
        },
        "2": {
            "class_type": "PlenioHQStereoCleanup",
            "inputs": {"audio": ["1", 0], **(stereo or {"preset": hq.AUTO})},
        },
        "3": {"class_type": "PlenioTestFakeAudioModel", "inputs": {"kind": "super-resolution"}},
        "4": {
            "class_type": "PlenioHQRegenerateHighs",
            "inputs": {"audio": ["2", 0], "model": ["3", 0], "seed": 5, **(highs or {"preset": hq.AUTO})},
        },
        "5": {
            "class_type": "PlenioHQDeReverb",
            "inputs": {"audio": ["4", 0], **(dereverb or {"preset": hq.AUTO})},
        },
        "6": {"class_type": "PlenioTestAudioProbe", "inputs": {"audio": ["5", 0], "name": "hq"}},
    }


def summary(entry: dict[str, Any], node: str) -> str:
    return str(entry["outputs"][node]["plenio_summary"][0]["markdown"])


def test_the_three_stages_keep_rate_and_length(server: ComfyServer, log: Log) -> None:
    entry = server.run(chain())
    probe = events(log, "probe")[-1]
    assert probe["rate"] == RATE and probe["shape"] == [1, 2, int(SECONDS * RATE)]
    # auto without a brief: standard, and the summary says why
    for node, title in (
        ("2", "HQ 1 · Stereo Cleanup"),
        ("4", "HQ 2 · Regenerate Highs"),
        ("5", "HQ 3 · De-Reverb"),
    ):
        text = summary(entry, node)
        assert text.startswith(f"**{title}: standard (auto: no brief connected)"), text
    assert "fake-sr" in summary(entry, "4")  # the connected model ran
    assert [e["kind"] for e in events(log, "audio_model")] == ["super-resolution"]


def test_auto_follows_the_brief_and_marks_untested_profiles(server: ComfyServer) -> None:
    prompt = chain()
    prompt["7"] = {
        "class_type": "PlenioSongBrief",
        "inputs": {
            "mode": "one song, stop to review",
            "template": "none",
            "description": "",
            "genre": "thrash metal",
            "mood": "",
            "tempo": "",
            "length": "short (about 1:30)",
            "vocals": "sung",
            "vocals.language": "English",
            "vocals.voice": "",
            "vocals.theme": "",
            "key": "",
            "meter": "",
            "arrangement": "off",
            "genre_closeness": 60,
            "lines_under_singing": False,
        },
    }
    for node in ("2", "4", "5"):
        prompt[node]["inputs"]["brief"] = ["7", 0]
    entry = server.run(prompt)
    text = summary(entry, "2")
    assert "strong (auto: genre 'thrash metal' (metal))" in text and "provisional" in text
    assert "side high-cut 9.5 kHz" in text  # the strong profile's numbers


def test_custom_uses_the_fields(server: ComfyServer) -> None:
    entry = server.run(
        chain(
            stereo={
                "preset": hq.CUSTOM,
                "preset.side_highcut_hz": 12000.0,
                "preset.side_cleanup": 0.3,
                "preset.warmth": 0.0,
            },
            highs={
                "preset": hq.CUSTOM,
                "preset.from_hz": 12200.0,
                "preset.new_share": 0.5,
                "preset.level_match": 1.0,
            },
            dereverb={"preset": hq.CUSTOM, "preset.dereverb": 0.2, "preset.phase_lock": 0.0},
        )
    )
    assert "custom - side high-cut 12 kHz, cleanup 30%, warmth 0" in summary(entry, "2")
    assert "new highs from 12.2 kHz (50%, level 1)" in summary(entry, "4")
    assert "de-reverb 20%, phase lock 0%" in summary(entry, "5")


def test_an_unknown_preset_is_refused(server: ComfyServer) -> None:
    """ComfyUI drops a DynamicCombo value it has no option for; the node then says what to choose."""
    with pytest.raises(ExecutionFailedError) as refused:
        server.run(chain(stereo={"preset": "louder"}))
    assert "The preset is missing or unknown" in str(refused.value) and hq.AUTO in str(refused.value)


def test_with_hq_mastering_off_hq2_passes_the_song_and_its_model_never_loads(
    server: ComfyServer, log: Log
) -> None:
    """Owner's request 2026-10-22: off, UniverSR does not run - HQ 2 does not even ask for its model (lazy),
    so the loader does not run and a model file that is not installed is no error."""
    prompt = chain(highs={"preset": hq.AUTO, "hq_mastering": False})
    prompt["8"] = {"class_type": "PlenioTestAudioProbe", "inputs": {"audio": ["2", 0], "name": "before"}}
    prompt["9"] = {"class_type": "PlenioTestAudioProbe", "inputs": {"audio": ["4", 0], "name": "after"}}
    entry = server.run(prompt)
    assert (
        summary(entry, "4") == "**HQ 2 · Regenerate Highs: off - HQ mastering is off, UniverSR did not run**"
    )
    assert entry["outputs"]["4"]["plenio_summary"][0]["status"] == "skipped"
    assert not events(log, "audio_model")  # the fake loader never ran
    before, after = (
        next(e for e in reversed(log.events()) if e.get("name") == n) for n in ("before", "after")
    )
    assert (before["shape"], before["peak"], before["rms"]) == (after["shape"], after["peak"], after["rms"])
    # the real loader with a file this server does not have: off runs, on says where the file goes
    missing = chain(highs={"preset": hq.AUTO, "hq_mastering": False})
    missing["3"] = {
        "class_type": "PlenioAudioModelLoader",
        "inputs": {"kind": "super-resolution", "kind.model": "pytorch_model.bin"},
    }
    server.run(missing)
    missing["4"]["inputs"]["hq_mastering"] = True
    with pytest.raises(ExecutionFailedError) as refused:
        server.run(missing)
    assert "pytorch_model.bin" in str(refused.value) and "models/audio_sr" in str(refused.value)
    # the switch node gives its value on (off by default; Enhance & Master sets it on); the page draws it as a
    # card (PLENIO_FINISH_SWITCH)
    info = server.get("/object_info/PlenioHQMastering")["PlenioHQMastering"]
    kind, switch = info["input"]["required"]["hq_mastering"]
    assert kind == "PLENIO_FINISH_SWITCH" and switch["default"] is False


def test_the_node_definitions(server: ComfyServer) -> None:
    for node_id in ("PlenioHQStereoCleanup", "PlenioHQRegenerateHighs", "PlenioHQDeReverb"):
        info = server.get(f"/object_info/{node_id}")[node_id]
        preset = info["input"]["required"]["preset"]
        assert [option["key"] for option in preset[1]["options"]] == list(hq.PRESETS), node_id
        assert info["category"] == "Plenio/Mastering"
    highs = server.get("/object_info/PlenioHQRegenerateHighs")["PlenioHQRegenerateHighs"]
    assert highs["input"]["optional"]["seed"][1]["control_after_generate"] == "fixed"


def test_hq2_runs_the_vendored_universr_at_its_16_khz_condition(server: ComfyServer, log: Log) -> None:
    """The real adapter (a tiny checkpoint, CPU): the 8.2 kHz crossover picks the 16 kHz input condition."""
    pytest.importorskip("torch", reason="the adapter needs PyTorch")
    if not (server.base / "models" / "audio_sr" / "tiny-universr.bin").is_file():
        pytest.skip("the tiny UniverSR checkpoint could not be built (torch/einops missing)")
    prompt = chain(highs={"preset": hq.PRESET_LABELS[hq.STANDARD]})
    prompt["1"]["inputs"]["seconds"] = 1.5
    prompt["3"] = {
        "class_type": "PlenioAudioModelLoader",
        "inputs": {"kind": "super-resolution", "kind.model": "tiny-universr.bin"},
    }
    entry = server.run(prompt, timeout=900.0)
    probe = events(log, "probe")[-1]
    assert probe["rate"] == RATE and probe["shape"] == [1, 2, int(1.5 * RATE)]
    assert "UniverSR from 8 kHz (4 steps), new highs from 8.2 kHz (85%, level 0.9)" in summary(entry, "4")
