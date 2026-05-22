"""Serializable style snapshots for supported Matplotlib artists."""

from __future__ import annotations

from typing import Any
import math

from matplotlib.colors import to_hex


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
            "color": _color(artist.get_color()),
            "linewidth": float(artist.get_linewidth()),
            "linestyle": artist.get_linestyle(),
            "marker": artist.get_marker(),
            "markersize": float(artist.get_markersize()),
            "alpha": artist.get_alpha(),
            "label": artist.get_label(),
        }
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
        props = {
            "text": artist.get_text(),
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
        ticks_explicit = hasattr(artist, "_mve_tick_start") or hasattr(artist, "_mve_tick_interval")
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
        props = {"axis": axis_name}
        if scale_explicit or not for_export:
            props["scale"] = scale
            props["scale_explicit"] = bool(scale_explicit)
        if ticks_explicit or not for_export:
            props.update(
                {
                    "ticks_explicit": bool(ticks_explicit),
                    "tick_start": _axis_tick_start(artist),
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


def _legend_fontsize(legend: Any) -> float | None:
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
        if hasattr(handle, "get_facecolor") and hasattr(handle, "get_hatch"):
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
                    "alpha": handle.get_alpha(),
                }
            )
    return specs


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


def _color(value: Any) -> str | None:
    if value is None:
        return None
    try:
        return to_hex(value, keep_alpha=False)
    except ValueError:
        return str(value)
