"""The demo page's showcase tool (``tools/demo_showcase.py``): the data file the page reads, YouTube links, a song's
entry from its record (only what its page in the player shows) and taking an entry out again."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]


def load_tool() -> Any:
    spec = importlib.util.spec_from_file_location("demo_showcase", ROOT / "tools" / "demo_showcase.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["demo_showcase"] = module
    spec.loader.exec_module(module)
    return module


tool = load_tool()


def record(title: str = "Neon Test", *, instrumental: bool = False) -> dict[str, Any]:
    brief = {
        "class_type": "PlenioSongBrief",
        "inputs": {
            "genre": "synth-pop",
            "vocals": "instrumental" if instrumental else "sung",
            "vocals.language": "English",
        },
    }
    return {
        "schema": "plenio.record/1",
        "created": "2026-10-29T08:33:22+0100",
        "title": title,
        "versions": {"plenio": "1.4.0"},
        "documents": {
            "style": {"text": "synth-pop, bright, 128 BPM"},
            "lyrics": {"text": "[Verse]\nThe city hums\n\n[Chorus]\nHold me in the glow"},
            "score": {"text": "X:1\nQ:1/4=128\nK:Bm\n"},
            "artwork_prompt": {"text": "a secret prompt"},
        },
        "audio": {"seconds": 103.92, "tags": {"genre": "synth-pop"}},
        "prompt": {"2": brief, "7": {"class_type": "PlenioWriteSong", "inputs": {"seed": 1779865293}}},
        "made": {
            "started": "2026-10-29T08:30:53+0100",
            "seconds": 148.9,
            "on": {
                "device": "gpu",
                "gpu": "NVIDIA GeForce RTX 5060 Ti",
                "cpu": "AMD Ryzen 9",
                "ram_gb": 61.6,
            },
        },
        "files": [],
    }


def song_folder(tmp_path: Path, title: str = "Neon Test", **kw: Any) -> Path:
    folder = tmp_path / "output"
    folder.mkdir(exist_ok=True)
    stem = f"2026-10-29 {title}"
    path = folder / f"{stem}.plenio.json"
    path.write_text(json.dumps(record(title, **kw)), encoding="utf-8")
    Image.new("RGB", (900, 700), (120, 40, 200)).save(folder / f"{stem}.jpg")
    (folder / f"{stem}.mp3").write_bytes(b"ID3fake-mp3")
    return path


def test_the_data_file_round_trips_as_the_page_reads_it(tmp_path: Path) -> None:
    path = tmp_path / "demo-showcase.js"
    assert tool.load(path)["entries"] == []
    data = {
        "playlist": tool.PLAYLIST,
        "entries": [{"id": "a", "kind": "video", "title": "Ä song", "youtube": "hPq9tUjTzr0"}],
    }
    tool.save(data, path)
    text = path.read_text(encoding="utf-8")
    assert text.startswith("//") and "window.PLENIO_SHOWCASE = {" in text and text.rstrip().endswith("};")
    assert "Ä song" in text
    assert tool.load(path) == data


def test_the_repository_file_is_valid() -> None:
    data = tool.load(ROOT / "docs" / "demo-showcase.js")
    ids = [entry["id"] for entry in data["entries"]]
    assert len(ids) == len(set(ids))
    for entry in data["entries"]:
        assert entry["kind"] in ("song", "video")
        assert entry.get("youtube") or entry.get("soundcloud") or entry.get("audio")
        if entry.get("youtube"):
            assert tool.YOUTUBE_ID.match(entry["youtube"])


@pytest.mark.parametrize(
    "link",
    [
        "hPq9tUjTzr0",
        "https://youtu.be/hPq9tUjTzr0",
        "https://www.youtube.com/watch?v=hPq9tUjTzr0&list=PLBZzzh1IMZzk",
        "https://youtube.com/shorts/hPq9tUjTzr0?feature=share",
        "https://www.youtube-nocookie.com/embed/hPq9tUjTzr0",
    ],
)
def test_youtube_links_give_the_video_id(link: str) -> None:
    assert tool.youtube_id(link) == "hPq9tUjTzr0"


def test_a_link_that_is_no_video_is_refused() -> None:
    with pytest.raises(tool.ShowcaseError):
        tool.youtube_id("https://www.youtube.com/playlist?list=PLBZzzh1IMZzk")


def test_ids_are_unique() -> None:
    assert tool.slug("Neon Midnight (3)", set()) == "neon-midnight-3"
    assert tool.slug("Neon Midnight", {"neon-midnight"}) == "neon-midnight-2"
    assert tool.slug("Luces de Neón", set()) == "luces-de-ne-n"
    assert tool.slug("!!!", set()) == "song"


def test_a_song_entry_holds_what_its_page_shows_and_no_prompt(tmp_path: Path) -> None:
    summary, files = tool.read_song(song_folder(tmp_path))
    docs = tmp_path / "docs"
    entry = tool.song_entry(summary, files, set(), audio=True, docs=docs, today="2026-10-29")
    assert entry["id"] == "neon-test" and entry["kind"] == "song" and entry["title"] == "Neon Test"
    assert entry["genre"] == "synth-pop" and entry["language"] == "English"
    assert entry["seconds"] == 103.9 and entry["bpm"] == 128 and entry["key"] == "Bm"
    assert "Hold me in the glow" in entry["lyrics"] and "[Chorus]" not in entry["lyrics"]
    assert entry["made"] == {"date": "2026-10-29", "seconds": 148.9, "on": "NVIDIA GeForce RTX 5060 Ti"}
    assert (
        entry["audio"] == "assets/showcase/neon-test.mp3"
        and (docs / entry["audio"]).read_bytes() == b"ID3fake-mp3"
    )
    with Image.open(docs / entry["cover"]) as cover:
        assert cover.size == (640, 640)
    text = json.dumps(entry)
    for secret in ("secret prompt", "1779865293", "Ryzen", "61.6", str(tmp_path).replace("\\", "\\\\")):
        assert secret not in text


def test_lyrics_can_be_left_out_and_an_instrumental_has_none(tmp_path: Path) -> None:
    summary, files = tool.read_song(song_folder(tmp_path))
    entry = tool.song_entry(
        summary, files, set(), soundcloud="https://soundcloud.com/a/b", lyrics=False, docs=tmp_path / "d"
    )
    assert "lyrics" not in entry and entry["soundcloud"] == "https://soundcloud.com/a/b"
    summary, files = tool.read_song(song_folder(tmp_path, "Calm", instrumental=True))
    entry = tool.song_entry(
        summary, files, set(), youtube="https://youtu.be/hPq9tUjTzr0", docs=tmp_path / "d"
    )
    assert entry["vocals"] == "instrumental" and "lyrics" not in entry and entry["youtube"] == "hPq9tUjTzr0"


def test_a_song_without_anything_to_play_is_refused(tmp_path: Path) -> None:
    summary, files = tool.read_song(song_folder(tmp_path))
    with pytest.raises(tool.ShowcaseError, match="where the song plays"):
        tool.song_entry(summary, files, set(), docs=tmp_path / "d")
    with pytest.raises(tool.ShowcaseError, match="SoundCloud"):
        tool.song_entry(summary, files, set(), soundcloud="https://example.com/x", docs=tmp_path / "d")


def test_a_song_exported_without_an_mp3_gets_one_from_its_flac(tmp_path: Path) -> None:
    import numpy as np

    from plenio.core.release import write_audio

    path = song_folder(tmp_path)
    path.with_name("2026-10-29 Neon Test.mp3").unlink()
    t = np.arange(48000) / 48000
    write_audio(
        path.with_name("2026-10-29 Neon Test.flac"), np.stack([np.sin(2 * np.pi * 440 * t)] * 2) * 0.3, 48000
    )
    summary, files = tool.read_song(path)
    docs = tmp_path / "docs"
    entry = tool.song_entry(summary, files, set(), audio=True, docs=docs)
    mp3 = docs / entry["audio"]
    data = mp3.read_bytes()
    assert data[:3] == b"ID3" or data[0] == 0xFF  # tags first, or straight the first MPEG frame
    import av

    with av.open(str(mp3)) as container:
        assert container.streams.audio[0].codec_context.name.startswith("mp3")  # the decoder: mp3 or mp3float
        seconds = float(container.duration or 0) / av.time_base
    assert abs(seconds - 1.0) < 0.2


def test_remove_takes_the_copied_files_too(tmp_path: Path) -> None:
    summary, files = tool.read_song(song_folder(tmp_path))
    docs = tmp_path / "docs"
    entry = tool.song_entry(summary, files, set(), audio=True, docs=docs)
    data = {"playlist": tool.PLAYLIST, "entries": [entry]}
    assert tool.remove(data, "neon-test", docs) == entry and data["entries"] == []
    assert not (docs / entry["cover"]).exists() and not (docs / entry["audio"]).exists()
    with pytest.raises(tool.ShowcaseError):
        tool.remove(data, "neon-test", docs)


def test_a_video_entry() -> None:
    entry = tool.video_entry(
        "https://youtu.be/hPq9tUjTzr0",
        "Restrained Driving Atmosphere",
        {"x"},
        genre="Progressive Trance",
        today="2026-10-29",
    )
    assert entry == {
        "id": "restrained-driving-atmosphere",
        "kind": "video",
        "title": "Restrained Driving Atmosphere",
        "genre": "Progressive Trance",
        "youtube": "hPq9tUjTzr0",
        "added": "2026-10-29",
    }
