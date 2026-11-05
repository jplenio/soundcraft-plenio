"""How well a song came out, measured (owner's request 2026-10-29): the measures on sounds whose answer is known -
a chord against a cluster of semitones and noise, a steady beat against a random one, an ending cut off, a hole,
clipping - and what the record says; and the stars weighed from them."""

from __future__ import annotations

import numpy as np
import pytest

from plenio.core.quality import measure_audio, measure_record, rate, song_quality, summary_line

RATE = 22050


def tones(freqs: list[float], seconds: float, amplitude: float = 0.2) -> np.ndarray:
    """Notes with a few harmonics, as an instrument has them."""
    t = np.arange(int(RATE * seconds)) / RATE
    out = np.zeros_like(t)
    for f in freqs:
        for k, weight in ((1, 1.0), (2, 0.4), (3, 0.2)):
            out += weight * np.sin(2 * np.pi * f * k * t)
    return (amplitude * out / len(freqs)).astype(np.float32)


def note(midi: float) -> float:
    return float(440.0 * 2 ** ((midi - 69) / 12))


def chord(root: int, minor: bool = False) -> list[float]:
    return [note(root), note(root + (3 if minor else 4)), note(root + 7)]


def progression(seconds_each: float = 2.0) -> np.ndarray:
    """I - IV - V - I in C, twice."""
    return np.concatenate([tones(chord(r), seconds_each) for r in (60, 65, 67, 60) * 2])


def fade(x: np.ndarray, seconds: float = 1.5) -> np.ndarray:
    n = int(RATE * seconds)
    y = x.copy()
    y[-n:] *= np.linspace(1, 0, n)
    return y


def clicks(bpm: float, seconds: float, jitter: float = 0.0, seed: int = 1) -> np.ndarray:
    rng = np.random.default_rng(seed)
    x = 0.01 * rng.standard_normal(int(RATE * seconds)).astype(np.float32)
    step = 60.0 / bpm
    t = 0.2
    while t < seconds - 0.1:
        start = int((t + (rng.uniform(-jitter, jitter) if jitter else 0.0)) * RATE)
        burst = rng.standard_normal(int(0.02 * RATE)) * np.exp(-np.arange(int(0.02 * RATE)) / 80)
        x[start : start + len(burst)] += 0.8 * burst.astype(np.float32)
        t += step
    return x


def test_a_chord_sounds_clearer_than_a_cluster_and_noise() -> None:
    clean = measure_audio(fade(progression()), RATE)
    cluster = measure_audio(fade(tones([note(60), note(61), note(62), note(63)], 16.0)), RATE)
    noise = measure_audio(
        fade(np.random.default_rng(3).standard_normal(RATE * 16).astype(np.float32) * 0.1), RATE
    )
    assert clean["chords"] > 0.85 > cluster["chords"] and clean["chords"] > noise["chords"]
    assert clean["clashes"] < 0.3 < cluster["clashes"] and clean["clashes"] < noise["clashes"]
    # one key all the way: clear; noise has none
    assert clean["key"] > 0.75 > noise["key"]


def test_a_steady_beat_against_a_random_one() -> None:
    steady = measure_audio(clicks(120, 20), RATE)["beat"]
    loose = measure_audio(clicks(120, 20, jitter=0.2), RATE)["beat"]
    assert steady > 0.5 and steady > loose + 0.2


def test_an_ending_cut_off_a_hole_and_clipping() -> None:
    song = progression()
    assert measure_audio(fade(song), RATE)["ending"] < 0.1
    assert measure_audio(song, RATE)["ending"] > 0.5  # stops in the middle of the sound
    holed = fade(song.copy())
    holed[RATE * 7 : RATE * 9] = 0.0
    assert measure_audio(holed, RATE)["gaps"] == 1
    assert measure_audio(fade(song), RATE)["gaps"] == 0
    loud = np.clip(song * 8, -1, 1)
    assert measure_audio(loud, RATE)["clipped"] > 0.01
    assert measure_audio(fade(song), RATE)["clipped"] == 0.0
    # stereo, channels first; and too short to tell much
    assert measure_audio(np.stack([song, song]), RATE)["chords"] > 0.85
    assert "chords" not in measure_audio(song[: RATE * 2], RATE)


