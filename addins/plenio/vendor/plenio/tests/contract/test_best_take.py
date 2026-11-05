"""Best Take: a further take is asked for only while the best take so far sang less than 96 % of its lyrics as
written - with high fidelity the second, with highest also the third (2026-10-25)."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.comfy

LYRICS = "[Verse]\nWe walk down the riverside\n\n[Chorus]\nHold me close tonight"


def best_take(monkeypatch: pytest.MonkeyPatch, shares: dict[str, float]) -> Any:
    """The node, its hearing replaced: each take (a string here) sings ``shares[take]`` of the lyrics."""
    from plenio.comfy import nodes
    from plenio.comfy.nodes import best_take as module

    monkeypatch.setattr(module, "score", lambda audio, lyrics, brief: shares[audio])
    return next(n for n in nodes.NODES if n.GET_SCHEMA().node_id == "PlenioBestTake")


def brief(fidelity: str) -> Any:
    from plenio.core.brief import SongBrief

    return replace(SongBrief(), fidelity=fidelity)


@pytest.mark.parametrize("fidelity", ["high", "highest"])
def test_a_first_take_of_96_percent_is_close_enough(
    comfy_path: Path, monkeypatch: pytest.MonkeyPatch, fidelity: str
) -> None:
    node = best_take(monkeypatch, {"one": 0.96})
    assert node.check_lazy_status(take="one", lyrics=LYRICS, brief=brief(fidelity)) == []
    out = node.execute(take="one", lyrics=LYRICS, brief=brief(fidelity))
    assert out.result[0] == "one" and out.result[1].data["takes"] == 1


def test_high_renders_the_second_below_96_percent_and_keeps_the_better(
    comfy_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    node = best_take(monkeypatch, {"one": 0.80, "two": 0.93})
    assert node.check_lazy_status(take="one", lyrics=LYRICS, brief=brief("high")) == ["second"]
    assert node.check_lazy_status(take="one", lyrics=LYRICS, brief=brief("high"), second="two") == []
    out = node.execute(take="one", lyrics=LYRICS, brief=brief("high"), second="two")
    assert out.result[0] == "two" and out.result[1].data["scores"] == [0.8, 0.93]


def test_highest_renders_a_third_only_when_neither_reached_96_percent(
    comfy_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    node = best_take(monkeypatch, {"one": 0.80, "two": 0.97, "low": 0.90})
    assert node.check_lazy_status(take="one", lyrics=LYRICS, brief=brief("highest")) == ["second"]
    assert node.check_lazy_status(take="one", lyrics=LYRICS, brief=brief("highest"), second="two") == []
    assert node.check_lazy_status(take="one", lyrics=LYRICS, brief=brief("highest"), second="low") == [
        "third"
    ]


def test_standard_and_an_instrumental_never_ask(comfy_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    node = best_take(monkeypatch, {"one": 0.10})
    assert node.check_lazy_status(take="one", lyrics=LYRICS, brief=brief("standard")) == []
    assert node.check_lazy_status(take="one", lyrics="", brief=brief("highest")) == []
