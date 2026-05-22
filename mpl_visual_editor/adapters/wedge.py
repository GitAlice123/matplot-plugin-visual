"""Pie wedge adapter."""

from __future__ import annotations

from typing import Any

from matplotlib.figure import Figure
from matplotlib.patches import Wedge

from ..refs import ArtistRef
from .base import BaseAdapter


class WedgeAdapter(BaseAdapter):
    kind = "wedge"

    def inspect(self, fig: Figure, claimed: set[int]) -> list[ArtistRef]:
        refs: list[ArtistRef] = []
        for ax_index, ax in enumerate(fig.axes):
            for patch_index, patch in enumerate(ax.patches):
                if id(patch) in claimed or not isinstance(patch, Wedge):
                    continue
                self._claim(patch, claimed)
                refs.append(
                    ArtistRef(
                        f"Axes {ax_index} / Pie wedge {patch_index}",
                        self.kind,
                        ("axes", ax_index, "patches", patch_index),
                        patch,
                    )
                )
        return refs

    def delete(self, ref: ArtistRef) -> None:
        ref.artist.remove()

    def highlight(self, ref: ArtistRef, editor: Any) -> dict[str, Any]:
        return {"kind": ref.kind, "artist": self._highlight_artist(ref.artist, linewidth=5, boost_zorder=True)}

    def build_form(self, ref: ArtistRef, editor: Any) -> bool:
        artist = ref.artist
        center_x, center_y = artist.center
        editor._add_bool("Visible", artist.get_visible(), artist.set_visible)
        editor._add_color("Fill color", artist.get_facecolor(), artist.set_facecolor)
        edge_width_widget = None

        def set_border(enabled: bool) -> None:
            width = float(edge_width_widget.value()) if edge_width_widget is not None else float(artist.get_linewidth())
            artist.set_linewidth(max(width, 1.0) if enabled else 0.0)

        border = editor._add_bool("Border", artist.get_linewidth() > 0, set_border)
        edge_color = editor._add_color("Edge color", artist.get_edgecolor(), artist.set_edgecolor)
        edge_width_widget = editor._add_float("Edge width", artist.get_linewidth(), artist.set_linewidth, 0.0, 20.0, 0.25)
        border.toggled.connect(lambda checked: editor._set_controls_enabled([edge_color, edge_width_widget], checked))
        editor._set_controls_enabled([edge_color, edge_width_widget], border.isChecked())
        editor._add_float("Alpha", artist.get_alpha() if artist.get_alpha() is not None else 1.0, artist.set_alpha, 0.0, 1.0, 0.05)
        editor._add_choice("Hatch", artist.get_hatch() or "None", ["None", "/", "\\", "|", "-", "+", "x", "o", "O", ".", "*"], lambda v: artist.set_hatch("" if v == "None" else v))
        editor._add_float("Center X", float(center_x), lambda v: self._set_center(artist, x=v), -1e12, 1e12, 0.01, decimals=4)
        editor._add_float("Center Y", float(center_y), lambda v: self._set_center(artist, y=v), -1e12, 1e12, 0.01, decimals=4)
        editor._add_float("Radius", float(artist.r), artist.set_radius, 1e-12, 1e12, 0.01, decimals=4)
        editor._add_float("Inner width", float(artist.width or 0.0), lambda v: artist.set_width(None if v <= 0 else v), 0.0, 1e12, 0.01, decimals=4)
        editor._add_float("Start angle", float(artist.theta1), artist.set_theta1, -3600.0, 3600.0, 1.0)
        editor._add_float("End angle", float(artist.theta2), artist.set_theta2, -3600.0, 3600.0, 1.0)
        return True

    def _set_center(self, artist: Any, x: float | None = None, y: float | None = None) -> None:
        center_x, center_y = artist.center
        artist.set_center((float(center_x if x is None else x), float(center_y if y is None else y)))
