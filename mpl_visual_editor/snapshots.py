"""Serializable style snapshots for supported Matplotlib artists."""

from __future__ import annotations

from typing import Any, Optional
import math

from matplotlib.collections import PathCollection
from matplotlib.colors import to_hex
from matplotlib.markers import MarkerStyle
import numpy as np

from .adapters.arrow import arrow_props
from .fills import fill_props
from .shapes import shape_props, textbox_props


def snapshot_artist(
    kind: str,
    artist_path: tuple[Any, ...],
    artist: Any,
    for_export: bool = False,
) -> dict[str, Any]:
    """Return serializable style properties for one editor artist reference."""

    props: dict[str, Any] = {}

    if kind == "figure":
        if hasattr(artist, "_mve_width") and hasattr(artist, "_mve_height"):
            width, height = float(artist._mve_width), float(artist._mve_height)
        else:
            width, height = artist.get_size_inches()
        props = {
            "width": float(width),
            "height": float(height),
            "aspect": float(width / height) if height else 1.0,
        }
    elif kind == "axes":
        props = {
            "facecolor": _color(artist.get_facecolor()),
            "xlabel": artist.get_xlabel(),
            "ylabel": artist.get_ylabel(),
            "title": artist.get_title(),
            "xgrid": any(line.get_visible() for line in artist.get_xgridlines()),
            "ygrid": any(line.get_visible() for line in artist.get_ygridlines()),
        }
    elif kind == "line":
        props = {
            "visible": bool(artist.get_visible()),
            "color": _color(artist.get_color()),
            "linewidth": float(artist.get_linewidth()),
            "linestyle": artist.get_linestyle(),
            "drawstyle": artist.get_drawstyle(),
            "marker": artist.get_marker(),
            "markersize": float(artist.get_markersize()),
            "markerfacecolor": _color(artist.get_markerfacecolor()),
            "markeredgecolor": _color(artist.get_markeredgecolor()),
            "markeredgewidth": float(artist.get_markeredgewidth()),
            "alpha": artist.get_alpha(),
            "label": artist.get_label(),
        }
        if hasattr(artist, "_mve_xdata") and hasattr(artist, "_mve_ydata"):
            props["xdata"] = list(artist._mve_xdata)
            props["ydata"] = list(artist._mve_ydata)
    elif kind == "scatter":
        props = {
            "visible": bool(artist.get_visible()),
            "label": artist.get_label(),
            "marker": _path_collection_marker(artist),
            "facecolor": _first_color(artist.get_facecolors()),
            "edgecolor": _first_color(artist.get_edgecolors()),
            "linewidth": _first_float(artist.get_linewidths(), 1.0),
            "size": _first_float(artist.get_sizes(), 36.0),
            "alpha": artist.get_alpha(),
        }
    elif kind == "wedge":
        center_x, center_y = artist.center
        props = {
            "visible": bool(artist.get_visible()),
            "facecolor": _color(artist.get_facecolor()),
            "edgecolor": _color(artist.get_edgecolor()),
            "linewidth": float(artist.get_linewidth()),
            "alpha": artist.get_alpha(),
            "hatch": artist.get_hatch() or "",
            "center": [float(center_x), float(center_y)],
            "radius": float(artist.r),
            "width": None if artist.width is None else float(artist.width),
            "theta1": float(artist.theta1),
            "theta2": float(artist.theta2),
        }
    elif kind == "patch":
        props = {
            "visible": bool(artist.get_visible()),
            "facecolor": _color(artist.get_facecolor()),
            "edgecolor": _color(artist.get_edgecolor()),
            "linewidth": float(artist.get_linewidth()),
            "alpha": artist.get_alpha(),
            "hatch": artist.get_hatch() or "",
        }
    elif kind == "shape":
        props = shape_props(artist)
    elif kind == "textbox":
        props = textbox_props(artist)
    elif kind == "fill":
        props = fill_props(artist)
    elif kind == "arrow":
        props = arrow_props(artist)
    elif kind == "bar":
        patches = list(artist.patches)
        props = {
            "label": artist.get_label(),
            "visibles": [bool(patch.get_visible()) for patch in patches],
            "facecolors": [_color(patch.get_facecolor()) for patch in patches],
            "edgecolors": [_color(patch.get_edgecolor()) for patch in patches],
            "linewidths": [float(patch.get_linewidth()) for patch in patches],
            "alphas": [patch.get_alpha() for patch in patches],
            "hatches": [patch.get_hatch() or "" for patch in patches],
            "widths": [abs(float(patch.get_width())) for patch in patches],
        }
    elif kind == "text":
        x, y = artist.get_position()
        props = {
            "text": artist.get_text(),
            "x": float(x),
            "y": float(y),
            "rotation": float(artist.get_rotation()),
            "color": _color(artist.get_color()),
            "fontsize": float(artist.get_fontsize()),
            "fontweight": artist.get_fontweight(),
            "fontstyle": artist.get_fontstyle(),
        }
    elif kind == "text_group":
        texts = [text for text in artist if hasattr(text, "get_text")]
        if texts:
            first = texts[0]
            props = {
                "count": len(texts),
                "color": _color(first.get_color()),
                "fontsize": float(first.get_fontsize()),
                "fontweight": first.get_fontweight(),
                "fontstyle": first.get_fontstyle(),
            }
    elif kind == "axis":
        axis_name = str(artist_path[2])[0]
        ax = artist.axes
        scale = ax.get_xscale() if axis_name == "x" else ax.get_yscale()
        scale_explicit = hasattr(artist, "_mve_scale")
        ticks_explicit = (
            hasattr(artist, "_mve_tick_start")
            or hasattr(artist, "_mve_tick_end")
            or hasattr(artist, "_mve_tick_interval")
        )
        labels_explicit = any(
            hasattr(artist, attr)
            for attr in [
                "_mve_tick_label_fontsize",
                "_mve_tick_label_color",
                "_mve_tick_label_fontweight",
                "_mve_tick_label_fontstyle",
                "_mve_tick_label_rotation",
            ]
        )
        labelpad_explicit = hasattr(artist, "_mve_labelpad")
        props = {"axis": axis_name}
        if labelpad_explicit or not for_export:
            props["labelpad"] = float(artist.labelpad)
            props["labelpad_explicit"] = bool(labelpad_explicit)
        if scale_explicit or not for_export:
            props["scale"] = scale
            props["scale_explicit"] = bool(scale_explicit)
        if ticks_explicit or not for_export:
            props.update(
                {
                    "ticks_explicit": bool(ticks_explicit),
                    "tick_start": _axis_tick_start(artist),
                    "tick_end": _axis_tick_end(artist),
                    "tick_interval": _axis_tick_interval(artist),
                }
            )
        if labels_explicit or not for_export:
            props.update(
                {
                    "tick_labels_explicit": bool(labels_explicit),
                    "tick_label_fontsize": _axis_tick_label_prop(artist, "fontsize", 10.0),
                    "tick_label_color": _color(_axis_tick_label_prop(artist, "color", "#000000")),
                    "tick_label_weight": _axis_tick_label_prop(artist, "fontweight", "normal"),
                    "tick_label_style": _axis_tick_label_prop(artist, "fontstyle", "normal"),
                    "tick_label_rotation": float(_axis_tick_label_prop(artist, "rotation", 0.0)),
                }
            )
        if for_export and set(props) == {"axis"}:
            props = {}
    elif kind == "legend":
        frame = artist.get_frame()
        props = {
            "visible": bool(artist.get_visible()),
            "fontsize": _legend_fontsize(artist),
            "handle_specs": _legend_handle_specs(artist),
            "loc": getattr(artist, "_mve_loc", getattr(artist, "_loc", "best")),
            "bbox_to_anchor": getattr(artist, "_mve_bbox_to_anchor", None),
            "ncols": getattr(artist, "_ncols", 1),
            "frame_on": bool(frame.get_visible()),
            "frame_alpha": frame.get_alpha(),
            "facecolor": _color(frame.get_facecolor()),
            "edgecolor": _color(frame.get_edgecolor()),
            "frame_linewidth": float(frame.get_linewidth()),
            "borderpad": float(artist.borderpad),
            "labelspacing": float(artist.labelspacing),
            "handlelength": float(artist.handlelength),
            "handletextpad": float(artist.handletextpad),
            "borderaxespad": float(artist.borderaxespad),
            "columnspacing": float(artist.columnspacing),
        }
    elif kind == "spine":
        props = {
            "visible": bool(artist.get_visible()),
            "color": _color(artist.get_edgecolor()),
            "linewidth": float(artist.get_linewidth()),
        }

    return {
        "kind": kind,
        "path": _plain_value(artist_path),
        "props": _plain_value(props),
    }


