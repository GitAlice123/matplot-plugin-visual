"""Adapter for existing FancyArrowPatch annotations."""

from __future__ import annotations

from typing import Any

from matplotlib.figure import Figure
from matplotlib.patches import FancyArrowPatch

from ..refs import ArtistRef
from .base import BaseAdapter


class ArrowAdapter(BaseAdapter):
    kind = "arrow"

    def inspect(self, fig: Figure, claimed: set[int]) -> list[ArtistRef]:
        refs: list[ArtistRef] = []
        for ax_index, ax in enumerate(fig.axes):
            for patch_index, patch in enumerate(ax.patches):
                if getattr(patch, "_mve_kind", None) == "shape" or not isinstance(patch, FancyArrowPatch):
                    continue
                self._claim(patch, claimed)
                refs.append(
                    ArtistRef(
                        f"Axes {ax_index} / Arrow {patch_index}",
                        self.kind,
                        ("axes", ax_index, "patches", patch_index),
                        patch,
                    )
                )
        return refs

    def delete(self, ref: ArtistRef) -> None:
        ref.artist.remove()

    def highlight(self, ref: ArtistRef, editor: Any) -> dict[str, Any]:
        return {"kind": ref.kind, "artist": self._highlight_artist(ref.artist, linewidth=4, boost_zorder=True)}

    def build_form(self, ref: ArtistRef, editor: Any) -> bool:
        props = arrow_props(ref.artist)
        artist = ref.artist
        editor._add_bool("Visible", props["visible"], artist.set_visible)
        editor._add_color("Color", props["edgecolor"], lambda v: _set_arrow_style(artist, edgecolor=v))
        editor._add_float("Line width", props["linewidth"], lambda v: _set_arrow_style(artist, linewidth=v), 0.0, 50.0, 0.25)
        editor._add_choice("Line style", props["linestyle"], ["-", "--", "-.", ":", "None"], lambda v: _set_arrow_style(artist, linestyle=v))
        editor._add_float("Head size", props["mutation_scale"], lambda v: _set_arrow_style(artist, mutation_scale=v), 1.0, 200.0, 1.0)
        editor._add_float("Alpha", props["alpha"] if props["alpha"] is not None else 1.0, lambda v: _set_arrow_style(artist, alpha=v), 0.0, 1.0, 0.05)
        editor._add_position_save_button("Save position")
        return True


def arrow_props(artist: Any) -> dict[str, Any]:
    pos_a, pos_b = _arrow_positions(artist)
    return {
        "visible": bool(artist.get_visible()),
        "posA": pos_a,
        "posB": pos_b,
        "edgecolor": _color(artist.get_edgecolor()),
        "linewidth": float(artist.get_linewidth()),
        "linestyle": _linestyle(artist),
        "mutation_scale": float(artist.get_mutation_scale()) if hasattr(artist, "get_mutation_scale") else 10.0,
        "alpha": artist.get_alpha(),
    }


def apply_arrow_props(artist: Any, props: dict[str, Any]) -> None:
    artist.set_visible(bool(props.get("visible", True)))
    if "posA" in props and "posB" in props and hasattr(artist, "set_positions"):
        artist.set_positions(tuple(props["posA"]), tuple(props["posB"]))
        artist._mve_posA = tuple(props["posA"])
        artist._mve_posB = tuple(props["posB"])
    _set_arrow_style(
        artist,
        edgecolor=props.get("edgecolor"),
        linewidth=props.get("linewidth"),
        linestyle=props.get("linestyle"),
        mutation_scale=props.get("mutation_scale"),
        alpha=props.get("alpha"),
    )


def _set_arrow_style(
    artist: Any,
    *,
    edgecolor: Any | None = None,
    linewidth: Any | None = None,
    linestyle: Any | None = None,
    mutation_scale: Any | None = None,
    alpha: Any | None = None,
) -> None:
    if edgecolor is not None:
        artist.set_color(edgecolor)
    if linewidth is not None:
        artist.set_linewidth(float(linewidth))
    if linestyle is not None:
        artist.set_linestyle(linestyle)
    if mutation_scale is not None and hasattr(artist, "set_mutation_scale"):
        artist.set_mutation_scale(float(mutation_scale))
    if alpha is not None:
        artist.set_alpha(alpha)


def _arrow_positions(artist: Any) -> tuple[tuple[float, float], tuple[float, float]]:
    if hasattr(artist, "_mve_posA") and hasattr(artist, "_mve_posB"):
        return tuple(artist._mve_posA), tuple(artist._mve_posB)
    pos = getattr(artist, "_posA_posB", None)
    if pos is not None:
        try:
            return (float(pos[0][0]), float(pos[0][1])), (float(pos[1][0]), float(pos[1][1]))
        except (TypeError, ValueError, IndexError):
            pass
    path = artist.get_path()
    vertices = path.vertices
    return (
        (float(vertices[0][0]), float(vertices[0][1])),
        (float(vertices[-1][0]), float(vertices[-1][1])),
    )


def _linestyle(artist: Any) -> str:
    value = artist.get_linestyle() if hasattr(artist, "get_linestyle") else "-"
    aliases = {"solid": "-", "dashed": "--", "dashdot": "-.", "dotted": ":"}
    return aliases.get(str(value), str(value))


def _color(value: Any) -> str:
    from matplotlib.colors import to_hex

    try:
        return to_hex(value, keep_alpha=False)
    except (TypeError, ValueError):
        return str(value)
