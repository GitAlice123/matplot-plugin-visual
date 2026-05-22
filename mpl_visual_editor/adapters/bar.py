"""Bar container adapter."""

from __future__ import annotations

from typing import Any

from matplotlib.container import BarContainer
from matplotlib.figure import Figure
from PySide6.QtWidgets import QLabel

from ..refs import ArtistRef
from .base import BaseAdapter


class BarAdapter(BaseAdapter):
    kind = "bar"

    def inspect(self, fig: Figure, claimed: set[int]) -> list[ArtistRef]:
        refs: list[ArtistRef] = []
        for ax_index, ax in enumerate(fig.axes):
            for container_index, container in enumerate(ax.containers):
                if isinstance(container, BarContainer) and container.patches:
                    self._claim(container, claimed)
                    for patch in container.patches:
                        self._claim(patch, claimed)
                    label = container.get_label()
                    refs.append(
                        ArtistRef(
                            f"Axes {ax_index} / Bar series {container_index}: {label}",
                            self.kind,
                            ("axes", ax_index, "containers", container_index),
                            container,
                        )
                    )
        return refs

    def delete(self, ref: ArtistRef) -> None:
        for patch in list(ref.artist.patches):
            patch.remove()

    def hit_test(self, ref: ArtistRef, event: Any, editor: Any) -> bool:
        return any(self._artist_contains(patch, event) for patch in ref.artist.patches)

    def highlight(self, ref: ArtistRef, editor: Any) -> dict[str, Any]:
        return {
            "kind": ref.kind,
            "patches": [
                self._highlight_artist(patch, linewidth=5, boost_zorder=True)
                for patch in ref.artist.patches
            ],
        }

    def restore_highlight(self, ref: ArtistRef, editor: Any, state: Any) -> None:
        if isinstance(state, dict):
            for patch_state in state.get("patches", []):
                self._restore_artist_highlight(patch_state)

    def build_form(self, ref: ArtistRef, editor: Any) -> bool:
        artist = ref.artist
        first_patch = editor._first_bar_patch(artist)
        if first_patch is None:
            editor.form.addRow(QLabel("This bar series has no patches."))
            return True

        editor._add_bool("Visible", all(patch.get_visible() for patch in artist.patches), lambda v: editor._set_bar_visible(artist, v))
        editor._add_text("Label", artist.get_label(), artist.set_label)
        editor._add_color("Fill color", first_patch.get_facecolor(), lambda v: editor._set_bar_facecolor(artist, v))
        edge_width_widget = None

        def set_border(enabled: bool) -> None:
            width = float(edge_width_widget.value()) if edge_width_widget is not None else float(first_patch.get_linewidth())
            editor._set_bar_linewidth(artist, max(width, 1.0) if enabled else 0.0)

        border = editor._add_bool("Border", first_patch.get_linewidth() > 0, set_border)
        edge_color = editor._add_color("Edge color", first_patch.get_edgecolor(), lambda v: editor._set_bar_edgecolor(artist, v))
        edge_width_widget = editor._add_float("Edge width", first_patch.get_linewidth(), lambda v: editor._set_bar_linewidth(artist, v), 0.0, 20.0, 0.25)
        border.toggled.connect(lambda checked: editor._set_controls_enabled([edge_color, edge_width_widget], checked))
        editor._set_controls_enabled([edge_color, edge_width_widget], border.isChecked())
        editor._add_float("Alpha", first_patch.get_alpha() if first_patch.get_alpha() is not None else 1.0, lambda v: editor._set_bar_alpha(artist, v), 0.0, 1.0, 0.05)
        editor._add_choice("Hatch", first_patch.get_hatch() or "None", ["None", "/", "\\", "|", "-", "+", "x", "o", "O", ".", "*"], lambda v: editor._set_bar_hatch(artist, "" if v == "None" else v))
        editor._add_float("Bar width", abs(first_patch.get_width()), lambda v: editor._set_bar_width(artist, v), 0.01, 10.0, 0.05, decimals=3)
        return True

