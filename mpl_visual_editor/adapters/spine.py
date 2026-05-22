"""Spine adapter."""

from __future__ import annotations

from typing import Any

from matplotlib.figure import Figure

from ..refs import ArtistRef
from .base import BaseAdapter


class SpineAdapter(BaseAdapter):
    kind = "spine"

    def inspect(self, fig: Figure, claimed: set[int]) -> list[ArtistRef]:
        refs: list[ArtistRef] = []
        for ax_index, ax in enumerate(fig.axes):
            for spine_name, spine in ax.spines.items():
                self._claim(spine, claimed)
                refs.append(
                    ArtistRef(
                        f"Axes {ax_index} / Spine {spine_name}",
                        self.kind,
                        ("axes", ax_index, "spines", spine_name),
                        spine,
                    )
                )
        return refs

    def delete(self, ref: ArtistRef) -> None:
        ref.artist.set_visible(False)

    def hit_test(self, ref: ArtistRef, event: Any, editor: Any) -> bool:
        if super().hit_test(ref, event, editor):
            return True
        if event.x is None or event.y is None:
            return False
        try:
            bbox = ref.artist.get_window_extent(renderer=editor.canvas.get_renderer()).expanded(1.4, 2.4)
            return bool(bbox.contains(float(event.x), float(event.y)))
        except Exception:
            return False

