"""The Plenio Player's folders (owner's request 2026-10-16): several, chosen in its Settings and kept in
``library.json``; and music not made with Plenio, played clearly marked with what its files have - its tags,
its cover, its lyrics, timed lines from an ``.lrc`` - never the files of a Plenio song."""

from __future__ import annotations

import http.client
import io
import json
import sys
import threading
from collections.abc import Iterator
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace

import pytest

from plenio.player import folders as folder_choice
from plenio.player.__main__ import make_library
from plenio.player.library import RETIRED_DIR, Library, song_detail
from plenio.player.other import embedded_cover, is_plenio_file, parse_lrc, plenio_owned, probe, tag_text
from plenio.player.server import State, serve

av = pytest.importorskip("av")
np = pytest.importorskip("numpy")


def tone(path: Path, tags: dict[str, str], *, picture: bytes | None = None, codec: str = "flac") -> None:
    """A second of a quiet tone with tags (and a picture inside), made with PyAV."""
    rate = 48000
    with av.open(str(path), "w") as container:
        for key, value in tags.items():
            container.metadata[key] = value
        stream = container.add_stream(codec, rate=rate)
        stream.layout = "stereo"
        pic = None
        if picture is not None:
            pic = container.add_stream("mjpeg")
            pic.width = pic.height = 8
            pic.pix_fmt = "yuvj420p"
            pic.disposition = av.stream.Disposition.attached_pic
        samples = (0.1 * np.sin(2 * np.pi * 440 * np.arange(rate) / rate)).astype(np.float32)
        planar = (stream.codec_context.format.name if stream.codec_context.format else "fltp").endswith("p")
        data = (
            np.stack([samples, samples]) if planar else np.stack([samples, samples]).T.reshape(1, -1).copy()
        )
        frame = av.AudioFrame.from_ndarray(data, format="fltp" if planar else "flt", layout="stereo")
        frame.sample_rate = rate
        frame.pts = 0
        frame.time_base = Fraction(1, rate)
        for packet in [*stream.encode(frame), *stream.encode(None)]:
            container.mux(packet)
        if pic is not None and picture is not None:
            packet = av.Packet(picture)
            packet.stream = pic
            packet.pts = packet.dts = 0
            packet.time_base = Fraction(1, 90000)
            container.mux(packet)


def jpeg() -> bytes:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), (200, 30, 30)).save(buffer, "JPEG")
    return buffer.getvalue()


def record(title: str) -> dict[str, object]:
    return {
        "schema": "plenio.release/1",
        "title": title,
        "created": "2026-10-10T10:00:00",
        "files": [{"name": f"{title}.flac", "format": "flac"}],
        "audio": {"seconds": 1.0},
    }


@pytest.fixture
def music(tmp_path: Path) -> Path:
    """A folder with a Plenio song (its audio, unmastered take, stems) and other music beside it."""
    folder = tmp_path / "Music"
    (folder / "plenio" / "River-stems").mkdir(parents=True)
    (folder / "plenio" / "River.plenio.json").write_text(json.dumps(record("River")), encoding="utf-8")
    for name in ("River.flac", "River (original).flac", "River-stems/vocals.flac"):
        tone(folder / "plenio" / name, {"title": "a Plenio file"})
    (folder / "albums" / "Jazz").mkdir(parents=True)
    tone(
        folder / "albums" / "Jazz" / "Blue.flac",
        {"title": "Blue Hour", "artist": "Someone", "album": "Nights", "genre": "Jazz", "date": "2019-05-01",
         "lyrics": "the blue hour\nfalls"},
    )  # fmt: skip
    (folder / "albums" / "Jazz" / "Blue.lrc").write_text(
        "[ar:Someone]\n[00:00.20]the blue <00:00.60>hour\n[00:00.80]falls\n", encoding="utf-8"
    )
    tone(folder / "albums" / "Pictured.flac", {"title": "With Picture"}, picture=jpeg())
    (folder / "albums" / "Jazz" / "cover.jpg").write_bytes(jpeg())
    (folder / RETIRED_DIR).mkdir()
    tone(folder / RETIRED_DIR / "Gone.flac", {"title": "Gone"})
    (folder / "albums" / "notes.txt").write_text("not music", encoding="utf-8")
    return folder


