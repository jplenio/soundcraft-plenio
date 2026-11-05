"""Audio HQ: three refinement stages before the EQ (the owner's *Plenio-AudioHQ v3.0* proposal, 2026-10-21).

1. **Stereo cleanup** - mid/side: a zero-phase high-cut and a spectral cleanup of the *side* signal above
   2 kHz (the unsteady stereo shimmer at the edge of the image), and a 2x oversampled saturation above
   400 Hz that adds a little 2nd/3rd harmonic warmth; the mid (voice, kick, snare, bass) is not filtered.
2. **Regenerate highs** - "erase and regenerate": the song is converted to a super-resolution model's input
   condition (the highs above its edge are gone), the model generates new highs, and above the crossover
   they replace a share of the original's, level-matched to the original's 40 ms envelope. Below the
   crossover the song stays the original (complementary zero-phase crossover).
3. **De-reverb** - a late-envelope subtraction above 600 Hz (the short metallic room after syllables and
   hits) and a magnitude-weighted smoothing of the phase above 2 kHz (phase lock; the proposal's text says
   2.5-9 kHz, its code acts on everything above 2 kHz).

The DSP follows the proposal's code (checked against it: -140 dB difference on a YuE2 take); deliberate
changes: numpy STFTs instead of torch (the same frames and windows), float32 spectra (bounded memory for
six-minute songs), no soft clipper (the proposal ran ``tanh`` over the whole song when a peak reached 0.999;
Loudness & Dynamics owns the peaks after the EQ), no silent DSP fallback for a missing model (R7: the model
input is required; the fallback cut the highs by 15 dB), and no file export or plot (Export Release and the
node summary do that). The engine is UniverSR, not the proposal's FlashSR: in the owner's listening test
(2026-10-22) UniverSR sounded better, and Plenio offers no FlashSR.

Presets: one **profile** per stage - *standard* (the proposal's values: the owner's listening test of
2026-10-21/22 for stages 1 and 2, stage 2 with UniverSR), *gentle*, *strong* and *wide* - or *auto*, which picks
the profile from the song's genre (``profile_for``), or *custom* (the node's fields). The values other than
*standard* are provisional (no listening test yet).
"""

from __future__ import annotations

import math
import re
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from fractions import Fraction
from typing import Any, Protocol, cast

import numpy as np

from ..dependencies import require
from ..errors import PlenioUserError
from .loudness import measure
from .refine import OUTPUT_RATE, Engine, run_chunked
from .resample import resample
from .signal import Cancel, as_channels, check_rate, no_cancel, number, peak

HQ_SCHEMA = "plenio.hq/1"

# --- profiles and presets -----------------------------------------------------------------------

STANDARD, GENTLE, STRONG, WIDE = "standard", "gentle", "strong", "wide"
PROFILES = (STANDARD, GENTLE, STRONG, WIDE)

HQ_MASTERING_HINT = (
    "Highest mastering quality: UniverSR (HQ 2) regenerates the highs - clearly fewer AI shimmer and artifacts, "
    "but the song takes about twice as long. Off (default; on in Enhance & Master): UniverSR is not needed."
)
"""The HQ Mastering switch's hint (on, HQ 2 runs; off by default - the owner's request 2026-10-22 -, on in Enhance
& Master since 2026-10-24): the node, its tooltip and the templates' notes say the same."""

AUTO = "auto - from the song's genre"
CUSTOM = "custom - the fields below"
PRESET_LABELS = {
    STANDARD: "standard - pop, hip-hop, soul, world",
    GENTLE: "gentle - classical, jazz, folk",
    STRONG: "strong - rock, metal, punk",
    WIDE: "wide - electronic, dance, ambient",
}
PRESETS = (AUTO, *PRESET_LABELS.values(), CUSTOM)
"""The preset choices of every HQ node, in this order: the same four profiles in all three stages."""

