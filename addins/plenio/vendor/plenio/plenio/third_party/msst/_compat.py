"""Stand-ins for the two packages the vendored BS-RoFormer imports and ComfyUI does not ship.

- ``beartype`` guards the upstream model's ``__init__`` signatures at runtime. Plenio builds the
  architecture from a pinned config, so the guards add nothing here: the stand-in aliases
  ``beartype.typing`` to :mod:`typing` and makes ``@beartype`` a no-op decorator.
- ``rotary_embedding_torch`` provides the rotary position embedding. When it is installed it is
  used (that is the package the released weights were trained with); otherwise this module installs
  a re-implementation of what ``RotaryEmbedding(dim)`` does with the defaults the upstream model
  uses: the head dimension rotated **in interleaved pairs** (``x0, x1``, ``x2, x3`` ...) by a
  geometric frequency schedule, kept as the parameter ``freqs`` - the released checkpoint carries it
  (``...rotary_embed.freqs``), so the model loads it like with the package (GitHub issue: on ComfyUI
  Desktop, which does not ship the package, an earlier stand-in had no ``freqs`` - the checkpoint
  was refused - and rotated halves of the dimension instead of pairs).

``ensure_dependencies()`` reports what it substituted; the engine puts that into the node's report.
"""

from __future__ import annotations

import importlib.util
import sys
import types
import typing
from typing import Any

__all__ = ["ensure_dependencies", "BeartypeDecorator", "rotary_embedding_class"]


def BeartypeDecorator(func: Any = None, **_kwargs: Any) -> Any:  # noqa: N802 - the name beartype uses
    """``@beartype`` without the runtime guarding (the architecture is fixed by the config)."""
    if func is None:
        return lambda inner: inner
    return func


_ROTARY_CLASS: Any = None


def rotary_embedding_class() -> Any:
    """The stand-in ``RotaryEmbedding`` (an ``nn.Module``, built when first needed: torch is imported
    only then). It reproduces ``rotary_embedding_torch`` 0.6 for ``RotaryEmbedding(dim)`` and
    ``rotate_queries_or_keys(t)``: the angles and the rotation in float32 with autocast off, the result
    in the input's dtype. The positions are counted in float32 - the package counts them in the
    input's dtype unless its cache already holds them, which only matters below float32 (the
    separator runs in float32)."""
    global _ROTARY_CLASS
    if _ROTARY_CLASS is not None:
        return _ROTARY_CLASS
    import contextlib

    import torch
    from torch import nn

    def rotate_half(x: Any) -> Any:
        pairs = x.reshape(*x.shape[:-1], -1, 2)
        first, second = pairs.unbind(dim=-1)
        return torch.stack((-second, first), dim=-1).reshape(x.shape)

    def no_autocast(device: Any) -> Any:
        try:
            return torch.autocast(device_type=device.type, enabled=False)
        except (RuntimeError, ValueError):  # a device type autocast does not know
            return contextlib.nullcontext()

    class RotaryEmbedding(nn.Module):  # type: ignore[misc]
        """``rotary_embedding_torch.RotaryEmbedding(dim)`` with its defaults (no xpos, no interpolation)."""

        def __init__(self, dim: int, theta: float = 10000, **_kwargs: Any) -> None:
            super().__init__()
            if dim % 2:
                raise ValueError("RotaryEmbedding needs an even dimension")
            freqs = 1.0 / (theta ** (torch.arange(0, dim, 2)[: dim // 2].float() / dim))
            # a parameter, as in the package: the released checkpoint carries it
            self.freqs = nn.Parameter(freqs, requires_grad=False)

        def rotate_queries_or_keys(self, t: Any, seq_dim: int = -2, offset: int = 0) -> Any:
            dtype, length = t.dtype, t.shape[seq_dim]
            positions = torch.arange(length, device=t.device, dtype=torch.float32) + offset
            with no_autocast(t.device):
                angles = torch.einsum("..., f -> ... f", positions.type(self.freqs.dtype), self.freqs)
                angles = angles.repeat_interleave(2, dim=-1)  # each angle for one pair of dimensions
                if seq_dim == -3:
                    angles = angles.unsqueeze(-2)
                width = angles.shape[-1]
                middle, right = t[..., :width], t[..., width:]
                rotated = middle * angles.cos() + rotate_half(middle) * angles.sin()
                return torch.cat((rotated, right), dim=-1).type(dtype)

    _ROTARY_CLASS = RotaryEmbedding
    return RotaryEmbedding


def _havable(name: str) -> bool:
    if name in sys.modules:
        return True
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def _install_beartype() -> None:
    package = types.ModuleType("beartype")
    package.beartype = BeartypeDecorator  # type: ignore[attr-defined]
    typing_shim = types.ModuleType("beartype.typing")
    for name in dir(typing):
        if not name.startswith("_"):
            setattr(typing_shim, name, getattr(typing, name))
    package.typing = typing_shim  # type: ignore[attr-defined]
    sys.modules["beartype"] = package
    sys.modules["beartype.typing"] = typing_shim


def _install_rotary() -> None:
    module = types.ModuleType("rotary_embedding_torch")
    module.RotaryEmbedding = rotary_embedding_class()  # type: ignore[attr-defined]
    sys.modules["rotary_embedding_torch"] = module


def ensure_dependencies() -> dict[str, str]:
    """Install the stand-ins for missing packages; returns what was substituted (empty: nothing)."""
    used: dict[str, str] = {}
    if not _havable("beartype"):
        _install_beartype()
        used["beartype"] = "vendored no-op type guard (beartype is not installed)"
    if not _havable("rotary_embedding_torch"):
        _install_rotary()
        used["rotary_embedding_torch"] = "vendored rotary embedding (the package's rotation, rebuilt)"
    return used
