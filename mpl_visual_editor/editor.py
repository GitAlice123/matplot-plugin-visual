"""PySide6 editor window for Matplotlib figures."""

from __future__ import annotations

import copy
import inspect
import importlib.util
import math
import sys
import warnings
from pathlib import Path
from typing import Any, Callable, Optional, Union

import matplotlib

matplotlib.use("QtAgg")

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from matplotlib.markers import MarkerStyle
from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QIcon, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from .exporter import export_style
from .adapters.registry import get_adapter
from .adapters.arrow import apply_arrow_props, arrow_props
from .fills import apply_fill_props
from .inspector import iter_artist_refs
from .refs import ArtistRef
from .snapshots import snapshot_artist
from .shapes import (
    LINE_SHAPE_TYPES,
    add_shape,
    add_textbox,
    apply_shape_props,
    apply_textbox_props,
    move_artist,
    shape_props,
    textbox_props,
)

PREVIEW_DPI = 100.0

INSERT_SHAPE_GROUPS = [
    ("Lines", [("Line", "shape:line"), ("Arrow", "shape:arrow"), ("Double arrow", "shape:double_arrow")]),
    ("Rectangles", [("Rectangle", "shape:rectangle"), ("Rounded rectangle", "shape:round_rectangle")]),
    ("Basic shapes", [("Ellipse", "shape:ellipse"), ("Triangle", "shape:triangle"), ("Diamond", "shape:diamond")]),
    ("Text", [("Text box", "textbox")]),
]


def _insert_shape_icon(tool: str, size: int = 28) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    pen = QPen(QColor("#2f3437"), 2.0)
    pen.setCapStyle(Qt.RoundCap)
    painter.setPen(pen)
    painter.setBrush(QBrush(QColor("#ffffff")))

    margin = 5.0
    left = margin
    right = size - margin
    top = margin
    bottom = size - margin
    mid = size / 2.0
    shape_type = tool.split(":", 1)[1] if tool.startswith("shape:") else "textbox"

    if shape_type in {"line", "arrow", "double_arrow"}:
        painter.drawLine(QPointF(left, mid), QPointF(right, mid))
        if shape_type in {"arrow", "double_arrow"}:
            _draw_icon_arrow_head(painter, QPointF(right, mid), QPointF(right - 6.0, mid - 4.0), QPointF(right - 6.0, mid + 4.0))
        if shape_type == "double_arrow":
            _draw_icon_arrow_head(painter, QPointF(left, mid), QPointF(left + 6.0, mid - 4.0), QPointF(left + 6.0, mid + 4.0))
    elif shape_type == "rectangle":
        painter.drawRect(int(left), int(top + 2), int(right - left), int(bottom - top - 4))
    elif shape_type == "round_rectangle":
        painter.drawRoundedRect(int(left), int(top + 2), int(right - left), int(bottom - top - 4), 5, 5)
    elif shape_type == "ellipse":
        painter.drawEllipse(int(left), int(top + 2), int(right - left), int(bottom - top - 4))
    elif shape_type == "triangle":
        painter.drawPolygon(QPolygonF([QPointF(mid, top), QPointF(right, bottom), QPointF(left, bottom)]))
    elif shape_type == "diamond":
        painter.drawPolygon(QPolygonF([QPointF(mid, top), QPointF(right, mid), QPointF(mid, bottom), QPointF(left, mid)]))
    else:
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(int(left), int(top + 2), int(right - left), int(bottom - top - 4), 4, 4)
        font = painter.font()
        font.setBold(True)
        font.setPointSize(11)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignCenter, "T")

    painter.end()
    return QIcon(pixmap)


def _draw_icon_arrow_head(painter: QPainter, tip: QPointF, side_a: QPointF, side_b: QPointF) -> None:
    painter.drawLine(tip, side_a)
    painter.drawLine(tip, side_b)


def _marker_path(marker: str) -> Any:
    marker_style = MarkerStyle(marker)
    return marker_style.get_path().transformed(marker_style.get_transform())


class _AspectCanvasHost(QWidget):
    """Centers the Matplotlib canvas while preserving the editor's figure aspect."""

    def __init__(self, editor: "StyleEditor") -> None:
        super().__init__()
        self.editor = editor

    def resizeEvent(self, event: Any) -> None:
        super().resizeEvent(event)
        self.editor._update_canvas_display_size()
        self.editor.canvas.draw_idle()


def edit(
    fig: Figure,
    export_path: Optional[Union[str, Path]] = None,
    apply_existing: bool = True,
    source_path: Optional[Union[str, Path]] = None,
) -> None:
    """Open a visual editor for an existing Matplotlib figure.

    When ``apply_existing`` is true, an existing patch at ``export_path`` is
    applied first. This makes the generated patch a reusable style layer: open
    the same plot again, continue editing from the last exported result, then
    overwrite the same patch.
    """

    patch_error = None
    patch_warning = None
    source_path = Path(source_path).resolve() if source_path is not None else _infer_calling_script()
    patch_path = Path(export_path) if export_path is not None else _default_export_path(source_path)
    if apply_existing and patch_path.exists():
        try:
            patch_source = _apply_existing_style_patch(fig, patch_path)
            if patch_source and source_path is not None:
                expected_source = _source_metadata(source_path)
                if _normalize_source_metadata(patch_source) != _normalize_source_metadata(expected_source):
                    patch_warning = (
                        f"{patch_path} was created from {patch_source!r}, "
                        f"but this editor was opened from {expected_source!r}."
                    )
        except Exception as exc:
            patch_error = exc

    app = QApplication.instance() or QApplication(sys.argv)
    window = StyleEditor(fig, patch_path, source_path=source_path)
    if patch_warning is not None:
        window.status.setText(f"Patch source mismatch: {patch_path}")
        QMessageBox.warning(
            window,
            "Style patch source mismatch",
            f"{patch_warning}\n\nThe patch was still applied. "
            "Exporting will overwrite the current export path.",
        )
    if patch_error is not None:
        window.status.setText(f"Could not apply existing patch: {patch_error}")
        QMessageBox.warning(
            window,
            "Style patch not applied",
            f"Could not apply existing patch:\n{patch_error}",
        )
    window.show()
    app.exec()


def _infer_calling_script() -> Optional[Path]:
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


def _default_export_path(source_path: Optional[Path]) -> Path:
    if source_path is None:
        return Path("style_patch.py")
    return source_path.with_name(f"{source_path.stem}_style_patch.py")


def _source_metadata(source_path: Optional[Path]) -> Optional[str]:
    if source_path is None:
        return None
    try:
        return source_path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return source_path.resolve().as_posix()


def _normalize_source_metadata(value: str) -> str:
    return value.replace("\\", "/").strip()


