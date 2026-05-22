"""Text adapter, including titles, axis labels, and ordinary ``ax.text`` labels."""

from __future__ import annotations

from typing import Any

from matplotlib.figure import Figure

from ..refs import ArtistRef
from .base import BaseAdapter


class TextAdapter(BaseAdapter):
    kind = "text"
    aliases = ("text_group",)

    def inspect(self, fig: Figure, claimed: set[int]) -> list[ArtistRef]:
        refs: list[ArtistRef] = []
        for ax_index, ax in enumerate(fig.axes):
            fixed_texts = [
                (f"Axes {ax_index} / Title", ("axes", ax_index, "title"), ax.title),
                (f"Axes {ax_index} / X label", ("axes", ax_index, "xlabel"), ax.xaxis.label),
                (f"Axes {ax_index} / Y label", ("axes", ax_index, "ylabel"), ax.yaxis.label),
            ]
            for label, path, text in fixed_texts:
                self._claim(text, claimed)
                refs.append(ArtistRef(label, self.kind, path, text))

            for text_index, text in enumerate(ax.texts):
                self._claim(text, claimed)
                value = text.get_text()
                suffix = f": {value}" if value else ""
                refs.append(
                    ArtistRef(
                        f"Axes {ax_index} / Text {text_index}{suffix}",
                        self.kind,
                        ("axes", ax_index, "texts", text_index),
                        text,
                    )
                )
            if ax.texts:
                refs.append(
                    ArtistRef(
                        f"Axes {ax_index} / Text group ({len(ax.texts)})",
                        "text_group",
                        ("axes", ax_index, "texts_group"),
                        tuple(ax.texts),
                    )
                )
        return refs

    def delete(self, ref: ArtistRef) -> None:
        if ref.kind == "text_group":
            for text in ref.artist:
                text.set_text("")
            return
        ref.artist.set_text("")

    def hit_test(self, ref: ArtistRef, event: Any, editor: Any) -> bool:
        if ref.kind == "text_group":
            return any(self._artist_contains(text, event) for text in ref.artist)
        return super().hit_test(ref, event, editor)

    def highlight(self, ref: ArtistRef, editor: Any) -> dict[str, Any]:
        if ref.kind == "text_group":
            return {
                "kind": ref.kind,
                "texts": [self._highlight_artist(text, boost_zorder=True) for text in ref.artist],
            }
        return super().highlight(ref, editor)

    def restore_highlight(self, ref: ArtistRef, editor: Any, state: Any) -> None:
        if ref.kind == "text_group" and isinstance(state, dict):
            for text_state in state.get("texts", []):
                self._restore_artist_highlight(text_state)
            return
        super().restore_highlight(ref, editor, state)
