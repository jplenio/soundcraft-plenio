"""Start the studio - ComfyUI - from the player (owner's request 2026-10-26: the player runs on its own; ComfyUI is
started only to make songs, and nobody has to open a workflow for it).

The player finds the ComfyUI it is installed in (``ComfyUI/custom_nodes/<Plenio>``: ``main.py`` two folders up), or the
folder the admin chose, and starts it in the background: the Python of that ComfyUI (the portable build's embedded
Python, a ``.venv``) or the one the player runs on, ``main.py`` and the arguments the admin set in Settings
(``--models-directory D:/models``, ``--cuda-device 1`` …) - a fixed argument list, no shell, no window, detached; its
output in ``comfyui.log`` in the player's state folder. It listens on this computer only: ``--listen`` and
``--enable-cors-header`` are refused (*In your network* is the network's way in, with its link). A ComfyUI the player
started can be stopped from it - by hand, or when nothing was made for a while -; one started otherwise is never
touched. When the admin wishes, a song ordered while ComfyUI is not running starts it.

Standard library only.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .launch import windowless

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
FILE = "studio.json"
LOG = "comfyui.log"
DEFAULTS: dict[str, Any] = {"root": "", "args": "", "port": 8188, "auto": False, "idle_stop_min": 0}
"""``root``: ComfyUI's folder (empty: the one Plenio is installed in); ``args``: more arguments for ``main.py``;
``auto``: a song ordered while ComfyUI is not running starts it; ``idle_stop_min``: a ComfyUI the player started is
stopped after so many minutes without a song (0: never)."""
REFUSED = ("--listen", "--enable-cors-header", "--port", "--tls-keyfile", "--tls-certfile")
"""Arguments the player does not pass: ComfyUI stays on this computer, on the port the player knows."""
STARTING_S = 240.0
"""How long a start may take before the player says it did not come up (the first start loads custom nodes)."""
RESTART_AFTER_S = 120.0
"""A ComfyUI started by itself that ended (a port taken, a broken install) is started by itself again only after
so many seconds - not every few seconds while a song waits."""
ARGS_LIMIT = 1000
START_FILE = "comfyui-start.json"
"""How each ComfyUI with Plenio was last started (its ``main.py``, Python and arguments), kept in the player's state
folder when ComfyUI loads Plenio: the player starts it the same way - with the models folder and the options its
owner gives it - when Settings has no arguments of its own."""
NOT_REPEATED = {
    "--listen": "?",
    "--port": 1,
    "--enable-cors-header": "?",
    "--tls-keyfile": 1,
    "--tls-certfile": 1,
}
"""Arguments of the remembered start the player leaves out (and how many values follow): it keeps ComfyUI on this
computer, on its own port. ``?``: a value only when the next word is not an option."""


class StudioLaunchError(ValueError):
    """A start or a setting refused, with the reason (and the HTTP status to answer)."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


COMFYUI_FILES = ("main.py", "folder_paths.py", "execution.py")
"""What a ComfyUI folder holds besides its ``comfy`` package: the player starts no other ``main.py``."""
PYTHON_NAME = re.compile(r"pythonw?(\d+(\.\d+)*)?(\.exe)?", re.IGNORECASE)
"""A Python interpreter's file name (``python.exe``, ``python3.12``): the only program the player starts."""


def is_comfyui(folder: Path) -> bool:
    """``folder`` is ComfyUI's own: its ``main.py`` beside ``folder_paths.py``, ``execution.py`` and ``comfy``."""
    return all((folder / name).is_file() for name in COMFYUI_FILES) and (folder / "comfy").is_dir()


def installed_root() -> Path | None:
    """The ComfyUI Plenio is installed in: ``<ComfyUI>/custom_nodes/<Plenio>``."""
    candidate = PACKAGE_ROOT.parent.parent
    if PACKAGE_ROOT.parent.name == "custom_nodes" and is_comfyui(candidate):
        return candidate
    return None


def python_of(root: Path) -> tuple[Path, bool]:
    """The Python that runs ``root``'s ComfyUI, and whether it is the portable build's embedded one: the portable
    build's ``python_embeded`` beside the ComfyUI folder, a ``.venv`` or ``venv`` in it - else the player's own."""
    windows = os.name == "nt"
    embedded = root.parent / "python_embeded" / "python.exe"
    if windows and embedded.is_file():
        return embedded, True
    for venv in (".venv", "venv"):
        found = root / venv / ("Scripts/python.exe" if windows else "bin/python")
        if found.is_file():
            return found, False
    return Path(sys.executable), False


