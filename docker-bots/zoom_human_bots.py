"""
Zomo Human Bots — Multi-Context Zoom Web Client Automation
============================================================
Runs multiple realistic human-looking bots in ONE Playwright browser
using isolated Browser Contexts (lightweight tabs).

Each bot has:
  - A unique realistic human name
  - Staggered join time (humans don't join simultaneously)
  - Human-like typing speed with jitter
  - Random chat messages at varied intervals
  - Emoji reactions (👍 👏 ❤️ 😊)
  - Randomized "raise hand" behavior
  - Unique per-bot Y4M video stream (color-varied animated face feeds)
  - Persistent webcam video (stays ON throughout meeting)
  - Automatic audio+video setup after waiting-room admission
  - Graceful disconnect and meeting-end handling

Usage:
  python zoom_human_bots.py --meeting-url "https://zoom.us/j/ID?pwd=PWD" --count 20

  Options:
    --meeting-url        Zoom meeting join URL (required)
    --count              Number of human bots to spawn (default: 5)
    --chat-min           Min seconds between chat messages (default: 20)
    --chat-max           Max seconds between chat messages (default: 60)
    --join-delay-min     Min seconds between each bot joining (default: 8)
    --join-delay-max     Max seconds between each bot joining (default: 25)
    --timeout            Max runtime in seconds (default: 3600)
    --headless           Run headless (default: True)
    --mock-video         Path to Y4M video file for fake webcam
    --names-file         Optional JSON file with custom name list
    --messages-file      Optional JSON file with custom message list
    --per-bot-browser    Launch independent browser per bot (unique video feeds)
    --avatar-dir         Folder with portrait photos to convert to Y4M
    --video-pool         Folder of Y4M files; auto-generated if empty
"""

import argparse
import asyncio
import json
import os
import random
import signal
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

def resolve_path(p_str: str) -> Path:
    p = Path(p_str)
    if p.exists():
        return p
    if (SCRIPT_DIR / p_str).exists():
        return SCRIPT_DIR / p_str
    if (SCRIPT_DIR / p.name).exists():
        return SCRIPT_DIR / p.name
    return p

# ── Human Name Pool ──────────────────────────────────────────

HUMAN_NAMES = [
    "Alex Morgan",     "Jamie Chen",      "Taylor Brooks",   "Jordan Lee",
    "Casey Williams",  "Riley Johnson",   "Avery Smith",     "Morgan Davis",
    "Cameron Wilson",  "Dakota Martinez", "Skyler Anderson", "Quinn Thompson",
    "Peyton Garcia",   "Logan Robinson",  "Hayden Clark",    "Reese Lewis",
    "Drew Hall",       "Blake Young",     "Finley Allen",    "Parker King",
    "Emery Scott",     "Rowan Green",     "Ellis Baker",     "Sawyer Nelson",
    "River Carter",    "Sage Mitchell",   "Harlow Perez",    "Lennox Roberts",
    "Crew Turner",     "Blythe Phillips", "Zion Campbell",   "Nova Parker",
    "Wren Evans",      "Jaden Edwards",   "Sloane Collins",  "Maddox Stewart",
    "Briar Sanchez",   "Remi Morris",     "Tatum Rogers",    "Landry Reed",
    "Marlowe Cook",    "Bellamy Morgan",  "Colt Bell",       "Indie Murphy",
    "Onyx Bailey",     "Blaire Rivera",   "Flint Cooper",    "Lark Richardson",
    "Cade Cox",        "Lyra Howard",
]

# ── Chat Message Pools ───────────────────────────────────────

CHAT_MESSAGES = {
    "greetings": [
        "Hi everyone! 😊",
        "Hey, good to be here!",
        "Good morning everyone!",
        "Hello! Hope everyone's doing well.",
        "Thanks for having me!",
        "Hey all, excited for this!",
    ],
    "reactions": [
        "That's a great point!",
        "Totally agree with that.",
        "Very insightful, thanks!",
        "Makes a lot of sense.",
        "I hadn't thought about it that way.",
        "This is really helpful.",
        "Excellent explanation!",
        "Couldn't agree more.",
        "That's exactly what I was thinking.",
        "Great perspective!",
    ],
    "questions": [
        "Can you elaborate on that a bit more?",
        "Is there a recording of this session?",
        "When will the slides be shared?",
        "Could you repeat that last part?",
        "What's the timeline for this?",
        "Is there a Q&A section later?",
    ],
    "generic": [
        "👍",
        "👏",
        "❤️",
        "😊",
        "Noted!",
        "Thanks!",
        "Got it.",
        "Sounds good!",
        "Perfect.",
        "Absolutely.",
        "Makes sense!",
    ],
}

ALL_MESSAGES = (
    CHAT_MESSAGES["greetings"] * 2 +
    CHAT_MESSAGES["reactions"] * 3 +
    CHAT_MESSAGES["questions"] +
    CHAT_MESSAGES["generic"] * 4
)

EMOJI_REACTIONS = ["👍", "👏", "❤️", "😊", "🎉", "🔥"]

# ── Logging ──────────────────────────────────────────────────

LOG_CALLBACK = None

COLORS = {
    "INFO":  "\033[96m",    # cyan
    "OK":    "\033[92m",    # green
    "WARN":  "\033[93m",    # yellow
    "ERR":   "\033[91m",    # red
    "CHAT":  "\033[95m",    # magenta
    "ACT":   "\033[94m",    # blue
    "JOIN":  "\033[32m",    # dark green
    "SYS":   "\033[37m",    # white
    "RESET": "\033[0m",
}

def set_log_callback(fn):
    global LOG_CALLBACK
    LOG_CALLBACK = fn

def log(level: str, msg: str, name: str = "SYSTEM"):
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    c = COLORS.get(level, COLORS["RESET"])
    r = COLORS["RESET"]
    # Pad name for aligned output
    name_padded = name[:16].ljust(16)
    print(f"{c}[{ts}] [{name_padded}] [{level:4s}]{r}  {msg}", flush=True)
    if LOG_CALLBACK:
        try:
            LOG_CALLBACK(level, msg, name)
        except Exception:
            pass

# ── Argument Parsing ─────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(description="Zomo Human Bots — Multi-Context Zoom Automation")
    p.add_argument("--meeting-url",    type=str,  default=os.getenv("MEETING_URL", ""))
    p.add_argument("--count",          type=int,  default=int(os.getenv("BOT_COUNT", "5")))
    p.add_argument("--chat-min",       type=int,  default=int(os.getenv("CHAT_MIN", "20")))
    p.add_argument("--chat-max",       type=int,  default=int(os.getenv("CHAT_MAX", "60")))
    p.add_argument("--join-delay-min", type=int,  default=int(os.getenv("JOIN_DELAY_MIN", "8")))
    p.add_argument("--join-delay-max", type=int,  default=int(os.getenv("JOIN_DELAY_MAX", "25")))
    p.add_argument("--video-delay-min",type=int,  default=int(os.getenv("VIDEO_DELAY_MIN", "1")), help="Min seconds after joining before first video start")
    p.add_argument("--video-delay-max",type=int,  default=int(os.getenv("VIDEO_DELAY_MAX", "5")), help="Max seconds after joining before first video start")
    p.add_argument("--timeout",        type=int,  default=int(os.getenv("BOT_TIMEOUT", "3600")))
    p.add_argument("--headless",       action="store_true", default=None)
    p.add_argument("--no-headless",    action="store_true", default=False, help="Run browser with visible windows")
    p.add_argument("--mock-video",     type=str,  default=os.getenv("MOCK_VIDEO", "./mock_face.y4m"))
    p.add_argument("--avatar-dir",     type=str,  default=os.getenv("AVATAR_DIR", "./avatars"), help="Folder containing photo portraits")
    p.add_argument("--video-pool",     type=str,  default=os.getenv("VIDEO_POOL", "./video_pool"), help="Folder containing cached Y4M video feeds")
    p.add_argument("--per-bot-browser",action="store_true", default=False, help="Launch independent browser instance per bot for unique video feeds")
    p.add_argument("--names-file",     type=str,  default=None)
    p.add_argument("--messages-file",  type=str,  default=None)
    
    args = p.parse_args()
    if args.no_headless:
        args.headless = False
    elif args.headless is None:
        args.headless = os.getenv("HEADLESS", "true").lower() == "true"
    return args


