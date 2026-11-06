"""Finding the bars of a score in audio whose tempo wanders: on made-up audio, where the truth is known.

    python -I addins/plenio/backend/tests/test_beats.py
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

import numpy as np

sys.dont_write_bytecode = True

ADDIN = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("scp_beats", ADDIN / "backend" / "soundcraft_plenio" / "beats.py")
beats = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(beats)

SR = beats.SAMPLE_RATE


def wandering(score_seconds: np.ndarray, depth: float, periods: float = 1.0) -> np.ndarray:
    """A take's time for a time of the score: a slow sine around the straight line, as YuE2 renders do."""
    return score_seconds + depth * np.sin(2 * np.pi * periods * score_seconds / score_seconds[-1])


def clicks(times: np.ndarray, seconds: float, accent_every: int = 4) -> np.ndarray:
    """A short noise burst on every time, louder on every first of a bar, on a little steady noise."""
    rng = np.random.default_rng(3)
    audio = 0.002 * rng.standard_normal(int(seconds * SR)).astype(np.float32)
    burst = (rng.standard_normal(400) * np.exp(-np.arange(400) / 80)).astype(np.float32)
    for k, t in enumerate(times):
        at = int(t * SR)
        if 0 <= at < len(audio) - 400:
            audio[at : at + 400] += (1.0 if k % accent_every == 0 else 0.6) * burst
    return audio


def tone(frames: int, rate: float, chord: list[int]) -> np.ndarray:
    v = np.zeros(12)
    v[chord] = 1
    return np.tile((v - v.mean()) / np.linalg.norm(v - v.mean()), (frames, 1))


class Pulses(unittest.TestCase):
    def test_a_pulse_is_what_the_meter_feels(self) -> None:
        pulses, firsts = beats.pulses_of([(4, 4), (2, 4)])
        self.assertEqual(pulses.tolist(), [0, 1, 2, 3, 4, 5, 6])
        self.assertEqual(firsts.tolist(), [0, 4, 6])
        pulses, firsts = beats.pulses_of([(6, 8), (9, 8)])
        self.assertEqual(pulses.tolist(), [0, 1.5, 3, 4.5, 6, 7.5])
        self.assertEqual(firsts.tolist(), [0, 2, 5])
        pulses, firsts = beats.pulses_of([(7, 8), (3, 8)])
        self.assertEqual(pulses.tolist(), [0, 0.5, 1, 1.5, 2, 2.5, 3, 3.5, 5])
        self.assertEqual(firsts.tolist(), [0, 7, 8])


class Believable(unittest.TestCase):
    meters = [(4, 4), (4, 4), (4, 4)]

    def test_bars_near_the_scores_tempo_in_order(self) -> None:
        self.assertTrue(beats.believable([0.0, 2.0, 4.1, 6.0], self.meters, 120.0))

    def test_anything_else_is_not(self) -> None:
        for bars in (
            [0.0, 2.0, 4.0],  # a measure short
            [0.0, 2.0, 2.0, 4.0],  # not in order
            [0.0, 2.0, 5.0, 7.0],  # a bar far too long
            [0.0, 2.0, float("nan"), 6.0],
        ):
            self.assertFalse(beats.believable(bars, self.meters, 120.0), bars)


