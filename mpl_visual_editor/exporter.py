"""Export current figure styling as a replayable Python patch."""

from __future__ import annotations

from pathlib import Path
from pprint import pformat
from typing import Any
import math

from matplotlib.colors import to_hex
from matplotlib.figure import Figure

from .inspector import iter_artist_refs


def export_style(fig: Figure, path: str | Path = "style_patch.py") -> Path:
    """Write an ``apply_style(fig)`` function for supported artists."""

    output = Path(path)
    patches = [_snapshot(ref.kind, ref.path, ref.artist) for ref in iter_artist_refs(fig)]
    patches = [patch for patch in patches if patch["props"]]
    output.write_text(_render_module(patches), encoding="utf-8")
    return output


def _snapshot(kind: str, artist_path: tuple[Any, ...], artist: Any) -> dict[str, Any]:
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
    elif kind == "text":
        props = {
            "text": artist.get_text(),
            "color": _color(artist.get_color()),
            "fontsize": float(artist.get_fontsize()),
            "fontweight": artist.get_fontweight(),
            "fontstyle": artist.get_fontstyle(),
        }
    elif kind == "axis":
        axis_name = str(artist_path[2])[0]
        ax = artist.axes
        props = {
            "axis": axis_name,
            "scale": ax.get_xscale() if axis_name == "x" else ax.get_yscale(),
            "tick_start": _axis_tick_start(artist),
            "tick_interval": _axis_tick_interval(artist),
            "tick_label_fontsize": _axis_tick_label_prop(artist, "fontsize", 10.0),
            "tick_label_color": _color(_axis_tick_label_prop(artist, "color", "#000000")),
            "tick_label_weight": _axis_tick_label_prop(artist, "fontweight", "normal"),
            "tick_label_style": _axis_tick_label_prop(artist, "fontstyle", "normal"),
            "tick_label_rotation": float(_axis_tick_label_prop(artist, "rotation", 0.0)),
        }
    elif kind == "legend":
        frame = artist.get_frame()
        props = {
            "visible": bool(artist.get_visible()),
            "fontsize": _legend_fontsize(artist),
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

    return {"kind": kind, "path": artist_path, "props": props}


def _legend_fontsize(legend: Any) -> float | None:
    texts = legend.get_texts()
    if not texts:
        return None
    return float(texts[0].get_fontsize())


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


def _render_module(patches: list[dict[str, Any]]) -> str:
    return f'''"""Generated by mpl_visual_editor.

Import this file after your original plotting code and call apply_style(fig).
"""

import math

STYLE_PATCHES = {pformat(patches, width=100)}


def _resolve(fig, path):
    parts = tuple(path)
    if parts == ("figure",):
        return fig
    ax = fig.axes[int(parts[1])]
    if len(parts) == 2:
        return ax
    target = parts[2]
    if target == "title":
        return ax.title
    if target == "xlabel":
        return ax.xaxis.label
    if target == "ylabel":
        return ax.yaxis.label
    if target == "xaxis":
        return ax.xaxis
    if target == "yaxis":
        return ax.yaxis
    if target == "lines":
        return ax.lines[int(parts[3])]
    if target == "legend":
        return ax.get_legend()
    if target == "spines":
        return ax.spines[str(parts[3])]
    raise ValueError(f"Unsupported path: {{path!r}}")


def apply_style(fig):
    """Apply exported visual styling to a Matplotlib Figure."""

    for patch in STYLE_PATCHES:
        artist = _resolve(fig, patch["path"])
        if artist is None:
            continue
        kind = patch["kind"]
        props = patch["props"]

        if kind == "figure":
            artist.set_size_inches(props["width"], props["height"], forward=True)
            artist._mve_width = float(props["width"])
            artist._mve_height = float(props["height"])
        elif kind == "axes":
            artist.set_facecolor(props["facecolor"])
            artist.set_xlabel(props["xlabel"])
            artist.set_ylabel(props["ylabel"])
            artist.set_title(props["title"])
            artist.grid(bool(props["xgrid"]), axis="x")
            artist.grid(bool(props["ygrid"]), axis="y")
        elif kind == "line":
            artist.set_color(props["color"])
            artist.set_linewidth(props["linewidth"])
            artist.set_linestyle(props["linestyle"])
            artist.set_marker(props["marker"])
            artist.set_markersize(props["markersize"])
            artist.set_alpha(props["alpha"])
            artist.set_label(props["label"])
        elif kind == "text":
            artist.set_text(props["text"])
            artist.set_color(props["color"])
            artist.set_fontsize(props["fontsize"])
            artist.set_fontweight(props["fontweight"])
            artist.set_fontstyle(props["fontstyle"])
        elif kind == "axis":
            ax = artist.axes
            axis_name = props["axis"]
            if axis_name == "x":
                ax.set_xscale(props["scale"])
            else:
                ax.set_yscale(props["scale"])
            _apply_axis_ticks(ax, axis_name, props["tick_start"], props["tick_interval"])
            _apply_axis_tick_labels(
                artist,
                props["tick_label_fontsize"],
                props["tick_label_color"],
                props["tick_label_weight"],
                props["tick_label_style"],
                props["tick_label_rotation"],
            )
        elif kind == "legend":
            ax = artist.axes
            artist = ax.legend(
                loc=props["loc"],
                bbox_to_anchor=props["bbox_to_anchor"],
                ncols=props["ncols"],
                fontsize=props["fontsize"],
                frameon=props["frame_on"],
                borderpad=props["borderpad"],
                labelspacing=props["labelspacing"],
                handlelength=props["handlelength"],
                handletextpad=props["handletextpad"],
                borderaxespad=props["borderaxespad"],
                columnspacing=props["columnspacing"],
            )
            artist.set_visible(props["visible"])
            for text in artist.get_texts():
                if props["fontsize"] is not None:
                    text.set_fontsize(props["fontsize"])
            frame = artist.get_frame()
            frame.set_visible(props["frame_on"])
            frame.set_alpha(props["frame_alpha"])
            frame.set_facecolor(props["facecolor"])
            frame.set_edgecolor(props["edgecolor"])
        elif kind == "spine":
            artist.set_visible(props["visible"])
            artist.set_edgecolor(props["color"])
            artist.set_linewidth(props["linewidth"])

    try:
        fig.tight_layout()
    except Exception:
        pass
    fig.canvas.draw_idle()
    return fig


def _apply_axis_ticks(ax, axis_name, start, interval):
    interval = float(interval)
    if interval <= 0:
        return
    if axis_name == "x":
        low, high = ax.get_xlim()
    else:
        low, high = ax.get_ylim()
    inverted = high < low
    if high < low:
        low, high = high, low
    ticks = []
    value = float(start)
    low = value
    if high <= low:
        high = low + interval
    limit = high + interval * 0.5
    while value <= limit and len(ticks) < 10000:
        if math.isfinite(value):
            ticks.append(value)
        value += interval
    if axis_name == "x":
        ax.set_xticks(ticks)
        ax.set_xlim((high, low) if inverted else (low, high))
        ax.xaxis._mve_tick_start = float(start)
        ax.xaxis._mve_tick_interval = interval
    else:
        ax.set_yticks(ticks)
        ax.set_ylim((high, low) if inverted else (low, high))
        ax.yaxis._mve_tick_start = float(start)
        ax.yaxis._mve_tick_interval = interval


def _apply_axis_tick_labels(axis, fontsize, color, weight, style, rotation):
    axis._mve_tick_label_fontsize = float(fontsize)
    axis._mve_tick_label_color = color
    axis._mve_tick_label_fontweight = weight
    axis._mve_tick_label_fontstyle = style
    axis._mve_tick_label_rotation = float(rotation)
    for label in axis.get_ticklabels():
        label.set_fontsize(float(fontsize))
        label.set_color(color)
        label.set_fontweight(weight)
        label.set_fontstyle(style)
        label.set_rotation(float(rotation))
'''
