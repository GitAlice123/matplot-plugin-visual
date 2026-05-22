"""Legend adapter."""

from __future__ import annotations

from matplotlib.figure import Figure

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

