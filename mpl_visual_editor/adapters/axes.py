"""Axes adapter."""

from __future__ import annotations

from typing import Any

from matplotlib.figure import Figure
from matplotlib.patches import Rectangle

from ..refs import ArtistRef
from .base import BaseAdapter


class AxesAdapter(BaseAdapter):
    kind = "axes"

    def inspect(self, fig: Figure, claimed: set[int]) -> list[ArtistRef]:
        refs: list[ArtistRef] = []
        for ax_index, ax in enumerate(fig.axes):
            self._claim(ax, claimed)
            self._claim(ax.patch, claimed)
            refs.append(ArtistRef(f"Axes {ax_index}", self.kind, ("axes", ax_index), ax))
        return refs

    def hit_test(self, ref: ArtistRef, event: Any, editor: Any) -> bool:
        return bool(event.inaxes is ref.artist)

    def highlight(self, ref: ArtistRef, editor: Any) -> dict[str, Any]:
        overlay = Rectangle(
            (0, 0),
            1,
            1,
            transform=ref.artist.transAxes,
            fill=False,
            edgecolor="#ffcc00",
            linewidth=2.5,
            linestyle="--",
            zorder=1_000_000,
            clip_on=False,
        )
        ref.artist.add_patch(overlay)
        return {"kind": ref.kind, "overlay": overlay}

    def restore_highlight(self, ref: ArtistRef, editor: Any, state: Any) -> None:
        if isinstance(state, dict) and "overlay" in state:
            self._remove_overlay(state["overlay"], editor)

    def _remove_overlay(self, overlay: Any, editor: Any) -> None:
        try:
            overlay.remove()
        except NotImplementedError:
            if overlay in editor.fig.artists:
                editor.fig.artists.remove(overlay)
            for ax in editor.fig.axes:
                if overlay in ax.patches:
                    ax.patches.remove(overlay)

