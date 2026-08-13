"""Project file management (.kgt format) for the GT Track Editor."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

PROJECT_VERSION = 1


class Project:
    """Holds all paths and project-level metadata.
    Serialises to/from a .kgt JSON file.
    """

    def __init__(self):
        self.path:            Optional[str] = None   # .kgt file path
        self.frames_dir:      str = ""
        self.annot_dir:       str = ""
        self.bytetrack_json:  str = ""
        self.output_dir:      str = ""               # where exports go
        self.video_path:      str = ""               # optional .mp4
        self.last_frame_idx:  int = 0
        self.created_at:      str = ""
        self.modified_at:     str = ""

    # ── Factories ─────────────────────────────────────────────────────────

    @classmethod
    def new(cls,
            frames_dir:     str,
            bytetrack_json: str,
            annot_dir:      str = "",
            output_dir:     str = "",
            video_path:     str = "") -> "Project":
        p = cls()
        p.frames_dir     = frames_dir
        p.bytetrack_json = bytetrack_json
        p.annot_dir      = annot_dir
        p.output_dir     = output_dir or str(Path(bytetrack_json).parent)
        p.video_path     = video_path
        p.created_at     = datetime.now().isoformat()
        p.modified_at    = p.created_at
        return p

    @classmethod
    def load(cls, project_path: str) -> "Project":
        with open(project_path, "r") as f:
            data = json.load(f)
        p = cls()
        p.path           = project_path
        p.frames_dir     = data.get("frames_dir", "")
        p.annot_dir      = data.get("annot_dir", "")
        p.bytetrack_json = data.get("bytetrack_json", "")
        p.output_dir     = data.get("output_dir", str(Path(project_path).parent))
        p.video_path     = data.get("video_path", "")
        p.last_frame_idx = int(data.get("last_frame_idx", 0))
        p.created_at     = data.get("created_at", "")
        p.modified_at    = data.get("modified_at", "")
        return p

    # ── Serialization ──────────────────────────────────────────────────────

    def to_dict(self,
                corrections: dict,
                verified:    list[int],
                undo_count:  int = 0) -> dict:
        self.modified_at = datetime.now().isoformat()
        return {
            "version":       PROJECT_VERSION,
            "frames_dir":    self.frames_dir,
            "annot_dir":     self.annot_dir,
            "bytetrack_json": self.bytetrack_json,
            "output_dir":    self.output_dir,
            "video_path":    self.video_path,
            "last_frame_idx": self.last_frame_idx,
            "corrections":   corrections,
            "verified_frames": verified,
            "undo_count":    undo_count,
            "created_at":    self.created_at,
            "modified_at":   self.modified_at,
        }

    def save(self, project_path: str, corrections: dict,
             verified: list[int], undo_count: int = 0):
        import os
        self.path = project_path
        data = self.to_dict(corrections, verified, undo_count)
        p = Path(project_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = str(p) + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, project_path)

    @staticmethod
    def corrections_from_dict(data: dict) -> tuple[dict, list[int]]:
        raw_corr = data.get("corrections", {})
        corrections = {int(k): {int(dk): int(dv) for dk, dv in v.items()}
                       for k, v in raw_corr.items()}
        verified = [int(x) for x in data.get("verified_frames", [])]
        return corrections, verified

    # ── Validation ────────────────────────────────────────────────────────

    def validate(self) -> list[str]:
        """Return list of problems (empty = OK)."""
        errs = []
        if not Path(self.frames_dir).is_dir():
            errs.append(f"Frames directory not found: {self.frames_dir}")
        if not Path(self.bytetrack_json).is_file():
            errs.append(f"ByteTrack JSON not found: {self.bytetrack_json}")
        return errs

    # ── Derived paths ─────────────────────────────────────────────────────

    def gt_json_path(self) -> str:
        return str(Path(self.output_dir) / "ground_truth_tracks.json")

    def mot_txt_path(self) -> str:
        return str(Path(self.output_dir) / "gt.txt")

    def correction_log_path(self) -> str:
        return str(Path(self.output_dir) / "correction_log.csv")

    def summary_csv_path(self) -> str:
        return str(Path(self.output_dir) / "summary.csv")