def _plain_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _plain_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return tuple(_plain_value(item) for item in value)
    if isinstance(value, list):
        return [_plain_value(item) for item in value]
    if hasattr(value, "item"):
        try:
            return value.item()
        except (TypeError, ValueError):
            pass
    return value


def _legend_fontsize(legend: Any) -> Optional[float]:
    texts = legend.get_texts()
    if not texts:
        return None
    return float(texts[0].get_fontsize())


def _legend_handle_specs(legend: Any) -> list[dict[str, Any]]:
    handles = getattr(legend, "legend_handles", None)
    if handles is None:
        handles = getattr(legend, "legendHandles", [])
    labels = [text.get_text() for text in legend.get_texts()]
    specs: list[dict[str, Any]] = []
    for index, handle in enumerate(handles):
        label = labels[index] if index < len(labels) else getattr(handle, "get_label", lambda: "")()
        if isinstance(handle, PathCollection):
            paths = handle.get_paths()
            path = paths[0] if paths else None
            specs.append(
                {
                    "kind": "scatter",
                    "label": label,
                    "facecolor": _first_color(handle.get_facecolors()),
                    "edgecolor": _first_color(handle.get_edgecolors()),
                    "linewidth": _first_float(handle.get_linewidths(), 1.0),
                    "size": _first_float(handle.get_sizes(), 36.0),
                    "alpha": handle.get_alpha(),
                    "marker": _marker_name(path),
                    "path": _path_spec(path),
                }
            )
        elif hasattr(handle, "get_facecolor") and hasattr(handle, "get_hatch"):
            specs.append(
                {
                    "kind": "patch",
                    "label": label,
                    "facecolor": _color(handle.get_facecolor()),
                    "edgecolor": _color(handle.get_edgecolor()) if hasattr(handle, "get_edgecolor") else None,
                    "linewidth": float(handle.get_linewidth()) if hasattr(handle, "get_linewidth") else 1.0,
                    "hatch": handle.get_hatch() or "",
                    "alpha": handle.get_alpha(),
                }
            )
        elif self_marker := _line_marker_spec(handle, label):
            specs.append(self_marker)
        elif hasattr(handle, "get_color") and hasattr(handle, "get_linestyle"):
            specs.append(
                {
                    "kind": "line",
                    "label": label,
                    "color": _color(handle.get_color()),
                    "linewidth": float(handle.get_linewidth()) if hasattr(handle, "get_linewidth") else 1.0,
                    "linestyle": handle.get_linestyle(),
                    "marker": handle.get_marker() if hasattr(handle, "get_marker") else "None",
                    "markersize": float(handle.get_markersize()) if hasattr(handle, "get_markersize") else 6.0,
                    "markerfacecolor": _color(handle.get_markerfacecolor()) if hasattr(handle, "get_markerfacecolor") else None,
                    "markeredgecolor": _color(handle.get_markeredgecolor()) if hasattr(handle, "get_markeredgecolor") else None,
                    "markeredgewidth": float(handle.get_markeredgewidth()) if hasattr(handle, "get_markeredgewidth") else 1.0,
                    "alpha": handle.get_alpha(),
                }
            )
    return specs


