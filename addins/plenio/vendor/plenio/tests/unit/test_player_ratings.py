"""Every song rated 0 to 5 (owner's request 2026-10-29): by ear in each listener's state, and measured - from the
record of a song exported since 1.4.0, else measured once by the player and kept. Both on the song's page in the
player, and the admin's stars written into the song's own page beside it."""

from __future__ import annotations

import http.client
import json
import threading
import time
from collections.abc import Iterator
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest

from plenio.player.accounts import Accounts
from plenio.player.library import Library
from plenio.player.measured import measured_for, ratings_of
from plenio.player.server import State, serve

av = pytest.importorskip("av")
np = pytest.importorskip("numpy")
JSON = {"Content-Type": "application/json"}


def chords_flac(path: Path, seconds: float = 12.0) -> None:
    """C - F - G - C, a few harmonics each, fading out at the end."""
    rate = 22050
    t = np.arange(int(rate * seconds)) / rate
    out = np.zeros_like(t)
    quarter = len(t) // 4
    for k, root in enumerate((60, 65, 67, 60)):
        part = slice(k * quarter, (k + 1) * quarter)
        for third in (0, 4, 7):
            f = 440.0 * 2 ** ((root + third - 69) / 12)
            out[part] += np.sin(2 * np.pi * f * t[part]) + 0.3 * np.sin(4 * np.pi * f * t[part])
    out = (0.08 * out * np.minimum(1.0, (len(t) - np.arange(len(t))) / (rate * 1.5))).astype(np.float32)
    with av.open(str(path), "w") as container:
        stream = container.add_stream("flac", rate=rate)
        stream.layout = "mono"
        frame = av.AudioFrame.from_ndarray(out[None, :], format="flt", layout="mono")
        frame.sample_rate = rate
        frame.pts = 0
        frame.time_base = Fraction(1, rate)
        for packet in [*stream.encode(frame), *stream.encode(None)]:
            container.mux(packet)


