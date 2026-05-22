"""Figure inspection helpers for the visual editor.

The inspector is now registry-backed: each supported Matplotlib object type is
discovered by an adapter, while visible unclaimed artists are reported as
``unsupported`` so product users can see what exists even before editing support
is implemented.
"""

from __future__ import annotations

from typing import Any, Iterable

from matplotlib.axes import Axes
from matplotlib.container import BarContainer
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle
from matplotlib.text import Text

from .adapters.registry import inspect_figure
from .refs import ArtistRef


def iter_artist_refs(fig: Figure) -> list[ArtistRef]:
    """Return artists in a predictable, adapter-defined order."""

    return inspect_figure(fig)


def resolve_path(fig: Figure, path: Iterable[Any]) -> Any:
    """Resolve an exported artist path against a figure."""

    parts = tuple(path)
    if parts == ("figure",):
        return fig
    if len(parts) < 2 or parts[0] != "axes":
        raise ValueError(f"Unsupported artist path: {parts!r}")

    ax: Axes = fig.axes[int(parts[1])]
    if len(parts) == 2:
        return ax

    target = parts[2]
    if target == "title":
        return ax.title
    if target == "xlabel":
        return ax.xaxis.label
    if target == "ylabel":
        return ax.yaxis.label
    if target == "texts":
        return ax.texts[int(parts[3])]
    if target == "texts_group":
        return tuple(ax.texts)
    if target == "mve_shapes":
        editor_id = str(parts[3])
        for patch in ax.patches:
            if getattr(patch, "_mve_kind", None) == "shape" and getattr(patch, "_mve_id", None) == editor_id:
                return patch
        raise ValueError(f"No editor shape for path: {parts!r}")
    if target == "mve_textboxes":
        editor_id = str(parts[3])
        for text in ax.texts:
            if getattr(text, "_mve_kind", None) == "textbox" and getattr(text, "_mve_id", None) == editor_id:
                return text
        raise ValueError(f"No editor text box for path: {parts!r}")
    if target == "xaxis":
        return ax.xaxis
    if target == "yaxis":
        return ax.yaxis
    if target == "lines":
        return ax.lines[int(parts[3])]
    if target == "collections":
        return ax.collections[int(parts[3])]
    if target == "patches":
        return ax.patches[int(parts[3])]
    if target == "containers":
        return ax.containers[int(parts[3])]
    if target == "legend":
        legend = ax.get_legend()
        if legend is None:
            raise ValueError(f"No legend for path: {parts!r}")
        return legend
    if target == "spines":
        return ax.spines[str(parts[3])]

    raise ValueError(f"Unsupported artist path: {parts!r}")


def is_text_artist(artist: Any) -> bool:
    return isinstance(artist, Text)


def is_line_artist(artist: Any) -> bool:
    return isinstance(artist, Line2D)


def is_bar_container(artist: Any) -> bool:
    return isinstance(artist, BarContainer) and bool(artist.patches)


def is_bar_patch(artist: Any) -> bool:
    return isinstance(artist, Rectangle)
