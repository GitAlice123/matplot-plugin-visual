"""A tiny visual style editor for existing Matplotlib figures."""

from .workflow import (
    StyleRunResult,
    apply_style_patch,
    default_figure_path,
    resolve_style_path,
    style_figure,
)


def edit(*args, **kwargs):
    """Open the editor.

    The GUI import is intentionally lazy so non-GUI helpers such as the exporter
    can be imported in environments where Qt is not installed yet.
    """

    try:
        from .editor import edit as _edit
    except ImportError as exc:
        raise ImportError(
            "mpl_visual_editor.edit() requires a Qt binding. "
            "Install dependencies with: pip install -r requirements.txt"
        ) from exc

    return _edit(*args, **kwargs)

__all__ = [
    "StyleRunResult",
    "apply_style_patch",
    "default_figure_path",
    "edit",
    "resolve_style_path",
    "style_figure",
]
