"""Playback controller — QTimer-driven frame advancement."""
from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Signal

SPEED_OPTIONS: list[tuple[str, float]] = [
    ("0.25×", 0.25),
    ("0.5×",  0.50),
    ("1×",    1.00),
    ("2×",    2.00),
    ("4×",    4.00),
]
BASE_FPS = 25.0   # assumed frame rate of source video


class PlaybackController(QObject):
    """Drives frame-by-frame playback via a QTimer.

    Signals:
        frame_requested(int): emitted every tick with the next frame index to display.
    """

    frame_requested = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._timer      = QTimer(self)
        self._timer.timeout.connect(self._on_tick)
        self._speed      = 1.0
        self._frame_idx  = 0
        self._max_idx    = 0
        self._playing    = False

    # ── Public API ────────────────────────────────────────────────────────

    def setup(self, frame_count: int, start_frame: int = 0):
        self._max_idx   = max(0, frame_count - 1)
        self._frame_idx = max(0, min(start_frame, self._max_idx))

    def set_speed(self, speed: float):
        self._speed = max(0.1, speed)
        if self._playing:
            self._restart_timer()

    def play(self):
        if not self._playing:
            self._playing = True
            self._restart_timer()

    def pause(self):
        self._playing = False
        self._timer.stop()

    def toggle_play_pause(self):
        if self._playing:
            self.pause()
        else:
            self.play()

    def is_playing(self) -> bool:
        return self._playing

    def seek(self, frame_position: int):
        """Seek to a frame by its 0-based list position."""
        was_playing = self._playing
        self.pause()
        self._frame_idx = max(0, min(frame_position, self._max_idx))
        self.frame_requested.emit(self._frame_idx)
        if was_playing:
            self.play()

    def step_forward(self):
        self.pause()
        if self._frame_idx < self._max_idx:
            self._frame_idx += 1
        self.frame_requested.emit(self._frame_idx)

    def step_backward(self):
        self.pause()
        if self._frame_idx > 0:
            self._frame_idx -= 1
        self.frame_requested.emit(self._frame_idx)

    def go_first(self):
        self.pause()
        self._frame_idx = 0
        self.frame_requested.emit(self._frame_idx)

    def go_last(self):
        self.pause()
        self._frame_idx = self._max_idx
        self.frame_requested.emit(self._frame_idx)

    @property
    def current_position(self) -> int:
        return self._frame_idx

    # ── Internal ──────────────────────────────────────────────────────────

    def _restart_timer(self):
        interval_ms = max(1, int(1000.0 / (BASE_FPS * self._speed)))
        self._timer.start(interval_ms)

    def _on_tick(self):
        if self._frame_idx >= self._max_idx:
            self.pause()
            return
        self._frame_idx += 1
        self.frame_requested.emit(self._frame_idx)