# ── Video Pool Preparation ────────────────────────────────────

# Distinct hue presets (H, S, V as fractions 0-1) for per-bot color variation
_BOT_SKIN_TONES = [
    (0.06, 0.30, 0.90),  # warm peach
    (0.05, 0.25, 0.80),  # olive
    (0.04, 0.20, 0.70),  # medium brown
    (0.08, 0.35, 0.95),  # fair/rosy
    (0.07, 0.22, 0.60),  # deep brown
    (0.05, 0.28, 0.85),  # golden
    (0.06, 0.18, 0.50),  # dark
    (0.09, 0.32, 0.92),  # light warm
]


def _hsv_to_yuv(h, s, v):
    """Convert HSV → RGB → YUV (BT.601). Returns (Y, U, V) integer bytes."""
    import math
    hi = int(h * 6) % 6
    f  = h * 6 - int(h * 6)
    p  = v * (1 - s)
    q  = v * (1 - f * s)
    t  = v * (1 - (1 - f) * s)
    rgb_map = [(v,t,p),(q,v,p),(p,v,t),(p,q,v),(t,p,v),(v,p,q)]
    r, g, b = rgb_map[hi]
    # BT.601 coefficients
    Y =  16 + int(65.481*r + 128.553*g + 24.966*b)
    U = 128 + int(-37.797*r - 74.203*g + 112.0*b)
    V = 128 + int(112.0*r - 93.786*g - 18.214*b)
    return (max(16, min(235, Y)), max(16, min(240, U)), max(16, min(240, V)))


