"""Interactive Timeline widget — shows all frames as a horizontal bar with coloured markers."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QRect, QPoint, QSize
from PySide6.QtGui import QColor, QPainter, QPen, QBrush, QFont, QFontMetrics, QMouseEvent
from PySide6.QtWidgets import QWidget, QSizePolicy, QToolTip

from utils.colors import TIMELINE_COLORS, BG_SURFACE, BG_WIDGET, BORDER, ACCENT, TEXT_SEC


class TimelineWidget(QWidget):
    """Horizontal timeline bar.

    Emits:
        seek_requested(position: int) — 0-based position in frame list
    """

    seek_requested = Signal(int)

    BAR_HEIGHT    = 18
    MARKER_HEIGHT = 12
    TICK_HEIGHT   = 6
    TOTAL_HEIGHT  = 54

    def __init__(self, parent=None):
        super().__init__(parent)
        self._frame_count    = 0
        self._current_pos    = 0          # 0-based list position
        self._switch_frames:  set[int]   = set()   # frame_idx values
        self._edited_frames:  set[int]   = set()
        self._verified_frames: set[int]  = set()
        self._frame_idx_list: list[int]  = []       # ordered frame_idx values

        self.setMinimumHeight(self.TOTAL_HEIGHT)
        self.setMaximumHeight(self.TOTAL_HEIGHT)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMouseTracking(True)

        self._hover_pos: int = -1
        self._font = QFont("Segoe UI", 8)

    # ── Public API ────────────────────────────────────────────────────────

    def setup(self, frame_idx_list: list[int]):
        self._frame_idx_list = list(frame_idx_list)
        self._frame_count    = len(frame_idx_list)
        self.update()

    def set_current_position(self, pos: int):
        self._current_pos = pos
        self.update()

    def update_markers(self,
                       switch_frames:   set[int],
                       edited_frames:   set[int],
                       verified_frames: set[int]):
        self._switch_frames   = switch_frames
        self._edited_frames   = edited_frames
        self._verified_frames = verified_frames
        self.update()

    # ── Painting ──────────────────────────────────────────────────────────

    def paintEvent(self, _):
        if self._frame_count == 0:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        W, H = self.width(), self.height()

        # Background
        painter.fillRect(0, 0, W, H, QColor(BG_SURFACE))

        # Track bar background
        bar_y = 16
        painter.fillRect(0, bar_y, W, self.BAR_HEIGHT, QColor(BG_WIDGET))

        # Markers
        for pos, fidx in enumerate(self._frame_idx_list):
            x = self._pos_to_x(pos)
            self._draw_marker(painter, x, bar_y, fidx)

        # Current position indicator (white line + triangle)
        cx = self._pos_to_x(self._current_pos)
        painter.setPen(QPen(QColor("white"), 2))
        painter.drawLine(cx, bar_y - 4, cx, bar_y + self.BAR_HEIGHT + 4)

        # Triangle above bar
        tri_x, tri_y = cx, bar_y - 4
        from PySide6.QtGui import QPolygon
        tri = QPolygon([
            QPoint(tri_x - 5, tri_y - 8),
            QPoint(tri_x + 5, tri_y - 8),
            QPoint(tri_x,     tri_y),
        ])
        painter.setBrush(QBrush(QColor("white")))
        painter.setPen(Qt.NoPen)
        painter.drawPolygon(tri)

        # Hover indicator
        if 0 <= self._hover_pos < self._frame_count:
            hx = self._pos_to_x(self._hover_pos)
            painter.setPen(QPen(QColor(255, 255, 255, 80), 1))
            painter.drawLine(hx, bar_y, hx, bar_y + self.BAR_HEIGHT)

        # Labels: first, current, last frame numbers
        painter.setFont(self._font)
        painter.setPen(QColor(TEXT_SEC))
        if self._frame_idx_list:
            fm = QFontMetrics(self._font)
            first_label = str(self._frame_idx_list[0] + 1)
            last_label  = str(self._frame_idx_list[-1] + 1)
            curr_label  = str(self._frame_idx_list[self._current_pos] + 1)
            painter.drawText(2, H - 2, first_label)
            tw = fm.horizontalAdvance(last_label)
            painter.drawText(W - tw - 2, H - 2, last_label)
            tw2 = fm.horizontalAdvance(curr_label)
            painter.setPen(QColor("white"))
            painter.drawText(max(0, cx - tw2 // 2), H - 2, curr_label)

    def _draw_marker(self, painter: QPainter, x: int, bar_y: int, fidx: int):
        # Priority: switch > edited > verified
        if fidx in self._switch_frames:
            color = TIMELINE_COLORS["switch"]
        elif fidx in self._edited_frames:
            color = TIMELINE_COLORS["edited"]
        elif fidx in self._verified_frames:
            color = TIMELINE_COLORS["verified"]
        else:
            return   # unreviewed — no marker

        w = max(2, self.width() // max(1, self._frame_count) - 1)
        painter.fillRect(x - w // 2, bar_y + 2,
                         max(2, w), self.BAR_HEIGHT - 4, color)

    # ── Mouse ─────────────────────────────────────────────────────────────

    def mousePressEvent(self, e: QMouseEvent):
        if e.button() == Qt.LeftButton:
            pos = self._x_to_pos(e.pos().x())
            if 0 <= pos < self._frame_count:
                self.seek_requested.emit(pos)

    def mouseMoveEvent(self, e: QMouseEvent):
        pos = self._x_to_pos(e.pos().x())
        if pos != self._hover_pos:
            self._hover_pos = pos
            self.update()
        # Tooltip
        if 0 <= pos < self._frame_count:
            fidx = self._frame_idx_list[pos]
            tags: list[str] = []
            if fidx in self._switch_frames:
                tags.append("ID switch")
            if fidx in self._edited_frames:
                tags.append("edited")
            if fidx in self._verified_frames:
                tags.append("verified")
            tip = f"Frame {fidx + 1}"
            if tags:
                tip += f"  [{', '.join(tags)}]"
            QToolTip.showText(e.globalPos(), tip, self)

    def leaveEvent(self, _):
        self._hover_pos = -1
        self.update()

    # ── Helpers ───────────────────────────────────────────────────────────

    def _pos_to_x(self, pos: int) -> int:
        if self._frame_count <= 1:
            return self.width() // 2
        return int(pos / (self._frame_count - 1) * (self.width() - 1))

    def _x_to_pos(self, x: int) -> int:
        if self._frame_count <= 1:
            return 0
        return round(x / max(1, self.width() - 1) * (self._frame_count - 1))