def parse_args(text: str) -> list[str]:
    """The admin's extra arguments as a list (quotes keep a path with spaces together); refused: what would open
    ComfyUI to the network or move it to another port, and anything that is not an option or its value."""
    if len(text) > ARGS_LIMIT:
        raise StudioLaunchError(f"At most {ARGS_LIMIT} characters of arguments.")
    try:
        parts = shlex.split(text, posix=os.name != "nt")
    except ValueError as error:
        raise StudioLaunchError(f"The arguments: {error}") from error
    if os.name == "nt":
        parts = [p[1:-1] if len(p) > 1 and p[0] == p[-1] == '"' else p for p in parts]
    for part in parts:
        name = part.split("=", 1)[0].lower()
        if name in REFUSED:
            raise StudioLaunchError(
                f"{name} is not passed: ComfyUI stays on this computer, on the port set here "
                "(the network comes in by Settings > In your network)."
            )
        if any(ch in part for ch in "\r\n\0"):
            raise StudioLaunchError("An argument with a line break.")
    if parts and not parts[0].startswith("-"):
        raise StudioLaunchError("The arguments start with an option, such as --models-directory.")
    return parts


def repeatable(argv: list[str]) -> list[str]:
    """A start's arguments without those the player sets itself or refuses (the address, the port, TLS, CORS, the
    portable build's flag - added again when its Python is the embedded one)."""
    out: list[str] = []
    skip = 0
    for index, part in enumerate(argv):
        if skip:
            skip -= 1
            continue
        name = part.split("=", 1)[0].lower()
        if name == "--windows-standalone-build":
            continue
        values = NOT_REPEATED.get(name)
        if values is None:
            if any(ch in part for ch in "\r\n\0"):
                return []
            out.append(part)
            continue
        if "=" in part:
            continue
        following = argv[index + 1] if index + 1 < len(argv) else ""
        skip = 1 if values == 1 or (following and not following.startswith("-")) else 0
    return out


def remember_start(
    directory: Path, argv: list[str], python: str, clock: Callable[[], float] = time.time
) -> None:
    """Keep how this ComfyUI was started (called when ComfyUI loads Plenio): ``argv`` begins with its ``main.py``."""
    if not argv or Path(argv[0]).name != "main.py":
        return
    main = str(Path(argv[0]).resolve())
    file = directory / START_FILE
    try:
        known = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        known = {}
    if not isinstance(known, dict):
        known = {}
    known[main] = {"python": python, "args": repeatable(list(argv[1:])), "at": clock()}
    directory.mkdir(parents=True, exist_ok=True)
    temp = file.with_suffix(".tmp")
    temp.write_text(json.dumps(known, indent=1), encoding="utf-8")
    temp.replace(file)


