"""Command-pattern Undo/Redo history for the GT Track Editor."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from models.track_store import TrackStore


class Command(ABC):
    """Abstract base for all reversible edit commands."""
    description: str = "Edit"

    @abstractmethod
    def execute(self): ...

    @abstractmethod
    def undo(self): ...


# ── Concrete commands ──────────────────────────────────────────────────────

class ChangeIdCommand(Command):
    """Change one or more detection IDs, remembering prior values for undo."""

    def __init__(self, store: "TrackStore",
                 changes: list[tuple[int, int, int]],  # (frame_idx, det_idx, old_id)
                 new_id: int,
                 source_original_id: int,
                 desc: str = ""):
        self._store = store
        self._changes = changes
        self._new_id = new_id
        self._source_original_id = source_original_id
        self.description = desc or f"Change ID {source_original_id} → {new_id}"

    def execute(self):
        for frame_idx, det_idx, _ in self._changes:
            self._store.set_correction(frame_idx, det_idx, self._new_id)

    def undo(self):
        for frame_idx, det_idx, old_id in self._changes:
            tracks = self._store.get_frame_tracks(frame_idx)
            det = next((d for d in tracks if d.det_idx == det_idx), None)
            if det is None:
                continue
            if old_id == det.original_id:
                self._store.clear_correction(frame_idx, det_idx)
            else:
                self._store.set_correction(frame_idx, det_idx, old_id)


class MergeTracksCommand(Command):
    """Merge all detections of source_id into target_id."""

    def __init__(self, store: "TrackStore",
                 source_id: int, target_id: int,
                 affected: list[tuple[int, int, int]]):  # (frame_idx, det_idx, old_id)
        self._store = store
        self._source_id = source_id
        self._target_id = target_id
        self._affected = affected
        self.description = f"Merge ID {source_id} → {target_id}"

    def execute(self):
        for frame_idx, det_idx, _ in self._affected:
            self._store.set_correction(frame_idx, det_idx, self._target_id)

    def undo(self):
        for frame_idx, det_idx, old_id in self._affected:
            tracks = self._store.get_frame_tracks(frame_idx)
            det = next((d for d in tracks if d.det_idx == det_idx), None)
            if det is None:
                continue
            if old_id == det.original_id:
                self._store.clear_correction(frame_idx, det_idx)
            else:
                self._store.set_correction(frame_idx, det_idx, old_id)


class SplitTrackCommand(Command):
    """Split a track from split_frame onward, assigning a new_id."""

    def __init__(self, store: "TrackStore",
                 original_id: int, split_frame: int, new_id: int,
                 affected: list[tuple[int, int]]):  # (frame_idx, det_idx)
        self._store = store
        self._original_id = original_id
        self._split_frame = split_frame
        self._new_id = new_id
        self._affected = affected
        self.description = f"Split ID {original_id} at frame {split_frame} → new ID {new_id}"

    def execute(self):
        for frame_idx, det_idx in self._affected:
            self._store.set_correction(frame_idx, det_idx, self._new_id)

    def undo(self):
        for frame_idx, det_idx in self._affected:
            tracks = self._store.get_frame_tracks(frame_idx)
            det = next((d for d in tracks if d.det_idx == det_idx), None)
            if det is None:
                continue
            if det.original_id == self._original_id:
                self._store.clear_correction(frame_idx, det_idx)
            else:
                self._store.set_correction(frame_idx, det_idx, self._original_id)


class VerifyFrameCommand(Command):
    """Mark/unmark a frame as verified."""

    def __init__(self, store: "TrackStore", frame_idx: int, verify: bool = True):
        self._store = store
        self._frame_idx = frame_idx
        self._verify = verify
        self._was_verified = frame_idx in store._verified_frames
        self.description = f"{'Verify' if verify else 'Unverify'} frame {frame_idx}"

    def execute(self):
        if self._verify:
            self._store._verified_frames.add(self._frame_idx)
        else:
            self._store._verified_frames.discard(self._frame_idx)

    def undo(self):
        if self._was_verified:
            self._store._verified_frames.add(self._frame_idx)
        else:
            self._store._verified_frames.discard(self._frame_idx)


class MoveResizeBboxCommand(Command):
    """Move or resize a bounding box."""

    def __init__(self, store: "TrackStore", frame_idx: int, det_idx: int,
                 old_bbox: list[float], new_bbox: list[float], desc: str = ""):
        self._store = store
        self._frame_idx = frame_idx
        self._det_idx = det_idx
        self._old_bbox = list(old_bbox)
        self._new_bbox = list(new_bbox)
        self.description = desc or f"Edit bbox det {det_idx} frame {frame_idx+1}"

    def execute(self):
        self._store.set_bbox_edit(self._frame_idx, self._det_idx, self._new_bbox)

    def undo(self):
        self._store.set_bbox_edit(self._frame_idx, self._det_idx, self._old_bbox)


class ChangeClassCommand(Command):
    """Change detection class ID and class name."""

    def __init__(self, store: "TrackStore", frame_idx: int, det_idx: int,
                 old_cls_id: int, old_cls_name: str,
                 new_cls_id: int, new_cls_name: str):
        self._store = store
        self._frame_idx = frame_idx
        self._det_idx = det_idx
        self._old_cls_id = old_cls_id
        self._old_cls_name = old_cls_name
        self._new_cls_id = new_cls_id
        self._new_cls_name = new_cls_name
        self.description = f"Change class det {det_idx} → {new_cls_name}"

    def execute(self):
        self._store.set_class_edit(self._frame_idx, self._det_idx, self._new_cls_id, self._new_cls_name)

    def undo(self):
        self._store.set_class_edit(self._frame_idx, self._det_idx, self._old_cls_id, self._old_cls_name)


class AddDetectionCommand(Command):
    """Add a new detection to a frame."""

    def __init__(self, store: "TrackStore", frame_idx: int, bbox_xyxy: list[float],
                 track_id: int, class_id: int = 0, class_name: str = "player"):
        self._store = store
        self._frame_idx = frame_idx
        self._bbox_xyxy = list(bbox_xyxy)
        self._track_id = track_id
        self._class_id = class_id
        self._class_name = class_name
        self._det_idx: Optional[int] = None
        self.description = f"Add box ID {track_id} frame {frame_idx+1}"

    def execute(self):
        self._det_idx = self._store.add_detection(
            self._frame_idx, self._bbox_xyxy, self._track_id,
            self._class_id, self._class_name
        )

    def undo(self):
        if self._det_idx is not None:
            self._store.remove_added_detection(self._frame_idx, self._det_idx)


class DeleteDetectionCommand(Command):
    """Delete an existing detection from a frame."""

    def __init__(self, store: "TrackStore", frame_idx: int, det_idx: int, desc: str = ""):
        self._store = store
        self._frame_idx = frame_idx
        self._det_idx = det_idx
        self.description = desc or f"Delete box det {det_idx} frame {frame_idx+1}"

    def execute(self):
        self._store.mark_detection_deleted(self._frame_idx, self._det_idx)

    def undo(self):
        self._store.unmark_detection_deleted(self._frame_idx, self._det_idx)


# ── History stack ──────────────────────────────────────────────────────────

class History:
    """Unlimited undo/redo stack using the Command pattern."""

    def __init__(self):
        self._undo_stack: list[Command] = []
        self._redo_stack: list[Command] = []

    def push(self, cmd: Command):
        """Execute a command and push it onto the undo stack."""
        cmd.execute()
        self._undo_stack.append(cmd)
        self._redo_stack.clear()

    def undo(self) -> Optional[str]:
        """Undo the last command. Returns its description or None."""
        if not self._undo_stack:
            return None
        cmd = self._undo_stack.pop()
        cmd.undo()
        self._redo_stack.append(cmd)
        return cmd.description

    def redo(self) -> Optional[str]:
        """Redo the next command. Returns its description or None."""
        if not self._redo_stack:
            return None
        cmd = self._redo_stack.pop()
        cmd.execute()
        self._undo_stack.append(cmd)
        return cmd.description

    def can_undo(self) -> bool:
        return bool(self._undo_stack)

    def can_redo(self) -> bool:
        return bool(self._redo_stack)

    def peek_undo(self) -> Optional[str]:
        return self._undo_stack[-1].description if self._undo_stack else None

    def peek_redo(self) -> Optional[str]:
        return self._redo_stack[-1].description if self._redo_stack else None

    def clear(self):
        self._undo_stack.clear()
        self._redo_stack.clear()

    def undo_count(self) -> int:
        return len(self._undo_stack)

    def redo_count(self) -> int:
        return len(self._redo_stack)
