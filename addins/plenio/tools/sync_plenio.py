#!/usr/bin/env python3
"""Copy the parts of the Plenio Music Production System that the SoundCraft add-in uses into
``addins/plenio/vendor/plenio``, unchanged, and record where they came from.

    python addins/plenio/tools/sync_plenio.py --from <Plenio checkout> [--ref HEAD] [--dry-run]
    python addins/plenio/tools/sync_plenio.py --check

The Plenio repository is only read: the files come from a commit (``--ref``, default ``HEAD``) as
Git stores them, so uncommitted changes there are never copied and every sync of one commit gives
the same files. ``--check`` verifies that nobody edited the copy by hand: adaptations belong in the
add-in's own code (``addins/plenio/backend``, ``addins/plenio/frontend/overlay``), never in
``vendor/``.

MiniMax is not part of the add-in: its templates and blueprints are not copied. Plenio's core code
names MiniMax in a few modules; those are copied as they are and simply not used.

Standard library only (Python 3.10 or newer).
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import re
import subprocess
import sys
from pathlib import Path

ADDIN = Path(__file__).resolve().parents[1]
VENDOR = ADDIN / "vendor"
TREE = VENDOR / "plenio"
MANIFEST = VENDOR / "VENDOR.toml"
HASHES = VENDOR / "VENDOR.sha256"
SOURCE_URL = "https://github.com/jplenio/Plenio-Music-Production-System"

# Folders copied whole (relative to the Plenio checkout).
FOLDERS = (
    "plenio/",
    "resources/",
    "frontend/",
    "tests/",
    "tools/",
    "subgraphs/",
    "example_workflows/",
    "locales/",
)
# Single files at the top of the checkout.
FILES = (
    "LICENSE",
    "NOTICE.md",
    "THIRD_PARTY.md",
    "README.md",
    "CHANGELOG.md",
    "SECURITY.md",
    "pyproject.toml",
    "requirements.txt",
    "__init__.py",
    "plenio_player.py",
    "plenio_player.sh",
    "Plenio Player.bat",
)
# Folders left out although their parent is copied: the tutorial videos' production files (their
# narration and showcase images are not needed and not ours to redistribute here).
SKIPPED = ("tools/tutorials/",)
# Folders whose files are left out when their name says MiniMax (templates and blueprints).
NO_MINIMAX_IN = ("subgraphs/", "example_workflows/")
MINIMAX = re.compile(r"minimax", re.IGNORECASE)


class SyncError(Exception):
    pass


def selected(path: str) -> bool:
    """Whether the add-in uses this file of the Plenio checkout."""
    if path in FILES:
        return True
    if not path.startswith(FOLDERS) or path.startswith(SKIPPED):
        return False
    if path.startswith(NO_MINIMAX_IN) and MINIMAX.search(path.rsplit("/", 1)[-1]):
        return False
    return True


def digest(data: bytes) -> str:
    """SHA-256 of a file as Git keeps it: text (no NUL byte) with CRLF read as LF, so a checkout's
    line endings never make a file look edited."""
    if b"\0" not in data:
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def git(source: Path, *args: str, stdin: bytes | None = None) -> bytes:
    try:
        done = subprocess.run(["git", "-C", str(source), *args], input=stdin, capture_output=True, check=False)
    except OSError as error:
        raise SyncError(f"git could not be started: {error}") from error
    if done.returncode != 0:
        raise SyncError(f"git {' '.join(args)}: {done.stderr.decode('utf-8', 'replace').strip()}")
    return done.stdout


def read_commit(source: Path, ref: str) -> tuple[str, dict[str, bytes]]:
    """The commit ``ref`` names and the contents of its selected files."""
    commit = git(source, "rev-parse", "--verify", f"{ref}^{{commit}}").decode().strip()
    listing = git(source, "ls-tree", "-r", "-z", "--full-tree", commit)
    blobs: list[tuple[str, str]] = []
    for entry in listing.split(b"\0"):
        if not entry:
            continue
        meta, _, raw_path = entry.partition(b"\t")
        mode, kind, sha = meta.decode().split()
        path = raw_path.decode("utf-8")
        if kind == "blob" and mode != "120000" and selected(path):
            blobs.append((path, sha))
    batch = git(source, "cat-file", "--batch", stdin="".join(f"{sha}\n" for _, sha in blobs).encode())
    files: dict[str, bytes] = {}
    at = 0
    for path, sha in blobs:
        header_end = batch.index(b"\n", at)
        got_sha, kind, size = batch[at:header_end].decode().split()
        if got_sha != sha or kind != "blob":
            raise SyncError(f"unexpected answer from git cat-file for {path}")
        start = header_end + 1
        end = start + int(size)
        files[path] = batch[start:end]
        at = end + 1
    return commit, files


def version_of(files: dict[str, bytes]) -> str:
    text = files.get("pyproject.toml", b"").decode("utf-8", "replace")
    found = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    return found.group(1) if found else "unknown"


def recorded_hashes() -> dict[str, str]:
    if not HASHES.is_file():
        return {}
    out = {}
    for line in HASHES.read_text(encoding="utf-8").splitlines():
        sha, _, path = line.partition("  ")
        if sha and path:
            out[path] = sha
    return out


def present_files() -> dict[str, Path]:
    if not TREE.is_dir():
        return {}
    return {p.relative_to(TREE).as_posix(): p for p in TREE.rglob("*") if p.is_file()}


def sync(source: Path, ref: str, dry_run: bool) -> int:
    if not (source / ".git").exists():
        raise SyncError(f"{source} is not a Git checkout of Plenio")
    commit, files = read_commit(source, ref)
    old = recorded_hashes()
    new = {path: digest(data) for path, data in files.items()}
    added = sorted(set(new) - set(old))
    removed = sorted(set(old) - set(new))
    changed = sorted(p for p in set(new) & set(old) if new[p] != old[p])
    print(f"Plenio {version_of(files)} at {commit[:12]}: {len(files)} files")
    print(f"  added {len(added)}, changed {len(changed)}, removed {len(removed)}")
    for label, paths in (("+", added), ("~", changed), ("-", removed)):
        for path in paths[:40]:
            print(f"  {label} {path}")
        if len(paths) > 40:
            print(f"  {label} … and {len(paths) - 40} more")
    if dry_run:
        return 0
    present = present_files()
    for path in present.keys() - files.keys():
        present[path].unlink()
    for path, data in files.items():
        target = TREE / path
        if path in present and digest(present[path].read_bytes()) == new[path]:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    for folder in sorted((p for p in TREE.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
        if not any(folder.iterdir()):
            folder.rmdir()
    HASHES.write_text("".join(f"{new[p]}  {p}\n" for p in sorted(new)), encoding="utf-8", newline="\n")
    MANIFEST.write_text(
        "# Written by addins/plenio/tools/sync_plenio.py - do not edit by hand.\n"
        f'source = "{SOURCE_URL}"\n'
        f'commit = "{commit}"\n'
        f'version = "{version_of(files)}"\n'
        f'synced = "{datetime.date.today().isoformat()}"\n'
        f"files = {len(files)}\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"wrote {TREE.relative_to(ADDIN.parents[1])} and {MANIFEST.name}")
    return 0


def check() -> int:
    recorded = recorded_hashes()
    if not recorded:
        print("no copy of Plenio yet (run with --from)")
        return 1
    present = present_files()
    missing = sorted(set(recorded) - set(present))
    extra = sorted(set(present) - set(recorded))
    edited = sorted(p for p in set(recorded) & set(present) if digest(present[p].read_bytes()) != recorded[p])
    for label, paths in (("missing", missing), ("not from Plenio", extra), ("edited by hand", edited)):
        for path in paths:
            print(f"{label}: {path}")
    if missing or extra or edited:
        print("vendor/plenio differs from the recorded copy: adaptations belong outside vendor/, then sync again")
        return 1
    print(f"vendor/plenio: {len(recorded)} files as copied")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--from", dest="source", type=Path, help="the Plenio checkout to copy from (only read)")
    parser.add_argument("--ref", default="HEAD", help="the commit to copy (default HEAD)")
    parser.add_argument("--dry-run", action="store_true", help="only report what would change")
    parser.add_argument("--check", action="store_true", help="verify the copy against VENDOR.sha256")
    args = parser.parse_args(argv)
    try:
        if args.check:
            return check()
        if args.source is None:
            parser.error("--from is needed (or --check)")
        return sync(args.source.resolve(), args.ref, args.dry_run)
    except SyncError as error:
        print(f"sync_plenio: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
