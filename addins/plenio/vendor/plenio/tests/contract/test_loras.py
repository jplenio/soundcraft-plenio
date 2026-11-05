"""YuE2 LoRAs (GitHub issue 2026-10-28): the original layout joined exactly into ComfyUI's fused projections,
every slot empty leaving YuE2 untouched, and whatever does not fit - another model's LoRA, a broken file, a weight
of another shape, values that are not numbers - left out and said, never a stopped run."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

pytestmark = pytest.mark.comfy
torch = pytest.importorskip("torch")

BLOCK = {
    "q": "self_attn",
    "k": "self_attn",
    "v": "self_attn",
    "o": "self_attn",
    "gate": "mlp",
    "up": "mlp",
    "down": "mlp",
}

HIDDEN = (
    8  # the tests' input width (YuE2's is 2048); the output sizes are YuE2's: the fused rows depend on them
)


def original(
    rank: int = 2, *, nar: bool = False, parts: tuple[str, ...] = ("q", "k", "v", "o", "gate", "up", "down")
) -> dict[str, Any]:
    """A LoRA in m-a-p's layout for layer 0: separate projections, ``lora_A`` / ``lora_B`` without ``.weight``."""
    out_sizes = {"q": 2048, "k": 1024, "v": 1024, "o": 2048, "gate": 6144, "up": 6144, "down": 2048}
    in_sizes = {"o": 2048, "down": 6144}
    block = {
        "q": "self_attn",
        "k": "self_attn",
        "v": "self_attn",
        "o": "self_attn",
        "gate": "mlp",
        "up": "mlp",
        "down": "mlp",
    }
    generator = torch.Generator().manual_seed(7)
    state: dict[str, Any] = {}
    for part in parts:
        name = f"model.layers.0.{'nar_' if nar else ''}{block[part]}.{part}_proj"
        state[f"{name}.lora_A"] = torch.randn(rank, in_sizes.get(part, HIDDEN), generator=generator)
        state[f"{name}.lora_B"] = torch.randn(out_sizes[part], rank, generator=generator)
    return state


def delta(state: dict[str, Any], name: str) -> Any:
    up, down = state[f"{name}.lora_up.weight"], state[f"{name}.lora_down.weight"]
    return (up @ down) * (float(state[f"{name}.alpha"]) / down.shape[0])


def test_the_original_layout_is_joined_exactly() -> None:
    from plenio.comfy.loras import is_original, join_original

    source = original()
    assert is_original(source)
    joined, problems = join_original(source, scale=1.5)
    assert problems == []

    def a(part: str) -> Any:
        return source[f"model.layers.0.{BLOCK[part]}.{part}_proj.lora_A"]

    def b(part: str) -> Any:
        return source[f"model.layers.0.{BLOCK[part]}.{part}_proj.lora_B"]

    qkv = delta(joined, "text_encoders.model.layers.0.self_attn.qkv_proj")
    expected = torch.cat([b(p) @ a(p) for p in ("q", "k", "v")]) * 1.5
    assert qkv.shape == (4096, HIDDEN) and torch.allclose(qkv, expected, atol=1e-4)
    gate_up = delta(joined, "text_encoders.model.layers.0.mlp.gate_up_proj")
    assert torch.allclose(gate_up, torch.cat([b("gate") @ a("gate"), b("up") @ a("up")]) * 1.5, atol=1e-4)
    for part, fused in (("o", "self_attn.o_proj"), ("down", "mlp.down_proj")):
        assert torch.allclose(
            delta(joined, f"text_encoders.model.layers.0.{fused}"), b(part) @ a(part) * 1.5, atol=1e-4
        )
    # ComfyUI's own layout is not joined again
    assert not is_original(
        {"text_encoders.model.layers.0.self_attn.qkv_proj.lora_up.weight": torch.zeros(4096, 2)}
    )


