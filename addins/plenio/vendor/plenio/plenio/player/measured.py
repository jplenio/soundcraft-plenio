"""How well each song came out, measured (owner's request 2026-10-29), for the player. A song exported since 1.4.0
has it in its record (Export Release measures it); one exported before is measured when its page asks - its audio
decoded with PyAV and :mod:`plenio.core.quality` run on it, about half a second a song - and the result kept in the
player's cache (``quality.json``). Without numpy and PyAV the record's measures alone are given.

The stars the admin gives a song by ear go into the song's own page beside it (``<name>.html``, the page Export
Release wrote - never a new file), with the measured ones.

The library's filter by the measured stars (owner's request 2026-10-30) needs them for every song: :meth:`Measured.stars`
gives those known without measuring, and the running player measures the others in the background, one song at a
time, resting as long as each took (:meth:`Measured.start`). One :class:`Measured` per cache folder
(:func:`measured_for`), so the page's answers and the background share what is kept.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

CACHE_FILE = "quality.json"
KEPT = 20000
"""Songs whose measures the cache keeps at most."""
SAVE_EVERY = 25
"""Songs measured in the background between two writes of the cache."""
LOOK_AGAIN_S = 60.0
"""How long the background rests before it looks for songs not measured yet (new ones) again."""
SONG_ID = re.compile(r"[0-9a-f]{12}")


def ratings_of(raw: Any) -> dict[str, float]:
    """The stars given by ear, as a listener's state keeps them: song id -> 0 to 5 in halves (anything else out)."""
    if not isinstance(raw, Mapping):
        return {}
    out: dict[str, float] = {}
    for song, value in raw.items():
        if SONG_ID.fullmatch(str(song)) and isinstance(value, (int, float)) and not isinstance(value, bool):
            if 0 <= value <= 5:
                out[str(song)] = round(float(value) * 2) / 2
    return out


def decode(path: Path, seconds: float) -> tuple[Any, int]:
    """A song's audio as float32, channels first, at its own rate (at most ``seconds`` of it)."""
    import av
    import numpy as np

    with av.open(str(path)) as container:
        stream = container.streams.audio[0]
        rate = int(stream.rate)
        layout = "stereo" if (stream.channels or 2) > 1 else "mono"
        resampler = av.AudioResampler(format="fltp", layout=layout, rate=rate)
        limit = int(rate * (seconds + 1))
        chunks = []
        total = 0
        for frame in container.decode(stream):
            for out in resampler.resample(frame):
                data = out.to_ndarray()
                chunks.append(data)
                total += data.shape[1]
            if total >= limit:
                break
        chunks += [out.to_ndarray() for out in resampler.resample(None)]
    return np.concatenate(chunks, axis=1)[:, :limit].astype(np.float32), rate


