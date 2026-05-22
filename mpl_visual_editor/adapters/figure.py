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

    def build_form(self, ref: ArtistRef, editor: object) -> bool:
        width, height = editor._figure_size()
        editor._add_float("Width inches", width, lambda v: editor._set_figure_size(width=v), 1.0, 30.0, 0.25)
        editor._add_float("Height inches", height, lambda v: editor._set_figure_size(height=v), 1.0, 30.0, 0.25)
        aspect = float(width / height) if height else 1.0
        editor._add_float("Aspect ratio", aspect, editor._set_figure_aspect, 0.1, 10.0, 0.05, decimals=3)
        return True

