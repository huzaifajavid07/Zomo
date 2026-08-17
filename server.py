"""
Zomo Server
FastAPI backend serving the web dashboard and providing REST + WebSocket APIs
for controlling the ZoomBot engine.
"""

import asyncio
import json
from pathlib import Path
from typing import Dict, Any, List, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Body, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from engine.config_manager import (
    load_config, save_config, load_presets, save_preset,
    get_active_messages, get_screen_presets, DEFAULT_CONFIG,
)
from engine.data_store import (
    get_all_users, get_user_by_id, authenticate_user, create_user, update_user,
    delete_user, get_all_meetings, save_meeting, update_meeting,
    delete_meeting, mark_active_meetings_as,
)
from engine.zoom_bot import ZoomBot

import os
import sys
import time
from datetime import datetime

# Add docker-bots directory to sys.path
BASE_DIR = Path(__file__).resolve().parent
sys.path.append(str(BASE_DIR / "docker-bots"))

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Capture main running asyncio loop for thread-safe cross-thread callbacks."""
    global main_loop
    main_loop = asyncio.get_running_loop()
    yield

app = FastAPI(title="Zomo - Zoom Bot Automation Studio", version="1.0.0", lifespan=lifespan)

allowed_origins_env = os.getenv("ALLOWED_ORIGINS", "http://localhost:8081,http://127.0.0.1:8081,http://localhost:3000,http://127.0.0.1:3000")
allowed_origins = [origin.strip() for origin in allowed_origins_env.split(",") if origin.strip()]
if "*" in allowed_origins_env.split(","):
    allowed_origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files & feed previews
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

(BASE_DIR / "data" / "feeds").mkdir(parents=True, exist_ok=True)
app.mount("/feeds", StaticFiles(directory=str(BASE_DIR / "data" / "feeds")), name="feeds")

# ── Global State ─────────────────────────────────────────────

bot: ZoomBot | None = None
multibot_manager: Any = None
multibot_task: asyncio.Task | None = None
multibot_config: Dict[str, Any] = {}

ws_connections: List[WebSocket] = []
log_history: List[Dict[str, Any]] = []
MAX_LOG_HISTORY = 500

main_loop: Optional[asyncio.AbstractEventLoop] = None


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
    """Bridge sync/async bot callbacks safely across threads to WebSocket clients."""
    global main_loop
    try:
        loop = main_loop or asyncio.get_running_loop()
        if loop and loop.is_running():
            asyncio.run_coroutine_threadsafe(broadcast_log(entry), loop)
        else:
            log_history.append(entry)
            if len(log_history) > MAX_LOG_HISTORY:
                log_history.pop(0)
    except Exception:
        log_history.append(entry)
        if len(log_history) > MAX_LOG_HISTORY:
            log_history.pop(0)


# ── Routes: Pages ───────────────────────────────────────────

@app.get("/")
@app.get("/dashboard")
async def serve_dashboard():
    """Serve the main dashboard HTML."""
    return FileResponse(str(BASE_DIR / "static" / "index.html"))


@app.get("/login")
async def serve_login():
    """Serve the login HTML page."""
    return FileResponse(str(BASE_DIR / "static" / "login.html"))


@app.get("/admin")
async def serve_admin():
    """Serve the user management admin HTML page."""
    return FileResponse(str(BASE_DIR / "static" / "admin.html"))


# ── User Resolution Helper ──────────────────────────────────

def resolve_request_user(request: Request) -> Dict[str, Any]:
    """Resolve calling user from headers or auth token."""
    user_id = request.headers.get("x-user-id")
    user_email = request.headers.get("x-user-email")
    user_role = request.headers.get("x-user-role")

    if user_id:
        u = get_user_by_id(user_id)
        if u:
            return u
        return {
            "id": str(user_id),
            "email": user_email or "user@example.com",
            "name": "User",
            "role": "superadmin" if user_role in ("superadmin", "admin") else "user"
        }

    return {"id": "1", "email": "admin@example.com", "name": "Super Admin", "role": "superadmin"}


# ── Routes: Auth & Users ─────────────────────────────────────

@app.post("/api/auth/login")
async def api_login(payload: Dict[str, Any] = Body(...)):
    """Authenticate user with email and password."""
    email = payload.get("email", "").strip()
    password = payload.get("password", "")
    if not email or not password:
        return JSONResponse({"status": "error", "message": "Email and password are required."}, status_code=400)

    user = authenticate_user(email, password)
    if not user:
        return JSONResponse({"status": "error", "message": "Invalid email or password."}, status_code=401)

    return {
        "status": "ok",
        "message": "Login successful",
        "user": user,
        "token": f"zomo_token_{user.get('id')}_{int(time.time())}"
    }


@app.get("/api/auth/me")
async def api_me(request: Request):
    """Return default/current authenticated session info."""
    user = resolve_request_user(request)
    return {"status": "ok", "user": user}


@app.get("/api/users")
async def list_users(request: Request):
    """List all registered users (Superadmin only)."""
    caller = resolve_request_user(request)
    if caller.get("role") not in ("superadmin", "admin"):
        return JSONResponse({"status": "error", "message": "Access denied. Superadmin access required."}, status_code=403)
    return {"status": "ok", "users": get_all_users()}


@app.post("/api/users")
async def add_user(request: Request, payload: Dict[str, Any] = Body(...)):
    """Create a new user (Superadmin only)."""
    caller = resolve_request_user(request)
    if caller.get("role") not in ("superadmin", "admin"):
        return JSONResponse({"status": "error", "message": "Access denied. Superadmin access required."}, status_code=403)

    try:
        new_user = create_user(payload)
        return {"status": "ok", "message": "User created successfully.", "user": new_user}
    except ValueError as ve:
        return JSONResponse({"status": "error", "message": str(ve)}, status_code=400)
    except Exception as e:
        return JSONResponse({"status": "error", "message": f"Failed to create user: {e}"}, status_code=500)


@app.put("/api/users/{user_id}")
async def edit_user(user_id: str, request: Request, payload: Dict[str, Any] = Body(...)):
    """Update an existing user (Superadmin only)."""
    caller = resolve_request_user(request)
    if caller.get("role") not in ("superadmin", "admin"):
        return JSONResponse({"status": "error", "message": "Access denied. Superadmin access required."}, status_code=403)

    updated = update_user(user_id, payload)
    if not updated:
        return JSONResponse({"status": "error", "message": "User not found."}, status_code=404)
    return {"status": "ok", "message": "User updated successfully.", "user": updated}


@app.delete("/api/users/{user_id}")
async def remove_user(user_id: str, request: Request):
    """Delete a user (Superadmin only)."""
    caller = resolve_request_user(request)
    if caller.get("role") not in ("superadmin", "admin"):
        return JSONResponse({"status": "error", "message": "Access denied. Superadmin access required."}, status_code=403)

    success = delete_user(user_id)
    if not success:
        return JSONResponse({"status": "error", "message": "User not found."}, status_code=404)
    return {"status": "ok", "message": "User deleted successfully."}


# ── Routes: Meetings (User-Isolated) ─────────────────────────

@app.get("/api/meetings")
async def list_meetings(request: Request):
    """List meetings with strict user isolation (Superadmin sees all, user sees only own)."""
    caller = resolve_request_user(request)
    is_super = caller.get("role") in ("superadmin", "admin")
    meetings = get_all_meetings(user_id=caller.get("id"), is_superadmin=is_super)

    # Sync with actual running state
    is_mb_running = bool(multibot_task and not multibot_task.done())
    is_bot_running = bool(bot and bot.state.value not in ("idle", "stopped", "error"))

    if not (is_mb_running or is_bot_running):
        for m in meetings:
            if m.get("status") == "active":
                m["status"] = "completed"

    return {"status": "ok", "meetings": meetings}


@app.post("/api/meetings")
async def create_meeting_record(request: Request, payload: Dict[str, Any] = Body(...)):
    """Create or record a meeting tagged to current user."""
    caller = resolve_request_user(request)
    meeting = save_meeting(payload, user_id=caller.get("id"), user_email=caller.get("email"))
    return {"status": "ok", "message": "Meeting saved.", "meeting": meeting}


@app.put("/api/meetings/{meeting_id}")
async def edit_meeting_record(meeting_id: str, request: Request, payload: Dict[str, Any] = Body(...)):
    """Update meeting parameters (with ownership check)."""
    caller = resolve_request_user(request)
    is_super = caller.get("role") in ("superadmin", "admin")
    updated = update_meeting(meeting_id, payload, user_id=caller.get("id"), is_superadmin=is_super)
    if not updated:
        return JSONResponse({"status": "error", "message": "Meeting not found or unauthorized."}, status_code=404)
    return {"status": "ok", "message": "Meeting updated.", "meeting": updated}


@app.delete("/api/meetings/{meeting_id}")
async def remove_meeting_record(meeting_id: str, request: Request):
    """Delete a meeting record (with ownership check)."""
    caller = resolve_request_user(request)
    is_super = caller.get("role") in ("superadmin", "admin")
    success = delete_meeting(meeting_id, user_id=caller.get("id"), is_superadmin=is_super)
    if not success:
        return JSONResponse({"status": "error", "message": "Meeting not found or unauthorized."}, status_code=404)
    return {"status": "ok", "message": "Meeting deleted."}


@app.post("/api/meetings/{meeting_id}/stop")
async def stop_specific_meeting(meeting_id: str, request: Request):
    """Stop active meeting bot execution (with ownership check)."""
    caller = resolve_request_user(request)
    is_super = caller.get("role") in ("superadmin", "admin")
    update_meeting(meeting_id, {"status": "stopped"}, user_id=caller.get("id"), is_superadmin=is_super)
    return await stop_bot()


# ── Routes: Bot Control ─────────────────────────────────────

@app.post("/api/bot/start")
async def start_bot(request: Request, payload: Dict[str, Any] = Body(default={})):
    """Start Desktop ZoomBot or Playwright Web Farm based on payload / config."""
    global bot, multibot_manager, multibot_task
    payload = payload or {}
    config = load_config()
    caller = resolve_request_user(request)

    engine_type = payload.get("engine") or config.get("execution", {}).get("engine", "desktop")
    bot_count = int(payload.get("bot_count", 1))
    meeting_url = payload.get("meeting_url", "").strip() or config.get("meeting_url", "").strip()

    # Record active meeting tagged to current user
    save_meeting({
        "meetingId": payload.get("meetingId") or meeting_url or "Desktop Bot Session",
        "botCount": bot_count,
        "timeout": int(payload.get("timeout", 1800)) // 60 if int(payload.get("timeout", 1800)) > 120 else int(payload.get("timeout", 30)),
        "vcType": payload.get("vcType", "zoom"),
        "status": "active",
        "startTime": datetime.now().strftime("%H:%M"),
    }, user_id=caller.get("id"), user_email=caller.get("email"))

    # Web Client Multi-Bot Farm Dispatch
    if engine_type == "web_farm" or bot_count >= 1 or meeting_url:
        if not meeting_url:
            return JSONResponse(
                {"status": "error", "message": "Please enter a Zoom meeting URL or Meeting ID in the Meeting Setup tab."},
                status_code=400,
            )
        payload["meeting_url"] = meeting_url
        payload["bot_count"] = bot_count
        return await start_multibot(payload)

    # PyAutoGUI Desktop Client ZoomBot Dispatch
    if bot and bot.state.value not in ("idle", "stopped", "error"):
        return JSONResponse({"status": "error", "message": "Desktop bot is already running."}, status_code=400)

    try:
        bot = ZoomBot(config=config, log_callback=sync_log_callback)
        bot.start()
        return {"status": "ok", "message": "🚀 Desktop ZoomBot engine started successfully!"}
    except Exception as e:
        return JSONResponse({"status": "error", "message": f"Failed to start Desktop bot: {e}"}, status_code=500)


@app.post("/api/bot/stop")
async def stop_bot():
    """Stop all running bot engines (Desktop or Multi-bot farm)."""
    global bot, multibot_manager, multibot_task
    stopped = False
    messages = []

    mark_active_meetings_as("stopped")

    if multibot_manager or (multibot_task and not multibot_task.done()):
        await stop_multibot()
        stopped = True
        messages.append("Multi-bot farm stopped.")

    if bot and bot.state.value not in ("idle", "stopped"):
        bot.stop()
        stopped = True
        messages.append("Desktop bot stopped.")

    if stopped:
        return {"status": "ok", "message": " ".join(messages)}
    return JSONResponse({"status": "error", "message": "No bot is currently running."}, status_code=400)


@app.post("/api/bot/pause")
async def pause_bot():
    """Pause the ZoomBot engine."""
    global bot, multibot_manager
    if multibot_manager:
        return {"status": "ok", "message": "Multi-bot farm is active."}
    if not bot or bot.state.value in ("idle", "stopped", "error"):
        return JSONResponse({"status": "error", "message": "No bot is running."}, status_code=400)
    bot.pause()
    return {"status": "ok", "message": "Desktop bot paused."}


@app.post("/api/bot/resume")
async def resume_bot():
    """Resume the ZoomBot engine."""
    global bot
    if not bot or bot.state.value not in ("paused",):
        return JSONResponse({"status": "error", "message": "No paused desktop bot found."}, status_code=400)
    bot.resume()
    return {"status": "ok", "message": "Desktop bot resumed."}


@app.get("/api/bot/status")
async def bot_status():
    """Get current bot status."""
    global bot, multibot_manager, multibot_task
    if multibot_manager and multibot_task and not multibot_task.done():
        mb_stat = await multibot_status()
        return {
            "engine": "web_farm",
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
        stat = bot.get_status()
        stat["engine"] = "desktop"
        return stat
    return {
        "engine": "idle",
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

    password = payload.get("password") or payload.get("passcode") or ""
    # Normalize meeting URL / ID if needed
    if meeting_url.isdigit() or (len(meeting_url) in (9, 10, 11) and not meeting_url.startswith("http")):
        meeting_url = f"https://zoom.us/j/{meeting_url}"
    if password and "pwd=" not in meeting_url:
        sep = "&" if "?" in meeting_url else "?"
        meeting_url = f"{meeting_url}{sep}pwd={password}"

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
            video_delay_min=int(payload.get("video_delay_min", 10)),
            video_delay_max=int(payload.get("video_delay_max", 45)),
            video_on_min=int(payload.get("video_on_min", 3)),
            video_on_max=int(payload.get("video_on_max", 5)),
            video_off_min=int(payload.get("video_off_min", 60)),
            video_off_max=int(payload.get("video_off_max", 240)),
            timeout=int(payload.get("timeout", 3600)),
            headless=headless,
            no_headless=not headless,
            mock_video=str(BASE_DIR / "docker-bots" / "mock_face.y4m"),
            dataset_dir=str(payload.get("dataset_dir") or (BASE_DIR / "docker-bots" / "facial_dataset")),
            max_active_video=int(payload.get("max_active_video", 50)),
            video_ratio=float(payload.get("video_ratio", 1.0)),
            video_cycle_interval=int(payload.get("video_cycle_interval", 0)),
            avatar_dir=str(BASE_DIR / "docker-bots" / "avatars"),
            video_pool=str(BASE_DIR / "docker-bots" / "video_pool"),
            per_bot_browser=bool(payload.get("per_bot_browser", True)),
            auto_replace=bool(payload.get("auto_replace", True)),
            names_file=payload.get("names_file"),
            messages_file=payload.get("messages_file"),
        )

        set_log_callback(multibot_log_listener)
        multibot_manager = BotManager(args)
        if custom_msgs:
            multibot_manager.custom_messages = custom_msgs

        multibot_config = {
            "meeting_url": meeting_url,
            "bot_count": bot_count,
            "max_active_video": int(payload.get("max_active_video", 2)),
            "video_ratio": float(payload.get("video_ratio", 0.2)),
            "chat_min": chat_min,
            "chat_max": chat_max,
            "started_at": time.time(),
        }

        multibot_task = asyncio.create_task(multibot_manager.run())

        # Auto-cleanup when the farm finishes naturally and catch background exceptions
        def _on_farm_done(task: asyncio.Task):
            global multibot_manager, multibot_task
            try:
                exc = task.exception()
                if exc:
                    print(f"[ERROR] Multi-bot farm background task failed: {exc}", flush=True)
                    multibot_log_listener("ERR", f"Multi-bot farm crashed: {exc}", "SERVER")
            except (asyncio.CancelledError, asyncio.InvalidStateError):
                pass
            if task is multibot_task:
                multibot_manager = None
                multibot_task = None

        multibot_task.add_done_callback(_on_farm_done)
        return {"status": "ok", "message": f"🚀 Multi-bot farm launched with {bot_count} bots!"}
    except Exception as e:
        return JSONResponse({"status": "error", "message": f"Failed to start multi-bot farm: {e}"}, status_code=500)


@app.post("/api/multibot/stop")
async def stop_multibot():
    """Stop all running multi-bots gracefully."""
    global multibot_manager, multibot_task
    if not multibot_manager and (not multibot_task or multibot_task.done()):
        return JSONResponse({"status": "error", "message": "No multi-bot farm is running."}, status_code=400)

    try:
        if multibot_manager:
            await multibot_manager.shutdown()
        if multibot_task and not multibot_task.done():
            multibot_task.cancel()
            try:
                await multibot_task
            except asyncio.CancelledError:
                pass

        multibot_manager = None
        multibot_task = None
        return {"status": "ok", "message": "⏹ Multi-bot farm stopped."}
    except Exception as e:
        multibot_manager = None
        multibot_task = None
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
    """Create or update a message preset with input validation."""
    messages = body.get("messages", [])
    description = body.get("description", "")
    try:
        save_preset(name, messages, description)
        return {"status": "ok", "message": f"Preset '{name}' saved."}
    except ValueError as ve:
        return JSONResponse({"status": "error", "message": str(ve)}, status_code=400)
    except Exception as e:
        return JSONResponse({"status": "error", "message": f"Failed to save preset: {e}"}, status_code=500)


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


# ── Routes: Video Feeds & YouTube Seeder ────────────────────

@app.get("/api/feeds")
async def list_feeds():
    """List all available bot video feeds in pool and catalog."""
    from engine.youtube_seeder import get_feeds_catalog
    catalog = get_feeds_catalog()
    pool_dir = BASE_DIR / "video_pool"
    y4m_files = [f.name for f in pool_dir.glob("*.y4m")] if pool_dir.exists() else []
    return {
        "count": len(y4m_files),
        "y4m_files": y4m_files,
        "feeds": catalog
    }


@app.post("/api/feeds/seed-youtube")
async def seed_youtube_feeds(payload: Dict[str, Any] = Body(...)):
    """
    Download a YouTube Zoom meeting recording, detect participant tiles,
    and crop 5-8s looping feeds into the bot video pool.
    """
    from engine.youtube_seeder import run_youtube_seeder_task

    url = payload.get("youtube_url") or payload.get("url")
    file_path = payload.get("input_file")
    duration = float(payload.get("duration", 6.0))
    max_bots = int(payload.get("max_bots", 10))
    grid = payload.get("grid")
    no_ping_pong = bool(payload.get("no_ping_pong", False))

    if not url and not file_path:
        return JSONResponse(
            status_code=400,
            content={"error": "Either 'youtube_url' or 'input_file' must be provided."}
        )

    # Log to dashboard
    sync_log_callback({
        "timestamp": datetime.now().strftime("%H:%M:%S"),
        "level": "info",
        "message": f"Starting YouTube Feed Seeder for URL: {url or file_path} (Duration: {duration}s, Max Bots: {max_bots})",
        "bot_name": "Seeder",
        "source": "feeder",
    })

    try:
        feeds = await run_youtube_seeder_task(
            youtube_url=url,
            input_file=file_path,
            duration=duration,
            max_bots=max_bots,
            grid=grid,
            no_ping_pong=no_ping_pong
        )
        sync_log_callback({
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "level": "success",
            "message": f"Successfully extracted {len(feeds)} bot video feed(s) from YouTube!",
            "bot_name": "Seeder",
            "source": "feeder",
        })
        return {
            "status": "success",
            "extracted_count": len(feeds),
            "feeds": feeds
        }
    except Exception as e:
        sync_log_callback({
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "level": "error",
            "message": f"Feed Seeder failed: {str(e)}",
            "bot_name": "Seeder",
            "source": "feeder",
        })
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.delete("/api/feeds/{feed_id}")
async def remove_feed(feed_id: str):
    """Delete a bot video feed by ID."""
    from engine.youtube_seeder import delete_feed
    ok = delete_feed(feed_id)
    if ok:
        return {"status": "ok", "message": f"Feed {feed_id} deleted."}
    return JSONResponse(status_code=404, content={"error": f"Feed {feed_id} not found."})


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
    print("\n  [Zomo] Zoom Bot Automation Studio")
    print("  ------------------------------------")
    print(f"  Dashboard: http://localhost:{port}")
    print(f"  API Docs:  http://localhost:{port}/docs\n")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
