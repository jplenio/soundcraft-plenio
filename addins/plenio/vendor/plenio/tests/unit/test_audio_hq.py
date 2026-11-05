"""Audio HQ 1-3 (``core.audio.hq``): presets and genre profiles, the STFT pair, and each stage's contract."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from types import SimpleNamespace

import numpy as np
import pytest

from plenio.core.audio import hq
from plenio.core.errors import PlenioUserError

RATE = 48000


def brief(genre: str = "", template: str = "") -> SimpleNamespace:
    return SimpleNamespace(genre=genre, template=template)


def song(seconds: float = 3.0, rate: int = RATE, seed: int = 1) -> np.ndarray:
    """A stereo test song: tones, a decaying noise burst every half second and wide (uncorrelated) hiss."""
    rng = np.random.default_rng(seed)
    t = np.arange(int(seconds * rate)) / rate
    tones = sum(np.sin(2 * np.pi * f * t) / (1 + i) for i, f in enumerate((220.0, 440.0, 1320.0, 3300.0)))
    burst = rng.standard_normal(t.size) * np.exp(-(t % 0.5) / 0.05)
    left = 0.2 * tones + 0.05 * burst + 0.01 * rng.standard_normal(t.size)
    right = 0.2 * tones + 0.05 * burst + 0.01 * rng.standard_normal(t.size)
    return np.stack([left, right])


def band_db(x: np.ndarray, low: float, high: float, rate: int = RATE) -> float:
    """The channels' mean power in a band (not the mono mix: new highs may be more or less correlated)."""
    spectrum = (np.abs(np.fft.rfft(x, axis=-1)) ** 2).mean(axis=0)
    freqs = np.fft.rfftfreq(x.shape[1], 1 / rate)
    band = (freqs >= low) & (freqs < high)
    return float(10 * np.log10(spectrum[band].sum() + 1e-30))


# --- presets and profiles -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("genre", "template", "profile"),
    [
        ("thrash metal", "", hq.STRONG),
        ("folk metal", "", hq.STRONG),  # the strong words come first
        ("pop-punk / emo", "", hq.STRONG),
        ("synth-pop", "", hq.WIDE),
        ("neurofunk", "edm/neurofunk-dnb-instrumental", hq.WIDE),
        ("drum & bass", "", hq.WIDE),
        ("chillout / downtempo", "", hq.WIDE),
        ("neoclassical", "", hq.GENTLE),
        # the templates' default song: pop, the profile of the owner's listening test (2026-10-22)
        ("singer-songwriter", "pop/singer-songwriter-acoustic-vocal", hq.STANDARD),
        ("smooth jazz", "", hq.GENTLE),
        ("hip-hop / rap", "", hq.STANDARD),
        ("k-pop", "asian/kpop-vocal", hq.STANDARD),
        ("", "metal/doom-metal-instrumental", hq.STRONG),  # no genre words: the template's family
        ("", "classical/cello-and-piano", hq.GENTLE),
        ("my own thing", "", hq.STANDARD),
    ],
)
def test_auto_picks_the_profile_from_the_genre(genre: str, template: str, profile: str) -> None:
    chosen, why = hq.profile_for(brief(genre, template))
    assert chosen == profile, why


def test_auto_without_a_brief_or_genre_is_standard_and_says_why() -> None:
    assert hq.profile_for(None) == (hq.STANDARD, "no brief connected")
    assert hq.profile_for(brief()) == (hq.STANDARD, "the brief names no genre")
    profile, why = hq.chosen_profile(hq.AUTO, brief("thrash metal"))
    assert profile == hq.STRONG and why.startswith("auto: genre 'thrash metal'")


def test_words_match_at_word_starts_only() -> None:
    # "house" in "lighthouse" is no genre word; "electro" in "electronic" is
    assert hq.profile_for(brief("lighthouse ballads"))[0] == hq.STANDARD
    assert hq.profile_for(brief("electronic"))[0] == hq.WIDE