def test_the_acoustic_half_and_a_missing_projection() -> None:
    from plenio.comfy.loras import join_original

    source = original(nar=True, parts=("q", "v"))
    source["model.vae2llm.lora_A"] = torch.ones(2, 64)
    source["model.vae2llm.lora_B"] = torch.ones(2048, 2)
    source["model.layers.0.nar_self_attn.q_proj.alpha"] = torch.tensor(4.0)  # its own scale: 4 / rank 2 = 2
    joined, problems = join_original(source)
    assert problems == []
    qkv = delta(joined, "diffusion_model.model.layers.0.self_attn.qkv_proj")
    q = (
        source["model.layers.0.nar_self_attn.q_proj.lora_B"]
        @ source["model.layers.0.nar_self_attn.q_proj.lora_A"]
    )
    assert torch.allclose(qkv[:2048], q * 2, atol=1e-4)
    assert torch.count_nonzero(qkv[2048:3072]) == 0  # no k: its rows stay as they are
    assert "diffusion_model.vae2llm.lora_up.weight" in joined


def test_a_projection_of_another_size_is_named() -> None:
    from plenio.comfy.loras import join_original

    source = original(parts=("q", "k"))
    source["model.layers.0.self_attn.q_proj.lora_B"] = torch.zeros(1024, 2)
    joined, problems = join_original(source)
    assert not any("qkv_proj" in key for key in joined)
    assert problems and "of another size" in problems[0]


class Patcher:
    """Enough of ComfyUI's ModelPatcher / CLIP for the node: a state, clone, add_patches."""

    def __init__(self, state: dict[str, Any], clip: bool) -> None:
        self.state = state
        self.patches: dict[Any, float] = {}
        holder = SimpleNamespace(state_dict=lambda: state)
        if clip:
            self.cond_stage_model = holder
        else:
            self.model = holder

    def clone(self) -> Patcher:
        twin = Patcher(self.state, hasattr(self, "cond_stage_model"))
        twin.patches = dict(self.patches)
        return twin

    def add_patches(self, patches: dict[Any, Any], strength: float) -> list[Any]:
        self.patches.update({key: strength for key in patches})
        return list(patches)


