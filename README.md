# 🚀 Zomo — Zoom Bot Automation Studio

A sleek, modern web dashboard + Python automation engine for controlling Zoom Desktop Client with virtual camera support (OBS), randomized chat messages, and human-like behavior simulation.

## Features

- **Web Control Dashboard** — Dark-mode glassmorphism UI with real-time metrics, live WebSocket logs, and one-click bot controls
- **Smart Timing** — Configurable chat intervals, camera delays, mouse jitter, and humanized behavior
- **Dual Execution Modes** — Keyboard shortcuts (`Alt+V`, `Alt+H`) or screen coordinate clicking
- **Chat Message Presets** — Casual, Formal, Class, and Standup presets with full editor
- **Visual Coordinate Calibrator** — Live mouse tracker + resolution presets for 1080p/1440p/4K
- **OBS Virtual Camera Guide** — Step-by-step setup instructions
- **Simulation Mode** — Dry run without sending actual clicks

## Quick Start

### 1. Install Dependencies

```bash
cd d:\myproj\zomo
pip install -r requirements.txt
```

### 2. Start the Server

```bash
python server.py
```

### 3. Open Dashboard

Navigate to **http://localhost:8000** in your browser.

### 4. Configure & Run

1. Adjust timing sliders and execution settings
2. Select a chat message preset
3. (Optional) Enable **Simulation Mode** for a dry run
4. Click **▶ Start Bot**

## OBS Virtual Camera Setup

1. Install [OBS Studio](https://obsproject.com/)
2. Create a scene with a video/image source
3. Click **Start Virtual Camera** in OBS Controls
4. In Zoom → Settings → Video, select **"OBS Virtual Camera"**

## Project Structure

```
zomo/
├── engine/
│   ├── __init__.py
│   ├── config_manager.py    # JSON config loader/saver
│   └── zoom_bot.py          # ZoomBot engine with state machine
├── server.py                # FastAPI backend (REST + WebSocket)
├── static/
│   ├── index.html           # Dashboard SPA
│   ├── css/main.css          # Design system
│   └── js/app.js             # Dashboard logic
├── presets/
│   └── default_messages.json # Chat message presets
├── requirements.txt
└── README.md
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET`  | `/` | Dashboard |
| `POST` | `/api/bot/start` | Start bot |
| `POST` | `/api/bot/stop` | Stop bot |
| `POST` | `/api/bot/pause` | Pause bot |
| `POST` | `/api/bot/resume` | Resume bot |
| `GET`  | `/api/bot/status` | Bot status |
| `GET/POST` | `/api/config` | Get/save config |
| `GET`  | `/api/presets` | List presets |
| `WS`   | `/ws/logs` | Live log stream |

## Requirements

- Python 3.7+
- Zoom Desktop Client (installed & logged in)
- OBS Studio (for virtual camera)
- Windows OS (PyAutoGUI desktop control)
