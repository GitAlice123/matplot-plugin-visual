"""Stable references to Matplotlib artists discovered by the editor."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ArtistRef:
    """A Matplotlib object addressable by the visual editor."""

    label: str
    kind: str
    path: tuple[Any, ...]
    artist: Any

