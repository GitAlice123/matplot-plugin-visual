"""Editor-created shape and text box adapter."""

from __future__ import annotations

from typing import Any

from matplotlib.figure import Figure

from ..refs import ArtistRef
from ..shapes import apply_shape_props, apply_textbox_props, shape_props, textbox_props
from .base import BaseAdapter


class ShapeAdapter(BaseAdapter):
    kind = "shape"
    aliases = ("textbox",)

    def inspect(self, fig: Figure, claimed: set[int]) -> list[ArtistRef]:
        refs: list[ArtistRef] = []
        for ax_index, ax in enumerate(fig.axes):
            for patch in ax.patches:
                if getattr(patch, "_mve_kind", None) != "shape":
                    continue
                self._claim(patch, claimed)
                refs.append(
                    ArtistRef(
                        f"Axes {ax_index} / Shape: {getattr(patch, '_mve_shape_type', 'shape')}",
                        "shape",
                        ("axes", ax_index, "mve_shapes", getattr(patch, "_mve_id", "")),
                        patch,
                    )
                )
            for text in ax.texts:
                if getattr(text, "_mve_kind", None) != "textbox":
                    continue
                self._claim(text, claimed)
                label = text.get_text().replace("\n", " ")
                suffix = f": {label}" if label else ""
                refs.append(
                    ArtistRef(
                        f"Axes {ax_index} / Text box{suffix}",
                        "textbox",
                        ("axes", ax_index, "mve_textboxes", getattr(text, "_mve_id", "")),
                        text,
                    )
                )
        return refs

    def delete(self, ref: ArtistRef) -> None:
        ref.artist.remove()

    def highlight(self, ref: ArtistRef, editor: Any) -> dict[str, Any]:
        return {"kind": ref.kind, "artist": self._highlight_artist(ref.artist, linewidth=4, boost_zorder=True)}

    def build_form(self, ref: ArtistRef, editor: Any) -> bool:
        if ref.kind == "textbox":
            self._build_textbox_form(ref, editor)
            return True
        self._build_shape_form(ref, editor)
        return True

    def _build_shape_form(self, ref: ArtistRef, editor: Any) -> None:
        artist = ref.artist
        props = shape_props(artist)
        shape_type = props.get("type", "rectangle")
        editor._add_bool("Visible", props["visible"], lambda v: self._set_shape(artist, visible=v))
        editor._add_float("X", props["x"], lambda v: self._set_shape(artist, x=v), -1e12, 1e12, 0.1, decimals=4)
        editor._add_float("Y", props["y"], lambda v: self._set_shape(artist, y=v), -1e12, 1e12, 0.1, decimals=4)
        if shape_type in {"line", "arrow"}:
            editor._add_float("Length", props["width"], lambda v: self._set_shape(artist, width=v), 1e-12, 1e12, 0.1, decimals=4)
            editor._add_float("Angle", props["angle"], lambda v: self._set_shape(artist, angle=v), -360.0, 360.0, 1.0)
            editor._add_color("Color", props["edgecolor"], lambda v: self._set_shape(artist, edgecolor=v))
            editor._add_float("Line width", props["linewidth"], lambda v: self._set_shape(artist, linewidth=v), 0.0, 50.0, 0.25)
            if shape_type == "arrow":
                editor._add_float("Head size", props["mutation_scale"], lambda v: self._set_shape(artist, mutation_scale=v), 1.0, 200.0, 1.0)
        else:
            editor._add_float("Width", props["width"], lambda v: self._set_shape(artist, width=v), 1e-12, 1e12, 0.1, decimals=4)
            editor._add_float("Height", props["height"], lambda v: self._set_shape(artist, height=v), 1e-12, 1e12, 0.1, decimals=4)
            editor._add_float("Angle", props["angle"], lambda v: self._set_shape(artist, angle=v), -360.0, 360.0, 1.0)
            editor._add_color("Fill color", props["facecolor"], lambda v: self._set_shape(artist, facecolor=v))
            editor._add_color("Edge color", props["edgecolor"], lambda v: self._set_shape(artist, edgecolor=v))
            editor._add_float("Line width", props["linewidth"], lambda v: self._set_shape(artist, linewidth=v), 0.0, 50.0, 0.25)
        editor._add_float("Alpha", props["alpha"] if props["alpha"] is not None else 1.0, lambda v: self._set_shape(artist, alpha=v), 0.0, 1.0, 0.05)
        editor._add_position_save_button("Save placement")

    def _build_textbox_form(self, ref: ArtistRef, editor: Any) -> None:
        artist = ref.artist
        props = textbox_props(artist)
        editor._add_bool("Visible", props["visible"], lambda v: self._set_textbox(artist, visible=v))
        editor._add_text("Text", props["text"], lambda v: self._set_textbox(artist, text=v))
        editor._add_float("X", props["x"], lambda v: self._set_textbox(artist, x=v), -1e12, 1e12, 0.1, decimals=4)
        editor._add_float("Y", props["y"], lambda v: self._set_textbox(artist, y=v), -1e12, 1e12, 0.1, decimals=4)
        editor._add_float("Rotation", props["rotation"], lambda v: self._set_textbox(artist, rotation=v), -360.0, 360.0, 1.0)
        editor._add_color("Text color", props["color"], lambda v: self._set_textbox(artist, color=v))
        editor._add_float("Font size", props["fontsize"], lambda v: self._set_textbox(artist, fontsize=v), 1.0, 160.0, 1.0)
        editor._add_choice("Weight", props["fontweight"], ["normal", "bold", "light", "semibold", "heavy"], lambda v: self._set_textbox(artist, fontweight=v))
        editor._add_choice("Style", props["fontstyle"], ["normal", "italic", "oblique"], lambda v: self._set_textbox(artist, fontstyle=v))
        editor._add_color("Box fill", props["facecolor"], lambda v: self._set_textbox(artist, facecolor=v))
        editor._add_color("Box edge", props["edgecolor"], lambda v: self._set_textbox(artist, edgecolor=v))
        editor._add_float("Box alpha", props["box_alpha"] if props["box_alpha"] is not None else 0.85, lambda v: self._set_textbox(artist, box_alpha=v), 0.0, 1.0, 0.05)
        editor._add_position_save_button("Save placement")

    def _set_shape(self, artist: Any, **changes: Any) -> None:
        props = shape_props(artist)
        props.update(changes)
        apply_shape_props(artist.axes, props, artist)

    def _set_textbox(self, artist: Any, **changes: Any) -> None:
        props = textbox_props(artist)
        props.update(changes)
        apply_textbox_props(artist.axes, props, artist)
