"""Convenience workflow helpers for plot scripts using mpl_visual_editor."""

from __future__ import annotations

import importlib.util
import inspect
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from matplotlib.figure import Figure

StyleMode = Literal["edit", "apply", "off"]


@dataclass(frozen=True)
class StyleRunResult:
    """Result returned by :func:`style_figure`."""

    style_path: Path
    figure_path: Path | None
    style_applied: bool
    figure_saved: bool


def style_figure(
    fig: Figure,
    *,
    mode: StyleMode = "edit",
    enabled: bool = True,
    name: str | None = None,
    source_path: str | Path | None = None,
    style_path: str | Path | None = None,
    style_dir: str | Path = "styles",
    save_path: str | Path | None = None,
    save: bool = False,
    save_kwargs: dict[str, Any] | None = None,
    apply_existing: bool = True,
) -> StyleRunResult:
    """Run the common edit/apply/off style workflow for a Matplotlib figure.

    ``mode="edit"`` opens the visual editor and exports to ``style_path``.
    ``mode="apply"`` applies an existing patch without opening Qt.
    ``mode="off"`` leaves the figure untouched. If ``enabled`` is false, style
    processing is skipped but optional saving still happens.
    """

    if mode not in {"edit", "apply", "off"}:
        raise ValueError('mode must be "edit", "apply", or "off"')

    source = (
        Path(source_path).resolve()
        if source_path is not None
        else _infer_calling_script()
    )
    resolved_style_path = resolve_style_path(
        name=name,
        source_path=source,
        style_path=style_path,
        style_dir=style_dir,
    )

    style_applied = False
    if enabled and mode == "edit":
        from .editor import edit

        edit(
            fig,
            export_path=resolved_style_path,
            apply_existing=apply_existing,
            source_path=source,
        )
        style_applied = True
    elif enabled and mode == "apply":
        style_applied = apply_style_patch(fig, resolved_style_path)

    resolved_save_path = Path(save_path) if save_path is not None else None
    figure_saved = False
    if save or resolved_save_path is not None:
        if resolved_save_path is None:
            resolved_save_path = default_figure_path(name=name, source_path=source)
        resolved_save_path.parent.mkdir(parents=True, exist_ok=True)
        kwargs = {"bbox_inches": "tight", "dpi": 300}
        if save_kwargs:
            kwargs.update(save_kwargs)
        fig.savefig(resolved_save_path, **kwargs)
        figure_saved = True

    return StyleRunResult(
        style_path=resolved_style_path,
        figure_path=resolved_save_path,
        style_applied=style_applied,
        figure_saved=figure_saved,
    )


def resolve_style_path(
    *,
    name: str | None = None,
    source_path: str | Path | None = None,
    style_path: str | Path | None = None,
    style_dir: str | Path = "styles",
) -> Path:
    """Resolve the patch path used by plot scripts."""

    if style_path is not None:
        return Path(style_path)
    stem = _style_stem(name=name, source_path=source_path)
    return Path(style_dir) / f"{stem}_style_patch.py"


def default_figure_path(
    *,
    name: str | None = None,
    source_path: str | Path | None = None,
    figure_dir: str | Path = "figures",
    suffix: str = ".pdf",
) -> Path:
    """Return the conventional figure export path for a styled plot."""

    if not suffix.startswith("."):
        suffix = f".{suffix}"
    return Path(figure_dir) / f"{_style_stem(name=name, source_path=source_path)}{suffix}"


def apply_style_patch(
    fig: Figure,
    style_path: str | Path,
    *,
    missing: Literal["warn", "ignore", "error"] = "warn",
) -> bool:
    """Apply a generated style patch to ``fig``.

    Returns true when a patch was found and applied.
    """

    path = Path(style_path)
    if not path.exists():
        if missing == "error":
            raise FileNotFoundError(path)
        if missing == "warn":
            print(f"[mpl_visual_editor] style patch not found, skip: {path}")
        return False

    module_name = f"_mpl_visual_editor_style_patch_{abs(hash(path.resolve()))}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load style patch: {path}")

    module = importlib.util.module_from_spec(spec)
    try:
        import numpy as np

        module.np = np
    except ImportError:
        pass
    spec.loader.exec_module(module)

    apply_style = getattr(module, "apply_style", None)
    if not callable(apply_style):
        raise RuntimeError(f"{path} does not define apply_style(fig)")
    _sanitize_legacy_axis_patches(module)
    _patch_style_module_helpers(module)
    apply_style(fig)
    return True


