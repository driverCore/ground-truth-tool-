"""I/O utilities — load/save all data formats for the GT Track Editor."""
from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path


# ── Load ──────────────────────────────────────────────────────────────────

def load_bytetrack_json(json_path: str) -> list[dict]:
    """Load tracks.json produced by bytetrack_gt_tt1.py.
    Returns list of frame records, each with 'frame', 'image_w', 'image_h', 'tracks'.
    """
    with open(json_path, "r") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"Expected a JSON array in {json_path}")
    return data


def load_project_file(path: str) -> dict:
    """Load a .kgt project file."""
    with open(path, "r") as f:
        return json.load(f)


# ── Save ──────────────────────────────────────────────────────────────────

def save_project_file(path: str, data: dict):
    """Save a .kgt project file atomically."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = str(p) + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    import os
    os.replace(tmp, path)


def save_ground_truth_json(path: str, records: list[dict]):
    """Save ground_truth_tracks.json with corrected IDs."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(records, f, indent=2)
    print(f"[IO] Saved ground_truth_tracks.json → {path}")


# ── Export ────────────────────────────────────────────────────────────────

def export_mot_challenge(path: str, records: list[dict]):
    """Export MOTChallenge gt.txt format.
    Format: <frame>,<id>,<bb_left>,<bb_top>,<bb_width>,<bb_height>,1,-1,-1,-1
    Frame numbering is 1-based.
    """
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for rec in records:
        frame_1 = int(rec.get("frame_idx", 0)) + 1
        for det in rec.get("tracks", []):
            x1, y1, x2, y2 = det["bbox_xyxy"]
            w = x2 - x1
            h = y2 - y1
            tid = int(det["track_id"])
            lines.append(f"{frame_1},{tid},{x1:.2f},{y1:.2f},{w:.2f},{h:.2f},1,-1,-1,-1")
    with open(path, "w") as f:
        f.write("\n".join(lines))
        if lines:
            f.write("\n")
    print(f"[IO] Exported MOTChallenge gt.txt → {path}  ({len(lines)} lines)")


def export_correction_log(path: str, log: list[dict]):
    """Export CSV correction log."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["timestamp", "frame_idx", "frame_name", "det_idx",
                  "original_id", "corrected_id", "scope"]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(log)
    print(f"[IO] Exported correction log → {path}  ({len(log)} entries)")


def export_csv_summary(path: str, stats: dict):
    """Export a one-page CSV summary of editing statistics."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Metric", "Value"])
        w.writerow(["Export time", datetime.now().isoformat()])
        for k, v in stats.items():
            w.writerow([k, v])
    print(f"[IO] Exported CSV summary → {path}")
