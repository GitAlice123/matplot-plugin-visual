"""Spine adapter."""

from __future__ import annotations

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

