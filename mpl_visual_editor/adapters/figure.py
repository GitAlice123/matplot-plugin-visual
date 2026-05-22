"""Figure adapter."""

from __future__ import annotations

from matplotlib.figure import Figure

from ..refs import ArtistRef
from .base import BaseAdapter


class FigureAdapter(BaseAdapter):
    kind = "figure"

    def inspect(self, fig: Figure, claimed: set[int]) -> list[ArtistRef]:
        self._claim(fig, claimed)
        return [ArtistRef("Figure", self.kind, ("figure",), fig)]

