"""A cover's lyrics from the mix or the vocal stem (owner 2026-10-24: the stem only where it hears better): the
hearing the ASR was clearly more confident of is kept."""

from __future__ import annotations

import math

from plenio.core.alignment import AsrWord
from plenio.core.asr import STEM_MARGIN, confidence, prefer_stem


def heard(*probabilities: float) -> list[AsrWord]:
    return [AsrWord(k, k + 0.5, f"w{k}", p) for k, p in enumerate(probabilities)]


def test_confidence_is_the_mean_log_probability() -> None:
    assert confidence([]) is None
    assert math.isclose(confidence(heard(1.0, math.exp(-1))) or 0.0, -0.5)
    assert confidence(heard(0.0)) == math.log(1e-4)  # a word at p 0 does not make it minus infinity


def test_the_stem_is_taken_only_when_heard_clearly_better() -> None:
    mix = heard(0.9, 0.8, 0.4)
    assert prefer_stem(mix, heard(0.95, 0.9, 0.9))
    assert not prefer_stem(mix, mix)
    near = [AsrWord(w.start, w.end, w.word, w.p * math.exp(STEM_MARGIN / 2)) for w in mix]
    assert not prefer_stem(mix, near)  # better, but within the margin: the recording stays
    assert not prefer_stem(mix, [])
    assert prefer_stem([], mix)
