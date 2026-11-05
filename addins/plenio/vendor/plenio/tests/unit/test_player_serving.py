"""How the Plenio Player serves a large library fast and safely (2026-10-26, a library of 2958 songs): the library
compressed and answered *unchanged* to a page that has it, small cover pictures for the cards, the folders read
again without holding up a reader, a request that fails answered with its reason, and the page kept out of other
sites' frames."""

from __future__ import annotations

import gzip
import http.client
import io
import json
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from plenio.player import server as server_module
from plenio.player.library import Library
from plenio.player.server import State, serve
from plenio.player.thumbs import thumbnail

PIL = pytest.importorskip("PIL.Image")


def record(title: str) -> dict[str, object]:
    return {
        "schema": "plenio.record/1",
        "title": title,
        "created": "2026-10-15T10:00:00Z",
        "documents": {"lyrics": {"text": "[Verse]\nla la la", "sha256": "l1"}, "style": {"text": "folk"}},
        "audio": {"seconds": 6.0, "tags": {"artist": "Plenio"}},
        "files": [{"name": f"{title}.flac", "format": "flac"}],
        "reports": [{"kind": "render", "data": {"engine": "yue2"}}],
    }


def cover(path: Path, size: int = 900) -> None:
    PIL.new("RGB", (size, size), (200, 40, 90)).save(path, "JPEG", quality=95)


@pytest.fixture
def songs(tmp_path: Path) -> Path:
    folder = tmp_path / "output" / "plenio"
    folder.mkdir(parents=True)
    for number in range(40):
        title = f"Song {number:02d}"
        data = record(title)
        data["files"] = [
            {"name": f"{title}.flac", "format": "flac"},
            {"name": f"{title}.jpg", "role": "cover"},
        ]
        (folder / f"{title}.plenio.json").write_text(json.dumps(data), encoding="utf-8")
        (folder / f"{title}.flac").write_bytes(b"x" * 100)
    cover(folder / "Song 00.jpg")
    return tmp_path / "output"


@pytest.fixture
def server(songs: Path, tmp_path: Path) -> Iterator[tuple[str, int, Library]]:
    library = Library([songs], cache=tmp_path / "state" / "cache.json")
    library.scan(force=True)
    running = serve(library, State(tmp_path / "state" / "state.json"), "127.0.0.1", 0)
    thread = threading.Thread(target=running.serve_forever, daemon=True)
    thread.start()
    yield "127.0.0.1", running.server_address[1], library
    running.shutdown()
    running.server_close()


def call(
    address: tuple[str, int, Library], method: str, path: str, body: bytes | None = None, **headers: str
) -> tuple[int, dict[str, str], bytes]:
    host, port, _ = address
    connection = http.client.HTTPConnection(host, port, timeout=10)
    connection.request(method, path, body=body, headers=headers)
    answer = connection.getresponse()
    data = answer.read()
    connection.close()
    return answer.status, dict(answer.getheaders()), data


def test_the_library_goes_compressed_and_unchanged_needs_no_body(server: tuple[str, int, Library]) -> None:
    status, headers, plain = call(server, "GET", "/api/library")
    assert status == 200 and "Content-Encoding" not in headers and len(json.loads(plain)["songs"]) == 40
    status, headers, packed = call(server, "GET", "/api/library", **{"Accept-Encoding": "gzip, deflate"})
    assert status == 200 and headers["Content-Encoding"] == "gzip" and headers["Vary"] == "Accept-Encoding"
    assert gzip.decompress(packed) == plain and len(packed) < len(plain) / 3
    # the browser keeps it and asks with its ETag: nothing changed, no body
    etag = headers["ETag"]
    assert headers["Cache-Control"] == "no-cache"
    status, headers, body = call(server, "GET", "/api/library", **{"If-None-Match": etag})
    assert status == 304 and body == b"" and headers["ETag"] == etag
    # a song more: another ETag, the new song in it
    folder = server[2].folders[0] / "plenio"
    (folder / "Fresh.plenio.json").write_text(json.dumps(record("Fresh")), encoding="utf-8")
    server[2].scan(force=True)
    status, headers, body = call(server, "GET", "/api/library", **{"If-None-Match": etag})
    assert status == 200 and headers["ETag"] != etag and len(json.loads(body)["songs"]) == 41


def test_a_player_started_again_never_answers_unchanged_for_the_one_before(
    server: tuple[str, int, Library], monkeypatch: pytest.MonkeyPatch
) -> None:
    etag = call(server, "GET", "/api/library")[1]["ETag"]
    assert call(server, "GET", "/api/library", **{"If-None-Match": etag})[0] == 304
    # the same library version, another start of the player: its ETag is another one
    monkeypatch.setattr(server_module, "BOOT", "another")
    status, headers, _ = call(server, "GET", "/api/library", **{"If-None-Match": etag})
    assert status == 200 and headers["ETag"] != etag and "another" in headers["ETag"]


def test_the_cards_get_small_covers(server: tuple[str, int, Library]) -> None:
    song = next(
        s for s in json.loads(call(server, "GET", "/api/library")[2])["songs"] if s["title"] == "Song 00"
    )
    status, headers, full = call(server, "GET", f"/media/{song['id']}/cover")
    assert status == 200 and PIL.open(io.BytesIO(full)).size == (900, 900)
    status, headers, small = call(server, "GET", f"/media/{song['id']}/cover?size=256")
    assert status == 200 and headers["Content-Type"] == "image/jpeg" and "max-age" in headers["Cache-Control"]
    assert PIL.open(io.BytesIO(small)).size == (256, 256) and len(small) < len(full)
    # a size the player does not make: the cover as it is
    assert call(server, "GET", f"/media/{song['id']}/cover?size=333")[2] == full
    # a picture asked again with its ETag: unchanged
    etag = headers["ETag"]
    assert call(server, "GET", f"/media/{song['id']}/cover?size=256", **{"If-None-Match": etag})[0] == 304


