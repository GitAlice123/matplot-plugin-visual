"""Base classes for Matplotlib artist adapters."""

from __future__ import annotations

from typing import Any, Protocol

import matplotlib.patheffects as path_effects
from matplotlib.figure import Figure

from ..refs import ArtistRef


class ArtistAdapter(Protocol):
    """Minimal adapter contract used by the first registry-backed inspector."""

    kind: str
    aliases: tuple[str, ...]

    def inspect(self, fig: Figure, claimed: set[int]) -> list[ArtistRef]:
        """Return refs owned by this adapter and add claimed artist ids."""

    def hit_test(self, ref: ArtistRef, event: Any, editor: Any) -> bool:
        """Return whether a canvas event targets this ref."""

    def highlight(self, ref: ArtistRef, editor: Any) -> Any:
        """Apply a temporary hover highlight and return restore state."""

    def restore_highlight(self, ref: ArtistRef, editor: Any, state: Any) -> None:
        """Restore state returned by ``highlight``."""

    def build_form(self, ref: ArtistRef, editor: Any) -> None:
        """Populate editor controls for this ref."""

    def snapshot(self, ref: ArtistRef) -> dict[str, Any]:
        """Return serializable style properties for this ref."""

    def apply(self, fig: Figure, path: tuple[Any, ...], props: dict[str, Any]) -> None:
        """Replay serialized style properties on a figure."""

    def delete(self, ref: ArtistRef) -> None:
        """Delete or hide this ref when supported."""

    def suggested_adapter(self, artist: Any) -> str:
        """Return a future adapter class name for an unsupported artist."""


class BaseAdapter:
    kind = ""
    aliases: tuple[str, ...] = ()

    def inspect(self, fig: Figure, claimed: set[int]) -> list[ArtistRef]:
        return []

    def _claim(self, artist: Any, claimed: set[int]) -> None:
        claimed.add(id(artist))

    def hit_test(self, ref: ArtistRef, event: Any, editor: Any) -> bool:
        return self._artist_contains(ref.artist, event)

    def _artist_contains(self, artist: Any, event: Any) -> bool:
        if hasattr(artist, "get_visible") and not artist.get_visible():
            return False
        try:
            contains, _details = artist.contains(event)
        except Exception:
            return False
        return bool(contains)

    def highlight(self, ref: ArtistRef, editor: Any) -> Any:
        state: dict[str, Any] = {"kind": ref.kind}
        artist_state = self._highlight_artist(ref.artist)
        if artist_state:
            state["artist"] = artist_state
        return state

    def restore_highlight(self, ref: ArtistRef, editor: Any, state: Any) -> None:
        if isinstance(state, dict) and "artist" in state:
            self._restore_artist_highlight(state["artist"])

    def _highlight_artist(
        self,
        artist: Any,
        linewidth: float = 4,
        foreground: str = "#ffcc00",
        boost_zorder: bool = False,
    ) -> dict[str, Any]:
        state: dict[str, Any] = {"artist": artist}
        if hasattr(artist, "get_path_effects") and hasattr(artist, "set_path_effects"):
            state["path_effects"] = artist.get_path_effects()
            artist.set_path_effects(
                [
                    path_effects.Stroke(linewidth=linewidth, foreground=foreground),
                    path_effects.Normal(),
                ]
            )
        if boost_zorder and hasattr(artist, "get_zorder") and hasattr(artist, "set_zorder"):
            state["zorder"] = artist.get_zorder()
            artist.set_zorder(float(state["zorder"]) + 1000)
        return state

    def _restore_artist_highlight(self, state: dict[str, Any]) -> None:
        artist = state["artist"]
        if "path_effects" in state:
            artist.set_path_effects(state["path_effects"])
        if "zorder" in state:
            artist.set_zorder(state["zorder"])

    def build_form(self, ref: ArtistRef, editor: Any) -> None:
        return None

    def snapshot(self, ref: ArtistRef) -> dict[str, Any]:
        return {}

    def apply(self, fig: Figure, path: tuple[Any, ...], props: dict[str, Any]) -> None:
        return None

    def delete(self, ref: ArtistRef) -> None:
        raise ValueError(f"Delete is not supported for {self.kind!r}")

    def suggested_adapter(self, artist: Any) -> str:
        return f"{type(artist).__name__}Adapter"