def _line_marker_spec(handle: Any, label: str) -> Optional[dict[str, Any]]:
    if not (hasattr(handle, "get_marker") and hasattr(handle, "get_linestyle")):
        return None
    marker = handle.get_marker()
    linestyle = str(handle.get_linestyle())
    if marker in {None, "None", "none", ""} or linestyle not in {"None", "none", " "}:
        return None
    markersize = float(handle.get_markersize()) if hasattr(handle, "get_markersize") else 6.0
    return {
        "kind": "scatter",
        "label": label,
        "facecolor": _color(handle.get_markerfacecolor()) if hasattr(handle, "get_markerfacecolor") else None,
        "edgecolor": _color(handle.get_markeredgecolor()) if hasattr(handle, "get_markeredgecolor") else None,
        "linewidth": float(handle.get_markeredgewidth()) if hasattr(handle, "get_markeredgewidth") else 1.0,
        "size": markersize * markersize,
        "alpha": handle.get_alpha() if hasattr(handle, "get_alpha") else None,
        "marker": marker,
        "path": None,
    }


def _path_spec(path: Any) -> Optional[dict[str, Any]]:
    if path is None:
        return None
    vertices = path.vertices.tolist() if hasattr(path.vertices, "tolist") else list(path.vertices)
    codes = path.codes.tolist() if getattr(path, "codes", None) is not None else None
    return {"vertices": vertices, "codes": codes}