def test_a_thumbnail_is_made_once_per_size_and_picture(tmp_path: Path) -> None:
    source = tmp_path / "cover.jpg"
    cover(source, 600)
    made = thumbnail(source, 128, tmp_path / "thumbs")
    assert made is not None and PIL.open(made).size == (128, 128)
    stamp = made.stat().st_mtime_ns
    assert thumbnail(source, 128, tmp_path / "thumbs") == made and made.stat().st_mtime_ns == stamp
    # a new picture: a new file
    time.sleep(0.01)
    cover(source, 500)
    assert thumbnail(source, 128, tmp_path / "thumbs") != made
    # not a picture: none
    (tmp_path / "broken.jpg").write_bytes(b"not a picture")
    assert thumbnail(tmp_path / "broken.jpg", 128, tmp_path / "thumbs") is None


def test_a_reader_does_not_wait_while_the_folders_are_read_again(songs: Path, tmp_path: Path) -> None:
    library = Library([songs], cache=tmp_path / "cache.json")
    assert len(library.songs()) == 40  # the first time a reader waits
    song_id = library.songs()[0]["id"]
    library._scanned = 0.0  # older than a reader's limit: read again in the background
    with library._lock:  # as if a long reading of thousands of records were going on
        started = time.monotonic()
        assert library.song(song_id) is not None
        assert len(library.songs()) == 40
        assert time.monotonic() - started < 0.5
    deadline = time.monotonic() + 5
    while library._background is not None and library._background.is_alive() and time.monotonic() < deadline:
        time.sleep(0.02)
    assert library._scanned > 0


def test_unchanged_folders_are_not_written_into_the_cache_again(songs: Path, tmp_path: Path) -> None:
    cache = tmp_path / "cache.json"
    library = Library([songs], cache=cache)
    library.scan(force=True)
    written = cache.stat().st_mtime_ns
    version = library.version
    time.sleep(0.02)
    library.scan(force=True)
    assert cache.stat().st_mtime_ns == written and library.version == version
    (songs / "plenio" / "Fresh.plenio.json").write_text(json.dumps(record("Fresh")), encoding="utf-8")
    library.scan(force=True)
    assert cache.stat().st_mtime_ns != written and library.version == version + 1
    assert "Fresh" in {s["title"] for s in library.songs()}


def test_many_songs_of_one_title_are_numbered_in_order(tmp_path: Path) -> None:
    folder = tmp_path / "plenio"
    folder.mkdir()
    for number in range(300):
        data = record("Yesterday")
        data["created"] = f"2026-10-{1 + number // 100:02d}T10:{number % 60:02d}:{number % 50:02d}Z"
        (folder / f"Yesterday {number}.plenio.json").write_text(json.dumps(data), encoding="utf-8")
    library = Library([tmp_path])
    started = time.monotonic()
    titles = {s["title"] for s in library.songs()}
    assert time.monotonic() - started < 10
    assert len(titles) == 300 and "Yesterday" in titles and "Yesterday (300)" in titles


def test_while_the_folders_are_read_the_first_time_the_page_hears_how_far(
    songs: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = Library([songs], cache=tmp_path / "cache.json")
    monkeypatch.setattr(server_module, "LIBRARY_WAIT_S", 0.05)
    running = serve(library, State(tmp_path / "state.json"), "127.0.0.1", 0)
    threading.Thread(target=running.serve_forever, daemon=True).start()
    address = ("127.0.0.1", running.server_address[1], library)
    try:
        with library._lock:  # the first reading is still going on
            answer = json.loads(call(address, "GET", "/api/library")[2])
            assert answer["songs"] == [] and set(answer["scanning"]) == {"done", "total"}
        deadline = time.monotonic() + 5
        while not library.ready and time.monotonic() < deadline:
            time.sleep(0.02)
        answer = json.loads(call(address, "GET", "/api/library")[2])
        assert len(answer["songs"]) == 40 and "scanning" not in answer
    finally:
        running.shutdown()
        running.server_close()


def test_a_request_that_fails_is_answered_with_its_reason(
    server: tuple[str, int, Library], monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(song_id: str) -> None:
        raise RuntimeError("the disk went away")

    monkeypatch.setattr(server[2], "song", broken)
    status, headers, body = call(server, "GET", "/api/song/abc")
    assert status == 500 and "the disk went away" in json.loads(body)["error"]
    # and the player goes on
    assert call(server, "GET", "/api/library")[0] == 200


def test_a_wrong_length_is_refused(server: tuple[str, int, Library]) -> None:
    host, port, _ = server
    connection = http.client.HTTPConnection(host, port, timeout=10)
    connection.putrequest("PUT", "/api/state")
    connection.putheader("Content-Type", "application/json")
    connection.putheader("Content-Length", "lots")
    connection.endheaders()
    assert connection.getresponse().status == 413
    connection.close()


def test_the_page_is_kept_out_of_other_sites_frames(server: tuple[str, int, Library]) -> None:
    for path in ("/", "/api/library"):
        headers = call(server, "GET", path)[1]
        assert headers["X-Frame-Options"] == "SAMEORIGIN"
        assert headers["Content-Security-Policy"] == "frame-ancestors 'self'"
        assert headers["X-Content-Type-Options"] == "nosniff"
