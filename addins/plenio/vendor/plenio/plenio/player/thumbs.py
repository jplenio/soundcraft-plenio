"""Small pictures of the songs' covers for the library's cards (2026-10-26): a cover of 1024 px is 150-300 KB, so a
page of 120 cards was 25 MB to a phone in the network. With Pillow (ComfyUI's Python has it) the player makes each
size once and keeps it in its cache; without Pillow the card gets the cover as it is.
"""

from __future__ import annotations

import hashlib
import os
import secrets
from pathlib import Path


def thumbnail(source: Path, size: int, cache: Path) -> Path | None:
    """``source`` at most ``size`` pixels wide and high, as a JPEG in ``cache`` (made once per size and per version
    of the picture); ``None``: no picture made - no Pillow, or a file it cannot read."""
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        stat = source.stat()
    except OSError:
        return None
    identity = f"{source.resolve()}|{stat.st_size}|{stat.st_mtime_ns}|{size}"
    key = hashlib.sha1(identity.encode()).hexdigest()[:24]
    target = cache / f"{key}.jpg"
    if target.is_file():
        return target
    temp = cache / f".{key}-{secrets.token_hex(4)}.tmp"
    try:
        cache.mkdir(parents=True, exist_ok=True)
        with Image.open(source) as image:
            image.draft("RGB", (size, size))  # a JPEG decodes at a smaller scale: much faster
            small = image.convert("RGB")
            small.thumbnail((size, size), Image.Resampling.LANCZOS)
            small.save(temp, "JPEG", quality=84, optimize=True, progressive=True)
        os.replace(temp, target)
    except (OSError, ValueError, Image.DecompressionBombError):
        temp.unlink(missing_ok=True)
        return None
    return target
