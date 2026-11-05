"""What Plenio's routes in ComfyUI answer only on the computer itself (``core.access``) - ComfyUI has no login, so
with ``--listen`` everyone in the network reaches them - and what a route says of an error (``core.errors``): a
bug's text stays in the log, it can name this computer's folders."""

from __future__ import annotations

from plenio.core.access import from_this_computer
from plenio.core.errors import (
    INTERNAL_MESSAGE,
    PlenioAccessError,
    PlenioUserError,
    PlenioWorkerError,
    public_error,
)


def test_a_browser_on_this_computer_comes_from_a_loopback_address() -> None:
    for peer in ("127.0.0.1", "127.0.0.2", "::1", "::ffff:127.0.0.1"):
        assert from_this_computer(peer, {}), peer
    for peer in ("192.168.1.20", "10.0.0.5", "fe80::1%eth0", "", None, "localhost", "not an address"):
        assert not from_this_computer(peer, {}), peer
    # a browser here that uses the computer's own address in the network
    assert from_this_computer("192.168.1.5", {}, own=["192.168.1.5"])
    assert not from_this_computer("192.168.1.20", {}, own=["192.168.1.5"])


def test_a_request_a_proxy_passed_on_comes_from_the_network() -> None:
    """The Plenio Player's gateways (In your network) and other proxies connect from this computer itself."""
    for header in ("X-Plenio-Remote", "x-forwarded-for", "Forwarded", "X-Real-IP"):
        assert not from_this_computer("127.0.0.1", {header: "1"}), header
    assert from_this_computer("127.0.0.1", {"Host": "127.0.0.1:8188", "Origin": "http://127.0.0.1:8188"})


def test_a_route_says_plenios_errors_as_written_and_a_bug_without_its_text() -> None:
    status, body = public_error(PlenioUserError("The record is gone.", hint="Choose another."))
    assert status == 400 and body["message"] == "The record is gone." and body["hint"] == "Choose another."
    status, body = public_error(PlenioAccessError("Only here."))
    assert status == 403 and body["type"] == "PlenioAccessError"
    status, body = public_error(PlenioWorkerError("The ASR stopped."))
    assert status == 500 and body["message"] == "The ASR stopped."
    secret = r"C:\Users\someone\ComfyUI\output\private\song.flac"
    status, body = public_error(FileNotFoundError(2, "No such file or directory", secret))
    assert status == 500 and body == {
        "type": "InternalError",
        "message": INTERNAL_MESSAGE,
        "hint": None,
        "details": {},
    }
    assert "someone" not in str(body)
