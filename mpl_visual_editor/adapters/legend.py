"""Legend adapter."""

from __future__ import annotations

from typing import Any

from matplotlib.figure import Figure
from matplotlib.patches import Rectangle

from ..refs import ArtistRef
from .base import BaseAdapter


class LegendAdapter(BaseAdapter):
    kind = "legend"

    def inspect(self, fig: Figure, claimed: set[int]) -> list[ArtistRef]:
        refs: list[ArtistRef] = []
        for ax_index, ax in enumerate(fig.axes):
            legend = ax.get_legend()
            if legend is not None:
                self._claim(legend, claimed)
                self._claim(legend.get_frame(), claimed)
                for text in legend.get_texts():
                    self._claim(text, claimed)
                refs.append(
                    ArtistRef(
                        f"Axes {ax_index} / Legend",
                        self.kind,
                        ("axes", ax_index, "legend"),
                        legend,
                    )
                )
        return refs

    def delete(self, ref: ArtistRef) -> None:
        ref.artist.remove()

    def hit_test(self, ref: ArtistRef, event: Any, editor: Any) -> bool:
        if event.x is None or event.y is None:
            return False
        if hasattr(ref.artist, "get_visible") and not ref.artist.get_visible():
            return False
        renderer = editor.canvas.get_renderer()
        bbox = ref.artist.get_window_extent(renderer=renderer)
        return bool(bbox.contains(float(event.x), float(event.y)))

    def highlight(self, ref: ArtistRef, editor: Any) -> dict[str, Any]:
        renderer = editor.canvas.get_renderer()
        bbox = ref.artist.get_window_extent(renderer=renderer).transformed(ref.artist.axes.transAxes.inverted())
        overlay = Rectangle(
            (bbox.x0, bbox.y0),
            bbox.width,
            bbox.height,
            transform=ref.artist.axes.transAxes,
            fill=False,
            edgecolor="#ffcc00",
            linewidth=2.5,
            linestyle="--",
            zorder=1_000_000,
            clip_on=False,
        )
        ref.artist.axes.add_patch(overlay)
        return {"kind": ref.kind, "overlay": overlay}

    def restore_highlight(self, ref: ArtistRef, editor: Any, state: Any) -> None:
        if isinstance(state, dict) and "overlay" in state:
            try:
                state["overlay"].remove()
            except Exception:
                pass

    def build_form(self, ref: ArtistRef, editor: Any) -> bool:
        artist = ref.artist
        editor._ensure_legend_axes_anchor(artist)
        artist.set_draggable(True, use_blit=False, update="bbox")
        frame = artist.get_frame()
        texts = artist.get_texts()
        fontsize = texts[0].get_fontsize() if texts else 10

        def set_frame_visible(visible: bool) -> None:
            artist.set_frame_on(bool(visible))
            frame.set_visible(bool(visible))

        frame_on = artist.get_frame_on() if hasattr(artist, "get_frame_on") else frame.get_visible()
        editor._add_bool("Visible", artist.get_visible(), artist.set_visible)
        editor._add_float("Font size", fontsize, lambda v: editor._rebuild_current_legend(fontsize=v), 1.0, 96.0, 1.0)
        editor._add_bool("Frame", frame_on, set_frame_visible)
        editor._add_float("Frame alpha", frame.get_alpha() if frame.get_alpha() is not None else 1.0, frame.set_alpha, 0.0, 1.0, 0.05)
        editor._add_color("Face color", frame.get_facecolor(), frame.set_facecolor)
        edge_width_widget = None

        def set_frame_border(enabled: bool) -> None:
            width = float(edge_width_widget.value()) if edge_width_widget is not None else float(frame.get_linewidth())
            frame.set_linewidth(max(width, 1.0) if enabled else 0.0)

        frame_border = editor._add_bool("Frame border", frame.get_linewidth() > 0, set_frame_border)
        edge_color = editor._add_color("Edge color", frame.get_edgecolor(), frame.set_edgecolor)
        edge_width_widget = editor._add_float("Edge width", frame.get_linewidth(), frame.set_linewidth, 0.0, 20.0, 0.25)
        frame_border.toggled.connect(lambda checked: editor._set_controls_enabled([edge_color, edge_width_widget], checked))
        editor._set_controls_enabled([edge_color, edge_width_widget], frame_border.isChecked())
        editor._add_position_save_button()
        editor._add_float("Border pad", artist.borderpad, lambda v: editor._rebuild_current_legend(borderpad=v), 0.0, 5.0, 0.1)
        editor._add_float("Label spacing", artist.labelspacing, lambda v: editor._rebuild_current_legend(labelspacing=v), 0.0, 5.0, 0.1)
        editor._add_float("Handle length", artist.handlelength, lambda v: editor._rebuild_current_legend(handlelength=v), 0.0, 8.0, 0.1)
        editor._add_float("Handle text pad", artist.handletextpad, lambda v: editor._rebuild_current_legend(handletextpad=v), 0.0, 5.0, 0.1)
        return True

