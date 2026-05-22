"""Base classes for Matplotlib artist adapters."""

from __future__ import annotations

from typing import Any, Protocol

from matplotlib.figure import Figure

from ..refs import ArtistRef


class ArtistAdapter(Protocol):
    """Minimal adapter contract used by the first registry-backed inspector."""

    kind: str

    def inspect(self, fig: Figure, claimed: set[int]) -> list[ArtistRef]:
        """Return refs owned by this adapter and add claimed artist ids."""

    def hit_test(self, ref: ArtistRef, event: Any, editor: Any) -> bool:
        """Return whether a canvas event targets this ref."""

    def highlight(self, ref: ArtistRef, editor: Any) -> Any:
        """Apply a temporary hover highlight and return restore state."""

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

    def inspect(self, fig: Figure, claimed: set[int]) -> list[ArtistRef]:
        return []

    def _claim(self, artist: Any, claimed: set[int]) -> None:
        claimed.add(id(artist))

    def hit_test(self, ref: ArtistRef, event: Any, editor: Any) -> bool:
        return False

    def highlight(self, ref: ArtistRef, editor: Any) -> Any:
        return None

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
