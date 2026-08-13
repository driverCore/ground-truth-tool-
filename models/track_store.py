"""Core data model for all track state in the GT Track Editor.

TrackStore holds:
  - Immutable frame / detection data loaded from ByteTrack JSON
  - A corrections layer {frame_idx: {det_idx: corrected_id}}
  - A set of verified frame indices
  - Derived ID-switch frame set (recomputed on every correction)
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Optional


# ── Data classes ──────────────────────────────────────────────────────────

@dataclass
class Detection:
    """Immutable detection record from the ByteTrack JSON."""
    det_idx:     int
    original_id: int          # ByteTrack-assigned ID — never changes
    class_id:    int
    class_name:  str
    bbox_xyxy:   list[float]  # [x1, y1, x2, y2] absolute pixels — immutable GT
    conf:        float


@dataclass
class FrameData:
    """Immutable per-frame record."""
    frame_idx:   int
    frame_name:  str           # e.g. "frame_0001"
    image_w:     int
    image_h:     int
    detections:  list[Detection]


@dataclass
class EffectiveDet:
    """A detection with corrections applied — what the UI displays."""
    det_idx:     int
    original_id: int
    current_id:  int
    class_id:    int
    class_name:  str
    bbox_xyxy:   list[float]
    conf:        float
    status:      str   # 'unreviewed' | 'edited' | 'verified'
    is_added:    bool = False


# ── TrackStore ────────────────────────────────────────────────────────────

class TrackStore:
    """Central data model. Pure Python — no Qt dependencies."""

    def __init__(self):
        self._frames:          list[FrameData]             = []
        self._frame_map:       dict[int, FrameData]        = {}   # frame_idx → FrameData
        self._corrections:     dict[int, dict[int, int]]             = {}   # {frame_idx: {det_idx: new_id}}
        self._bbox_edits:      dict[int, dict[int, list[float]]]     = {}   # {frame_idx: {det_idx: [x1,y1,x2,y2]}}
        self._class_edits:     dict[int, dict[int, tuple[int, str]]] = {}   # {frame_idx: {det_idx: (class_id, class_name)}}
        self._added_detections: dict[int, list[Detection]]           = {}   # {frame_idx: [Detection]}
        self._deleted_detections: dict[int, set[int]]                = {}   # {frame_idx: {det_idx}}
        self._next_det_idx:    int                                   = 1000
        self._verified_frames: set[int]                              = set()
        self._switch_frames:   set[int]                              = set()
        self._corrections_log: list[dict]                            = []
        self._json_path:       Optional[str]                         = None  # path to source tracks.json
        self._range_start_pos: int                                   = 0
        self._range_end_pos:   int                                   = -1

    # ── Loading ───────────────────────────────────────────────────────────

    def load_from_records(self, records: list[dict]):
        """Ingest the list of frame dicts from tracks.json."""
        self._frames.clear()
        self._frame_map.clear()
        self._range_start_pos = 0
        self._range_end_pos   = -1

        for pos, rec in enumerate(records):
            frame_name = rec.get("frame", f"frame_{pos:04d}")
            # Parse 0-based index from name or position
            m = re.search(r"(\d+)", frame_name)
            frame_idx = (int(m.group(1)) - 1) if m else pos

            dets: list[Detection] = []
            for i, t in enumerate(rec.get("tracks", [])):
                det_id = int(t.get("track_id", t.get("original_id", i + 1)))
                dets.append(Detection(
                    det_idx     = i,
                    original_id = det_id,
                    class_id    = int(t.get("class_id", 0)),
                    class_name  = str(t.get("class_name", "")),
                    bbox_xyxy   = list(t["bbox_xyxy"]),
                    conf        = float(t.get("conf", 1.0)),
                ))

            fd = FrameData(
                frame_idx  = frame_idx,
                frame_name = frame_name,
                image_w    = int(rec.get("image_w", 1280)),
                image_h    = int(rec.get("image_h", 576)),
                detections = dets,
            )
            self._frames.append(fd)
            self._frame_map[frame_idx] = fd

        self._frames.sort(key=lambda f: f.frame_idx)
        self._recompute_switches()

    def load_corrections(self, corrections: dict, verified: list[int]):
        """Restore saved corrections from a project file."""
        self._corrections = {
            int(k): {int(dk): int(dv) for dk, dv in dmap.items()}
            for k, dmap in corrections.items()
        }
        self._verified_frames = set(int(v) for v in verified)
        self._recompute_switches()

    # ── JSON write-back ───────────────────────────────────────────────────

    def set_json_path(self, path: str):
        """Set the path of the source tracks.json so edits can be written back."""
        self._json_path = path

    def write_to_json(self):
        """Atomically rewrite the original tracks.json with all current corrections applied."""
        if not self._json_path:
            return
        records = self.to_export_records()
        tmp = self._json_path + ".tmp"
        try:
            with open(tmp, "w") as f:
                json.dump(records, f, indent=2)
            os.replace(tmp, self._json_path)
        except Exception:
            with open(self._json_path, "w") as f:
                json.dump(records, f, indent=2)
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except Exception:
                    pass


    # ── Frame queries ─────────────────────────────────────────────────────

    @property
    def frame_count(self) -> int:
        return len(self._frames)

    def all_frames(self) -> list[FrameData]:
        return list(self._frames)

    def get_frame_data(self, frame_idx: int) -> Optional[FrameData]:
        return self._frame_map.get(frame_idx)

    def get_frame_by_position(self, pos: int) -> Optional[FrameData]:
        if 0 <= pos < len(self._frames):
            return self._frames[pos]
        return None

    def position_of(self, frame_idx: int) -> int:
        for i, f in enumerate(self._frames):
            if f.frame_idx == frame_idx:
                return i
        return -1

    def first_frame_idx(self) -> int:
        return self._frames[0].frame_idx if self._frames else 0

    def last_frame_idx(self) -> int:
        return self._frames[-1].frame_idx if self._frames else 0

    # ── Track queries with corrections applied ─────────────────────────────

    def get_frame_tracks(self, frame_idx: int) -> list[EffectiveDet]:
        """Return detections for a frame with all corrections applied."""
        fd = self._frame_map.get(frame_idx)
        if fd is None:
            return []
        corr       = self._corrections.get(frame_idx, {})
        bbox_ed    = self._bbox_edits.get(frame_idx, {})
        cls_ed     = self._class_edits.get(frame_idx, {})
        del_dets   = self._deleted_detections.get(frame_idx, set())
        added_dets = self._added_detections.get(frame_idx, [])
        is_ver     = frame_idx in self._verified_frames

        all_dets = list(fd.detections) + list(added_dets)
        result = []
        for det in all_dets:
            if det.det_idx in del_dets:
                continue
            new_id = corr.get(det.det_idx, det.original_id)
            bbox   = list(bbox_ed.get(det.det_idx, det.bbox_xyxy))
            cid, cname = cls_ed.get(det.det_idx, (det.class_id, det.class_name))

            if is_ver:
                status = "verified"
            elif det.det_idx in corr or det.det_idx in bbox_ed or det.det_idx in cls_ed or any(d.det_idx == det.det_idx for d in added_dets):
                status = "edited"
            else:
                status = "unreviewed"

            result.append(EffectiveDet(
                det_idx     = det.det_idx,
                original_id = det.original_id,
                current_id  = new_id,
                class_id    = cid,
                class_name  = cname,
                bbox_xyxy   = bbox,
                conf        = det.conf,
                status      = status,
                is_added    = any(d.det_idx == det.det_idx for d in added_dets),
            ))
        return result

    def get_all_current_ids(self) -> set[int]:
        ids: set[int] = set()
        for f in self._frames:
            for ed in self.get_frame_tracks(f.frame_idx):
                ids.add(ed.current_id)
        return ids

    def get_next_available_id(self) -> int:
        used = self.get_all_current_ids()
        i = 1
        while i in used:
            i += 1
        return i

    def get_original_id_span(self, original_id: int) -> tuple[int, int, int]:
        """(start_frame_idx, end_frame_idx, frame_count) for a ByteTrack original_id."""
        hits = [f.frame_idx for f in self._frames
                if any(d.original_id == original_id for d in f.detections)]
        if not hits:
            return (-1, -1, 0)
        return (min(hits), max(hits), len(hits))

    def get_current_id_span(self, current_id: int) -> tuple[int, int, int]:
        """Span for a corrected current ID."""
        hits = [f.frame_idx for f in self._frames
                if any(ed.current_id == current_id
                       for ed in self.get_frame_tracks(f.frame_idx))]
        if not hits:
            return (-1, -1, 0)
        return (min(hits), max(hits), len(hits))

    def frames_with_original_id(self, original_id: int) -> list[tuple[int, int]]:
        """Return [(frame_idx, det_idx)] for every occurrence of original_id."""
        result: list[tuple[int, int]] = []
        for f in self._frames:
            for d in f.detections:
                if d.original_id == original_id:
                    result.append((f.frame_idx, d.det_idx))
        return result

    # ── Switch / status queries ────────────────────────────────────────────

    def get_switch_frames(self) -> list[int]:
        return sorted(self._switch_frames)

    def get_corrected_frames(self) -> list[int]:
        return sorted(self._corrections.keys())

    def get_verified_frames(self) -> list[int]:
        return sorted(self._verified_frames)

    def is_switch_frame(self, frame_idx: int) -> bool:
        return frame_idx in self._switch_frames

    def is_corrected_frame(self, frame_idx: int) -> bool:
        return frame_idx in self._corrections

    def is_verified_frame(self, frame_idx: int) -> bool:
        return frame_idx in self._verified_frames

    def get_statistics(self) -> dict:
        return {
            "Total frames":     len(self._frames),
            "Corrected frames": len(self._corrections),
            "Verified frames":  len(self._verified_frames),
            "ID switch frames": len(self._switch_frames),
            "Total tracks":     len(self.get_all_current_ids()),
        }

    # ── Low-level correction setters (called by Command.execute/undo) ──────

    def set_correction(self, frame_idx: int, det_idx: int, new_id: int):
        if frame_idx not in self._corrections:
            self._corrections[frame_idx] = {}
        self._corrections[frame_idx][det_idx] = new_id
        self._recompute_switches()

    def clear_correction(self, frame_idx: int, det_idx: int):
        if frame_idx in self._corrections:
            self._corrections[frame_idx].pop(det_idx, None)
            if not self._corrections[frame_idx]:
                del self._corrections[frame_idx]
        self._recompute_switches()

    def set_bbox_edit(self, frame_idx: int, det_idx: int, bbox_xyxy: list[float]):
        if frame_idx not in self._bbox_edits:
            self._bbox_edits[frame_idx] = {}
        self._bbox_edits[frame_idx][det_idx] = list(bbox_xyxy)

    def clear_bbox_edit(self, frame_idx: int, det_idx: int):
        if frame_idx in self._bbox_edits:
            self._bbox_edits[frame_idx].pop(det_idx, None)
            if not self._bbox_edits[frame_idx]:
                del self._bbox_edits[frame_idx]

    def set_class_edit(self, frame_idx: int, det_idx: int, class_id: int, class_name: str):
        if frame_idx not in self._class_edits:
            self._class_edits[frame_idx] = {}
        self._class_edits[frame_idx][det_idx] = (class_id, class_name)

    def clear_class_edit(self, frame_idx: int, det_idx: int):
        if frame_idx in self._class_edits:
            self._class_edits[frame_idx].pop(det_idx, None)
            if not self._class_edits[frame_idx]:
                del self._class_edits[frame_idx]

    def add_detection(self, frame_idx: int, bbox_xyxy: list[float], track_id: int,
                      class_id: int = 0, class_name: str = "player", conf: float = 1.0) -> int:
        det_idx = self._next_det_idx
        self._next_det_idx += 1
        det = Detection(
            det_idx=det_idx,
            original_id=track_id,
            class_id=class_id,
            class_name=class_name,
            bbox_xyxy=list(bbox_xyxy),
            conf=conf
        )
        if frame_idx not in self._added_detections:
            self._added_detections[frame_idx] = []
        self._added_detections[frame_idx].append(det)
        if track_id != det.original_id:
            self.set_correction(frame_idx, det_idx, track_id)
        self._recompute_switches()
        return det_idx

    def remove_added_detection(self, frame_idx: int, det_idx: int):
        if frame_idx in self._added_detections:
            self._added_detections[frame_idx] = [
                d for d in self._added_detections[frame_idx] if d.det_idx != det_idx
            ]
            if not self._added_detections[frame_idx]:
                del self._added_detections[frame_idx]
        self.clear_correction(frame_idx, det_idx)
        self.clear_bbox_edit(frame_idx, det_idx)
        self.clear_class_edit(frame_idx, det_idx)
        self._recompute_switches()

    def mark_detection_deleted(self, frame_idx: int, det_idx: int):
        if frame_idx not in self._deleted_detections:
            self._deleted_detections[frame_idx] = set()
        self._deleted_detections[frame_idx].add(det_idx)
        self._recompute_switches()

    def unmark_detection_deleted(self, frame_idx: int, det_idx: int):
        if frame_idx in self._deleted_detections:
            self._deleted_detections[frame_idx].discard(det_idx)
            if not self._deleted_detections[frame_idx]:
                del self._deleted_detections[frame_idx]
        self._recompute_switches()

    # ── Propagation preview (used by EditController) ───────────────────────

    def preview_propagate(self,
                          frame_idx: int,
                          det_idx: int,
                          new_id: int,
                          end_frame: Optional[int] = None
                          ) -> list[tuple[int, int, int]]:
        """
        Preview what would change if original_id's correction is propagated
        forward from frame_idx (to end_frame or track end).

        Returns: [(frame_idx, det_idx, old_current_id), ...]
        Stops propagation at the first frame with a conflict (new_id already
        used by a *different* detection).
        """
        fd = self._frame_map.get(frame_idx)
        if fd is None:
            return []
        src = next((d for d in fd.detections if d.det_idx == det_idx), None)
        if src is None:
            return []
        original_id = src.original_id
        changes: list[tuple[int, int, int]] = []

        for f in self._frames:
            fi = f.frame_idx
            if fi < frame_idx:
                continue
            if end_frame is not None and fi > end_frame:
                break

            target = next((d for d in f.detections if d.original_id == original_id), None)
            if target is None:
                continue

            corr = self._corrections.get(fi, {})
            old_id = corr.get(target.det_idx, target.original_id)
            if old_id == new_id:
                continue  # already correct

            # Conflict check: would new_id collide with another det in same frame?
            conflict = any(
                (corr.get(d.det_idx, d.original_id) == new_id and d.original_id != original_id)
                for d in f.detections
            )
            if conflict:
                break  # stop propagation here

            changes.append((fi, target.det_idx, old_id))

        return changes

    def preview_merge(self, source_id: int, target_id: int) -> list[tuple[int, int, int]]:
        """Preview all detections that would change when merging source→target."""
        changes: list[tuple[int, int, int]] = []
        for f in self._frames:
            eff_tracks = self.get_frame_tracks(f.frame_idx)
            for ed in eff_tracks:
                if ed.current_id == source_id:
                    # Would set this det's id to target_id
                    # Conflict: target_id already present in same frame via different det
                    clash = any(x.current_id == target_id and x.det_idx != ed.det_idx
                                for x in eff_tracks)
                    if clash:
                        continue  # skip conflicting frames (or abort)
                    changes.append((f.frame_idx, ed.det_idx, ed.current_id))
        return changes

    def preview_split(self, original_id: int, split_frame: int,
                      new_id: int) -> list[tuple[int, int]]:
        """Preview detections that would change when splitting from split_frame onward."""
        changes: list[tuple[int, int]] = []
        for f in self._frames:
            if f.frame_idx < split_frame:
                continue
            for d in f.detections:
                if d.original_id == original_id:
                    changes.append((f.frame_idx, d.det_idx))
        return changes

    # ── Switch detection ───────────────────────────────────────────────────

    def _recompute_switches(self):
        """Mark frames where the active ID set changes vs. the previous frame."""
        self._switch_frames.clear()
        prev_ids: Optional[set[int]] = None
        for f in self._frames:
            curr_ids = {ed.current_id for ed in self.get_frame_tracks(f.frame_idx)}
            if prev_ids is not None and curr_ids != prev_ids:
                self._switch_frames.add(f.frame_idx)
            prev_ids = curr_ids

    # ── Range Sliding Window Bounds ────────────────────────────────────────

    def set_range_bounds(self, start_pos: int, end_pos: int):
        if not self._frames:
            return
        sp = max(0, min(start_pos, len(self._frames) - 1))
        ep = max(sp, min(end_pos, len(self._frames) - 1))
        self._range_start_pos = sp
        self._range_end_pos   = ep

    def get_range_bounds(self) -> tuple[int, int]:
        if not self._frames:
            return (0, 0)
        end_p = self._range_end_pos if self._range_end_pos >= 0 else (len(self._frames) - 1)
        return (self._range_start_pos, end_p)

    def reset_range(self):
        if self._frames:
            self._range_start_pos = 0
            self._range_end_pos   = len(self._frames) - 1

    # ── Export serialization ──────────────────────────────────────────────

    def to_export_records(self) -> list[dict]:
        """Produce the full corrected records list for ground_truth_tracks.json,
        filtered to the active sliding window [range_start_pos, range_end_pos]."""
        if not self._frames:
            return []
        sp, ep = self.get_range_bounds()
        selected_frames = self._frames[sp : ep + 1]

        records = []
        for f in selected_frames:
            eff = self.get_frame_tracks(f.frame_idx)
            records.append({
                "frame":      f.frame_name,
                "frame_idx":  f.frame_idx,
                "image_w":    f.image_w,
                "image_h":    f.image_h,
                "tracks": [
                    {
                        "track_id":    ed.current_id,
                        "original_id": ed.current_id,
                        "class_id":    ed.class_id,
                        "class_name":  ed.class_name,
                        "conf":        ed.conf,
                        "bbox_xyxy":   ed.bbox_xyxy,
                        "status":      ed.status,
                    }
                    for ed in eff
                ],
            })
        return records

    def corrections_to_dict(self) -> dict:
        return {str(k): {str(dk): dv for dk, dv in v.items()}
                for k, v in self._corrections.items()}
