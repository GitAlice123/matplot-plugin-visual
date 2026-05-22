"""Adapter registry used by the inspector and future editor/exporter code."""

from __future__ import annotations

from typing import Any

from matplotlib.figure import Figure

from .arrow import ArrowAdapter
from .axes import AxesAdapter
from .axis import AxisAdapter
from .bar import BarAdapter
from .base import ArtistAdapter
from .fill import FillAdapter
from .figure import FigureAdapter
from .legend import LegendAdapter
from .line import LineAdapter
from .patch import PatchAdapter
from .scatter import ScatterAdapter
from .shape import ShapeAdapter
from .spine import SpineAdapter
from .text import TextAdapter
from .unsupported import UnsupportedAdapter
from .wedge import WedgeAdapter


_ADAPTERS: list[ArtistAdapter] = [
    FigureAdapter(),
    AxesAdapter(),
    ShapeAdapter(),
    FillAdapter(),
    TextAdapter(),
    AxisAdapter(),
    LineAdapter(),
    ArrowAdapter(),
    ScatterAdapter(),
    BarAdapter(),
    WedgeAdapter(),
    PatchAdapter(),
    LegendAdapter(),
    SpineAdapter(),
    UnsupportedAdapter(),
]


def registered_adapters() -> list[ArtistAdapter]:
    return list(_ADAPTERS)


def get_adapter(kind: str) -> ArtistAdapter | None:
    for adapter in _ADAPTERS:
        if adapter.kind == kind or kind in getattr(adapter, "aliases", ()):
            return adapter
    return None


def inspect_figure(fig: Figure) -> list[Any]:
    refs: list[Any] = []
    claimed: set[int] = set()
    for adapter in _ADAPTERS:
        refs.extend(adapter.inspect(fig, claimed))
    return refs

