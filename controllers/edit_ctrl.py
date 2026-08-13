"""Edit controller — all ID-correction business logic, creates Commands and pushes to History."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from PySide6.QtCore import QObject, Signal

from models.track_store import TrackStore
from models.history import (History, ChangeIdCommand, MergeTracksCommand,
                             SplitTrackCommand, VerifyFrameCommand,
                             MoveResizeBboxCommand, ChangeClassCommand,
                             AddDetectionCommand, DeleteDetectionCommand)


class EditController(QObject):
    """Owns TrackStore + History. Orchestrates all edits and emits change signals.

    Signals:
        tracks_changed(frame_idx): fire after any edit so the canvas/panel refresh.
        history_changed(): undo/redo stack state changed.
        project_modified(): any change that requires a save.
        statistics_changed(): stats panel should refresh.
    """

    tracks_changed    = Signal(int)   # frame_idx
    history_changed   = Signal()
    project_modified  = Signal()
    statistics_changed = Signal()

    def __init__(self, store: TrackStore, history: History, parent=None):
        super().__init__(parent)
        self._store   = store
        self._history = history
        self._log: list[dict] = []   # correction log entries

    # ── Properties ────────────────────────────────────────────────────────

    @property
    def store(self) -> TrackStore:
        return self._store

    @property
    def history(self) -> History:
        return self._history

    @property
    def correction_log(self) -> list[dict]:
        return self._log

    # ── Change ID ─────────────────────────────────────────────────────────

    def preview_change_id(self,
                          frame_idx: int,
                          det_idx:   int,
                          new_id:    int,
                          scope:     str,
                          end_frame: Optional[int] = None,
                          ) -> list[tuple[int, int, int]]:
        """
        Return preview of (frame_idx, det_idx, old_id) tuples that would change.
        scope: 'frame' | 'forward' | 'range'
        """
        if scope == "frame":
            eff = self._store.get_frame_tracks(frame_idx)
            det = next((d for d in eff if d.det_idx == det_idx), None)
            if det is None:
                return []
            old = det.current_id
            if old == new_id:
                return []
            return [(frame_idx, det_idx, old)]

        elif scope in ("forward", "range"):
            ef = end_frame if scope == "range" else None
            return self._store.preview_propagate(frame_idx, det_idx, new_id, ef)

        return []

    def change_id(self,
                  frame_idx: int,
                  det_idx:   int,
                  new_id:    int,
                  scope:     str,
                  end_frame: Optional[int] = None) -> bool:
        """Apply ID change and push to history.  Returns True on success."""
        changes = self.preview_change_id(frame_idx, det_idx, new_id, scope, end_frame)
        if not changes:
            return False

        eff = self._store.get_frame_tracks(frame_idx)
        det = next((d for d in eff if d.det_idx == det_idx), None)
        original_id = det.current_id if det else det_idx

        cmd = ChangeIdCommand(
            self._store, changes, new_id, original_id,
            desc=f"Change ID {original_id}→{new_id} ({scope})"
        )
        self._history.push(cmd)

        # Log the correction
        for fi, di, old in changes:
            self._log.append({
                "timestamp":    datetime.now().isoformat(),
                "frame_idx":    fi,
                "frame_name":   self._store.get_frame_data(fi).frame_name if self._store.get_frame_data(fi) else "",
                "det_idx":      di,
                "original_id":  original_id,
                "corrected_id": new_id,
                "scope":        scope,
            })

        # Write corrected IDs back to the original tracks.json immediately
        self._flush()

        # Emit signals for all affected frames
        affected_frames = {fi for fi, _, _ in changes}
        for fi in affected_frames:
            self.tracks_changed.emit(fi)
        self.history_changed.emit()
        self.project_modified.emit()
        self.statistics_changed.emit()
        return True

    # ── Merge tracks ──────────────────────────────────────────────────────

    def preview_merge(self, source_id: int, target_id: int) -> list[tuple[int, int, int]]:
        return self._store.preview_merge(source_id, target_id)

    def merge_tracks(self, source_id: int, target_id: int) -> bool:
        if source_id == target_id:
            return False
        affected = self._store.preview_merge(source_id, target_id)
        if not affected:
            return False
        cmd = MergeTracksCommand(self._store, source_id, target_id, affected)
        self._history.push(cmd)
        self._flush()
        affected_frames = {fi for fi, _, _ in affected}
        for fi in affected_frames:
            self.tracks_changed.emit(fi)
        self.history_changed.emit()
        self.project_modified.emit()
        self.statistics_changed.emit()
        return True

    # ── Split track ───────────────────────────────────────────────────────

    def split_track(self, original_id: int, split_frame: int,
                    new_id: Optional[int] = None) -> tuple[bool, int]:
        """Split track from split_frame onward.  Returns (success, new_id)."""
        if new_id is None:
            new_id = self._store.get_next_available_id()
        affected = self._store.preview_split(original_id, split_frame, new_id)
        if not affected:
            return False, new_id
        cmd = SplitTrackCommand(self._store, original_id, split_frame, new_id, affected)
        self._history.push(cmd)
        self._flush()
        affected_frames = {fi for fi, _ in affected}
        for fi in affected_frames:
            self.tracks_changed.emit(fi)
        self.history_changed.emit()
        self.project_modified.emit()
        self.statistics_changed.emit()
        return True, new_id

    # ── Verify frame ──────────────────────────────────────────────────────

    def verify_frame(self, frame_idx: int, verified: bool = True):
        cmd = VerifyFrameCommand(self._store, frame_idx, verified)
        self._history.push(cmd)
        self.tracks_changed.emit(frame_idx)
        self.history_changed.emit()
        self.project_modified.emit()
        self.statistics_changed.emit()

    # ── Move / Resize Bbox ────────────────────────────────────────────────
    def edit_bbox(self, frame_idx: int, det_idx: int, old_bbox: list[float], new_bbox: list[float]) -> bool:
        if old_bbox == new_bbox:
            return False
        cmd = MoveResizeBboxCommand(self._store, frame_idx, det_idx, old_bbox, new_bbox)
        self._history.push(cmd)
        self._flush()
        self.tracks_changed.emit(frame_idx)
        self.history_changed.emit()
        self.project_modified.emit()
        self.statistics_changed.emit()
        return True

    # ── Change Class ──────────────────────────────────────────────────────
    def change_class(self, frame_idx: int, det_idx: int, old_cls_id: int, old_cls_name: str,
                     new_cls_id: int, new_cls_name: str) -> bool:
        if (old_cls_id, old_cls_name) == (new_cls_id, new_cls_name):
            return False
        cmd = ChangeClassCommand(self._store, frame_idx, det_idx, old_cls_id, old_cls_name, new_cls_id, new_cls_name)
        self._history.push(cmd)
        self._flush()
        self.tracks_changed.emit(frame_idx)
        self.history_changed.emit()
        self.project_modified.emit()
        self.statistics_changed.emit()
        return True

    # ── Add Detection ─────────────────────────────────────────────────────
    def add_detection(self, frame_idx: int, bbox_xyxy: list[float], track_id: Optional[int] = None,
                      class_id: int = 0, class_name: str = "player") -> Optional[int]:
        if track_id is None:
            track_id = self._store.get_next_available_id()
        cmd = AddDetectionCommand(self._store, frame_idx, bbox_xyxy, track_id, class_id, class_name)
        self._history.push(cmd)
        self._flush()
        self.tracks_changed.emit(frame_idx)
        self.history_changed.emit()
        self.project_modified.emit()
        self.statistics_changed.emit()
        return cmd._det_idx

    # ── Delete Detection ──────────────────────────────────────────────────
    def delete_detection(self, frame_idx: int, det_idx: int) -> bool:
        cmd = DeleteDetectionCommand(self._store, frame_idx, det_idx)
        self._history.push(cmd)
        self._flush()
        self.tracks_changed.emit(frame_idx)
        self.history_changed.emit()
        self.project_modified.emit()
        self.statistics_changed.emit()
        return True

    # ── Undo / Redo ───────────────────────────────────────────────────────

    def undo(self) -> Optional[str]:
        desc = self._history.undo()
        if desc is not None:
            self._flush()
            for f in self._store.all_frames():
                self.tracks_changed.emit(f.frame_idx)
            self.history_changed.emit()
            self.project_modified.emit()
            self.statistics_changed.emit()
        return desc

    def redo(self) -> Optional[str]:
        desc = self._history.redo()
        if desc is not None:
            self._flush()
            for f in self._store.all_frames():
                self.tracks_changed.emit(f.frame_idx)
            self.history_changed.emit()
            self.project_modified.emit()
            self.statistics_changed.emit()
        return desc

    def can_undo(self) -> bool:
        return self._history.can_undo()

    def can_redo(self) -> bool:
        return self._history.can_redo()

    # ── Internal ──────────────────────────────────────────────────────────

    def _flush(self):
        """Write corrected IDs back to the original tracks.json immediately."""
        try:
            self._store.write_to_json()
        except Exception as e:
            print(f"[EditCtrl] WARNING: failed to write tracks.json: {e}")
