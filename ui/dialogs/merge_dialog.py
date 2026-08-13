"""Merge Tracks dialog — merge source_id into target_id."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QSpinBox,
    QDialogButtonBox, QListWidget, QListWidgetItem, QFrame, QPushButton,
)

from utils.colors import ACCENT, DANGER


class MergeDialog(QDialog):
    def __init__(self, source_id: int, all_ids: list[int], preview_fn, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Merge Tracks")
        self.setMinimumWidth(380)
        self.setModal(True)

        self._source_id  = source_id
        self._all_ids    = sorted(all_ids)
        self._preview_fn = preview_fn

        self.result_source = source_id
        self.result_target = -1

        self._build_ui()
        self._connect()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(10)
        root.setContentsMargins(16, 16, 16, 16)

        root.addWidget(QLabel(
            f"<b>Source (will be absorbed):</b> "
            f"<span style='color:{DANGER}'>ID {self._source_id}</span>",
            textFormat=Qt.RichText,
        ))

        row = QHBoxLayout()
        row.addWidget(QLabel("Merge INTO ID:"))
        self._spin_target = QSpinBox()
        self._spin_target.setRange(1, 9999)
        # Default to first other ID
        others = [i for i in self._all_ids if i != self._source_id]
        if others:
            self._spin_target.setValue(others[0])
        row.addWidget(self._spin_target)
        row.addStretch()
        root.addLayout(row)

        sep = QFrame(); sep.setFrameShape(QFrame.HLine)
        root.addWidget(sep)

        self._btn_preview = QPushButton("Preview")
        self._btn_preview.setObjectName("btn_primary")
        root.addWidget(self._btn_preview)

        self._preview_label = QLabel("Frames affected: —")
        self._preview_label.setObjectName("label_secondary")
        root.addWidget(self._preview_label)

        self._list = QListWidget()
        self._list.setMaximumHeight(110)
        root.addWidget(self._list)

        root.addWidget(QLabel(
            f"<span style='color:{DANGER}'><b>Warning:</b> Source ID {self._source_id} "
            f"will no longer exist after merging.</span>",
            textFormat=Qt.RichText,
        ))

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setText("Merge")
        btns.button(QDialogButtonBox.Ok).setObjectName("btn_danger")
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

    def _connect(self):
        self._btn_preview.clicked.connect(self._on_preview)

    def _on_preview(self):
        target = self._spin_target.value()
        if target == self._source_id:
            self._preview_label.setText("Source and target must differ.")
            return
        changes = self._preview_fn(self._source_id, target)
        self._list.clear()
        self._preview_label.setText(f"{len(changes)} detection(s) affected:")
        for fi, di, old in changes:
            self._list.addItem(f"  Frame {fi}  ·  det {di}  :  ID {old} → {target}")

    def _on_accept(self):
        self.result_target = self._spin_target.value()
        self.accept()


class SplitDialog(QDialog):
    """Split a track from a given frame, creating a new ID."""

    def __init__(self, original_id: int, frame_idx: int, suggested_new_id: int,
                 max_frame: int, preview_fn, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Split Track")
        self.setMinimumWidth(360)
        self.setModal(True)

        self._original_id       = original_id
        self._frame_idx         = frame_idx
        self._suggested_new_id  = suggested_new_id
        self._max_frame         = max_frame
        self._preview_fn        = preview_fn

        self.result_split_frame = frame_idx
        self.result_new_id      = suggested_new_id

        self._build_ui()
        self._connect()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(10)
        root.setContentsMargins(16, 16, 16, 16)

        root.addWidget(QLabel(
            f"<b>Split Track ID {self._original_id}</b>  at frame:",
            textFormat=Qt.RichText,
        ))

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Split at frame:"))
        self._spin_frame = QSpinBox()
        self._spin_frame.setRange(0, self._max_frame)
        self._spin_frame.setValue(self._frame_idx)
        row1.addWidget(self._spin_frame)
        row1.addStretch()
        root.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("New ID (from split frame):"))
        self._spin_new = QSpinBox()
        self._spin_new.setRange(1, 9999)
        self._spin_new.setValue(self._suggested_new_id)
        row2.addWidget(self._spin_new)
        row2.addStretch()
        root.addLayout(row2)

        sep = QFrame(); sep.setFrameShape(QFrame.HLine)
        root.addWidget(sep)

        self._btn_preview = QPushButton("Preview")
        self._btn_preview.setObjectName("btn_primary")
        root.addWidget(self._btn_preview)

        self._preview_label = QLabel("Frames that will be re-assigned: —")
        self._preview_label.setObjectName("label_secondary")
        root.addWidget(self._preview_label)

        self._list = QListWidget()
        self._list.setMaximumHeight(100)
        root.addWidget(self._list)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setText("Split")
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

    def _connect(self):
        self._btn_preview.clicked.connect(self._on_preview)

    def _on_preview(self):
        sf     = self._spin_frame.value()
        new_id = self._spin_new.value()
        changes = self._preview_fn(self._original_id, sf, new_id)
        self._list.clear()
        self._preview_label.setText(f"{len(changes)} detection(s) will get new ID {new_id}:")
        for fi, di in changes:
            self._list.addItem(f"  Frame {fi}  ·  det {di}")

    def _on_accept(self):
        self.result_split_frame = self._spin_frame.value()
        self.result_new_id      = self._spin_new.value()
        self.accept()
