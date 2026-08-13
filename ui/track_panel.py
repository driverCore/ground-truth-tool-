"""Track Panel — right-side panel showing selected detection info, bounding box controls, and all tracks in frame."""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QGroupBox, QFrame, QComboBox,
)

from models.track_store import EffectiveDet, TrackStore
from utils.colors import (
    track_color, STATUS_COLORS, ACCENT, WARNING, DANGER,
    TEXT_SEC, BG_PANEL, BG_SURFACE,
)


class TrackPanel(QWidget):
    """Right-side panel for detection & bounding box editing.

    Emits:
        change_id_requested(det_idx, frame_idx)
        merge_requested(current_id)
        split_requested(original_id, frame_idx)
        verify_frame_requested(frame_idx)
        track_selected(det_idx)
        delete_box_requested(det_idx, frame_idx)
        add_box_requested(frame_idx)
        change_class_requested(det_idx, frame_idx, new_cls_id, new_cls_name)
    """

    change_id_requested    = Signal(int, int)   # det_idx, frame_idx
    merge_requested        = Signal(int)         # current_id
    split_requested        = Signal(int, int)    # original_id, frame_idx
    verify_frame_requested = Signal(int)       # frame_idx
    track_selected         = Signal(int)         # det_idx
    delete_box_requested   = Signal(int, int)   # det_idx, frame_idx
    add_box_requested      = Signal(int)         # frame_idx
    change_class_requested = Signal(int, int, int, str) # det_idx, frame_idx, cls_id, cls_name

    CLASSES = [
        (0, "player"),
        (1, "referee"),
        (2, "defender"),
        (3, "raider"),
    ]

    def __init__(self, store: TrackStore, parent=None):
        super().__init__(parent)
        self._store       = store
        self._frame_idx   = -1
        self._detections: list[EffectiveDet] = []
        self._selected: Optional[EffectiveDet] = None
        self.setMinimumWidth(270)
        self.setMaximumWidth(350)
        self._build_ui()

    # ── Build UI ──────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        # ── Selected track info & controls ──────────────────────────────
        self._grp_selected = QGroupBox("Selected BBox & Player")
        sg = QVBoxLayout(self._grp_selected)
        sg.setSpacing(4)

        def lrow(label_text: str, obj_name: str = "") -> tuple[QLabel, QLabel]:
            row = QHBoxLayout()
            lbl = QLabel(label_text + ":")
            lbl.setObjectName("label_secondary")
            lbl.setFixedWidth(90)
            val = QLabel("—")
            if obj_name:
                val.setObjectName(obj_name)
            row.addWidget(lbl)
            row.addWidget(val)
            row.addStretch()
            sg.addLayout(row)
            return lbl, val

        _, self._lbl_cur_id   = lrow("Current ID",  "label_stat_value")
        _, self._lbl_orig_id  = lrow("Original ID")

        # Class selector row
        class_row = QHBoxLayout()
        lbl_c = QLabel("Class:")
        lbl_c.setObjectName("label_secondary")
        lbl_c.setFixedWidth(90)
        self._combo_class = QComboBox()
        for cid, cname in self.CLASSES:
            self._combo_class.addItem(f"{cid}: {cname}", (cid, cname))
        self._combo_class.currentIndexChanged.connect(self._on_class_changed)
        class_row.addWidget(lbl_c)
        class_row.addWidget(self._combo_class, stretch=1)
        sg.addLayout(class_row)

        _, self._lbl_status   = lrow("Status")
        _, self._lbl_bbox     = lrow("BBox xyxy")
        _, self._lbl_conf     = lrow("Confidence")
        _, self._lbl_span     = lrow("Track span")

        sep1 = QFrame(); sep1.setFrameShape(QFrame.HLine)
        sg.addWidget(sep1)

        # BBox & ID action buttons
        btn_row1 = QHBoxLayout()
        self._btn_add_box = QPushButton("+ Add Box (A)")
        self._btn_add_box.setToolTip("Add new bounding box to this frame (Key: A)")
        self._btn_add_box.clicked.connect(self._on_add_box)
        btn_row1.addWidget(self._btn_add_box)

        self._btn_del_box = QPushButton("Delete Box")
        self._btn_del_box.setStyleSheet("background-color: #d32f2f; color: white;")
        self._btn_del_box.setToolTip("Delete selected bounding box (Delete key)")
        self._btn_del_box.clicked.connect(self._on_delete_box)
        btn_row1.addWidget(self._btn_del_box)
        sg.addLayout(btn_row1)

        btn_row2 = QHBoxLayout()
        self._btn_change_id = QPushButton("Change ID")
        self._btn_change_id.setObjectName("btn_primary")
        self._btn_change_id.setToolTip("Edit this player's track ID")
        self._btn_change_id.clicked.connect(self._on_change_id)
        btn_row2.addWidget(self._btn_change_id)

        self._btn_verify = QPushButton("✓ Verify Frame")
        self._btn_verify.setObjectName("btn_success")
        self._btn_verify.setToolTip("Mark all tracks in this frame as verified")
        self._btn_verify.clicked.connect(self._on_verify)
        btn_row2.addWidget(self._btn_verify)
        sg.addLayout(btn_row2)

        btn_row3 = QHBoxLayout()
        self._btn_merge = QPushButton("Merge Track")
        self._btn_merge.setToolTip("Merge this track into another ID")
        self._btn_merge.clicked.connect(self._on_merge)
        btn_row3.addWidget(self._btn_merge)

        self._btn_split = QPushButton("Split Here")
        self._btn_split.setToolTip("Split this track at current frame")
        self._btn_split.clicked.connect(self._on_split)
        btn_row3.addWidget(self._btn_split)
        sg.addLayout(btn_row3)

        self._set_selected_enabled(False)
        root.addWidget(self._grp_selected)

        # ── All tracks in frame ──────────────────────────────────────────
        self._grp_all = QGroupBox("All Tracks — This Frame")
        ag = QVBoxLayout(self._grp_all)
        ag.setContentsMargins(4, 4, 4, 4)
        self._track_list = QListWidget()
        self._track_list.setSpacing(1)
        self._track_list.currentRowChanged.connect(self._on_list_selection_changed)
        ag.addWidget(self._track_list)
        root.addWidget(self._grp_all)

        # ── Statistics ────────────────────────────────────────────────────
        self._grp_stats = QGroupBox("Session Statistics")
        stg = QVBoxLayout(self._grp_stats)
        stg.setSpacing(3)
        self._stats_labels: dict[str, QLabel] = {}
        for key in ("Total frames", "Corrected frames", "Verified frames",
                    "ID switch frames", "Total tracks"):
            row = QHBoxLayout()
            k = QLabel(key + ":"); k.setObjectName("label_secondary"); k.setFixedWidth(120)
            v = QLabel("—")
            row.addWidget(k); row.addWidget(v); row.addStretch()
            stg.addLayout(row)
            self._stats_labels[key] = v
        root.addWidget(self._grp_stats)
        root.addStretch()

    # ── Public API ────────────────────────────────────────────────────────

    def update_frame(self, frame_idx: int, detections: list[EffectiveDet]):
        self._frame_idx  = frame_idx
        self._detections = detections
        self._selected   = None
        self._refresh_track_list()
        self._refresh_selected_panel(None)

    def set_selected_detection(self, det_idx: int, frame_idx: int):
        self._frame_idx = frame_idx
        self._selected  = next((d for d in self._detections if d.det_idx == det_idx), None)
        self._refresh_selected_panel(self._selected)
        # Sync list
        for i in range(self._track_list.count()):
            item = self._track_list.item(i)
            if item.data(Qt.UserRole) == det_idx:
                self._track_list.blockSignals(True)
                self._track_list.setCurrentRow(i)
                self._track_list.blockSignals(False)
                break

    def update_statistics(self, stats: dict):
        for k, v in stats.items():
            if k in self._stats_labels:
                self._stats_labels[k].setText(str(v))

    # ── Internal refresh ──────────────────────────────────────────────────

    def _refresh_track_list(self):
        self._track_list.blockSignals(True)
        self._track_list.clear()
        for det in self._detections:
            span_s, span_e, length = self._store.get_original_id_span(det.original_id)
            status_sym = {"verified": "●", "edited": "◑", "unreviewed": "○"}.get(det.status, "○")
            color_hex  = track_color(det.current_id).name()
            text = f"{status_sym}  ID {det.current_id:>3}  ·  frames {span_s+1}–{span_e+1}  ({length}f)"
            if det.original_id != det.current_id:
                text += f"  [was {det.original_id}]"
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, det.det_idx)
            item.setForeground(QColor(color_hex))
            self._track_list.addItem(item)
        self._track_list.blockSignals(False)

    def _refresh_selected_panel(self, det: Optional[EffectiveDet]):
        if det is None:
            self._lbl_cur_id.setText("—")
            self._lbl_orig_id.setText("—")
            self._combo_class.blockSignals(True)
            self._combo_class.setCurrentIndex(0)
            self._combo_class.blockSignals(False)
            self._lbl_status.setText("—")
            self._lbl_bbox.setText("—")
            self._lbl_conf.setText("—")
            self._lbl_span.setText("—")
            self._set_selected_enabled(False)
            return

        s, e, length = self._store.get_original_id_span(det.original_id)
        x1, y1, x2, y2 = [int(v) for v in det.bbox_xyxy]
        status_text = {"verified": "✓ Verified", "edited": "✎ Edited",
                       "unreviewed": "○ Unreviewed"}.get(det.status, det.status)

        self._lbl_cur_id.setText(str(det.current_id))
        self._lbl_cur_id.setStyleSheet(f"color: {track_color(det.current_id).name()}; font-weight:bold; font-size:14px;")
        self._lbl_orig_id.setText(str(det.original_id))

        self._combo_class.blockSignals(True)
        matched_idx = 0
        for i, (cid, cname) in enumerate(self.CLASSES):
            if det.class_id == cid or det.class_name == cname:
                matched_idx = i
                break
        self._combo_class.setCurrentIndex(matched_idx)
        self._combo_class.blockSignals(False)

        self._lbl_status.setText(status_text)
        self._lbl_bbox.setText(f"[{x1},{y1},{x2},{y2}]")
        self._lbl_conf.setText(f"{det.conf:.3f}")
        self._lbl_span.setText(f"frame {s+1} – {e+1}")
        self._set_selected_enabled(True)

    def _set_selected_enabled(self, enabled: bool):
        self._btn_change_id.setEnabled(enabled)
        self._btn_del_box.setEnabled(enabled)
        self._btn_merge.setEnabled(enabled)
        self._btn_split.setEnabled(enabled)
        self._combo_class.setEnabled(enabled)

    # ── Slots ─────────────────────────────────────────────────────────────

    def _on_list_selection_changed(self, row: int):
        item = self._track_list.item(row)
        if item is None:
            return
        det_idx = item.data(Qt.UserRole)
        det = next((d for d in self._detections if d.det_idx == det_idx), None)
        self._selected = det
        self._refresh_selected_panel(det)
        self.track_selected.emit(det_idx)

    def _on_change_id(self):
        if self._selected and self._frame_idx >= 0:
            self.change_id_requested.emit(self._selected.det_idx, self._frame_idx)

    def _on_delete_box(self):
        if self._selected and self._frame_idx >= 0:
            self.delete_box_requested.emit(self._selected.det_idx, self._frame_idx)

    def _on_add_box(self):
        if self._frame_idx >= 0:
            self.add_box_requested.emit(self._frame_idx)

    def _on_class_changed(self, idx: int):
        if self._selected and self._frame_idx >= 0:
            cid, cname = self._combo_class.itemData(idx)
            self.change_class_requested.emit(
                self._selected.det_idx, self._frame_idx, cid, cname
            )

    def _on_merge(self):
        if self._selected:
            self.merge_requested.emit(self._selected.current_id)

    def _on_split(self):
        if self._selected and self._frame_idx >= 0:
            self.split_requested.emit(self._selected.original_id, self._frame_idx)

    def _on_verify(self):
        if self._frame_idx >= 0:
            self.verify_frame_requested.emit(self._frame_idx)
