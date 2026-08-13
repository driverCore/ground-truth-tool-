"""Controls bar — playback buttons, speed selector, frame jump, and range window controls."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QSpinBox, QFrame, QSizePolicy,
)

from controllers.playback_ctrl import SPEED_OPTIONS
from utils.colors import ACCENT, BG_SURFACE, BORDER, TEXT_SEC


class ControlsBar(QWidget):
    """Bottom playback controls bar.

    Emits:
        play_pause_toggled()
        step_backward_requested()
        step_forward_requested()
        first_frame_requested()
        last_frame_requested()
        speed_changed(float)
        jump_to_frame_requested(frame_1based: int)
        prev_switch_requested()
        next_switch_requested()
        range_bounds_changed(start_1based: int, end_1based: int)
        range_reset_requested()
    """

    play_pause_toggled       = Signal()
    step_backward_requested  = Signal()
    step_forward_requested   = Signal()
    first_frame_requested    = Signal()
    last_frame_requested     = Signal()
    speed_changed            = Signal(float)
    jump_to_frame_requested  = Signal(int)     # 1-based frame number from user
    prev_switch_requested    = Signal()
    next_switch_requested    = Signal()
    range_bounds_changed     = Signal(int, int) # 1-based start, end
    range_reset_requested    = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._frame_count = 1
        self._build_ui()

    def _build_ui(self):
        self.setMaximumHeight(50)
        root = QHBoxLayout(self)
        root.setContentsMargins(8, 4, 8, 4)
        root.setSpacing(4)

        def sep():
            f = QFrame(); f.setFrameShape(QFrame.VLine)
            return f

        # ── Navigation ────────────────────────────────────────────────────
        self._btn_first = QPushButton("|◀")
        self._btn_first.setToolTip("First frame")
        self._btn_first.setFixedWidth(36)
        self._btn_prev  = QPushButton("◀")
        self._btn_prev.setToolTip("Previous frame  (← key)")
        self._btn_prev.setFixedWidth(36)
        self._btn_play  = QPushButton("▶")
        self._btn_play.setToolTip("Play / Pause  (Space key)")
        self._btn_play.setObjectName("btn_primary")
        self._btn_play.setFixedWidth(50)
        self._btn_next  = QPushButton("▶")
        self._btn_next.setToolTip("Next frame  (→ key)")
        self._btn_next.setFixedWidth(36)
        self._btn_last  = QPushButton("▶|")
        self._btn_last.setToolTip("Last frame")
        self._btn_last.setFixedWidth(36)

        for btn in (self._btn_first, self._btn_prev, self._btn_play,
                    self._btn_next, self._btn_last):
            root.addWidget(btn)

        root.addWidget(sep())

        # ── Speed ─────────────────────────────────────────────────────────
        root.addWidget(QLabel("Speed:"))
        self._combo_speed = QComboBox()
        self._combo_speed.setFixedWidth(72)
        for label, _ in SPEED_OPTIONS:
            self._combo_speed.addItem(label)
        self._combo_speed.setCurrentIndex(2)   # 1× default
        root.addWidget(self._combo_speed)

        root.addWidget(sep())

        # ── Frame jump ────────────────────────────────────────────────────
        root.addWidget(QLabel("Frame:"))
        self._spin_frame = QSpinBox()
        self._spin_frame.setRange(1, 99999)
        self._spin_frame.setFixedWidth(70)
        self._spin_frame.setToolTip("Jump to frame (press Enter)")
        root.addWidget(self._spin_frame)

        self._btn_go = QPushButton("Go")
        self._btn_go.setFixedWidth(32)
        root.addWidget(self._btn_go)

        root.addWidget(sep())

        # ── Range Window Trimming ──────────────────────────────────────────
        root.addWidget(QLabel("Window:"))
        self._spin_start_frame = QSpinBox()
        self._spin_start_frame.setRange(1, 99999)
        self._spin_start_frame.setFixedWidth(70)
        self._spin_start_frame.setToolTip("Active start frame (skip frames before this)")
        root.addWidget(self._spin_start_frame)

        root.addWidget(QLabel("-"))
        self._spin_end_frame = QSpinBox()
        self._spin_end_frame.setRange(1, 99999)
        self._spin_end_frame.setFixedWidth(70)
        self._spin_end_frame.setToolTip("Active end frame (skip frames after this)")
        root.addWidget(self._spin_end_frame)

        self._btn_reset_range = QPushButton("Reset")
        self._btn_reset_range.setFixedWidth(48)
        self._btn_reset_range.setToolTip("Reset active window to full sequence")
        root.addWidget(self._btn_reset_range)

        root.addWidget(sep())

        # ── Switch navigation ─────────────────────────────────────────────
        self._btn_prev_sw = QPushButton("[ Prev Sw")
        self._btn_prev_sw.setToolTip("Jump to previous ID switch frame")
        root.addWidget(self._btn_prev_sw)

        self._btn_next_sw = QPushButton("Next Sw ]")
        self._btn_next_sw.setToolTip("Jump to next ID switch frame")
        root.addWidget(self._btn_next_sw)

        root.addStretch()

        # ── Frame display ─────────────────────────────────────────────────
        self._lbl_position = QLabel("Frame 0 / 0")
        self._lbl_position.setObjectName("label_secondary")
        self._lbl_position.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._lbl_position.setFixedWidth(110)
        root.addWidget(self._lbl_position)

        # ── Connections ───────────────────────────────────────────────────
        self._btn_first.clicked.connect(self.first_frame_requested)
        self._btn_prev.clicked.connect(self.step_backward_requested)
        self._btn_play.clicked.connect(self._on_play_pause)
        self._btn_next.clicked.connect(self.step_forward_requested)
        self._btn_last.clicked.connect(self.last_frame_requested)
        self._combo_speed.currentIndexChanged.connect(self._on_speed_changed)
        self._btn_go.clicked.connect(self._on_go)
        self._spin_frame.editingFinished.connect(self._on_go)
        self._btn_prev_sw.clicked.connect(self.prev_switch_requested)
        self._btn_next_sw.clicked.connect(self.next_switch_requested)

        self._spin_start_frame.editingFinished.connect(self._on_range_spin_changed)
        self._spin_end_frame.editingFinished.connect(self._on_range_spin_changed)
        self._btn_reset_range.clicked.connect(self.range_reset_requested)

    # ── Public API ────────────────────────────────────────────────────────

    def setup(self, frame_count: int):
        self._frame_count = frame_count
        self._spin_frame.setRange(1, frame_count)
        self._spin_start_frame.setRange(1, frame_count)
        self._spin_end_frame.setRange(1, frame_count)

        self._spin_start_frame.blockSignals(True)
        self._spin_start_frame.setValue(1)
        self._spin_start_frame.blockSignals(False)

        self._spin_end_frame.blockSignals(True)
        self._spin_end_frame.setValue(frame_count)
        self._spin_end_frame.blockSignals(False)

        self._lbl_position.setText(f"Frame 1 / {frame_count}")

    def set_range_bounds(self, start_1based: int, end_1based: int):
        self._spin_start_frame.blockSignals(True)
        self._spin_end_frame.blockSignals(True)
        self._spin_start_frame.setValue(start_1based)
        self._spin_end_frame.setValue(end_1based)
        self._spin_start_frame.blockSignals(False)
        self._spin_end_frame.blockSignals(False)

    def set_playing(self, playing: bool):
        self._btn_play.setText("⏸" if playing else "▶")
        self._btn_play.setToolTip("Pause (Space)" if playing else "Play (Space)")

    def set_current_position(self, pos: int, frame_idx: int):
        """pos = 0-based list position, frame_idx = actual 0-based frame index."""
        self._spin_frame.blockSignals(True)
        self._spin_frame.setValue(frame_idx + 1)
        self._spin_frame.blockSignals(False)
        self._lbl_position.setText(f"Frame {frame_idx + 1} / {self._frame_count}")

    # ── Slots ─────────────────────────────────────────────────────────────

    def _on_play_pause(self):
        self.play_pause_toggled.emit()

    def _on_speed_changed(self, idx: int):
        _, speed = SPEED_OPTIONS[idx]
        self.speed_changed.emit(speed)

    def _on_go(self):
        self.jump_to_frame_requested.emit(self._spin_frame.value())

    def _on_range_spin_changed(self):
        s = self._spin_start_frame.value()
        e = self._spin_end_frame.value()
        if s > e:
            s = e
            self._spin_start_frame.setValue(s)
        self.range_bounds_changed.emit(s, e)
