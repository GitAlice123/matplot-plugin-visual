"""Generic filled patch adapter, used by boxplot boxes."""

from __future__ import annotations

from typing import Any

from matplotlib.figure import Figure
from matplotlib.patches import PathPatch

from ..refs import ArtistRef
from .base import BaseAdapter


class PatchAdapter(BaseAdapter):
    kind = "patch"

    def inspect(self, fig: Figure, claimed: set[int]) -> list[ArtistRef]:
        refs: list[ArtistRef] = []
        for ax_index, ax in enumerate(fig.axes):
            for patch_index, patch in enumerate(ax.patches):
                if id(patch) in claimed or not isinstance(patch, PathPatch):
                    continue
                self._claim(patch, claimed)
                refs.append(
                    ArtistRef(
                        f"Axes {ax_index} / Patch {patch_index}: {type(patch).__name__}",
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
        editor._add_bool("Visible", artist.get_visible(), artist.set_visible)
        editor._add_color("Fill color", artist.get_facecolor(), artist.set_facecolor)
        edge_width_widget = None

        def set_border(enabled: bool) -> None:
            width = float(edge_width_widget.value()) if edge_width_widget is not None else float(artist.get_linewidth())
            artist.set_linewidth(max(width, 1.0) if enabled else 0.0)

        border = editor._add_bool("Border", artist.get_linewidth() > 0, set_border)
        edge_color = editor._add_color("Edge color", artist.get_edgecolor(), artist.set_edgecolor)
        edge_width_widget = editor._add_float("Edge width", artist.get_linewidth(), artist.set_linewidth, 0.0, 50.0, 0.25)
        border.toggled.connect(lambda checked: editor._set_controls_enabled([edge_color, edge_width_widget], checked))
        editor._set_controls_enabled([edge_color, edge_width_widget], border.isChecked())
        editor._add_float("Alpha", artist.get_alpha() if artist.get_alpha() is not None else 1.0, artist.set_alpha, 0.0, 1.0, 0.05)
        editor._add_choice("Hatch", artist.get_hatch() or "None", ["None", "/", "\\", "|", "-", "+", "x", "o", "O", ".", "*"], lambda v: artist.set_hatch("" if v == "None" else v))
        return True
