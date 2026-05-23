"""X/Y axis adapter."""

from __future__ import annotations

from typing import Any

from matplotlib.figure import Figure

from ..refs import ArtistRef
from .base import BaseAdapter


class AxisAdapter(BaseAdapter):
    kind = "axis"

    def inspect(self, fig: Figure, claimed: set[int]) -> list[ArtistRef]:
        refs: list[ArtistRef] = []
        for ax_index, ax in enumerate(fig.axes):
            for name, axis in [("X axis", ax.xaxis), ("Y axis", ax.yaxis)]:
                path_name = "xaxis" if name.startswith("X") else "yaxis"
                self._claim(axis, claimed)
                refs.append(
                    ArtistRef(
                        f"Axes {ax_index} / {name}",
                        self.kind,
                        ("axes", ax_index, path_name),
                        axis,
                    )
                )
        return refs

    def hit_test(self, ref: ArtistRef, event: Any, editor: Any) -> bool:
        if event.x is None or event.y is None:
            return False

        x = float(event.x)
        y = float(event.y)
        return self._axis_artist_contains(ref, event, editor, x, y)

    def highlight(self, ref: ArtistRef, editor: Any) -> dict[str, Any]:
        return {
            "kind": ref.kind,
            "axis_artists": [
                self._highlight_artist(axis_artist)
                for axis_artist in self._axis_highlight_artists(ref)
                if hasattr(axis_artist, "get_path_effects") and hasattr(axis_artist, "set_path_effects")
            ],
        }

    def restore_highlight(self, ref: ArtistRef, editor: Any, state: Any) -> None:
        if isinstance(state, dict):
            for axis_artist_state in state.get("axis_artists", []):
                self._restore_artist_highlight(axis_artist_state)

    def build_form(self, ref: ArtistRef, editor: Any) -> bool:
        artist = ref.artist
        axis_name = str(ref.path[2])[0]
        ax = artist.axes
        if not editor._is_categorical_axis(artist, axis_name):
            scale = ax.get_xscale() if axis_name == "x" else ax.get_yscale()
            editor._add_choice("Scale", scale, ["linear", "log"], lambda v: editor._set_axis_scale(artist, axis_name, v))
            editor._add_float("Tick start", editor._axis_tick_start(artist), lambda v: editor._apply_axis_ticks(artist, axis_name, v, editor._axis_tick_interval(artist), editor._axis_tick_end(artist)), -1_000_000_000.0, 1_000_000_000.0, 0.1, decimals=6)
            editor._add_float("Tick end", editor._axis_tick_end(artist), lambda v: editor._apply_axis_ticks(artist, axis_name, editor._axis_tick_start(artist), editor._axis_tick_interval(artist), v), -1_000_000_000.0, 1_000_000_000.0, 0.1, decimals=6)
            editor._add_float("Tick interval", editor._axis_tick_interval(artist), lambda v: editor._apply_axis_ticks(artist, axis_name, editor._axis_tick_start(artist), v, editor._axis_tick_end(artist)), 0.000001, 1_000_000_000.0, 0.1, decimals=6)
        editor._add_float("Tick label size", editor._axis_tick_label_prop(artist, "fontsize", 10.0), lambda v: editor._apply_axis_tick_labels(artist, fontsize=v), 1.0, 96.0, 1.0)
        editor._add_color("Tick label color", editor._axis_tick_label_prop(artist, "color", "#000000"), lambda v: editor._apply_axis_tick_labels(artist, color=v))
        editor._add_choice("Tick label weight", editor._axis_tick_label_prop(artist, "fontweight", "normal"), ["normal", "bold", "light", "semibold", "heavy"], lambda v: editor._apply_axis_tick_labels(artist, weight=v))
        editor._add_choice("Tick label style", editor._axis_tick_label_prop(artist, "fontstyle", "normal"), ["normal", "italic", "oblique"], lambda v: editor._apply_axis_tick_labels(artist, style=v))
        editor._add_float("Tick label rotation", editor._axis_tick_label_prop(artist, "rotation", 0.0), lambda v: editor._apply_axis_tick_labels(artist, rotation=v), -180.0, 180.0, 5.0, decimals=1)
        return True

    def _axis_artist_contains(
        self,
        ref: ArtistRef,
        event: Any,
        editor: Any,
        x: float,
        y: float,
    ) -> bool:
        renderer = editor.canvas.get_renderer()
        for artist, pad_x, pad_y in self._axis_tick_hit_targets(ref):
            if hasattr(artist, "get_visible") and not artist.get_visible():
                continue
            try:
                contains, _details = artist.contains(event)
                if contains:
                    return True
            except Exception:
                pass
            try:
                bbox = artist.get_window_extent(renderer=renderer)
                if self._bbox_contains_padded(bbox, x, y, pad_x, pad_y):
                    return True
            except Exception:
                pass
        return False

    def _axis_tick_hit_targets(self, ref: ArtistRef) -> list[tuple[Any, float, float]]:
        axis = ref.artist
        targets: list[tuple[Any, float, float]] = []
        for tick in axis.get_major_ticks():
            if tick.tick1line is not None:
                targets.append((tick.tick1line, 10.0, 10.0))
            if tick.tick2line is not None:
                targets.append((tick.tick2line, 10.0, 10.0))
            if tick.label1 is not None:
                targets.append((tick.label1, 4.0, 4.0))
            if tick.label2 is not None:
                targets.append((tick.label2, 4.0, 4.0))
        return targets

    def _bbox_contains_padded(self, bbox: Any, x: float, y: float, pad_x: float, pad_y: float) -> bool:
        return bool(
            bbox.x0 - pad_x <= x <= bbox.x1 + pad_x
            and bbox.y0 - pad_y <= y <= bbox.y1 + pad_y
        )

    def _axis_highlight_artists(self, ref: ArtistRef) -> list[Any]:
        axis = ref.artist
        artists: list[Any] = []
        for tick in axis.get_major_ticks():
            if tick.tick1line is not None:
                artists.append(tick.tick1line)
            if tick.tick2line is not None:
                artists.append(tick.tick2line)
            if tick.label1 is not None:
                artists.append(tick.label1)
            if tick.label2 is not None:
                artists.append(tick.label2)
        return artists