def generate_colored_bot_video(output_path: str, bot_index: int,
                               width=320, height=240, fps=10, duration_sec=300):
    """Generate a unique colored animated face silhouette Y4M for a specific bot.
    Uses lower resolution (320x240) and 10fps to keep file size manageable,
    and a 5-minute duration so the stream doesn't go black mid-session."""
    import math
    tone = _BOT_SKIN_TONES[bot_index % len(_BOT_SKIN_TONES)]
    skin_Y, skin_U, skin_V = _hsv_to_yuv(*tone)
    total_frames = fps * duration_sec
    cx, cy     = width // 2, height // 2
    head_r     = min(width, height) // 6
    body_w     = min(width, height) // 4
    body_h     = min(width, height) // 3
    head_cy    = cy - head_r * 2
    body_cy    = cy + head_r

    # Pre-compute a single base frame to copy for speed, just vary the animation phase
    log("INFO", f"Generating {duration_sec}s bot video at {width}x{height}@{fps}fps "
        f"({total_frames} frames)...", "SETUP")

    with open(output_path, "wb") as f:
        header = f"YUV4MPEG2 W{width} H{height} F{fps}:1 Ip A1:1 C420\n"
        f.write(header.encode("ascii"))

        # Precompute static face mask for performance
        face_mask = bytearray(width * height)   # 1 = face/body, 0 = background
        uv_mask   = bytearray((width // 2) * (height // 2))
        for row in range(height):
            for col in range(width):
                dx = col - cx
                hd = math.sqrt(dx**2 + (row - head_cy)**2)
                bd = math.sqrt((dx / body_w)**2 + ((row - body_cy) / body_h)**2)
                face_mask[row * width + col] = 1 if (hd < head_r or bd < 1.0) else 0
        for row in range(height // 2):
            for col in range(width // 2):
                sr, sc = row * 2, col * 2
                dx = sc - cx
                hd = math.sqrt(dx**2 + (sr - head_cy)**2)
                bd = math.sqrt((dx / body_w)**2 + ((sr - body_cy) / body_h)**2)
                uv_mask[row * (width // 2) + col] = 1 if (hd < head_r or bd < 1.0) else 0

        for frame_num in range(total_frames):
            phase = (frame_num / fps) * 0.5  # slow subtle animation
            anim = int(4 * math.sin(phase))

            y_plane = bytearray(width * height)
            for i in range(width * height):
                if face_mask[i]:
                    y_plane[i] = max(16, min(235, skin_Y + anim))
                else:
                    row_i = i // width
                    bg = 70 + int(8 * math.sin(row_i * 0.04 + phase))
                    y_plane[i] = max(16, min(235, bg))

            u_plane = bytearray((width // 2) * (height // 2))
            v_plane = bytearray((width // 2) * (height // 2))
            for i in range(len(uv_mask)):
                if uv_mask[i]:
                    u_plane[i] = skin_U
                    v_plane[i] = skin_V
                else:
                    u_plane[i] = 128
                    v_plane[i] = 128

            f.write(b"FRAME\n")
            f.write(bytes(y_plane) + bytes(u_plane) + bytes(v_plane))




def prepare_video_pool(avatar_dir: str = "./avatars", pool_dir: str = "./video_pool",
                       bot_count: int = 1) -> list:
    """Scan avatar images → Y4M, or auto-generate unique colored streams per bot."""
    avatars_path = resolve_path(avatar_dir)
    pool_path = resolve_path(pool_dir)
    pool_path.mkdir(parents=True, exist_ok=True)

    # Convert any avatar photos to Y4M if present
    if avatars_path.exists():
        valid_exts = {".jpg", ".jpeg", ".png", ".webp"}
        image_files = [f for f in avatars_path.iterdir() if f.suffix.lower() in valid_exts]
        if image_files:
            try:
                from image_to_video import create_animated_y4m_from_image
                for img in image_files:
                    out_y4m = pool_path / f"{img.stem}.y4m"
                    if not out_y4m.exists():
                        log("INFO", f"Converting avatar photo → video: {img.name}...", "SETUP")
                        create_animated_y4m_from_image(str(img), str(out_y4m))
            except Exception as e:
                log("WARN", f"Avatar image conversion warning: {e}", "SETUP")

    y4m_files = list(pool_path.glob("*.y4m"))

    # Auto-generate unique colored bot feeds if pool is insufficient
    if len(y4m_files) < bot_count:
        needed = bot_count - len(y4m_files)
        existing_count = len(y4m_files)
        log("INFO", f"Auto-generating {needed} unique bot video feed(s) in {pool_path}/...", "SETUP")
        for idx in range(needed):
            bot_idx = existing_count + idx
            out_y4m = pool_path / f"bot_face_{bot_idx:02d}.y4m"
            try:
                generate_colored_bot_video(str(out_y4m), bot_index=bot_idx)
                log("OK", f"  Generated: {out_y4m.name} (skin tone variant {bot_idx})", "SETUP")
                y4m_files.append(out_y4m)
            except Exception as e:
                log("WARN", f"  Could not generate bot video {bot_idx}: {e}", "SETUP")

    return [str(f.resolve()) for f in sorted(pool_path.glob("*.y4m"))]

# ── URL Normalization ─────────────────────────────────────────

def to_web_client_url(url: str) -> str:
    """Convert standard Zoom invite link or Meeting ID to web client join URL."""
    if not url:
        return url
    url = url.strip()
    clean_id = url.replace(" ", "").replace("-", "")
    if clean_id.isdigit():
        return f"https://zoom.us/wc/join/{clean_id}"
    if "/wc/" in url:
        return url
    if "/j/" in url:
        if "?" in url:
            return url.replace("/j/", "/wc/join/")
        else:
            return url.replace("/j/", "/wc/join/")
    if not url.startswith("http"):
        return f"https://zoom.us/wc/join/{url}"
    return url

# ── Browser Args ─────────────────────────────────────────────

def get_browser_args(mock_video: str) -> list:
    """Return Chromium launch arguments for minimal RAM, fake media, human UA."""
    args = [
        "--autoplay-policy=no-user-gesture-required",
        "--use-fake-ui-for-media-stream",
        "--use-fake-device-for-media-stream",
        "--enable-usermedia-screen-capturing",
        "--allow-file-access-from-files",
        "--disable-blink-features=AutomationControlled",
        "--disable-infobars",
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-dev-shm-usage",
        "--disable-web-security",
        "--disable-features=IsolateOrigins,site-per-process",
        "--disable-extensions",
        "--disable-background-timer-throttling",
        "--disable-backgrounding-occluded-windows",
        "--disable-renderer-backgrounding",
        "--memory-pressure-off",
        "--no-first-run",
        "--no-default-browser-check",
    ]

    video = resolve_path(mock_video)
    if not video.exists():
        try:
            from generate_mock_video import create_y4m
            log("INFO", f"Generating synthetic human webcam video at {video}...", "SETUP")
            create_y4m(str(video), width=640, height=480, fps=15, duration_sec=20)
        except Exception as e:
            log("WARN", f"Could not auto-generate mock video: {e}. Using Chrome color bars.", "SETUP")

    if video.exists():
        args.append(f"--use-file-for-fake-video-capture={video.resolve()}")
        log("OK", f"Mock video active: {video.resolve()}", "SETUP")
    else:
        log("WARN", f"Mock video file not available. Using default fake video stream.", "SETUP")

    return args


# ══════════════════════════════════════════════════════════════
# HumanBot — Single Browser Context (Tab)
# ══════════════════════════════════════════════════════════════

class HumanBot:
    def __init__(self, name: str, context, meeting_url: str,
                 chat_min: int, chat_max: int,
                 messages: list, timeout: int, bot_index: int,
                 video_delay_min: int = 1, video_delay_max: int = 5):
        self.name            = name
        self.context         = context
        self.url             = meeting_url
        self.chat_min        = chat_min
        self.chat_max        = chat_max
        self.messages        = messages
        self.timeout         = timeout
        self.index           = bot_index
        self.video_delay_min = video_delay_min
        self.video_delay_max = video_delay_max
        self.page            = None
        self.alive           = False
        self.msgs_sent       = 0
        self.joined_at       = None

    def log(self, level, msg):
        log(level, msg, self.name[:16])

    # ── Page Setup ────────────────────────────────────────────

    async def open_page(self):
        self.page = await self.context.new_page()
        # Stealth bypass script to prevent Zoom bot detection ("Automated bots aren't allowed to join")
        STEALTH_JS = """
        // 1. Mask navigator.webdriver
        try {
            delete Object.getPrototypeOf(navigator).webdriver;
        } catch (e) {}
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

        // 2. Add Chrome Runtime & csi/loadTimes
        window.chrome = {
            app: { isInstalled: false },
            runtime: {
                OnInstalledReason: { INSTALL: 'install' },
                PlatformOs: { WIN: 'win' },
            },
            csi: function() {},
            loadTimes: function() {}
        };

        // 3. User-Agent Data mock
        if (!navigator.userAgentData) {
            Object.defineProperty(navigator, 'userAgentData', {
                get: () => ({
                    brands: [
                        { brand: 'Google Chrome', version: '124' },
                        { brand: 'Chromium', version: '124' },
                        { brand: 'Not-A.Brand', version: '99' }
                    ],
                    mobile: false,
                    platform: 'Windows'
                })
            });
        }

        // 4. Permissions query fallback
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications' ?
                Promise.resolve({ state: Notification.permission }) :
                originalQuery(parameters)
        );

        // 5. Languages & Plugins
        Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
        Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
        """
        await self.page.add_init_script(STEALTH_JS)

    # ── Human-like Mouse Movement ─────────────────────────────

    async def human_mouse_move(self):
        """Simulate natural mouse movement across waypoints to pass reCAPTCHA v3 bot checks."""
        try:
            if not self.page:
                return
            vp = self.page.viewport_size or {"width": 1280, "height": 720}
            w, h = vp.get("width", 1280), vp.get("height", 720)

            # Move mouse through 3-4 random waypoints
            curr_x = random.randint(100, 400)
            curr_y = random.randint(100, 300)
            await self.page.mouse.move(curr_x, curr_y)

            for _ in range(random.randint(2, 4)):
                target_x = random.randint(50, w - 50)
                target_y = random.randint(50, h - 50)
                steps = random.randint(8, 16)
                await self.page.mouse.move(target_x, target_y, steps=steps)
                await asyncio.sleep(random.uniform(0.1, 0.25))
        except Exception:
            pass

    # ── Mute Microphone (always kept muted) ───────────────────

    async def ensure_muted(self) -> bool:
        """Ensure the bot's microphone is muted. Audio is ALWAYS muted — bots are silent listeners."""
        try:
            if not self.page:
                return False
            mute_selectors = [
                "button[aria-label*='mute' i]:not([aria-label*='unmute' i])",
                "button:has-text('Mute')",
                "[aria-label='mute my microphone' i]",
                ".audio-control-button--unmuted",
                "button.ax-outline:has-text('Mute')",
            ]
            for sel in mute_selectors:
                try:
                    loc = self.page.locator(sel)
                    if await loc.count() > 0 and await loc.first.is_visible():
                        aria = (await loc.first.get_attribute("aria-label") or "").lower()
                        txt  = (await loc.first.inner_text() or "").lower()
                        if "unmute" not in aria and "unmute" not in txt:
                            await loc.first.click()
                            self.log("ACT", "🔇 Microphone muted")
                            return True
                except Exception:
                    continue
            return False
        except Exception:
            return False

    # ── Webcam Video Control ──────────────────────────────────

    async def wake_toolbar(self):
        """Wake up Zoom Web Client footer toolbar if auto-hidden."""
        try:
            if self.page:
                vp = self.page.viewport_size or {"width": 1280, "height": 720}
                cx, cy = vp["width"] // 2, vp["height"] // 2
                await self.page.mouse.move(cx, cy)
                await asyncio.sleep(0.2)
                await self.page.mouse.move(cx, cy + 10)
                footer = self.page.locator("#wc-footer")
                if await footer.count() > 0:
                    await footer.first.hover()
                await asyncio.sleep(0.3)
        except Exception:
            pass

    async def _dismiss_video_preview_dialog(self):
        """Dismiss Zoom's video preview / join-with-video confirmation dialog."""
        preview_selectors = [
            "button:has-text('Join with Video')",
            "[aria-label*='Join with Video' i]",
            "button:has-text('Join With Video')",
            "button:has-text('Start with Video')",
            # The "Always show video preview" checkbox confirmation button
            ".ReactModal__Content button:has-text('Join')",
            "[class*='preview'] button:has-text('Join')",
            "[class*='preview-video'] button",
            "[class*='video-preview'] button:has-text('Join')",
            "dialog button:has-text('Join')",
        ]
        for sel in preview_selectors:
            try:
                loc = self.page.locator(sel)
                if await loc.count() > 0 and await loc.first.is_visible():
                    await loc.first.click()
                    self.log("ACT", f"🎬 Dismissed video preview dialog")
                    await asyncio.sleep(0.5)
                    return True
            except Exception:
                continue
        # JS fallback: click any visible Join button inside a dialog/modal
        try:
            clicked = await self.page.evaluate("""
                () => {
                    const modals = document.querySelectorAll(
                        '.ReactModal__Content, dialog, [role="dialog"], [class*="preview"]'
                    );
                    for (const m of modals) {
                        const btns = m.querySelectorAll('button');
                        for (const b of btns) {
                            const t = b.textContent.trim().toLowerCase();
                            if (t === 'join' || t === 'join with video' || t === 'start with video') {
                                b.click();
                                return true;
                            }
                        }
                    }
                    return false;
                }
            """)
            if clicked:
                await asyncio.sleep(0.5)
        except Exception:
            pass
        return False

    async def ensure_video_on(self) -> bool:
        """Ensure the bot's webcam video is streaming. Uses multiple strategies
        and actually confirms success by checking if video is on after each attempt."""
        try:
            if not self.page:
                return False

            await self.wake_toolbar()
            await asyncio.sleep(0.3)

            # Already streaming? Quick exit.
            if await self.is_video_on():
                return True

            # ── Strategy 1: Click Start Video button via selectors ──
            start_video_selectors = [
                "#wc-footer button[aria-label*='Start Video' i]",
                "#wc-footer button[aria-label*='start video' i]",
                "button[aria-label='Start Video']",
                "button[aria-label='Start my video']",
                "button[aria-label*='start' i][aria-label*='video' i]",
                "button:has-text('Start Video')",
                "button:has-text('Start my video')",
                "button:has-text('Turn on video')",
                ".footer-button-base__inner-layout:has-text('Start Video')",
                ".video-control-button--off",
                ".footer-button__start-video",
                "[class*='VideoButton']:not([class*='stop' i])",
                "[class*='video-btn']:not([class*='stop' i])",
            ]

            clicked_btn = False
            for sel in start_video_selectors:
                try:
                    loc = self.page.locator(sel)
                    if await loc.count() > 0 and await loc.first.is_visible():
                        await loc.first.click()
                        clicked_btn = True
                        await asyncio.sleep(1.5)  # wait for dialog to appear
                        break
                except Exception:
                    continue

            if clicked_btn:
                # Always try to dismiss the preview dialog after clicking Start Video
                await self._dismiss_video_preview_dialog()
                await asyncio.sleep(1.0)
                if await self.is_video_on():
                    self.log("ACT", "📹 Video stream started via button")
                    return True

            # ── Strategy 2: JS direct click on video button ──
            try:
                clicked = await self.page.evaluate("""
                    () => {
                        // Try aria-label matching
                        const ariaTargets = [
                            'Start Video', 'start video', 'Start my video', 'Turn on video'
                        ];
                        for (const btn of document.querySelectorAll('button')) {
                            const label = (btn.getAttribute('aria-label') || '').trim();
                            const text  = btn.textContent.trim();
                            if (ariaTargets.some(t => label.toLowerCase().includes(t.toLowerCase()) ||
                                                       text.toLowerCase().includes(t.toLowerCase()))) {
                                if (btn.offsetParent !== null) {  // visible check
                                    btn.click();
                                    return 'clicked:' + (label || text);
                                }
                            }
                        }
                        return null;
                    }
                """)
                if clicked:
                    self.log("ACT", f"📹 JS video start: {clicked}")
                    await asyncio.sleep(1.5)
                    await self._dismiss_video_preview_dialog()
                    await asyncio.sleep(0.8)
                    if await self.is_video_on():
                        self.log("ACT", "📹 Video confirmed ON via JS strategy")
                        return True
            except Exception:
                pass

            # ── Strategy 3: Keyboard shortcut Alt+V ──
            try:
                await self.wake_toolbar()
                await self.page.keyboard.press("Alt+v")
                await asyncio.sleep(1.5)
                await self._dismiss_video_preview_dialog()
                await asyncio.sleep(0.8)
                if await self.is_video_on():
                    self.log("ACT", "📹 Video confirmed ON via Alt+V")
                    return True
                # Even if we can't confirm, log the attempt
                self.log("ACT", "📹 Alt+V pressed (unconfirmed)")
            except Exception:
                pass

            return False
        except Exception as e:
            self.log("WARN", f"ensure_video_on error: {e}")
            return False

    async def is_video_on(self) -> bool:
        """Return True if video is currently streaming.
        Checks multiple indicators used across different Zoom Web Client versions."""
        try:
            if not self.page:
                return False

            # Check button text/aria-label for "Stop Video"
            for sel in [
                "button:has-text('Stop Video')",
                "button[aria-label*='Stop Video' i]",
                "button[aria-label*='stop video' i]",
                "button[aria-label*='stop my video' i]",
                "[aria-label*='Stop Video' i]",
            ]:
                try:
                    loc = self.page.locator(sel)
                    if await loc.count() > 0 and await loc.first.is_visible():
                        return True
                except Exception:
                    pass

            # Check aria-pressed / aria-checked on video button (some Zoom versions)
            for sel in [
                "button[aria-pressed='true'][aria-label*='video' i]",
                "button[aria-checked='true'][aria-label*='video' i]",
                ".video-control-button--on",
                "[class*='video'][class*='--on']",
                "[class*='video'][class*='active']",
            ]:
                try:
                    loc = self.page.locator(sel)
                    if await loc.count() > 0 and await loc.first.is_visible():
                        return True
                except Exception:
                    pass

            # JS fallback: inspect DOM for video-on state
            try:
                result = await self.page.evaluate("""
                    () => {
                        for (const btn of document.querySelectorAll('button')) {
                            const label = (btn.getAttribute('aria-label') || '').toLowerCase();
                            const text  = btn.textContent.trim().toLowerCase();
                            if (label.includes('stop video') || text === 'stop video') {
                                if (btn.offsetParent !== null) return true;
                            }
                        }
                        return false;
                    }
                """)
                if result:
                    return True
            except Exception:
                pass

            return False
        except Exception:
            return False

    async def turn_off_video(self) -> bool:
        """Stop the webcam feed (bot briefly steps away from camera)."""
        try:
            if not self.page:
                return False
            stop_selectors = [
                "button:has-text('Stop Video')",
                "button[aria-label*='stop' i][aria-label*='video' i]",
                "[aria-label*='stop my video' i]",
                "[aria-label*='Stop Video' i]",
                ".footer-button-base:has-text('Stop Video')",
                "#wc-footer button:has-text('Stop Video')",
                ".video-control-button--on",
            ]
            for sel in stop_selectors:
                try:
                    loc = self.page.locator(sel)
                    if await loc.count() > 0 and await loc.first.is_visible():
                        await loc.first.click()
                        self.log("ACT", "📷 Camera paused (stepped away)")
                        return True
                except Exception:
                    continue
            return False
        except Exception:
            return False

    # ── Human-like Typing ─────────────────────────────────────

    async def human_type(self, locator, text: str):
        """Type text character-by-character with natural delays."""
        await locator.click()
        await asyncio.sleep(random.uniform(0.15, 0.4))
        for char in text:
            await locator.press(char)
            # Natural WPM: fast typist ~60-80 WPM → 60-120ms per char
            delay = random.gauss(0.075, 0.025)
            await asyncio.sleep(max(0.03, delay))
        await asyncio.sleep(random.uniform(0.1, 0.3))

    # ── Safe Element Interaction ──────────────────────────────

    async def dismiss_cookie_banner(self) -> bool:
        """Aggressively dismiss or DOM-remove any cookie consent popups/overlays."""
        if not self.page:
            return False

        cookie_selectors = [
            "#onetrust-accept-btn-handler",
            "button:has-text('ACCEPT COOKIES')",
            "button:has-text('Accept Cookies')",
            "button:has-text('Accept All Cookies')",
            "button:has-text('Accept All')",
            "button:has-text('Accept')",
            "button:has-text('I Agree')",
            "button:has-text('Agree')",
            "#select-all-cookies",
            ".onetrust-close-btn-handler",
            "button[aria-label='Close']",
            "#wc_agree1",
        ]

        clicked = False
        for sel in cookie_selectors:
            try:
                loc = self.page.locator(sel)
                cnt = await loc.count()
                if cnt > 0:
                    for idx in range(cnt):
                        item = loc.nth(idx)
                        if await item.is_visible():
                            try:
                                await item.click(timeout=1500)
                            except Exception:
                                try:
                                    await item.click(force=True, timeout=1500)
                                except Exception:
                                    await item.evaluate("el => el.click()")
                            self.log("ACT", f"✓ Dismissed cookie banner via: {sel}")
                            clicked = True
                            await asyncio.sleep(0.3)
                            break
            except Exception:
                continue

        # Failsafe: DOM removal of OneTrust backdrop/banner elements if still present
        try:
            await self.page.evaluate("""() => {
                const ids = [
                    'onetrust-banner-sdk',
                    'onetrust-consent-sdk',
                    'onetrust-pc-dark-filter',
                    'onetrust-group-container'
                ];
                ids.forEach(id => {
                    const el = document.getElementById(id);
                    if (el) el.remove();
                });
                document.querySelectorAll('.onetrust-pc-dark-filter, [class*="onetrust"], [id*="onetrust"]').forEach(el => el.remove());
            }""")
        except Exception:
            pass

        return clicked

    async def try_click(self, selector: str, timeout: int = 3000, description: str = "") -> bool:
        try:
            loc = self.page.locator(selector)
            await loc.wait_for(state="visible", timeout=timeout)
            await asyncio.sleep(random.uniform(0.1, 0.4))
            try:
                await loc.first.click(timeout=2000)
            except Exception:
                await loc.first.click(force=True, timeout=2000)
            if description:
                self.log("ACT", f"✓ {description}")
            return True
        except Exception:
            return False

    async def find_and_fill(self, selectors: list, text: str) -> bool:
        for sel in selectors:
            try:
                loc = self.page.locator(sel)
                if await loc.count() > 0:
                    vis = await loc.first.is_visible()
                    if vis:
                        await loc.first.clear()
                        await self.human_type(loc.first, text)
                        return True
            except Exception:
                continue
        return False

    # ── Meeting State Detection ───────────────────────────────

    async def check_join_status(self) -> str:
        """Check if bot is in meeting room, waiting room, or not joined."""
        if not self.page:
            return "NOT_JOINED"

        # Check Waiting Room indicators
        waiting_indicators = [
            "text=waiting room",
            "text=host will let you in soon",
            "text=Please wait, the meeting host will let you in",
            "text=Waiting for host",
            "text=The meeting host will let you in soon",
            ".waiting-room-content",
            "[class*='waiting-room']",
        ]
        for sel in waiting_indicators:
            try:
                loc = self.page.locator(sel)
                if await loc.count() > 0 and await loc.first.is_visible():
                    return "WAITING_ROOM"
            except Exception:
                pass

        # Check Bot Guard / Automation blocked indicators
        bot_blocked_indicators = [
            "text=Automated bots aren't allowed to join this meeting",
            "text=Automated bots",
            "text=Sign in to join",
            "text=sign in to join the meeting",
        ]
        for sel in bot_blocked_indicators:
            try:
                loc = self.page.locator(sel)
                if await loc.count() > 0 and await loc.first.is_visible():
                    return "BOT_BLOCKED"
            except Exception:
                pass

        # Check Active Meeting indicators
        meeting_indicators = [
            "button:has-text('Chat')",
            "button:has-text('Participants')",
            "[aria-label*='open the chat pane']",
            "[aria-label*='Chat']",
            "[aria-label*='Participants']",
            ".footer-button-base",
            "#wc-footer",
            "#wc-container-right",
            ".meeting-app",
            "canvas#video-canvas",
        ]
        for sel in meeting_indicators:
            try:
                loc = self.page.locator(sel)
                if await loc.count() > 0 and await loc.first.is_visible():
                    return "JOINED"
            except Exception:
                pass

        return "NOT_JOINED"

    async def is_alive(self) -> bool:
        if not self.page:
            return False
        end_texts = [
            "text=This meeting has been ended",
            "text=The host has ended the meeting",
            "text=You have been removed",
            "text=Meeting has ended",
            "text=The meeting has ended",
        ]
        for sel in end_texts:
            try:
                loc = self.page.locator(sel)
                if await loc.count() > 0 and await loc.first.is_visible():
                    return False
            except Exception:
                pass
        return True

    # ── Join Flow ─────────────────────────────────────────────

    async def join(self) -> bool:
        self.log("JOIN", f"Navigating → {self.url[:60]}...")
        try:
            await self.page.goto(self.url, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            self.log("ERR", f"Navigation failed: {e}")
            return False

        await asyncio.sleep(random.uniform(1.5, 3.0))

        # ── Step 1: Dismiss Cookie / Privacy / Terms popups ──
        await self.dismiss_cookie_banner()
        await asyncio.sleep(random.uniform(0.5, 1.0))

        # ── Step 2: Dismiss desktop app prompt / click browser join link ──
        browser_join = [
            "text=Join from Your Browser",
            "text=join from your browser",
            "text=Join from your browser",
            "a[href*='wc/join']",
            "a[href*='/wc/']",
            "button:has-text('Join from Your Browser')",
        ]
        for sel in browser_join:
            if await self.try_click(sel, 3000, "Browser join link"):
                await asyncio.sleep(random.uniform(1.5, 3.0))
                break

        await asyncio.sleep(random.uniform(0.5, 1.5))
        await self.dismiss_cookie_banner()

        # ── Step 3: Fill display name ──
        name_selectors = [
            "#inputname",
            "input[name='inputname']",
            "input[name='name']",
            "input[placeholder*='name' i]",
            "input[placeholder*='Name']",
            "input#join-confno-name",
            "input[aria-label*='name' i]",
            "input[aria-label*='Name']",
            "input[id*='name' i]",
            "input[type='text']",
        ]

        filled = False
        for attempt in range(5):
            await self.dismiss_cookie_banner()
            filled = await self.find_and_fill(name_selectors, self.name)
            if filled:
                self.log("OK", f"Name entered: {self.name}")
                break
            await asyncio.sleep(1.5)

        if not filled:
            self.log("WARN", "Could not fill name field automatically.")

        await asyncio.sleep(random.uniform(0.4, 1.0))

        # ── Step 4: Accept Terms of Service ──
        tos_selectors = [
            "#wc_agree1",
            "input[type='checkbox'][id*='agree']",
            "input[type='checkbox']",
            "text=I agree",
        ]
        for sel in tos_selectors:
            await self.try_click(sel, 1500, "ToS checkbox")

        await asyncio.sleep(random.uniform(0.3, 0.8))

        # ── Step 5: Simulate human mouse gesture to satisfy reCAPTCHA v3 score ──
        await self.human_mouse_move()
        await asyncio.sleep(random.uniform(0.3, 0.7))

        # ── Step 6: Click Join ──
        join_selectors = [
            "#joinBtn",
            "button:has-text('Join')",
            "button:has-text('join')",
            "input[value='Join']",
            "button[type='submit']",
            ".preview-join-button",
        ]
        for sel in join_selectors:
            if await self.try_click(sel, 3000, "Join button"):
                break

        # ── Step 7: Passcode Check ──
        passcode_selectors = [
            "#inputpasscode",
            "input[name='inputpasscode']",
            "input[placeholder*='passcode' i]",
            "input[placeholder*='Passcode']",
        ]
        for sel in passcode_selectors:
            try:
                loc = self.page.locator(sel)
                if await loc.count() > 0 and await loc.first.is_visible():
                    self.log("WARN", "🔒 Passcode prompt requested. Check if passcode in URL is correct.")
                    break
            except Exception:
                pass

        self.log("INFO", "Waiting for meeting room connection...")
        await asyncio.sleep(random.uniform(6, 10))

        # ── Step 8: Check Status & Handle Audio (with retry for BotGuard) ──
        status = await self.check_join_status()

        # Retry if blocked by BotGuard reCAPTCHA
        if status == "BOT_BLOCKED":
            self.log("WARN", "🔄 Bot block detected. Simulating extra mouse activity and retrying join...")
            await self.human_mouse_move()
            await asyncio.sleep(random.uniform(3.0, 5.0))
            for sel in join_selectors:
                if await self.try_click(sel, 3000, "Join button retry"):
                    break
            await asyncio.sleep(6)
            status = await self.check_join_status()

        if status == "BOT_BLOCKED":
            self.log("ERR", "🛑 Zoom BotGuard detected automation ('Automated bots aren't allowed to join this meeting').")
            screenshot_path = f"debug_{self.index+1}_{self.name.replace(' ', '_')}.png"
            try:
                await self.page.screenshot(path=screenshot_path)
                self.log("ERR", f"  Debug screenshot saved: {screenshot_path}")
            except Exception:
                pass
            return False
        elif status == "WAITING_ROOM":
            self.log("WARN", "⏳ Bot is in WAITING ROOM — run loop will handle admission.")
            self.joined_at = time.time()
            self.alive = True
            return True
        elif status == "JOINED":
            # Full audio + video setup
            await self.setup_audio_and_video()

            # Send initial greeting
            greeting = random.choice(CHAT_MESSAGES["greetings"])
            await self.send_chat(greeting)

            self.joined_at = time.time()
            self.alive = True
            self.log("OK", "✅ Successfully joined meeting with audio & video!")
            return True
        else:
            # Capture debug screenshot to inspect what browser shows
            screenshot_path = f"debug_{self.index+1}_{self.name.replace(' ', '_')}.png"
            try:
                await self.page.screenshot(path=screenshot_path)
                self.log("ERR", f"❌ Could not join meeting. Debug screenshot saved: {screenshot_path}")
            except Exception:
                self.log("ERR", "❌ Could not verify meeting join.")
            return False

    # ── Chat ──────────────────────────────────────────────────

    async def _open_chat_panel(self) -> bool:
        """Ensure the chat side-panel is open. Returns True if likely open."""
        # Check if input is already visible
        already_open = [
            "div[contenteditable='true']",
            "textarea[placeholder*='message' i]",
            "[aria-label*='type message' i]",
        ]
        for sel in already_open:
            try:
                loc = self.page.locator(sel)
                if await loc.count() > 0 and await loc.first.is_visible():
                    return True
            except Exception:
                pass

        # Try clicking the Chat button
        chat_btn_selectors = [
            "button:has-text('Chat')",
            "[aria-label*='open the chat pane' i]",
            "[aria-label='Chat']",
            "[aria-label*='Chat' i]",
            ".footer-button-base:has-text('Chat')",
            "#wc-footer button:has-text('Chat')",
            "[class*='chat-button']",
            "[class*='ChatButton']",
            "button[title*='Chat' i]",
        ]
        clicked = False
        for sel in chat_btn_selectors:
            if await self.try_click(sel, 2500):
                clicked = True
                await asyncio.sleep(random.uniform(0.6, 1.2))
                break

        if not clicked:
            # Fallback: Zoom web chat keyboard shortcut Alt+H
            try:
                await self.page.keyboard.press("Alt+h")
                await asyncio.sleep(0.8)
            except Exception:
                pass

        # Confirm panel opened
        for sel in already_open:
            try:
                loc = self.page.locator(sel)
                if await loc.count() > 0 and await loc.first.is_visible():
                    return True
            except Exception:
                pass
        return False

    async def send_chat(self, message: str) -> bool:
        try:
            # Ensure chat panel is open
            await self._open_chat_panel()

            # Find and use chat input (support both textarea and div[contenteditable])
            input_selectors = [
                "[aria-label*='type message' i]",
                "[aria-label*='chat' i][contenteditable='true']",
                "div[contenteditable='true']",
                "textarea[placeholder*='message' i]",
                "textarea[placeholder*='Message']",
                "[class*='chat-box'] [contenteditable='true']",
                "[class*='chat-box'] textarea",
                "[class*='chat-input'] [contenteditable='true']",
                "[class*='chat-input'] textarea",
                "#wc-container-right [contenteditable='true']",
                "#wc-container-right textarea",
                "div[class*='chat'] [contenteditable='true']",
                "div[class*='chat'] textarea",
            ]

            for sel in input_selectors:
                try:
                    loc = self.page.locator(sel)
                    if await loc.count() > 0 and await loc.first.is_visible():
                        # Scroll into view and click
                        try:
                            await loc.first.scroll_into_view_if_needed()
                        except Exception:
                            pass
                        await loc.first.click()
                        await asyncio.sleep(random.uniform(0.2, 0.45))

                        # Clear any stale text, then type
                        try:
                            await loc.first.select_all()
                        except Exception:
                            pass
                        try:
                            await loc.first.fill(message)
                        except Exception:
                            for char in message:
                                await loc.first.press(char)
                                await asyncio.sleep(max(0.02, random.gauss(0.065, 0.02)))

                        await asyncio.sleep(random.uniform(0.3, 0.6))
                        await loc.first.press("Enter")
                        self.msgs_sent += 1
                        self.log("CHAT", f"💬 '{message}' (total: {self.msgs_sent})")
                        return True
                except Exception:
                    continue

            self.log("WARN", "Chat input field not visible or disabled by host.")
            return False

        except Exception as e:
            self.log("ERR", f"Chat error: {e}")
            return False

    # ── Emoji Reaction ────────────────────────────────────────

    async def send_reaction(self):
        """Send an emoji reaction via Zoom's reaction panel."""
        try:
            reaction_btn = [
                "button:has-text('Reactions')",
                "[aria-label='Reactions']",
                "[class*='reaction-btn']",
            ]
            for sel in reaction_btn:
                if await self.try_click(sel, 2000):
                    await asyncio.sleep(random.uniform(0.3, 0.7))
                    emoji = random.choice(EMOJI_REACTIONS)
                    emoji_sel = f"[aria-label='{emoji}'], button:has-text('{emoji}')"
                    if await self.try_click(emoji_sel, 1500):
                        self.log("ACT", f"Reacted with {emoji}")
                    return
        except Exception:
            pass

    # ── Raise Hand ────────────────────────────────────────────

    async def raise_hand(self):
        """Raise hand in the meeting."""
        try:
            raise_selectors = [
                "button:has-text('Raise Hand')",
                "[aria-label='Raise Hand']",
                "[class*='raise-hand']",
            ]
            for sel in raise_selectors:
                if await self.try_click(sel, 2000, "Raise Hand"):
                    self.log("ACT", "✋ Raised hand")
                    return
        except Exception:
            pass

    async def is_audio_connected(self) -> bool:
        """Return True if audio is already connected (Mute/Unmute button present)."""
        try:
            if not self.page:
                return False
            for sel in [
                "button[aria-label*='mute' i]",
                "button:has-text('Mute')",
                "button:has-text('Unmute')",
                ".audio-option-button",
                "[class*='audio-control-button']",
            ]:
                loc = self.page.locator(sel)
                if await loc.count() > 0 and await loc.first.is_visible():
                    return True
            return False
        except Exception:
            return False

    # ── Post-Admission Audio+Video Setup ─────────────────────

    async def setup_audio_and_video(self):
        """Join system audio (computer audio, muted) and start video feed after entering the meeting room."""
        self.log("ACT", "🔊 Joining system audio and video...")

        # ── Step 1: Aggressive multi-strategy system audio connection ──
        for attempt in range(3):
            if await self.is_audio_connected():
                break

            # 1a. Click toolbar "Join Audio" button to open audio dialog
            toolbar_selectors = [
                "button:has-text('Join Audio')",
                "[aria-label*='join audio' i]",
                ".footer-button-base:has-text('Join Audio')",
                "#wc-footer button:has-text('Join Audio')",
                ".join-audio-container",
                "button[class*='join-audio']",
                "[class*='audio-option']",
                "button[aria-label*='audio' i]:not([aria-label*='mute' i])",
            ]
            for sel in toolbar_selectors:
                if await self.try_click(sel, 2000, "Toolbar Join Audio"):
                    await asyncio.sleep(1.2)
                    break

            # 1b. Click "Join Audio by Computer" / "Computer Audio" in the modal
            modal_selectors = [
                "button:has-text('Join Audio by Computer')",
                "button:has-text('Computer Audio')",
                "button.join-audio-by-win-btn",
                "[aria-label*='Join Audio by Computer' i]",
                "[aria-label*='Computer Audio' i]",
                ".join-dialog button:has-text('Audio')",
                "button:has-text('Join with Computer Audio')",
                "button[class*='join-audio-by-computer']",
            ]
            for sel in modal_selectors:
                if await self.try_click(sel, 3000, "Join Audio by Computer"):
                    await asyncio.sleep(1.2)
                    break

            # 1c. JS fallback — forcibly click any audio join button
            if not await self.is_audio_connected():
                try:
                    clicked = await self.page.evaluate("""
                        () => {
                            const texts = ['Join Audio by Computer', 'Computer Audio', 'Join with Computer Audio', 'Join Audio'];
                            for (const btn of document.querySelectorAll('button')) {
                                const t = btn.textContent.trim();
                                if (texts.some(x => t.includes(x))) { btn.click(); return true; }
                            }
                            return false;
                        }
                    """)
                    if clicked:
                        self.log("ACT", "🔊 JS-click: audio join button found and clicked")
                        await asyncio.sleep(1.0)
                except Exception:
                    pass

            # 1d. Keyboard shortcut Alt+A as last resort
            if not await self.is_audio_connected():
                try:
                    await self.page.keyboard.press("Alt+a")
                    await asyncio.sleep(1.0)
                    self.log("ACT", "🔊 Alt+A shortcut attempted for audio")
                except Exception:
                    pass

            await asyncio.sleep(0.8)

        if await self.is_audio_connected():
            self.log("OK", "✅ System audio joined successfully")
        else:
            self.log("WARN", "⚠️ Could not confirm audio connection — proceeding anyway")

        # ── Step 2: Always mute mic (bots are silent listeners) ──
        await self.ensure_muted()

        # ── Step 3: Start video feed immediately on join ──
        for attempt in range(3):
            if await self.ensure_video_on():
                self.log("OK", "✅ Video stream started successfully")
                break
            await asyncio.sleep(1.5)
        else:
            self.log("WARN", "⚠️ Could not start video stream on join")

        # ── Step 4: Dismiss any remaining popups/tooltips ──
        for sel in [
            "button:has-text('Got it')",
            "button:has-text('Later')",
            "button:has-text('OK')",
            "[aria-label='Close']",
        ]:
            await self.try_click(sel, 1500)

    # ── Main Behavior Loop ────────────────────────────────────

    async def run(self):
        try:
            await self.open_page()
            joined = await self.join()
            if not joined:
                self.log("ERR", "Failed to join. Exiting.")
                return

            # Schedule events
            start = time.time()
            video_is_on      = False
            # First video start: almost immediately (3-8s after joining) — bots stream video right away
            next_video_event = start + random.randint(3, 8)
            next_chat        = start + random.randint(self.chat_min, self.chat_max)
            next_reaction    = start + random.randint(60, 180)
            raise_hand_at    = start + random.randint(120, 600) if random.random() < 0.3 else float("inf")
            # Mic mute re-check every 30s to ensure it stays muted
            next_mute_check  = start + 8
            # Re-check audio connection after 15s to ensure it's established
            next_audio_check = start + 15
            was_waiting      = False  # track if we were in waiting room

            while True:
                now = time.time()

                # Check timeout
                if now - start >= self.timeout:
                    self.log("INFO", "Timeout reached. Exiting.")
                    break

                # Check if still in meeting
                if not await self.is_alive():
                    self.log("WARN", "Meeting ended or removed.")
                    break

                # ── Waiting Room → Admitted transition ──
                current_status = await self.check_join_status()
                if current_status == "WAITING_ROOM":
                    if not was_waiting:
                        self.log("INFO", "⏳ In waiting room — waiting to be admitted...")
                        was_waiting = True
                    await asyncio.sleep(3)
                    continue
                elif was_waiting and current_status == "JOINED":
                    self.log("OK", "🚪 Admitted from waiting room! Joining audio (muted)...")
                    was_waiting = False
                    await self.setup_audio_and_video()
                    # Send greeting
                    await self.send_chat(random.choice(CHAT_MESSAGES["greetings"]))
                    self.joined_at = time.time()
                    next_chat = time.time() + random.randint(self.chat_min, self.chat_max)

                # ── Random Video Toggle (on/off at natural intervals) ──
                if now >= next_video_event:
                    if not video_is_on:
                        # Turn ON — bot appears on camera
                        turned_on = await self.ensure_video_on()
                        if turned_on:
                            video_is_on = True
                            # Stay on camera for 4–8 minutes (bots stream video most of the time)
                            on_dur = random.randint(240, 480)
                            next_video_event = now + on_dur
                            self.log("ACT", f"📹 Camera ON — streaming for ~{on_dur//60}m {on_dur%60}s")
                        else:
                            # Couldn't start — retry sooner
                            next_video_event = now + random.randint(8, 20)
                    else:
                        # Turn OFF — bot briefly steps away (realistic break)
                        await self.turn_off_video()
                        video_is_on = False
                        # Only off-camera for 15–30 seconds (short break)
                        off_dur = random.randint(15, 30)
                        next_video_event = now + off_dur
                        self.log("ACT", f"📷 Camera OFF — returning in ~{off_dur}s")

                # ── Mic always muted — re-enforce every 30s ──
                if now >= next_mute_check:
                    await self.ensure_muted()
                    next_mute_check = now + 30

                # ── Audio connection health check — reconnect if dropped ──
                if now >= next_audio_check:
                    if not await self.is_audio_connected():
                        self.log("WARN", "🔴 Audio disconnected — attempting reconnect...")
                        await self.setup_audio_and_video()
                    next_audio_check = now + 60

                # Send chat message
                if now >= next_chat:
                    msg = random.choice(self.messages)
                    await self.send_chat(msg)
                    interval = random.randint(self.chat_min, self.chat_max)
                    next_chat = now + interval
                    self.log("INFO", f"Next chat in {interval}s")

                # Send emoji reaction
                if now >= next_reaction and random.random() < 0.4:
                    await self.send_reaction()
                    next_reaction = now + random.randint(90, 300)

                # Raise hand (occasional)
                if now >= raise_hand_at:
                    await self.raise_hand()
                    raise_hand_at = float("inf")  # only once per session

                await asyncio.sleep(1)

        except asyncio.CancelledError:
            self.log("WARN", "Task cancelled.")
        except Exception as e:
            self.log("ERR", f"Unexpected error: {e}")
        finally:
            self.alive = False
            self.log("INFO", f"Exited. Messages sent: {self.msgs_sent}")
            try:
                await self.page.close()
            except Exception:
                pass


# ══════════════════════════════════════════════════════════════
# BotManager — Orchestrates All Bots in One Browser
# ══════════════════════════════════════════════════════════════

class BotManager:
    def __init__(self, args):
        self.args      = args
        self.bots      = []
        self.tasks     = []
        self.browsers  = []
        self.browser   = None
        self._shutdown = asyncio.Event()

    async def run(self):
        from playwright.async_api import async_playwright

        # ── Load custom names / messages ──
        names = list(HUMAN_NAMES)
        if self.args.names_file and Path(self.args.names_file).exists():
            with open(self.args.names_file) as f:
                names = json.load(f)
            log("OK", f"Loaded {len(names)} custom names.", "SETUP")

        messages = list(getattr(self, "custom_messages", None) or ALL_MESSAGES)
        if self.args.messages_file and Path(self.args.messages_file).exists():
            with open(self.args.messages_file) as f:
                messages = json.load(f)
            log("OK", f"Loaded {len(messages)} custom messages.", "SETUP")

        # ── Prepare photo portrait video pool (auto-generate unique per-bot if needed) ──
        video_pool_files = prepare_video_pool(
            self.args.avatar_dir, self.args.video_pool,
            bot_count=self.args.count if self.args.per_bot_browser else 1
        )
        if video_pool_files:
            log("OK", f"Video Pool active: {len(video_pool_files)} bot video feed(s) ready.", "SETUP")

        # Shuffle and pick names (handle count > name pool)
        random.shuffle(names)
        selected_names = []
        for i in range(self.args.count):
            selected_names.append(names[i % len(names)])
            if i >= len(names) - 1:
                # Append index suffix to avoid duplicate names
                selected_names[-1] = f"{selected_names[-1]} {i // len(names) + 2}"

        meeting_url = to_web_client_url(self.args.meeting_url)
        if not meeting_url:
            log("ERR", "No meeting URL provided. Use --meeting-url or MEETING_URL env.", "SETUP")
            sys.exit(1)

        log("SYS", f"Meeting URL : {meeting_url}", "MANAGER")
        log("SYS", f"Bot Count   : {self.args.count}", "MANAGER")
        log("SYS", f"Headless    : {self.args.headless}", "MANAGER")
        log("SYS", f"Chat Interval: {self.args.chat_min}-{self.args.chat_max}s", "MANAGER")
        log("SYS", f"Join Delay  : {self.args.join_delay_min}-{self.args.join_delay_max}s apart", "MANAGER")
        log("SYS", f"Timeout     : {self.args.timeout}s", "MANAGER")

        async with async_playwright() as pw:
            # Launch shared browser if not using per-bot-browser mode
            if not self.args.per_bot_browser:
                shared_video = video_pool_files[0] if video_pool_files else self.args.mock_video
                browser_args = get_browser_args(shared_video)
                self.browser = await pw.chromium.launch(
                    headless=self.args.headless,
                    args=browser_args,
                    ignore_default_args=["--enable-automation"],
                )
                self.browsers.append(self.browser)
                log("OK", f"Chromium browser launched (shared instance, video: {Path(shared_video).name}).", "MANAGER")

            VIEWPORTS = [
                {"width": 1280, "height": 720},
                {"width": 1366, "height": 768},
                {"width": 1440, "height": 900},
                {"width": 1536, "height": 864},
                {"width": 1280, "height": 800},
                {"width": 1600, "height": 900},
                {"width": 1920, "height": 1080},
            ]

            # ── Spawn each bot ──
            for i, name in enumerate(selected_names):
                vp = VIEWPORTS[i % len(VIEWPORTS)]
                scale = random.choice([1.0, 1.25, 1.5])

                if self.args.per_bot_browser:
                    bot_video = video_pool_files[i % len(video_pool_files)] if video_pool_files else self.args.mock_video
                    bot_args = get_browser_args(bot_video)
                    b_inst = await pw.chromium.launch(
                        headless=self.args.headless,
                        args=bot_args,
                        ignore_default_args=["--enable-automation"],
                    )
                    self.browsers.append(b_inst)
                    context = await b_inst.new_context(
                        permissions=["camera", "microphone"],
                        viewport=vp,
                        device_scale_factor=scale,
                        user_agent=(
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            f"Chrome/{random.randint(123, 126)}.0.0.0 Safari/537.36"
                        ),
                        ignore_https_errors=True,
                    )
                else:
                    context = await self.browser.new_context(
                        permissions=["camera", "microphone"],
                        viewport=vp,
                        device_scale_factor=scale,
                        user_agent=(
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            f"Chrome/{random.randint(123, 126)}.0.0.0 Safari/537.36"
                        ),
                        ignore_https_errors=True,
                    )

                await context.grant_permissions(["camera", "microphone"])

                bot = HumanBot(
                    name            = name,
                    context         = context,
                    meeting_url     = meeting_url,
                    chat_min        = self.args.chat_min,
                    chat_max        = self.args.chat_max,
                    messages        = messages,
                    timeout         = self.args.timeout,
                    bot_index       = i,
                    video_delay_min = self.args.video_delay_min,
                    video_delay_max = self.args.video_delay_max,
                )
                self.bots.append(bot)

                # Launch bot task
                task = asyncio.create_task(bot.run())
                self.tasks.append(task)

                log("JOIN", f"Bot {i+1}/{self.args.count}: '{name}' starting...", "MANAGER")

                # Staggered join — humans don't all join at the same time
                if i < len(selected_names) - 1:
                    delay = random.randint(
                        self.args.join_delay_min,
                        self.args.join_delay_max
                    )
                    log("INFO", f"Next bot joins in {delay}s...", "MANAGER")
                    await asyncio.sleep(delay)

            log("OK", f"All {self.args.count} bots spawned. Running...", "MANAGER")

            # ── Monitor until all bots finish ──
            try:
                await asyncio.gather(*self.tasks, return_exceptions=True)
            except asyncio.CancelledError:
                pass
            finally:
                await self.shutdown()

    async def shutdown(self):
        log("SYS", "Shutting down all bots...", "MANAGER")
        for task in self.tasks:
            if not task.done():
                task.cancel()
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
        for b in self.browsers:
            try:
                await b.close()
            except Exception:
                pass
        log("OK", "Browsers closed.", "MANAGER")

        # Print summary
        total_msgs = sum(b.msgs_sent for b in self.bots)
        log("SYS", f"── Session Summary ─────────────────────────", "MANAGER")
        log("SYS", f"  Total bots    : {len(self.bots)}", "MANAGER")
        log("SYS", f"  Total messages: {total_msgs}", "MANAGER")
        for b in self.bots:
            log("SYS", f"  {b.name[:20].ljust(20)}: {b.msgs_sent} msgs", "MANAGER")


# ── Entry Point ──────────────────────────────────────────────

async def _main():
    args = parse_args()
    manager = BotManager(args)

    loop = asyncio.get_event_loop()

    def handle_signal():
        log("WARN", "Shutdown signal received. Stopping...", "MANAGER")
        for task in asyncio.all_tasks(loop):
            task.cancel()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, handle_signal)
        except NotImplementedError:
            pass  # Windows doesn't support add_signal_handler for SIGINT

    await manager.run()


def main():
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        print("\n[MANAGER] Interrupted by user.")
    except Exception as e:
        print(f"\n[MANAGER] Fatal: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