def _apply_existing_style_patch(fig: Figure, patch_path: Union[str, Path]) -> Optional[str]:
    patch_path = Path(patch_path)
    module_name = f"_mpl_visual_editor_style_patch_{abs(hash(patch_path.resolve()))}"
    spec = importlib.util.spec_from_file_location(module_name, patch_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {patch_path}")
    module = importlib.util.module_from_spec(spec)
    try:
        import numpy as np

        module.np = np
    except ImportError:
        pass
    spec.loader.exec_module(module)
    apply_style = getattr(module, "apply_style", None)
    if not callable(apply_style):
        raise RuntimeError(f"{patch_path} does not define apply_style(fig)")
    _sanitize_legacy_axis_patches(module)
    _patch_style_module_helpers(module)
    apply_style(fig)
    source = getattr(module, "MPL_VISUAL_EDITOR_SOURCE", None)
    return str(source) if source is not None else None


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


class StyleEditor(QMainWindow):
    """Minimal style editor window."""

    def __init__(
        self,
        fig: Figure,
        export_path: Union[str, Path] = "style_patch.py",
        source_path: Optional[Path] = None,
    ) -> None:
        super().__init__()
        self.fig = fig
        self.export_path = Path(export_path)
        self.source_path = source_path
        self.refs: list[ArtistRef] = iter_artist_refs(fig)
        self.current_ref: Optional[ArtistRef] = None
        self.hover_ref: Optional[ArtistRef] = None
        self.pinned_ref: Optional[ArtistRef] = None
        self._highlight_state: Optional[dict[str, Any]] = None
        self._building_form = False
        self._selecting_programmatically = False
        self._rebuilding_legend = False
        self._suppress_dirty = False
        self._committed_snapshot: Optional[dict[str, Any]] = None
        self._dirty = False
        self._save_buttons: list[QPushButton] = []
        self._dirty_widgets: set[QWidget] = set()
        self._active_save_button: Optional[QPushButton] = None
        self._position_save_button: Optional[QPushButton] = None
        self._legend_press_xy: Optional[tuple[float, float]] = None
        self._drag_ref: Optional[ArtistRef] = None
        self._drag_last_data: Optional[tuple[float, float]] = None
        self._drag_moved = False
        self._insert_tool: Optional[str] = None
        self._draw_anchor_data: Optional[tuple[float, float]] = None
        self._selection_handles: list[Any] = []
        self._active_handle: Optional[str] = None
        self._legend_position_dirty = False
        self._fit_in_progress = False
        self._base_subplotpars: Optional[tuple[float, float, float, float]] = None
        self._preview_zoom: Optional[float] = None
        self._has_unexported_changes = False
        self._history_limit = 10
        self._undo_stack: list[dict[str, Any]] = []
        self._redo_stack: list[dict[str, Any]] = []
        self._restoring_history = False
        self._pending_history_snapshot: Optional[dict[str, Any]] = None
        self._inline_text_editor: Optional[QLineEdit] = None
        self._inline_text_ref: Optional[ArtistRef] = None
        self._inline_text_committing = False

        self.setWindowTitle("Matplotlib Visual Style Editor")
        self.resize(1180, 760)

        self.canvas = FigureCanvasQTAgg(fig)
        self.canvas.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.canvas.setMinimumSize(1, 1)
        self.toolbar = NavigationToolbar2QT(self.canvas, self)
        self.canvas_host = _AspectCanvasHost(self)
        self.canvas_scroll = QScrollArea()
        self.canvas_scroll.setWidgetResizable(True)
        self.canvas_scroll.setAlignment(Qt.AlignCenter)
        self.object_list = QListWidget()
        self.object_list.setSelectionMode(QListWidget.ExtendedSelection)
        self.form_host = QWidget()
        self.form = QFormLayout(self.form_host)
        self.status = QLabel("Ready")
        self.preview_zoom_label = QLabel("Fit")

        self._build_ui()
        self._initialize_figure_design_size()
        self._connect_hover_events()
        self._configure_picking()
        self._populate_object_list()
        if self.refs:
            self._selecting_programmatically = True
            try:
                self.object_list.setCurrentRow(0)
            finally:
                self._selecting_programmatically = False
        QTimer.singleShot(0, lambda: self._fit_figure_to_canvas(adjust_layout=True))

    def _build_ui(self) -> None:
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.addWidget(QLabel("Objects"))
        left_layout.addWidget(self.object_list, 1)

        refresh_button = QPushButton("Refresh objects")
        refresh_button.clicked.connect(self._refresh_refs)
        left_layout.addWidget(refresh_button)

        add_shape_button = QPushButton("Add shape")
        shape_menu = QMenu(add_shape_button)
        for section, tools in INSERT_SHAPE_GROUPS:
            shape_menu.addSection(section)
            for label, tool in tools:
                action = shape_menu.addAction(_insert_shape_icon(tool), label)
                action.triggered.connect(lambda _checked=False, selected_tool=tool: self._set_insert_tool(selected_tool))
        add_shape_button.setMenu(shape_menu)
        left_layout.addWidget(add_shape_button)

        history_controls = QWidget()
        history_layout = QHBoxLayout(history_controls)
        history_layout.setContentsMargins(0, 0, 0, 0)
        self.undo_button = QPushButton("Undo")
        self.undo_button.clicked.connect(self._undo)
        self.redo_button = QPushButton("Redo")
        self.redo_button.clicked.connect(self._redo)
        history_layout.addWidget(self.undo_button)
        history_layout.addWidget(self.redo_button)
        left_layout.addWidget(history_controls)
        self._refresh_history_buttons()

        export_button = QPushButton("Export style patch")
        export_button.clicked.connect(self._export)
        left_layout.addWidget(export_button)

        choose_export_button = QPushButton("Export as...")
        choose_export_button.clicked.connect(self._export_as)
        left_layout.addWidget(choose_export_button)

        export_figure_button = QPushButton("Export figure...")
        export_figure_button.clicked.connect(self._export_figure)
        left_layout.addWidget(export_figure_button)

        delete_button = QPushButton("Delete selected")
        delete_button.clicked.connect(self._delete_selected)
        left_layout.addWidget(delete_button)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.addWidget(QLabel("Properties"))
        right_layout.addWidget(self.form_host, 1)
        right_layout.addWidget(self.status)

        plot_panel = QWidget()
        plot_layout = QVBoxLayout(plot_panel)
        plot_layout.setContentsMargins(0, 0, 0, 0)
        plot_layout.addWidget(self.toolbar)
        preview_controls = QWidget()
        preview_controls_layout = QHBoxLayout(preview_controls)
        preview_controls_layout.setContentsMargins(6, 0, 6, 0)
        zoom_out_button = QPushButton("-")
        zoom_out_button.clicked.connect(lambda: self._zoom_preview(1 / 1.25))
        zoom_in_button = QPushButton("+")
        zoom_in_button.clicked.connect(lambda: self._zoom_preview(1.25))
        zoom_fit_button = QPushButton("Fit")
        zoom_fit_button.clicked.connect(self._fit_preview)
        zoom_actual_button = QPushButton("100%")
        zoom_actual_button.clicked.connect(self._actual_size_preview)
        preview_controls_layout.addWidget(QLabel("Preview zoom:"))
        preview_controls_layout.addWidget(zoom_out_button)
        preview_controls_layout.addWidget(zoom_in_button)
        preview_controls_layout.addWidget(zoom_fit_button)
        preview_controls_layout.addWidget(zoom_actual_button)
        preview_controls_layout.addWidget(self.preview_zoom_label)
        preview_controls_layout.addStretch(1)
        plot_layout.addWidget(preview_controls)
        canvas_host_layout = QVBoxLayout(self.canvas_host)
        canvas_host_layout.setContentsMargins(24, 24, 24, 24)
        canvas_host_layout.addWidget(self.canvas, 0, Qt.AlignCenter)
        self.canvas_scroll.setWidget(self.canvas_host)
        plot_layout.addWidget(self.canvas_scroll, 1)

        side_splitter = QSplitter(Qt.Vertical)
        side_splitter.addWidget(left_panel)
        side_splitter.addWidget(right_panel)
        side_splitter.setSizes([360, 400])

        main_splitter = QSplitter(Qt.Horizontal)
        main_splitter.addWidget(side_splitter)
        main_splitter.addWidget(plot_panel)
        main_splitter.setSizes([360, 820])
        self.setCentralWidget(main_splitter)

        self.object_list.currentItemChanged.connect(self._on_selection_changed)

    def _populate_object_list(self) -> None:
        self.object_list.clear()
        for ref in self.refs:
            item = QListWidgetItem(ref.label)
            item.setData(Qt.UserRole, ref)
            self.object_list.addItem(item)

    def _configure_picking(self) -> None:
        for ref in self.refs:
            artist = ref.artist
            if ref.kind in {"line", "spine"} and hasattr(artist, "set_picker"):
                artist.set_picker(8)
            elif ref.kind == "text" and hasattr(artist, "set_picker"):
                artist.set_picker(True)
            elif ref.kind == "text_group":
                for text in artist:
                    if hasattr(text, "set_picker"):
                        text.set_picker(True)
            elif ref.kind in {"shape", "textbox"} and hasattr(artist, "set_picker"):
                artist.set_picker(True)
            elif ref.kind == "bar":
                for patch in artist.patches:
                    if hasattr(patch, "set_picker"):
                        patch.set_picker(True)
            elif ref.kind == "legend":
                artist.set_draggable(True, use_blit=False, update="bbox")
            elif ref.kind == "unsupported" and hasattr(artist, "set_picker"):
                artist.set_picker(True)

    def _refresh_refs(self) -> None:
        self.pinned_ref = None
        self._clear_selection_handles()
        self._clear_hover_highlight()
        self.refs = iter_artist_refs(self.fig)
        self._configure_picking()
        self._populate_object_list()
        if self.refs:
            self.object_list.setCurrentRow(0)
        self._redraw("Object list refreshed")

    def _set_insert_tool(self, tool: str) -> None:
        self._discard_unsaved_preview()
        self._insert_tool = tool
        self.pinned_ref = None
        self._clear_selection_handles()
        self._clear_hover_highlight()
        self.canvas.setCursor(Qt.CrossCursor)
        label = tool.split(":", 1)[1] if tool.startswith("shape:") else "text box"
        self.status.setText(f"Click to place {label}, or drag to draw its size. Right-click to cancel.")

    def _clear_insert_tool(self) -> None:
        self._insert_tool = None
        self.canvas.unsetCursor()

    def _insert_tool_at_event(self, event: Any) -> bool:
        if self._insert_tool is None:
            return False
        target = self._event_data_point(event)
        if target is None:
            self.status.setText("Click on or near an axes to place the object.")
            return True
        tool = self._insert_tool
        self._clear_insert_tool()
        ax, data_x, data_y = target
        center = (data_x, data_y)
        self._push_undo_snapshot()
        if tool.startswith("shape:"):
            shape_type = tool.split(":", 1)[1]
            artist = add_shape(ax, shape_type, center=center)
            message = f"Added {shape_type}. Drag handles to move, resize, or rotate."
        else:
            artist = add_textbox(ax, center=center)
            message = "Added text box. Drag it or its handles."
        self._refresh_refs()
        self._select_ref_by_artist(artist)
        if self.current_ref is not None and self.current_ref.kind in {"shape", "textbox"}:
            self._active_handle = "end" if tool.startswith("shape:") and tool.split(":", 1)[1] in LINE_SHAPE_TYPES else "se"
            self._drag_last_data = center
            self._draw_anchor_data = center
            self._drag_moved = False
        self._mark_position_dirty()
        self.status.setText(message)
        return True

    def _target_axes(self) -> Optional[Any]:
        ref = self.pinned_ref or self.current_ref
        artist = getattr(ref, "artist", None)
        ax = self._coerce_axes(getattr(artist, "axes", None))
        if ax is not None:
            return ax
        return self._coerce_axes(self.fig.axes[0] if self.fig.axes else None)

    def _event_data_point(self, event: Any, preferred_axes: Optional[Any] = None) -> Optional[tuple[Any, float, float]]:
        if event.x is None or event.y is None:
            return None
        ax = self._coerce_axes(event.inaxes) or self._coerce_axes(preferred_axes) or self._target_axes()
        if ax is None:
            ax = self._nearest_axes(float(event.x), float(event.y))
        if ax is None:
            return None
        if event.inaxes is ax and event.xdata is not None and event.ydata is not None:
            return ax, float(event.xdata), float(event.ydata)
        data_x, data_y = ax.transData.inverted().transform((float(event.x), float(event.y)))
        return ax, float(data_x), float(data_y)

    def _coerce_axes(self, candidate: Any) -> Optional[Any]:
        if candidate is None:
            return None
        if hasattr(candidate, "transData"):
            return candidate
        if isinstance(candidate, (list, tuple)):
            for item in candidate:
                ax = self._coerce_axes(item)
                if ax is not None:
                    return ax
        return None

    def _event_artist_point(self, event: Any, artist: Any) -> Optional[tuple[float, float]]:
        if event.x is None or event.y is None:
            return None
        try:
            x, y = artist.get_transform().inverted().transform((float(event.x), float(event.y)))
        except Exception:
            target = self._event_data_point(event, getattr(artist, "axes", None))
            if target is None:
                return None
            _ax, x, y = target
        return float(x), float(y)

    def _nearest_axes(self, x: float, y: float) -> Optional[Any]:
        if not self.fig.axes:
            return None
        renderer = self.canvas.get_renderer()
        best_ax = None
        best_distance = float("inf")
        for ax in self.fig.axes:
            bbox = ax.get_window_extent(renderer=renderer)
            dx = max(float(bbox.x0) - x, 0.0, x - float(bbox.x1))
            dy = max(float(bbox.y0) - y, 0.0, y - float(bbox.y1))
            distance = math.hypot(dx, dy)
            if distance < best_distance:
                best_distance = distance
                best_ax = ax
        return best_ax

    def _set_text_position(self, artist: Any, x: Optional[float] = None, y: Optional[float] = None) -> None:
        current_x, current_y = artist.get_position()
        artist.set_position(
            (
                float(current_x if x is None else x),
                float(current_y if y is None else y),
            )
        )

    def _move_text_by_display_delta(self, artist: Any, dx: float, dy: float) -> None:
        self._prepare_text_for_free_drag(artist)
        try:
            x, y = artist.get_position()
            display_x, display_y = artist.get_transform().transform((float(x), float(y)))
            new_x, new_y = artist.get_transform().inverted().transform((display_x + float(dx), display_y + float(dy)))
        except Exception:
            return
        artist.set_position((float(new_x), float(new_y)))

    def _prepare_text_for_free_drag(self, artist: Any) -> None:
        if hasattr(artist, "set_in_layout"):
            artist.set_in_layout(False)
        ax = getattr(artist, "axes", None)
        if ax is None:
            return
        if artist is getattr(ax, "title", None):
            ax._autotitlepos = False
        if artist is getattr(ax.xaxis, "label", None):
            ax.xaxis._autolabelpos = False
        if artist is getattr(ax.yaxis, "label", None):
            ax.yaxis._autolabelpos = False

    def _select_ref_by_artist(self, artist: Any) -> None:
        for ref in self.refs:
            if ref.artist is artist:
                self.pinned_ref = ref
                self._select_ref(ref)
                self._set_hover_highlight(ref)
                return

    def _on_selection_changed(self, current: Optional[QListWidgetItem]) -> None:
        if current is None:
            return
        if not self._selecting_programmatically:
            self._discard_unsaved_preview()
        self.current_ref = current.data(Qt.UserRole)
        if self.current_ref is not None and not self._selecting_programmatically:
            self.pinned_ref = self.current_ref
            self._set_hover_highlight(self.current_ref)
            self.status.setText(f"Selected: {self.current_ref.label}")
        self._build_form(self.current_ref)
        self._show_selection_handles(self.current_ref)
        self._update_canvas_display_size()

    def _connect_hover_events(self) -> None:
        self.canvas.mpl_connect("motion_notify_event", self._on_canvas_motion)
        self.canvas.mpl_connect("button_press_event", self._on_canvas_click)
        self.canvas.mpl_connect("button_release_event", self._on_canvas_release)
        self.canvas.mpl_connect("figure_leave_event", self._on_canvas_leave)

    def _on_canvas_motion(self, event: Any) -> None:
        if self._active_handle is not None:
            self._drag_selection_handle(event)
            return
        if self._drag_ref is not None:
            self._drag_editor_artist(event)
            return
        if self._legend_press_xy is not None and self.current_ref is not None and self.current_ref.kind == "legend":
            QTimer.singleShot(0, self._refresh_hover_highlight)
            return
        if self.pinned_ref is not None:
            return

        ref = self._find_ref_at_event(event)
        if ref is None:
            self._clear_hover_highlight()
            return
        if self.hover_ref is not None and self.hover_ref.path == ref.path:
            return

        self._set_hover_highlight(ref)
        self.status.setText(f"Hover: {ref.label}")

    def _on_canvas_click(self, event: Any) -> None:
        if getattr(event, "dblclick", False):
            if event.button == 1:
                self._start_inline_text_edit_at_event(event)
            return
        if self._inline_text_editor is not None:
            self._cancel_inline_text_edit()
        if event.button == 3 and self._insert_tool is not None:
            self._clear_insert_tool()
            self.status.setText("Insert cancelled.")
            return
        if event.button != 1:
            return
        if self._insert_tool_at_event(event):
            return

        handle = self._find_selection_handle(event)
        if handle is not None:
            self._active_handle = handle
            self._drag_last_data = (float(event.xdata), float(event.ydata)) if event.xdata is not None and event.ydata is not None else None
            self._drag_moved = False
            self._pending_history_snapshot = self._capture_history_snapshot()
            return

        ref = self._find_ref_at_event(event)
        if ref is None:
            self._discard_unsaved_preview()
            self.pinned_ref = None
            self._clear_selection_handles()
            self._clear_hover_highlight()
            self.status.setText("Selection unlocked")
            return

        if self.current_ref is not None and self.current_ref.path != ref.path:
            self._discard_unsaved_preview()
        self.pinned_ref = ref
        self._select_ref(ref)
        self._set_hover_highlight(ref)
        self._show_selection_handles(ref)
        self._update_canvas_display_size()
        target = self._event_data_point(event, ref.artist.axes if hasattr(ref.artist, "axes") else None)
        if ref.kind == "text":
            if event.x is not None and event.y is not None:
                self._drag_ref = ref
                self._drag_last_data = (float(event.x), float(event.y))
                self._drag_moved = False
                self._pending_history_snapshot = self._capture_history_snapshot()
        elif ref.kind in {"shape", "textbox", "arrow"} and target is not None:
            _ax, data_x, data_y = target
            self._drag_ref = ref
            self._drag_last_data = (data_x, data_y)
            self._drag_moved = False
            self._pending_history_snapshot = self._capture_history_snapshot()
        if ref.kind == "legend":
            self._legend_press_xy = (float(event.x), float(event.y))
            self._pending_history_snapshot = self._capture_history_snapshot()
        self.status.setText(f"Pinned: {ref.label}")

    def _on_canvas_release(self, event: Any) -> None:
        if self._active_handle is not None:
            moved = self._drag_moved
            self._active_handle = None
            self._drag_last_data = None
            self._draw_anchor_data = None
            self._drag_moved = False
            if moved:
                if self._pending_history_snapshot is not None:
                    self._push_undo_snapshot(self._pending_history_snapshot)
                self._mark_position_dirty()
                self.status.setText("Placement auto-saved.")
            self._pending_history_snapshot = None
            return
        if self._drag_ref is not None:
            moved = self._drag_moved
            self._drag_ref = None
            self._drag_last_data = None
            self._drag_moved = False
            if moved:
                if self._pending_history_snapshot is not None:
                    self._push_undo_snapshot(self._pending_history_snapshot)
                self._mark_position_dirty()
                self.status.setText("Placement auto-saved.")
            self._pending_history_snapshot = None
            return
        if (
            self.current_ref is None
            or self.current_ref.kind != "legend"
            or self._legend_press_xy is None
            or event.x is None
            or event.y is None
        ):
            self._legend_press_xy = None
            self._pending_history_snapshot = None
            return

        start_x, start_y = self._legend_press_xy
        self._legend_press_xy = None
        moved = abs(float(event.x) - start_x) + abs(float(event.y) - start_y)
        if moved > 4:
            self._legend_position_dirty = True
            if self._pending_history_snapshot is not None:
                self._push_undo_snapshot(self._pending_history_snapshot)
            self._save_current_legend_position()
            self._refresh_hover_highlight()
            self.canvas.draw_idle()
            self.status.setText("Legend position auto-saved.")
        self._pending_history_snapshot = None

    def _on_canvas_leave(self, _event: Any) -> None:
        if self.pinned_ref is not None:
            return
        self._clear_hover_highlight()

    def _start_inline_text_edit_at_event(self, event: Any) -> None:
        ref = self._text_ref_at_event(event)
        if ref is None:
            return
        self._discard_unsaved_preview()
        self._select_ref(ref)
        self.pinned_ref = ref
        self._set_hover_highlight(ref)
        self._show_selection_handles(ref)
        self._start_inline_text_edit(ref)

    def _text_ref_at_event(self, event: Any) -> Optional[ArtistRef]:
        for ref in reversed(self.refs):
            if ref.kind not in {"text", "textbox"}:
                continue
            adapter = get_adapter(ref.kind)
            if adapter is not None and adapter.hit_test(ref, event, self):
                return ref
        return None

    def _start_inline_text_edit(self, ref: ArtistRef) -> None:
        self._cancel_inline_text_edit()
        if not hasattr(ref.artist, "get_text"):
            return
        try:
            self.canvas.draw()
            renderer = self.canvas.get_renderer()
            bbox = ref.artist.get_window_extent(renderer=renderer)
        except Exception:
            return

        editor = QLineEdit(str(ref.artist.get_text()), self.canvas)
        editor.selectAll()
        width = max(80, int(math.ceil(bbox.width)) + 24)
        height = max(24, int(editor.sizeHint().height()))
        left = max(0, min(int(math.floor(bbox.x0)), max(0, self.canvas.width() - width)))
        top = max(0, min(int(math.floor(self.canvas.height() - bbox.y1)), max(0, self.canvas.height() - height)))
        editor.setGeometry(left, top, width, height)

        def key_press(key_event: Any) -> None:
            if key_event.key() == Qt.Key_Escape:
                self._cancel_inline_text_edit()
                return
            if key_event.key() in {Qt.Key_Return, Qt.Key_Enter}:
                self._commit_inline_text_edit()
                return
            QLineEdit.keyPressEvent(editor, key_event)

        def focus_out(focus_event: Any) -> None:
            QLineEdit.focusOutEvent(editor, focus_event)
            if not self._inline_text_committing:
                self._cancel_inline_text_edit()

        editor.keyPressEvent = key_press  # type: ignore[method-assign]
        editor.focusOutEvent = focus_out  # type: ignore[method-assign]
        self._inline_text_editor = editor
        self._inline_text_ref = ref
        editor.show()
        editor.setFocus(Qt.MouseFocusReason)
        self.status.setText("Editing text inline. Press Enter to apply or Esc to cancel.")

    def _commit_inline_text_edit(self) -> None:
        editor = self._inline_text_editor
        ref = self._inline_text_ref
        if editor is None or ref is None:
            return
        value = editor.text()
        old_value = ref.artist.get_text() if hasattr(ref.artist, "get_text") else value
        self._inline_text_committing = True
        try:
            self._clear_inline_text_editor()
            if value == old_value:
                return
            self._push_undo_snapshot()
            self._set_ref_text(ref, value)
            self._mark_unexported_changes()
            self._refresh_refs_preserving_path(ref.path)
            self.canvas.draw_idle()
            self.status.setText("Text updated.")
        finally:
            self._inline_text_committing = False

    def _cancel_inline_text_edit(self) -> None:
        self._clear_inline_text_editor()

    def _clear_inline_text_editor(self) -> None:
        editor = self._inline_text_editor
        self._inline_text_editor = None
        self._inline_text_ref = None
        if editor is not None:
            editor.hide()
            editor.deleteLater()

    def _set_ref_text(self, ref: ArtistRef, value: str) -> None:
        if ref.kind == "textbox":
            props = textbox_props(ref.artist)
            props["text"] = value
            apply_textbox_props(ref.artist.axes, props, ref.artist)
            return
        ref.artist.set_text(value)

    def _drag_editor_artist(self, event: Any) -> None:
        if (
            self._drag_ref is None
            or self._drag_last_data is None
        ):
            return
        if self._drag_ref.kind == "text":
            if event.x is None or event.y is None:
                return
            last_x, last_y = self._drag_last_data
            self._move_text_by_display_delta(self._drag_ref.artist, float(event.x) - last_x, float(event.y) - last_y)
            self._drag_last_data = (float(event.x), float(event.y))
            self._drag_moved = True
            self._show_selection_handles(self._drag_ref)
            self.canvas.draw_idle()
            return
        else:
            target = self._event_data_point(event, self._drag_ref.artist.axes if hasattr(self._drag_ref.artist, "axes") else None)
            if target is None:
                return
            _ax, x, y = target
        last_x, last_y = self._drag_last_data
        dx, dy = x - last_x, y - last_y
        if dx == 0 and dy == 0:
            return
        self._move_geometry_ref(self._drag_ref, dx, dy)
        self._drag_last_data = (x, y)
        self._drag_moved = True
        self._show_selection_handles(self._drag_ref)
        self.canvas.draw_idle()

    def _move_geometry_ref(self, ref: ArtistRef, dx: float, dy: float) -> None:
        if ref.kind in {"shape", "textbox"}:
            move_artist(ref.artist, dx, dy)
        elif ref.kind == "text":
            x, y = ref.artist.get_position()
            ref.artist.set_position((float(x) + dx, float(y) + dy))
        elif ref.kind == "arrow":
            props = arrow_props(ref.artist)
            props["posA"] = [props["posA"][0] + dx, props["posA"][1] + dy]
            props["posB"] = [props["posB"][0] + dx, props["posB"][1] + dy]
            apply_arrow_props(ref.artist, props)

    def _move_line(self, line: Any, dx: float, dy: float) -> None:
        xdata = [float(x) + dx for x in line.get_xdata()]
        ydata = [float(y) + dy for y in line.get_ydata()]
        line.set_data(xdata, ydata)
        line._mve_xdata = list(xdata)
        line._mve_ydata = list(ydata)

    def _find_selection_handle(self, event: Any) -> Optional[str]:
        if event.x is None or event.y is None:
            return None
        best_handle: Optional[str] = None
        best_distance = float("inf")
        priority = {
            "start": 0,
            "end": 0,
            "rotate": 1,
            "nw": 2,
            "n": 2,
            "ne": 2,
            "e": 2,
            "se": 2,
            "s": 2,
            "sw": 2,
            "w": 2,
            "move": 3,
        }
        for handle in reversed(self._selection_handles):
            try:
                xdata = float(handle.get_xdata()[0])
                ydata = float(handle.get_ydata()[0])
                hx, hy = handle.axes.transData.transform((xdata, ydata))
            except Exception:
                continue
            distance = math.hypot(float(event.x) - hx, float(event.y) - hy)
            radius = float(getattr(handle, "_mve_hit_radius", 12.0))
            if distance > radius:
                continue
            handle_name = getattr(handle, "_mve_handle", None)
            if handle_name is None:
                continue
            if (
                best_handle is None
                or distance < best_distance - 0.5
                or (
                    math.isclose(distance, best_distance, abs_tol=0.5)
                    and priority.get(handle_name, 99) < priority.get(best_handle, 99)
                )
            ):
                best_handle = handle_name
                best_distance = distance
        return best_handle

    def _drag_selection_handle(self, event: Any) -> None:
        if (
            self.current_ref is None
            or self._active_handle is None
        ):
            return
        ref = self.current_ref
        target = self._event_data_point(event, ref.artist.axes if hasattr(ref.artist, "axes") else None)
        if target is None:
            return
        _ax, x, y = target
        if ref.kind == "shape":
            self._drag_shape_handle(ref, self._active_handle, x, y)
        elif ref.kind == "textbox":
            self._drag_textbox_handle(ref, self._active_handle, x, y)
        elif ref.kind == "text":
            self._drag_text_handle(ref, self._active_handle, x, y)
        elif ref.kind == "arrow":
            self._drag_arrow_handle(ref, self._active_handle, x, y)
        else:
            return
        self._drag_moved = True
        self._show_selection_handles(ref)
        self.canvas.draw_idle()

    def _drag_shape_handle(self, ref: ArtistRef, handle: str, x: float, y: float) -> None:
        props = shape_props(ref.artist)
        cx, cy = float(props["x"]), float(props["y"])
        if handle == "move":
            if self._drag_last_data is None:
                self._drag_last_data = (x, y)
            last_x, last_y = self._drag_last_data
            props["x"] = cx + x - last_x
            props["y"] = cy + y - last_y
            self._drag_last_data = (x, y)
        elif handle in {"start", "end"}:
            points = self._shape_handle_points(props)
            fixed_name = "end" if handle == "start" else "start"
            fixed = self._draw_anchor_data if self._draw_anchor_data is not None and handle == "end" else points.get(fixed_name)
            if fixed is None:
                return
            fx, fy = fixed
            props["x"] = (x + fx) / 2.0
            props["y"] = (y + fy) / 2.0
            props["width"] = max(math.hypot(x - fx, y - fy), 1e-12)
            if handle == "start":
                props["angle"] = math.degrees(math.atan2(fy - y, fx - x))
            else:
                props["angle"] = math.degrees(math.atan2(y - fy, x - fx))
        elif handle == "rotate":
            props["angle"] = math.degrees(math.atan2(y - cy, x - cx)) - 90.0
        else:
            points = self._shape_handle_points(props)
            opposite_name = {
                "nw": "se",
                "n": "s",
                "ne": "sw",
                "e": "w",
                "se": "nw",
                "s": "n",
                "sw": "ne",
                "w": "e",
            }.get(handle)
            opposite = self._draw_anchor_data if self._draw_anchor_data is not None and handle == "se" else (
                points.get(opposite_name) if opposite_name else None
            )
            if opposite is None:
                return
            ox, oy = opposite
            props["x"] = (x + ox) / 2.0
            props["y"] = (y + oy) / 2.0
            angle = math.radians(float(props.get("angle", 0.0)))
            cos_a, sin_a = math.cos(-angle), math.sin(-angle)
            dx, dy = x - ox, y - oy
            local_x = dx * cos_a - dy * sin_a
            local_y = dx * sin_a + dy * cos_a
            if props.get("type") in LINE_SHAPE_TYPES:
                props["width"] = max(abs(local_x), 1e-12)
            else:
                if handle in {"nw", "ne", "e", "se", "sw", "w"}:
                    props["width"] = max(abs(local_x), 1e-12)
                if handle in {"nw", "n", "ne", "se", "s", "sw"}:
                    props["height"] = max(abs(local_y), 1e-12)
        apply_shape_props(ref.artist.axes, props, ref.artist)

    def _drag_textbox_handle(self, ref: ArtistRef, handle: str, x: float, y: float) -> None:
        props = textbox_props(ref.artist)
        cx, cy = float(props["x"]), float(props["y"])
        if handle == "move":
            if self._drag_last_data is None:
                self._drag_last_data = (x, y)
            last_x, last_y = self._drag_last_data
            props["x"] = cx + x - last_x
            props["y"] = cy + y - last_y
            self._drag_last_data = (x, y)
        elif handle == "rotate":
            props["rotation"] = math.degrees(math.atan2(y - cy, x - cx)) - 90.0
        else:
            points = self._textbox_handle_points(ref.artist)
            current = math.hypot(points.get(handle, (x, y))[0] - cx, points.get(handle, (x, y))[1] - cy)
            updated = math.hypot(x - cx, y - cy)
            if current > 1e-12:
                props["fontsize"] = max(1.0, min(160.0, float(props["fontsize"]) * updated / current))
        apply_textbox_props(ref.artist.axes, props, ref.artist)

    def _drag_text_handle(self, ref: ArtistRef, handle: str, x: float, y: float) -> None:
        if handle != "move":
            return
        ref.artist.set_position((x, y))

    def _drag_line_handle(self, ref: ArtistRef, handle: str, x: float, y: float) -> None:
        line = ref.artist
        xdata = [float(value) for value in line.get_xdata()]
        ydata = [float(value) for value in line.get_ydata()]
        if not xdata or not ydata:
            return
        if handle == "move":
            if self._drag_last_data is None:
                self._drag_last_data = (x, y)
            last_x, last_y = self._drag_last_data
            self._move_line(line, x - last_x, y - last_y)
            self._drag_last_data = (x, y)
            return
        if len(xdata) == 2 and handle in {"start", "end"}:
            index = 0 if handle == "start" else 1
            xdata[index] = x
            ydata[index] = y
            line.set_data(xdata, ydata)
            line._mve_xdata = list(xdata)
            line._mve_ydata = list(ydata)

    def _drag_arrow_handle(self, ref: ArtistRef, handle: str, x: float, y: float) -> None:
        props = arrow_props(ref.artist)
        if handle == "move":
            if self._drag_last_data is None:
                self._drag_last_data = (x, y)
            last_x, last_y = self._drag_last_data
            dx, dy = x - last_x, y - last_y
            props["posA"] = [props["posA"][0] + dx, props["posA"][1] + dy]
            props["posB"] = [props["posB"][0] + dx, props["posB"][1] + dy]
            self._drag_last_data = (x, y)
        elif handle == "start":
            props["posA"] = [x, y]
        elif handle == "end":
            props["posB"] = [x, y]
        else:
            return
        apply_arrow_props(ref.artist, props)

    def _show_selection_handles(self, ref: Optional[ArtistRef]) -> None:
        self._clear_selection_handles()
        if ref is None or ref.kind not in {"shape", "textbox", "arrow"}:
            return
        ax = ref.artist.axes
        if ax is None:
            return
        if ref.kind == "shape":
            points = self._shape_handle_points(shape_props(ref.artist))
        elif ref.kind == "textbox":
            points = self._textbox_handle_points(ref.artist)
        else:
            points = self._arrow_handle_points(ref.artist)
        xlim = ax.get_xlim()
        ylim = ax.get_ylim()
        for name, (x, y) in points.items():
            marker = "o" if name in {"rotate", "start", "end"} else "s"
            handle = ax.plot(
                [x],
                [y],
                marker=marker,
                markersize=2.0 if name in {"start", "end", "move"} else 1.8,
                markerfacecolor="#ffffff",
                markeredgecolor="#1976d2",
                markeredgewidth=0.8,
                color="#1976d2",
                linestyle="None",
                zorder=10000,
                picker=10,
            )[0]
            handle._mve_kind = "editor_handle"
            handle._mve_handle = name
            handle._mve_hit_radius = 14.0 if name in {"start", "end"} else 10.0
            self._selection_handles.append(handle)
        ax.set_xlim(xlim)
        ax.set_ylim(ylim)

    def _clear_selection_handles(self) -> None:
        for handle in self._selection_handles:
            try:
                handle.remove()
            except Exception:
                pass
        self._selection_handles = []

    def _shape_handle_points(self, props: dict[str, Any]) -> dict[str, tuple[float, float]]:
        x, y = float(props["x"]), float(props["y"])
        width = float(props["width"])
        if props.get("type") in LINE_SHAPE_TYPES:
            angle = math.radians(float(props.get("angle", 0.0)))
            dx = math.cos(angle) * width / 2.0
            dy = math.sin(angle) * width / 2.0
            return {
                "start": (x - dx, y - dy),
                "move": (x, y),
                "end": (x + dx, y + dy),
            }
        height = (
            float(props["height"])
            if props.get("type") not in LINE_SHAPE_TYPES
            else max(float(props["width"]) * 0.2, 1e-12)
        )
        angle = math.radians(float(props.get("angle", 0.0)))
        corners = {
            "nw": (-width / 2.0, height / 2.0),
            "n": (0.0, height / 2.0),
            "ne": (width / 2.0, height / 2.0),
            "e": (width / 2.0, 0.0),
            "se": (width / 2.0, -height / 2.0),
            "s": (0.0, -height / 2.0),
            "sw": (-width / 2.0, -height / 2.0),
            "w": (-width / 2.0, 0.0),
            "move": (0.0, 0.0),
            "rotate": (0.0, height / 2.0 + max(height, width) * 0.25),
        }
        return {name: self._rotate_point(x, y, px, py, angle) for name, (px, py) in corners.items()}

    def _textbox_handle_points(self, artist: Any) -> dict[str, tuple[float, float]]:
        ax = artist.axes
        renderer = self.canvas.get_renderer()
        try:
            bbox = artist.get_window_extent(renderer=renderer).transformed(ax.transData.inverted())
            x0, x1, y0, y1 = bbox.x0, bbox.x1, bbox.y0, bbox.y1
        except Exception:
            x, y = artist.get_position()
            span_x = abs(ax.get_xlim()[1] - ax.get_xlim()[0]) * 0.12
            span_y = abs(ax.get_ylim()[1] - ax.get_ylim()[0]) * 0.08
            x0, x1, y0, y1 = x - span_x / 2.0, x + span_x / 2.0, y - span_y / 2.0, y + span_y / 2.0
        cx, cy = artist.get_position()
        return {
            "nw": (x0, y1),
            "n": ((x0 + x1) / 2.0, y1),
            "ne": (x1, y1),
            "e": (x1, (y0 + y1) / 2.0),
            "se": (x1, y0),
            "s": ((x0 + x1) / 2.0, y0),
            "sw": (x0, y0),
            "w": (x0, (y0 + y1) / 2.0),
            "move": (float(cx), float(cy)),
            "rotate": (float(cx), y1 + (y1 - y0) * 0.5),
        }

    def _text_handle_points(self, artist: Any) -> dict[str, tuple[float, float]]:
        x, y = artist.get_position()
        return {"move": (float(x), float(y))}

    def _line_handle_points(self, line: Any) -> dict[str, tuple[float, float]]:
        xdata = [float(value) for value in line.get_xdata()]
        ydata = [float(value) for value in line.get_ydata()]
        if not xdata or not ydata:
            return {}
        points = {
            "move": (sum(xdata) / len(xdata), sum(ydata) / len(ydata)),
        }
        if len(xdata) == 2:
            points["start"] = (xdata[0], ydata[0])
            points["end"] = (xdata[1], ydata[1])
        return points

    def _arrow_handle_points(self, artist: Any) -> dict[str, tuple[float, float]]:
        props = arrow_props(artist)
        pos_a = props["posA"]
        pos_b = props["posB"]
        return {
            "start": (float(pos_a[0]), float(pos_a[1])),
            "move": ((float(pos_a[0]) + float(pos_b[0])) / 2.0, (float(pos_a[1]) + float(pos_b[1])) / 2.0),
            "end": (float(pos_b[0]), float(pos_b[1])),
        }

    def _rotate_point(self, cx: float, cy: float, x: float, y: float, angle: float) -> tuple[float, float]:
        cos_a, sin_a = math.cos(angle), math.sin(angle)
        return cx + x * cos_a - y * sin_a, cy + x * sin_a + y * cos_a

    def closeEvent(self, event: Any) -> None:
        if self._has_unexported_changes:
            choice = QMessageBox.warning(
                self,
                "Unexported style changes",
                "You have style changes that have not been exported since the last edit.\n\n"
                "If you close now, changes that were not exported with Export style patch "
                "will be cleared the next time you open this figure.\n\n"
                "Close without exporting?",
                QMessageBox.Close | QMessageBox.Cancel,
                QMessageBox.Cancel,
            )
            if choice != QMessageBox.Close:
                event.ignore()
                return
        self._clear_inline_text_editor()
        self._clear_selection_handles()
        self._clear_hover_highlight(redraw=False)
        super().closeEvent(event)

    def _find_ref_at_event(self, event: Any) -> Optional[ArtistRef]:
        if event.x is None or event.y is None:
            return None

        for ref in reversed(self.refs):
            if ref.kind not in {"text", "textbox"}:
                continue
            adapter = get_adapter(ref.kind)
            if adapter is not None and adapter.hit_test(ref, event, self):
                return ref

        for ref in reversed(self.refs):
            if ref.kind in {"figure", "axes", "axis", "text", "textbox", "text_group"}:
                continue
            adapter = get_adapter(ref.kind)
            if adapter is not None and adapter.hit_test(ref, event, self):
                return ref

        for kind in ["axis", "axes"]:
            for ref in self.refs:
                if ref.kind != kind:
                    continue
                adapter = get_adapter(ref.kind)
                if adapter is not None and adapter.hit_test(ref, event, self):
                    return ref
        return None

    def _select_ref(self, ref: ArtistRef) -> None:
        for row in range(self.object_list.count()):
            item = self.object_list.item(row)
            item_ref = item.data(Qt.UserRole)
            if item_ref.path == ref.path:
                if self.object_list.currentRow() != row:
                    self.object_list.setCurrentRow(row)
                return

    def _refresh_refs_preserving_path(self, path: Optional[Union[tuple[Any, ...], list[Any]]]) -> None:
        self._clear_hover_highlight(redraw=False)
        self._clear_selection_handles()
        self.refs = iter_artist_refs(self.fig)
        self._configure_picking()
        self._populate_object_list()
        self.current_ref = None
        self.pinned_ref = None
        selected_ref = self._ref_for_path(path) if path is not None else None
        if selected_ref is None and self.refs:
            selected_ref = self.refs[0]
        if selected_ref is None:
            self.canvas.draw_idle()
            return
        self._selecting_programmatically = True
        try:
            self._select_ref(selected_ref)
        finally:
            self._selecting_programmatically = False
        self.current_ref = selected_ref
        self.pinned_ref = selected_ref
        self._build_form(selected_ref)
        self._set_hover_highlight(selected_ref)
        self._show_selection_handles(selected_ref)

    def _ref_for_path(self, path: Optional[Union[tuple[Any, ...], list[Any]]]) -> Optional[ArtistRef]:
        if path is None:
            return None
        target = tuple(path)
        for ref in self.refs:
            if tuple(ref.path) == target:
                return ref
        return None

    def _set_hover_highlight(self, ref: ArtistRef) -> None:
        self._clear_hover_highlight(redraw=False)
        self.hover_ref = ref
        self._highlight_state = self._apply_hover_highlight(ref)
        self.canvas.draw_idle()

    def _clear_hover_highlight(self, redraw: bool = True) -> None:
        if self.hover_ref is None or self._highlight_state is None:
            return
        self._restore_hover_highlight(self.hover_ref, self._highlight_state)
        self.hover_ref = None
        self._highlight_state = None
        if redraw:
            self.canvas.draw_idle()

    def _refresh_hover_highlight(self) -> None:
        if self.hover_ref is None or self._highlight_state is None:
            return
        ref = self.hover_ref
        self._restore_hover_highlight(ref, self._highlight_state)
        self._highlight_state = self._apply_hover_highlight(ref)
        self.canvas.draw_idle()

    def _apply_hover_highlight(self, ref: ArtistRef) -> dict[str, Any]:
        adapter = get_adapter(ref.kind)
        if adapter is not None:
            return adapter.highlight(ref, self)
        return {"kind": ref.kind}

    def _restore_hover_highlight(self, ref: ArtistRef, state: dict[str, Any]) -> None:
        adapter = get_adapter(ref.kind)
        if adapter is not None:
            adapter.restore_highlight(ref, self, state)

    def _build_form(self, ref: ArtistRef) -> None:
        self._building_form = True
        self._save_buttons = []
        self._position_save_button = None
        self._dirty = False
        self._dirty_widgets = set()
        self._committed_snapshot = snapshot_artist(ref.kind, ref.path, ref.artist)
        while self.form.rowCount():
            self.form.removeRow(0)

        artist = ref.artist
        self.form.addRow(QLabel(f"{ref.kind}: {ref.label}"))
        adapter = get_adapter(ref.kind)
        if adapter is not None and adapter.build_form(ref, self):
            self._building_form = False
            return

        self.form.addRow(QLabel("No editor for this artist type yet."))

        self._building_form = False

    def _add_text(self, label: str, value: str, setter: Callable[[str], Any]) -> QLineEdit:
        widget = QLineEdit(str(value))
        widget._mve_commit = lambda: setter(widget.text())
        save_button = self._add_property_row(label, widget)
        widget.textEdited.connect(lambda _text: self._mark_pending_dirty(save_button))
        widget.editingFinished.connect(lambda: self._apply(lambda: setter(widget.text()), save_button))
        return widget

    def _add_float(
        self,
        label: str,
        value: float,
        setter: Callable[[float], Any],
        minimum: float,
        maximum: float,
        step: float,
        live: bool = True,
        decimals: int = 2,
        keyboard_tracking: bool = False,
    ) -> QDoubleSpinBox:
        widget = QDoubleSpinBox()
        widget.setRange(minimum, maximum)
        widget.setSingleStep(step)
        widget.setDecimals(decimals)
        widget.setKeyboardTracking(keyboard_tracking)
        widget.setValue(float(value))
        widget._mve_commit = lambda: setter(float(widget.value()))
        save_button = self._add_property_row(label, widget)
        if live:
            widget.valueChanged.connect(lambda new_value: self._apply(lambda: setter(float(new_value)), save_button))
        else:
            widget.editingFinished.connect(lambda: self._apply(lambda: setter(float(widget.value())), save_button))
        return widget

    def _add_bool(self, label: str, value: bool, setter: Callable[[bool], Any]) -> QCheckBox:
        widget = QCheckBox()
        widget.setChecked(bool(value))
        save_button = self._add_property_row(label, widget)
        widget.toggled.connect(lambda checked: self._apply(lambda: setter(bool(checked)), save_button))
        return widget

    def _add_choice(self, label: str, value: Any, choices: list[str], setter: Callable[[str], Any]) -> QComboBox:
        widget = QComboBox()
        widget.addItems(choices)
        text_value = str(value)
        index = widget.findText(text_value)
        if index < 0 and text_value in {"None", "none"}:
            index = widget.findText("None")
        if index >= 0:
            widget.setCurrentIndex(index)
        save_button = self._add_property_row(label, widget)
        widget.currentTextChanged.connect(lambda text: self._apply(lambda: setter(text), save_button))
        return widget

    def _add_color(self, label: str, value: Any, setter: Callable[[str], Any]) -> QPushButton:
        button = QPushButton(str(value))
        save_button = self._add_property_row(label, button)
        button.clicked.connect(lambda: self._pick_color(button, setter, save_button))
        return button

    def _add_button(self, label: str, callback: Callable[[], Any]) -> None:
        button = QPushButton(label)
        save_button = self._hidden_save_button(button)
        button.clicked.connect(lambda: self._apply(callback, save_button))
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(button, 1)
        self.form.addRow("", row)

    def _add_position_save_button(self, button_text: str = "Save position") -> None:
        self._position_save_button = None

    def _add_property_row(self, label: str, widget: QWidget) -> QPushButton:
        save_button = self._hidden_save_button(widget)
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(widget, 1)
        self.form.addRow(label, row)
        return save_button

    def _hidden_save_button(self, widget: QWidget) -> QPushButton:
        save_button = QPushButton()
        save_button.setVisible(False)
        save_button.setEnabled(False)
        save_button._mve_editor_widget = widget
        return save_button

    def _pick_color(self, button: QPushButton, setter: Callable[[str], Any], save_button: QPushButton) -> None:
        color = QColorDialog.getColor(parent=self)
        if not color.isValid():
            return
        value = color.name()
        button.setText(value)
        self._apply(lambda: setter(value), save_button)

    def _set_controls_enabled(self, widgets: list[QWidget], enabled: bool) -> None:
        for widget in widgets:
            widget.setEnabled(bool(enabled))

    def _capture_history_snapshot(self) -> dict[str, Any]:
        refs = [
            snapshot_artist(ref.kind, ref.path, ref.artist)
            for ref in iter_artist_refs(self.fig)
            if self._history_ref_supported(ref)
        ]
        return {"refs": refs}

    def _history_ref_supported(self, ref: ArtistRef) -> bool:
        if getattr(ref.artist, "_mve_kind", None) == "editor_handle":
            return False
        if hasattr(ref.artist, "get_zorder"):
            try:
                if float(ref.artist.get_zorder()) >= 1_000_000:
                    return False
            except (TypeError, ValueError):
                pass
        return ref.kind not in {"unsupported", "text_group"}

    def _push_undo_snapshot(self, snapshot: Optional[dict[str, Any]] = None) -> None:
        if self._building_form or self._suppress_dirty or self._restoring_history:
            return
        snapshot = snapshot or self._capture_history_snapshot()
        self._undo_stack.append(snapshot)
        if len(self._undo_stack) > self._history_limit:
            self._undo_stack = self._undo_stack[-self._history_limit :]
        self._redo_stack.clear()
        self._refresh_history_buttons()

    def _refresh_history_buttons(self) -> None:
        if hasattr(self, "undo_button"):
            self.undo_button.setEnabled(bool(self._undo_stack))
        if hasattr(self, "redo_button"):
            self.redo_button.setEnabled(bool(self._redo_stack))

    def _undo(self) -> None:
        if not self._undo_stack:
            return
        current = self._capture_history_snapshot()
        snapshot = self._undo_stack.pop()
        self._redo_stack.append(current)
        if len(self._redo_stack) > self._history_limit:
            self._redo_stack = self._redo_stack[-self._history_limit :]
        self._restore_history_snapshot(snapshot)
        self._mark_unexported_changes()
        self._refresh_history_buttons()
        self.status.setText("Undid last change.")

    def _redo(self) -> None:
        if not self._redo_stack:
            return
        current = self._capture_history_snapshot()
        snapshot = self._redo_stack.pop()
        self._undo_stack.append(current)
        if len(self._undo_stack) > self._history_limit:
            self._undo_stack = self._undo_stack[-self._history_limit :]
        self._restore_history_snapshot(snapshot)
        self._mark_unexported_changes()
        self._refresh_history_buttons()
        self.status.setText("Redid change.")

    def _restore_history_snapshot(self, snapshot: dict[str, Any]) -> None:
        preferred_path = self.current_ref.path if self.current_ref is not None else None
        target_snapshots = [item for item in snapshot.get("refs", []) if isinstance(item, dict)]
        target_paths = {tuple(item.get("path", ())) for item in target_snapshots}
        self._restoring_history = True
        old_suppress_dirty = self._suppress_dirty
        self._suppress_dirty = True
        self._clear_inline_text_editor()
        self._clear_hover_highlight(redraw=False)
        self._clear_selection_handles()
        try:
            self._remove_history_extras(target_paths)
            self.refs = iter_artist_refs(self.fig)
            ref_map = {tuple(ref.path): ref for ref in self.refs}
            for item in target_snapshots:
                path = tuple(item.get("path", ()))
                ref = ref_map.get(path)
                if ref is not None:
                    self._restore_snapshot(ref, item)
                    continue
                self._restore_missing_history_artist(item)
                self.refs = iter_artist_refs(self.fig)
                ref_map = {tuple(new_ref.path): new_ref for new_ref in self.refs}
        finally:
            self._suppress_dirty = old_suppress_dirty
            self._restoring_history = False
        self._refresh_refs_preserving_path(preferred_path)
        self.canvas.draw_idle()

    def _remove_history_extras(self, target_paths: set[tuple[Any, ...]]) -> None:
        for ref in iter_artist_refs(self.fig):
            if tuple(ref.path) in target_paths:
                continue
            if ref.kind not in {"shape", "textbox", "fill"}:
                continue
            try:
                ref.artist.remove()
            except Exception:
                pass

    def _restore_missing_history_artist(self, snapshot: dict[str, Any]) -> None:
        path = tuple(snapshot.get("path", ()))
        props = snapshot.get("props", {})
        if len(path) < 2 or path[0] != "axes" or not isinstance(props, dict):
            return
        try:
            ax = self.fig.axes[int(path[1])]
        except (IndexError, TypeError, ValueError):
            return
        kind = snapshot.get("kind")
        if kind == "shape":
            apply_shape_props(ax, props)
        elif kind == "textbox":
            apply_textbox_props(ax, props)
        elif kind == "fill":
            apply_fill_props(ax, props)

    def _rebuild_current_legend(self, **changes: Any) -> None:
        if self._rebuilding_legend:
            return
        if self.current_ref is None or self.current_ref.kind != "legend":
            return
        self._rebuild_legend(self.current_ref.artist, **changes)

    def _set_figure_size(self, width: Optional[float] = None, height: Optional[float] = None) -> None:
        width_now, height_now = self._figure_size()
        self._apply_figure_size(
            float(width_now if width is None else width),
            float(height_now if height is None else height),
        )

    def _set_figure_aspect(self, aspect: float) -> None:
        _width_now, height_now = self._figure_size()
        self._apply_figure_size(float(height_now) * float(aspect), float(height_now))

    def _figure_size(self) -> tuple[float, float]:
        if hasattr(self.fig, "_mve_width") and hasattr(self.fig, "_mve_height"):
            return float(self.fig._mve_width), float(self.fig._mve_height)
        width, height = self.fig.get_size_inches()
        return float(width), float(height)

    def _apply_figure_size(self, width: float, height: float) -> None:
        self.fig._mve_width = float(width)
        self.fig._mve_height = float(height)
        self.fig.set_size_inches(float(width), float(height), forward=False)
        self._update_canvas_display_size()

    def _enforce_saved_figure_size(self) -> None:
        width, height = self._figure_size()
        self.fig.set_size_inches(width, height, forward=False)
        self._update_canvas_display_size()

    def _initialize_figure_design_size(self) -> None:
        if not hasattr(self.fig, "_mve_width") or not hasattr(self.fig, "_mve_height"):
            width, height = self.fig.get_size_inches()
            self.fig._mve_width = float(width)
            self.fig._mve_height = float(height)
        self._update_canvas_display_size()

    def _update_canvas_display_size(self) -> None:
        if not hasattr(self, "canvas_host"):
            return
        design_width, design_height = self._figure_size()
        if design_width <= 0 or design_height <= 0:
            return
        viewport = self.canvas_scroll.viewport() if hasattr(self, "canvas_scroll") else self.canvas_host
        host_width = max(1, viewport.width() - 48)
        host_height = max(1, viewport.height() - 48)
        natural_width = max(1.0, design_width * PREVIEW_DPI)
        natural_height = max(1.0, design_height * PREVIEW_DPI)
        fit_scale = min(host_width / natural_width, host_height / natural_height)
        scale = fit_scale if self._preview_zoom is None else self._preview_zoom
        target_width = max(1, int(round(natural_width * scale)))
        target_height = max(1, int(round(natural_height * scale)))
        target_dpi = max(1.0, PREVIEW_DPI * scale)
        if not math.isclose(float(self.fig.dpi), target_dpi, rel_tol=0.001, abs_tol=0.001):
            self.fig.set_dpi(target_dpi)
        if self.canvas.width() != target_width or self.canvas.height() != target_height:
            self.canvas.setFixedSize(target_width, target_height)
            self.canvas_host.setMinimumSize(target_width + 48, target_height + 48)
        self._update_preview_zoom_label(scale)

    def _zoom_preview(self, factor: float) -> None:
        current_scale = self._current_preview_scale()
        self._preview_zoom = min(8.0, max(0.1, current_scale * float(factor)))
        self._update_canvas_display_size()
        self.canvas.draw_idle()

    def _fit_preview(self) -> None:
        self._preview_zoom = None
        self._update_canvas_display_size()
        self.canvas.draw_idle()

    def _actual_size_preview(self) -> None:
        self._preview_zoom = 1.0
        self._update_canvas_display_size()
        self.canvas.draw_idle()

    def _current_preview_scale(self) -> float:
        return max(0.1, float(self.fig.dpi) / PREVIEW_DPI)

    def _update_preview_zoom_label(self, scale: float) -> None:
        if not hasattr(self, "preview_zoom_label"):
            return
        suffix = " (Fit)" if self._preview_zoom is None else ""
        self.preview_zoom_label.setText(f"{scale * 100:.0f}%{suffix}")

    def _preview_fit_scale(self) -> float:
        design_width, design_height = self._figure_size()
        if design_width <= 0 or design_height <= 0:
            return 1.0
        viewport = self.canvas_scroll.viewport() if hasattr(self, "canvas_scroll") else self.canvas_host
        host_width = max(1, viewport.width() - 48)
        host_height = max(1, viewport.height() - 48)
        natural_width = max(1.0, design_width * PREVIEW_DPI)
        natural_height = max(1.0, design_height * PREVIEW_DPI)
        return min(host_width / natural_width, host_height / natural_height)

    def _set_axis_scale(self, axis: Any, axis_name: str, scale: str) -> None:
        ax = axis.axes
        if axis_name == "x":
            ax.set_xscale(scale)
        else:
            ax.set_yscale(scale)
        axis._mve_scale = scale
        self._apply_axis_ticks(axis, axis_name, self._axis_tick_start(axis), self._axis_tick_interval(axis), self._axis_tick_end(axis))

    def _set_axis_labelpad(self, axis: Any, value: float) -> None:
        axis.labelpad = float(value)
        axis._mve_labelpad = float(value)

    def _is_categorical_axis(self, axis: Any, axis_name: str) -> bool:
        ax = axis.axes
        if axis_name == "x" and any(getattr(container, "patches", None) for container in ax.containers):
            labels = [label.get_text() for label in axis.get_ticklabels() if label.get_text()]
            if labels and any(not self._is_float_text(label) for label in labels):
                return True
        if getattr(axis.units, "_mapping", None):
            return True
        return False

    def _is_float_text(self, value: str) -> bool:
        try:
            float(value.replace("\N{MINUS SIGN}", "-"))
        except ValueError:
            return False
        return True

    def _first_bar_patch(self, container: Any) -> Optional[Any]:
        return container.patches[0] if getattr(container, "patches", None) else None

    def _set_bar_visible(self, container: Any, visible: bool) -> None:
        for patch in container.patches:
            patch.set_visible(bool(visible))

    def _set_bar_facecolor(self, container: Any, color: str) -> None:
        for patch in container.patches:
            patch.set_facecolor(color)

    def _set_bar_edgecolor(self, container: Any, color: str) -> None:
        for patch in container.patches:
            patch.set_edgecolor(color)

    def _set_bar_linewidth(self, container: Any, linewidth: float) -> None:
        for patch in container.patches:
            patch.set_linewidth(float(linewidth))

    def _set_bar_alpha(self, container: Any, alpha: float) -> None:
        for patch in container.patches:
            patch.set_alpha(float(alpha))

    def _set_bar_hatch(self, container: Any, hatch: str) -> None:
        for patch in container.patches:
            patch.set_hatch(hatch)

    def _set_bar_width(self, container: Any, width: float) -> None:
        for patch in container.patches:
            self._set_bar_patch_width_centered(patch, width)

    def _set_bar_patch_width_centered(self, patch: Any, width: float) -> None:
        width = float(width)
        old_width = float(patch.get_width())
        center = float(patch.get_x()) + old_width / 2.0
        signed_width = math.copysign(width, old_width if old_width else 1.0)
        patch.set_width(signed_width)
        patch.set_x(center - signed_width / 2.0)

    def _first_text_in_group(self, texts: Any) -> Optional[Any]:
        for text in texts:
            if hasattr(text, "get_text"):
                return text
        return None

    def _set_text_group_color(self, texts: Any, color: str) -> None:
        for text in texts:
            text.set_color(color)

    def _set_text_group_fontsize(self, texts: Any, fontsize: float) -> None:
        for text in texts:
            text.set_fontsize(float(fontsize))

    def _set_text_group_fontweight(self, texts: Any, weight: str) -> None:
        for text in texts:
            text.set_fontweight(weight)

    def _set_text_group_fontstyle(self, texts: Any, style: str) -> None:
        for text in texts:
            text.set_fontstyle(style)

    def _apply_axis_ticks(self, axis: Any, axis_name: str, start: float, interval: float, end: Optional[float] = None) -> None:
        interval = float(interval)
        start = float(start)
        if end is not None:
            end = float(end)
        if (
            interval <= 0
            or not math.isfinite(interval)
            or not math.isfinite(start)
            or (end is not None and not math.isfinite(end))
        ):
            return
        ax = axis.axes
        current_low, current_high = ax.get_xlim() if axis_name == "x" else ax.get_ylim()
        inverted = current_high < current_low
        low, high = (current_high, current_low) if inverted else (current_low, current_high)

        max_ticks = 1000
        ticks: list[float] = []
        value = start
        low = value
        if end is not None:
            high = max(start, end)
        if high <= low:
            high = low + interval
        limit = high + interval * 0.5
        while value <= limit and len(ticks) < max_ticks:
            if math.isfinite(value):
                ticks.append(value)
            value += interval
        if len(ticks) >= max_ticks:
            high = ticks[-1]
            self.status.setText(f"Limited {axis_name.upper()} ticks to {max_ticks}; increase interval for a wider range.")

        if axis_name == "x":
            ax.set_xticks(ticks)
            ax.set_xlim((high, low) if inverted else (low, high))
        else:
            ax.set_yticks(ticks)
            ax.set_ylim((high, low) if inverted else (low, high))
        axis._mve_tick_start = start
        axis._mve_tick_end = high
        axis._mve_tick_interval = interval
        self._reapply_axis_tick_label_style(axis)

    def _apply_axis_tick_labels(
        self,
        axis: Any,
        fontsize: Optional[float] = None,
        color: Optional[str] = None,
        weight: Optional[str] = None,
        style: Optional[str] = None,
        rotation: Optional[float] = None,
    ) -> None:
        fontsize = self._axis_tick_label_prop(axis, "fontsize", 10.0) if fontsize is None else fontsize
        color = self._axis_tick_label_prop(axis, "color", "#000000") if color is None else color
        weight = self._axis_tick_label_prop(axis, "fontweight", "normal") if weight is None else weight
        style = self._axis_tick_label_prop(axis, "fontstyle", "normal") if style is None else style
        rotation = self._axis_tick_label_prop(axis, "rotation", 0.0) if rotation is None else rotation

        axis._mve_tick_label_fontsize = float(fontsize)
        axis._mve_tick_label_color = color
        axis._mve_tick_label_fontweight = weight
        axis._mve_tick_label_fontstyle = style
        axis._mve_tick_label_rotation = float(rotation)
        self._reapply_axis_tick_label_style(axis)

    def _reapply_axis_tick_label_style(self, axis: Any) -> None:
        if not hasattr(axis, "_mve_tick_label_fontsize"):
            return
        for label in axis.get_ticklabels():
            label.set_fontsize(float(axis._mve_tick_label_fontsize))
            label.set_color(axis._mve_tick_label_color)
            label.set_fontweight(axis._mve_tick_label_fontweight)
            label.set_fontstyle(axis._mve_tick_label_fontstyle)
            label.set_rotation(float(axis._mve_tick_label_rotation))

    def _axis_tick_start(self, axis: Any) -> float:
        if hasattr(axis, "_mve_tick_start"):
            return float(axis._mve_tick_start)
        ticks = self._finite_axis_ticks(axis)
        if ticks:
            return float(ticks[0])
        low, _high = axis.get_view_interval()
        return float(low)

    def _axis_tick_interval(self, axis: Any) -> float:
        if hasattr(axis, "_mve_tick_interval"):
            return float(axis._mve_tick_interval)
        ticks = self._finite_axis_ticks(axis)
        for left, right in zip(ticks, ticks[1:]):
            interval = right - left
            if interval > 0:
                return float(interval)
        return 1.0

    def _axis_tick_end(self, axis: Any) -> float:
        if hasattr(axis, "_mve_tick_end"):
            return float(axis._mve_tick_end)
        ticks = self._finite_axis_ticks(axis)
        if ticks:
            return float(ticks[-1])
        _low, high = axis.get_view_interval()
        return float(high)

    def _axis_tick_label_prop(self, axis: Any, prop: str, default: Any) -> Any:
        attr = f"_mve_tick_label_{prop}"
        if hasattr(axis, attr):
            return getattr(axis, attr)
        labels = axis.get_ticklabels()
        visible_labels = [label for label in labels if label.get_visible()]
        label = visible_labels[0] if visible_labels else (labels[0] if labels else None)
        if label is None:
            return default
        if prop == "fontsize":
            return float(label.get_fontsize())
        if prop == "color":
            return label.get_color()
        if prop == "fontweight":
            return label.get_fontweight()
        if prop == "fontstyle":
            return label.get_fontstyle()
        if prop == "rotation":
            return float(label.get_rotation())
        return default

    def _finite_axis_ticks(self, axis: Any) -> list[float]:
        ticks: list[float] = []
        for tick in axis.get_ticklocs():
            value = float(tick)
            if math.isfinite(value):
                ticks.append(value)
        return sorted(set(ticks))

    def _rebuild_legend(self, legend: Any, **changes: Any) -> None:
        if self._rebuilding_legend:
            return
        self._rebuilding_legend = True
        self._clear_hover_highlight(redraw=False)
        try:
            ax = legend.axes
            frame = legend.get_frame()
            texts = legend.get_texts()
            fontsize = texts[0].get_fontsize() if texts else None
            props = {
                "loc": getattr(legend, "_mve_loc", getattr(legend, "_loc", "best")),
                "ncols": getattr(legend, "_ncols", 1),
                "frameon": frame.get_visible(),
                "borderpad": legend.borderpad,
                "labelspacing": legend.labelspacing,
                "handlelength": legend.handlelength,
                "handletextpad": legend.handletextpad,
                "borderaxespad": legend.borderaxespad,
                "columnspacing": legend.columnspacing,
            }
            if hasattr(legend, "_mve_bbox_to_anchor"):
                props["bbox_to_anchor"] = legend._mve_bbox_to_anchor
            if fontsize is not None:
                props["fontsize"] = fontsize
            props.update(changes)
            if props.get("bbox_to_anchor") is None:
                props.pop("bbox_to_anchor", None)
            handles, labels = self._legend_handles_labels(legend)
            if handles and labels:
                props["handles"] = [self._clone_legend_handle(handle) for handle in handles]
                props["labels"] = labels

            visible = legend.get_visible()
            frame_alpha = frame.get_alpha()
            facecolor = frame.get_facecolor()
            edgecolor = frame.get_edgecolor()
            frame_linewidth = frame.get_linewidth()
            draggable = legend.get_draggable() is not None

            try:
                legend.remove()
            except Exception:
                pass
            new_legend = ax.legend(**props)
            new_legend.set_visible(visible)
            new_legend.set_draggable(draggable, use_blit=False, update="bbox")
            new_frame = new_legend.get_frame()
            new_frame.set_alpha(frame_alpha)
            new_frame.set_facecolor(facecolor)
            new_frame.set_edgecolor(edgecolor)
            new_frame.set_linewidth(frame_linewidth)
            if "bbox_to_anchor" in props:
                new_legend._mve_bbox_to_anchor = props["bbox_to_anchor"]
                new_legend._mve_loc = props["loc"]
            elif hasattr(new_legend, "_mve_bbox_to_anchor"):
                delattr(new_legend, "_mve_bbox_to_anchor")
                new_legend._mve_loc = props["loc"]

            self._replace_current_legend_ref(new_legend)
        finally:
            self._rebuilding_legend = False

    def _legend_handles_labels(self, legend: Any) -> tuple[list[Any], list[str]]:
        handles = getattr(legend, "legend_handles", None)
        if handles is None:
            handles = getattr(legend, "legendHandles", [])
        labels = [text.get_text() for text in legend.get_texts()]
        return list(handles), labels

    def _clone_legend_handle(self, handle: Any) -> Any:
        try:
            cloned = copy.copy(handle)
        except Exception:
            return handle
        if hasattr(cloned, "axes"):
            cloned.axes = None
        if hasattr(cloned, "figure"):
            cloned.figure = None
        return cloned

    def _capture_current_legend_position(self, legend: Any) -> None:
        ax = legend.axes
        self.canvas.draw()
        renderer = self.canvas.get_renderer()
        bbox = legend.get_window_extent(renderer=renderer)
        axes_bbox = bbox.transformed(ax.transAxes.inverted())
        self._rebuild_legend(
            legend,
            loc="upper left",
            bbox_to_anchor=(axes_bbox.x0, axes_bbox.y1),
            borderaxespad=0.0,
        )

    def _ensure_legend_axes_anchor(self, legend: Any) -> None:
        if hasattr(legend, "_mve_bbox_to_anchor"):
            return
        ax = legend.axes
        try:
            self.canvas.draw()
            renderer = self.canvas.get_renderer()
            bbox = legend.get_window_extent(renderer=renderer)
            axes_bbox = bbox.transformed(ax.transAxes.inverted())
        except Exception:
            return
        legend._mve_bbox_to_anchor = (float(axes_bbox.x0), float(axes_bbox.y1))
        legend._mve_loc = "upper left"
        legend.borderaxespad = 0.0

    def _replace_current_legend_ref(self, legend: Any) -> None:
        self._clear_hover_highlight(redraw=False)
        self.refs = iter_artist_refs(self.fig)
        self._configure_picking()
        for row in range(self.object_list.count()):
            item = self.object_list.item(row)
            ref = item.data(Qt.UserRole)
            if ref.kind == "legend":
                updated_ref = next(
                    new_ref
                    for new_ref in self.refs
                    if new_ref.kind == "legend" and new_ref.path == ref.path
                )
                item.setData(Qt.UserRole, updated_ref)
                if self.current_ref is not None and self.current_ref.path == updated_ref.path:
                    self.current_ref = updated_ref
                    self.pinned_ref = updated_ref
                    self.hover_ref = None
                    self._set_hover_highlight(updated_ref)
                    if not self._suppress_dirty:
                        self._mark_dirty(self._active_save_button)
                    self.status.setText("Legend layout updated")
                return

    def _apply(self, callback: Callable[[], Any], save_button: Optional[QPushButton] = None) -> None:
        if self._building_form:
            return
        view_state = self._capture_preview_view()
        self._active_save_button = save_button
        try:
            self._push_undo_snapshot()
            callback()
            self._sync_current_line_legend_handle()
            self._sync_current_bar_legend_handle()
            self._sync_current_scatter_legend_handle()
            self._auto_save_current_state()
        finally:
            self._active_save_button = None
        self._redraw("Updated", view_state=view_state)

    def _sync_current_line_legend_handle(self) -> None:
        if self.current_ref is None or self.current_ref.kind != "line":
            return
        line = self.current_ref.artist
        ax = line.axes
        legend = ax.get_legend()
        if legend is None:
            return

        handles = getattr(legend, "legend_handles", None)
        if handles is None:
            handles = getattr(legend, "legendHandles", [])
        try:
            line_index = list(ax.lines).index(line)
            handle = list(handles)[line_index]
        except (ValueError, IndexError, TypeError):
            return

        self._copy_line_style_to_legend_handle(line, handle)

    def _copy_line_style_to_legend_handle(self, line: Any, handle: Any) -> None:
        for getter_name, setter_name in [
            ("get_color", "set_color"),
            ("get_linewidth", "set_linewidth"),
            ("get_linestyle", "set_linestyle"),
            ("get_marker", "set_marker"),
            ("get_markersize", "set_markersize"),
            ("get_markerfacecolor", "set_markerfacecolor"),
            ("get_markeredgecolor", "set_markeredgecolor"),
            ("get_markeredgewidth", "set_markeredgewidth"),
            ("get_alpha", "set_alpha"),
        ]:
            if hasattr(line, getter_name) and hasattr(handle, setter_name):
                getattr(handle, setter_name)(getattr(line, getter_name)())

    def _sync_current_bar_legend_handle(self) -> None:
        if self.current_ref is None or self.current_ref.kind != "bar":
            return
        container = self.current_ref.artist
        first_patch = self._first_bar_patch(container)
        if first_patch is None:
            return
        ax = first_patch.axes
        legend = ax.get_legend()
        if legend is None:
            return

        handles = getattr(legend, "legend_handles", None)
        if handles is None:
            handles = getattr(legend, "legendHandles", [])
        label = container.get_label()
        legend_texts = [text.get_text() for text in legend.get_texts()]
        try:
            handle = list(handles)[legend_texts.index(label)]
        except (ValueError, IndexError, TypeError):
            return
        self._copy_bar_style_to_legend_handle(first_patch, handle)

    def _copy_bar_style_to_legend_handle(self, patch: Any, handle: Any) -> None:
        for getter_name, setter_name in [
            ("get_facecolor", "set_facecolor"),
            ("get_edgecolor", "set_edgecolor"),
            ("get_linewidth", "set_linewidth"),
            ("get_alpha", "set_alpha"),
            ("get_hatch", "set_hatch"),
        ]:
            if hasattr(patch, getter_name) and hasattr(handle, setter_name):
                getattr(handle, setter_name)(getattr(patch, getter_name)())

    def _sync_current_scatter_legend_handle(self) -> None:
        if self.current_ref is None or self.current_ref.kind != "scatter":
            return
        scatter = self.current_ref.artist
        ax = scatter.axes
        legend = ax.get_legend()
        if legend is None:
            return

        handles = getattr(legend, "legend_handles", None)
        if handles is None:
            handles = getattr(legend, "legendHandles", [])
        legend_texts = [text.get_text() for text in legend.get_texts()]
        label = scatter.get_label()
        try:
            handle = list(handles)[legend_texts.index(label)]
        except (ValueError, IndexError, TypeError):
            return
        self._copy_scatter_style_to_legend_handle(scatter, handle)

    def _copy_scatter_style_to_legend_handle(self, scatter: Any, handle: Any) -> None:
        facecolors = scatter.get_facecolors() if hasattr(scatter, "get_facecolors") else []
        edgecolors = scatter.get_edgecolors() if hasattr(scatter, "get_edgecolors") else []
        linewidths = scatter.get_linewidths() if hasattr(scatter, "get_linewidths") else []
        sizes = scatter.get_sizes() if hasattr(scatter, "get_sizes") else []
        facecolor = facecolors[0] if len(facecolors) else None
        edgecolor = edgecolors[0] if len(edgecolors) else None
        linewidth = float(linewidths[0]) if len(linewidths) else None
        size = float(sizes[0]) if len(sizes) else None
        alpha = scatter.get_alpha() if hasattr(scatter, "get_alpha") else None
        paths = scatter.get_paths() if hasattr(scatter, "get_paths") else []

        if hasattr(handle, "set_markerfacecolor"):
            if paths and hasattr(handle, "set_marker"):
                handle.set_marker(self._scatter_marker_name(scatter))
            if facecolor is not None:
                handle.set_markerfacecolor(facecolor)
            if edgecolor is not None and hasattr(handle, "set_markeredgecolor"):
                handle.set_markeredgecolor(edgecolor)
            if linewidth is not None and hasattr(handle, "set_markeredgewidth"):
                handle.set_markeredgewidth(linewidth)
            if size is not None and hasattr(handle, "set_markersize"):
                handle.set_markersize(math.sqrt(size))
            if alpha is not None and hasattr(handle, "set_alpha"):
                handle.set_alpha(alpha)
            return

        if paths and hasattr(handle, "set_paths"):
            handle.set_paths(paths)

        for getter_name, setter_name in [
            ("get_facecolors", "set_facecolor"),
            ("get_edgecolors", "set_edgecolor"),
            ("get_linewidths", "set_linewidth"),
            ("get_sizes", "set_sizes"),
            ("get_alpha", "set_alpha"),
        ]:
            if not hasattr(scatter, getter_name) or not hasattr(handle, setter_name):
                continue
            value = getattr(scatter, getter_name)()
            if getter_name in {"get_facecolors", "get_edgecolors"}:
                if value is None or len(value) == 0:
                    continue
                value = value[0]
            elif getter_name == "get_linewidths":
                if value is None or len(value) == 0:
                    continue
                value = float(value[0])
            elif getter_name == "get_sizes":
                if value is None or len(value) == 0:
                    continue
                value = [float(value[0])]
            getattr(handle, setter_name)(value)

    def _scatter_marker_name(self, scatter: Any) -> str:
        paths = scatter.get_paths() if hasattr(scatter, "get_paths") else []
        if not paths:
            return "o"
        path = paths[0]
        for marker in ["o", "s", "^", "v", "D", "x", "+", "*", ".", "P", "X"]:
            marker_path = _marker_path(marker)
            if path.vertices.shape == marker_path.vertices.shape and (path.vertices == marker_path.vertices).all():
                return marker
        return "o"

    def _mark_dirty(self, save_button: Optional[QPushButton] = None) -> None:
        if self._building_form or self._suppress_dirty:
            return
        self._auto_save_current_state()
        return

    def _mark_pending_dirty(self, save_button: Optional[QPushButton] = None) -> None:
        if self._building_form or self._suppress_dirty:
            return
        self.status.setText("Text changed. Press Enter to apply and auto-save it.")

    def _mark_position_dirty(self) -> None:
        if self._building_form or self._suppress_dirty:
            return
        self._auto_save_current_state(message="Placement auto-saved.")

    def _mark_unexported_changes(self) -> None:
        if self._building_form or self._suppress_dirty:
            return
        self._has_unexported_changes = True

    def _auto_save_current_state(self, message: Optional[str] = None) -> None:
        if self._building_form or self._suppress_dirty or self.current_ref is None:
            return
        self._mark_unexported_changes()
        self._committed_snapshot = snapshot_artist(
            self.current_ref.kind,
            self.current_ref.path,
            self.current_ref.artist,
        )
        self._dirty = False
        self._dirty_widgets = set()
        self._legend_position_dirty = False
        self.status.setText(message or f"Auto-saved: {self.current_ref.label}")

    def _legacy_mark_dirty(self, save_button: Optional[QPushButton] = None) -> None:
        if self._building_form or self._suppress_dirty:
            return
        self._dirty = True
        if save_button is not None and hasattr(save_button, "_mve_editor_widget"):
            widget = getattr(save_button, "_mve_editor_widget", None)
            if isinstance(widget, QWidget):
                self._dirty_widgets.add(widget)
        if save_button is not None:
            save_button.setEnabled(True)
            save_button.setStyleSheet("font-weight: 700; background: #ffcc00;")
        self.status.setText("Preview auto-saved.")

    def _save_current_changes(self, editor_widget: Optional[QWidget] = None) -> None:
        if self.current_ref is None:
            return
        old_suppress_dirty = self._suppress_dirty
        self._suppress_dirty = True
        try:
            self._commit_editor(editor_widget)
            for widget in list(self._dirty_widgets):
                if widget is not editor_widget:
                    self._commit_editor(widget)
            QApplication.processEvents()
        finally:
            self._suppress_dirty = old_suppress_dirty
        self._committed_snapshot = snapshot_artist(
            self.current_ref.kind,
            self.current_ref.path,
            self.current_ref.artist,
        )
        self._dirty = False
        self._dirty_widgets = set()
        for button in self._save_buttons:
            button.setEnabled(False)
            button.setStyleSheet("")
        if self._position_save_button is not None:
            self._position_save_button.setEnabled(False)
            self._position_save_button.setStyleSheet("")
        self._legend_position_dirty = False
        self.status.setText(f"Saved: {self.current_ref.label}")

    def _save_current_changes_from_sender(self) -> None:
        sender = self.sender()
        editor_widget = getattr(sender, "_mve_editor_widget", None)
        self._save_current_changes(editor_widget)

    def _save_current_position(self) -> None:
        if self.current_ref is not None and self.current_ref.kind == "legend":
            self._save_current_legend_position()
            return
        self._save_current_changes()

    def _commit_editor(self, widget: Optional[QWidget] = None) -> None:
        if widget is not None and not isinstance(widget, QWidget):
            widget = None
        widget = widget or QApplication.focusWidget()
        if isinstance(widget, QDoubleSpinBox):
            widget.interpretText()
            if hasattr(widget, "_mve_commit"):
                widget._mve_commit()
            if widget.hasFocus():
                widget.clearFocus()
        elif isinstance(widget, QLineEdit):
            if hasattr(widget, "_mve_commit"):
                widget._mve_commit()
            else:
                widget.editingFinished.emit()
            if widget.hasFocus():
                widget.clearFocus()

    def _commit_all_form_editors(self, skip: Optional[QWidget] = None) -> None:
        for widget in self.form_host.findChildren(QDoubleSpinBox):
            if widget is skip:
                continue
            widget.interpretText()
            if hasattr(widget, "_mve_commit"):
                widget._mve_commit()
        for widget in self.form_host.findChildren(QLineEdit):
            if widget is skip:
                continue
            if isinstance(widget.parent(), QDoubleSpinBox):
                continue
            if hasattr(widget, "_mve_commit"):
                widget._mve_commit()
            else:
                widget.editingFinished.emit()

    def _save_current_legend_position(self) -> None:
        if self.current_ref is None or self.current_ref.kind != "legend":
            return
        self._suppress_dirty = True
        try:
            self._capture_current_legend_position(self.current_ref.artist)
        finally:
            self._suppress_dirty = False
        self._committed_snapshot = snapshot_artist(
            self.current_ref.kind,
            self.current_ref.path,
            self.current_ref.artist,
        )
        self._dirty = False
        self._legend_position_dirty = False
        self._mark_unexported_changes()
        for button in self._save_buttons:
            button.setEnabled(False)
            button.setStyleSheet("")
        if self._position_save_button is not None:
            self._position_save_button.setEnabled(False)
            self._position_save_button.setStyleSheet("")
        self.status.setText("Saved: legend position")

    def _discard_unsaved_preview(self) -> None:
        if not self._dirty or self.current_ref is None or self._committed_snapshot is None:
            return
        self._clear_hover_highlight(redraw=False)
        self._clear_selection_handles()
        self._restore_snapshot(self.current_ref, self._committed_snapshot)
        self._dirty = False
        self._legend_position_dirty = False
        if self._position_save_button is not None:
            self._position_save_button.setEnabled(False)
            self._position_save_button.setStyleSheet("")
        self.refs = iter_artist_refs(self.fig)
        self._configure_picking()
        self.canvas.draw_idle()

    def _restore_snapshot(self, ref: ArtistRef, snapshot: dict[str, Any]) -> None:
        artist = ref.artist
        props = snapshot["props"]
        kind = snapshot["kind"]
        if kind == "figure":
            self._apply_figure_size(float(props["width"]), float(props["height"]))
        elif kind == "axes":
            artist.set_facecolor(props["facecolor"])
            artist.set_xlabel(props["xlabel"])
            artist.set_ylabel(props["ylabel"])
            artist.set_title(props["title"])
            artist.grid(bool(props["xgrid"]), axis="x")
            artist.grid(bool(props["ygrid"]), axis="y")
        elif kind == "line":
            if "xdata" in props and "ydata" in props:
                artist.set_data(props["xdata"], props["ydata"])
                artist._mve_xdata = list(props["xdata"])
                artist._mve_ydata = list(props["ydata"])
            artist.set_visible(props.get("visible", True))
            artist.set_color(props["color"])
            artist.set_linewidth(props["linewidth"])
            artist.set_linestyle(props["linestyle"])
            artist.set_drawstyle(props.get("drawstyle", "default"))
            artist.set_marker(props["marker"])
            artist.set_markersize(props["markersize"])
            artist.set_markerfacecolor(props.get("markerfacecolor", props["color"]))
            artist.set_markeredgecolor(props.get("markeredgecolor", props["color"]))
            artist.set_markeredgewidth(props.get("markeredgewidth", 1.0))
            artist.set_alpha(props["alpha"])
            artist.set_label(props["label"])
        elif kind == "scatter":
            artist.set_visible(props["visible"])
            artist.set_label(props["label"])
            artist.set_paths([_marker_path(props.get("marker", "o"))])
            artist.set_facecolor(props["facecolor"])
            artist.set_edgecolor(props["edgecolor"])
            artist.set_linewidth(props["linewidth"])
            artist.set_sizes([props["size"]] * max(1, len(artist.get_offsets())))
            artist.set_alpha(props["alpha"])
        elif kind == "bar":
            self._restore_bar_snapshot(artist, props)
        elif kind == "wedge":
            artist.set_visible(props["visible"])
            artist.set_facecolor(props["facecolor"])
            artist.set_edgecolor(props["edgecolor"])
            artist.set_linewidth(props["linewidth"])
            artist.set_alpha(props["alpha"])
            artist.set_hatch(props.get("hatch", ""))
            artist.set_center(tuple(props["center"]))
            artist.set_radius(props["radius"])
            artist.set_width(props.get("width"))
            artist.set_theta1(props["theta1"])
            artist.set_theta2(props["theta2"])
        elif kind == "patch":
            artist.set_visible(props["visible"])
            artist.set_facecolor(props["facecolor"])
            artist.set_edgecolor(props["edgecolor"])
            artist.set_linewidth(props["linewidth"])
            artist.set_alpha(props["alpha"])
            artist.set_hatch(props.get("hatch", ""))
        elif kind == "shape":
            apply_shape_props(artist.axes, props, artist)
        elif kind == "textbox":
            apply_textbox_props(artist.axes, props, artist)
        elif kind == "fill":
            apply_fill_props(artist.axes, props, artist)
        elif kind == "arrow":
            apply_arrow_props(artist, props)
        elif kind == "text":
            artist.set_text(props["text"])
            if "x" in props and "y" in props:
                artist.set_position((props["x"], props["y"]))
            if "rotation" in props:
                artist.set_rotation(props["rotation"])
            artist.set_color(props["color"])
            artist.set_fontsize(props["fontsize"])
            artist.set_fontweight(props["fontweight"])
            artist.set_fontstyle(props["fontstyle"])
        elif kind == "text_group":
            self._set_text_group_color(artist, props["color"])
            self._set_text_group_fontsize(artist, props["fontsize"])
            self._set_text_group_fontweight(artist, props["fontweight"])
            self._set_text_group_fontstyle(artist, props["fontstyle"])
        elif kind == "axis":
            axis_name = props["axis"]
            if props.get("labelpad_explicit", True):
                self._set_axis_labelpad(artist, props["labelpad"])
            if props.get("scale_explicit", True):
                self._set_axis_scale(artist, axis_name, props["scale"])
            if props.get("ticks_explicit", True):
                self._apply_axis_ticks(artist, axis_name, props["tick_start"], props["tick_interval"], props.get("tick_end"))
            if props.get("tick_labels_explicit", True):
                self._apply_axis_tick_labels(
                    artist,
                    fontsize=props["tick_label_fontsize"],
                    color=props["tick_label_color"],
                    weight=props["tick_label_weight"],
                    style=props["tick_label_style"],
                    rotation=props["tick_label_rotation"],
                )
        elif kind == "legend":
            self._restore_legend_snapshot(artist, props)
        elif kind == "spine":
            artist.set_visible(props["visible"])
            artist.set_edgecolor(props["color"])
            artist.set_linewidth(props["linewidth"])

    def _restore_bar_snapshot(self, container: Any, props: dict[str, Any]) -> None:
        container.set_label(props["label"])
        for index, patch in enumerate(container.patches):
            patch.set_visible(self._bar_list_value(props, "visible", index))
            patch.set_facecolor(self._bar_list_value(props, "facecolor", index))
            patch.set_edgecolor(self._bar_list_value(props, "edgecolor", index))
            patch.set_linewidth(self._bar_list_value(props, "linewidth", index))
            patch.set_alpha(self._bar_list_value(props, "alpha", index))
            patch.set_hatch(self._bar_list_value(props, "hatch", index) or "")
            self._set_bar_patch_width_centered(patch, self._bar_list_value(props, "width", index))

    def _bar_list_value(self, props: dict[str, Any], name: str, index: int) -> Any:
        plural_name = "hatches" if name == "hatch" else f"{name}s"
        values = props.get(plural_name)
        if values is None:
            return props.get(name)
        if not values:
            return None
        return values[min(index, len(values) - 1)]

    def _restore_legend_snapshot(self, legend: Any, props: dict[str, Any]) -> None:
        changes = {
            "loc": props["loc"],
            "bbox_to_anchor": props["bbox_to_anchor"],
            "ncols": props["ncols"],
            "fontsize": props["fontsize"],
            "frameon": props["frame_on"],
            "borderpad": props["borderpad"],
            "labelspacing": props["labelspacing"],
            "handlelength": props["handlelength"],
            "handletextpad": props["handletextpad"],
            "borderaxespad": props["borderaxespad"],
            "columnspacing": props["columnspacing"],
        }
        self._dirty = False
        self._suppress_dirty = True
        try:
            self._rebuild_legend(legend, **changes)
            if self.current_ref is not None and self.current_ref.kind == "legend":
                restored = self.current_ref.artist
                restored.set_visible(props["visible"])
                frame = restored.get_frame()
                frame.set_visible(props["frame_on"])
                frame.set_alpha(props["frame_alpha"])
                frame.set_facecolor(props["facecolor"])
                frame.set_edgecolor(props["edgecolor"])
                frame.set_linewidth(props.get("frame_linewidth", 1.0))
        finally:
            self._suppress_dirty = False

    def _redraw(self, message: str, view_state: Optional[dict[str, float]] = None) -> None:
        view_state = view_state or self._capture_preview_view()
        self._fit_figure_to_canvas(adjust_layout=True)
        self._restore_preview_view(view_state)
        self.canvas.draw_idle()
        QTimer.singleShot(0, lambda: self._restore_preview_view(view_state))
        self.status.setText(message)

    def _capture_preview_view(self) -> Optional[dict[str, float]]:
        if not hasattr(self, "canvas_scroll"):
            return None
        hbar = self.canvas_scroll.horizontalScrollBar()
        vbar = self.canvas_scroll.verticalScrollBar()
        scale = self._current_preview_scale()
        fit_scale = self._preview_fit_scale()
        is_fit = self._preview_zoom is None and math.isclose(scale, fit_scale, rel_tol=0.02, abs_tol=0.02)
        return {
            "h_value": float(hbar.value()),
            "v_value": float(vbar.value()),
            "h_ratio": self._scroll_ratio(hbar),
            "v_ratio": self._scroll_ratio(vbar),
            "scale": scale,
            "is_fit": float(is_fit),
        }

    def _restore_preview_view(self, state: Optional[dict[str, float]]) -> None:
        if state is None or not hasattr(self, "canvas_scroll"):
            return
        if not bool(state.get("is_fit", 0.0)):
            self._preview_zoom = float(state["scale"])
            self._update_canvas_display_size()
        hbar = self.canvas_scroll.horizontalScrollBar()
        vbar = self.canvas_scroll.verticalScrollBar()
        self._restore_scrollbar(hbar, state["h_value"], state["h_ratio"])
        self._restore_scrollbar(vbar, state["v_value"], state["v_ratio"])

    def _scroll_ratio(self, scrollbar: Any) -> float:
        maximum = scrollbar.maximum()
        if maximum <= 0:
            return 0.0
        return float(scrollbar.value()) / float(maximum)

    def _restore_scrollbar(self, scrollbar: Any, value: float, ratio: float) -> None:
        maximum = scrollbar.maximum()
        if maximum <= 0:
            scrollbar.setValue(0)
            return
        target = value if value <= maximum else ratio * maximum
        scrollbar.setValue(int(round(target)))

    def _fit_figure_to_canvas(self, adjust_layout: bool = False) -> None:
        if self._fit_in_progress:
            return
        self._fit_in_progress = True
        try:
            self._enforce_saved_figure_size()
            if adjust_layout:
                if self._base_subplotpars is None:
                    try:
                        with warnings.catch_warnings():
                            warnings.simplefilter("ignore", UserWarning)
                            self.fig.tight_layout()
                    except Exception:
                        pass
                    self._capture_base_subplotpars()
                else:
                    self._restore_base_subplotpars()
            self._update_canvas_display_size()
        finally:
            self._fit_in_progress = False

    def _capture_base_subplotpars(self) -> tuple[float, float, float, float]:
        if self._base_subplotpars is None:
            params = self.fig.subplotpars
            self._base_subplotpars = (params.left, params.right, params.bottom, params.top)
        return self._base_subplotpars

    def _restore_base_subplotpars(self) -> None:
        left, right, bottom, top = self._capture_base_subplotpars()
        try:
            self.fig.subplots_adjust(left=left, right=right, bottom=bottom, top=top)
        except Exception:
            pass

    def _export(self) -> None:
        self._discard_unsaved_preview()
        pinned_ref = self.pinned_ref
        self._clear_selection_handles()
        self._clear_hover_highlight()
        path = export_style(self.fig, self.export_path, source=_source_metadata(self.source_path))
        self._has_unexported_changes = False
        if pinned_ref is not None:
            self._set_hover_highlight(pinned_ref)
            self._show_selection_handles(pinned_ref)
        self.status.setText(f"Exported {path}")
        QMessageBox.information(self, "Export complete", f"Exported {path}")

    def _export_as(self) -> None:
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Export style patch",
            str(self.export_path),
            "Python files (*.py)",
        )
        if filename:
            self.export_path = Path(filename)
            self._export()

    def _export_figure(self) -> None:
        filename, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export figure",
            self._default_figure_export_path(),
            "PDF files (*.pdf);;PNG files (*.png);;SVG files (*.svg);;JPEG files (*.jpg *.jpeg);;TIFF files (*.tif *.tiff);;All files (*)",
        )
        if not filename:
            return
        path = Path(filename)
        if not path.suffix:
            path = path.with_suffix(self._suffix_for_filter(selected_filter))
        try:
            self._save_figure(path)
        except Exception as exc:
            QMessageBox.warning(self, "Figure export failed", str(exc))
            return
        self.status.setText(f"Exported figure {path}")
        QMessageBox.information(self, "Figure export complete", f"Exported {path}")

    def _default_figure_export_path(self) -> str:
        stem = self.export_path.stem
        if stem.endswith("_style_patch"):
            stem = stem[: -len("_style_patch")]
        return str(self.export_path.with_name(f"{stem}.pdf"))

    def _suffix_for_filter(self, selected_filter: str) -> str:
        if "*.png" in selected_filter:
            return ".png"
        if "*.svg" in selected_filter:
            return ".svg"
        if "*.jpg" in selected_filter or "*.jpeg" in selected_filter:
            return ".jpg"
        if "*.tif" in selected_filter or "*.tiff" in selected_filter:
            return ".tiff"
        return ".pdf"

    def _save_figure(self, path: Union[str, Path]) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        highlighted_ref = self.hover_ref
        selected_ref = self.current_ref
        self._clear_selection_handles()
        if highlighted_ref is not None:
            self._clear_hover_highlight(redraw=False)
        try:
            self._fit_figure_to_canvas()
            self.fig.savefig(path, dpi=300, bbox_inches="tight")
        finally:
            if highlighted_ref is not None:
                self._set_hover_highlight(highlighted_ref)
            self._show_selection_handles(selected_ref)
        return path

    def _delete_selected(self) -> None:
        ref = self.pinned_ref or self.current_ref
        if ref is None:
            QMessageBox.information(self, "Nothing selected", "Select an object first.")
            return

        if ref.kind in {"figure", "axes"}:
            QMessageBox.information(
                self,
                "Object cannot be deleted",
                "This prototype does not delete whole figures or axes yet.",
            )
            return

        self._push_undo_snapshot()
        self._clear_hover_highlight()
        self._clear_selection_handles()
        self.pinned_ref = None
        self.current_ref = None

        try:
            self._delete_ref(ref)
        except Exception as exc:
            QMessageBox.warning(self, "Delete failed", str(exc))
            return
        self._mark_unexported_changes()

        self.refs = iter_artist_refs(self.fig)
        self._configure_picking()
        self._populate_object_list()
        if self.refs:
            self._selecting_programmatically = True
            try:
                self.object_list.setCurrentRow(0)
            finally:
                self._selecting_programmatically = False
        self._redraw(f"Deleted: {ref.label}")

    def _delete_ref(self, ref: ArtistRef) -> None:
        adapter = get_adapter(ref.kind)
        if adapter is None:
            raise ValueError(f"Delete is not supported for {ref.kind!r}")
        adapter.delete(ref)