def test_other_music_only_where_chosen_and_never_a_plenio_songs_files(music: Path) -> None:
    plenio_only = Library([music])
    plenio_only.scan(force=True)
    assert [s["title"] for s in plenio_only.songs()] == ["River"]
    library = Library([music], other=[music])
    library.scan(force=True)
    titles = sorted(s["title"] for s in library.songs())
    # the Plenio song's audio, unmastered take and stems stay its own; the retired folder stays unread
    assert titles == ["Blue Hour", "River", "With Picture"]
    blue = next(s for s in library.songs() if s["title"] == "Blue Hour")
    assert blue["other"] is True and blue["kind"] == "other" and blue["model"] == ""
    assert (blue["artist"], blue["album"], blue["genre"], blue["year"]) == (
        "Someone",
        "Nights",
        "Jazz",
        "2019",
    )
    assert blue["lyrics"] == "the blue hour\nfalls" and 0.9 < blue["seconds"] < 1.1
    assert blue["has"]["cover"] and blue["has"]["lines"] and not blue["has"]["score"]
    river = next(s for s in library.songs() if s["title"] == "River")
    assert not river.get("other")


def test_a_song_of_other_music_has_its_timed_lyrics_cover_and_files(music: Path, tmp_path: Path) -> None:
    library = Library([music], other=[music])
    library.scan(force=True)
    blue = library.song(next(s["id"] for s in library.songs() if s["title"] == "Blue Hour"))
    assert blue is not None
    detail = song_detail(blue)
    assert detail["notation"] == {} and detail["record_path"] == "" and detail["timing_source"] == "lrc"
    assert [line["text"] for line in detail["lines"]] == ["the blue hour", "falls"]
    assert detail["lines"][0]["units"] == [[0.2, 8], [0.6, 13]]  # word by word
    assert detail["files"] == {"audio": "Blue.flac", "lines": "Blue.lrc", "cover": "cover.jpg"}
    # removing it takes the audio and its own lyrics, never the folder's cover the album shares
    assert detail["owned_files"] == ["Blue.flac", "Blue.lrc"]
    assert library.remove(blue.id, "retire") is not None
    assert (music / "albums" / "Jazz" / "cover.jpg").is_file()
    assert (music / RETIRED_DIR / "albums" / "Jazz" / "Blue.flac").is_file()
    assert "Blue Hour" not in [s["title"] for s in library.songs()]


