"""Line adapter."""

from __future__ import annotations

from typing import Any

from matplotlib.figure import Figure

from ..refs import ArtistRef
from .base import BaseAdapter


class LineAdapter(BaseAdapter):
    kind = "line"

    def inspect(self, fig: Figure, claimed: set[int]) -> list[ArtistRef]:
        refs: list[ArtistRef] = []
        for ax_index, ax in enumerate(fig.axes):
            for line_index, line in enumerate(ax.lines):
                self._claim(line, claimed)
                refs.append(
                    ArtistRef(
                        f"Axes {ax_index} / Line {line_index}: {line.get_label()}",
                        self.kind,
                        ("axes", ax_index, "lines", line_index),
                        line,
                    )
                )
        return refs

    def delete(self, ref: ArtistRef) -> None:
        ref.artist.remove()

    def highlight(self, ref: ArtistRef, editor: Any) -> dict[str, Any]:
        return {"kind": ref.kind, "artist": self._highlight_artist(ref.artist, boost_zorder=True)}

