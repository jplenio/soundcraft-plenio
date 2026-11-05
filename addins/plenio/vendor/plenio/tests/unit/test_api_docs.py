"""The Song API's reference in docs/api (owner's request 2026-10-26: an API documentation good enough for third
parties): the OpenAPI copy and the field tables are made from the shipped templates by tools/api_docs.py - and
current, like the templates themselves."""

from __future__ import annotations

import json
from pathlib import Path

import api_docs

ROOT = Path(__file__).resolve().parents[2]


def test_the_api_reference_in_the_docs_is_current() -> None:
    stale = [
        path.relative_to(ROOT).as_posix()
        for path, text in api_docs.outputs().items()
        if not path.is_file() or path.read_text(encoding="utf-8") != text
    ]
    assert stale == [], f"run tools/api_docs.py: {stale}"


def test_the_guide_names_every_endpoint_of_the_api() -> None:
    guide = (ROOT / "docs" / "api" / "README.md").read_text(encoding="utf-8")
    document = json.loads((ROOT / "docs" / "api" / "openapi.json").read_text(encoding="utf-8"))
    for path, operations in document["paths"].items():
        for method in operations:
            shown = path.replace("{id}", "{id}").rstrip("/") or "/"
            assert f"`{method.upper()} {shown}" in guide, f"{method.upper()} {path}"
    # the examples are there and use the calls the guide describes
    for example in ("make_song.py", "make_song.mjs", "make_song.sh"):
        text = (ROOT / "docs" / "api" / "examples" / example).read_text(encoding="utf-8")
        assert "Idempotency-Key" in text and "wait=30" in text, example
