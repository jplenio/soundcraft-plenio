"""Check Sung Words is retired (owner's rule 2026-10-24: the lyrics as sung stay as heard). Its nodes stay so that a
workflow saved with the block still runs - they ask no writer and leave the record as it is."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.comfy


def node(name: str) -> Any:
    from plenio.comfy import nodes

    return next(n for n in nodes.NODES if n.GET_SCHEMA().node_id == name)


def test_the_retired_block_asks_nothing_and_changes_nothing(comfy_path: Path, tmp_path: Path) -> None:
    record = tmp_path / "Song.plenio.json"
    text = json.dumps(
        {"schema": "plenio.release/1", "timing": [{"sung": {"lines": [{"text": "We walk doun"}]}}]}
    )
    record.write_text(text, encoding="utf-8")
    compose, apply = node("PlenioComposeSungCheck"), node("PlenioApplySungCheck")
    assert compose.GET_SCHEMA().is_deprecated and apply.GET_SCHEMA().is_deprecated
    assert compose.execute(record=str(record)).result[0] == ""
    assert apply.check_lazy_status(record=str(record)) == []
    out = apply.execute(record=str(record))
    assert out.result[0] == str(record) and out.result[1].status.value == "skipped"
    assert record.read_text(encoding="utf-8") == text
