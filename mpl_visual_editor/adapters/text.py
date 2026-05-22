"""Text adapter, including titles, axis labels, and ordinary ``ax.text`` labels."""

from __future__ import annotations

from typing import Any

from matplotlib.figure import Figure
from PySide6.QtWidgets import QLabel

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

            editable_texts = [text for text in ax.texts if id(text) not in claimed]
            for text_index, text in enumerate(editable_texts):
                if id(text) in claimed:
                    continue
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
            if editable_texts:
                refs.append(
                    ArtistRef(
                        f"Axes {ax_index} / Text group ({len(editable_texts)})",
                        "text_group",
                        ("axes", ax_index, "texts_group"),
                        tuple(editable_texts),
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

    def build_form(self, ref: ArtistRef, editor: Any) -> bool:
        if ref.kind == "text_group":
            first_text = editor._first_text_in_group(ref.artist)
            if first_text is None:
                editor.form.addRow(QLabel("This text group is empty."))
                return True
            editor.form.addRow(QLabel(f"{len(ref.artist)} text artists will be updated together."))
            editor._add_color("Color", first_text.get_color(), lambda v: editor._set_text_group_color(ref.artist, v))
            editor._add_float("Font size", first_text.get_fontsize(), lambda v: editor._set_text_group_fontsize(ref.artist, v), 1.0, 160.0, 1.0)
            editor._add_choice("Weight", first_text.get_fontweight(), ["normal", "bold", "light", "semibold", "heavy"], lambda v: editor._set_text_group_fontweight(ref.artist, v))
            editor._add_choice("Style", first_text.get_fontstyle(), ["normal", "italic", "oblique"], lambda v: editor._set_text_group_fontstyle(ref.artist, v))
            return True

        artist = ref.artist
        editor._add_text("Text", artist.get_text(), artist.set_text)
        x, y = artist.get_position()
        editor._add_float("X", float(x), lambda v: editor._set_text_position(artist, x=v), -1e12, 1e12, 0.1, decimals=4)
        editor._add_float("Y", float(y), lambda v: editor._set_text_position(artist, y=v), -1e12, 1e12, 0.1, decimals=4)
        editor._add_float("Rotation", float(artist.get_rotation()), artist.set_rotation, -360.0, 360.0, 1.0)
        editor._add_color("Color", artist.get_color(), artist.set_color)
        editor._add_float("Font size", artist.get_fontsize(), artist.set_fontsize, 1.0, 96.0, 1.0)
        editor._add_choice("Weight", artist.get_fontweight(), ["normal", "bold", "light", "semibold", "heavy"], artist.set_fontweight)
        editor._add_choice("Style", artist.get_fontstyle(), ["normal", "italic", "oblique"], artist.set_fontstyle)
        editor._add_position_save_button("Save position")
        return True
