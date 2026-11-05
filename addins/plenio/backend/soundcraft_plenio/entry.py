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
        log.info("SoundCraft Plenio add-in %s: routes under %s", routes.WRAPPER_VERSION, routes.BASE)


async def comfy_entrypoint() -> SoundCraftPlenio:
    return SoundCraftPlenio()