def _marker_name(path: Any) -> Optional[str]:
    if path is None:
        return None
    for marker in ["x", "o", "s", "^", "v", "D", "+", "*", ".", "P", "X"]:
        marker_style = MarkerStyle(marker)
        marker_path = marker_style.get_path().transformed(marker_style.get_transform())
        if _paths_match(path, marker_path):
            return marker
    return None


def _path_collection_marker(collection: Any) -> str:
    paths = collection.get_paths() if hasattr(collection, "get_paths") else []
    if not paths:
        return "o"
    return _marker_name(paths[0]) or "o"


def _paths_match(left: Any, right: Any) -> bool:
    left_codes = getattr(left, "codes", None)
    right_codes = getattr(right, "codes", None)
    if left_codes is None and right_codes is not None:
        return False
    if left_codes is not None and right_codes is None:
        return False
    if left_codes is not None and not np.array_equal(left_codes, right_codes):
        return False
    return np.allclose(left.vertices, right.vertices, rtol=1e-6, atol=1e-8)


def _axis_tick_start(axis: Any) -> float:
    if hasattr(axis, "_mve_tick_start"):
        return float(axis._mve_tick_start)
    ticks = _finite_ticks(axis)
    if ticks:
        return float(ticks[0])
    low, _high = axis.get_view_interval()
    return float(low)


def _axis_tick_interval(axis: Any) -> float:
    if hasattr(axis, "_mve_tick_interval"):
        return float(axis._mve_tick_interval)
    ticks = _finite_ticks(axis)
    for left, right in zip(ticks, ticks[1:]):
        interval = right - left
        if interval > 0:
            return float(interval)
    return 1.0


def _axis_tick_end(axis: Any) -> float:
    if hasattr(axis, "_mve_tick_end"):
        return float(axis._mve_tick_end)
    ticks = _finite_ticks(axis)
    if ticks:
        return float(ticks[-1])
    _low, high = axis.get_view_interval()
    return float(high)


def _finite_ticks(axis: Any) -> list[float]:
    ticks: list[float] = []
    for tick in axis.get_ticklocs():
        value = float(tick)
        if math.isfinite(value):
            ticks.append(value)
    return sorted(set(ticks))


def _axis_tick_label_prop(axis: Any, prop: str, default: Any) -> Any:
    attr = f"_mve_tick_label_{prop}"
    if hasattr(axis, attr):
        return getattr(axis, attr)
    labels = axis.get_ticklabels()
    visible_labels = [label for label in labels if label.get_visible()]
    label = visible_labels[0] if visible_labels else (labels[0] if labels else None)
    if label is None:
        return default
    if prop == "fontsize":
        return float(label.get_fontsize())
    if prop == "color":
        return label.get_color()
    if prop == "fontweight":
        return label.get_fontweight()
    if prop == "fontstyle":
        return label.get_fontstyle()
    if prop == "rotation":
        return float(label.get_rotation())
    return default


def _color(value: Any) -> Optional[str]:
    if value is None:
        return None
    try:
        return to_hex(value, keep_alpha=False)
    except ValueError:
        return str(value)


def _first_color(values: Any) -> str:
    if values is None or len(values) == 0:
        return "#000000"
    return _color(values[0]) or "#000000"


def _first_float(values: Any, default: float) -> float:
    if values is None or len(values) == 0:
        return float(default)
    return float(values[0])
