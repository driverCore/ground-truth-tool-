# Kabaddi Ground Truth Track Editor

An interactive PyQt/PySide6 desktop application for viewing, editing, merging, re-assigning, and refining ByteTrack object detection tracks (`tracks.json`) over video frame sequences.

---

## Features

- **Dynamic Bounding Box Overlay**: Interactive canvas displaying bounding box tracks over video frames.
- **In-Place ID Editing**: Single-click on any track ID tag or press `C` to edit track IDs directly in place.
- **Fast Frame Navigation**:
  - `A` / `D` keys or `Left` / `Right` arrow keys to step backward / forward.
  - Double-click **Left** mouse button anywhere on the screen to go to the **previous frame**.
  - Double-click **Right** mouse button anywhere on the screen to go to the **next frame**.
  - `A` and `D` keypresses inside the ID editor automatically save the ID and navigate frames without typing letters.
- **Track Management**:
  - Hover or select any bounding box to reveal a red `×` button for quick deletion.
  - Track panel for listing active tracks, hiding/showing tracks, and merging tracks across frames.
- **Dark / Light Theme**: Instant toggle between sleek Dark Mode and high-contrast Light Mode via View menu, top-right corner button, or `Ctrl+T`.
- **Undo / Redo Support**: Full history stack (`Ctrl+Z` / `Ctrl+Y`).
- **Autosave & Session Recovery**: Automatic saving and crash recovery.

---

## Installation

1. Clone this repository:
   ```bash
   git clone https://github.com/joyboyAT/ground-truth-tool-.git
   cd ground-truth-tool-
   ```

2. Install requirements:
   ```bash
   pip install -r requirements.txt
   ```

---

## Usage

Launch the Ground Truth Track Editor:
```bash
python main.py
```

Or pass a `tracks.json` file directly:
```bash
python main.py path/to/bytetrack_folder/tracks.json
```

---

## Controls & Shortcuts Summary

| Shortcut / Action | Function |
| :--- | :--- |
| `A` / `←` | Step backward 1 frame |
| `D` / `→` | Step forward 1 frame |
| Double-click **Left Mouse** | Step backward 1 frame |
| Double-click **Right Mouse** | Step forward 1 frame |
| `Space` | Play / Pause video sequence |
| `W` | Toggle Draw Bounding Box mode |
| `C` or Single-click ID | Edit track ID in-place |
| Click red `×` on box | Delete bounding box |
| `Delete` | Delete selected bounding box |
| `Ctrl + T` | Toggle Dark / Light theme mode |
| `Ctrl + Z` | Undo last edit |
| `Ctrl + Y` | Redo edit |
| `Ctrl + S` | Save `tracks.json` |
