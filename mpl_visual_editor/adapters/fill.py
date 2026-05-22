"""PolyCollection/fill region adapter."""

from __future__ import annotations

from typing import Any

from matplotlib.collections import PathCollection, PolyCollection
from matplotlib.figure import Figure

from ..fills import apply_fill_props, fill_props
from ..refs import ArtistRef
from .base import BaseAdapter


class FillAdapter(BaseAdapter):
    kind = "fill"

    def inspect(self, fig: Figure, claimed: set[int]) -> list[ArtistRef]:
        refs: list[ArtistRef] = []
        for ax_index, ax in enumerate(fig.axes):
            for collection_index, collection in enumerate(ax.collections):
                if isinstance(collection, PathCollection) or not isinstance(collection, PolyCollection):
                    continue
                self._claim(collection, claimed)
                label = "Fill region" if getattr(collection, "_mve_kind", None) == "fill" else "PolyCollection"
                refs.append(
                    ArtistRef(
                        f"Axes {ax_index} / {label} {collection_index}",
                        self.kind,
                        ("axes", ax_index, "collections", collection_index),
                        collection,
                    )
                )
        return refs

    def delete(self, ref: ArtistRef) -> None:
        ref.artist.remove()

    def highlight(self, ref: ArtistRef, editor: Any) -> dict[str, Any]:
        return {"kind": ref.kind, "artist": self._highlight_artist(ref.artist, linewidth=4, boost_zorder=True)}

    def build_form(self, ref: ArtistRef, editor: Any) -> bool:
        artist = ref.artist
        props = fill_props(artist)
        editor._add_bool("Visible", props["visible"], lambda v: self._set_fill(artist, visible=v))
        if props.get("editable_geometry"):
            editor._add_float("X", props["x"], lambda v: self._set_fill(artist, x=v), -1e12, 1e12, 0.1, decimals=4)
            editor._add_float("Y", props["y"], lambda v: self._set_fill(artist, y=v), -1e12, 1e12, 0.1, decimals=4)
            editor._add_float("Width", props["width"], lambda v: self._set_fill(artist, width=v), 1e-12, 1e12, 0.1, decimals=4)
            editor._add_float("Height", props["height"], lambda v: self._set_fill(artist, height=v), 1e-12, 1e12, 0.1, decimals=4)
        editor._add_color("Fill color", props["facecolor"], lambda v: self._set_fill(artist, facecolor=v))
        editor._add_color("Edge color", props["edgecolor"], lambda v: self._set_fill(artist, edgecolor=v))
        editor._add_float("Edge width", props["linewidth"], lambda v: self._set_fill(artist, linewidth=v), 0.0, 50.0, 0.25)
        editor._add_float("Alpha", props["alpha"] if props["alpha"] is not None else 0.18, lambda v: self._set_fill(artist, alpha=v), 0.0, 1.0, 0.05)
        return True

    def _set_fill(self, artist: Any, **changes: Any) -> None:
        props = fill_props(artist)
        props.update(changes)
        apply_fill_props(artist.axes, props, artist)
