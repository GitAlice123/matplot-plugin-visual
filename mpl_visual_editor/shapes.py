"""Helpers for editor-created shapes and text boxes."""

from __future__ import annotations

import math
import uuid
from typing import Any

from matplotlib.colors import to_hex
from matplotlib.patches import Ellipse, FancyArrowPatch, FancyBboxPatch, Polygon, Rectangle

LINE_SHAPE_TYPES = {"line", "arrow", "double_arrow"}
ARROW_SHAPE_TYPES = {"arrow", "double_arrow"}


def add_shape(ax: Any, shape_type: str, center: tuple[float, float] | None = None) -> Any:
    x, y, width, height = _default_geometry(ax)
    if center is not None:
        x, y = float(center[0]), float(center[1])
    props = {
        "id": _new_id("shape"),
        "type": shape_type,
        "visible": True,
        "x": x,
        "y": y,
        "width": width,
        "height": height,
        "angle": 0.0,
        "facecolor": "#ffffff" if shape_type not in LINE_SHAPE_TYPES else None,
        "edgecolor": "#c0392b" if shape_type in ARROW_SHAPE_TYPES else "#222222",
        "linewidth": 1.0,
        "linestyle": "-",
        "alpha": 1.0,
        "mutation_scale": 10.0,
    }
    return apply_shape_props(ax, props)


def add_textbox(ax: Any, center: tuple[float, float] | None = None) -> Any:
    x, y, _width, _height = _default_geometry(ax)
    if center is not None:
        x, y = float(center[0]), float(center[1])
    props = {
        "id": _new_id("textbox"),
        "visible": True,
        "text": "Text box",
        "x": x,
        "y": y,
        "rotation": 0.0,
        "color": "#000000",
        "fontsize": 10.0,
        "fontweight": "normal",
        "fontstyle": "normal",
        "facecolor": "none",
        "edgecolor": "none",
        "box_alpha": 0.0,
        "pad": 0.3,
    }
    return apply_textbox_props(ax, props)


def find_editor_artist(ax: Any, kind: str, editor_id: str) -> Any | None:
    artists = ax.texts if kind == "textbox" else ax.patches
    for artist in artists:
        if getattr(artist, "_mve_kind", None) == kind and getattr(artist, "_mve_id", None) == editor_id:
            return artist
    return None


def shape_props(artist: Any) -> dict[str, Any]:
    return {
        "id": getattr(artist, "_mve_id", _new_id("shape")),
        "type": getattr(artist, "_mve_shape_type", "rectangle"),
        "visible": bool(artist.get_visible()),
        "x": float(getattr(artist, "_mve_x", 0.0)),
        "y": float(getattr(artist, "_mve_y", 0.0)),
        "width": float(getattr(artist, "_mve_width", 1.0)),
        "height": float(getattr(artist, "_mve_height", 1.0)),
        "angle": float(getattr(artist, "_mve_angle", 0.0)),
        "facecolor": _color(artist.get_facecolor()) if hasattr(artist, "get_facecolor") else None,
        "edgecolor": _edgecolor(artist),
        "linewidth": float(artist.get_linewidth()) if hasattr(artist, "get_linewidth") else 1.0,
        "linestyle": _linestyle(artist),
        "alpha": artist.get_alpha(),
        "mutation_scale": float(getattr(artist, "_mve_mutation_scale", 10.0)),
    }


def textbox_props(artist: Any) -> dict[str, Any]:
    bbox_patch = artist.get_bbox_patch()
    facecolor = _patch_color(bbox_patch, "face") if bbox_patch is not None else "none"
    edgecolor = _patch_color(bbox_patch, "edge") if bbox_patch is not None else "none"
    box_alpha = bbox_patch.get_alpha() if bbox_patch is not None else 0.85
    return {
        "id": getattr(artist, "_mve_id", _new_id("textbox")),
        "visible": bool(artist.get_visible()),
        "text": artist.get_text(),
        "x": float(artist.get_position()[0]),
        "y": float(artist.get_position()[1]),
        "rotation": float(artist.get_rotation()),
        "color": _color(artist.get_color()) or "#000000",
        "fontsize": float(artist.get_fontsize()),
        "fontweight": artist.get_fontweight(),
        "fontstyle": artist.get_fontstyle(),
        "facecolor": facecolor,
        "edgecolor": edgecolor,
        "box_alpha": box_alpha,
        "pad": float(getattr(artist, "_mve_pad", 0.3)),
    }