def test_every_preset_resolves_and_custom_uses_the_fields() -> None:
    assert hq.PRESETS[0] == hq.AUTO and hq.PRESETS[-1] == hq.CUSTOM
    assert len(set(hq.PRESETS)) == len(hq.PRESETS) == 6
    for profile, label in hq.PRESET_LABELS.items():
        assert label.startswith(profile)
        for table in (hq.STEREO_PROFILES, hq.REGENERATE_PROFILES, hq.DEREVERB_PROFILES):
            settings, chosen, why = hq.resolve(label, None, table, None)
            assert chosen == profile and why == "preset" and settings == table[profile]
    custom = hq.StereoCleanup(9000.0, 0.5, 0.1)
    assert hq.resolve(hq.CUSTOM, None, hq.STEREO_PROFILES, custom) == (custom, None, "custom")
    with pytest.raises(PlenioUserError, match="Unknown preset"):
        hq.chosen_profile("loud", None)


def test_every_profile_regenerates_from_the_crossover_the_owner_heard() -> None:
    """2026-10-22: a gentle profile from 12.2 kHz changed a singer-songwriter song too little to hear."""
    assert {settings.from_hz for settings in hq.REGENERATE_PROFILES.values()} == {8200.0}


def test_the_envelope_smoothing_equals_scipys_gaussian_filter() -> None:
    from scipy.ndimage import gaussian_filter1d

    values = np.random.default_rng(3).standard_normal(48000) ** 2
    assert np.allclose(
        hq._gaussian_smooth(values, 1920.0), gaussian_filter1d(values, 1920.0), rtol=0, atol=1e-12
    )


def test_standard_is_the_proposal_the_owner_listened_to() -> None:
    """The listening test of 2026-10-21 used the proposal's defaults; standard must stay exactly them."""
    assert hq.STEREO_PROFILES[hq.STANDARD] == hq.StereoCleanup(10500.0, 0.65, 0.18)
    assert hq.REGENERATE_PROFILES[hq.STANDARD] == hq.RegenerateHighs(8200.0, 0.85, 0.90)
    assert hq.DEREVERB_PROFILES[hq.STANDARD] == hq.DeReverb(0.45, 0.55)
    for table in (hq.STEREO_PROFILES, hq.REGENERATE_PROFILES, hq.DEREVERB_PROFILES):
        assert set(table) == set(hq.PROFILES)
        for settings in table.values():
            assert settings.checked() == settings


# --- the STFT pair ------------------------------------------------------------------------------