def remembered_start(directory: Path, root: Path | None = None) -> tuple[Path, dict[str, Any]] | None:
    """The last start of the ComfyUI in ``root`` (``None``: of any whose ``main.py`` still exists, the newest):
    its ``main.py`` and ``{python, args, at}``."""
    try:
        known = json.loads((directory / START_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(known, dict):
        return None
    found: list[tuple[float, Path, dict[str, Any]]] = []
    for main, entry in known.items():
        path = Path(main)
        if not isinstance(entry, dict) or not path.is_file():
            continue
        if root is not None and path.resolve() != (root / "main.py").resolve():
            continue
        args = entry.get("args")
        if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
            continue
        found.append((float(entry.get("at") or 0), path, entry))
    if not found:
        return None
    _at, path, entry = max(found, key=lambda item: item[0])
    return path, entry


class StudioLauncher:
    """The ComfyUI the player starts: its settings (``studio.json`` in the player's state folder), the process it
    started, whether it came up."""

    def __init__(
        self,
        directory: Path,
        reachable: Callable[[str], bool] | None = None,
        clock: Callable[[], float] = time.time,
    ):
        self.directory = directory
        self.path = directory / FILE
        self.lock = threading.Lock()
        self.clock = clock
        self.reachable = reachable or (lambda url: False)
        self.elsewhere: Callable[[], str | None] = lambda: None
        """A ComfyUI on this computer the player did not start - the one that started the player, ComfyUI Desktop
        on 8000 ...: its address, or ``None``. While one answers, the player starts none of its own."""
        self.settings = self._load()
        self.process: subprocess.Popen[bytes] | None = None
        self.started_at = 0.0
        self.last_busy = clock()
        self.error = ""

    # --- settings ---------------------------------------------------------------------------------------------
    def _load(self) -> dict[str, Any]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        out = dict(DEFAULTS)
        if isinstance(data, dict):
            out.update({k: v for k, v in data.items() if k in DEFAULTS})
        return out

    def _save(self) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(self.settings, indent=1), encoding="utf-8")
        temp.replace(self.path)

    def configure(self, changes: dict[str, Any]) -> dict[str, Any]:
        """The admin's settings, checked: ComfyUI's own folder (empty: the one Plenio is in), the arguments, a port,
        starting by itself, stopping after idle minutes."""
        with self.lock:
            settings = dict(self.settings)
            if "root" in changes:
                root = str(changes["root"] or "").strip()
                if root and not is_comfyui(Path(root)):
                    raise StudioLaunchError(
                        "That is no ComfyUI folder (its main.py, folder_paths.py, execution.py and comfy) - choose "
                        "ComfyUI's own folder."
                    )
                settings["root"] = root
            if "args" in changes:
                text = str(changes["args"] or "").strip()
                parse_args(text)
                settings["args"] = text
            if "port" in changes:
                try:
                    port = int(changes["port"])
                except (TypeError, ValueError) as error:
                    raise StudioLaunchError("The port is a number from 1024 to 65535.") from error
                if not 1024 <= port <= 65535:
                    raise StudioLaunchError("The port is a number from 1024 to 65535.")
                settings["port"] = port
            if "auto" in changes:
                settings["auto"] = bool(changes["auto"])
            if "idle_stop_min" in changes:
                try:
                    minutes = int(changes["idle_stop_min"])
                except (TypeError, ValueError) as error:
                    raise StudioLaunchError("Minutes: 0 (never) to 600.") from error
                settings["idle_stop_min"] = max(0, min(600, minutes))
            self.settings = settings
            self._save()
        return self.status()

    # --- where and how ----------------------------------------------------------------------------------------
    def root(self) -> Path | None:
        """The folder chosen in Settings, else the ComfyUI Plenio is installed in, else the one last started with
        Plenio (ComfyUI Desktop keeps Plenio outside its own folder)."""
        chosen = str(self.settings.get("root") or "").strip()
        if chosen:
            path = Path(chosen)
            return path if is_comfyui(path) else None
        installed = installed_root()
        if installed is not None:
            return installed
        last = remembered_start(self.directory)
        return last[0].parent if last and is_comfyui(last[0].parent) else None

    def arguments(self, root: Path) -> tuple[list[str], str, dict[str, Any] | None]:
        """The arguments for ``main.py``: the ones set in Settings, else those of the last start of this ComfyUI
        (its models folder, its options), else none - and where they come from (``settings``, ``last start`` or
        ``""``), with that last start."""
        own = str(self.settings.get("args") or "").strip()
        if own:
            return parse_args(own), "settings", None
        last = remembered_start(self.directory, root)
        if last is None:
            return [], "", None
        # filtered again: the file is the player's, but a hand-edited --listen must not open ComfyUI to the network
        return repeatable(list(last[1]["args"])), "last start", last[1]

    def url(self) -> str:
        return f"http://127.0.0.1:{int(self.settings.get('port') or 8188)}"

    def answering(self) -> str | None:
        """The ComfyUI that answers on this computer: on the player's port, or another one found."""
        if self.reachable(self.url()):
            return self.url()
        other = self.elsewhere()
        return other.rstrip("/") if other else None

    def command(self) -> tuple[list[str], Path]:
        """The argument list that starts ComfyUI, and the folder it runs in."""
        root = self.root()
        if root is None:
            raise StudioLaunchError(
                "The player does not know yet how to start ComfyUI: Plenio is not inside a ComfyUI folder here, and "
                "ComfyUI has not run with Plenio since. Start ComfyUI once the way you usually do - from then on the "
                "player starts it the same way - or choose its folder under How it starts ComfyUI.",
                409,
            )
        extra, _source, last = self.arguments(root)
        python, embedded = python_of(root)
        last_python = Path(str((last or {}).get("python") or ""))
        if last_python.is_file() and PYTHON_NAME.fullmatch(last_python.name):
            # the Python it last ran on (ComfyUI Desktop's own environment, a conda one ...) - a Python, whatever
            # the start file says
            python = last_python
            embedded = python.parent.name == "python_embeded"
        command = [str(python)]
        if embedded:
            command.append("-s")
        command += [str(root / "main.py"), "--port", str(int(self.settings.get("port") or 8188))]
        if embedded:
            command.append("--windows-standalone-build")
        command += extra
        return command, root

    # --- start, stop ------------------------------------------------------------------------------------------
    def started(self) -> bool:
        """The player's own ComfyUI runs (it started it, and it has not ended)."""
        return self.process is not None and self.process.poll() is None

    def start(self) -> dict[str, Any]:
        """Start ComfyUI in the background - unless one answers already, or the player's own is on its way up."""
        with self.lock:
            if self.answering():
                return self.status()
            if self.started():
                return self.status()
            command, root = self.command()
            self.directory.mkdir(parents=True, exist_ok=True)
            flags: dict[str, Any] = {}
            if sys.platform == "win32":
                flags["creationflags"] = windowless()
            else:
                flags["start_new_session"] = True
            log = (self.directory / LOG).open("ab")
            try:
                log.write(
                    f"\n--- started by the Plenio Player {time.ctime()}: {' '.join(command)}\n".encode()
                )
                log.flush()
                self.process = subprocess.Popen(  # noqa: S603 - a fixed argument list, no shell
                    command,
                    cwd=str(root),
                    stdin=subprocess.DEVNULL,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                    **flags,
                )
            except OSError as error:
                self.error = f"ComfyUI did not start: {error}"
                raise StudioLaunchError(self.error, 500) from error
            finally:
                log.close()
            self.started_at = self.clock()
            self.last_busy = self.clock()
            self.error = ""
        return self.status()

    def stop(self) -> dict[str, Any]:
        """Stop the ComfyUI the player started (one started otherwise is not the player's to stop)."""
        with self.lock:
            process = self.process
            if process is None or process.poll() is not None:
                raise StudioLaunchError(
                    "The player did not start the ComfyUI that runs - stop it where it was started.", 409
                )
            if sys.platform == "win32":
                # the whole tree: ComfyUI may have started workers of its own
                subprocess.run(  # noqa: S603, S607 - a fixed argument list
                    ["taskkill", "/T", "/F", "/PID", str(process.pid)], capture_output=True, check=False
                )
            else:
                process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
            self.process = None
        return self.status()

    def busy(self) -> None:
        """A song is being made or waits: the idle time starts again."""
        self.last_busy = self.clock()

    def tick(self, waiting: bool) -> None:
        """The party songs' worker asks now and then: start ComfyUI for a song that waits (when the admin wants
        it), stop the player's own after the idle minutes."""
        if waiting:
            self.busy()
            if (
                self.settings.get("auto")
                and not self.started()
                and self.clock() - self.started_at > RESTART_AFTER_S
                and not self.answering()
            ):
                try:
                    self.start()
                except StudioLaunchError as error:
                    self.error = str(error)
            return
        minutes = int(self.settings.get("idle_stop_min") or 0)
        if minutes and self.started() and self.clock() - self.last_busy > minutes * 60:
            try:
                self.stop()
            except StudioLaunchError:
                pass

    def log_tail(self, lines: int = 14) -> list[str]:
        try:
            with (self.directory / LOG).open("rb") as handle:
                handle.seek(0, os.SEEK_END)
                size = handle.tell()
                handle.seek(max(0, size - 16384))
                text = handle.read().decode("utf-8", errors="replace")
        except OSError:
            return []
        return [line for line in text.splitlines() if line.strip()][-lines:]

    def status(self, *, admin: bool = True) -> dict[str, Any]:
        """What the page shows: whether ComfyUI runs, whether the player started it (and when), whether it can,
        and for the admin the folder, the Python, the arguments and the end of the log."""
        found = self.answering()
        running = found is not None
        own = self.started()
        starting = own and not running and self.clock() - self.started_at < STARTING_S
        try:
            command, root = self.command()
            can, why = True, ""
        except StudioLaunchError as error:
            command, root, can, why = [], None, False, str(error)
        out: dict[str, Any] = {
            "running": running,
            "own": own,
            "starting": starting,
            "since": self.started_at if own else None,
            "can_start": can,
            "why": why,
            "url": found or self.url(),
            "auto": bool(self.settings.get("auto")),
            "idle_stop_min": int(self.settings.get("idle_stop_min") or 0),
            "error": self.error,
        }
        if own and not running and not starting and not self.error:
            out["error"] = "ComfyUI did not answer in time - its log says why."
        if admin:
            source, used, last_at = "", "", None
            if root is not None:
                try:
                    extra, source, last = self.arguments(root)
                    used = " ".join(extra)
                    last_at = (float(last.get("at") or 0) or None) if last else None
                except StudioLaunchError:
                    source = ""
            out.update(
                args_from=source,
                args_used=used,
                last_start_at=last_at,
                root=str(root or self.settings.get("root") or ""),
                chosen_root=str(self.settings.get("root") or ""),
                installed_root=str(installed_root() or ""),
                python=command[0] if command else "",
                args=str(self.settings.get("args") or ""),
                port=int(self.settings.get("port") or 8188),
                command=" ".join(command),
                log=self.log_tail(),
            )
        return out
