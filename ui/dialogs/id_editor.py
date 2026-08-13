"""ID Editor dialog — change a player's track ID with scope selection and propagation preview."""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QSpinBox,
    QRadioButton, QButtonGroup, QGroupBox, QDialogButtonBox,
    QListWidget, QListWidgetItem, QFrame, QPushButton, QSizePolicy,
)

from utils.colors import ACCENT, WARNING, DANGER, TEXT_SEC, BG_PANEL


class IdEditorDialog(QDialog):
    """Modal dialog to change a detection's track ID.

    After the user confirms, call .result_scope / .result_new_id / .result_end_frame
    to retrieve what was selected.
    """

    def __init__(self,
                 current_id:   int,
                 original_id:  int,
                 frame_idx:    int,
                 max_frame:    int,
                 preview_fn,           # callable(det_idx, new_id, scope, end) -> list
                 det_idx:      int,
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle("Change Player ID")
        self.setMinimumWidth(420)
        self.setModal(True)

        self._current_id  = current_id
        self._original_id = original_id
        self._frame_idx   = frame_idx
        self._max_frame   = max_frame
        self._preview_fn  = preview_fn
        self._det_idx     = det_idx

        # Results
        self.result_new_id    = current_id
        self.result_scope     = "frame"
        self.result_end_frame: Optional[int] = None

        self._build_ui()
        self._connect()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(12)
        root.setContentsMargins(16, 16, 16, 16)

        # ── Info row ──────────────────────────────────────────────────────
        info = QLabel(
            f"<b>Player</b> &nbsp; ByteTrack ID: <span style='color:{ACCENT}'>{self._original_id}</span>"
            f" &nbsp;|&nbsp; Current: <span style='color:{WARNING}'>{self._current_id}</span>"
            f" &nbsp;|&nbsp; Frame: {self._frame_idx}"
        )
        info.setTextFormat(Qt.RichText)
        root.addWidget(info)

        sep = QFrame(); sep.setFrameShape(QFrame.HLine)
        root.addWidget(sep)

        # ── New ID ────────────────────────────────────────────────────────
        id_row = QHBoxLayout()
        id_row.addWidget(QLabel("New ID:"))
        self._spin_id = QSpinBox()
        self._spin_id.setRange(1, 9999)
        self._spin_id.setValue(self._current_id)
        self._spin_id.setFixedWidth(90)
        id_row.addWidget(self._spin_id)
        id_row.addStretch()
        root.addLayout(id_row)

        # ── Scope ─────────────────────────────────────────────────────────
        scope_box = QGroupBox("Apply to")
        scope_layout = QVBoxLayout(scope_box)
        self._btn_grp = QButtonGroup(self)

        self._rb_frame   = QRadioButton("This frame only")
        self._rb_forward = QRadioButton("This frame and all forward (until conflict)")
        self._rb_range   = QRadioButton("Custom range:")
        self._rb_frame.setChecked(True)

        for rb in (self._rb_frame, self._rb_forward, self._rb_range):
            self._btn_grp.addButton(rb)
            scope_layout.addWidget(rb)

        range_row = QHBoxLayout()
        range_row.setContentsMargins(24, 0, 0, 0)
        range_row.addWidget(QLabel("From frame:"))
        self._spin_from = QSpinBox()
        self._spin_from.setRange(0, self._max_frame)
        self._spin_from.setValue(self._frame_idx)
        self._spin_from.setEnabled(False)
        range_row.addWidget(self._spin_from)
        range_row.addWidget(QLabel("to frame:"))
        self._spin_to = QSpinBox()
        self._spin_to.setRange(0, self._max_frame)
        self._spin_to.setValue(self._max_frame)
        self._spin_to.setEnabled(False)
        range_row.addWidget(self._spin_to)
        range_row.addStretch()
        scope_layout.addLayout(range_row)
        root.addWidget(scope_box)

        # ── Preview button + list ─────────────────────────────────────────
        self._btn_preview = QPushButton("Preview Changes")
        self._btn_preview.setObjectName("btn_primary")
        root.addWidget(self._btn_preview)

        self._preview_label = QLabel("Click 'Preview Changes' to see affected frames.")
        self._preview_label.setObjectName("label_secondary")
        root.addWidget(self._preview_label)

        self._preview_list = QListWidget()
        self._preview_list.setMaximumHeight(120)
        root.addWidget(self._preview_list)

        # ── Dialog buttons ────────────────────────────────────────────────
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setText("Apply")
        btns.button(QDialogButtonBox.Ok).setObjectName("btn_primary")
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

    def _connect(self):
        self._rb_range.toggled.connect(self._on_range_toggled)
        self._btn_preview.clicked.connect(self._on_preview)
        self._spin_id.valueChanged.connect(self._clear_preview)
        self._btn_grp.buttonClicked.connect(self._clear_preview)

    def _on_range_toggled(self, checked: bool):
        self._spin_from.setEnabled(checked)
        self._spin_to.setEnabled(checked)

    def _clear_preview(self):
        self._preview_list.clear()
        self._preview_label.setText("Click 'Preview Changes' to see affected frames.")

    def _on_preview(self):
        new_id   = self._spin_id.value()
        scope    = self._current_scope()
        end_f    = self._spin_to.value() if scope == "range" else None
        changes  = self._preview_fn(self._det_idx, new_id, scope, end_f)

        self._preview_list.clear()
        if not changes:
            self._preview_label.setText("No changes would be made.")
            return
        self._preview_label.setText(f"{len(changes)} detection(s) will be updated:")
        for fi, di, old in changes:
            item = QListWidgetItem(f"  Frame {fi}  ·  det {di}  :  ID {old} → {new_id}")
            self._preview_list.addItem(item)

    def _current_scope(self) -> str:
        if self._rb_frame.isChecked():
            return "frame"
        if self._rb_forward.isChecked():
            return "forward"
        return "range"

    def _on_accept(self):
        self.result_new_id    = self._spin_id.value()
        self.result_scope     = self._current_scope()
        self.result_end_frame = self._spin_to.value() if self.result_scope == "range" else None
        self.accept()
