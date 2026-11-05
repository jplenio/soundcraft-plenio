"""Who asks: a browser on this computer, or a request from the network - for what Plenio's routes in ComfyUI answer
only on the computer itself (the System Check's report names its folders; the Plenio Player button starts a program
on it). ComfyUI itself has no login: with ``--listen`` everyone in the network reaches its routes.

Standard library only (``plenio.comfy.routes`` passes aiohttp's request apart, so this is tested without it).
"""

from __future__ import annotations

import ipaddress
from collections.abc import Iterable, Mapping

PASSED_ON = ("forwarded", "x-forwarded-for", "x-real-ip", "x-plenio-remote")
"""Headers of a request a proxy passed on - from another computer, whatever address it comes from. The Plenio
Player's gateways (*In your network*) say ``X-Plenio-Remote``; a browser's own value never gets through them."""


def _address(text: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    # an IPv6 address may name its interface: fe80::1%eth0
    try:
        found = ipaddress.ip_address(text.split("%", 1)[0])
    except ValueError:
        return None
    if isinstance(found, ipaddress.IPv6Address) and found.ipv4_mapped is not None:
        return found.ipv4_mapped
    return found


def from_this_computer(peer: str | None, headers: Mapping[str, str], own: Iterable[str] = ()) -> bool:
    """A request of a browser on this computer: its connection comes from a loopback address - or from the address it
    was made to (``own``: a browser here that uses the computer's address in the network) - and no proxy passed it on.
    """
    address = _address(peer or "")
    if address is None:
        return False
    here = {found for found in (_address(text) for text in own) if found is not None}
    if not (address.is_loopback or address in here):
        return False
    names = {str(name).lower() for name in headers}
    return not any(name in names for name in PASSED_ON)
