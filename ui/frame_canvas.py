"""Frame Canvas — displays frames with GT bbox overlays & LabelImg-style editing.

Features:
  - Loads frame images from a directory
  - Draws coloured bboxes + ID labels + 8 resize handles for selected box
  - Interactive box moving & resizing via mouse dragging
  - Box creation mode (click & drag empty area)
  - Zoom (Ctrl+Wheel) and pan (middle-drag / Space+drag)
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal, QPoint, QRectF, QEvent
from PySide6.QtGui import (
    QColor, QFont, QFontMetrics, QPainter, QPen, QPixmap,
    QBrush, QWheelEvent, QMouseEvent, QKeyEvent, QCursor,
)
from PySide6.QtWidgets import QWidget, QSizePolicy

from models.track_store import EffectiveDet
from utils.colors import (
    bbox_border_color, label_bg_color, BG_BASE, TEXT_SEC,
    STATUS_COLORS, ACCENT,
)


class FrameCanvas(QWidget):
    """Central display widget for frame viewing and bounding box editing.

    Signals:
        detection_clicked(det_idx, frame_idx)  — user clicked a bbox
        detection_hovered(det_idx, frame_idx)  — mouse is over a bbox
        bbox_edited(det_idx, frame_idx, old_bbox, new_bbox) — bbox moved/resized
        detection_created(frame_idx, bbox_xyxy) — new box drawn by user
    """

    detection_clicked = Signal(int, int)       # det_idx, frame_idx
    detection_hovered = Signal(int, int)       # det_idx, frame_idx
    bbox_edited       = Signal(int, int, list, list)  # det_idx, frame_idx, old_bbox, new_bbox
    detection_created = Signal(int, list)      # frame_idx, bbox_xyxy
    cancel_detection  = Signal(int, int)       # det_idx, frame_idx
    change_id_requested = Signal(int, int)     # det_idx, frame_idx
    id_edited_inplace = Signal(int, int, int)  # det_idx, frame_idx, new_id
    navigate_frame    = Signal(str)            # "prev" | "next"

    ZOOM_MIN = 0.1
    ZOOM_MAX = 10.0
    ZOOM_STEP = 1.15

    HANDLE_SIZE = 8

    HANDLE_CURSORS = {
        "TL": Qt.SizeFDiagCursor,
        "BR": Qt.SizeFDiagCursor,
        "TR": Qt.SizeBDiagCursor,
        "BL": Qt.SizeBDiagCursor,
        "T":  Qt.SizeVerCursor,
        "B":  Qt.SizeVerCursor,
        "L":  Qt.SizeHorCursor,
        "R":  Qt.SizeHorCursor,
    }

    def __init__(self, frames_dir: str, parent=None):
        super().__init__(parent)
        self._frames_dir  = Path(frames_dir)
        self._frame_idx   = -1
        self._detections: list[EffectiveDet] = []
        self._selected_det: Optional[int] = None   # det_idx
        self._hovered_det:  Optional[int] = None

        # Editing & Interaction state
        self._create_mode = False
        self._drag_mode: Optional[str] = None      # "MOVE" | "RESIZE" | "CREATE"
        self._active_handle: Optional[str] = None   # "TL", "TR", "BL", "BR", "T", "B", "L", "R"
        self._drag_start_canvas: QPoint = QPoint()
        self._orig_bbox: list[float] = []
        self._create_start: tuple[float, float] = (0.0, 0.0)
        self._creating_rect: Optional[list[float]] = None

        # Zoom / pan state
        self._zoom    = 1.0
        self._offset  = QPoint(0, 0)
        self._panning = False
        self._pan_start: QPoint = QPoint()
        self._offset_start: QPoint = QPoint()
        self._space_held = False

        # Cached pixmap
        self._pixmap: Optional[QPixmap] = None
        self._img_w = 1
        self._img_h = 1

        self.setMinimumSize(400, 300)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAttribute(Qt.WA_OpaquePaintEvent)

        # Fonts
        self._font      = QFont("Segoe UI", 9, QFont.Bold)
        self._font_info = QFont("Segoe UI", 11)

        # In-place ID editor
        from PySide6.QtWidgets import QLineEdit
        self._id_editor = QLineEdit(self)
        self._id_editor.setVisible(False)
        self._id_editor.setStyleSheet(
            "background-color: #1f2937; color: white; border: 1px solid #3b82f6; "
            "padding: 0px; margin: 0px; font-weight: bold; font-family: Segoe UI;"
        )
        self._id_editor.setFont(self._font)
        self._id_editor.editingFinished.connect(self._on_id_editing_finished)
        self._id_editor.installEventFilter(self)
        self._editing_det_idx = None

    # ── Public API ────────────────────────────────────────────────────────

    def display_frame(self, frame_idx: int, detections: list[EffectiveDet],
                      frame_name: str = ""):
        self._frame_idx  = frame_idx
        self._detections = detections
        self._frame_name = frame_name
        self._hovered_det  = None
        self._drag_mode    = None
        self._creating_rect = None
        self._pixmap = self._load_pixmap(frame_name or f"frame_{frame_idx + 1:04d}")
        if self._pixmap:
            self._img_w = self._pixmap.width()
            self._img_h = self._pixmap.height()
        if hasattr(self, "_id_editor"):
            self._id_editor.setVisible(False)
            self._editing_det_idx = None
        self.update()

    def set_selected_detection(self, det_idx: Optional[int]):
        self._selected_det = det_idx
        self.update()

    def set_create_mode(self, enabled: bool):
        self._create_mode = enabled
        if enabled:
            self.setCursor(Qt.CrossCursor)
        else:
            self.setCursor(Qt.ArrowCursor)

    def is_create_mode(self) -> bool:
        return self._create_mode

    def reset_zoom(self):
        self._zoom   = 1.0
        self._offset = QPoint(0, 0)
        self.update()

    def zoom_in(self):
        self._apply_zoom(self.ZOOM_STEP, self.rect().center())

    def zoom_out(self):
        self._apply_zoom(1.0 / self.ZOOM_STEP, self.rect().center())

    # ── Painting ──────────────────────────────────────────────────────────

    def paintEvent(self, _):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        # Background
        painter.fillRect(self.rect(), QColor(BG_BASE))

        if self._pixmap is None or self._pixmap.isNull():
            painter.setPen(QColor(TEXT_SEC))
            painter.drawText(self.rect(), Qt.AlignCenter,
                             "No frame loaded\n\nOpen a project to begin.")
            return

        # Compute image-to-canvas transform
        scale, ox, oy = self._compute_transform()

        # Draw image
        dest_w = int(self._img_w * scale)
        dest_h = int(self._img_h * scale)
        dest_x = ox
        dest_y = oy
        painter.drawPixmap(dest_x, dest_y, dest_w, dest_h, self._pixmap)

        # Draw bboxes
        painter.setFont(self._font)
        for det in self._detections:
            self._draw_bbox(painter, det, scale, ox, oy)

        # Draw box creation preview if drawing
        if self._creating_rect:
            cx1, cy1 = self._image_to_canvas(self._creating_rect[0], self._creating_rect[1])
            cx2, cy2 = self._image_to_canvas(self._creating_rect[2], self._creating_rect[3])
            pen = QPen(QColor(ACCENT), 2, Qt.DashLine)
            painter.setPen(pen)
            painter.setBrush(QBrush(QColor(0, 230, 118, 40)))
            painter.drawRect(QRectF(cx1, cy1, cx2 - cx1, cy2 - cy1))

        # Frame info overlay (bottom-left)
        self._draw_info_overlay(painter)

    def _draw_bbox(self, painter: QPainter, det: EffectiveDet,
                   scale: float, ox: int, oy: int):
        x1, y1, x2, y2 = det.bbox_xyxy
        cx1 = int(x1 * scale) + ox
        cy1 = int(y1 * scale) + oy
        cx2 = int(x2 * scale) + ox
        cy2 = int(y2 * scale) + oy

        is_selected = (det.det_idx == self._selected_det)
        is_hovered  = (det.det_idx == self._hovered_det)

        border = bbox_border_color(det.current_id, det.status)
        pen_w  = 3 if is_selected else (2 if is_hovered else 1)

        # Bbox outline
        pen = QPen(border, pen_w)
        if is_selected:
            pen.setStyle(Qt.SolidLine)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(cx1, cy1, cx2 - cx1, cy2 - cy1)

        # Selection glow
        if is_selected:
            glow = QColor(border)
            glow.setAlpha(40)
            painter.fillRect(cx1, cy1, cx2 - cx1, cy2 - cy1, glow)

            # Draw 8 resize handles for selected box
            handles = self._get_handles_canvas(det)
            hs = self.HANDLE_SIZE
            painter.setPen(QPen(QColor("white"), 1))
            painter.setBrush(QBrush(QColor(ACCENT)))
            for hx, hy in handles.values():
                painter.drawRect(hx - hs // 2, hy - hs // 2, hs, hs)

            # Draw × button for hovered or selected box
            if is_selected or is_hovered:
                btn_size = 20
                margin = 4
                btn_rect = QRectF(cx2 - btn_size - margin, cy1 + margin, btn_size, btn_size)
                
                # Draw a nice red circular button
                painter.setPen(QPen(QColor(255, 255, 255), 1.5))
                painter.setBrush(QBrush(QColor(239, 68, 68))) # Tailwind red-500
                painter.drawEllipse(btn_rect)
                
                # Draw '×' text centered
                old_font = painter.font()
                painter.setFont(QFont("Segoe UI", 11, QFont.Bold))
                painter.drawText(btn_rect, Qt.AlignCenter, "×")
                painter.setFont(old_font)

        # ID & Class label
        label = f"ID {det.current_id}"
        if det.class_name:
            label += f" | {det.class_name}"
        if det.original_id != det.current_id:
            label += f" (was {det.original_id})"

        fm      = QFontMetrics(self._font)
        txt_w   = fm.horizontalAdvance(label) + 8
        txt_h   = fm.height() + 4
        lx      = cx1
        ly      = max(cy1 - txt_h, 0)

        bg = label_bg_color(det.current_id, det.status)
        painter.fillRect(lx, ly, txt_w, txt_h, bg)
        painter.setPen(QColor("white"))
        painter.drawText(lx + 4, ly + txt_h - 4, label)

        # Status dot
        status_c = STATUS_COLORS.get(det.status, QColor("grey"))
        painter.setBrush(QBrush(status_c))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(cx2 - 10, cy1 + 2, 8, 8)

    def _draw_info_overlay(self, painter: QPainter):
        if self._frame_idx < 0:
            return
        text = f"Frame {self._frame_idx + 1}"
        if self._create_mode:
            text += "  [ADD BOX MODE]"
        painter.setFont(self._font_info)
        fm     = QFontMetrics(self._font_info)
        tw     = fm.horizontalAdvance(text) + 12
        th     = fm.height() + 6
        margin = 8
        rx     = margin
        ry     = self.height() - margin - th

        bg = QColor(0, 0, 0, 160)
        painter.fillRect(rx, ry, tw, th, bg)
        painter.setPen(QColor("white"))
        painter.drawText(rx + 6, ry + th - 4, text)

    # ── Geometry & Transform Helpers ──────────────────────────────────────

    def _compute_transform(self) -> tuple[float, int, int]:
        """Return (scale, offset_x, offset_y) to fit+centre image in widget."""
        W, H = self.width(), self.height()
        iw, ih = self._img_w, self._img_h
        base_scale = min(W / iw, H / ih)
        scale = base_scale * self._zoom
        sx = int((W - iw * scale) / 2) + self._offset.x()
        sy = int((H - ih * scale) / 2) + self._offset.y()
        return scale, sx, sy

    def _canvas_to_image(self, cx: int, cy: int) -> tuple[float, float]:
        scale, ox, oy = self._compute_transform()
        ix = (cx - ox) / scale
        iy = (cy - oy) / scale
        return max(0.0, min(float(self._img_w), ix)), max(0.0, min(float(self._img_h), iy))

    def _image_to_canvas(self, ix: float, iy: float) -> tuple[int, int]:
        scale, ox, oy = self._compute_transform()
        return int(ix * scale) + ox, int(iy * scale) + oy

    def _get_handles_canvas(self, det: EffectiveDet) -> dict[str, tuple[int, int]]:
        scale, ox, oy = self._compute_transform()
        x1, y1, x2, y2 = det.bbox_xyxy
        cx1 = int(x1 * scale) + ox
        cy1 = int(y1 * scale) + oy
        cx2 = int(x2 * scale) + ox
        cy2 = int(y2 * scale) + oy
        cmx = (cx1 + cx2) // 2
        cmy = (cy1 + cy2) // 2
        return {
            "TL": (cx1, cy1),
            "TR": (cx2, cy1),
            "BL": (cx1, cy2),
            "BR": (cx2, cy2),
            "T":  (cmx, cy1),
            "B":  (cmx, cy2),
            "L":  (cx1, cmy),
            "R":  (cx2, cmy),
        }

    def _get_cancel_btn_rect(self) -> Optional[QRectF]:
        target_det = self._hovered_det if self._hovered_det is not None else self._selected_det
        if target_det is None:
            return None
        det = next((d for d in self._detections if d.det_idx == target_det), None)
        if not det:
            return None

        scale, ox, oy = self._compute_transform()
        x1, y1, x2, y2 = det.bbox_xyxy
        cx2 = int(x2 * scale) + ox
        cy1 = int(y1 * scale) + oy

        btn_size = 20
        margin = 4
        return QRectF(cx2 - btn_size - margin, cy1 + margin, btn_size, btn_size)

    def _hit_test_label(self, cx: int, cy: int) -> Optional[int]:
        """Check if (cx, cy) is inside the ID label rect of any detection.
        Returns det_idx if found, else None.
        """
        if self._frame_idx < 0 or not self._detections:
            return None

        scale, ox, oy = self._compute_transform()
        fm = QFontMetrics(self._font)

        for det in self._detections:
            # Recompute label text and rect coordinates exactly as in _draw_bbox
            label = f"ID {det.current_id}"
            if det.class_name:
                label += f" | {det.class_name}"
            if det.original_id != det.current_id:
                label += f" (was {det.original_id})"

            txt_w = fm.horizontalAdvance(label) + 8
            txt_h = fm.height() + 4

            x1, y1, _, _ = det.bbox_xyxy
            lx = int(x1 * scale) + ox
            ly = max(int(y1 * scale) + oy - txt_h, 0)

            # Check if (cx, cy) is inside the label rect
            if lx <= cx <= lx + txt_w and ly <= cy <= ly + txt_h:
                return det.det_idx

        return None

    def _start_inplace_edit(self, det_idx: int):
        det = next((d for d in self._detections if d.det_idx == det_idx), None)
        if not det:
            return
        
        self._editing_det_idx = det_idx
        
        scale, ox, oy = self._compute_transform()
        fm = QFontMetrics(self._font)
        
        current_id_str = str(det.current_id)
        
        label = f"ID {det.current_id}"
        if det.class_name:
            label += f" | {det.class_name}"
        if det.original_id != det.current_id:
            label += f" (was {det.original_id})"

        txt_w = fm.horizontalAdvance(label) + 8
        txt_h = fm.height() + 4

        x1, y1, _, _ = det.bbox_xyxy
        lx = int(x1 * scale) + ox
        ly = max(int(y1 * scale) + oy - txt_h, 0)
        
        self._id_editor.setGeometry(lx, ly, max(txt_w, 60), txt_h)
        self._id_editor.setText(current_id_str)
        self._id_editor.setVisible(True)
        self._id_editor.setFocus()
        self._id_editor.selectAll()

    def _on_id_editing_finished(self):
        if self._editing_det_idx is None:
            return
        
        text = self._id_editor.text().strip()
        det_idx = self._editing_det_idx
        self._editing_det_idx = None
        self._id_editor.setVisible(False)
        
        det = next((d for d in self._detections if d.det_idx == det_idx), None)
        if det and text.isdigit():
            new_id = int(text)
            if new_id != det.current_id:
                self.id_edited_inplace.emit(det_idx, self._frame_idx, new_id)
        
        self.update()

    def _hit_test_handle(self, cx: int, cy: int) -> Optional[str]:
        if self._selected_det is None:
            return None
        det = next((d for d in self._detections if d.det_idx == self._selected_det), None)
        if not det:
            return None
        handles = self._get_handles_canvas(det)
        for h_name, (hx, hy) in handles.items():
            if abs(cx - hx) <= 8 and abs(cy - hy) <= 8:
                return h_name
        return None

    def _hit_test(self, cx: int, cy: int) -> Optional[int]:
        """Return det_idx of the smallest bbox containing the point, or None."""
        ix, iy = self._canvas_to_image(cx, cy)
        best_area = float("inf")
        best_idx  = None
        for det in self._detections:
            x1, y1, x2, y2 = det.bbox_xyxy
            if x1 <= ix <= x2 and y1 <= iy <= y2:
                area = (x2 - x1) * (y2 - y1)
                if area < best_area:
                    best_area = area
                    best_idx  = det.det_idx
        return best_idx

    # ── Mouse events ──────────────────────────────────────────────────────

    def mousePressEvent(self, e: QMouseEvent):
        if e.button() == Qt.MiddleButton or (e.button() == Qt.LeftButton and self._space_held):
            self._panning      = True
            self._pan_start    = e.pos()
            self._offset_start = QPoint(self._offset)
            self.setCursor(Qt.ClosedHandCursor)
            return

        if e.button() == Qt.LeftButton:
            # Check cancel button click first
            btn_rect = self._get_cancel_btn_rect()
            if btn_rect:
                mx, my = e.pos().x(), e.pos().y()
                if btn_rect.left() <= mx <= btn_rect.right() and btn_rect.top() <= my <= btn_rect.bottom():
                    target_det = self._hovered_det if self._hovered_det is not None else self._selected_det
                    if target_det is not None:
                        self.cancel_detection.emit(target_det, self._frame_idx)
                        e.accept()
                        return

            cx, cy = e.pos().x(), e.pos().y()

            # Check ID label click
            hit_det_idx = self._hit_test_label(cx, cy)
            if hit_det_idx is not None:
                self._start_inplace_edit(hit_det_idx)
                e.accept()
                return

            # 1. Check handle hit first
            h_name = self._hit_test_handle(cx, cy)
            if h_name and self._selected_det is not None:
                det = next((d for d in self._detections if d.det_idx == self._selected_det), None)
                if det:
                    self._drag_mode = "RESIZE"
                    self._active_handle = h_name
                    self._drag_start_canvas = e.pos()
                    self._orig_bbox = list(det.bbox_xyxy)
                    return

            # 2. Check create mode
            if self._create_mode:
                self._drag_mode = "CREATE"
                ix, iy = self._canvas_to_image(cx, cy)
                self._create_start = (ix, iy)
                self._creating_rect = [ix, iy, ix, iy]
                self.update()
                return

            # 3. Hit test bbox
            det_idx = self._hit_test(cx, cy)
            if det_idx is not None:
                if det_idx == self._selected_det:
                    # Dragging selected bbox to move
                    det = next((d for d in self._detections if d.det_idx == det_idx), None)
                    if det:
                        self._drag_mode = "MOVE"
                        self._drag_start_canvas = e.pos()
                        self._orig_bbox = list(det.bbox_xyxy)
                else:
                    self._selected_det = det_idx
                    self.update()
                    self.detection_clicked.emit(det_idx, self._frame_idx)
            else:
                self._selected_det = None
                self.update()

    def mouseMoveEvent(self, e: QMouseEvent):
        cx, cy = e.pos().x(), e.pos().y()

        if self._panning:
            delta = e.pos() - self._pan_start
            self._offset = self._offset_start + delta
            self.update()
            return

        if self._drag_mode == "RESIZE" and self._selected_det is not None and self._orig_bbox:
            det = next((d for d in self._detections if d.det_idx == self._selected_det), None)
            if det:
                ix, iy = self._canvas_to_image(cx, cy)
                six, siy = self._canvas_to_image(self._drag_start_canvas.x(), self._drag_start_canvas.y())
                d_ix = ix - six
                d_iy = iy - siy

                x1, y1, x2, y2 = self._orig_bbox
                h = self._active_handle
                if "L" in h: x1 += d_ix
                if "R" in h: x2 += d_ix
                if "T" in h: y1 += d_iy
                if "B" in h: y2 += d_iy

                # Clamp bounds
                nx1 = max(0.0, min(x1, x2 - 2))
                ny1 = max(0.0, min(y1, y2 - 2))
                nx2 = min(float(self._img_w), max(x2, nx1 + 2))
                ny2 = min(float(self._img_h), max(y2, ny1 + 2))
                det.bbox_xyxy = [nx1, ny1, nx2, ny2]
                self.update()
                return

        if self._drag_mode == "MOVE" and self._selected_det is not None and self._orig_bbox:
            det = next((d for d in self._detections if d.det_idx == self._selected_det), None)
            if det:
                ix, iy = self._canvas_to_image(cx, cy)
                six, siy = self._canvas_to_image(self._drag_start_canvas.x(), self._drag_start_canvas.y())
                d_ix = ix - six
                d_iy = iy - siy

                w = self._orig_bbox[2] - self._orig_bbox[0]
                h = self._orig_bbox[3] - self._orig_bbox[1]

                nx1 = max(0.0, min(float(self._img_w - w), self._orig_bbox[0] + d_ix))
                ny1 = max(0.0, min(float(self._img_h - h), self._orig_bbox[1] + d_iy))
                nx2 = nx1 + w
                ny2 = ny1 + h
                det.bbox_xyxy = [nx1, ny1, nx2, ny2]
                self.update()
                return

        if self._drag_mode == "CREATE":
            ix, iy = self._canvas_to_image(cx, cy)
            six, siy = self._create_start
            x1 = max(0.0, min(six, ix))
            y1 = max(0.0, min(siy, iy))
            x2 = min(float(self._img_w), max(six, ix))
            y2 = min(float(self._img_h), max(siy, iy))
            self._creating_rect = [x1, y1, x2, y2]
            self.update()
            return

        # Hover cursor logic
        if self._create_mode:
            self.setCursor(Qt.CrossCursor)
            return

        h_name = self._hit_test_handle(cx, cy)
        if h_name and h_name in self.HANDLE_CURSORS:
            self.setCursor(self.HANDLE_CURSORS[h_name])
            return

        # Check if mouse is over any label or button
        hit_label_det = self._hit_test_label(cx, cy)
        btn_rect = self._get_cancel_btn_rect()
        over_btn = False
        if btn_rect:
            if btn_rect.left() <= cx <= btn_rect.right() and btn_rect.top() <= cy <= btn_rect.bottom():
                over_btn = True

        if over_btn:
            # Keep current hovered/selected detection active
            pass
        elif hit_label_det is not None:
            if hit_label_det != self._hovered_det:
                self._hovered_det = hit_label_det
                self.update()
                self.detection_hovered.emit(hit_label_det, self._frame_idx)
            self.setCursor(Qt.PointingHandCursor)
            return
        else:
            det_idx = self._hit_test(cx, cy)
            if det_idx != self._hovered_det:
                self._hovered_det = det_idx
                self.update()
                if det_idx is not None:
                    self.detection_hovered.emit(det_idx, self._frame_idx)

        if det_idx is not None:
            if det_idx == self._selected_det:
                self.setCursor(Qt.SizeAllCursor)
            else:
                self.setCursor(Qt.PointingHandCursor)
        else:
            self.setCursor(Qt.ArrowCursor)

    def mouseReleaseEvent(self, e: QMouseEvent):
        if self._panning:
            self._panning = False
            self.setCursor(Qt.CrossCursor if self._create_mode else Qt.ArrowCursor)
            return

        if self._drag_mode in ("RESIZE", "MOVE") and self._selected_det is not None and self._orig_bbox:
            det = next((d for d in self._detections if d.det_idx == self._selected_det), None)
            if det and det.bbox_xyxy != self._orig_bbox:
                self.bbox_edited.emit(self._selected_det, self._frame_idx, self._orig_bbox, list(det.bbox_xyxy))

        elif self._drag_mode == "CREATE" and self._creating_rect:
            x1, y1, x2, y2 = self._creating_rect
            if (x2 - x1) >= 5 and (y2 - y1) >= 5:
                self.detection_created.emit(self._frame_idx, list(self._creating_rect))
            self._creating_rect = None

        self._drag_mode = None
        self._active_handle = None
        self.update()

    def wheelEvent(self, e: QWheelEvent):
        if e.modifiers() & Qt.ControlModifier:
            factor = self.ZOOM_STEP if e.angleDelta().y() > 0 else 1.0 / self.ZOOM_STEP
            self._apply_zoom(factor, e.position().toPoint())
            e.accept()

    def keyPressEvent(self, e: QKeyEvent):
        if e.key() == Qt.Key_Space and not e.isAutoRepeat():
            self._space_held = True
            self.setCursor(Qt.OpenHandCursor)
        super().keyPressEvent(e)

    def keyReleaseEvent(self, e: QKeyEvent):
        if e.key() == Qt.Key_Space:
            self._space_held = False
            self.setCursor(Qt.CrossCursor if self._create_mode else Qt.ArrowCursor)
        super().keyReleaseEvent(e)

    def mouseDoubleClickEvent(self, e: QMouseEvent):
        if e.button() == Qt.LeftButton:
            self.navigate_frame.emit("prev")
            e.accept()
        elif e.button() == Qt.RightButton:
            self.navigate_frame.emit("next")
            e.accept()
        else:
            super().mouseDoubleClickEvent(e)

    def eventFilter(self, watched, event) -> bool:
        if watched == self._id_editor and event.type() == QEvent.KeyPress:
            key = event.key()
            if key == Qt.Key_A or key == Qt.Key_D:
                self._on_id_editing_finished()
                if key == Qt.Key_A:
                    self.navigate_frame.emit("prev")
                else:
                    self.navigate_frame.emit("next")
                return True
        return super().eventFilter(watched, event)

    def _apply_zoom(self, factor: float, center: QPoint):
        old_zoom = self._zoom
        new_zoom = max(self.ZOOM_MIN, min(self.ZOOM_MAX, self._zoom * factor))
        if new_zoom == old_zoom:
            return
        ix = center.x() - self._offset.x()
        iy = center.y() - self._offset.y()
        ratio = new_zoom / old_zoom
        self._offset = QPoint(
            int(center.x() - ix * ratio),
            int(center.y() - iy * ratio),
        )
        self._zoom = new_zoom
        self.update()

    # ── Image loading ─────────────────────────────────────────────────────

    def _load_pixmap(self, frame_name: str) -> Optional[QPixmap]:
        for ext in (".jpg", ".jpeg", ".png", ".bmp"):
            p = self._frames_dir / (frame_name + ext)
            if p.exists():
                pm = QPixmap(str(p))
                if not pm.isNull():
                    return pm
        return None
