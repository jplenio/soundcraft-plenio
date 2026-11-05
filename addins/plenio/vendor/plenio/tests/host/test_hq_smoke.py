"""HQ 1 and HQ 2 with the released UniverSR weights on local hardware (V3).

A real take (the sample in ``assets/sound-samples`` or ``PLENIO_LEGACY_SAMPLE``), 20 s of it, through
HQ 1 · Stereo Cleanup and HQ 2 · Regenerate Highs on the GPU. Needs ``PLENIO_SMOKE=1``,
``PLENIO_COMFYUI_ROOT`` and ``PLENIO_MODELS_DIR`` with ``audio_sr/pytorch_model.bin``.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest

from harness import PACKAGE_NAME, PROJECT, ComfyServer, copy_package
from plenio.core.audio import hq

pytestmark = [pytest.mark.host, pytest.mark.smoke]

MODELS = Path(os.environ.get("PLENIO_MODELS_DIR", "") or "missing-models-dir")
SAMPLE = Path(
    os.environ.get("PLENIO_LEGACY_SAMPLE", "")
    or PROJECT / "assets" / "sound-samples" / "Example Album - A Feeling With No Address.mp3"
)


@pytest.fixture(scope="module")
def gpu_server(tmp_path_factory: pytest.TempPathFactory, comfy_path: Path) -> Iterator[ComfyServer]:
    if not (MODELS / "audio_sr" / "pytorch_model.bin").exists():
        pytest.skip(f"the UniverSR weights are not under {MODELS / 'audio_sr'}")
    if not SAMPLE.exists():
        pytest.skip(f"sample not found: {SAMPLE} (set PLENIO_LEGACY_SAMPLE)")
    base = tmp_path_factory.mktemp("comfy-hq")
    (base / "custom_nodes").mkdir()
    copy_package(base / "custom_nodes")
    (base / "input").mkdir()
    shutil.copy2(SAMPLE, base / "input" / ("hq-take" + SAMPLE.suffix))
    server = ComfyServer(
        comfy_path,
        base,
        node_packs=[PACKAGE_NAME],
        cpu=False,
        models_dir=MODELS,
        extra_env={"PLENIO_OFFLINE": "1"},
    )
    server.start()
    yield server
    server.stop()


def test_hq1_and_hq2_with_the_released_universr(gpu_server: ComfyServer) -> None:
    standard = hq.PRESET_LABELS[hq.STANDARD]
    prompt = {
        "1": {"class_type": "LoadAudio", "inputs": {"audio": "hq-take" + SAMPLE.suffix}},
        "2": {
            "class_type": "TrimAudioDuration",
            "inputs": {"audio": ["1", 0], "start_index": 30.0, "duration": 20.0},
        },
        "3": {"class_type": "PlenioHQStereoCleanup", "inputs": {"audio": ["2", 0], "preset": standard}},
        "4": {
            "class_type": "PlenioAudioModelLoader",
            "inputs": {"kind": "super-resolution", "kind.model": "pytorch_model.bin"},
        },
        "5": {
            "class_type": "PlenioHQRegenerateHighs",
            "inputs": {"audio": ["3", 0], "model": ["4", 0], "preset": standard, "seed": 0},
        },
        "6": {"class_type": "PreviewAudio", "inputs": {"audio": ["5", 0]}},
    }
    entry = gpu_server.run(prompt, timeout=1800.0)
    first = entry["outputs"]["3"]["plenio_summary"][0]["markdown"]
    second = entry["outputs"]["5"]["plenio_summary"][0]["markdown"]
    print(first, second, sep="\n")
    assert first.startswith("**HQ 1 · Stereo Cleanup: standard")
    assert "UniverSR from 8 kHz (4 steps), new highs from 8.2 kHz" in second
    # the model generated highs: without them the envelope match leaves 15 % of the original's (-16 dB)
    highs = float(second.split("; highs ")[1].split(" dB")[0])
    assert highs > -10.0, second
