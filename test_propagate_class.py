"""
test_propagate_class.py
=======================
Automated test suite verifying the automatic class propagation feature:
1. Changing raider/defender class on a particular ID updates that ID across all subsequent frames.
2. Frames prior to the edit frame remain unaffected.
3. Undo cleanly reverts the class change across all subsequent frames.
4. Redo cleanly reapplies the class change across all subsequent frames.
5. propagate=False restricts the edit to the single frame.
6. Immediate JSON flush persists updated class labels.
"""

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

# Setup paths
APP_DIR = Path(r"c:\Users\aryan\Downloads\BTP\ground_truth\editor_app")
sys.path.insert(0, str(APP_DIR))

from models.track_store import TrackStore
from models.history import History
from controllers.edit_ctrl import EditController


def test_propagate_class_feature():
    print("=" * 70)
    print("TEST: Class propagation forward across subsequent frames")
    print("=" * 70)

    # 1. Create a temporary tracks.json with 5 frames and 2 tracks (ID 1: defender, ID 2: raider)
    test_records = []
    for f in range(5):
        test_records.append({
            "frame": f"frame_{f+1:04d}",
            "frame_idx": f,
            "image_w": 1280,
            "image_h": 720,
            "tracks": [
                {
                    "track_id": 1,
                    "original_id": 1,
                    "class_id": 1,
                    "class_name": "defender",
                    "conf": 1.0,
                    "bbox_xyxy": [100.0, 100.0, 200.0, 300.0],
                    "status": "unreviewed",
                },
                {
                    "track_id": 2,
                    "original_id": 2,
                    "class_id": 0,
                    "class_name": "raider",
                    "conf": 1.0,
                    "bbox_xyxy": [400.0, 100.0, 500.0, 300.0],
                    "status": "unreviewed",
                },
            ],
        })

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tf:
        json.dump(test_records, tf, indent=2)
        temp_json_path = tf.name

    try:
        # Load into TrackStore
        from utils.io import load_bytetrack_json
        records = load_bytetrack_json(temp_json_path)
        store = TrackStore()
        store.load_from_records(records)
        store.set_json_path(temp_json_path)
        history = History()
        edit_ctrl = EditController(store, history)

        assert store.frame_count == 5, f"Expected 5 frames, got {store.frame_count}"

        # Test Case 1: At frame 2, change ID 1 from defender (1) to raider (0) with propagate=True
        frame_2_tracks = store.get_frame_tracks(2)
        det_id_1 = next(d for d in frame_2_tracks if d.current_id == 1)

        print("\n--- Test Case 1: Change ID 1 from defender to raider at frame 2 with propagate=True ---")
        ok = edit_ctrl.change_class(
            frame_idx=2,
            det_idx=det_id_1.det_idx,
            old_cls_id=1,
            old_cls_name="defender",
            new_cls_id=0,
            new_cls_name="raider",
            propagate=True,
        )
        assert ok, "change_class returned False"

        # Verify frames 0 and 1: ID 1 should STILL be defender
        for fi in [0, 1]:
            trks = store.get_frame_tracks(fi)
            det = next(d for d in trks if d.current_id == 1)
            assert det.class_id == 1 and det.class_name == "defender", (
                f"Prior frame {fi} should remain defender, got {det.class_name}"
            )
        print("  [OK] Prior frames (0, 1) unaffected: ID 1 is still defender.")

        # Verify frames 2, 3, 4: ID 1 should now be raider
        for fi in [2, 3, 4]:
            trks = store.get_frame_tracks(fi)
            det = next(d for d in trks if d.current_id == 1)
            assert det.class_id == 0 and det.class_name == "raider", (
                f"Subsequent frame {fi} should be raider, got {det.class_name}"
            )
        print("  [OK] Subsequent frames (2, 3, 4) automatically updated: ID 1 is now raider.")

        # Verify JSON file on disk was updated immediately
        disk_records = json.loads(Path(temp_json_path).read_text())
        for fi in [2, 3, 4]:
            d_trks = disk_records[fi]["tracks"]
            d_det = next(t for t in d_trks if t["track_id"] == 1)
            assert d_det["class_id"] == 0 and d_det["class_name"] == "raider", (
                f"Disk JSON frame {fi} should be raider, got {d_det['class_name']}"
            )
        print("  [OK] Changes flushed to disk tracks.json immediately.")

        # Test Case 2: Test Undo (Ctrl+Z)
        print("\n--- Test Case 2: Undo class change ---")
        desc = edit_ctrl.undo()
        print(f"  Undone: {desc.encode('ascii', 'replace').decode('ascii') if desc else ''}")
        for fi in range(5):
            trks = store.get_frame_tracks(fi)
            det = next(d for d in trks if d.current_id == 1)
            assert det.class_id == 1 and det.class_name == "defender", (
                f"After undo, frame {fi} should be defender, got {det.class_name}"
            )
        print("  [OK] Undo restored all frames to defender.")

        # Test Case 3: Test Redo (Ctrl+Y)
        print("\n--- Test Case 3: Redo class change ---")
        desc = edit_ctrl.redo()
        print(f"  Redone: {desc.encode('ascii', 'replace').decode('ascii') if desc else ''}")
        for fi in [2, 3, 4]:
            trks = store.get_frame_tracks(fi)
            det = next(d for d in trks if d.current_id == 1)
            assert det.class_id == 0 and det.class_name == "raider", (
                f"After redo, frame {fi} should be raider, got {det.class_name}"
            )
        print("  [OK] Redo reapplied raider class to frames 2, 3, 4.")

        # Test Case 4: propagate=False (single frame edit)
        print("\n--- Test Case 4: Single frame edit with propagate=False ---")
        frame_3_tracks = store.get_frame_tracks(3)
        det_id_2 = next(d for d in frame_3_tracks if d.current_id == 2)
        ok = edit_ctrl.change_class(
            frame_idx=3,
            det_idx=det_id_2.det_idx,
            old_cls_id=0,
            old_cls_name="raider",
            new_cls_id=1,
            new_cls_name="defender",
            propagate=False,
        )
        assert ok

        # Frame 3 should be defender, frame 4 should still be raider
        det_f3 = next(d for d in store.get_frame_tracks(3) if d.current_id == 2)
        det_f4 = next(d for d in store.get_frame_tracks(4) if d.current_id == 2)
        assert det_f3.class_id == 1 and det_f3.class_name == "defender"
        assert det_f4.class_id == 0 and det_f4.class_name == "raider"
        print("  [OK] Single frame edit affected only frame 3; frame 4 remained raider.")

        print("\n" + "=" * 70)
        print("ALL TESTS PASSED SUCCESSFULLY! CLASS PROPAGATION FULLY VERIFIED!")
        print("=" * 70)

    finally:
        if os.path.exists(temp_json_path):
            os.remove(temp_json_path)


if __name__ == "__main__":
    test_propagate_class_feature()
