"""The video tutorials: the README and the docs link every tutorial to the video the player's help plays
(frontend/src/player/help.ts), so a tutorial uploaded anew is changed everywhere or the tests say where not."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VIDEO = r"https://youtu\.be/([\w-]{11})"


def player_tutorials() -> dict[str, str]:
    """The videos in the player's help: the tutorials by number, the films without one (★) by title."""
    help_ts = (ROOT / "frontend" / "src" / "player" / "help.ts").read_text(encoding="utf-8")
    found = re.findall(r"\{ id: '([\w-]{11})', number: '([^']+)', title: '([^']+)'", help_ts)
    return {number if number.isdigit() else title: video for video, number, title in found}


def linked_videos() -> list[tuple[str, str, str]]:
    """Every YouTube video the README and the docs link: (file, link text or picture's alt text, video)."""
    links = []
    for path in [ROOT / "README.md", *sorted((ROOT / "docs").rglob("*.md"))]:
        text = path.read_text(encoding="utf-8")
        name = path.relative_to(ROOT).as_posix()
        links += [(name, label, video) for label, video in re.findall(rf"\[([^\]]+)\]\({VIDEO}\)", text)]
        links += [
            (name, label, video)
            for video, label in re.findall(rf'<a href="{VIDEO}"><img [^>]*alt="([^"]+)"', text)
        ]
    return links


def test_every_tutorial_link_plays_the_video_the_player_plays() -> None:
    tutorials = player_tutorials()
    wrong, in_readme = [], set()
    for name, label, video in linked_videos():
        number = re.match(r"(?:Tutorial )?(\d+) · ", label)
        key = number.group(1) if number else label
        if key not in tutorials:
            continue  # a song's video, not a tutorial
        if name == "README.md":
            in_readme.add(key)
        if video != tutorials[key]:
            wrong.append(f"{name}: {label} -> {video}, the player plays {tutorials[key]}")
    assert wrong == []
    # the README's table and its two films name every video of the player's help (the links above were read)
    assert in_readme == set(tutorials)