def apply_shape_props(ax: Any, props: dict[str, Any], artist: Any | None = None) -> Any:
    props = dict(props)
    props.setdefault("id", _new_id("shape"))
    props.setdefault("type", "rectangle")
    if artist is None:
        artist = find_editor_artist(ax, "shape", str(props["id"]))
    if artist is not None and getattr(artist, "_mve_shape_type", None) != props["type"]:
        artist.remove()
        artist = None
    if artist is None:
        artist = _create_shape(ax, props)
    _update_shape_artist(artist, props)
    return artist


def apply_textbox_props(ax: Any, props: dict[str, Any], artist: Any | None = None) -> Any:
    props = dict(props)
    props.setdefault("id", _new_id("textbox"))
    if artist is None:
        artist = find_editor_artist(ax, "textbox", str(props["id"]))
    if artist is None:
        artist = ax.text(
            float(props.get("x", 0.5)),
            float(props.get("y", 0.5)),
            str(props.get("text", "Text box")),
            ha="center",
            va="center",
            clip_on=False,
            zorder=1000,
        )
    artist.set_text(str(props.get("text", "")))
    artist.set_position((float(props.get("x", 0.0)), float(props.get("y", 0.0))))
    artist.set_rotation(float(props.get("rotation", 0.0)))
    artist.set_color(props.get("color", "#000000"))
    artist.set_fontsize(float(props.get("fontsize", 10.0)))
    artist.set_fontweight(props.get("fontweight", "normal"))
    artist.set_fontstyle(props.get("fontstyle", "normal"))
    artist.set_visible(bool(props.get("visible", True)))
    artist.set_bbox(
        {
            "boxstyle": f"round,pad={float(props.get('pad', 0.3))}",
            "facecolor": props.get("facecolor", "#ffffff"),
            "edgecolor": props.get("edgecolor", "#222222"),
            "alpha": props.get("box_alpha", 0.85),
            "linewidth": 1.0,
        }
    )
    _tag_artist(artist, "textbox", props)
    artist._mve_pad = float(props.get("pad", 0.3))
    return artist


def move_artist(artist: Any, dx: float, dy: float) -> None:
    if getattr(artist, "_mve_kind", None) == "textbox":
        props = textbox_props(artist)
        props["x"] += dx
        props["y"] += dy
        apply_textbox_props(artist.axes, props, artist)
        return
    props = shape_props(artist)
    props["x"] += dx
    props["y"] += dy
    apply_shape_props(artist.axes, props, artist)


def _create_shape(ax: Any, props: dict[str, Any]) -> Any:
    shape_type = props.get("type", "rectangle")
    if shape_type == "ellipse":
        artist = Ellipse((0.0, 0.0), 1.0, 1.0, clip_on=False, zorder=1000)
    elif shape_type in LINE_SHAPE_TYPES:
        arrowstyle = {"arrow": "->", "double_arrow": "<->"}.get(shape_type, "-")
        artist = FancyArrowPatch((0.0, 0.0), (1.0, 0.0), arrowstyle=arrowstyle, clip_on=False, zorder=1000)
    elif shape_type in {"triangle", "diamond"}:
        artist = Polygon([[0.0, 0.0]], closed=True, clip_on=False, zorder=1000)
    elif shape_type == "round_rectangle":
        artist = FancyBboxPatch(
            (0.0, 0.0),
            1.0,
            1.0,
            boxstyle="round,pad=0.02",
            clip_on=False,
            zorder=1000,
        )
    else:
        try:
            artist = Rectangle((0.0, 0.0), 1.0, 1.0, rotation_point="center", clip_on=False, zorder=1000)
        except TypeError:
            artist = Rectangle((0.0, 0.0), 1.0, 1.0, clip_on=False, zorder=1000)
    ax.add_patch(artist)
    return artist


