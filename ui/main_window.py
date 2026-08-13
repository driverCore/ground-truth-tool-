"""Main Window — Kabaddi GT Track Editor (direct JSON edit mode).

Workflow:
  File > Open tracks.json  →  edit IDs  →  changes saved automatically to same file.
  No .kgt project files.  Works for any action class tracks.json.
"""
from __future__ import annotations

import traceback
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QTimer, Signal, Slot
from PySide6.QtGui import QAction, QKeySequence, QCloseEvent
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QSplitter, QVBoxLayout, QHBoxLayout,
    QFileDialog, QMessageBox, QLabel, QInputDialog, QStatusBar, QApplication,
)

from models.track_store import TrackStore
from models.history import History
from controllers.edit_ctrl import EditController
from controllers.playback_ctrl import PlaybackController
from ui.frame_canvas import FrameCanvas
from ui.timeline_widget import TimelineWidget
from ui.track_panel import TrackPanel
from ui.controls_bar import ControlsBar
from ui.dialogs.id_editor import IdEditorDialog
from ui.dialogs.merge_dialog import MergeDialog, SplitDialog
from utils import io as uio
from utils.settings import AppSettings
from utils.colors import APP_STYLESHEET, BG_SURFACE


class MainWindow(QMainWindow):
    APP_TITLE = "Kabaddi GT Track Editor"

    def __init__(self):
        super().__init__()
        self._settings  = AppSettings()
        self._json_path: Optional[str] = None   # currently open tracks.json
        self._store     = TrackStore()
        self._history   = History()
        self._edit_ctrl = EditController(self._store, self._history)
        self._play_ctrl = PlaybackController()
        self._canvas: Optional[FrameCanvas] = None

        self._build_ui()
        self._build_menus()
        self._connect_stable_signals()
        self._setup_shortcuts()
        self._restore_geometry()

        self.setWindowTitle(self.APP_TITLE)
        self._update_ui_state()

    # ── Build UI ──────────────────────────────────────────────────────────

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Main horizontal splitter ───────────────────────────────────────
        self._main_splitter = QSplitter(Qt.Horizontal)
        self._main_splitter.setHandleWidth(4)

        # Canvas area
        self._canvas_container = QWidget()
        cl = QVBoxLayout(self._canvas_container)
        cl.setContentsMargins(0, 0, 0, 0)
        self._canvas_placeholder = QLabel(
            "Open a tracks.json file to begin.\n\n"
            "File → Open tracks.json…\n\n"
            "Changes are saved automatically to the same file."
        )
        self._canvas_placeholder.setAlignment(Qt.AlignCenter)
        self._canvas_placeholder.setStyleSheet(
            "background:#0d1117; font-size:15px; color:#8b949e;"
        )
        cl.addWidget(self._canvas_placeholder)

        self._track_panel = TrackPanel(self._store)
        self._main_splitter.addWidget(self._canvas_container)
        self._main_splitter.addWidget(self._track_panel)
        self._main_splitter.setSizes([900, 300])
        root.addWidget(self._main_splitter, stretch=1)

        # ── Bottom: controls + timeline ───────────────────────────────────
        bottom = QWidget()
        bottom.setStyleSheet(f"background:{BG_SURFACE};")
        bl = QVBoxLayout(bottom)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(0)
        self._controls = ControlsBar()
        self._timeline = TimelineWidget()
        bl.addWidget(self._controls)
        bl.addWidget(self._timeline)
        root.addWidget(bottom)

        # ── Status bar ────────────────────────────────────────────────────
        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._lbl_left  = QLabel("No file open")
        self._lbl_right = QLabel("")
        self._lbl_right.setAlignment(Qt.AlignRight)
        self._status.addWidget(self._lbl_left, 1)
        self._status.addPermanentWidget(self._lbl_right)

        self.setMinimumSize(1100, 700)
        self.resize(1400, 820)

    # ── Menus ─────────────────────────────────────────────────────────────

    def _build_menus(self):
        mb = self.menuBar()

        # ── File ──────────────────────────────────────────────────────────
        file_menu = mb.addMenu("&File")

        self._act_open = QAction("&Open tracks.json…", self, shortcut="Ctrl+O")
        self._act_open.setToolTip("Open any ByteTrack tracks.json to edit IDs")
        file_menu.addAction(self._act_open)

        file_menu.addSeparator()

        # Recent files
        self._recent_menu = file_menu.addMenu("Recent Files")
        self._rebuild_recent_menu()

        file_menu.addSeparator()
        act_quit = QAction("&Quit", self, shortcut="Ctrl+Q")
        act_quit.triggered.connect(self.close)
        file_menu.addAction(act_quit)

        # ── Edit ──────────────────────────────────────────────────────────
        edit_menu = mb.addMenu("&Edit")
        self._act_undo   = QAction("&Undo", self, shortcut="Ctrl+Z")
        self._act_redo   = QAction("&Redo", self, shortcut="Ctrl+Y")
        self._act_verify = QAction("✓ Verify Frame", self, shortcut="V")
        edit_menu.addAction(self._act_undo)
        edit_menu.addAction(self._act_redo)
        edit_menu.addSeparator()
        edit_menu.addAction(self._act_verify)

        # ── View ──────────────────────────────────────────────────────────
        view_menu = mb.addMenu("&View")
        act_zi  = QAction("Zoom In",    self, shortcut="Ctrl++")
        act_zo  = QAction("Zoom Out",   self, shortcut="Ctrl+-")
        act_zf  = QAction("Fit View",   self, shortcut="Ctrl+0")
        act_zi.triggered.connect(lambda: self._canvas and self._canvas.zoom_in())
        act_zo.triggered.connect(lambda: self._canvas and self._canvas.zoom_out())
        act_zf.triggered.connect(lambda: self._canvas and self._canvas.reset_zoom())
        view_menu.addAction(act_zi)
        view_menu.addAction(act_zo)
        view_menu.addAction(act_zf)
        view_menu.addSeparator()
        act_fs = QAction("Full&screen", self, shortcut="F11")
        act_fs.triggered.connect(self._toggle_fullscreen)
        view_menu.addAction(act_fs)

        # ── Export ────────────────────────────────────────────────────────
        export_menu = mb.addMenu("E&xport")
        self._act_export_mot = QAction("Export MOTChallenge gt.txt", self, shortcut="Ctrl+E")
        export_menu.addAction(self._act_export_mot)

        # ── Help ─────────────────────────────────────────────────────────
        help_menu = mb.addMenu("&Help")
        act_shortcuts = QAction("&Keyboard Shortcuts", self, shortcut="F1")
        act_shortcuts.triggered.connect(self._show_shortcuts_dialog)
        help_menu.addAction(act_shortcuts)

        # ── Connect menu actions ───────────────────────────────────────────
        self._act_open.triggered.connect(self._on_open)
        self._act_undo.triggered.connect(self._on_undo)
        self._act_redo.triggered.connect(self._on_redo)
        self._act_verify.triggered.connect(self._on_verify_frame)
        self._act_export_mot.triggered.connect(self._export_mot)

    def _rebuild_recent_menu(self):
        self._recent_menu.clear()
        recents = self._settings.get_recent_projects()
        for path in recents:
            act = QAction(path, self)
            act.triggered.connect(lambda checked, p=path: self._load_json_file(p))
            self._recent_menu.addAction(act)
        if not recents:
            self._recent_menu.addAction(QAction("(none)", self))

    # ── Signal wiring ─────────────────────────────────────────────────────

    def _connect_stable_signals(self):
        """Connect signals for widgets that persist across file loads."""
        self._play_ctrl.frame_requested.connect(self._on_frame_position_changed)

        self._controls.play_pause_toggled.connect(self._play_ctrl.toggle_play_pause)
        self._controls.step_backward_requested.connect(self._play_ctrl.step_backward)
        self._controls.step_forward_requested.connect(self._play_ctrl.step_forward)
        self._controls.first_frame_requested.connect(self._play_ctrl.go_first)
        self._controls.last_frame_requested.connect(self._play_ctrl.go_last)
        self._controls.speed_changed.connect(self._play_ctrl.set_speed)
        self._controls.jump_to_frame_requested.connect(self._jump_to_frame_1based)
        self._controls.prev_switch_requested.connect(self._prev_switch)
        self._controls.next_switch_requested.connect(self._next_switch)

        self._timeline.seek_requested.connect(self._play_ctrl.seek)

        self._track_panel.change_id_requested.connect(self._on_change_id_requested)
        self._track_panel.merge_requested.connect(self._on_merge_requested)
        self._track_panel.split_requested.connect(self._on_split_requested)
        self._track_panel.verify_frame_requested.connect(
            lambda fi: self._edit_ctrl.verify_frame(fi))
        self._track_panel.track_selected.connect(
            lambda di: self._canvas and self._canvas.set_selected_detection(di))
        self._track_panel.delete_box_requested.connect(self._on_delete_selected_box)
        self._track_panel.add_box_requested.connect(self._toggle_add_box_mode)
        self._track_panel.change_class_requested.connect(self._on_change_class)

    def _connect_edit_ctrl_signals(self):
        """Connect edit controller signals (reconnected on each file load)."""
        self._edit_ctrl.tracks_changed.connect(self._on_tracks_changed)
        self._edit_ctrl.history_changed.connect(self._on_history_changed)
        self._edit_ctrl.statistics_changed.connect(self._refresh_statistics)

    # ── Keyboard shortcuts ────────────────────────────────────────────────

    def _is_input_focused(self) -> bool:
        widget = QApplication.focusWidget()
        if widget is None:
            return False
        from PySide6.QtWidgets import QLineEdit, QTextEdit, QPlainTextEdit, QAbstractSpinBox
        return isinstance(widget, (QLineEdit, QTextEdit, QPlainTextEdit, QAbstractSpinBox))

    def _on_shortcut_step_backward(self):
        if not self._is_input_focused():
            self._play_ctrl.step_backward()

    def _on_shortcut_step_forward(self):
        if not self._is_input_focused():
            self._play_ctrl.step_forward()

    def _on_shortcut_toggle_play_pause(self):
        if not self._is_input_focused():
            self._play_ctrl.toggle_play_pause()

    def _on_shortcut_prev_switch(self):
        if not self._is_input_focused():
            self._prev_switch()

    def _on_shortcut_next_switch(self):
        if not self._is_input_focused():
            self._next_switch()

    def _on_shortcut_verify_frame(self):
        if not self._is_input_focused():
            self._on_verify_frame()

    def _on_shortcut_toggle_add_box_mode(self):
        if not self._is_input_focused():
            self._toggle_add_box_mode()

    def _on_shortcut_delete_selected_box(self):
        if not self._is_input_focused():
            self._on_delete_selected_box()

    def _on_shortcut_escape_pressed(self):
        if not self._is_input_focused():
            self._on_escape_pressed()

    def _on_shortcut_save_explicit(self):
        if not self._is_input_focused():
            self._on_save_explicit()

    def _setup_shortcuts(self):
        from PySide6.QtGui import QShortcut
        QShortcut(QKeySequence(Qt.Key_Left),  self).activated.connect(self._on_shortcut_step_backward)
        QShortcut(QKeySequence(Qt.Key_Right), self).activated.connect(self._on_shortcut_step_forward)
        QShortcut(QKeySequence(Qt.Key_Space), self).activated.connect(self._on_shortcut_toggle_play_pause)
        QShortcut(QKeySequence("["), self).activated.connect(self._on_shortcut_prev_switch)
        QShortcut(QKeySequence("]"), self).activated.connect(self._on_shortcut_next_switch)
        QShortcut(QKeySequence("V"), self).activated.connect(self._on_shortcut_verify_frame)
        QShortcut(QKeySequence(Qt.Key_Delete), self).activated.connect(self._on_shortcut_delete_selected_box)
        QShortcut(QKeySequence(Qt.Key_Backspace), self).activated.connect(self._on_shortcut_delete_selected_box)
        QShortcut(QKeySequence(Qt.Key_Escape), self).activated.connect(self._on_shortcut_escape_pressed)
        QShortcut(QKeySequence("S"), self).activated.connect(self._on_shortcut_save_explicit)
        QShortcut(QKeySequence("Ctrl+S"), self).activated.connect(self._on_shortcut_save_explicit)
        QShortcut(QKeySequence("F1"), self).activated.connect(self._show_shortcuts_dialog)

        # Add W, A, D shortcuts
        QShortcut(QKeySequence("W"), self).activated.connect(self._on_shortcut_toggle_add_box_mode)
        QShortcut(QKeySequence("A"), self).activated.connect(self._on_shortcut_step_backward)
        QShortcut(QKeySequence("D"), self).activated.connect(self._on_shortcut_step_forward)

    # ── Open / Load ───────────────────────────────────────────────────────

    def _on_open(self):
        last = self._settings.get_last_dir() or str(Path.cwd())
        path, _ = QFileDialog.getOpenFileName(
            self, "Open ByteTrack tracks.json", last, "JSON files (*.json);;All files (*)"
        )
        if path:
            self._load_json_file(path)

    def _load_json_file(self, json_path: str):
        """Main entry point: load a tracks.json, auto-detect frames dir, start editing."""
        json_path = str(Path(json_path).resolve())
        if not Path(json_path).exists():
            QMessageBox.warning(self, "File not found", json_path)
            return

        # Load records
        try:
            records = uio.load_bytetrack_json(json_path)
        except Exception as ex:
            QMessageBox.critical(self, "Load error", f"Cannot read {json_path}:\n{ex}")
            return

        # Build fresh store + controller
        self._json_path = json_path
        self._store     = TrackStore()
        self._store.load_from_records(records)
        self._store.set_json_path(json_path)       # ← enables auto write-back
        self._history   = History()
        self._edit_ctrl = EditController(self._store, self._history)
        self._connect_edit_ctrl_signals()

        # Auto-detect frames directory
        frames_dir = self._detect_frames_dir(json_path)
        if not frames_dir:
            frames_dir = QFileDialog.getExistingDirectory(
                self, "Select Frames Directory (could not auto-detect)",
                str(Path(json_path).parent.parent)
            )
        if not frames_dir:
            QMessageBox.warning(self, "No frames dir",
                                "Frames directory not found — canvas will be blank.")
            frames_dir = str(Path(json_path).parent)   # fallback

        # Build / replace canvas
        cl = self._canvas_container.layout()
        if self._canvas is not None:
            cl.removeWidget(self._canvas)
            self._canvas.deleteLater()
            self._canvas = None
        if not self._canvas_placeholder.isHidden():
            cl.removeWidget(self._canvas_placeholder)
            self._canvas_placeholder.hide()

        self._canvas = FrameCanvas(frames_dir)
        self._canvas.detection_clicked.connect(self._on_detection_clicked)
        self._canvas.bbox_edited.connect(self._on_bbox_edited)
        self._canvas.detection_created.connect(self._on_detection_created)
        self._canvas.cancel_detection.connect(self._on_delete_selected_box)
        self._canvas.change_id_requested.connect(self._on_change_id_requested)
        self._canvas.id_edited_inplace.connect(self._on_id_edited_inplace)
        self._canvas.navigate_frame.connect(self._on_navigate_frame_request)
        cl.addWidget(self._canvas)

        # Setup playback + UI
        self._play_ctrl.setup(self._store.frame_count, 0)
        self._controls.setup(self._store.frame_count)
        self._timeline.setup([f.frame_idx for f in self._store.all_frames()])
        self._refresh_timeline_markers()
        self._track_panel._store = self._store
        self._on_frame_position_changed(0)

        # Settings + status
        self._settings.set_last_dir(str(Path(json_path).parent))
        self._settings.add_recent_project(json_path)
        self._rebuild_recent_menu()

        name = Path(json_path).parent.name + "/" + Path(json_path).name
        self.setWindowTitle(f"{name} — {self.APP_TITLE}")
        self._lbl_left.setText(
            f"Editing: {json_path}  ·  {self._store.frame_count} frames  "
            f"·  auto-save ON"
        )
        self._update_ui_state()
        self._refresh_statistics()
        self.raise_()
        self.activateWindow()

    @staticmethod
    def _detect_frames_dir(json_path: str) -> str:
        """Auto-detect frames directory from tracks.json path.

        Naming convention:
          .../raid/toe touch/bytetrack_tt_1_frames/tracks.json
          →  .../raid/toe touch/frames/tt_1_frames/

        Also tries the json's parent directory directly.
        """
        p = Path(json_path).parent
        folder = p.name   # e.g. "bytetrack_tt_1_frames"

        # Strategy 1: strip "bytetrack_" prefix → look in class directory's "frames/" dir
        if folder.startswith("bytetrack_"):
            sub = folder[len("bytetrack_"):]   # e.g., "th52_frames"
            
            # The structure is: ClassName / bytetrack / bytetrack_th52_frames / tracks.json
            # So p.parent.parent is the ClassName directory
            if p.parent.name == "bytetrack":
                class_dir = p.parent.parent
            else:
                class_dir = p.parent # Fallback for old structure

            candidate = class_dir / "frames" / sub
            if candidate.is_dir():
                return str(candidate)

        # Strategy 2: look for any directory with "frames" or "frame" in name within the class directory
        if p.parent.name == "bytetrack":
            class_dir = p.parent.parent
        else:
            class_dir = p.parent

        frames_parent = class_dir / "frames"
        if frames_parent.is_dir():
            # Try to find an exact match first if we failed above
            candidate = frames_parent / folder.replace("bytetrack_", "")
            if candidate.is_dir():
                return str(candidate)
                
            # Otherwise just pick any child
            children = [c for c in frames_parent.iterdir() if c.is_dir()]
            if children:
                return str(children[0])

        return ""

    # ── Frame display ─────────────────────────────────────────────────────

    @Slot(int)
    def _on_frame_position_changed(self, pos: int):
        fd = self._store.get_frame_by_position(pos)
        if fd is None:
            return
        dets = self._store.get_frame_tracks(fd.frame_idx)
        if self._canvas:
            self._canvas.display_frame(fd.frame_idx, dets, fd.frame_name)
        self._track_panel.update_frame(fd.frame_idx, dets)
        self._timeline.set_current_position(pos)
        self._controls.set_current_position(pos, fd.frame_idx)
        self._controls.set_playing(self._play_ctrl.is_playing())

    @Slot(int)
    def _on_tracks_changed(self, frame_idx: int):
        pos = self._store.position_of(frame_idx)
        if pos == self._play_ctrl.current_position:
            self._on_frame_position_changed(pos)
        self._refresh_timeline_markers()

    def _refresh_timeline_markers(self):
        self._timeline.update_markers(
            set(self._store.get_switch_frames()),
            set(self._store.get_corrected_frames()),
            set(self._store.get_verified_frames()),
        )

    # ── Detection interaction ─────────────────────────────────────────────

    @Slot(int, int)
    def _on_detection_clicked(self, det_idx: int, frame_idx: int):
        self._track_panel.set_selected_detection(det_idx, frame_idx)

    # ── Edit actions ──────────────────────────────────────────────────────

    @Slot(int, int)
    def _on_change_id_requested(self, det_idx: int, frame_idx: int):
        fd = self._store.get_frame_data(frame_idx)
        if fd is None:
            return
        eff = self._store.get_frame_tracks(frame_idx)
        det = next((d for d in eff if d.det_idx == det_idx), None)
        if det is None:
            return

        def preview_fn(di, new_id, scope, end_f):
            return self._edit_ctrl.preview_change_id(frame_idx, di, new_id, scope, end_f)

        dlg = IdEditorDialog(
            current_id  = det.current_id,
            original_id = det.original_id,
            frame_idx   = frame_idx,
            max_frame   = self._store.last_frame_idx(),
            preview_fn  = preview_fn,
            det_idx     = det_idx,
            parent      = self,
        )
        if dlg.exec():
            ok = self._edit_ctrl.change_id(
                frame_idx, det_idx,
                dlg.result_new_id,
                dlg.result_scope,
                dlg.result_end_frame,
            )
            if ok:
                self._status.showMessage(
                    f"✓ Changed ID {det.current_id} → {dlg.result_new_id}  "
                    f"({dlg.result_scope}) — saved to {Path(self._json_path).name}",
                    4000
                )

    @Slot(int, int, int)
    def _on_id_edited_inplace(self, det_idx: int, frame_idx: int, new_id: int):
        ok = self._edit_ctrl.change_id(
            frame_idx, det_idx,
            new_id,
            "frame",
        )
        if ok:
            self._status.showMessage(f"✓ Changed ID in-place → {new_id} — saved", 4000)

    @Slot(str)
    def _on_navigate_frame_request(self, direction: str):
        if direction == "prev":
            self._play_ctrl.step_backward()
        elif direction == "next":
            self._play_ctrl.step_forward()

    @Slot(int)
    def _on_merge_requested(self, current_id: int):
        all_ids = sorted(self._store.get_all_current_ids())
        dlg = MergeDialog(current_id, all_ids, self._edit_ctrl.preview_merge, parent=self)
        if dlg.exec() and dlg.result_target > 0:
            ok = self._edit_ctrl.merge_tracks(current_id, dlg.result_target)
            if ok:
                self._status.showMessage(
                    f"✓ Merged ID {current_id} → {dlg.result_target} — saved", 4000)

    @Slot(int, int)
    def _on_split_requested(self, original_id: int, frame_idx: int):
        new_id = self._store.get_next_available_id()
        dlg = SplitDialog(
            original_id, frame_idx, new_id,
            self._store.last_frame_idx(),
            self._store.preview_split,
            parent=self
        )
        if dlg.exec():
            ok, actual_new_id = self._edit_ctrl.split_track(
                original_id, dlg.result_split_frame, dlg.result_new_id)
            if ok:
                self._status.showMessage(
                    f"✓ Split ID {original_id} → new ID {actual_new_id} — saved", 4000)

    @Slot()
    def _on_verify_frame(self):
        fi = self._current_frame_idx()
        if fi >= 0:
            self._edit_ctrl.verify_frame(fi)
            self._status.showMessage(f"✓ Verified frame {fi + 1}", 2000)

    @Slot()
    def _on_undo(self):
        desc = self._edit_ctrl.undo()
        if desc:
            self._status.showMessage(f"Undo: {desc} — saved", 2000)

    @Slot()
    def _on_redo(self):
        desc = self._edit_ctrl.redo()
        if desc:
            self._status.showMessage(f"Redo: {desc} — saved", 2000)

    @Slot()
    def _on_history_changed(self):
        self._act_undo.setEnabled(self._history.can_undo())
        self._act_redo.setEnabled(self._history.can_redo())
        u = self._history.peek_undo()
        r = self._history.peek_redo()
        self._act_undo.setText(f"Undo {u}" if u else "Undo")
        self._act_redo.setText(f"Redo {r}" if r else "Redo")

    # ── Export ────────────────────────────────────────────────────────────

    def _export_mot(self):
        if not self._json_path:
            return
        default = str(Path(self._json_path).parent / "gt.txt")
        path, _ = QFileDialog.getSaveFileName(
            self, "Export MOTChallenge gt.txt", default, "Text files (*.txt)"
        )
        if path:
            try:
                uio.export_mot_challenge(path, self._store.to_export_records())
                self._status.showMessage(f"Exported: {path}", 4000)
            except Exception as ex:
                QMessageBox.critical(self, "Export error", str(ex))

    # ── BBox & Class Editing Slots ──────────────────────────────────────

    def _on_bbox_edited(self, det_idx: int, frame_idx: int, old_bbox: list, new_bbox: list):
        self._edit_ctrl.edit_bbox(frame_idx, det_idx, old_bbox, new_bbox)

    def _on_detection_created(self, frame_idx: int, bbox_xyxy: list):
        det_idx = self._edit_ctrl.add_detection(frame_idx, bbox_xyxy)
        if self._canvas:
            self._canvas.set_create_mode(False)
            if det_idx is not None:
                self._canvas.set_selected_detection(det_idx)
                self._track_panel.set_selected_detection(det_idx, frame_idx)

    def _on_delete_selected_box(self, det_idx: Optional[int] = None, frame_idx: Optional[int] = None):
        if self._canvas is None:
            return
        if det_idx is None:
            det_idx = self._canvas._selected_det
        if frame_idx is None:
            frame_idx = self._current_frame_idx()
        if det_idx is not None and frame_idx >= 0:
            self._edit_ctrl.delete_detection(frame_idx, det_idx)
            self._canvas.set_selected_detection(None)

    def _toggle_add_box_mode(self, frame_idx: Optional[int] = None):
        if self._canvas is None:
            return
        curr = self._canvas.is_create_mode()
        self._canvas.set_create_mode(not curr)
        if not curr:
            self._status.showMessage("Add Box Mode: Click and drag on empty image space to draw a box.", 4000)

    def _on_change_class(self, det_idx: int, frame_idx: int, new_cls_id: int, new_cls_name: str):
        tracks = self._store.get_frame_tracks(frame_idx)
        det = next((d for d in tracks if d.det_idx == det_idx), None)
        if det:
            self._edit_ctrl.change_class(
                frame_idx, det_idx, det.class_id, det.class_name, new_cls_id, new_cls_name
            )

    def _on_escape_pressed(self):
        if self._canvas:
            self._canvas.set_create_mode(False)
            self._canvas.set_selected_detection(None)

    def _on_save_explicit(self):
        if self._store and self._json_path:
            self._store.write_to_json()
            self._status.showMessage(f"Saved to {self._json_path}", 3000)

    def _show_shortcuts_dialog(self):
        msg = (
            "<h3>Keyboard Shortcuts</h3>"
            "<table>"
            "<tr><td><b>W</b></td><td>Toggle Add Box mode (drag mouse to draw box)</td></tr>"
            "<tr><td><b>Delete / Backspace</b></td><td>Delete selected box</td></tr>"
            "<tr><td><b>Esc</b></td><td>Deselect box / Cancel Add Box mode</td></tr>"
            "<tr><td><b>Ctrl+Z</b></td><td>Undo last action</td></tr>"
            "<tr><td><b>Ctrl+Y</b></td><td>Redo action</td></tr>"
            "<tr><td><b>S / Ctrl+S</b></td><td>Save edits to tracks.json</td></tr>"
            "<tr><td><b>Left Arrow / A</b></td><td>Previous frame</td></tr>"
            "<tr><td><b>Right Arrow / D</b></td><td>Next frame</td></tr>"
            "<tr><td><b>Space</b></td><td>Play / Pause playback (Hold + Drag to pan)</td></tr>"
            "<tr><td><b>[ / ]</b></td><td>Jump to Previous / Next track switch frame</td></tr>"
            "<tr><td><b>V</b></td><td>Verify current frame</td></tr>"
            "<tr><td><b>Ctrl + Wheel</b></td><td>Zoom in / out on canvas</td></tr>"
            "<tr><td><b>Ctrl + 0</b></td><td>Reset zoom to fit frame</td></tr>"
            "</table>"
        )
        QMessageBox.information(self, "Keyboard Shortcuts", msg)

    # ── Navigation ────────────────────────────────────────────────────────

    def _jump_to_frame_1based(self, n: int):
        pos = self._store.position_of(n - 1)
        if pos >= 0:
            self._play_ctrl.seek(pos)

    def _prev_switch(self):
        switches = self._store.get_switch_frames()
        fi = self._current_frame_idx()
        prev = [f for f in switches if f < fi]
        if prev:
            self._play_ctrl.seek(self._store.position_of(max(prev)))

    def _next_switch(self):
        switches = self._store.get_switch_frames()
        fi = self._current_frame_idx()
        nxt = [f for f in switches if f > fi]
        if nxt:
            self._play_ctrl.seek(self._store.position_of(min(nxt)))

    def _current_frame_idx(self) -> int:
        fd = self._store.get_frame_by_position(self._play_ctrl.current_position)
        return fd.frame_idx if fd else -1

    def _refresh_statistics(self):
        stats = self._store.get_statistics()
        self._track_panel.update_statistics(stats)
        self._lbl_right.setText(
            f"Tracks: {stats.get('Total tracks', 0)}  ·  "
            f"Switches: {stats.get('ID switch frames', 0)}  ·  "
            f"Corrected: {stats.get('Corrected frames', 0)}"
        )

    # ── Window ────────────────────────────────────────────────────────────

    def _update_ui_state(self):
        has = self._json_path is not None
        self._act_undo.setEnabled(False)
        self._act_redo.setEnabled(False)
        self._act_verify.setEnabled(has)
        self._act_export_mot.setEnabled(has)

    def _toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def _restore_geometry(self):
        geom, state = self._settings.load_window()
        if geom:
            self.restoreGeometry(geom)
        if state:
            self.restoreState(state)

    def closeEvent(self, e: QCloseEvent):
        self._settings.save_window(self.saveGeometry(), self.saveState())
        e.accept()

    # ── Direct open from CLI ───────────────────────────────────────────────

    def open_json(self, path: str):
        """Called from main.py when a path is passed on the command line."""
        self._load_json_file(path)
