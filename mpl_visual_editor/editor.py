"""PySide6 editor window for Matplotlib figures."""

from __future__ import annotations

import copy
import inspect
import importlib.util
import math
import sys
import warnings
from pathlib import Path
from typing import Any, Callable

import matplotlib

matplotlib.use("QtAgg")

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from PySide6.QtCore import Qt, QTimer
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
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from .exporter import export_style
from .adapters.registry import get_adapter
from .inspector import iter_artist_refs
from .refs import ArtistRef
from .snapshots import snapshot_artist


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
    export_path: str | Path | None = None,
    apply_existing: bool = True,
) -> None:
    """Open a visual editor for an existing Matplotlib figure.

    When ``apply_existing`` is true, an existing patch at ``export_path`` is
    applied first. This makes the generated patch a reusable style layer: open
    the same plot again, continue editing from the last exported result, then
    overwrite the same patch.
    """

    patch_error = None
    patch_warning = None
    source_path = _infer_calling_script()
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


def _default_export_path(source_path: Path | None) -> Path:
    if source_path is None:
        return Path("style_patch.py")
    return source_path.with_name(f"{source_path.stem}_style_patch.py")


def _source_metadata(source_path: Path | None) -> str | None:
    if source_path is None:
        return None
    try:
        return source_path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return source_path.resolve().as_posix()


def _normalize_source_metadata(value: str) -> str:
    return value.replace("\\", "/").strip()


