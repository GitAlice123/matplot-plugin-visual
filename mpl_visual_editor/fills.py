"""Helpers for editable fill regions."""

from __future__ import annotations

from typing import Any

from matplotlib.collections import PolyCollection
from matplotlib.colors import to_hex


def fill_props(artist: Any) -> dict[str, Any]:
    paths = artist.get_paths() if hasattr(artist, "get_paths") else []
    vertices = paths[0].vertices.tolist() if paths else []
    x, y, width, height = _bbox(vertices)
    return {
        "id": getattr(artist, "_mve_id", "fill"),
        "visible": bool(artist.get_visible()),
        "x": float(getattr(artist, "_mve_x", x)),
        "y": float(getattr(artist, "_mve_y", y)),
        "width": float(getattr(artist, "_mve_width", width)),
        "height": float(getattr(artist, "_mve_height", height)),
        "vertices": vertices,
        "facecolor": _first_color(artist.get_facecolors()),
        "edgecolor": _first_color(artist.get_edgecolors(), default="none"),
        "linewidth": _first_float(artist.get_linewidths(), 0.0),
        "alpha": artist.get_alpha(),
        "editable_geometry": bool(getattr(artist, "_mve_editable_geometry", False)),
    }


def apply_fill_props(ax: Any, props: dict[str, Any], artist: Any | None = None) -> PolyCollection:
    props = dict(props)
    props.setdefault("id", "fill")
    if artist is None:
        artist = _find_fill(ax, str(props["id"]))
    if props.get("editable_geometry"):
        vertices = _rect_vertices(
            float(props.get("x", 0.0)),
            float(props.get("y", 0.0)),
            float(props.get("width", 1.0)),
            float(props.get("height", 1.0)),
        )
        props["vertices"] = vertices
    else:
        vertices = props.get("vertices") or []
    if artist is None:
        artist = PolyCollection([vertices], closed=True, clip_on=False, zorder=3)
        ax.add_collection(artist)
    artist.set_verts([vertices])
    artist.set_facecolor(props.get("facecolor", "#f28e2b"))
    artist.set_edgecolor(props.get("edgecolor", "none"))
    artist.set_linewidth(float(props.get("linewidth", 0.0)))
    artist.set_alpha(props.get("alpha", 0.18))
    artist.set_visible(bool(props.get("visible", True)))
    _tag_fill(artist, props)
    return artist


def _find_fill(ax: Any, editor_id: str) -> Any | None:
    for collection in ax.collections:
        if getattr(collection, "_mve_kind", None) == "fill" and getattr(collection, "_mve_id", None) == editor_id:
            return collection
    return None


def _tag_fill(artist: Any, props: dict[str, Any]) -> None:
    artist._mve_kind = "fill"
    artist._mve_id = str(props.get("id", "fill"))
    artist._mve_x = float(props.get("x", 0.0))
    artist._mve_y = float(props.get("y", 0.0))
    artist._mve_width = float(props.get("width", 1.0))
    artist._mve_height = float(props.get("height", 1.0))
    artist._mve_editable_geometry = bool(props.get("editable_geometry", False))


def _bbox(vertices: Any) -> tuple[float, float, float, float]:
    if not vertices:
        return 0.0, 0.0, 1.0, 1.0
    xs = [float(v[0]) for v in vertices]
    ys = [float(v[1]) for v in vertices]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    return (x0 + x1) / 2.0, (y0 + y1) / 2.0, max(x1 - x0, 1e-12), max(y1 - y0, 1e-12)


def _first_color(values: Any, default: str = "#000000") -> str:
    if values is None or len(values) == 0:
        return default
    try:
        value = values[0]
        if len(value) >= 4 and float(value[3]) == 0.0:
            return "none"
        return to_hex(value, keep_alpha=False)
    except (TypeError, ValueError):
        return str(values[0])


def _first_float(values: Any, default: float) -> float:
    if values is None or len(values) == 0:
        return float(default)
    return float(values[0])


