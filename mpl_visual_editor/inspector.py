"""Figure inspection helpers for the visual editor.

The first prototype intentionally supports common Matplotlib artists only:
axes, lines, text labels, legends, and spines. Each editable target is addressed
by a small, stable path that can be replayed by the exporter.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.text import Text


@dataclass(frozen=True)
class ArtistRef:
    """An editable Matplotlib object discovered in a figure."""

    label: str
    kind: str
    path: tuple[Any, ...]
    artist: Any


def iter_artist_refs(fig: Figure) -> list[ArtistRef]:
    """Return editable artists in a predictable order."""

    refs: list[ArtistRef] = []
    for ax_index, ax in enumerate(fig.axes):
        refs.append(ArtistRef(f"Axes {ax_index}", "axes", ("axes", ax_index), ax))

        title = ax.title
        refs.append(
            ArtistRef(
                f"Axes {ax_index} / Title",
                "text",
                ("axes", ax_index, "title"),
                title,
            )
        )
        refs.append(
            ArtistRef(
                f"Axes {ax_index} / X label",
                "text",
                ("axes", ax_index, "xlabel"),
                ax.xaxis.label,
            )
        )
        refs.append(
            ArtistRef(
                f"Axes {ax_index} / Y label",
                "text",
                ("axes", ax_index, "ylabel"),
                ax.yaxis.label,
            )
        )

        for line_index, line in enumerate(ax.lines):
            refs.append(
                ArtistRef(
                    f"Axes {ax_index} / Line {line_index}: {line.get_label()}",
                    "line",
                    ("axes", ax_index, "lines", line_index),
                    line,
                )
            )

        legend = ax.get_legend()
        if legend is not None:
            refs.append(
                ArtistRef(
                    f"Axes {ax_index} / Legend",
                    "legend",
                    ("axes", ax_index, "legend"),
                    legend,
                )
            )

        for spine_name, spine in ax.spines.items():
            refs.append(
                ArtistRef(
                    f"Axes {ax_index} / Spine {spine_name}",
                    "spine",
                    ("axes", ax_index, "spines", spine_name),
                    spine,
                )
            )

    return refs


def resolve_path(fig: Figure, path: Iterable[Any]) -> Any:
    """Resolve an exported artist path against a figure."""

    parts = tuple(path)
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
    if target == "lines":
        return ax.lines[int(parts[3])]
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