@pytest.fixture
def player(tmp_path: Path) -> Iterator[tuple[int, Path, dict[str, str]]]:
    folder = tmp_path / "output" / "plenio"
    folder.mkdir(parents=True)
    ids = {}
    for title, quality in (("Old", None), ("New", {"version": 1, "stars": 4.5, "score": 0.9, "parts": []})):
        chords_flac(folder / f"{title}.flac")
        record: dict[str, Any] = {
            "schema": "plenio.release/1",
            "title": title,
            "files": [{"name": f"{title}.flac", "format": "flac"}],
            "audio": {"seconds": 12.0, "loudness": [{"integrated_lufs": -14.0, "true_peak_dbtp": -1.2}]},
        }
        if quality:
            record["quality"] = quality
        (folder / f"{title}.plenio.json").write_text(json.dumps(record), encoding="utf-8")
        (folder / f"{title}.html").write_text("<!doctype html><title>as exported</title>", encoding="utf-8")
    library = Library([tmp_path / "output"])
    library.scan(force=True)
    for song in library.songs():
        ids[song["title"]] = song["id"]
    server = serve(
        library,
        State(tmp_path / "state" / "state.json"),
        "127.0.0.1",
        0,
        accounts=Accounts(tmp_path / "state"),
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server.server_address[1], folder, ids
    server.shutdown()
    server.server_close()


def call(port: int, method: str, path: str, body: Any = None, **headers: str) -> tuple[int, Any]:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    connection.request(
        method, path, body=None if body is None else json.dumps(body).encode(), headers=headers
    )
    answer = connection.getresponse()
    raw = answer.read()
    connection.close()
    try:
        return answer.status, json.loads(raw)
    except ValueError:
        return answer.status, raw.decode("utf-8", "replace")


def test_a_song_is_measured_once_and_kept_and_one_since_1_4_has_it_in_its_record(
    player: Any, tmp_path: Path
) -> None:
    port, _folder, ids = player
    status, answer = call(port, "GET", f"/api/quality/{ids['Old']}")
    measured = answer["quality"]
    assert status == 200 and 0 <= measured["stars"] <= 5
    assert {"chords", "key", "ending", "loudness"} <= {p["key"] for p in measured["parts"]}
    kept = json.loads((tmp_path / "state" / "cache" / "quality.json").read_text(encoding="utf-8"))
    assert kept[ids["Old"]]["quality"]["stars"] == measured["stars"]
    assert call(port, "GET", f"/api/quality/{ids['New']}")[1]["quality"]["stars"] == 4.5
    assert call(port, "GET", "/api/quality/ffffffffffff")[0] == 404


def test_the_measured_stars_of_every_song_for_the_filter_the_others_measured_in_the_background(
    player: Any, tmp_path: Path
) -> None:
    port, _folder, ids = player
    status, answer = call(port, "GET", "/api/stars")
    # the record's at once, without opening it again; the old song is not measured yet
    assert status == 200 and answer["stars"] == {ids["New"]: 4.5}
    assert answer["measuring"] == {"done": 0, "total": 0}
    # the running player measures it in the background (python -m plenio.player starts this)
    measured = measured_for(tmp_path / "state" / "cache")
    measured.start(Library([tmp_path / "output"]))
    try:
        for _ in range(200):
            stars = call(port, "GET", "/api/stars")[1]["stars"]
            if ids["Old"] in stars:
                break
            time.sleep(0.1)
        assert 0 <= stars[ids["Old"]] <= 5 and stars[ids["New"]] == 4.5
    finally:
        measured.close()
    kept = json.loads((tmp_path / "state" / "cache" / "quality.json").read_text(encoding="utf-8"))
    assert kept[ids["Old"]]["quality"]["stars"] == stars[ids["Old"]] and ids["New"] not in kept
    # the song's page asks for the same, kept one
    assert call(port, "GET", f"/api/quality/{ids['Old']}")[1]["quality"]["stars"] == stars[ids["Old"]]


def test_the_admins_stars_go_into_the_songs_own_page(player: Any) -> None:
    port, folder, ids = player
    rev = call(port, "GET", "/api/state")[1]["rev"]
    saved = call(
        port,
        "PUT",
        "/api/state",
        {"ratings": {ids["New"]: 3.5, "junk": 9, ids["Old"]: 7}, "rev": rev},
        **JSON,
    )
    assert saved[0] == 200
    assert call(port, "GET", "/api/state")[1]["ratings"] == {ids["New"]: 3.5}
    # the page in the player: both, the measured faded
    page = call(port, "GET", f"/page/{ids['New']}")[1]
    assert "3.5 of 5, rated by ear" in page and "4.5 of 5, measured" in page and 'class="measured"' in page
    # and the page beside the song, written anew (in the background)
    for _ in range(60):
        beside = (folder / "New.html").read_text(encoding="utf-8")
        if "rated by ear" in beside:
            break
        time.sleep(0.1)
    assert "3.5 of 5, rated by ear" in beside and "How it came out, measured" not in beside  # no parts kept
    assert "as exported" in (folder / "Old.html").read_text(encoding="utf-8")  # not rated: not touched


def test_a_user_sees_their_own_stars_and_the_page_beside_the_song_is_not_theirs(player: Any) -> None:
    port, folder, ids = player
    lea = call(port, "POST", "/api/users", {"name": "Lea", "password": "secret1"}, **JSON)[1]["user"]["id"]
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    connection.request(
        "POST", "/api/login", body=json.dumps({"user": lea, "password": "secret1"}).encode(), headers=JSON
    )
    answer = connection.getresponse()
    answer.read()
    cookie = str(answer.getheader("Set-Cookie")).split(";")[0]
    connection.close()
    rev = call(port, "GET", "/api/state", Cookie=cookie)[1]["rev"]
    saved = call(port, "PUT", "/api/state", {"ratings": {ids["New"]: 1.5}, "rev": rev}, Cookie=cookie, **JSON)
    assert saved[0] == 200
    assert "1.5 of 5, rated by ear" in call(port, "GET", f"/page/{ids['New']}", Cookie=cookie)[1]
    assert "rated by ear" not in call(port, "GET", f"/page/{ids['New']}")[1]  # the admin gave none
    assert "as exported" in (folder / "New.html").read_text(encoding="utf-8")  # only the admin's go there


def test_stars_by_ear_are_kept_clean() -> None:
    assert ratings_of(
        {"aaaaaaaaaaaa": 3.3, "bbbbbbbbbbbb": 0, "c": 2, "dddddddddddd": True, "eeeeeeeeeeee": 6}
    ) == {
        "aaaaaaaaaaaa": 3.5,
        "bbbbbbbbbbbb": 0.0,
    }
    assert ratings_of(None) == {} and ratings_of([1]) == {}