def _patch_style_module_helpers(module: Any) -> None:
    try:
        from .exporter import _legend_handles_from_specs
    except Exception:
        return
    _repair_scatter_legend_handle_specs(module)
    module._legend_handles_from_specs = _legend_handles_from_specs


def _repair_scatter_legend_handle_specs(module: Any) -> None:
    patches = getattr(module, "STYLE_PATCHES", None)
    if not isinstance(patches, list):
        return
    scatter_props_by_label = {
        patch.get("props", {}).get("label"): patch.get("props", {})
        for patch in patches
        if isinstance(patch, dict) and patch.get("kind") == "scatter"
    }
    for patch in patches:
        if not isinstance(patch, dict) or patch.get("kind") != "legend":
            continue
        props = patch.get("props")
        if not isinstance(props, dict):
            continue
        handle_specs = props.get("handle_specs")
        if not isinstance(handle_specs, list):
            continue
        for spec in handle_specs:
            if not isinstance(spec, dict) or spec.get("kind") != "line":
                continue
            marker = spec.get("marker")
            label = spec.get("label")
            scatter_props = scatter_props_by_label.get(label)
            if marker in {None, "None", "none", ""} or not scatter_props:
                continue
            spec.clear()
            spec.update(
                {
                    "kind": "scatter",
                    "label": label,
                    "facecolor": scatter_props.get("facecolor"),
                    "edgecolor": scatter_props.get("edgecolor"),
                    "linewidth": scatter_props.get("linewidth", 1.0),
                    "size": scatter_props.get("size", 36.0),
                    "alpha": scatter_props.get("alpha"),
                    "marker": marker,
                    "path": None,
                }
            )


def _style_stem(*, name: str | None, source_path: str | Path | None) -> str:
    if name:
        return name
    if source_path is not None:
        return Path(source_path).stem
    return "style"


def _infer_calling_script() -> Path | None:
    this_file = Path(__file__).resolve()
    package_init = this_file.with_name("__init__.py")
    for frame in inspect.stack()[1:]:
        filename = frame.filename
        if not filename or filename.startswith("<"):
            continue
        path = Path(filename).resolve()
        if path in {this_file, package_init}:
            continue
        if path.exists():
            return path
    return None


def _sanitize_legacy_axis_patches(module: Any) -> None:
    patches = getattr(module, "STYLE_PATCHES", None)
    if not isinstance(patches, list):
        return
    sanitized_patches = []
    has_legacy_axis_ticks = False
    has_legacy_axis_labels = False
    for patch in patches:
        if isinstance(patch, dict) and patch.get("kind") == "axes":
            props = patch.get("props")
            if isinstance(props, dict):
                props.pop("position", None)
            sanitized_patches.append(patch)
            continue
        if not isinstance(patch, dict) or patch.get("kind") != "axis":
            sanitized_patches.append(patch)
            continue
        props = patch.get("props")
        if not isinstance(props, dict):
            sanitized_patches.append(patch)
            continue
        is_legacy_axis_patch = (
            "ticks_explicit" not in props
            and "tick_labels_explicit" not in props
            and "scale_explicit" not in props
        )
        if is_legacy_axis_patch:
            continue
        sanitized_patches.append(patch)
        if "ticks_explicit" not in props:
            has_legacy_axis_ticks = True
        if "tick_labels_explicit" not in props:
            has_legacy_axis_labels = True
    module.STYLE_PATCHES = sanitized_patches
    if has_legacy_axis_ticks:
        module._apply_axis_ticks = lambda *args, **kwargs: None
    if has_legacy_axis_labels:
        module._apply_axis_tick_labels = lambda *args, **kwargs: None
