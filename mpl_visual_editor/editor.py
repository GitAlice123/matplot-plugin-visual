"""PySide6 editor window for Matplotlib figures."""

from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Any, Callable

import matplotlib

matplotlib.use("QtAgg")

import matplotlib.patheffects as path_effects
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle
from PySide6.QtCore import Qt
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
from .exporter import _snapshot as snapshot_artist
from .inspector import ArtistRef, iter_artist_refs


class _AspectCanvasHost(QWidget):
    """Centers the Matplotlib canvas while preserving the editor's figure aspect."""

    def __init__(self, editor: "StyleEditor") -> None:
        super().__init__()
        self.editor = editor

    def resizeEvent(self, event: Any) -> None:
        super().resizeEvent(event)
        self.editor._update_canvas_display_size()


def edit(fig: Figure, export_path: str | Path = "style_patch.py") -> None:
    """Open a visual editor for an existing Matplotlib figure."""

    app = QApplication.instance() or QApplication(sys.argv)
    window = StyleEditor(fig, export_path)
    window.show()
    app.exec()


class StyleEditor(QMainWindow):
    """Minimal style editor window."""

    def __init__(self, fig: Figure, export_path: str | Path = "style_patch.py") -> None:
        super().__init__()
        self.fig = fig
        self.export_path = Path(export_path)
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

        self.setWindowTitle("Matplotlib Visual Style Editor")
        self.resize(1180, 760)

        self.canvas = FigureCanvasQTAgg(fig)
        self.canvas.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
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

    def _build_ui(self) -> None:
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.addWidget(QLabel("Objects"))
        left_layout.addWidget(self.object_list, 1)

        refresh_button = QPushButton("Refresh objects")
        refresh_button.clicked.connect(self._refresh_refs)
        left_layout.addWidget(refresh_button)

        export_button = QPushButton("Export style_patch.py")
        export_button.clicked.connect(self._export)
        left_layout.addWidget(export_button)

        choose_export_button = QPushButton("Export as...")
        choose_export_button.clicked.connect(self._export_as)
        left_layout.addWidget(choose_export_button)

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
        canvas_host_layout.setContentsMargins(0, 0, 0, 0)
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
            if self._artist_contains(ref.artist, event):
                return ref

        axis_ref = self._axis_ref_at_event(event)
        if axis_ref is not None:
            return axis_ref

        if event.inaxes is not None:
            for ref in self.refs:
                if ref.kind == "axes" and ref.artist is event.inaxes:
                    return ref
        return None

    def _axis_ref_at_event(self, event: Any) -> ArtistRef | None:
        if event.x is None or event.y is None:
            return None

        x = float(event.x)
        y = float(event.y)
        for ref in self.refs:
            if ref.kind != "axis":
                continue
            if self._axis_artist_contains(ref, event, x, y):
                return ref

        pad = 34

        for ax in self.fig.axes:
            bbox = ax.bbox
            inside_expanded = (
                bbox.x0 - pad <= x <= bbox.x1 + pad
                and bbox.y0 - pad <= y <= bbox.y1 + pad
            )
            if not inside_expanded:
                continue

            near_x_axis = bbox.x0 - pad <= x <= bbox.x1 + pad and (
                abs(y - bbox.y0) <= pad or abs(y - bbox.y1) <= pad
            )
            near_y_axis = bbox.y0 - pad <= y <= bbox.y1 + pad and (
                abs(x - bbox.x0) <= pad or abs(x - bbox.x1) <= pad
            )
            if not (near_x_axis or near_y_axis):
                continue

            target = "xaxis" if near_x_axis and not near_y_axis else "yaxis"
            if near_x_axis and near_y_axis:
                distance_x = min(abs(y - bbox.y0), abs(y - bbox.y1))
                distance_y = min(abs(x - bbox.x0), abs(x - bbox.x1))
                target = "xaxis" if distance_x <= distance_y else "yaxis"

            for ref in self.refs:
                if ref.kind == "axis" and ref.artist.axes is ax and ref.path[2] == target:
                    return ref
        return None

    def _axis_artist_contains(self, ref: ArtistRef, event: Any, x: float, y: float) -> bool:
        renderer = self.canvas.get_renderer()
        for artist in self._axis_highlight_artists(ref):
            if hasattr(artist, "get_visible") and not artist.get_visible():
                continue
            try:
                contains, _details = artist.contains(event)
                if contains:
                    return True
            except Exception:
                pass
            try:
                bbox = artist.get_window_extent(renderer=renderer).expanded(1.4, 1.8)
                if bbox.contains(x, y):
                    return True
            except Exception:
                pass
        return False

    def _artist_contains(self, artist: Any, event: Any) -> bool:
        if hasattr(artist, "get_visible") and not artist.get_visible():
            return False
        try:
            contains, _details = artist.contains(event)
        except Exception:
            return False
        return bool(contains)

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
        artist = ref.artist
        state: dict[str, Any] = {"kind": ref.kind}

        if hasattr(artist, "get_path_effects") and hasattr(artist, "set_path_effects"):
            state["path_effects"] = artist.get_path_effects()
            artist.set_path_effects(
                [
                    path_effects.Stroke(linewidth=4, foreground="#ffcc00"),
                    path_effects.Normal(),
                ]
            )

        if ref.kind in {"line", "spine"}:
            if hasattr(artist, "get_zorder") and hasattr(artist, "set_zorder"):
                state["zorder"] = artist.get_zorder()
                artist.set_zorder(float(state["zorder"]) + 1000)
        elif ref.kind == "legend":
            frame = artist.get_frame()
            state["frame"] = {
                "path_effects": frame.get_path_effects(),
            }
            frame.set_path_effects(
                [
                    path_effects.Stroke(linewidth=4, foreground="#ffcc00"),
                    path_effects.Normal(),
                ]
            )
        elif ref.kind == "axis":
            state["axis_artists"] = []
            for axis_artist in self._axis_highlight_artists(ref):
                if hasattr(axis_artist, "get_path_effects") and hasattr(axis_artist, "set_path_effects"):
                    state["axis_artists"].append((axis_artist, axis_artist.get_path_effects()))
                    axis_artist.set_path_effects(
                        [
                            path_effects.Stroke(linewidth=4, foreground="#ffcc00"),
                            path_effects.Normal(),
                        ]
                    )
        elif ref.kind == "axes":
            overlay = Rectangle(
                (0, 0),
                1,
                1,
                transform=artist.transAxes,
                fill=False,
                edgecolor="#ffcc00",
                linewidth=2.5,
                linestyle="--",
                zorder=1_000_000,
                clip_on=False,
            )
            artist.add_patch(overlay)
            state["overlay"] = overlay

        return state

    def _restore_hover_highlight(self, ref: ArtistRef, state: dict[str, Any]) -> None:
        artist = ref.artist
        if "path_effects" in state:
            artist.set_path_effects(state["path_effects"])

        if ref.kind in {"line", "spine"}:
            if "zorder" in state:
                artist.set_zorder(state["zorder"])
        elif ref.kind == "legend" and "frame" in state:
            frame = artist.get_frame()
            frame_state = state["frame"]
            frame.set_path_effects(frame_state["path_effects"])
        elif ref.kind == "axis" and "axis_artists" in state:
            for axis_artist, old_effects in state["axis_artists"]:
                axis_artist.set_path_effects(old_effects)
        elif ref.kind == "axes" and "overlay" in state:
            self._remove_overlay(state["overlay"])

    def _axis_highlight_artists(self, ref: ArtistRef) -> list[Any]:
        axis = ref.artist
        artists: list[Any] = [axis.label]
        for tick in axis.get_major_ticks():
            artists.extend([tick.tick1line, tick.tick2line, tick.label1, tick.label2])
        return artists

    def _remove_overlay(self, overlay: Any) -> None:
        try:
            overlay.remove()
        except NotImplementedError:
            if overlay in self.fig.artists:
                self.fig.artists.remove(overlay)
            for ax in self.fig.axes:
                if overlay in ax.patches:
                    ax.patches.remove(overlay)

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
        elif ref.kind == "line":
            self._add_text("Label", artist.get_label(), artist.set_label)
            self._add_color("Color", artist.get_color(), artist.set_color)
            self._add_float("Line width", artist.get_linewidth(), artist.set_linewidth, 0.0, 20.0, 0.25)
            self._add_choice("Line style", artist.get_linestyle(), ["-", "--", "-.", ":", "None", " "], artist.set_linestyle)
            self._add_choice("Marker", artist.get_marker(), ["None", " ", ".", "o", "s", "^", "v", "D", "x", "+", "*"], artist.set_marker)
            self._add_float("Marker size", artist.get_markersize(), artist.set_markersize, 0.0, 40.0, 0.5)
            self._add_float("Alpha", artist.get_alpha() if artist.get_alpha() is not None else 1.0, artist.set_alpha, 0.0, 1.0, 0.05)
        elif ref.kind == "text":
            self._add_text("Text", artist.get_text(), artist.set_text)
            self._add_color("Color", artist.get_color(), artist.set_color)
            self._add_float("Font size", artist.get_fontsize(), artist.set_fontsize, 1.0, 96.0, 1.0)
            self._add_choice("Weight", artist.get_fontweight(), ["normal", "bold", "light", "semibold", "heavy"], artist.set_fontweight)
            self._add_choice("Style", artist.get_fontstyle(), ["normal", "italic", "oblique"], artist.set_fontstyle)
        elif ref.kind == "axis":
            axis_name = str(ref.path[2])[0]
            ax = artist.axes
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
            artist.set_draggable(True, use_blit=False)
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
        elif ref.kind == "spine":
            self._add_bool("Visible", artist.get_visible(), artist.set_visible)
            self._add_color("Color", artist.get_edgecolor(), artist.set_edgecolor)
            self._add_float("Line width", artist.get_linewidth(), artist.set_linewidth, 0.0, 20.0, 0.25)
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
    ) -> None:
        widget = QDoubleSpinBox()
        widget.setRange(minimum, maximum)
        widget.setSingleStep(step)
        widget.setDecimals(decimals)
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
            self.canvas.setFixedSize(target_width, target_height)
            self.canvas.resize(target_width, target_height)

    def _set_axis_scale(self, axis: Any, axis_name: str, scale: str) -> None:
        ax = axis.axes
        if axis_name == "x":
            ax.set_xscale(scale)
        else:
            ax.set_yscale(scale)
        self._apply_axis_ticks(axis, axis_name, self._axis_tick_start(axis), self._axis_tick_interval(axis))

    def _apply_axis_ticks(self, axis: Any, axis_name: str, start: float, interval: float) -> None:
        interval = float(interval)
        if interval <= 0:
            return
        ax = axis.axes
        low, high = ax.get_xlim() if axis_name == "x" else ax.get_ylim()
        inverted = high < low
        if high < low:
            low, high = high, low

        ticks: list[float] = []
        value = float(start)
        low = value
        if high <= low:
            high = low + interval
        limit = high + interval * 0.5
        while value <= limit and len(ticks) < 10000:
            if math.isfinite(value):
                ticks.append(value)
            value += interval

        if axis_name == "x":
            ax.set_xticks(ticks)
            ax.set_xlim((high, low) if inverted else (low, high))
        else:
            ax.set_yticks(ticks)
            ax.set_ylim((high, low) if inverted else (low, high))
        axis._mve_tick_start = float(start)
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

            visible = legend.get_visible()
            frame_alpha = frame.get_alpha()
            facecolor = frame.get_facecolor()
            edgecolor = frame.get_edgecolor()
            draggable = legend.get_draggable() is not None

            new_legend = ax.legend(**props)
            new_legend.set_visible(visible)
            new_legend.set_draggable(draggable, use_blit=False)
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
        elif kind == "text":
            artist.set_text(props["text"])
            artist.set_color(props["color"])
            artist.set_fontsize(props["fontsize"])
            artist.set_fontweight(props["fontweight"])
            artist.set_fontstyle(props["fontstyle"])
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
        self._fit_figure_to_canvas()
        self.canvas.draw_idle()
        self.status.setText(message)

    def _fit_figure_to_canvas(self) -> None:
        self._enforce_saved_figure_size()
        try:
            self.fig.tight_layout()
        except Exception:
            pass

    def _export(self) -> None:
        self._discard_unsaved_preview()
        pinned_ref = self.pinned_ref
        self._clear_hover_highlight()
        path = export_style(self.fig, self.export_path)
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
        artist = ref.artist
        if ref.kind == "text":
            artist.set_text("")
        elif ref.kind == "line":
            artist.remove()
        elif ref.kind == "legend":
            artist.remove()
        elif ref.kind == "spine":
            artist.set_visible(False)
        else:
            raise ValueError(f"Delete is not supported for {ref.kind!r}")