class FindBars(unittest.TestCase):
    def find(self, meters, bpm, depth, warp, shift=0.0, wanted=None, harmony=None, anchors=None):
        pulses, firsts = beats.pulses_of(meters)
        score = pulses * 60.0 / bpm
        truth = wandering(score, depth) + shift
        audio = clicks(truth, float(truth[-1]) + 2.0, accent_every=len(pulses) // len(meters))
        found = beats.find_bars(beats.onset_envelope(audio), meters, bpm, warp, harmony, wanted, anchors)
        return found, truth[firsts]

    def test_bars_follow_a_tempo_that_wanders(self) -> None:
        # A quarter of a second off the straight line: what no single tempo could follow.
        found, truth = self.find([(4, 4)] * 60, 84.0, 0.25, [1.0, 0.0], shift=0.5)
        self.assertLess(np.abs(found - truth)[1:-1].max(), 0.012)

    def test_mixed_meters_keep_their_measures(self) -> None:
        meters = ([(4, 4)] * 7 + [(2, 4)]) * 6
        found, truth = self.find(meters, 96.0, 0.2, [1.0, 0.0], shift=0.3)
        self.assertLess(np.abs(found - truth)[1:-1].max(), 0.015)

    def test_six_eight_goes_by_its_dotted_quarters(self) -> None:
        found, truth = self.find([(6, 8)] * 60, 100.0, 0.15, [1.0, 0.0], shift=0.3)
        self.assertLess(np.abs(found - truth)[1:-1].max(), 0.015)

    def test_a_warp_off_by_a_second_is_found_back(self) -> None:
        found, truth = self.find([(4, 4)] * 40, 90.0, 0.1, [1.0, 1.0], shift=0.5)
        self.assertLess(np.abs(found - truth)[1:-1].max(), 0.02)

    def test_the_singing_says_which_pulse_is_which(self) -> None:
        # Clicks alone repeat with every beat; a warp a beat and a bit off would stay a whole beat off.
        meters, bpm, depth = [(4, 4)] * 30, 90.0, 0.05
        pulses, firsts = beats.pulses_of(meters)
        score = pulses * 60.0 / bpm
        truth = wandering(score, depth)
        beat = 60.0 / bpm
        audio = clicks(truth, float(truth[-1]) + 2.0)
        envelope = beats.onset_envelope(audio)
        marks = np.column_stack([truth[::2], score[::2]])
        warp = [1.0, beat * 0.9]
        plain = beats.find_bars(envelope, meters, bpm, warp)
        sung = beats.find_bars(envelope, meters, bpm, warp, anchors=marks)
        self.assertGreater(np.median(np.abs(plain - truth[firsts])), beat * 0.5)
        self.assertLess(np.abs(sung - truth[firsts])[1:-1].max(), 0.02)

    def test_the_scores_notes_say_which_pulse_is_which(self) -> None:
        # Two chords in turn, bar by bar: only the right bars have the score's chord on them.
        meters, bpm, depth = [(4, 4)] * 30, 90.0, 0.05
        pulses, firsts = beats.pulses_of(meters)
        score = pulses * 60.0 / bpm
        truth = wandering(score, depth)
        beat = 60.0 / bpm
        total = float(truth[-1]) + 2.0
        audio = clicks(truth, total)
        rate = 20.0
        chroma = np.zeros((int(total * rate), 12))
        wanted = np.zeros((len(pulses), 12))
        a, b = [0, 4, 7], [2, 5, 9]
        for j, t in enumerate(truth):
            chord = a if (j // 4) % 2 == 0 else b
            v = np.zeros(12)
            v[chord] = 1
            v = (v - v.mean()) / np.linalg.norm(v - v.mean())
            start = int(t * rate)
            chroma[start : start + int(beat * rate) + 1] = v
            wanted[j] = v
        # Off by a whole beat: only the chords can tell.
        warp = [1.0, beat]
        found = beats.find_bars(beats.onset_envelope(audio), meters, bpm, warp, beats.Harmony(chroma, rate), wanted)
        self.assertLess(np.abs(found - truth[firsts])[1:-1].max(), 0.02)

    def test_where_nothing_sounds_the_tempo_goes_on(self) -> None:
        # The score starts before the audio, and the audio is silent in the middle.
        meters = [(4, 4)] * 40
        bpm = 100.0
        pulses, firsts = beats.pulses_of(meters)
        score = pulses * 60.0 / bpm
        truth = score - 1.5
        keep = (truth < 30) | (truth > 45)
        audio = clicks(truth[keep], float(truth[-1]) + 2.0)
        found = beats.find_bars(beats.onset_envelope(audio), meters, bpm, [1.0, -1.5])
        self.assertLess(np.abs(found - truth[firsts])[2:-2].max(), 0.05)
        self.assertTrue(beats.believable(found, meters, bpm))


class Measure(unittest.TestCase):
    """What the route answers, with Plenio's modules made up: what it does when the song does not meet."""

    class Score:
        meters = [(4, 4)] * 30
        tempo = 90
        vocal = ins = ()

    def modules(self, estimate=None):
        score = self.Score

        class Align:
            RATE = 20

            @staticmethod
            def estimate(_path, _text):
                return estimate

            @staticmethod
            def _audio_chroma(_path):
                return np.ones((4000, 12)) / np.sqrt(12)

            @staticmethod
            def _score_chroma(_score, count):
                return np.ones((count, 12)) / np.sqrt(12)

        class Canonical:
            @staticmethod
            def from_abc(_text):
                return score

        return Align, Canonical

    def setUp(self) -> None:
        self.load, self.match = beats._load_mono, beats._match
        pulses, _ = beats.pulses_of(self.Score.meters)
        truth = wandering(pulses * 60.0 / self.Score.tempo, 0.1)
        beats._load_mono = lambda _path: clicks(truth, float(truth[-1]) + 2.0)

    def tearDown(self) -> None:
        beats._load_mono, beats._match = self.load, self.match

    def test_a_song_that_meets_its_score_gets_its_bars(self) -> None:
        answer = beats.measure("x", "abc", [1.0, 0.0], [], *self.modules())
        self.assertEqual(answer["warp"], [1.0, 0.0])
        bars = answer["bars"]
        self.assertEqual((len(bars["score"]), len(bars["audio"]), len(bars["meters"])), (31, 31, 30))
        self.assertEqual(bars["meters"][0], [4, 4])
        self.assertAlmostEqual(bars["score"][1], 4 * 60 / 90, places=5)

    def test_without_a_warp_the_estimate_gives_it(self) -> None:
        answer = beats.measure("x", "abc", None, [], *self.modules({"warp": [1.0, 0.0]}))
        self.assertEqual(answer["warp"], [1.0, 0.0])
        self.assertIsNotNone(answer["bars"])

    def test_without_a_warp_or_an_estimate_nothing_is_said(self) -> None:
        self.assertEqual(beats.measure("x", "abc", None, [], *self.modules()), {"warp": None, "bars": None})

    def test_bars_the_notes_do_not_fit_are_not_believed(self) -> None:
        # Clearly worse on the bars than on the straight line.
        results = iter([0.2, 0.3])
        beats._match = lambda *_args: next(results)
        answer = beats.measure("x", "abc", [1.0, 0.0], [], *self.modules())
        self.assertIsNone(answer["bars"])
        self.assertEqual(answer["warp"], [1.0, 0.0])


if __name__ == "__main__":
    unittest.main()
