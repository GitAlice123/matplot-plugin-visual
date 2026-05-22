"""Axes adapter."""

from __future__ import annotations

from matplotlib.figure import Figure

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

