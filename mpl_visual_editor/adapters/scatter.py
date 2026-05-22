"""Scatter/path collection adapter."""

from __future__ import annotations

from typing import Any

from matplotlib.collections import PathCollection
from matplotlib.figure import Figure

from ..refs import ArtistRef
from .base import BaseAdapter


class ScatterAdapter(BaseAdapter):
    kind = "scatter"

    def inspect(self, fig: Figure, claimed: set[int]) -> list[ArtistRef]:
        refs: list[ArtistRef] = []
        for ax_index, ax in enumerate(fig.axes):
            for collection_index, collection in enumerate(ax.collections):
                if not isinstance(collection, PathCollection):
                    continue
                self._claim(collection, claimed)
                refs.append(
                    ArtistRef(
                        f"Axes {ax_index} / Scatter {collection_index}: {collection.get_label()}",
                        self.kind,
                        ("axes", ax_index, "collections", collection_index),
                        collection,
                    )
                )
        return refs

    def delete(self, ref: ArtistRef) -> None:
        ref.artist.remove()

    def highlight(self, ref: ArtistRef, editor: Any) -> dict[str, Any]:
        return {"kind": ref.kind, "artist": self._highlight_artist(ref.artist, linewidth=5, boost_zorder=True)}

    def build_form(self, ref: ArtistRef, editor: Any) -> bool:
        artist = ref.artist
        editor._add_bool("Visible", artist.get_visible(), artist.set_visible)
        editor._add_text("Label", artist.get_label(), artist.set_label)
        editor._add_color("Fill color", self._first_color(artist.get_facecolors()), artist.set_facecolor)
        editor._add_color("Edge color", self._first_color(artist.get_edgecolors()), artist.set_edgecolor)
        editor._add_float("Edge width", self._first_float(artist.get_linewidths(), 1.0), artist.set_linewidth, 0.0, 20.0, 0.25)
        editor._add_float("Marker area", self._first_float(artist.get_sizes(), 36.0), lambda v: self._set_sizes(artist, v), 0.1, 2000.0, 1.0)
        editor._add_float("Alpha", artist.get_alpha() if artist.get_alpha() is not None else 1.0, artist.set_alpha, 0.0, 1.0, 0.05)
        return True

    def _set_sizes(self, artist: Any, value: float) -> None:
        count = len(artist.get_offsets())
        artist.set_sizes([float(value)] * max(1, count))

    def _first_color(self, colors: Any) -> str:
        if colors is None or len(colors) == 0:
            return "#000000"
        from matplotlib.colors import to_hex

        return to_hex(colors[0], keep_alpha=False)

    def _first_float(self, values: Any, default: float) -> float:
        if values is None or len(values) == 0:
            return float(default)
        return float(values[0])
