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
from PySide6.QtGui import QAction, QKeySequence, QCloseEvent, QActionGroup
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QSplitter, QVBoxLayout, QHBoxLayout,
    QFileDialog, QMessageBox, QLabel, QInputDialog, QStatusBar, QApplication,
    QPushButton,
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
from ui.dialogs.trim_dialog import TrimDialog
from utils import io as uio
from utils.settings import AppSettings
from utils.colors import get_app_stylesheet, get_theme_colors, APP_STYLESHEET, BG_SURFACE


class MainWindow(QMainWindow):
    APP_TITLE = "Kabaddi GT Track Editor"

    def __init__(self):
        super().__init__()
        self._settings  = AppSettings()
        self._current_theme = self._settings.get_theme()
        self._json_path: Optional[str] = None   # currently open tracks.json
        self._store     = TrackStore()
        self._history   = History()
        self._edit_ctrl = EditController(self._store, self._history)
        self._play_ctrl = PlaybackController()
        self._canvas: Optional[FrameCanvas] = None

        self._build_ui()
        self._build_menus()
        self._apply_theme(self._current_theme, save=False)
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
        self._bottom_container = QWidget()
        self._bottom_container.setStyleSheet(f"background:{BG_SURFACE};")
        bl = QVBoxLayout(self._bottom_container)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(0)
        self._controls = ControlsBar()
        self._timeline = TimelineWidget()
        bl.addWidget(self._controls)
        bl.addWidget(self._timeline)
        root.addWidget(self._bottom_container)

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

        self._act_open_frames = QAction("Open &Frames Folder…", self)
        self._act_open_frames.setToolTip("Manually select the folder containing the background frames")
        file_menu.addAction(self._act_open_frames)

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
        self._act_trim   = QAction("✂  Trim Frames…", self)
        self._act_trim.setToolTip(
            "Remove unwanted frames from the beginning and/or end of the sequence"
        )
        edit_menu.addAction(self._act_undo)
        edit_menu.addAction(self._act_redo)
        edit_menu.addSeparator()
        edit_menu.addAction(self._act_verify)
        edit_menu.addSeparator()
        edit_menu.addAction(self._act_trim)

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
        view_menu.addSeparator()

        # Theme Submenu & Action
        theme_menu = view_menu.addMenu("🌓 &Theme")
        self._act_theme_dark = QAction("🌙 &Dark Mode (Default)", self, checkable=True)
        self._act_theme_light = QAction("☀️ &Light Mode", self, checkable=True)

        theme_group = QActionGroup(self)
        theme_group.addAction(self._act_theme_dark)
        theme_group.addAction(self._act_theme_light)

        self._act_theme_dark.triggered.connect(lambda: self._apply_theme("dark"))
        self._act_theme_light.triggered.connect(lambda: self._apply_theme("light"))

        theme_menu.addAction(self._act_theme_dark)
        theme_menu.addAction(self._act_theme_light)

        self._act_toggle_theme = QAction("🌓 Toggle Light / Dark Mode", self, shortcut="Ctrl+T")
        self._act_toggle_theme.triggered.connect(self._toggle_theme)
        view_menu.addAction(self._act_toggle_theme)

        # Top-Right Corner Theme Toggle Button
        self._btn_theme_toggle = QPushButton("🌙 Dark")
        self._btn_theme_toggle.setObjectName("btn_theme_toggle")
        self._btn_theme_toggle.setToolTip("Click to toggle Dark / Light Theme (Ctrl+T)")
        self._btn_theme_toggle.clicked.connect(self._toggle_theme)
        mb.setCornerWidget(self._btn_theme_toggle, Qt.TopRightCorner)

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
        self._act_open_frames.triggered.connect(self._on_open_frames_folder)
        self._act_undo.triggered.connect(self._on_undo)
        self._act_redo.triggered.connect(self._on_redo)
        self._act_verify.triggered.connect(self._on_verify_frame)
        self._act_export_mot.triggered.connect(self._export_mot)
        self._act_trim.triggered.connect(self._on_trim_frames)

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
        self._timeline.range_changed.connect(self._on_timeline_range_changed)

        self._controls.range_bounds_changed.connect(self._on_controls_range_changed)
        self._controls.range_reset_requested.connect(self._on_range_reset_requested)

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
        self._track_panel.range_bounds_changed.connect(self._on_controls_range_changed)
        self._track_panel.range_reset_requested.connect(self._on_range_reset_requested)

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

        # Theme toggle shortcut
        QShortcut(QKeySequence("Ctrl+T"), self).activated.connect(self._toggle_theme)

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
        # Priority 0: read frames_folder embedded directly in the JSON records
        frames_dir = ""
        if records and isinstance(records[0], dict):
            embedded = records[0].get("frames_folder", "")
            if embedded:
                p_emb = Path(embedded)
                if p_emb.is_dir():
                    frames_dir = str(p_emb.resolve())
                elif (Path(json_path).parent / p_emb).is_dir():
                    frames_dir = str((Path(json_path).parent / p_emb).resolve())
        if not frames_dir:
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
        self._canvas.set_theme(self._current_theme)
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
        self._track_panel.setup_range_bounds(self._store.frame_count, 1, self._store.frame_count)
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

        Handles:
          - Standard dataset paths: dhruba_dataset_processed/raid/toe_touch/bytetrack/bytetrack_toe1_frames/tracks.json
          - Staging paths: class_labelled_ground_truth/dhruba_dataset_processed/.../tracks.json
          - Ambiguous flat paths: ambiguous/videos/ak6/tracks.json
          - Ambiguous class paths: ambiguous/by_class/defend/ankle_hold/bytetrack_ak6_frames/tracks.json
        """
        p = Path(json_path).resolve()
        folder = p.parent.name
        vid_target = folder.replace("bytetrack_", "").replace("_frames", "")

        # Strategy -2: Check embedded frames_folder in JSON records
        try:
            import json as _json
            with open(json_path, "r", encoding="utf-8") as _f:
                _data = _json.load(_f)
                if isinstance(_data, list) and _data and isinstance(_data[0], dict):
                    _emb = _data[0].get("frames_folder", "")
                    if _emb:
                        _p_emb = Path(_emb)
                        if _p_emb.is_dir():
                            return str(_p_emb.resolve())
                        _rel = (p.parent / _p_emb).resolve()
                        if _rel.is_dir():
                            return str(_rel)
        except Exception:
            pass

        # Strategy -1: If the folder containing the JSON has images, use it directly.
        # Handles custom folders like 'exception' or 'exception2'.
        if list(p.parent.glob("*.jpg")) or list(p.parent.glob("*.png")):
            return str(p.parent)

        # Strategy -1b: If a 'frames' or 'source_frames' subfolder exists alongside tracks.json, use it
        for sub in ("frames", "source_frames"):
            cand = p.parent / sub
            if cand.is_dir() and (list(cand.glob("*.jpg")) or list(cand.glob("*.png"))):
                return str(cand.resolve())

        # Strategy -1c: Check parent's 'frames' or 'source_frames' directory (e.g. diagnostic_analysis/frames/C01)
        for parent_sub in ("frames", "source_frames"):
            cand = p.parent.parent / parent_sub / folder
            if cand.is_dir() and (list(cand.glob("*.jpg")) or list(cand.glob("*.png"))):
                return str(cand.resolve())

        # Strategy 0a: Diagnostic case mapping
        case_map = {
            "C01": "dubki16", "C02": "toe1", "C03": "dubki36", "C04": "lionjump20",
            "C05": "lionjump25", "C06": "toe48", "C07": "toe21", "C08": "block54",
            "C09": "wh19", "C10": "dash45",
        }
        if folder in case_map:
            vid_target = case_map[folder]

        # Find project root by searching upwards for dhruba_dataset_processed
        project_root = p.parent
        while project_root.parent != project_root:
            if (project_root / "dhruba_dataset_processed").is_dir():
                break
            project_root = project_root.parent

        if not (project_root / "dhruba_dataset_processed").is_dir():
            # Fallback to file location's root
            project_root = Path(__file__).resolve().parent.parent.parent

        dataset_root = project_root / "dhruba_dataset_processed"

        # Strategy 0: Direct search by video name in dhruba_dataset_processed
        if dataset_root.is_dir() and vid_target:
            # Look for exact '{vid_target}_frames'
            exact_matches = list(dataset_root.glob(f"**/frames/{vid_target}_frames"))
            if exact_matches and exact_matches[0].is_dir():
                return str(exact_matches[0])

            # Look for partial matches containing vid_target
            partial_matches = list(dataset_root.glob(f"**/frames/*{vid_target}*_frames"))
            if partial_matches and partial_matches[0].is_dir():
                return str(partial_matches[0])

        # Strategy 1: Check manifest.json if path is inside ambiguous directory
        manifest_path = project_root / "ambiguous" / "manifest.json"
        if manifest_path.exists():
            try:
                import json as _j
                manifest = _j.loads(manifest_path.read_text(encoding="utf-8"))
                for item in manifest:
                    if item.get("video") == vid_target or item.get("flat_path") in str(json_path):
                        f_dir_rel = item.get("frames_dir", "")
                        f_dir_abs = project_root / f_dir_rel
                        if f_dir_abs.is_dir():
                            return str(f_dir_abs)
            except Exception:
                pass

        # Strategy 2: Relative class directory structure (ClassName / frames / sub)
        if folder.startswith("bytetrack_"):
            sub = folder[len("bytetrack_"):]
            if p.parent.parent.name == "bytetrack":
                class_dir = p.parent.parent.parent
            else:
                class_dir = p.parent.parent
            candidate = class_dir / "frames" / sub
            if candidate.is_dir():
                return str(candidate)

        # Strategy 3: Parent frames directory
        if p.parent.parent.name == "bytetrack":
            class_dir = p.parent.parent.parent
        else:
            class_dir = p.parent.parent
        frames_parent = class_dir / "frames"
        if frames_parent.is_dir():
            candidate = frames_parent / folder.replace("bytetrack_", "")
            if candidate.is_dir():
                return str(candidate)
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

    # ── Open Frames Folder ────────────────────────────────────────────────

    @Slot()
    def _on_open_frames_folder(self):
        """Let user manually pick the folder with background frame images."""
        if not self._json_path:
            QMessageBox.information(self, "No JSON Loaded",
                                   "Please open a tracks.json file first.")
            return
        from PySide6.QtWidgets import QFileDialog
        last = self._settings.get_last_dir() or str(Path.home())
        path = QFileDialog.getExistingDirectory(self, "Select Frames Folder", last)
        if path:
            self._canvas.set_frames_dir(path)
            self._status.showMessage(f"Frames folder set to: {path}", 5000)
            # Refresh current frame display
            if self._store.frame_count > 0:
                self._on_frame_position_changed(self._play_ctrl.current_position)

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

    def _on_change_class(self, det_idx: int, frame_idx: int, new_cls_id: int, new_cls_name: str, propagate: bool = True):
        tracks = self._store.get_frame_tracks(frame_idx)
        det = next((d for d in tracks if d.det_idx == det_idx), None)
        if det:
            target_id = det.current_id
            ok = self._edit_ctrl.change_class(
                frame_idx, det_idx, det.class_id, det.class_name, new_cls_id, new_cls_name, propagate=propagate
            )
            if not ok:
                if propagate:
                    self._status.showMessage(
                        f"ID {target_id} is already '{new_cls_name}' on this and all subsequent frames.", 3000
                    )
            else:
                if propagate:
                    self._status.showMessage(
                        f"Updated class for ID {target_id} to '{new_cls_name}' across all subsequent frames.", 4000
                    )
                else:
                    self._status.showMessage(
                        f"Updated class for ID {target_id} to '{new_cls_name}' on frame {frame_idx + 1}.", 3000
                    )

    def _on_escape_pressed(self):
        if self._canvas:
            self._canvas.set_create_mode(False)
            self._canvas.set_selected_detection(None)

    def _on_save_explicit(self):
        if self._store and self._json_path:
            self._store.write_to_json()
            self._status.showMessage(f"Saved to {self._json_path}", 3000)

    # ── Trim ──────────────────────────────────────────────────────────────

    def _get_frame_thumbnail(self, pos: int):
        """Return a QPixmap for the frame at 0-based position, or None."""
        from PySide6.QtGui import QPixmap
        if self._canvas is None:
            return None
        fd = self._store.get_frame_by_position(pos)
        if fd is None:
            return None
        # Reuse the canvas's internal image loader
        pix = self._canvas._load_pixmap(fd.frame_name)
        return pix

    @Slot()
    def _on_trim_frames(self):
        """Open the Trim Frames dialog and apply the trim on acceptance."""
        if not self._json_path or self._store.frame_count == 0:
            return

        dlg = TrimDialog(
            total_frames  = self._store.frame_count,
            get_thumbnail = self._get_frame_thumbnail,
            parent        = self,
        )
        if not dlg.exec():
            return

        start_pos         = dlg.result_start_pos
        end_pos           = dlg.result_end_pos
        delete_images     = dlg.result_delete_images

        # Perform the trim — returns removed FrameData list
        removed_frames = self._store.trim_frames(start_pos, end_pos)

        # Optionally delete image files from disk
        deleted_count = 0
        if delete_images and self._canvas is not None:
            frames_dir = self._canvas._frames_dir
            for fd in removed_frames:
                # Try common image extensions
                for ext in (".jpg", ".jpeg", ".png", ".bmp", ".webp"):
                    img_path = Path(frames_dir) / (fd.frame_name + ext)
                    if img_path.exists():
                        try:
                            img_path.unlink()
                            deleted_count += 1
                        except Exception:
                            pass
                        break

        # Reset playback and UI to the new (shorter) sequence
        new_count = self._store.frame_count
        self._play_ctrl.setup(new_count, 0)
        self._controls.setup(new_count)
        self._timeline.setup([f.frame_idx for f in self._store.all_frames()])
        self._refresh_timeline_markers()
        self._on_frame_position_changed(0)
        self._refresh_statistics()

        trim_start = start_pos
        trim_end   = self._store.frame_count  # already trimmed, so this is relative
        removed_n  = len(removed_frames)
        msg = (
            f"✂ Trimmed {removed_n} frame(s) — {new_count} frames remain"
            + (f"; deleted {deleted_count} image file(s) from disk" if deleted_count else "")
            + f" — saved to {Path(self._json_path).name}"
        )
        self._status.showMessage(msg, 6000)

    def _show_shortcuts_dialog(self):
        msg = (
            "<h3>Keyboard Shortcuts</h3>"
            "<table>"
            "<tr><td><b>W</b></td><td>Toggle Add Box mode (drag mouse to draw box)</td></tr>"
            "<tr><td><b>Delete / Backspace</b></td><td>Delete selected box</td></tr>"
            "<tr><td><b>Esc</b></td><td>Deselect box / Cancel Add Box mode</td></tr>"
            "<tr><td><b>Ctrl+Z</b></td><td>Undo last action</td></tr>"
            "<tr><td><b>Ctrl+Y</b></td><td>Redo action</td></tr>"
            "<tr><td><b>Ctrl+T</b></td><td>Toggle Dark / Light theme</td></tr>"
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

    def _on_timeline_range_changed(self, start_pos: int, end_pos: int):
        if not self._store or self._store.frame_count == 0:
            return
        self._store.set_range_bounds(start_pos, end_pos)
        all_f = self._store.all_frames()
        if 0 <= start_pos < len(all_f) and 0 <= end_pos < len(all_f):
            s_1based = all_f[start_pos].frame_idx + 1
            e_1based = all_f[end_pos].frame_idx + 1
            self._controls.set_range_bounds(s_1based, e_1based)
            self._track_panel.set_range_bounds(s_1based, e_1based)
            active_count = end_pos - start_pos + 1
            self._status.showMessage(
                f"Sliding Window set: Frames {s_1based} .. {e_1based} ({active_count} active frames)", 3000
            )

    def _on_controls_range_changed(self, start_1based: int, end_1based: int):
        if not self._store or self._store.frame_count == 0:
            return
        pos_start = self._store.position_of(start_1based - 1)
        pos_end   = self._store.position_of(end_1based - 1)
        if pos_start < 0:
            pos_start = 0
        if pos_end < 0:
            pos_end = self._store.frame_count - 1
        self._timeline.set_range(pos_start, pos_end)
        self._controls.set_range_bounds(start_1based, end_1based)
        self._track_panel.set_range_bounds(start_1based, end_1based)
        self._store.set_range_bounds(pos_start, pos_end)
        active_count = max(0, pos_end - pos_start + 1)
        self._status.showMessage(
            f"Sliding Window set: Frames {start_1based} .. {end_1based} ({active_count} active frames)", 3000
        )

    def _on_range_reset_requested(self):
        if not self._store or self._store.frame_count == 0:
            return
        self._store.reset_range()
        sp, ep = self._store.get_range_bounds()
        self._timeline.set_range(sp, ep)
        all_f = self._store.all_frames()
        if all_f:
            s_1based = all_f[sp].frame_idx + 1
            e_1based = all_f[ep].frame_idx + 1
            self._controls.set_range_bounds(s_1based, e_1based)
            self._track_panel.set_range_bounds(s_1based, e_1based)
        self._status.showMessage("Sliding Window reset to full sequence", 3000)

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
        self._act_trim.setEnabled(has)

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

    # ── Theme Management ──────────────────────────────────────────────────

    def _toggle_theme(self):
        next_theme = "light" if self._current_theme == "dark" else "dark"
        self._apply_theme(next_theme, save=True)

    def _apply_theme(self, theme_name: str, save: bool = True):
        self._current_theme = theme_name
        app = QApplication.instance()
        if app:
            app.setStyleSheet(get_app_stylesheet(theme_name))

        colors = get_theme_colors(theme_name)
        if hasattr(self, "_canvas_placeholder") and self._canvas_placeholder:
            self._canvas_placeholder.setStyleSheet(
                f"background:{colors['BG_BASE']}; font-size:15px; color:{colors['TEXT_SEC']};"
            )
        if hasattr(self, "_bottom_container") and self._bottom_container:
            self._bottom_container.setStyleSheet(f"background:{colors['BG_SURFACE']};")

        if hasattr(self, "_timeline") and self._timeline:
            self._timeline.set_theme(theme_name)

        if hasattr(self, "_canvas") and self._canvas:
            self._canvas.set_theme(theme_name)

        if hasattr(self, "_track_panel") and self._track_panel:
            self._track_panel.set_theme(theme_name)

        if hasattr(self, "_act_theme_dark") and hasattr(self, "_act_theme_light"):
            self._act_theme_dark.setChecked(theme_name == "dark")
            self._act_theme_light.setChecked(theme_name == "light")

        if hasattr(self, "_btn_theme_toggle") and self._btn_theme_toggle:
            if theme_name == "dark":
                self._btn_theme_toggle.setText("🌙 Dark")
                self._btn_theme_toggle.setToolTip("Currently Dark Mode. Click to switch to Light Mode (Ctrl+T)")
            else:
                self._btn_theme_toggle.setText("☀️ Light")
                self._btn_theme_toggle.setToolTip("Currently Light Mode. Click to switch to Dark Mode (Ctrl+T)")

        if save:
            self._settings.set_theme(theme_name)
            mode_str = "Light" if theme_name == "light" else "Dark"
            self._status.showMessage(f"Theme switched to {mode_str} Mode", 2500)

    # ── Direct open from CLI ───────────────────────────────────────────────

    def open_json(self, path: str):
        """Called from main.py when a path is passed on the command line."""
        self._load_json_file(path)
