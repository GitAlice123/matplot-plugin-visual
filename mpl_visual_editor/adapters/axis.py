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
        if self._axis_artist_contains(ref, event, editor, x, y):
            return True

        ax = ref.artist.axes
        bbox = ax.bbox
        pad = 34
        inside_expanded = (
            bbox.x0 - pad <= x <= bbox.x1 + pad
            and bbox.y0 - pad <= y <= bbox.y1 + pad
        )
        if not inside_expanded:
            return False

        near_x_axis = bbox.x0 - pad <= x <= bbox.x1 + pad and (
            abs(y - bbox.y0) <= pad or abs(y - bbox.y1) <= pad
        )
        near_y_axis = bbox.y0 - pad <= y <= bbox.y1 + pad and (
            abs(x - bbox.x0) <= pad or abs(x - bbox.x1) <= pad
        )
        if not (near_x_axis or near_y_axis):
            return False

        target = "xaxis" if near_x_axis and not near_y_axis else "yaxis"
        if near_x_axis and near_y_axis:
            distance_x = min(abs(y - bbox.y0), abs(y - bbox.y1))
            distance_y = min(abs(x - bbox.x0), abs(x - bbox.x1))
            target = "xaxis" if distance_x <= distance_y else "yaxis"
        return bool(ref.artist.axes is ax and ref.path[2] == target)

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

    def _axis_artist_contains(
        self,
        ref: ArtistRef,
        event: Any,
        editor: Any,
        x: float,
        y: float,
    ) -> bool:
        renderer = editor.canvas.get_renderer()
        for artist in self._axis_highlight_artists(ref):
            if hasattr(artist, "get_visible") and not artist.get_visible():
                continue
            try:
                contains, _details = artist.contains(event)
                if contains:
                    return True
            except Exception:
                pass
            try:
                bbox = artist.get_window_extent(renderer=renderer).expanded(1.4, 1.8)
                if bbox.contains(x, y):
                    return True
            except Exception:
                pass
        return False

    def _axis_highlight_artists(self, ref: ArtistRef) -> list[Any]:
        axis = ref.artist
        artists: list[Any] = [axis.label]
        for tick in axis.get_major_ticks():
            artists.extend([tick.tick1line, tick.tick2line, tick.label1, tick.label2])
        return artists