FAMILY_PROFILES = {
    **dict.fromkeys(("rock", "metal", "punk", "alternative"), STRONG),
    **dict.fromkeys(("edm", "electronic", "house", "disco", "ambient"), WIDE),
    **dict.fromkeys(
        (
            "classical",
            "jazz",
            "folk",
            "blues",
            "country",
            "gospel",
            "musical",
            "kids",
            "meditation",
            "cinematic",
            "european",
        ),
        GENTLE,
    ),
}
"""Template families (``resources/templates/<family>/``); every other family is *standard*."""

GENRE_WORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        STRONG,
        (
            "rock",
            "metal",
            "punk",
            "grunge",
            "djent",
            "metalcore",
            "hardcore",
            "emo",
            "shoegaze",
            "post-rock",
            "sludge",
            "industrial",
        ),
    ),
    (
        WIDE,
        (
            "electronic",
            "electronica",
            "electro",
            "edm",
            "techno",
            "house",
            "trance",
            "dubstep",
            "drum & bass",
            "drum and bass",
            "dnb",
            "jungle",
            "neurofunk",
            "breakbeat",
            "synth",
            "ambient",
            "downtempo",
            "chillout",
            "idm",
            "chiptune",
            "vaporwave",
            "hardstyle",
            "eurodance",
            "future bass",
            "future rave",
            "uk garage",
            "trip-hop",
            "disco",
            "hyperpop",
            "phonk",
            "kosmische",
            "berlin school",
            "darkwave",
            "ebm",
        ),
    ),
    (
        GENTLE,
        (
            "classical",
            "orchestral",
            "symphonic",
            "baroque",
            "chamber",
            "string quartet",
            "piano",
            "opera",
            "choral",
            "choir",
            "chant",
            "hymn",
            "jazz",
            "bebop",
            "swing",
            "bossa",
            "folk",
            "bluegrass",
            "americana",
            "country",
            "blues",
            "chanson",
            "fado",
            "flamenco",
            "lullaby",
            "meditation",
            "sleep",
            "film score",
            "underscore",
            "cinematic",
            "minimalism",
            "neoclassical",
            "medieval",
            "waltz",
        ),
    ),
)
"""Words in the brief's genre, checked in this order (``folk metal`` is *strong*, ``synth-pop`` *wide*)."""


def profile_for(brief: Any) -> tuple[str, str]:
    """``(profile, why)`` for *auto*: the brief's genre words first, then its template's family."""
    if brief is None:
        return STANDARD, "no brief connected"
    genre = str(getattr(brief, "genre", "") or "").strip()
    lowered = genre.lower()
    for profile, words in GENRE_WORDS:
        for word in words:
            if re.search(rf"(?<![a-z]){re.escape(word)}", lowered):
                return profile, f"genre {genre!r} ({word})"
    template = str(getattr(brief, "template", "") or "").strip()
    family = template.split("/", 1)[0] if template else ""
    if family in FAMILY_PROFILES:
        return FAMILY_PROFILES[family], f"template family {family!r}"
    if genre or template:
        return STANDARD, f"genre {genre!r}" if genre else f"template family {family!r}"
    return STANDARD, "the brief names no genre"


def chosen_profile(preset: str, brief: Any) -> tuple[str | None, str]:
    """``(profile, why)`` of a preset choice; ``(None, ...)`` for *custom*."""
    if preset == CUSTOM:
        return None, "custom"
    if preset == AUTO:
        profile, why = profile_for(brief)
        return profile, f"auto: {why}"
    for profile, label in PRESET_LABELS.items():
        if preset == label:
            return profile, "preset"
    raise PlenioUserError(f"Unknown preset {preset!r}.", hint=f"Use one of {list(PRESETS)}.")


# --- shared DSP ---------------------------------------------------------------------------------


def _signal() -> Any:
    return require("scipy.signal")


def _ndimage() -> Any:
    return require("scipy.ndimage")