def record(**over: object) -> dict:
    base = {
        "prompt": {
            "2": {"class_type": "PlenioSongBrief", "inputs": {"length": "about 2:30", "vocals": "sung"}}
        },
        "audio": {
            "seconds": 150.0,
            "loudness": [{"integrated_lufs": -14.1, "true_peak_dbtp": -1.2, "loudness_range_lu": 6.0}],
        },
        "timing": [{"take": "master", "sung": {"written_heard": 0.92}}],
        "reports": [
            {
                "kind": "loudness",
                "data": {
                    "target": "streaming (-14 LUFS, -1 dBTP)",
                    "items": [{"target": {"integrated_lufs": -14.0, "ceiling_dbtp": -1.0}}],
                },
                "messages": [],
            },
            {
                "kind": "song_sheet",
                "data": {
                    "findings": [
                        {"severity": "warning", "message": "x", "where": "lyrics"},
                        {"severity": "info", "message": "y", "where": "score"},
                    ]
                },
                "messages": ["x"],
            },
        ],
    }
    base.update(over)
    return base


def test_what_the_record_says() -> None:
    found = measure_record(record())
    assert found["lyrics"] == pytest.approx(0.92) and found["warnings"] == 1
    assert (
        found["integrated_lufs"] == -14.1 and found["target_lufs"] == -14.0 and found["ceiling_dbtp"] == -1.0
    )
    # a master's aim named only in its choice
    club = {"kind": "loudness", "data": {"target": "club (-9 LUFS, -0.5 dBTP)", "items": []}}
    assert measure_record(record(reports=[club]))["target_lufs"] == -9.0
    assert found["length_asked"] == 150 and found["length"] == 150 and found["instrumental"] is False
    # without the timed singing: the take Best Take kept (its share of the words heard)
    best = {"kind": "best_take", "data": {"level": "high", "takes": 2, "kept": 2, "scores": [0.7, 0.88]}}
    assert measure_record(record(timing=[], reports=[best]))["lyrics"] == 0.88
    # the fidelity chosen (a level, not a measure) is not a measure
    assert "lyrics" not in measure_record(record(timing=[], reports=[], made={"lyrics_fidelity": "high"}))
    instrumental = record(
        prompt={"2": {"class_type": "PlenioSongBrief", "inputs": {"vocals": "instrumental"}}}
    )
    assert measure_record(instrumental)["instrumental"] is True


def test_the_stars_weigh_how_it_sounds_and_take_off_for_what_went_wrong() -> None:
    good = {"lyrics": 0.95, "chords": 0.78, "clashes": 0.5, "key": 0.9, "beat": 0.6, "ending": 0.0, "gaps": 0}
    assert rate(good)["stars"] == 5.0
    poor = {"lyrics": 0.5, "chords": 0.66, "clashes": 0.9, "key": 0.6, "beat": 0.1, "ending": 0.0, "gaps": 0}
    assert rate(poor)["stars"] == 1.0
    # an ending cut off and a hole take stars off
    assert rate({**good, "ending": 0.8, "gaps": 1})["stars"] == 3.0
    # what was not measured is left out: an instrumental's lyrics do not count
    no_words = rate({**good, "lyrics": 0.1, "instrumental": True})
    assert no_words["stars"] == 5.0 and all(p["key"] != "lyrics" for p in no_words["parts"])
    assert rate({})["stars"] is None
    parts = {p["key"]: p for p in rate(good)["parts"]}
    assert parts["chords"]["kind"] == "quality" and parts["ending"]["kind"] == "fault"
    assert summary_line(rate(good)) == "5 of 5 by measure"
    assert "weakest: lyrics sung as written" in summary_line(rate({**good, "lyrics": 0.6}))


def test_a_songs_quality_from_its_sound_and_record() -> None:
    found = song_quality(fade(progression()), RATE, record())
    assert found["version"] == 1 and 0 <= found["stars"] <= 5
    assert found["measures"]["lyrics"] == pytest.approx(0.92) and "chords" in found["measures"]
    # the record only (a player without the sound to read)
    assert song_quality(None, RATE, record())["measures"]["lyrics"] == pytest.approx(0.92)