@pytest.fixture
def yue2(comfy_path: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> SimpleNamespace:
    """A small YuE2: layer 0's fused projections, the files of models/loras in ``tmp_path``."""
    import comfy.lora
    import folder_paths

    model_state = {
        "diffusion_model.model.layers.0.self_attn.qkv_proj.weight": torch.zeros(4096, HIDDEN),
        "diffusion_model.model.layers.0.self_attn.o_proj.weight": torch.zeros(2048, 2048),
    }
    clip_state = {
        "model.layers.0.self_attn.qkv_proj.weight": torch.zeros(4096, HIDDEN),
        "model.layers.0.mlp.gate_up_proj.weight": torch.zeros(12288, HIDDEN),
        "model.layers.0.mlp.down_proj.weight": torch.zeros(2048, 6144),
        "model.layers.0.self_attn.o_proj.weight": torch.zeros(2048, 2048),
    }
    monkeypatch.setattr(
        comfy.lora,
        "model_lora_keys_unet",
        lambda model, key_map={}: {k[: -len(".weight")]: k for k in model.state_dict()},
    )
    monkeypatch.setattr(
        comfy.lora,
        "model_lora_keys_clip",
        lambda model, key_map={}: {f"text_encoders.{k[: -len('.weight')]}": k for k in model.state_dict()},
    )
    monkeypatch.setattr(
        folder_paths,
        "get_full_path",
        lambda kind, name: str(tmp_path / name) if (tmp_path / name).exists() else None,
    )
    return SimpleNamespace(
        model=Patcher(model_state, clip=False), clip=Patcher(clip_state, clip=True), folder=tmp_path
    )


def save(folder: Path, name: str, state: dict[str, Any]) -> str:
    from safetensors.torch import save_file

    save_file({k: v.contiguous() for k, v in state.items()}, str(folder / name))
    return name


def run(yue2: SimpleNamespace, **slots: Any) -> tuple[Any, Any, str, str]:
    from plenio.comfy.nodes.loras import PlenioLoras

    output = PlenioLoras.execute(yue2.model, yue2.clip, **slots)
    summary = output.ui["plenio_summary"][0]
    return output.result[0], output.result[1], summary["status"], summary["markdown"]


def test_every_slot_empty_leaves_yue2_as_loaded(yue2: SimpleNamespace) -> None:
    model, clip, status, markdown = run(yue2, lora_1="none", strength_1=1.0, lora_2="none")
    assert model is yue2.model and clip is yue2.clip
    assert status == "ok" and "YuE2 as loaded" in markdown
    model, clip, _status, markdown = run(
        yue2, lora_1=save(yue2.folder, "x.safetensors", original()), strength_1=0.0
    )
    assert model is yue2.model and clip is yue2.clip and "strength 0 - off" in markdown


def test_a_plan_lora_in_either_layout_patches_the_planner_only(yue2: SimpleNamespace) -> None:
    native = save(
        yue2.folder,
        "inst_comfyui.safetensors",
        {
            "text_encoders.model.layers.0.self_attn.qkv_proj.lora_up.weight": torch.ones(4096, 6) * 0.01,
            "text_encoders.model.layers.0.self_attn.qkv_proj.lora_down.weight": torch.ones(6, HIDDEN) * 0.01,
        },
    )
    joined = save(yue2.folder, "rock-ar.safetensors", original())
    model, clip, status, markdown = run(yue2, lora_1=native, strength_1=1.0, lora_2=joined, strength_2=0.5)
    assert model is yue2.model and clip is not yue2.clip
    assert status == "ok" and "**2 of 2 LoRA(s) applied**" in markdown
    assert "rock-ar.safetensors at 0.5: 4 for the plan (original YuE2 layout" in markdown
    assert clip.patches["model.layers.0.self_attn.qkv_proj.weight"] == 0.5  # the later one's strength on it
    assert yue2.clip.patches == {}  # the CLIP that came in is not changed


def test_what_does_not_fit_is_left_out_and_the_rest_applies(yue2: SimpleNamespace) -> None:
    flux = save(
        yue2.folder,
        "flux.safetensors",
        {"lora_unet_double_blocks_0_img_attn_qkv.lora_up.weight": torch.ones(3, 2)},
    )
    broken = yue2.folder / "broken.safetensors"
    broken.write_bytes(b"not a safetensors file")
    odd = save(
        yue2.folder,
        "odd.safetensors",
        {
            "text_encoders.model.layers.0.self_attn.o_proj.lora_up.weight": torch.ones(2048, 2),
            "text_encoders.model.layers.0.self_attn.o_proj.lora_down.weight": torch.ones(
                2, 99
            ),  # not 2048 wide
        },
    )
    nan = original(nar=True, parts=("o",))
    nan["model.layers.0.nar_self_attn.o_proj.lora_B"][0, 0] = float("nan")
    sound = save(yue2.folder, "nan-nar.safetensors", nan)
    model, clip, status, markdown = run(
        yue2, lora_1=flux, lora_2="broken.safetensors", lora_3=odd, lora_4=sound
    )
    assert model is yue2.model and clip is yue2.clip  # nothing applied
    assert status == "warning" and "**0 of 4 LoRA(s) applied**" in markdown
    assert "flux.safetensors: left out - none of its weights belongs to YuE2" in markdown
    assert "broken.safetensors: left out - cannot be read" in markdown
    assert "1 weight(s) of another shape than this model's" in markdown
    assert "1 weight(s) with values that are not numbers" in markdown
    # a LoRA that is not there any more
    _model, _clip, _status, markdown = run(yue2, lora_1="gone.safetensors")
    assert "gone.safetensors: left out - not found in models/loras" in markdown


def test_a_sound_lora_patches_the_acoustic_model(yue2: SimpleNamespace) -> None:
    sound = save(yue2.folder, "rock-nar.safetensors", original(nar=True, parts=("q", "k", "v", "o")))
    model, clip, status, markdown = run(yue2, lora_1=sound, strength_1=1.0)
    assert clip is yue2.clip and model is not yue2.model
    assert set(model.patches) == {
        "diffusion_model.model.layers.0.self_attn.qkv_proj.weight",
        "diffusion_model.model.layers.0.self_attn.o_proj.weight",
    }
    assert status == "ok" and "2 for the sound" in markdown