@pytest.mark.parametrize(("size", "hop"), [(2048, 512), (4096, 1024)])
def test_stft_and_istft_reconstruct(size: int, hop: int) -> None:
    x = song(1.3)[0]
    spectrum = hq.stft(x, size, hop)
    assert spectrum.shape == (size // 2 + 1, 1 + x.size // hop) and spectrum.dtype == np.complex64
    back = hq.istft(spectrum, size, hop, x.size)
    assert back.shape == x.shape
    assert 10 * np.log10(np.mean((back - x) ** 2) / np.mean(x**2)) < -100


# --- stage 1 ------------------------------------------------------------------------------------


def test_stereo_cleanup_narrows_the_side_highs_and_keeps_the_middle() -> None:
    x = song()
    out, report = hq.stereo_cleanup(x, RATE, hq.STEREO_PROFILES[hq.STANDARD], preset="p", profile="standard")
    assert out.shape == x.shape
    assert report["side_change_db"]["10500-20000 Hz"] < -6
    assert report["schema"] == hq.HQ_SCHEMA and report["profile"] == "standard" and not report["provisional"]
    # a centred signal has no side: without warmth it comes back unchanged
    mono_mix = np.stack([x[0], x[0]])
    same, _ = hq.stereo_cleanup(mono_mix, RATE, hq.StereoCleanup(10500.0, 0.65, 0.0))
    assert np.max(np.abs(same - mono_mix)) < 1e-6


def test_stereo_cleanup_of_mono_applies_only_the_warmth() -> None:
    x = song()[:1]
    out, report = hq.stereo_cleanup(x, RATE, hq.STEREO_PROFILES[hq.STANDARD])
    assert out.shape == x.shape and "mono input" in report["notes"][0]
    unchanged, _ = hq.stereo_cleanup(x, RATE, hq.StereoCleanup(10500.0, 0.65, 0.0))
    assert np.array_equal(unchanged, x)


def test_the_warmth_adds_gentle_harmonics() -> None:
    t = np.arange(RATE * 2) / RATE
    sine = 0.5 * np.sin(2 * np.pi * 1000.0 * t)
    out, _ = hq.stereo_cleanup(np.stack([sine, sine]), RATE, hq.StereoCleanup(20000.0, 0.0, 0.18))
    spectrum = np.abs(np.fft.rfft(out[0, RATE // 2 : RATE // 2 + RATE]))
    third = 20 * np.log10(spectrum[3000] / spectrum[1000])
    assert -60 < third < -45  # audible as density, far from distortion


# --- stage 2 ------------------------------------------------------------------------------------


@dataclass
class FakeEngine:
    """Upsamples by repetition and adds seeded noise: new 'highs' that differ from the original's."""

    input_rate: int = 16000
    name: str = "fake"
    chunk_seconds: float = 1.0
    overlap_seconds: float = 0.1
    calls: list[int] = field(default_factory=list)

    @property
    def condition_hz(self) -> float:
        return self.input_rate / 2

    def upsample(self, chunk: np.ndarray, seed: int) -> np.ndarray:
        self.calls.append(self.input_rate)
        factor = 48000 // self.input_rate
        noise = np.random.default_rng(seed).standard_normal((chunk.shape[0], chunk.shape[1] * factor))
        return np.repeat(chunk, factor, axis=1) + 0.01 * noise


@dataclass
class FakeConditionedEngine(FakeEngine):
    input_rates: tuple[int, ...] = (8000, 12000, 16000, 24000)

    def at_input_rate(self, rate: int) -> FakeConditionedEngine:
        return replace(self, input_rate=rate)


@pytest.mark.parametrize(
    ("from_hz", "rate"), [(8200.0, 16000), (12200.0, 24000), (4500.0, 8000), (10000.0, 16000)]
)
def test_the_model_runs_at_the_condition_under_the_crossover(from_hz: float, rate: int) -> None:
    assert hq.condition_for(FakeConditionedEngine(), from_hz).input_rate == rate


def test_a_crossover_below_every_condition_is_refused() -> None:
    with pytest.raises(PlenioUserError, match="below every input condition"):
        hq.condition_for(FakeConditionedEngine(input_rates=(16000, 24000)), 6000.0)
    plain = FakeEngine(input_rate=24000)
    assert hq.condition_for(plain, 8200.0) is plain  # one condition: used as it is


def test_regenerate_keeps_everything_below_the_crossover() -> None:
    x = song()
    out, report = hq.regenerate_highs(x, RATE, FakeConditionedEngine(), hq.REGENERATE_PROFILES[hq.STANDARD])
    assert out.shape == x.shape
    below = band_db(out - x, 20, 5000) - band_db(x, 20, 5000)
    assert below < -60  # the complementary crossover: nothing below it changes
    assert report["engine"] == "fake" and report["engine_input_rate"] == 16000
    assert report["engine_edge_hz"] == 8000.0 and report["highs_change_db"] is not None


def test_no_new_share_returns_the_original() -> None:
    x = song()
    out, _ = hq.regenerate_highs(x, RATE, FakeConditionedEngine(), hq.RegenerateHighs(8200.0, 0.0, 0.9))
    assert np.max(np.abs(out - x)) < 1e-9


def test_the_new_highs_follow_the_original_level() -> None:
    x = song()
    level = hq.RegenerateHighs(8200.0, 1.0, 1.0)
    out, _ = hq.regenerate_highs(x, RATE, FakeConditionedEngine(), level)
    assert abs(band_db(out, 10000, 20000) - band_db(x, 10000, 20000)) < 1.5
    quieter, _ = hq.regenerate_highs(x, RATE, FakeConditionedEngine(), replace(level, level_match=0.5))
    assert band_db(quieter, 10000, 20000) - band_db(x, 10000, 20000) == pytest.approx(-6.0, abs=1.5)


def test_regenerate_keeps_a_44100_song_at_its_rate_and_length() -> None:
    x = song(2.0, rate=44100)
    out, report = hq.regenerate_highs(
        x, 44100, FakeConditionedEngine(), hq.REGENERATE_PROFILES[hq.GENTLE], profile=hq.GENTLE
    )
    assert out.shape == x.shape and report["engine_input_rate"] == 16000 and report["provisional"]


def test_regenerate_is_deterministic_for_a_seed() -> None:
    x = song(1.5)
    first, _ = hq.regenerate_highs(x, RATE, FakeConditionedEngine(), hq.RegenerateHighs(seed=3))
    again, _ = hq.regenerate_highs(x, RATE, FakeConditionedEngine(), hq.RegenerateHighs(seed=3))
    other, _ = hq.regenerate_highs(x, RATE, FakeConditionedEngine(), hq.RegenerateHighs(seed=4))
    assert np.array_equal(first, again) and not np.array_equal(first, other)


def test_regenerate_passes_a_song_without_room_for_new_highs_on_and_says_so() -> None:
    """A 16 kHz upload has no band above 8.2 kHz: a visible skip, not an error that stops the master (R7)."""
    x = song(1.0, rate=16000)
    out, report = hq.regenerate_highs(x, 16000, FakeEngine(), hq.RegenerateHighs())
    assert np.array_equal(out, x) and report["skipped"] and "no band above 8.2 kHz" in report["notes"][0]


def test_very_short_audio_is_passed_on_with_a_note() -> None:
    x = song(0.05)
    for out, report in (
        hq.stereo_cleanup(x, RATE, hq.STEREO_PROFILES[hq.STANDARD]),
        hq.regenerate_highs(x, RATE, FakeEngine(), hq.RegenerateHighs()),
        hq.dereverb(x, RATE, hq.DEREVERB_PROFILES[hq.STANDARD]),
    ):
        assert np.array_equal(out, x) and report["skipped"] and "too short" in report["notes"][0]


# --- stage 3 ------------------------------------------------------------------------------------


def test_dereverb_lowers_the_highs_and_leaves_the_low_band() -> None:
    """What it does, measured (2026-10-21): attacks and tails lose about the same above 3 kHz - it lowers the
    highs rather than only the room - and nothing changes below 600 Hz (the stage's frequency mask)."""
    x = song()
    out, report = hq.dereverb(x, RATE, hq.DEREVERB_PROFILES[hq.STANDARD])
    assert out.shape == x.shape and report["highs_change_db"] < -1
    low, low_out = (hq._zero_phase(a, 400.0, RATE, "low") for a in (x, out))
    assert 10 * np.log10(np.mean((low_out - low) ** 2) / np.mean(low**2)) < -40


def test_dereverb_off_returns_a_copy() -> None:
    x = song(1.0)
    out, _ = hq.dereverb(x, RATE, hq.DeReverb(0.0, 0.0))
    assert np.array_equal(out, x) and out is not x


def test_settings_are_checked() -> None:
    with pytest.raises(PlenioUserError, match="side cleanup"):
        hq.stereo_cleanup(song(0.5), RATE, hq.StereoCleanup(10500.0, 1.5, 0.1))
    with pytest.raises(PlenioUserError, match="share of new highs"):
        hq.regenerate_highs(song(0.5), RATE, FakeEngine(), hq.RegenerateHighs(8200.0, 2.0))
    with pytest.raises(PlenioUserError, match="phase lock"):
        hq.dereverb(song(0.5), RATE, hq.DeReverb(0.4, -1.0))