def _zero_phase(samples: np.ndarray, cutoff_hz: float, rate: int, kind: str, order: int = 4) -> np.ndarray:
    """Butterworth forward-backward (no phase shift), as the proposal's ``_zero_phase_filter``."""
    signal = _signal()
    edge = float(np.clip(cutoff_hz / (0.5 * rate), 1e-4, 0.999))
    sos = signal.butter(order, edge, btype=kind, output="sos")
    return np.asarray(signal.sosfiltfilt(sos, samples, axis=-1))


def _window(size: int) -> np.ndarray:
    """The periodic Hann window (``torch.hann_window``)."""
    return (0.5 - 0.5 * np.cos(2 * np.pi * np.arange(size) / size)).astype(np.float32)


def stft(samples: np.ndarray, size: int, hop: int) -> np.ndarray:
    """``[size // 2 + 1, frames]`` complex64, framed like ``torch.stft(center=True, pad_mode='reflect')``."""
    padded = np.pad(np.asarray(samples, dtype=np.float32), size // 2, mode="reflect")
    frames = 1 + (padded.size - size) // hop
    window = _window(size)
    out = np.empty((size // 2 + 1, frames), dtype=np.complex64)
    block = 2048
    for start in range(0, frames, block):
        stop = min(frames, start + block)
        index = np.arange(size)[None, :] + hop * np.arange(start, stop)[:, None]
        out[:, start:stop] = np.fft.rfft(padded[index] * window, axis=1).T
    return out


def istft(spectrum: np.ndarray, size: int, hop: int, length: int) -> np.ndarray:
    """The inverse of ``stft`` (window-weighted overlap-add, ``torch.istft(center=True, length=...)``)."""
    window = _window(size)
    frames = spectrum.shape[1]
    total = size + hop * (frames - 1)
    out = np.zeros(total, dtype=np.float64)
    weight = np.zeros(total, dtype=np.float64)
    block = 2048
    for start in range(0, frames, block):
        stop = min(frames, start + block)
        chunk = np.fft.irfft(spectrum[:, start:stop], n=size, axis=0).T * window
        for offset, frame in enumerate(chunk):
            begin = (start + offset) * hop
            out[begin : begin + size] += frame
    squared = window.astype(np.float64) ** 2
    for index in range(frames):
        weight[index * hop : index * hop + size] += squared
    out = out[size // 2 : size // 2 + length]
    weight = weight[size // 2 : size // 2 + length]
    result: np.ndarray = out / np.where(weight > 1e-11, weight, 1.0)
    if result.size < length:
        result = np.pad(result, (0, length - result.size))
    return result


def _band_side_db(samples: np.ndarray, rate: int, low_hz: float, high_hz: float) -> float | None:
    """Side energy relative to mid energy in a band (dB), for the reports."""
    if samples.shape[0] < 2:
        return None
    signal = _signal()
    mid, side = 0.5 * (samples[0] + samples[1]), 0.5 * (samples[0] - samples[1])
    size = min(4096, mid.size)
    freqs, power_mid = signal.welch(mid, rate, nperseg=size)
    _, power_side = signal.welch(side, rate, nperseg=size)
    band = (freqs >= low_hz) & (freqs < min(high_hz, rate / 2))
    m, s = float(power_mid[band].sum()), float(power_side[band].sum())
    if m <= 0 or s <= 0:
        return None
    return 10 * math.log10(s / m)


def _band_db(samples: np.ndarray, rate: int, low_hz: float, high_hz: float) -> float | None:
    signal = _signal()
    size = min(4096, samples.shape[1])
    freqs, power = signal.welch(samples.mean(axis=0), rate, nperseg=size)
    band = (freqs >= low_hz) & (freqs < min(high_hz, rate / 2))
    value = float(power[band].sum())
    return 10 * math.log10(value) if value > 0 else None


def _change(before: float | None, after: float | None) -> float | None:
    return None if before is None or after is None else round(after - before, 2)


def _lufs_change(before: np.ndarray, after: np.ndarray, rate: int) -> float | None:
    a = measure(before, rate, with_true_peak=False).integrated_lufs
    b = measure(after, rate, with_true_peak=False).integrated_lufs
    return None if a is None or b is None else round(float(b) - float(a), 2)


MIN_FRAMES = 8192
"""Shorter audio (0.17 s at 48 kHz) is passed on unchanged with a note: the spectra need more."""


def _skipped(
    data: np.ndarray,
    stage: str,
    preset: str,
    profile: str | None,
    why: str,
    settings: Any,
    note: str,
    started: float,
    clock: Callable[[], float],
) -> tuple[np.ndarray, dict[str, Any]]:
    """The audio unchanged and a report that says why (R7: a visible *skipped*, never a silent pass-through)."""
    report = _base_report(stage, preset, profile, why, settings)
    report.update(skipped=True, seconds=round(clock() - started, 3), notes=[note])
    return data + 0.0, report


def _base_report(stage: str, preset: str, profile: str | None, why: str, settings: Any) -> dict[str, Any]:
    return {
        "schema": HQ_SCHEMA,
        "stage": stage,
        "preset": preset,
        "profile": profile,
        "chosen_by": why,
        "provisional": profile not in (None, STANDARD),
        "settings": asdict(settings),
    }


# --- stage 1: stereo cleanup --------------------------------------------------------------------


@dataclass(frozen=True)
class StereoCleanup:
    side_highcut_hz: float = 10500.0
    """The side signal's zero-phase high-cut (blended by ``0.4 + 0.6 * side_cleanup``)."""
    side_cleanup: float = 0.65
    """0 off ... 1 strongest: the high-cut blend and the spectral cleanup of the side above 2 kHz."""
    warmth: float = 0.18
    """0 off ... 0.8: the 2x oversampled saturation above 400 Hz (mid 0.22x, side 0.14x of it)."""

    def checked(self) -> StereoCleanup:
        return StereoCleanup(
            number(self.side_highcut_hz, "side high-cut", 4000.0, 20000.0),
            number(self.side_cleanup, "side cleanup", 0.0, 1.0),
            number(self.warmth, "warmth", 0.0, 0.8),
        )


STEREO_PROFILES = {
    STANDARD: StereoCleanup(10500.0, 0.65, 0.18),
    GENTLE: StereoCleanup(11500.0, 0.55, 0.14),
    STRONG: StereoCleanup(9500.0, 0.80, 0.25),
    WIDE: StereoCleanup(14000.0, 0.40, 0.12),
}


def _exciter(samples: np.ndarray, drive: float) -> np.ndarray:
    """2x oversampled asymmetric tanh (even and odd harmonics), as the proposal's exciter."""
    signal = _signal()
    length = samples.shape[-1]
    doubled = signal.resample_poly(samples, 2, 1, axis=-1)
    k = 1.0 + 2.5 * drive
    bias = 0.06 * drive
    saturated = (np.tanh(k * (doubled + bias)) - np.tanh(k * bias)) / np.tanh(k)
    return np.asarray(signal.resample_poly(saturated, 1, 2, axis=-1))[..., :length]


def _side_cleanup(side: np.ndarray, rate: int, strength: float) -> np.ndarray:
    ndimage = _ndimage()
    size, hop = 2048, 512
    spectrum = stft(side, size, hop)
    magnitude = np.abs(spectrum)
    bed = ndimage.median_filter(magnitude, size=(21, 5), mode="nearest")
    freqs = np.linspace(0.0, rate / 2.0, size // 2 + 1, dtype=np.float32)[:, None]
    weight = np.clip((freqs - 2000.0) / 4000.0, 0.0, 1.0)
    gain = np.clip(1.0 - strength * 0.75 * weight * (bed / (magnitude + 1e-12)), 0.25, 1.0)
    del bed
    gain = ndimage.gaussian_filter(gain.astype(np.float32), sigma=(1.5, 2.0), mode="nearest")
    return istft(spectrum * gain, size, hop, side.size)


def stereo_cleanup(
    samples: Any,
    rate: int,
    settings: StereoCleanup,
    *,
    preset: str = CUSTOM,
    profile: str | None = None,
    why: str = "custom",
    cancel: Cancel = no_cancel,
    clock: Callable[[], float] = time.perf_counter,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Stage 1 (see the module docstring); mono input gets the warmth only."""
    started = clock()
    data = as_channels(samples)
    rate = check_rate(rate)
    options = settings.checked()
    if data.shape[1] < MIN_FRAMES:
        return _skipped(
            data,
            "stereo cleanup",
            preset,
            profile,
            why,
            options,
            "too short to clean: passed on unchanged",
            started,
            clock,
        )
    notes: list[str] = []
    if data.shape[0] < 2:
        out = data + 0.0 if options.warmth <= 0 else _exciter(data, options.warmth)
        notes.append("mono input: no side signal - only the warmth applies")
    else:
        mid = 0.5 * (data[0] + data[1])
        side = 0.5 * (data[0] - data[1])
        if options.side_highcut_hz < rate * 0.49:
            low = _zero_phase(side, options.side_highcut_hz, rate, "low")
            blend = min(1.0, 0.4 + 0.6 * options.side_cleanup)
            side = (1.0 - blend) * side + blend * low
        cancel()
        if options.side_cleanup > 0:
            side = _side_cleanup(side, rate, options.side_cleanup)
        cancel()
        if options.warmth > 0:
            stacked = np.stack([mid, side])
            high = _zero_phase(stacked, 400.0, rate, "high", order=2)
            excited = _exciter(high, options.warmth)
            mid = mid + 0.22 * options.warmth * (excited[0] - high[0])
            side = side + 0.14 * options.warmth * (excited[1] - high[1])
        out = np.stack([mid + side, mid - side])
    report = _base_report("stereo cleanup", preset, profile, why, options)
    report.update(
        side_change_db={
            f"{lo}-{hi} Hz": _change(_band_side_db(data, rate, lo, hi), _band_side_db(out, rate, lo, hi))
            for lo, hi in ((2000, 6000), (6000, 10500), (10500, 20000))
        },
        loudness_change_lu=_lufs_change(data, out, rate),
        peak_in=round(peak(data), 6),
        peak_out=round(peak(out), 6),
        seconds=round(clock() - started, 3),
        notes=notes,
    )
    return out, report


# --- stage 2: regenerate highs ------------------------------------------------------------------


@dataclass(frozen=True)
class RegenerateHighs:
    from_hz: float = 8200.0
    """The crossover: above it the new highs take over; below it the song stays the original."""
    new_share: float = 0.85
    """Share of the new highs above the crossover (the rest is the original's)."""
    level_match: float = 0.90
    """The new highs follow the original's 40 ms envelope times this (0.3 ... 1.5)."""
    seed: int = 0

    def checked(self) -> RegenerateHighs:
        return RegenerateHighs(
            number(self.from_hz, "new highs from", 4500.0, 20000.0),
            number(self.new_share, "share of new highs", 0.0, 1.0),
            number(self.level_match, "level match", 0.3, 1.5),
            int(number(self.seed, "seed", 0, 2**32 - 1)),
        )


REGENERATE_PROFILES = {
    STANDARD: RegenerateHighs(8200.0, 0.85, 0.90),
    GENTLE: RegenerateHighs(8200.0, 0.80, 0.90),
    STRONG: RegenerateHighs(8200.0, 0.95, 0.90),
    WIDE: RegenerateHighs(8200.0, 0.85, 0.95),
}
"""Every profile regenerates from 8.2 kHz, the crossover the owner listened to (2026-10-22: a gentle profile
from 12.2 kHz, chosen by *auto* for a singer-songwriter song, changed the song too little to hear); they differ
only in the share of new highs and how closely those follow the original's level."""
ENVELOPE_SECONDS = 0.04
MAX_ENVELOPE_GAIN = 2.5


class ConditionedEngine(Engine, Protocol):
    """An engine trained for several input conditions (UniverSR: 8/12/16/24 kHz input rates)."""

    input_rates: tuple[int, ...]

    def at_input_rate(self, rate: int) -> Engine:
        """The same model at another input condition."""
        ...


def condition_for(engine: Engine, from_hz: float) -> Engine:
    """The engine at its input condition for a crossover: the highest one whose edge (half its input rate)
    lies at or below the crossover - so the model generates everything the crossover hands over to it.

    An engine with one condition (no ``input_rates``) is used as it is, its input low-passed at the
    crossover when it would see more.
    """
    rates = getattr(engine, "input_rates", None)
    if not rates:
        return engine
    fitting = [int(rate) for rate in rates if rate / 2 <= from_hz]
    if not fitting:
        raise PlenioUserError(
            f"New highs from {from_hz:g} Hz is below every input condition of {engine.name} "
            f"(edges {', '.join(f'{rate / 2000:g} kHz' for rate in sorted(rates))}).",
            hint=f"Choose at least {min(rates) / 2 + 200:g} Hz.",
        )
    return cast(ConditionedEngine, engine).at_input_rate(max(fitting))


def _gaussian_smooth(values: np.ndarray, sigma: float) -> np.ndarray:
    """``scipy.ndimage.gaussian_filter1d(values, sigma)`` (mode *reflect*, truncate 4) as an FFT convolution: the
    same numbers, but a 40 ms envelope of a four-minute song in a second instead of minutes."""
    radius = int(4.0 * sigma + 0.5)
    offsets = np.arange(-radius, radius + 1, dtype=np.float64)
    kernel = np.exp(-0.5 * (offsets / sigma) ** 2)
    kernel /= kernel.sum()
    padded = np.pad(values, radius, mode="symmetric")
    return np.asarray(_signal().oaconvolve(padded, kernel, mode="valid"))


def _engine_input(samples: np.ndarray, rate: int, target: int) -> np.ndarray:
    """The model's input at its condition rate, through SciPy's default polyphase filter (as the proposal).

    Not Plenio's resampler: that one is flat only to 90 % of the new Nyquist frequency, and UniverSR
    generates no highs from an input that ends there - measured on a YuE2 take at the 16 kHz condition:
    -107 dB above 8.2 kHz instead of the original's -72 dB. SciPy's filter has its -6 dB point at the
    Nyquist frequency, like the condition the model was trained with.
    """
    if rate == target:
        return samples
    ratio = Fraction(target, rate).limit_denominator(10000)
    return np.asarray(_signal().resample_poly(samples, ratio.numerator, ratio.denominator, axis=-1))


def regenerate_highs(
    samples: Any,
    rate: int,
    engine: Engine,
    settings: RegenerateHighs,
    *,
    preset: str = CUSTOM,
    profile: str | None = None,
    why: str = "custom",
    cancel: Cancel = no_cancel,
    clock: Callable[[], float] = time.perf_counter,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Stage 2 (see the module docstring): same rate and length as the input."""
    started = clock()
    data = as_channels(samples)
    rate = check_rate(rate)
    options = settings.checked()
    if options.from_hz >= rate / 2 - 500:
        note = (
            f"at {rate} Hz there is no band above {options.from_hz / 1000:g} kHz for new highs: passed on unchanged "
            "(convert the song to 44.1 or 48 kHz first - Loudness & Dynamics or Refine - to regenerate its highs)"
        )
        return _skipped(data, "regenerate highs", preset, profile, why, options, note, started, clock)
    if data.shape[1] < MIN_FRAMES:
        return _skipped(
            data,
            "regenerate highs",
            preset,
            profile,
            why,
            options,
            "too short: passed on unchanged",
            started,
            clock,
        )
    model = condition_for(engine, options.from_hz)
    source = data
    edge = model.input_rate / 2
    if edge > options.from_hz:
        source = _zero_phase(data, options.from_hz, rate, "low", order=8)
    erased = _engine_input(source, rate, model.input_rate)
    generated = run_chunked(erased, model, seed=options.seed, cancel=cancel)
    generated = resample(generated, OUTPUT_RATE, rate)
    frames = data.shape[1]
    generated = np.pad(generated[:, :frames], ((0, 0), (0, max(0, frames - generated.shape[1]))))
    sigma = max(256, int(rate * ENVELOPE_SECONDS))
    out = np.empty_like(data)
    for channel in range(data.shape[0]):
        cancel()
        low = _zero_phase(data[channel], options.from_hz, rate, "low")
        high = data[channel] - low
        new = generated[channel] - _zero_phase(generated[channel], options.from_hz, rate, "low")
        envelope = np.sqrt(np.maximum(_gaussian_smooth(high**2, sigma), 0.0) + 1e-12)
        new_envelope = np.sqrt(np.maximum(_gaussian_smooth(new**2, sigma), 0.0) + 1e-12)
        matched = new * np.clip(envelope / new_envelope * options.level_match, 0.0, MAX_ENVELOPE_GAIN)
        out[channel] = low + (1.0 - options.new_share) * high + options.new_share * matched
    top = min(20000.0, rate / 2)
    report = _base_report("regenerate highs", preset, profile, why, options)
    report.update(
        engine=model.name,
        engine_input_rate=int(model.input_rate),
        engine_edge_hz=edge,
        engine_steps=getattr(model, "ode_steps", None),
        highs_change_db=_change(
            _band_db(data, rate, options.from_hz, top), _band_db(out, rate, options.from_hz, top)
        ),
        side_change_db=_change(
            _band_side_db(data, rate, options.from_hz, top), _band_side_db(out, rate, options.from_hz, top)
        ),
        loudness_change_lu=_lufs_change(data, out, rate),
        peak_in=round(peak(data), 6),
        peak_out=round(peak(out), 6),
        seconds=round(clock() - started, 3),
        notes=[],
    )
    return out, report


# --- stage 3: de-reverb -------------------------------------------------------------------------


@dataclass(frozen=True)
class DeReverb:
    dereverb: float = 0.45
    """0 off ... 1: how much of the late, diffuse envelope above 600 Hz is taken out."""
    phase_lock: float = 0.55
    """0 off ... 1: how far the phase above 2 kHz is pulled towards its weighted neighbourhood."""

    def checked(self) -> DeReverb:
        return DeReverb(
            number(self.dereverb, "de-reverb", 0.0, 1.0),
            number(self.phase_lock, "phase lock", 0.0, 1.0),
        )


DEREVERB_PROFILES = {
    STANDARD: DeReverb(0.45, 0.55),
    GENTLE: DeReverb(0.25, 0.30),
    STRONG: DeReverb(0.65, 0.70),
    WIDE: DeReverb(0.30, 0.40),
}


def _dereverb_channel(channel: np.ndarray, rate: int, options: DeReverb) -> np.ndarray:
    ndimage = _ndimage()
    size, hop = 4096, 1024
    spectrum = stft(channel, size, hop)
    magnitude = np.abs(spectrum)
    phase = np.angle(spectrum)
    del spectrum
    freqs = np.linspace(0.0, rate / 2.0, size // 2 + 1, dtype=np.float32)[:, None]
    if options.dereverb > 0:
        fast = ndimage.gaussian_filter1d(magnitude, sigma=1.0, axis=1)
        delayed = np.pad(magnitude, ((0, 0), (6, 0)), mode="edge")[:, :-6]
        late = ndimage.gaussian_filter1d(delayed, sigma=5.0, axis=1)
        del delayed
        late = 0.6 * late + 0.4 * ndimage.median_filter(late, size=(15, 1), mode="nearest")
        mask = np.clip((freqs - 600.0) / 2500.0, 0.0, 1.0)
        gain = np.clip(1.0 - options.dereverb * 0.65 * mask * (late / (fast + 1e-12)), 0.30, 1.0)
        del fast, late
        magnitude = magnitude * ndimage.gaussian_filter(
            gain.astype(np.float32), sigma=(1.5, 1.8), mode="nearest"
        )
    if options.phase_lock > 0:
        weighted = magnitude**1.5
        real = ndimage.gaussian_filter(np.cos(phase) * weighted, sigma=(1.2, 0.8), mode="nearest")
        imag = ndimage.gaussian_filter(np.sin(phase) * weighted, sigma=(1.2, 0.8), mode="nearest")
        del weighted
        coherent = np.arctan2(imag, real)
        lock = options.phase_lock * np.clip((freqs - 2000.0) / 3000.0, 0.0, 0.85)
        phase = np.arctan2(
            (1.0 - lock) * np.sin(phase) + lock * np.sin(coherent),
            (1.0 - lock) * np.cos(phase) + lock * np.cos(coherent),
        )
    return istft(magnitude * np.exp(1j * phase).astype(np.complex64), size, hop, channel.size)


def dereverb(
    samples: Any,
    rate: int,
    settings: DeReverb,
    *,
    preset: str = CUSTOM,
    profile: str | None = None,
    why: str = "custom",
    cancel: Cancel = no_cancel,
    clock: Callable[[], float] = time.perf_counter,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Stage 3 (see the module docstring); every channel on its own."""
    started = clock()
    data = as_channels(samples)
    rate = check_rate(rate)
    options = settings.checked()
    if data.shape[1] < MIN_FRAMES:
        return _skipped(
            data,
            "de-reverb",
            preset,
            profile,
            why,
            options,
            "too short to process: passed on unchanged",
            started,
            clock,
        )
    if options.dereverb <= 0 and options.phase_lock <= 0:
        out = data + 0.0
    else:
        channels = []
        for channel in data:
            cancel()
            channels.append(_dereverb_channel(channel, rate, options))
        out = np.stack(channels)
    report = _base_report("de-reverb", preset, profile, why, options)
    report.update(
        highs_change_db=_change(_band_db(data, rate, 3200, 20000), _band_db(out, rate, 3200, 20000)),
        loudness_change_lu=_lufs_change(data, out, rate),
        peak_in=round(peak(data), 6),
        peak_out=round(peak(out), 6),
        seconds=round(clock() - started, 3),
        notes=[],
    )
    return out, report


def resolve(preset: str, brief: Any, profiles: dict[str, Any], custom: Any) -> tuple[Any, str | None, str]:
    """The settings of a preset choice: ``(settings, profile, why)``; *custom* returns ``custom``."""
    profile, why = chosen_profile(preset, brief)
    return (custom if profile is None else profiles[profile]), profile, why


__all__ = [
    "AUTO",
    "CUSTOM",
    "DEREVERB_PROFILES",
    "GENTLE",
    "HQ_SCHEMA",
    "PRESETS",
    "PRESET_LABELS",
    "PROFILES",
    "REGENERATE_PROFILES",
    "STANDARD",
    "STEREO_PROFILES",
    "STRONG",
    "WIDE",
    "DeReverb",
    "RegenerateHighs",
    "StereoCleanup",
    "chosen_profile",
    "condition_for",
    "dereverb",
    "istft",
    "profile_for",
    "regenerate_highs",
    "resolve",
    "stereo_cleanup",
    "stft",
]
