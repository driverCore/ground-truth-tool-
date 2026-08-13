"""Persistent QSettings wrapper for the GT Track Editor."""
from PySide6.QtCore import QSettings

APP_ORG  = "KabaddiBTP"
APP_NAME = "GTTrackEditor"
MAX_RECENT = 10


class AppSettings:
    def __init__(self):
        self._s = QSettings(APP_ORG, APP_NAME)

    # ── Recent projects ────────────────────────────────────────────────────
    def get_recent_projects(self) -> list[str]:
        v = self._s.value("recent_projects", [])
        return v if isinstance(v, list) else []

    def add_recent_project(self, path: str):
        recent = self.get_recent_projects()
        if path in recent:
            recent.remove(path)
        recent.insert(0, path)
        self._s.setValue("recent_projects", recent[:MAX_RECENT])

    def remove_recent_project(self, path: str):
        recent = self.get_recent_projects()
        if path in recent:
            recent.remove(path)
            self._s.setValue("recent_projects", recent)

    def clear_recent(self):
        self._s.setValue("recent_projects", [])

    # ── Window state ───────────────────────────────────────────────────────
    def save_window(self, geometry, state):
        self._s.setValue("window_geometry", geometry)
        self._s.setValue("window_state", state)

    def load_window(self):
        return (self._s.value("window_geometry"),
                self._s.value("window_state"))

    # ── Playback preferences ───────────────────────────────────────────────
    def get_playback_speed(self) -> float:
        return float(self._s.value("playback_speed", 1.0))

    def set_playback_speed(self, speed: float):
        self._s.setValue("playback_speed", speed)

    # ── Autosave ───────────────────────────────────────────────────────────
    def get_autosave_interval(self) -> int:
        return int(self._s.value("autosave_interval", 30))

    def set_autosave_interval(self, secs: int):
        self._s.setValue("autosave_interval", secs)

    # ── Last opened directory ──────────────────────────────────────────────
    def get_last_dir(self) -> str:
        return str(self._s.value("last_dir", ""))

    def set_last_dir(self, path: str):
        self._s.setValue("last_dir", path)

    # ── Session recovery ───────────────────────────────────────────────────
    def set_crash_recovery(self, project_path: str):
        self._s.setValue("crash_recovery_project", project_path)

    def get_crash_recovery(self) -> str:
        return str(self._s.value("crash_recovery_project", ""))

    def clear_crash_recovery(self):
        self._s.remove("crash_recovery_project")
