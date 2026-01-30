# ESPRESSO ☕

**The calm before the brainstorm.**

A minimalist task management app with focus mode, timers, and project organization.

![ESPRESSO](espresso-icon.png)

## Quick Start

### Prerequisites
- Python 3.x
- A modern web browser

### Launch the App

**macOS:** Double-click `launch.command`

**Or manually:**
```bash
python3 run.py
```

The app opens automatically at `http://localhost:8000`

## Features

### Task Management
- **Projects** — Organize tasks into projects (click the project name to switch/add)
- **Drag & drop** — Reorder tasks by dragging the handle (≡)
- **States** — Active, Paused (with blockers), Done (today/this week)
- **Color tags** — Click the dot next to any task to color-code it
- **Estimates** — Click the time to set estimates in minutes

### Focus Mode
- Click the **◎** button to focus on your top task
- **Ctrl+click** (Cmd+click on Mac) any task to focus on it specifically
- Built-in timer synced to your estimate
- Notes field for the focused task

### Dependencies
- Click the **link icon** on any task to set dependencies
- Dependent tasks auto-pause until their blocker is done
- Move tasks between projects from the same modal

### Other
- **Compact mode** — Toggle with **▤** for a denser view
- **Dark/Light theme** — Toggle with **☀︎ / ☾**
- **Force save** — Click **💾** to force-sync and take ownership
- **Auto-save** — Changes save automatically to `state.json`

## Keyboard Shortcuts

| Action | Shortcut |
|--------|----------|
| Focus on any task | Ctrl+click (Cmd+click) |
| Submit new task | Enter |
| Cancel editing | Escape |

## Data Storage

Tasks are stored locally in `state.json`. To backup your data, copy this file.

## License

MIT