def _update_shape_artist(artist: Any, props: dict[str, Any]) -> None:
    shape_type = props.get("type", "rectangle")
    x = float(props.get("x", 0.0))
    y = float(props.get("y", 0.0))
    width = max(float(props.get("width", 1.0)), 1e-12)
    height = max(float(props.get("height", 1.0)), 1e-12)
    angle = float(props.get("angle", 0.0))
    edgecolor = props.get("edgecolor", "#222222")
    facecolor = props.get("facecolor")
    linewidth = float(props.get("linewidth", 1.0))
    linestyle = props.get("linestyle", "-")
    alpha = props.get("alpha", 1.0)

    if shape_type in LINE_SHAPE_TYPES:
        radians = math.radians(angle)
        dx = math.cos(radians) * width / 2.0
        dy = math.sin(radians) * width / 2.0
        artist.set_positions((x - dx, y - dy), (x + dx, y + dy))
        artist.set_mutation_scale(float(props.get("mutation_scale", 10.0)))
        artist.set_color(edgecolor)
        artist._mve_mutation_scale = float(props.get("mutation_scale", 10.0))
    elif shape_type in {"triangle", "diamond"}:
        artist.set_xy(_polygon_vertices(shape_type, x, y, width, height, angle))
        artist.set_facecolor(facecolor or "none")
        artist.set_edgecolor(edgecolor)
    elif shape_type == "ellipse":
        artist.center = (x, y)
        artist.width = width
        artist.height = height
        artist.angle = angle
        artist.set_facecolor(facecolor or "none")
        artist.set_edgecolor(edgecolor)
    elif shape_type == "round_rectangle":
        artist.set_bounds(x - width / 2.0, y - height / 2.0, width, height)
        artist.set_facecolor(facecolor or "none")
        artist.set_edgecolor(edgecolor)
    else:
        artist.set_xy((x - width / 2.0, y - height / 2.0))
        artist.set_width(width)
        artist.set_height(height)
        if hasattr(artist, "set_angle"):
            artist.set_angle(angle)
        else:
            artist.angle = angle
        artist.set_facecolor(facecolor or "none")
        artist.set_edgecolor(edgecolor)

    artist.set_linewidth(linewidth)
    if hasattr(artist, "set_linestyle"):
        artist.set_linestyle(linestyle)
    artist.set_alpha(alpha)
    artist.set_visible(bool(props.get("visible", True)))
    _tag_artist(artist, "shape", props)


def _tag_artist(artist: Any, kind: str, props: dict[str, Any]) -> None:
    artist._mve_kind = kind
    artist._mve_id = str(props.get("id", _new_id(kind)))
    if kind == "shape":
        artist._mve_shape_type = str(props.get("type", "rectangle"))
        artist._mve_x = float(props.get("x", 0.0))
        artist._mve_y = float(props.get("y", 0.0))
        artist._mve_width = float(props.get("width", 1.0))
        artist._mve_height = float(props.get("height", 1.0))
        artist._mve_angle = float(props.get("angle", 0.0))


def _polygon_vertices(
    shape_type: str,
    x: float,
    y: float,
    width: float,
    height: float,
    angle: float,
) -> list[tuple[float, float]]:
    if shape_type == "triangle":
        points = [(0.0, height / 2.0), (-width / 2.0, -height / 2.0), (width / 2.0, -height / 2.0)]
    else:
        points = [(0.0, height / 2.0), (width / 2.0, 0.0), (0.0, -height / 2.0), (-width / 2.0, 0.0)]
    radians = math.radians(angle)
    cos_a, sin_a = math.cos(radians), math.sin(radians)
    return [(x + px * cos_a - py * sin_a, y + px * sin_a + py * cos_a) for px, py in points]


def _default_geometry(ax: Any) -> tuple[float, float, float, float]:
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    width = abs(x1 - x0) * 0.22 or 1.0
    height = abs(y1 - y0) * 0.16 or 1.0
    return (x0 + x1) / 2.0, (y0 + y1) / 2.0, width, height


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def _edgecolor(artist: Any) -> str | None:
    if hasattr(artist, "get_edgecolor"):
        return _color(artist.get_edgecolor())
    if hasattr(artist, "get_color"):
        return _color(artist.get_color())
    return None


def _linestyle(artist: Any) -> str:
    if not hasattr(artist, "get_linestyle"):
        return "-"
    value = artist.get_linestyle()
    if value in {None, "None", "none"}:
        return "None"
    aliases = {
        "solid": "-",
        "dashed": "--",
        "dashdot": "-.",
        "dotted": ":",
    }
    return aliases.get(str(value), str(value))


def _color(value: Any) -> str | None:
    if value is None:
        return None
    try:
        return to_hex(value, keep_alpha=False)
    except (TypeError, ValueError):
        return str(value)


def _patch_color(patch: Any, kind: str) -> str:
    getter = patch.get_facecolor if kind == "face" else patch.get_edgecolor
    color = getter()
    try:
        if len(color) >= 4 and float(color[3]) == 0.0:
            return "none"
    except (TypeError, ValueError):
        pass
    return _color(color) or "none"