def test_other_music_is_read_with_pyav_19_too(
    music: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # CI's PyAV 19 removed av.open's metadata_errors: passing it raised, and the files showed no tags
    def open_19(path: str, *args: object, **options: object) -> object:
        if "metadata_errors" in options:
            raise TypeError("open() got an unexpected keyword argument 'metadata_errors'")
        return av.open(path, *args, **options)

    monkeypatch.setitem(sys.modules, "av", SimpleNamespace(__version__="19.0.1", open=open_19))
    found = probe(music / "albums" / "Jazz" / "Blue.flac")
    assert found["tags"]["title"] == "Blue Hour" and found["tags"]["artist"] == "Someone"
    assert found["seconds"] == pytest.approx(1.0, abs=0.05)
    cover = embedded_cover(music / "albums" / "Pictured.flac", "abc", tmp_path / "cache")
    assert cover is not None and cover.read_bytes()[:2] == b"\xff\xd8"
    # PyAV 19 hands tags that are not UTF-8 over as surrogates: they are dropped, so the page's JSON holds
    assert tag_text("caf\udce9 au lait") == "caf au lait"
    assert tag_text("Café \ud800x") == "Café x"
    assert tag_text(2019) == "2019"


def test_lrc_lines_and_word_times() -> None:
    lines = parse_lrc("[ti:x]\n[00:01.00][00:09.50]chorus\n[00:03.00]<00:03.00>one <00:03.40>two\n\n[bad]\n")
    assert [(line["text"], line["start"]) for line in lines] == [
        ("chorus", 1.0),
        ("one two", 3.0),
        ("chorus", 9.5),
    ]
    assert lines[1]["units"] == [[3.0, 3], [3.4, 7]]
    assert lines[0]["end"] == pytest.approx(2.95) and lines[2]["end"] == pytest.approx(13.45)


def test_what_belongs_to_a_plenio_song(music: Path) -> None:
    library = Library([music])
    library.scan(force=True)
    songs = [library.song(s["id"]) for s in library.songs()]
    owned, stems = plenio_owned(s for s in songs if s)
    folder = music / "plenio"
    for name in ("River.flac", "River (original).flac", "River take 2.flac", "River-stems/vocals.flac"):
        assert is_plenio_file(folder / name, owned, stems), name
    for name in ("Riverside.flac", "Other.flac"):
        assert not is_plenio_file(folder / name, owned, stems), name


@pytest.fixture
def server(music: Path, tmp_path: Path) -> Iterator[tuple[str, int, Library, Path]]:
    library = Library([music / "plenio"], cache=tmp_path / "state" / "cache.json")
    library.scan(force=True)
    state = State(tmp_path / "state" / "state.json")
    running = serve(library, state, "127.0.0.1", 0)
    threading.Thread(target=running.serve_forever, daemon=True).start()
    yield "127.0.0.1", running.server_address[1], library, tmp_path / "state"
    running.shutdown()
    running.server_close()


def call(
    address: tuple[str, int, Library, Path], method: str, path: str, body: object = None, **headers: str
):
    connection = http.client.HTTPConnection(address[0], address[1], timeout=20)
    data = json.dumps(body).encode() if body is not None else None
    if data is not None:
        headers.setdefault("Content-Type", "application/json")
    connection.request(method, path, body=data, headers=headers)
    answer = connection.getresponse()
    payload = answer.read()
    connection.close()
    return answer.status, json.loads(payload) if payload.startswith((b"{", b"[")) else payload


def test_settings_choose_several_folders_and_other_music(
    server: tuple[str, int, Library, Path], music: Path, tmp_path: Path
) -> None:
    status, answer = call(server, "GET", "/api/folders")
    assert status == 200 and not answer["chosen"]
    assert [f["path"] for f in answer["folders"]] == [str((music / "plenio").resolve())]
    assert answer["folders"][0]["songs"] == 1
    second = tmp_path / "More"
    second.mkdir()
    chosen = [
        {"path": str(music / "plenio")},
        {"path": str(music / "albums"), "other": True},
        {"path": str(second)},
    ]
    status, answer = call(server, "PUT", "/api/folders", {"folders": chosen})
    assert status == 200 and answer["chosen"]
    rows = {Path(f["path"]).name: f for f in answer["folders"]}
    assert (rows["plenio"]["songs"], rows["albums"]["other_songs"], rows["More"]["songs"]) == (1, 2, 0)
    assert rows["albums"]["other"] and not rows["plenio"]["other"]
    saved = json.loads((server[3] / "library.json").read_text(encoding="utf-8"))
    assert [f["other"] for f in saved["folders"]] == [False, True, False]
    titles = sorted(s["title"] for s in call(server, "GET", "/api/library")[1]["songs"])
    assert titles == ["Blue Hour", "River", "With Picture"]
    # the picture inside a file is its cover
    pictured = next(
        s for s in call(server, "GET", "/api/library")[1]["songs"] if s["title"] == "With Picture"
    )
    status, cover = call(server, "GET", f"/media/{pictured['id']}/cover")
    assert status == 200 and cover[:2] == b"\xff\xd8"
    # back to the folders it started with
    status, answer = call(server, "PUT", "/api/folders", {"reset": True})
    assert status == 200 and not answer["chosen"] and len(answer["folders"]) == 1
    assert not (server[3] / "library.json").exists()


def test_folders_are_checked_and_only_the_players_page_changes_them(
    server: tuple[str, int, Library, Path], music: Path
) -> None:
    missing = {"folders": [{"path": str(music / "nowhere")}]}
    status, answer = call(server, "PUT", "/api/folders", missing)
    assert status == 400 and "no such folder" in answer["error"]
    assert call(server, "PUT", "/api/folders", {"folders": [{"path": "relative/path"}]})[0] == 400
    assert call(server, "PUT", "/api/folders", {"folders": []})[0] == 400
    good = {"folders": [{"path": str(music)}]}
    assert call(server, "PUT", "/api/folders", good, **{"Content-Type": "text/plain"})[0] == 403
    assert call(server, "PUT", "/api/folders", good, Origin="http://evil.example")[0] == 403
    assert not (server[3] / "library.json").exists()


def test_the_folder_browser_lists_folders_only_and_only_for_the_page(
    server: tuple[str, int, Library, Path], music: Path
) -> None:
    assert call(server, "GET", f"/api/dirs?path={music}")[0] == 403
    status, answer = call(server, "GET", f"/api/dirs?path={music}", **{"X-Plenio-Player": "1"})
    assert (
        status == 200
        and answer["path"] == str(music.resolve())
        and answer["parent"] == str(music.resolve().parent)
    )
    assert [d["name"] for d in answer["dirs"]] == [RETIRED_DIR, "albums", "plenio"]
    assert any(place["name"] == "Home" for place in answer["places"])
    start = call(server, "GET", "/api/dirs", **{"X-Plenio-Player": "1"})[1]
    assert start["path"] is None and start["places"]
    assert call(server, "GET", "/api/dirs?path=does-not-exist", **{"X-Plenio-Player": "1"})[1]["error"]


def test_the_folders_chosen_in_settings_win_at_the_start(music: Path, tmp_path: Path) -> None:
    state = tmp_path / "state"
    library = make_library([music / "plenio"], state)
    assert library.folders == [(music / "plenio").resolve()] and not library.other
    folder_choice.save(state, [folder_choice.Folder(music.resolve(), other=True)])
    library = make_library([music / "plenio"], state)
    assert library.folders == [music.resolve()] and library.other == {music.resolve()}
    assert library.started_with == [(music / "plenio").resolve()]
