"""
Zomo Server
FastAPI backend serving the web dashboard and providing REST + WebSocket APIs
for controlling the ZoomBot engine.
"""

import asyncio
import json
from pathlib import Path
from typing import Dict, Any, List, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Body
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from engine.config_manager import (
    load_config, save_config, load_presets, save_preset,
    get_active_messages, get_screen_presets, DEFAULT_CONFIG,
)
from engine.zoom_bot import ZoomBot

import sys
import time
from datetime import datetime

# Add docker-bots directory to sys.path
BASE_DIR = Path(__file__).resolve().parent
sys.path.append(str(BASE_DIR / "docker-bots"))

app = FastAPI(title="Zomo - Zoom Bot Automation Studio", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# ── Global State ─────────────────────────────────────────────

bot: ZoomBot | None = None
multibot_manager: Any = None
multibot_task: asyncio.Task | None = None
multibot_config: Dict[str, Any] = {}

ws_connections: List[WebSocket] = []
log_history: List[Dict[str, Any]] = []
MAX_LOG_HISTORY = 500


def multibot_log_listener(level: str, msg: str, name: str):
    """Bridge multibot logs to the WebSocket live log stream."""
    entry = {
        "timestamp": datetime.now().strftime("%H:%M:%S"),
        "level": level.lower(),
        "message": f"[{name}] {msg}",
        "bot_name": name,
        "source": "multibot",
    }
    sync_log_callback(entry)


async def broadcast_log(entry: Dict[str, Any]):
    """Send a log entry to all connected WebSocket clients."""
    log_history.append(entry)
    if len(log_history) > MAX_LOG_HISTORY:
        log_history.pop(0)

    message = json.dumps({"type": "log", "data": entry})
    disconnected = []
    for ws in ws_connections:
        try:
            await ws.send_text(message)
        except Exception:
            disconnected.append(ws)
    for ws in disconnected:
        ws_connections.remove(ws)


def sync_log_callback(entry: Dict[str, Any]):
    """Bridge sync bot callbacks to async broadcast."""
    try:
        loop = asyncio.get_running_loop()
        # Safe to schedule from any thread — call_soon_threadsafe is thread-safe
        loop.call_soon_threadsafe(asyncio.ensure_future, broadcast_log(entry))
    except RuntimeError:
        # No running event loop (e.g. called from a non-async context), just store
        log_history.append(entry)


# ── Routes: Dashboard ────────────────────────────────────────

@app.get("/")
async def serve_dashboard():
    """Serve the main dashboard HTML."""
    return FileResponse(str(BASE_DIR / "static" / "index.html"))


# ── Routes: Bot Control ─────────────────────────────────────

@app.post("/api/bot/start")
async def start_bot(payload: Dict[str, Any] = Body(default={})):
    """Start the Playwright Web Client bot engine."""
    global bot, multibot_manager, multibot_task
    payload = payload or {}
    meeting_url = payload.get("meeting_url", "").strip()
    if not meeting_url:
        config = load_config()
        meeting_url = config.get("meeting_url", "").strip()

    if not meeting_url:
        return JSONResponse(
            {"status": "error", "message": "Please enter a Zoom meeting URL or Meeting ID in the Meeting Setup tab."},
            status_code=400,
        )

    payload["meeting_url"] = meeting_url
    if "bot_count" not in payload:
        payload["bot_count"] = 1

    return await start_multibot(payload)


@app.post("/api/bot/stop")
async def stop_bot():
    """Stop all running bot engines."""
    global bot, multibot_manager, multibot_task
    if multibot_manager or (multibot_task and not multibot_task.done()):
        return await stop_multibot()
    if bot:
        bot.stop()
        return {"status": "ok", "message": "Bot stopped."}
    return JSONResponse({"status": "error", "message": "No bot is running."}, status_code=400)


@app.post("/api/bot/pause")
async def pause_bot():
    """Pause the ZoomBot engine."""
    global bot
    if multibot_manager:
        return {"status": "ok", "message": "Multi-bot farm is running."}
    if not bot:
        return JSONResponse({"status": "error", "message": "No bot is running."}, status_code=400)
    bot.pause()
    return {"status": "ok", "message": "Bot paused."}


@app.post("/api/bot/resume")
async def resume_bot():
    """Resume the ZoomBot engine."""
    global bot
    if not bot:
        return JSONResponse({"status": "error", "message": "No bot is running."}, status_code=400)
    bot.resume()
    return {"status": "ok", "message": "Bot resumed."}


@app.get("/api/bot/status")
async def bot_status():
    """Get current bot status."""
    global bot, multibot_manager, multibot_task
    if multibot_manager and multibot_task and not multibot_task.done():
        mb_stat = await multibot_status()
        return {
            "state": "active" if mb_stat.get("is_running") else "stopped",
            "elapsed": mb_stat.get("elapsed", 0),
            "messages_sent": mb_stat.get("total_messages_sent", 0),
            "camera_on": True,
            "next_chat_in": 15,
            "next_cam_in": 0,
            "simulation_mode": False,
            "bot_count": mb_stat.get("bot_count", 0),
        }
    if bot:
        return bot.get_status()
    return {
        "state": "idle",
        "elapsed": 0,
        "messages_sent": 0,
        "camera_on": False,
        "next_chat_in": 0,
        "next_cam_in": 0,
        "simulation_mode": False,
    }


# ── Routes: Multi-Bot Control ────────────────────────────────

@app.post("/api/multibot/start")
async def start_multibot(payload: Dict[str, Any]):
    """Launch multi-bot Playwright farm with user parameters."""
    global multibot_manager, multibot_task, multibot_config
    if multibot_task and not multibot_task.done():
        return JSONResponse({"status": "error", "message": "Multi-bot farm is already running."}, status_code=400)

    meeting_url = payload.get("meeting_url", "").strip()
    if not meeting_url:
        return JSONResponse({"status": "error", "message": "Please enter a valid Zoom meeting URL or ID."}, status_code=400)

    # Normalize meeting URL / ID if needed
    if meeting_url.isdigit() or (len(meeting_url) in (9, 10, 11) and not meeting_url.startswith("http")):
        meeting_url = f"https://zoom.us/j/{meeting_url}"

    try:
        from zoom_human_bots import BotManager, set_log_callback
        from types import SimpleNamespace

        bot_count = max(1, min(50, int(payload.get("bot_count", 5))))
        chat_min = max(2, int(payload.get("chat_min", 15)))
        chat_max = max(chat_min, int(payload.get("chat_max", 45)))
        join_delay_min = max(1, int(payload.get("join_delay_min", 5)))
        join_delay_max = max(join_delay_min, int(payload.get("join_delay_max", 15)))
        headless = bool(payload.get("headless", True))
        custom_msgs = payload.get("custom_messages", [])

        args = SimpleNamespace(
            meeting_url=meeting_url,
            count=bot_count,
            chat_min=chat_min,
            chat_max=chat_max,
            join_delay_min=join_delay_min,
            join_delay_max=join_delay_max,
            video_delay_min=1,
            video_delay_max=5,
            timeout=int(payload.get("timeout", 3600)),
            headless=headless,
            no_headless=not headless,
            mock_video=str(BASE_DIR / "docker-bots" / "mock_face.y4m"),
            avatar_dir=str(BASE_DIR / "docker-bots" / "avatars"),
            video_pool=str(BASE_DIR / "docker-bots" / "video_pool"),
            per_bot_browser=bool(payload.get("per_bot_browser", False)),
            names_file=None,
            messages_file=None,
        )

        set_log_callback(multibot_log_listener)
        multibot_manager = BotManager(args)
        if custom_msgs:
            multibot_manager.custom_messages = custom_msgs

        multibot_config = {
            "meeting_url": meeting_url,
            "bot_count": bot_count,
            "chat_min": chat_min,
            "chat_max": chat_max,
            "started_at": time.time(),
        }

        multibot_task = asyncio.create_task(multibot_manager.run())

        # Auto-cleanup when the farm finishes naturally
        def _on_farm_done(task: asyncio.Task):
            global multibot_manager, multibot_task
            if task is multibot_task:
                multibot_manager = None
                multibot_task = None

        multibot_task.add_done_callback(_on_farm_done)
        return {"status": "ok", "message": f"🚀 Multi-bot farm launched with {bot_count} bots!"}
    except Exception as e:
        return JSONResponse({"status": "error", "message": f"Failed to start multi-bot farm: {e}"}, status_code=500)


@app.post("/api/multibot/stop")
async def stop_multibot():
    """Stop all running multi-bots."""
    global multibot_manager, multibot_task
    if not multibot_manager and (not multibot_task or multibot_task.done()):
        return JSONResponse({"status": "error", "message": "No multi-bot farm is running."}, status_code=400)

    try:
        if multibot_manager:
            await multibot_manager.shutdown()
        if multibot_task and not multibot_task.done():
            multibot_task.cancel()

        multibot_manager = None
        multibot_task = None
        return {"status": "ok", "message": "⏹ Multi-bot farm stopped."}
    except Exception as e:
        return JSONResponse({"status": "error", "message": f"Error stopping farm: {e}"}, status_code=500)


@app.get("/api/multibot/status")
async def multibot_status():
    """Get current status of multi-bot farm and individual bots."""
    global multibot_manager, multibot_task, multibot_config
    if not multibot_manager or not multibot_task:
        return {
            "is_running": False,
            "bot_count": 0,
            "active_count": 0,
            "elapsed": 0,
            "total_messages": 0,
            "bots": []
        }

    is_running = not multibot_task.done()
    elapsed = round(time.time() - multibot_config.get("started_at", time.time()), 1) if is_running else 0
    bot_list = []
    total_msgs = 0
    active_cnt = 0

    if hasattr(multibot_manager, "bots"):
        for b in multibot_manager.bots:
            msgs = getattr(b, "msgs_sent", 0)
            total_msgs += msgs
            is_alive = getattr(b, "alive", False)
            if is_alive:
                active_cnt += 1
            bot_list.append({
                "name": b.name,
                "msgs_sent": msgs,
                "alive": is_alive,
                "index": getattr(b, "index", 0),
            })

    return {
        "is_running": is_running,
        "bot_count": len(bot_list) if bot_list else multibot_config.get("bot_count", 0),
        "active_count": active_cnt,
        "elapsed": elapsed,
        "total_messages": total_msgs,
        "bots": bot_list,
    }


# ── Routes: Configuration ───────────────────────────────────

@app.get("/api/config")
async def get_config():
    """Get current configuration."""
    return load_config()


@app.post("/api/config")
async def update_config(config: Dict[str, Any]):
    """Update and save configuration. Hot-updates running bot."""
    save_config(config)
    if bot and bot.state.value not in ("idle", "stopped", "error"):
        bot.update_config(config)
    return {"status": "ok", "message": "Configuration saved."}


@app.get("/api/config/defaults")
async def get_defaults():
    """Get default configuration values."""
    return DEFAULT_CONFIG


# ── Routes: Presets ──────────────────────────────────────────

@app.get("/api/presets")
async def get_presets():
    """Get all message presets."""
    return load_presets()


@app.post("/api/presets/{name}")
async def create_preset(name: str, body: Dict[str, Any]):
    """Create or update a message preset."""
    messages = body.get("messages", [])
    description = body.get("description", "")
    save_preset(name, messages, description)
    return {"status": "ok", "message": f"Preset '{name}' saved."}


@app.get("/api/presets/active-messages")
async def get_active_msgs():
    """Get the currently active message list."""
    config = load_config()
    return {"messages": get_active_messages(config)}


# ── Routes: Calibration ─────────────────────────────────────

@app.get("/api/calibrator/screen-presets")
async def screen_presets():
    """Get coordinate presets for common screen resolutions."""
    return get_screen_presets()


@app.get("/api/calibrator/mouse-position")
async def mouse_position():
    """Get current mouse cursor position."""
    import pyautogui
    pos = pyautogui.position()
    return {"x": pos.x, "y": pos.y}


# ── Routes: Logs ─────────────────────────────────────────────

@app.get("/api/logs")
async def get_logs():
    """Get recent log history."""
    return {"logs": log_history}


@app.delete("/api/logs")
async def clear_logs():
    """Clear log history."""
    log_history.clear()
    return {"status": "ok", "message": "Logs cleared."}


# ── WebSocket: Live Logs ─────────────────────────────────────

@app.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket):
    """WebSocket endpoint for real-time log streaming."""
    await websocket.accept()
    ws_connections.append(websocket)

    # Send existing log history on connect
    try:
        for entry in log_history[-50:]:
            await websocket.send_text(json.dumps({"type": "log", "data": entry}))
    except Exception:
        pass

    try:
        while True:
            # Keep connection alive, listen for client messages
            data = await websocket.receive_text()
            # Client can send commands via WS too
            try:
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        pass
    finally:
        if websocket in ws_connections:
            ws_connections.remove(websocket)


if __name__ == "__main__":
    import os
    port = int(os.getenv("PORT", "8081"))
    print("\n  🚀 Zomo - Zoom Bot Automation Studio")
    print("  ────────────────────────────────────")
    print(f"  Dashboard: http://localhost:{port}")
    print(f"  API Docs:  http://localhost:{port}/docs\n")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