def _apply_existing_style_patch(fig: Figure, patch_path: str | Path) -> str | None:
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
    apply_style(fig)
    source = getattr(module, "MPL_VISUAL_EDITOR_SOURCE", None)
    return str(source) if source is not None else None


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
        export_path: str | Path = "style_patch.py",
        source_path: Path | None = None,
    ) -> None:
        super().__init__()
        self.fig = fig
        self.export_path = Path(export_path)
        self.source_path = source_path
        self.refs: list[ArtistRef] = iter_artist_refs(fig)
        self.current_ref: ArtistRef | None = None
        self.hover_ref: ArtistRef | None = None
        self.pinned_ref: ArtistRef | None = None
        self._highlight_state: dict[str, Any] | None = None
        self._building_form = False
        self._selecting_programmatically = False
        self._rebuilding_legend = False
        self._suppress_dirty = False
        self._committed_snapshot: dict[str, Any] | None = None
        self._dirty = False
        self._save_buttons: list[QPushButton] = []
        self._dirty_widgets: set[QWidget] = set()
        self._active_save_button: QPushButton | None = None
        self._position_save_button: QPushButton | None = None
        self._legend_press_xy: tuple[float, float] | None = None
        self._legend_position_dirty = False
        self._fit_in_progress = False
        self._base_subplotpars: tuple[float, float, float, float] | None = None

        self.setWindowTitle("Matplotlib Visual Style Editor")
        self.resize(1180, 760)

        self.canvas = FigureCanvasQTAgg(fig)
        self.canvas.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.canvas.setMinimumSize(1, 1)
        self.toolbar = NavigationToolbar2QT(self.canvas, self)
        self.canvas_host = _AspectCanvasHost(self)
        self.object_list = QListWidget()
        self.form_host = QWidget()
        self.form = QFormLayout(self.form_host)
        self.status = QLabel("Ready")

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
        canvas_host_layout = QVBoxLayout(self.canvas_host)
        canvas_host_layout.setContentsMargins(24, 24, 24, 24)
        canvas_host_layout.addWidget(self.canvas, 0, Qt.AlignCenter)
        plot_layout.addWidget(self.canvas_host, 1)

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
            elif ref.kind == "bar":
                for patch in artist.patches:
                    if hasattr(patch, "set_picker"):
                        patch.set_picker(True)
            elif ref.kind == "unsupported" and hasattr(artist, "set_picker"):
                artist.set_picker(True)

    def _refresh_refs(self) -> None:
        self.pinned_ref = None
        self._clear_hover_highlight()
        self.refs = iter_artist_refs(self.fig)
        self._configure_picking()
        self._populate_object_list()
        if self.refs:
            self.object_list.setCurrentRow(0)
        self._redraw("Object list refreshed")

    def _on_selection_changed(self, current: QListWidgetItem | None) -> None:
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
        self._update_canvas_display_size()

    def _connect_hover_events(self) -> None:
        self.canvas.mpl_connect("motion_notify_event", self._on_canvas_motion)
        self.canvas.mpl_connect("button_press_event", self._on_canvas_click)
        self.canvas.mpl_connect("button_release_event", self._on_canvas_release)
        self.canvas.mpl_connect("figure_leave_event", self._on_canvas_leave)

    def _on_canvas_motion(self, event: Any) -> None:
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
        if event.button != 1:
            return

        ref = self._find_ref_at_event(event)
        if ref is None:
            self._discard_unsaved_preview()
            self.pinned_ref = None
            self._clear_hover_highlight()
            self.status.setText("Selection unlocked")
            return

        if self.current_ref is not None and self.current_ref.path != ref.path:
            self._discard_unsaved_preview()
        self.pinned_ref = ref
        self._select_ref(ref)
        self._set_hover_highlight(ref)
        self._update_canvas_display_size()
        if ref.kind == "legend":
            self._legend_press_xy = (float(event.x), float(event.y))
        self.status.setText(f"Pinned: {ref.label}")

    def _on_canvas_release(self, event: Any) -> None:
        if (
            self.current_ref is None
            or self.current_ref.kind != "legend"
            or self._legend_press_xy is None
            or event.x is None
            or event.y is None
        ):
            self._legend_press_xy = None
            return

        start_x, start_y = self._legend_press_xy
        self._legend_press_xy = None
        moved = abs(float(event.x) - start_x) + abs(float(event.y) - start_y)
        if moved > 4:
            self._legend_position_dirty = True
            self._mark_position_dirty()
            self.status.setText("Legend moved. Click Save to keep it.")

    def _on_canvas_leave(self, _event: Any) -> None:
        if self.pinned_ref is not None:
            return
        self._clear_hover_highlight()

    def _find_ref_at_event(self, event: Any) -> ArtistRef | None:
        if event.x is None or event.y is None:
            return None

        for ref in reversed(self.refs):
            if ref.kind in {"figure", "axes", "axis"}:
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

        if ref.kind == "figure":
            width, height = self._figure_size()
            self._add_float("Width inches", width, lambda v: self._set_figure_size(width=v), 1.0, 30.0, 0.25)
            self._add_float("Height inches", height, lambda v: self._set_figure_size(height=v), 1.0, 30.0, 0.25)
            aspect = float(width / height) if height else 1.0
            self._add_float("Aspect ratio", aspect, self._set_figure_aspect, 0.1, 10.0, 0.05, decimals=3)
        elif ref.kind == "axes":
            self._add_text("Title", artist.get_title(), artist.set_title)
            self._add_text("X label", artist.get_xlabel(), artist.set_xlabel)
            self._add_text("Y label", artist.get_ylabel(), artist.set_ylabel)
            self._add_color("Face color", artist.get_facecolor(), artist.set_facecolor)
            self._add_bool("X grid", any(line.get_visible() for line in artist.get_xgridlines()), lambda v: artist.grid(v, axis="x"))
            self._add_bool("Y grid", any(line.get_visible() for line in artist.get_ygridlines()), lambda v: artist.grid(v, axis="y"))
        elif ref.kind == "bar":
            first_patch = self._first_bar_patch(artist)
            if first_patch is None:
                self.form.addRow(QLabel("This bar series has no patches."))
            else:
                self._add_bool("Visible", all(patch.get_visible() for patch in artist.patches), lambda v: self._set_bar_visible(artist, v))
                self._add_text("Label", artist.get_label(), artist.set_label)
                self._add_color("Fill color", first_patch.get_facecolor(), lambda v: self._set_bar_facecolor(artist, v))
                self._add_color("Edge color", first_patch.get_edgecolor(), lambda v: self._set_bar_edgecolor(artist, v))
                self._add_float("Edge width", first_patch.get_linewidth(), lambda v: self._set_bar_linewidth(artist, v), 0.0, 20.0, 0.25)
                self._add_float("Alpha", first_patch.get_alpha() if first_patch.get_alpha() is not None else 1.0, lambda v: self._set_bar_alpha(artist, v), 0.0, 1.0, 0.05)
                self._add_choice("Hatch", first_patch.get_hatch() or "None", ["None", "/", "\\", "|", "-", "+", "x", "o", "O", ".", "*"], lambda v: self._set_bar_hatch(artist, "" if v == "None" else v))
                self._add_float("Bar width", abs(first_patch.get_width()), lambda v: self._set_bar_width(artist, v), 0.01, 10.0, 0.05, decimals=3)
        elif ref.kind == "text":
            self._add_text("Text", artist.get_text(), artist.set_text)
            self._add_color("Color", artist.get_color(), artist.set_color)
            self._add_float("Font size", artist.get_fontsize(), artist.set_fontsize, 1.0, 96.0, 1.0)
            self._add_choice("Weight", artist.get_fontweight(), ["normal", "bold", "light", "semibold", "heavy"], artist.set_fontweight)
            self._add_choice("Style", artist.get_fontstyle(), ["normal", "italic", "oblique"], artist.set_fontstyle)
        elif ref.kind == "text_group":
            first_text = self._first_text_in_group(artist)
            if first_text is None:
                self.form.addRow(QLabel("This text group is empty."))
            else:
                self.form.addRow(QLabel(f"{len(artist)} text artists will be updated together."))
                self._add_color("Color", first_text.get_color(), lambda v: self._set_text_group_color(artist, v))
                self._add_float("Font size", first_text.get_fontsize(), lambda v: self._set_text_group_fontsize(artist, v), 1.0, 160.0, 1.0)
                self._add_choice("Weight", first_text.get_fontweight(), ["normal", "bold", "light", "semibold", "heavy"], lambda v: self._set_text_group_fontweight(artist, v))
                self._add_choice("Style", first_text.get_fontstyle(), ["normal", "italic", "oblique"], lambda v: self._set_text_group_fontstyle(artist, v))
        elif ref.kind == "axis":
            axis_name = str(ref.path[2])[0]
            ax = artist.axes
            if not self._is_categorical_axis(artist, axis_name):
                scale = ax.get_xscale() if axis_name == "x" else ax.get_yscale()
                self._add_choice("Scale", scale, ["linear", "log"], lambda v: self._set_axis_scale(artist, axis_name, v))
                self._add_float("Tick start", self._axis_tick_start(artist), lambda v: self._apply_axis_ticks(artist, axis_name, v, self._axis_tick_interval(artist)), -1_000_000_000.0, 1_000_000_000.0, 0.1, decimals=6)
                self._add_float("Tick interval", self._axis_tick_interval(artist), lambda v: self._apply_axis_ticks(artist, axis_name, self._axis_tick_start(artist), v), 0.000001, 1_000_000_000.0, 0.1, decimals=6)
            self._add_float("Tick label size", self._axis_tick_label_prop(artist, "fontsize", 10.0), lambda v: self._apply_axis_tick_labels(artist, fontsize=v), 1.0, 96.0, 1.0)
            self._add_color("Tick label color", self._axis_tick_label_prop(artist, "color", "#000000"), lambda v: self._apply_axis_tick_labels(artist, color=v))
            self._add_choice("Tick label weight", self._axis_tick_label_prop(artist, "fontweight", "normal"), ["normal", "bold", "light", "semibold", "heavy"], lambda v: self._apply_axis_tick_labels(artist, weight=v))
            self._add_choice("Tick label style", self._axis_tick_label_prop(artist, "fontstyle", "normal"), ["normal", "italic", "oblique"], lambda v: self._apply_axis_tick_labels(artist, style=v))
            self._add_float("Tick label rotation", self._axis_tick_label_prop(artist, "rotation", 0.0), lambda v: self._apply_axis_tick_labels(artist, rotation=v), -180.0, 180.0, 5.0, decimals=1)
        elif ref.kind == "legend":
            self._ensure_legend_axes_anchor(artist)
            artist.set_draggable(True, use_blit=False, update="bbox")
            frame = artist.get_frame()
            texts = artist.get_texts()
            fontsize = texts[0].get_fontsize() if texts else 10
            self._add_bool("Visible", artist.get_visible(), artist.set_visible)
            self._add_float("Font size", fontsize, lambda v: self._rebuild_current_legend(fontsize=v), 1.0, 96.0, 1.0)
            self._add_bool("Frame", frame.get_visible(), frame.set_visible)
            self._add_float("Frame alpha", frame.get_alpha() if frame.get_alpha() is not None else 1.0, frame.set_alpha, 0.0, 1.0, 0.05)
            self._add_color("Face color", frame.get_facecolor(), frame.set_facecolor)
            self._add_color("Edge color", frame.get_edgecolor(), frame.set_edgecolor)
            self._add_position_save_button()
            self._add_float("Border pad", artist.borderpad, lambda v: self._rebuild_current_legend(borderpad=v), 0.0, 5.0, 0.1)
            self._add_float("Label spacing", artist.labelspacing, lambda v: self._rebuild_current_legend(labelspacing=v), 0.0, 5.0, 0.1)
            self._add_float("Handle length", artist.handlelength, lambda v: self._rebuild_current_legend(handlelength=v), 0.0, 8.0, 0.1)
            self._add_float("Handle text pad", artist.handletextpad, lambda v: self._rebuild_current_legend(handletextpad=v), 0.0, 5.0, 0.1)
        elif ref.kind == "unsupported":
            adapter = get_adapter("unsupported")
            suggested = adapter.suggested_adapter(artist) if adapter is not None else f"{type(artist).__name__}Adapter"
            self.form.addRow(QLabel("This artist is detected but not editable yet."))
            self.form.addRow("Artist type", QLabel(type(artist).__name__))
            self.form.addRow("Editable", QLabel("No"))
            self.form.addRow("Reason", QLabel("no adapter registered"))
            self.form.addRow("Suggested adapter", QLabel(suggested))
        else:
            self.form.addRow(QLabel("No editor for this artist type yet."))

        self._building_form = False

    def _add_text(self, label: str, value: str, setter: Callable[[str], Any]) -> None:
        widget = QLineEdit(str(value))
        widget._mve_commit = lambda: setter(widget.text())
        save_button = self._add_property_row(label, widget)
        widget.editingFinished.connect(lambda: self._apply(lambda: setter(widget.text()), save_button))

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
    ) -> None:
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

    def _add_bool(self, label: str, value: bool, setter: Callable[[bool], Any]) -> None:
        widget = QCheckBox()
        widget.setChecked(bool(value))
        save_button = self._add_property_row(label, widget)
        widget.toggled.connect(lambda checked: self._apply(lambda: setter(bool(checked)), save_button))

    def _add_choice(self, label: str, value: Any, choices: list[str], setter: Callable[[str], Any]) -> None:
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

    def _add_color(self, label: str, value: Any, setter: Callable[[str], Any]) -> None:
        button = QPushButton(str(value))
        save_button = self._add_property_row(label, button)
        button.clicked.connect(lambda: self._pick_color(button, setter, save_button))

    def _add_button(self, label: str, callback: Callable[[], Any]) -> None:
        button = QPushButton(label)
        save_button = QPushButton("Save")
        save_button.setEnabled(False)
        save_button._mve_editor_widget = button
        button.clicked.connect(lambda: self._apply(callback, save_button))
        save_button.clicked.connect(self._save_current_changes_from_sender)
        self._save_buttons.append(save_button)
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(button, 1)
        layout.addWidget(save_button)
        self.form.addRow("", row)

    def _add_position_save_button(self) -> None:
        button = QPushButton("Save position")
        button.setEnabled(False)
        button.clicked.connect(self._save_current_legend_position)
        self._position_save_button = button
        self.form.addRow("Position", button)

    def _add_property_row(self, label: str, widget: QWidget) -> QPushButton:
        save_button = QPushButton("Save")
        save_button.setEnabled(False)
        save_button._mve_editor_widget = widget
        save_button.clicked.connect(self._save_current_changes_from_sender)
        self._save_buttons.append(save_button)
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(widget, 1)
        layout.addWidget(save_button)
        self.form.addRow(label, row)
        return save_button

    def _pick_color(self, button: QPushButton, setter: Callable[[str], Any], save_button: QPushButton) -> None:
        color = QColorDialog.getColor(parent=self)
        if not color.isValid():
            return
        value = color.name()
        button.setText(value)
        self._apply(lambda: setter(value), save_button)

    def _rebuild_current_legend(self, **changes: Any) -> None:
        if self._rebuilding_legend:
            return
        if self.current_ref is None or self.current_ref.kind != "legend":
            return
        self._rebuild_legend(self.current_ref.artist, **changes)

    def _set_figure_size(self, width: float | None = None, height: float | None = None) -> None:
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
        self._update_canvas_display_size()

    def _enforce_saved_figure_size(self) -> None:
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
        host_width = max(1, self.canvas_host.width())
        host_height = max(1, self.canvas_host.height())
        if host_width <= 1 or host_height <= 1:
            return

        aspect = design_width / design_height
        target_width = host_width
        target_height = int(round(target_width / aspect))
        if target_height > host_height:
            target_height = host_height
            target_width = int(round(target_height * aspect))

        target_width = max(1, target_width)
        target_height = max(1, target_height)
        if self.canvas.width() != target_width or self.canvas.height() != target_height:
            self.canvas.setMaximumSize(target_width, target_height)
            self.canvas.resize(target_width, target_height)

    def _set_axis_scale(self, axis: Any, axis_name: str, scale: str) -> None:
        ax = axis.axes
        if axis_name == "x":
            ax.set_xscale(scale)
        else:
            ax.set_yscale(scale)
        axis._mve_scale = scale
        self._apply_axis_ticks(axis, axis_name, self._axis_tick_start(axis), self._axis_tick_interval(axis))

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

    def _first_bar_patch(self, container: Any) -> Any | None:
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

    def _first_text_in_group(self, texts: Any) -> Any | None:
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

    def _apply_axis_ticks(self, axis: Any, axis_name: str, start: float, interval: float) -> None:
        interval = float(interval)
        start = float(start)
        if interval <= 0 or not math.isfinite(interval) or not math.isfinite(start):
            return
        ax = axis.axes
        low, high = ax.get_xlim() if axis_name == "x" else ax.get_ylim()
        inverted = high < low
        if high < low:
            low, high = high, low

        max_ticks = 1000
        ticks: list[float] = []
        value = start
        low = value
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
        axis._mve_tick_interval = interval
        self._reapply_axis_tick_label_style(axis)

    def _apply_axis_tick_labels(
        self,
        axis: Any,
        fontsize: float | None = None,
        color: str | None = None,
        weight: str | None = None,
        style: str | None = None,
        rotation: float | None = None,
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
            draggable = legend.get_draggable() is not None

            new_legend = ax.legend(**props)
            new_legend.set_visible(visible)
            new_legend.set_draggable(draggable, use_blit=False, update="bbox")
            new_frame = new_legend.get_frame()
            new_frame.set_alpha(frame_alpha)
            new_frame.set_facecolor(facecolor)
            new_frame.set_edgecolor(edgecolor)
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

    def _apply(self, callback: Callable[[], Any], save_button: QPushButton | None = None) -> None:
        if self._building_form:
            return
        self._active_save_button = save_button
        try:
            callback()
            self._sync_current_line_legend_handle()
            self._sync_current_bar_legend_handle()
            self._mark_dirty(save_button)
        finally:
            self._active_save_button = None
        self._redraw("Updated")

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

    def _mark_dirty(self, save_button: QPushButton | None = None) -> None:
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
        self.status.setText("Preview updated. Click Save to keep it.")

    def _mark_position_dirty(self) -> None:
        if self._building_form or self._suppress_dirty:
            return
        self._legend_position_dirty = True
        if self._position_save_button is not None:
            self._position_save_button.setEnabled(True)
            self._position_save_button.setStyleSheet("font-weight: 700; background: #ffcc00;")

    def _save_current_changes(self, editor_widget: QWidget | None = None) -> None:
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
        self.status.setText(f"Saved: {self.current_ref.label}")

    def _save_current_changes_from_sender(self) -> None:
        sender = self.sender()
        editor_widget = getattr(sender, "_mve_editor_widget", None)
        self._save_current_changes(editor_widget)

    def _commit_editor(self, widget: QWidget | None = None) -> None:
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

    def _commit_all_form_editors(self, skip: QWidget | None = None) -> None:
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
            artist.set_color(props["color"])
            artist.set_linewidth(props["linewidth"])
            artist.set_linestyle(props["linestyle"])
            artist.set_marker(props["marker"])
            artist.set_markersize(props["markersize"])
            artist.set_alpha(props["alpha"])
            artist.set_label(props["label"])
        elif kind == "bar":
            self._restore_bar_snapshot(artist, props)
        elif kind == "text":
            artist.set_text(props["text"])
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
            self._set_axis_scale(artist, axis_name, props["scale"])
            self._apply_axis_ticks(artist, axis_name, props["tick_start"], props["tick_interval"])
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
        finally:
            self._suppress_dirty = False

    def _redraw(self, message: str) -> None:
        self._fit_figure_to_canvas(adjust_layout=True)
        self.canvas.draw_idle()
        self.status.setText(message)

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
        self._clear_hover_highlight()
        path = export_style(self.fig, self.export_path, source=_source_metadata(self.source_path))
        if pinned_ref is not None:
            self._set_hover_highlight(pinned_ref)
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

    def _save_figure(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._fit_figure_to_canvas()
        self.fig.savefig(path, dpi=300, bbox_inches="tight")
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

        self._clear_hover_highlight()
        self.pinned_ref = None
        self.current_ref = None

        try:
            self._delete_ref(ref)
        except Exception as exc:
            QMessageBox.warning(self, "Delete failed", str(exc))
            return

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
