"""TrimDialog — Video-editor-style frame trimmer.

Shows two live frame previews (start / end boundary) side-by-side,
with a draggable filmstrip bar below.  Drag the left bracket to set the
in-point; drag the right bracket to set the out-point.  The trimmed
regions are dimmed automatically.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import Qt, Signal, QTimer, QRect, QPoint, QRectF
from PySide6.QtGui import (
    QColor, QFont, QFontMetrics, QPainter, QPen, QBrush,
    QLinearGradient, QPixmap, QPainterPath, QCursor,
)
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QCheckBox, QSizePolicy, QDialogButtonBox, QFrame, QWidget,
)


# ──────────────────────────────────────────────────────────────────────────────
#  Colour constants
# ──────────────────────────────────────────────────────────────────────────────
_C_BG          = QColor("#0d1117")
_C_STRIP_FULL  = QColor("#21262d")
_C_STRIP_KEEP  = QColor("#1f6feb")       # active "keep" region
_C_HANDLE      = QColor("#f0883e")       # bracket handle colour
_C_HANDLE_HOV  = QColor("#ffa657")
_C_OVERLAY     = QColor(0, 0, 0, 155)   # dimming on trimmed regions
_C_TEXT        = QColor("#e6edf3")
_C_TEXT_SEC    = QColor("#8b949e")
_C_WARN        = QColor("#d29922")
_C_BORDER      = QColor("#30363d")
_C_KEEP_TINT   = QColor(31, 111, 235, 40)   # faint blue fill in keep zone


# ──────────────────────────────────────────────────────────────────────────────
#  TrimTimeline  — the filmstrip widget with draggable in/out handles
# ──────────────────────────────────────────────────────────────────────────────

class TrimTimeline(QWidget):
    """Horizontal filmstrip bar with two draggable bracket handles.

    Signals
    -------
    start_changed(int):  new 0-based start position
    end_changed(int):    new 0-based end position
    """

    start_changed = Signal(int)
    end_changed   = Signal(int)

    _HANDLE_W  = 14    # px width of each bracket handle
    _TRACK_H   = 52    # px height of the coloured strip
    _LABEL_H   = 20    # px height of the frame-number label above strip

    def __init__(self, total_frames: int, parent=None):
        super().__init__(parent)
        self._total    = total_frames
        self._start    = 0                      # 0-based
        self._end      = max(0, total_frames - 1)
        self._drag     : Optional[str] = None   # "start" | "end"
        self._hovered  : Optional[str] = None

        h = self._TRACK_H + self._LABEL_H + 24  # top labels + strip + bottom labels
        self.setMinimumSize(400, h)
        self.setFixedHeight(h)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMouseTracking(True)

        self._font_sm = QFont("Segoe UI", 8)
        self._font_md = QFont("Segoe UI", 9, QFont.Bold)

    # ── Public API ────────────────────────────────────────────────────────

    def set_start(self, pos: int):
        self._start = max(0, min(pos, self._end))
        self.update()

    def set_end(self, pos: int):
        self._end = max(self._start, min(pos, self._total - 1))
        self.update()

    @property
    def start(self) -> int:
        return self._start

    @property
    def end(self) -> int:
        return self._end

    # ── Coordinate helpers ────────────────────────────────────────────────

    def _strip_rect(self) -> QRect:
        """The rectangle of the coloured filmstrip (excluding handle knobs)."""
        lh = self._LABEL_H
        pw = self._HANDLE_W
        return QRect(pw, lh, self.width() - 2 * pw, self._TRACK_H)

    def _pos_to_x(self, pos: int) -> int:
        sr = self._strip_rect()
        if self._total <= 1:
            return sr.left()
        return sr.left() + int(pos / (self._total - 1) * sr.width())

    def _x_to_pos(self, x: int) -> int:
        sr = self._strip_rect()
        if sr.width() <= 0:
            return 0
        t = max(0.0, min(1.0, (x - sr.left()) / sr.width()))
        return round(t * (self._total - 1))

    def _handle_rect(self, which: str) -> QRect:
        hw = self._HANDLE_W
        lh = self._LABEL_H
        pos = self._start if which == "start" else self._end
        cx  = self._pos_to_x(pos)
        return QRect(cx - hw // 2, lh, hw, self._TRACK_H)

    def _hit_handle(self, x: int, y: int) -> Optional[str]:
        for which in ("start", "end"):
            r = self._handle_rect(which)
            r.adjust(-6, -2, 6, 2)
            if r.contains(x, y):
                return which
        return None

    # ── Paint ─────────────────────────────────────────────────────────────

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        sr    = self._strip_rect()
        lh    = self._LABEL_H
        sx0   = self._pos_to_x(self._start)
        sx1   = self._pos_to_x(self._end)

        # ── Full strip background ─────────────────────────────────────────
        p.fillRect(sr, _C_STRIP_FULL)

        # ── Keep-zone tint ───────────────────────────────────────────────
        keep_r = QRect(sx0, sr.top(), sx1 - sx0, sr.height())
        p.fillRect(keep_r, _C_STRIP_KEEP)
        p.fillRect(keep_r, _C_KEEP_TINT)

        # Subtle frame tick marks
        p.setPen(QPen(QColor(255, 255, 255, 18), 1))
        if self._total > 1:
            step = max(1, self._total // 80)
            for i in range(0, self._total, step):
                tx = self._pos_to_x(i)
                p.drawLine(tx, sr.top() + 4, tx, sr.bottom() - 4)

        # ── Dimmed regions (trimmed) ─────────────────────────────────────
        left_trim  = QRect(sr.left(), sr.top(), max(0, sx0 - sr.left()), sr.height())
        right_trim = QRect(sx1, sr.top(), sr.right() - sx1, sr.height())
        p.fillRect(left_trim,  _C_OVERLAY)
        p.fillRect(right_trim, _C_OVERLAY)

        # Diagonal hatch on trimmed areas
        p.setPen(QPen(QColor(255, 255, 255, 12), 1))
        for region in (left_trim, right_trim):
            if region.width() > 0:
                step = 12
                for off in range(-region.height(), region.width(), step):
                    x1 = region.left() + off
                    x2 = x1 + region.height()
                    p.drawLine(
                        max(region.left(), x1), region.top(),
                        min(region.right(), x2), region.bottom()
                    )

        # ── Strip border ─────────────────────────────────────────────────
        p.setPen(QPen(_C_BORDER, 1))
        p.setBrush(Qt.NoBrush)
        p.drawRect(sr)

        # ── Frame number labels above the handles ─────────────────────────
        p.setFont(self._font_sm)
        fm = QFontMetrics(self._font_sm)

        for which, pos, align in (
            ("start", self._start, Qt.AlignLeft),
            ("end",   self._end,   Qt.AlignRight),
        ):
            cx = self._pos_to_x(pos)
            label = f"Frame {pos + 1}"
            tw = fm.horizontalAdvance(label)
            # keep label inside widget
            lx = max(0, min(self.width() - tw, cx - tw // 2))
            p.setPen(_C_TEXT_SEC)
            p.drawText(lx, 0, tw, lh - 2, Qt.AlignBottom | Qt.AlignLeft, label)

        # ── Handles (bracket shapes) ──────────────────────────────────────
        self._draw_handle(p, "start")
        self._draw_handle(p, "end")

        # ── Bottom summary ────────────────────────────────────────────────
        keep  = self._end - self._start + 1
        tl    = self._start
        tr    = (self._total - 1) - self._end
        by    = sr.bottom() + 6
        bh    = self.height() - by

        p.setFont(self._font_md)
        summary = (
            f"Keep {keep} frame{'s' if keep != 1 else ''}  "
            f"({'−' + str(tl) if tl else ''}{'  ' if tl and tr else ''}"
            f"{'−' + str(tr) if tr else ''})"
        )
        if tl == 0 and tr == 0:
            summary = f"All {self._total} frames kept — no trim"
        p.setPen(_C_TEXT_SEC)
        p.drawText(0, by, self.width(), bh, Qt.AlignCenter, summary)

    def _draw_handle(self, p: QPainter, which: str):
        hw   = self._HANDLE_W
        lh   = self._LABEL_H
        pos  = self._start if which == "start" else self._end
        cx   = self._pos_to_x(pos)
        sr   = self._strip_rect()
        hov  = (self._hovered == which or self._drag == which)
        col  = _C_HANDLE_HOV if hov else _C_HANDLE

        # Vertical bar
        bar_rect = QRectF(cx - 2, sr.top(), 4, sr.height())
        p.fillRect(bar_rect, col)

        # Top cap (triangle pointing inward)
        cap_h = 10
        path = QPainterPath()
        if which == "start":
            path.moveTo(cx - hw // 2, sr.top())
            path.lineTo(cx + hw // 2, sr.top())
            path.lineTo(cx + hw // 2, sr.top() + cap_h)
            path.lineTo(cx,           sr.top() + cap_h * 2)
            path.lineTo(cx - hw // 2, sr.top() + cap_h)
            path.closeSubpath()
        else:
            path.moveTo(cx + hw // 2, sr.top())
            path.lineTo(cx - hw // 2, sr.top())
            path.lineTo(cx - hw // 2, sr.top() + cap_h)
            path.lineTo(cx,           sr.top() + cap_h * 2)
            path.lineTo(cx + hw // 2, sr.top() + cap_h)
            path.closeSubpath()

        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(col))
        p.drawPath(path)

        # Bottom cap
        path2 = QPainterPath()
        if which == "start":
            path2.moveTo(cx - hw // 2, sr.bottom())
            path2.lineTo(cx + hw // 2, sr.bottom())
            path2.lineTo(cx + hw // 2, sr.bottom() - cap_h)
            path2.lineTo(cx,           sr.bottom() - cap_h * 2)
            path2.lineTo(cx - hw // 2, sr.bottom() - cap_h)
            path2.closeSubpath()
        else:
            path2.moveTo(cx + hw // 2, sr.bottom())
            path2.lineTo(cx - hw // 2, sr.bottom())
            path2.lineTo(cx - hw // 2, sr.bottom() - cap_h)
            path2.lineTo(cx,           sr.bottom() - cap_h * 2)
            path2.lineTo(cx + hw // 2, sr.bottom() - cap_h)
            path2.closeSubpath()
        p.drawPath(path2)

    # ── Mouse events ──────────────────────────────────────────────────────

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag = self._hit_handle(e.position().x(), e.position().y())
            if self._drag:
                self.setCursor(Qt.SizeHorCursor)
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        x   = int(e.position().x())
        y   = int(e.position().y())
        pos = self._x_to_pos(x)

        if self._drag == "start":
            new = max(0, min(pos, self._end))
            if new != self._start:
                self._start = new
                self.update()
                self.start_changed.emit(self._start)
        elif self._drag == "end":
            new = max(self._start, min(pos, self._total - 1))
            if new != self._end:
                self._end = new
                self.update()
                self.end_changed.emit(self._end)
        else:
            hit = self._hit_handle(x, y)
            if hit != self._hovered:
                self._hovered = hit
                self.update()
            self.setCursor(Qt.SizeHorCursor if hit else Qt.ArrowCursor)

        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self._drag:
            self._drag = None
            self.setCursor(Qt.ArrowCursor)
        super().mouseReleaseEvent(e)

    def leaveEvent(self, e):
        self._hovered = None
        self.update()
        super().leaveEvent(e)


# ──────────────────────────────────────────────────────────────────────────────
#  Preview panel
# ──────────────────────────────────────────────────────────────────────────────

class _PreviewPanel(QWidget):
    """Shows a frame thumbnail with an 'In' or 'Out' label and frame number."""

    def __init__(self, role: str, parent=None):
        super().__init__(parent)
        self._role  = role   # "In" or "Out"
        self._frame = -1
        self._pix   : Optional[QPixmap] = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        # Role badge
        badge_row = QHBoxLayout()
        self._badge = QLabel(role)
        self._badge.setAlignment(Qt.AlignCenter)
        badge_col = "#f0883e" if role == "In" else "#58a6ff"
        self._badge.setStyleSheet(
            f"background:{badge_col}; color:#0d1117; font-weight:700;"
            f" font-size:11px; padding:2px 10px; border-radius:4px;"
        )
        self._badge.setFixedWidth(44)
        badge_row.addWidget(self._badge)
        badge_row.addStretch()
        lay.addLayout(badge_row)

        # Thumbnail
        self._thumb = QLabel()
        self._thumb.setAlignment(Qt.AlignCenter)
        self._thumb.setFixedSize(280, 158)
        self._thumb.setStyleSheet(
            "background:#0d1117; border:2px solid " +
            (badge_col) + "; border-radius:6px; color:#484f58;"
        )
        self._thumb.setText("No preview")
        lay.addWidget(self._thumb)

        # Frame label
        self._lbl_frame = QLabel("")
        self._lbl_frame.setAlignment(Qt.AlignCenter)
        self._lbl_frame.setStyleSheet("font-size:11px; color:#8b949e;")
        lay.addWidget(self._lbl_frame)

    def update_preview(self, pos: int, pix: Optional[QPixmap]):
        self._frame = pos
        self._pix   = pix
        if pix and not pix.isNull():
            scaled = pix.scaled(280, 158, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self._thumb.setPixmap(scaled)
            self._thumb.setText("")
        else:
            self._thumb.clear()
            self._thumb.setText("No preview")
        self._lbl_frame.setText(f"Frame {pos + 1}")


# ──────────────────────────────────────────────────────────────────────────────
#  TrimDialog
# ──────────────────────────────────────────────────────────────────────────────

class TrimDialog(QDialog):
    """Video-editor-style trim dialog.

    Parameters
    ----------
    total_frames:
        Total number of frames currently loaded (0 means nothing to trim).
    get_thumbnail:
        Callable(position: int) -> Optional[QPixmap] — returns a thumbnail
        for the frame at the given 0-based position, or None if unavailable.
    parent:
        Parent widget.

    Results (read after exec() == QDialog.Accepted)
    -------
    result_start_pos : int   — 0-based inclusive start
    result_end_pos   : int   — 0-based inclusive end
    result_delete_images : bool
    """

    def __init__(
        self,
        total_frames: int,
        get_thumbnail: Callable[[int], Optional[QPixmap]],
        parent=None,
    ):
        super().__init__(parent)
        self._total     = total_frames
        self._get_thumb = get_thumbnail
        self._prev_start = -1   # track last previewed pos to avoid redundant loads
        self._prev_end   = -1

        # Results
        self.result_start_pos    : int  = 0
        self.result_end_pos      : int  = max(0, total_frames - 1)
        self.result_delete_images: bool = False

        self.setWindowTitle("Trim Frames")
        self.setMinimumWidth(680)
        self.setModal(True)
        self._apply_style()
        self._build_ui()

        # Load initial previews after the dialog is shown
        QTimer.singleShot(80, self._refresh_both_previews)

    def _apply_style(self):
        self.setStyleSheet("""
            QDialog { background: #0d1117; }
            QLabel  { color: #e6edf3; }
            QGroupBox {
                color: #8b949e; font-size: 11px;
                border: 1px solid #30363d; border-radius: 6px;
                margin-top: 8px; padding: 10px 6px 6px 6px;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
            QCheckBox { color: #f85149; }
            QCheckBox::indicator { width: 14px; height: 14px; }
            QPushButton {
                background: #21262d; color: #e6edf3;
                border: 1px solid #30363d; border-radius: 6px;
                padding: 6px 16px; font-size: 12px;
            }
            QPushButton:hover { background: #30363d; }
        """)

    # ── Build UI ──────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(14)
        root.setContentsMargins(20, 16, 20, 16)

        # ── Title ─────────────────────────────────────────────────────────
        title = QLabel("✂  Trim Frames")
        title.setStyleSheet("font-size:17px; font-weight:700; color:#e6edf3;")
        root.addWidget(title)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color:#30363d; margin-bottom:4px;")
        root.addWidget(sep)

        # ── Dual preview ─────────────────────────────────────────────────
        preview_row = QHBoxLayout()
        preview_row.setSpacing(20)
        self._panel_in  = _PreviewPanel("In",  self)
        self._panel_out = _PreviewPanel("Out", self)
        preview_row.addWidget(self._panel_in,  stretch=1)

        # Centre info column
        centre = QVBoxLayout()
        centre.setAlignment(Qt.AlignVCenter)
        centre.addStretch()
        self._lbl_keep = QLabel("")
        self._lbl_keep.setAlignment(Qt.AlignCenter)
        self._lbl_keep.setWordWrap(True)
        self._lbl_keep.setStyleSheet(
            "font-size:13px; color:#58a6ff; font-weight:700;"
        )
        centre.addWidget(self._lbl_keep)
        self._lbl_remove = QLabel("")
        self._lbl_remove.setAlignment(Qt.AlignCenter)
        self._lbl_remove.setWordWrap(True)
        self._lbl_remove.setStyleSheet("font-size:11px; color:#8b949e;")
        centre.addWidget(self._lbl_remove)
        centre.addStretch()
        preview_row.addLayout(centre)

        preview_row.addWidget(self._panel_out, stretch=1)
        root.addLayout(preview_row)

        # ── Filmstrip timeline ────────────────────────────────────────────
        hint = QLabel(
            "Drag the  🟠 In  and  🔵 Out  handles to set the trim range"
        )
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet("font-size:11px; color:#8b949e; margin-top:4px;")
        root.addWidget(hint)

        self._timeline = TrimTimeline(self._total, self)
        root.addWidget(self._timeline)

        self._timeline.start_changed.connect(self._on_start_changed)
        self._timeline.end_changed.connect(self._on_end_changed)

        # ── Delete images checkbox ────────────────────────────────────────
        self._chk_delete = QCheckBox(
            "Also delete trimmed image files from disk  "
            "(irreversible — cannot be undone!)"
        )
        self._chk_delete.setChecked(False)
        root.addWidget(self._chk_delete)

        # ── Warning ───────────────────────────────────────────────────────
        warn = QLabel(
            "⚠  Trim rewrites tracks.json immediately.  "
            "This action cannot be undone via Ctrl+Z."
        )
        warn.setWordWrap(True)
        warn.setStyleSheet("color:#d29922; font-size:11px;")
        root.addWidget(warn)

        # ── Buttons ───────────────────────────────────────────────────────
        btns = QDialogButtonBox()
        self._btn_trim = btns.addButton("✂  Trim & Save", QDialogButtonBox.AcceptRole)
        self._btn_trim.setStyleSheet(
            "QPushButton { background:#238636; color:#fff; font-weight:700;"
            " padding:7px 20px; border-radius:6px; border:none; }"
            "QPushButton:hover { background:#2ea043; }"
            "QPushButton:disabled { background:#21262d; color:#484f58; border:none; }"
        )
        btns.addButton("Cancel", QDialogButtonBox.RejectRole)
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

        # Initial summary
        self._refresh_summary()

    # ── Slots ─────────────────────────────────────────────────────────────

    def _on_start_changed(self, pos: int):
        self._refresh_summary()
        if pos != self._prev_start:
            self._prev_start = pos
            pix = self._get_thumb(pos)
            self._panel_in.update_preview(pos, pix)

    def _on_end_changed(self, pos: int):
        self._refresh_summary()
        if pos != self._prev_end:
            self._prev_end = pos
            pix = self._get_thumb(pos)
            self._panel_out.update_preview(pos, pix)

    def _refresh_both_previews(self):
        s = self._timeline.start
        e = self._timeline.end
        self._prev_start = s
        self._prev_end   = e
        self._panel_in.update_preview(s,  self._get_thumb(s))
        self._panel_out.update_preview(e, self._get_thumb(e))
        self._refresh_summary()

    def _refresh_summary(self):
        s     = self._timeline.start
        e     = self._timeline.end
        keep  = e - s + 1
        tl    = s
        tr    = (self._total - 1) - e
        total_trim = tl + tr

        if total_trim == 0:
            self._lbl_keep.setText(f"All {self._total} frames kept")
            self._lbl_remove.setText("No frames will be removed")
            self._btn_trim.setEnabled(False)
        else:
            self._lbl_keep.setText(f"{keep} frames kept")
            parts = []
            if tl:
                parts.append(f"{tl} from start")
            if tr:
                parts.append(f"{tr} from end")
            self._lbl_remove.setText(f"Removing {total_trim}  ({', '.join(parts)})")
            self._btn_trim.setEnabled(True)

    def _on_accept(self):
        self.result_start_pos     = self._timeline.start
        self.result_end_pos       = self._timeline.end
        self.result_delete_images = self._chk_delete.isChecked()
        self.accept()
