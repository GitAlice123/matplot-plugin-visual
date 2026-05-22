"""Detection adapter for visible artists that are not editable yet."""

from __future__ import annotations

from typing import Any

from matplotlib.axis import Axis
from matplotlib.container import Container
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle
from matplotlib.text import Text
from PySide6.QtWidgets import QLabel

from ..refs import ArtistRef
from .base import BaseAdapter


class UnsupportedAdapter(BaseAdapter):
    kind = "unsupported"

    def inspect(self, fig: Figure, claimed: set[int]) -> list[ArtistRef]:
        refs: list[ArtistRef] = []
        for ax_index, ax in enumerate(fig.axes):
            unsupported_index = 0
            for artist in ax.get_children():
                if not self._should_report(artist, claimed):
                    continue
                type_name = type(artist).__name__
                refs.append(
                    ArtistRef(
                        f"Axes {ax_index} / Unsupported: {type_name}",
                        self.kind,
                        ("axes", ax_index, "unsupported", unsupported_index, type_name),
                        artist,
                    )
                )
                claimed.add(id(artist))
                unsupported_index += 1
        return refs

    def _should_report(self, artist: Any, claimed: set[int]) -> bool:
        if getattr(artist, "_mve_kind", None) == "editor_handle":
            return False
        if id(artist) in claimed:
            return False
        if isinstance(artist, (Axis, Container)):
            return False
        if isinstance(artist, Rectangle) and getattr(artist, "axes", None) is not None:
            return False
        if isinstance(artist, Text) and not artist.get_text():
            return False
        if hasattr(artist, "get_visible") and not artist.get_visible():
            return False
        return True

    def suggested_adapter(self, artist: Any) -> str:
        name = type(artist).__name__
        suggestions = {
            "PathCollection": "ScatterAdapter",
            "QuadMesh": "MeshAdapter",
            "PolyCollection": "CollectionAdapter",
            "LineCollection": "CollectionAdapter",
            "FancyArrowPatch": "ArrowAdapter",
            "Annotation": "AnnotationAdapter",
            "ErrorbarContainer": "ErrorbarAdapter",
            "Wedge": "WedgeAdapter",
            "PathPatch": "PatchAdapter",
        }
        return suggestions.get(name, f"{name}Adapter")

    def build_form(self, ref: ArtistRef, editor: Any) -> bool:
        artist = ref.artist
        editor.form.addRow(QLabel("This artist is detected but not editable yet."))
        editor.form.addRow("Artist type", QLabel(type(artist).__name__))
        editor.form.addRow("Editable", QLabel("No"))
        editor.form.addRow("Reason", QLabel("no adapter registered"))
        editor.form.addRow("Suggested adapter", QLabel(self.suggested_adapter(artist)))
        return True
