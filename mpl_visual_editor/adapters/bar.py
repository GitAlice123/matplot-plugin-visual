"""Bar container adapter."""

from __future__ import annotations

from matplotlib.container import BarContainer
from matplotlib.figure import Figure

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