class Measured:
    """The measured quality of the library's songs: the record's, else measured once and kept."""

    def __init__(self, folder: Path) -> None:
        self.path = folder / CACHE_FILE
        self.lock = threading.Lock()
        self._cache: dict[str, Any] | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.progress: dict[str, int] = {"done": 0, "total": 0}
        """The songs measured in the background so far, of those that were not (``total`` 0: none waiting)."""

    def _kept(self) -> dict[str, Any]:
        if self._cache is None:
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                data = {}
            self._cache = data if isinstance(data, dict) else {}
        return self._cache

    def _keep(self, song_id: str, entry: dict[str, Any], save: bool = True) -> None:
        with self.lock:
            kept = self._kept()
            kept.pop(song_id, None)
            kept[song_id] = entry
            while len(kept) > KEPT:
                kept.pop(next(iter(kept)))
        if save:
            self._save()

    def _save(self) -> None:
        with self.lock:
            text = json.dumps(self._kept())
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                temp = self.path.with_suffix(".tmp")
                temp.write_text(text, encoding="utf-8")
                temp.replace(self.path)
            except OSError:
                pass  # kept in memory until the next one

    def known(self, song: Any) -> tuple[bool, float | None]:
        """The measured stars of ``song`` when they are known without measuring: its record's, else the kept ones
        (``False``: not measured yet)."""
        try:
            from ..core.quality import QUALITY_VERSION
        except ImportError:
            return False, None
        given = song.summary.get("measured")
        if isinstance(given, Mapping) and given.get("version") == QUALITY_VERSION:
            return True, given.get("stars")
        with self.lock:
            cached = self._kept().get(song.id)
        quality = cached.get("quality") if isinstance(cached, dict) else None
        if isinstance(quality, dict) and quality.get("version") == QUALITY_VERSION:
            return True, quality.get("stars")
        return False, None

    def stars(self, library: Any) -> dict[str, float | None]:
        """The measured stars of every song known now: song id -> stars (``None``: measured, without stars)."""
        out: dict[str, float | None] = {}
        for song in library.every():
            found, stars = self.known(song)
            if found:
                out[song.id] = stars
        return out

    def start(self, library: Any) -> None:
        """Measure the songs not measured yet in the background - one at a time, resting as long as each took, so
        that the computer hardly notices - and look for new ones every minute. Once per player."""
        try:
            from ..core.quality import song_quality  # noqa: F401 - only where it can measure
        except ImportError:
            return
        if self._thread is not None and self._thread.is_alive():
            return
        stop = self._stop = threading.Event()

        def work() -> None:
            while not stop.is_set():
                waiting = [song for song in library.every() if not self.known(song)[0]]
                self.progress = {"done": 0, "total": len(waiting)}
                for done, song in enumerate(waiting, 1):
                    if stop.is_set():
                        break
                    began = time.monotonic()
                    try:
                        self.of(song, save=done % SAVE_EVERY == 0)
                    except Exception:  # noqa: BLE001 - one song that cannot be measured does not stop the others
                        log.info("Plenio Player: %s could not be measured", song.id, exc_info=True)
                    self.progress["done"] = done
                    stop.wait(max(0.2, time.monotonic() - began))
                if waiting:
                    self._save()
                self.progress = {"done": 0, "total": 0}
                stop.wait(LOOK_AGAIN_S)

        self._thread = threading.Thread(target=work, name="plenio-measure", daemon=True)
        self._thread.start()

    def close(self) -> None:
        """Stop measuring in the background (what was measured is kept)."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=10)

    def of(self, song: Any, save: bool = True) -> dict[str, Any] | None:
        """How well ``song`` came out, measured (``None``: this player cannot measure it)."""
        try:
            from ..core.quality import MAX_SECONDS, QUALITY_VERSION, song_quality
        except ImportError:
            return None
        record: dict[str, Any] = {}
        if not song.other:
            try:
                record = json.loads(song.record.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                record = {}
        given = record.get("quality")
        if isinstance(given, dict) and given.get("version") == QUALITY_VERSION:
            return given
        audio = song.files.get("audio")
        try:
            stat = audio.stat() if audio is not None else None
        except OSError:
            stat = None
        stamp = [stat.st_size, int(stat.st_mtime)] if stat else None
        with self.lock:
            cached = self._kept().get(song.id)
        if (
            isinstance(cached, dict)
            and cached.get("stamp") == stamp
            and (cached.get("quality") or {}).get("version") == QUALITY_VERSION
        ):
            return dict(cached["quality"])
        samples, rate = None, 0
        if audio is not None and stat is not None:
            try:
                samples, rate = decode(audio, MAX_SECONDS)
            except Exception:  # noqa: BLE001 - no PyAV here, or a file it cannot read: the record's measures
                log.info("Plenio Player: %s could not be measured", audio.name, exc_info=True)
                samples = None
        quality = song_quality(samples, rate, record or None)
        self._keep(song.id, {"stamp": stamp, "quality": quality}, save=save)
        return quality

    def write_pages(self, library: Any, ratings: Mapping[str, float | None]) -> None:
        """The songs' own pages beside them written anew with the admin's stars (in the background): only pages
        Export Release wrote, never a new file."""

        def work() -> None:
            from ..core.files import atomic_write_text
            from .song_page import page_for

            for song_id, stars in ratings.items():
                song = library.song(song_id)
                page = song.files.get("page") if song is not None and not song.other else None
                if page is None or not page.is_file():
                    continue
                try:
                    atomic_write_text(page, page_for(song.record, rating=stars, quality=self.of(song)))
                except (OSError, ValueError):
                    log.warning("Plenio Player: the page of %s was not written", song_id, exc_info=True)

        threading.Thread(target=work, name="plenio-song-pages", daemon=True).start()


_shared: dict[Path, Measured] = {}
_shared_lock = threading.Lock()


def measured_for(folder: Path) -> Measured:
    """The one :class:`Measured` of a cache folder: the page's answers and the background share what is kept."""
    key = Path(folder).resolve()
    with _shared_lock:
        found = _shared.get(key)
        if found is None:
            found = _shared[key] = Measured(key)
        return found
