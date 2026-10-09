"""Interactive Timeline widget — shows all frames as a horizontal bar with coloured markers and dual-handle sliding window range selection."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QRect, QPoint, QSize
from PySide6.QtGui import QColor, QPainter, QPen, QBrush, QFont, QFontMetrics, QMouseEvent, QPolygon
from PySide6.QtWidgets import QWidget, QSizePolicy, QToolTip

from utils.colors import (
    get_theme_colors, get_timeline_colors,
    TIMELINE_COLORS, BG_SURFACE, BG_WIDGET, BORDER, ACCENT, TEXT_SEC,
)


class TimelineWidget(QWidget):
    """Horizontal timeline bar with dual-handle sliding window range selection.

    Emits:
        seek_requested(position: int) — 0-based position in frame list
        range_changed(start_pos: int, end_pos: int) — active sliding window bounds (0-based positions)
    """

    seek_requested = Signal(int)
    range_changed  = Signal(int, int)

    BAR_HEIGHT    = 18
    MARKER_HEIGHT = 12
    TICK_HEIGHT   = 6
    TOTAL_HEIGHT  = 54
    HANDLE_HIT_PX = 8

    def __init__(self, parent=None):
        super().__init__(parent)
        self._theme          = "dark"
        self._frame_count    = 0
        self._current_pos    = 0          # 0-based list position
        self._start_pos      = 0          # sliding window start position
        self._end_pos        = 0          # sliding window end position
        self._dragging_handle: str | None = None  # 'start' | 'end' | None
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

    def set_theme(self, theme: str):
        self._theme = theme
        self.update()

    def setup(self, frame_idx_list: list[int]):
        self._frame_idx_list = list(frame_idx_list)
        self._frame_count    = len(frame_idx_list)
        self._start_pos      = 0
        self._end_pos        = max(0, self._frame_count - 1)
        self.update()

    def set_current_position(self, pos: int):
        self._current_pos = pos
        self.update()

    def set_range(self, start_pos: int, end_pos: int):
        if self._frame_count == 0:
            return
        sp = max(0, min(start_pos, self._frame_count - 1))
        ep = max(sp, min(end_pos, self._frame_count - 1))
        if sp != self._start_pos or ep != self._end_pos:
            self._start_pos = sp
            self._end_pos   = ep
            self.update()

    def get_range(self) -> tuple[int, int]:
        return (self._start_pos, self._end_pos)

    def reset_range(self):
        if self._frame_count > 0:
            self.set_range(0, self._frame_count - 1)
            self.range_changed.emit(self._start_pos, self._end_pos)

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
        colors = get_theme_colors(self._theme)

        # Background
        painter.fillRect(0, 0, W, H, QColor(colors["BG_SURFACE"]))

        # Track bar background
        bar_y = 16
        painter.fillRect(0, bar_y, W, self.BAR_HEIGHT, QColor(colors["BG_WIDGET"]))

        # Active sliding window highlight
        start_x = self._pos_to_x(self._start_pos)
        end_x   = self._pos_to_x(self._end_pos)
        if start_x <= end_x:
            win_color = QColor(49, 130, 206, 45) if self._theme == "dark" else QColor(9, 105, 218, 35)
            painter.fillRect(start_x, bar_y, max(1, end_x - start_x + 1), self.BAR_HEIGHT, win_color)

        # Markers inside window
        for pos, fidx in enumerate(self._frame_idx_list):
            x = self._pos_to_x(pos)
            is_active = (self._start_pos <= pos <= self._end_pos)
            self._draw_marker(painter, x, bar_y, fidx, active=is_active)

        # Dimmed overlays outside sliding window
        dim_color = QColor(0, 0, 0, 160) if self._theme == "dark" else QColor(220, 225, 232, 175)
        if start_x > 0:
            painter.fillRect(0, bar_y, start_x, self.BAR_HEIGHT, dim_color)
        if end_x < W - 1:
            painter.fillRect(end_x + 1, bar_y, W - end_x - 1, self.BAR_HEIGHT, dim_color)

        # Range Handles: Start handle (Green) and End handle (Red)
        # Left Start Handle [
        painter.setPen(QPen(QColor("#38a169"), 3))
        painter.drawLine(start_x, bar_y - 2, start_x, bar_y + self.BAR_HEIGHT + 2)
        tri_start = QPolygon([
            QPoint(start_x,     bar_y - 6),
            QPoint(start_x - 6, bar_y - 12),
            QPoint(start_x + 6, bar_y - 12),
        ])
        painter.setBrush(QBrush(QColor("#38a169")))
        painter.setPen(Qt.NoPen)
        painter.drawPolygon(tri_start)

        # Right End Handle ]
        painter.setPen(QPen(QColor("#e53e3e"), 3))
        painter.drawLine(end_x, bar_y - 2, end_x, bar_y + self.BAR_HEIGHT + 2)
        tri_end = QPolygon([
            QPoint(end_x,     bar_y - 6),
            QPoint(end_x - 6, bar_y - 12),
            QPoint(end_x + 6, bar_y - 12),
        ])
        painter.setBrush(QBrush(QColor("#e53e3e")))
        painter.setPen(Qt.NoPen)
        painter.drawPolygon(tri_end)

        # Handle Labels (S / E) above bar
        painter.setFont(self._font)
        painter.setPen(QColor("#38a169"))
        painter.drawText(max(0, start_x - 4), bar_y - 14, "S")
        painter.setPen(QColor("#e53e3e"))
        painter.drawText(min(W - 10, end_x - 4), bar_y - 14, "E")

        # Current position indicator
        curr_line_c = QColor("white") if self._theme == "dark" else QColor("#0969da")
        cx = self._pos_to_x(self._current_pos)
        painter.setPen(QPen(curr_line_c, 2))
        painter.drawLine(cx, bar_y - 4, cx, bar_y + self.BAR_HEIGHT + 4)

        # Triangle above bar for current position
        tri_x, tri_y = cx, bar_y - 4
        tri_curr = QPolygon([
            QPoint(tri_x - 5, tri_y - 8),
            QPoint(tri_x + 5, tri_y - 8),
            QPoint(tri_x,     tri_y),
        ])
        painter.setBrush(QBrush(curr_line_c))
        painter.setPen(Qt.NoPen)
        painter.drawPolygon(tri_curr)

        # Hover indicator
        if 0 <= self._hover_pos < self._frame_count:
            hx = self._pos_to_x(self._hover_pos)
            hover_c = QColor(255, 255, 255, 80) if self._theme == "dark" else QColor(0, 0, 0, 70)
            painter.setPen(QPen(hover_c, 1))
            painter.drawLine(hx, bar_y, hx, bar_y + self.BAR_HEIGHT)

        # Labels: first, current, last frame numbers
        painter.setFont(self._font)
        painter.setPen(QColor(colors["TEXT_SEC"]))
        if self._frame_idx_list:
            fm = QFontMetrics(self._font)
            first_label = str(self._frame_idx_list[0] + 1)
            last_label  = str(self._frame_idx_list[-1] + 1)
            curr_label  = f"{self._frame_idx_list[self._current_pos] + 1}  [Range: {self._frame_idx_list[self._start_pos] + 1} - {self._frame_idx_list[self._end_pos] + 1}]"
            painter.drawText(2, H - 2, first_label)
            tw = fm.horizontalAdvance(last_label)
            painter.drawText(W - tw - 2, H - 2, last_label)
            tw2 = fm.horizontalAdvance(curr_label)
            painter.setPen(QColor("white") if self._theme == "dark" else QColor(colors["TEXT_PRI"]))
            painter.drawText(max(0, cx - tw2 // 2), H - 2, curr_label)

    def _draw_marker(self, painter: QPainter, x: int, bar_y: int, fidx: int, active: bool = True):
        # Priority: switch > edited > verified
        tl_colors = get_timeline_colors(self._theme)
        if fidx in self._switch_frames:
            color = tl_colors["switch"]
        elif fidx in self._edited_frames:
            color = tl_colors["edited"]
        elif fidx in self._verified_frames:
            color = tl_colors["verified"]
        else:
            return   # unreviewed — no marker

        if not active:
            color = QColor(color)
            color.setAlpha(60)

        w = max(2, self.width() // max(1, self._frame_count) - 1)
        painter.fillRect(x - w // 2, bar_y + 2,
                         max(2, w), self.BAR_HEIGHT - 4, color)

    # ── Mouse ─────────────────────────────────────────────────────────────

    def mousePressEvent(self, e: QMouseEvent):
        if e.button() == Qt.LeftButton:
            x = e.pos().x()
            sx = self._pos_to_x(self._start_pos)
            ex = self._pos_to_x(self._end_pos)

            if abs(x - sx) <= self.HANDLE_HIT_PX:
                self._dragging_handle = 'start'
            elif abs(x - ex) <= self.HANDLE_HIT_PX:
                self._dragging_handle = 'end'
            else:
                self._dragging_handle = None
                pos = self._x_to_pos(x)
                if 0 <= pos < self._frame_count:
                    self.seek_requested.emit(pos)

    def mouseMoveEvent(self, e: QMouseEvent):
        x = e.pos().x()

        if self._dragging_handle == 'start':
            new_pos = max(0, min(self._x_to_pos(x), self._end_pos))
            if new_pos != self._start_pos:
                self._start_pos = new_pos
                self.range_changed.emit(self._start_pos, self._end_pos)
                self.update()
        elif self._dragging_handle == 'end':
            new_pos = max(self._start_pos, min(self._x_to_pos(x), self._frame_count - 1))
            if new_pos != self._end_pos:
                self._end_pos = new_pos
                self.range_changed.emit(self._start_pos, self._end_pos)
                self.update()
        else:
            # Hover cursor feedback for handles
            sx = self._pos_to_x(self._start_pos)
            ex = self._pos_to_x(self._end_pos)
            if abs(x - sx) <= self.HANDLE_HIT_PX or abs(x - ex) <= self.HANDLE_HIT_PX:
                self.setCursor(Qt.SizeHorCursor)
            else:
                self.setCursor(Qt.PointingHandCursor)

            pos = self._x_to_pos(x)
            if pos != self._hover_pos:
                self._hover_pos = pos
                self.update()

            # Tooltip
            if 0 <= pos < self._frame_count:
                fidx = self._frame_idx_list[pos]
                tags: list[str] = []
                if pos < self._start_pos:
                    tags.append("skipped (before start)")
                elif pos > self._end_pos:
                    tags.append("skipped (after end)")
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

    def mouseReleaseEvent(self, e: QMouseEvent):
        if self._dragging_handle:
            self._dragging_handle = None
            self.setCursor(Qt.PointingHandCursor)

    def leaveEvent(self, _):
        self._hover_pos = -1
        self._dragging_handle = None
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
