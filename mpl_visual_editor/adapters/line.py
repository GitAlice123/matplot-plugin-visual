"""Line adapter."""

from __future__ import annotations

from typing import Any

from matplotlib.figure import Figure

from ..refs import ArtistRef
from .base import BaseAdapter


class LineAdapter(BaseAdapter):
    kind = "line"

    def inspect(self, fig: Figure, claimed: set[int]) -> list[ArtistRef]:
        refs: list[ArtistRef] = []
        for ax_index, ax in enumerate(fig.axes):
            for line_index, line in enumerate(ax.lines):
                if getattr(line, "_mve_kind", None) == "editor_handle":
                    continue
                self._claim(line, claimed)
                refs.append(
                    ArtistRef(
                        f"Axes {ax_index} / Line {line_index}: {line.get_label()}",
                        self.kind,
                        ("axes", ax_index, "lines", line_index),
                        line,
                    )
                )
        return refs

    def delete(self, ref: ArtistRef) -> None:
        ref.artist.remove()

    def highlight(self, ref: ArtistRef, editor: Any) -> dict[str, Any]:
        return {"kind": ref.kind, "artist": self._highlight_artist(ref.artist, boost_zorder=True)}

    def build_form(self, ref: ArtistRef, editor: Any) -> bool:
        artist = ref.artist
        editor._add_bool("Visible", artist.get_visible(), artist.set_visible)
        editor._add_text("Label", artist.get_label(), artist.set_label)
        editor._add_color("Color", artist.get_color(), artist.set_color)
        editor._add_float("Line width", artist.get_linewidth(), artist.set_linewidth, 0.0, 20.0, 0.25)
        editor._add_choice("Line style", artist.get_linestyle(), ["-", "--", "-.", ":", "None", " "], artist.set_linestyle)
        editor._add_choice("Draw style", artist.get_drawstyle(), ["default", "steps", "steps-pre", "steps-mid", "steps-post"], artist.set_drawstyle)
        editor._add_choice("Marker", artist.get_marker(), ["None", " ", ".", "o", "s", "^", "v", "D", "x", "+", "*"], artist.set_marker)
        editor._add_float("Marker size", artist.get_markersize(), artist.set_markersize, 0.0, 40.0, 0.5)
        editor._add_color("Marker fill", artist.get_markerfacecolor(), artist.set_markerfacecolor)
        marker_edge_width_widget = None

        def set_marker_border(enabled: bool) -> None:
            width = float(marker_edge_width_widget.value()) if marker_edge_width_widget is not None else float(artist.get_markeredgewidth())
            artist.set_markeredgewidth(max(width, 1.0) if enabled else 0.0)

        marker_border = editor._add_bool("Marker border", artist.get_markeredgewidth() > 0, set_marker_border)
        marker_edge = editor._add_color("Marker edge", artist.get_markeredgecolor(), artist.set_markeredgecolor)
        marker_edge_width_widget = editor._add_float("Marker edge width", artist.get_markeredgewidth(), artist.set_markeredgewidth, 0.0, 20.0, 0.25)
        marker_border.toggled.connect(lambda checked: editor._set_controls_enabled([marker_edge, marker_edge_width_widget], checked))
        editor._set_controls_enabled([marker_edge, marker_edge_width_widget], marker_border.isChecked())
        editor._add_float("Alpha", artist.get_alpha() if artist.get_alpha() is not None else 1.0, artist.set_alpha, 0.0, 1.0, 0.05)
        editor._add_position_save_button("Save position")
        return True

