"""The V3 entry point: Plenio's own extension, plus the add-in's routes."""

from __future__ import annotations

import logging

from . import routes
from .plenio_vendor.plenio.comfy import host
from .plenio_vendor.plenio.comfy.extension import PlenioExtension

log = logging.getLogger("soundcraft-plenio")


class SoundCraftPlenio(PlenioExtension):
    """Plenio unchanged - every node, route and the Song API - and the routes of ``routes.py``."""

    async def on_load(self) -> None:
        await super().on_load()
        routes.register(host.prompt_server_routes())
        watch_parent()
        log.info("SoundCraft Plenio add-in %s: routes under %s", routes.WRAPPER_VERSION, routes.BASE)


async def comfy_entrypoint() -> SoundCraftPlenio:
    return SoundCraftPlenio()


def watch_parent() -> None:
    """End this ComfyUI when the SoundCraft that started it is gone (``SCP_PARENT_PID``): a SoundCraft
    that crashed or was killed cannot stop its instance, which would keep holding the GPU."""
    import os
    import sys
    import threading
    import time

    try:
        pid = int(os.environ.get("SCP_PARENT_PID", ""))
    except ValueError:
        return

    def alive() -> bool:
        if sys.platform == "win32":
            import ctypes

            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
            if not handle:
                return False
            try:
                code = ctypes.c_ulong()
                return bool(kernel32.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259  # STILL_ACTIVE
            finally:
                kernel32.CloseHandle(handle)
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True

    def watch() -> None:
        while alive():
            time.sleep(3.0)
        log.warning("SoundCraft (process %s) is gone: this Plenio studio ends too", pid)
        os._exit(0)

    threading.Thread(target=watch, name="soundcraft-parent", daemon=True).start()
