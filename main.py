"""Entry point for the Kabaddi Ground Truth Track Editor.

Usage:
    python tools/ground_truth_editor/main.py
    python tools/ground_truth_editor/main.py path/to/project.kgt
"""
from __future__ import annotations

import sys
import os
import traceback
from pathlib import Path

# Allow imports from this package root
_HERE = Path(__file__).parent
sys.path.insert(0, str(_HERE))

# Crash log next to this file so we always find it
_CRASH_LOG = Path(__file__).parent / "gt_editor_crash.log"


def main():
    try:
        _run()
    except Exception:
        msg = traceback.format_exc()
        print(msg, file=sys.stderr)
        try:
            _CRASH_LOG.write_text(msg)
            print(f"\nCrash log written to: {_CRASH_LOG}", file=sys.stderr)
        except Exception:
            pass
        sys.exit(1)


def _run():
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")

    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QFont
    from PySide6.QtCore import QTimer

    app = QApplication(sys.argv)
    app.setApplicationName("GTTrackEditor")
    app.setOrganizationName("KabaddiBTP")
    app.setApplicationDisplayName("Kabaddi GT Track Editor")

    # Apply stylesheet from saved user preferences
    from utils.settings import AppSettings
    from utils.colors import get_app_stylesheet
    settings = AppSettings()
    app.setStyleSheet(get_app_stylesheet(settings.get_theme()))

    font = QFont("Segoe UI", 10)
    app.setFont(font)

    from ui.main_window import MainWindow
    window = MainWindow()
    window.show()

    # If a tracks.json was passed as argument, open it
    if len(sys.argv) > 1:
        project_path = sys.argv[1]
        if Path(project_path).exists():
            QTimer.singleShot(300, lambda: window.open_json(project_path))
        else:
            print(f"[WARN] File not found: {project_path}", file=sys.stderr)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()

