"""Bar container adapter."""

from __future__ import annotations

from typing import Any

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

    def delete(self, ref: ArtistRef) -> None:
        for patch in list(ref.artist.patches):
            patch.remove()

    def hit_test(self, ref: ArtistRef, event: Any, editor: Any) -> bool:
        return any(self._artist_contains(patch, event) for patch in ref.artist.patches)

    def highlight(self, ref: ArtistRef, editor: Any) -> dict[str, Any]:
        return {
            "kind": ref.kind,
            "patches": [
                self._highlight_artist(patch, linewidth=5, boost_zorder=True)
                for patch in ref.artist.patches
            ],
        }

    def restore_highlight(self, ref: ArtistRef, editor: Any, state: Any) -> None:
        if isinstance(state, dict):
            for patch_state in state.get("patches", []):
                self._restore_artist_highlight(patch_state)

