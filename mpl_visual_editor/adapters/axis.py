"""X/Y axis adapter."""

from __future__ import annotations

from matplotlib.figure import Figure

from ..refs import ArtistRef
from .base import BaseAdapter


class AxisAdapter(BaseAdapter):
    kind = "axis"

    def inspect(self, fig: Figure, claimed: set[int]) -> list[ArtistRef]:
        refs: list[ArtistRef] = []
        for ax_index, ax in enumerate(fig.axes):
            for name, axis in [("X axis", ax.xaxis), ("Y axis", ax.yaxis)]:
                path_name = "xaxis" if name.startswith("X") else "yaxis"
                self._claim(axis, claimed)
                refs.append(
                    ArtistRef(
                        f"Axes {ax_index} / {name}",
                        self.kind,
                        ("axes", ax_index, path_name),
                        axis,
                    )
                )
        return refs

