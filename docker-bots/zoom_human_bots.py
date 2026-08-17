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
import math
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
    p.add_argument("--video-delay-min",type=int,  default=int(os.getenv("VIDEO_DELAY_MIN", "10")), help="Min seconds after joining before first video start")
    p.add_argument("--video-delay-max",type=int,  default=int(os.getenv("VIDEO_DELAY_MAX", "45")), help="Max seconds after joining before first video start")
    p.add_argument("--video-on-min",   type=int,  default=int(os.getenv("VIDEO_ON_MIN", "3")), help="Min seconds camera stays ON during a burst (default: 3)")
    p.add_argument("--video-on-max",   type=int,  default=int(os.getenv("VIDEO_ON_MAX", "5")), help="Max seconds camera stays ON during a burst (default: 5)")
    p.add_argument("--video-off-min",  type=int,  default=int(os.getenv("VIDEO_OFF_MIN", "60")), help="Min seconds camera stays OFF between bursts")
    p.add_argument("--video-off-max",  type=int,  default=int(os.getenv("VIDEO_OFF_MAX", "240")), help="Max seconds camera stays OFF between bursts")
    p.add_argument("--timeout",        type=int,  default=int(os.getenv("BOT_TIMEOUT", "3600")))
    p.add_argument("--headless",       action="store_true", default=None)
    p.add_argument("--no-headless",    action="store_true", default=False, help="Run browser with visible windows")
    p.add_argument("--mock-video",     type=str,  default=os.getenv("MOCK_VIDEO", "./mock_face.y4m"))
    p.add_argument("--dataset-dir",    type=str,  default=os.getenv("DATASET_DIR", "./facial_dataset"), help="Folder containing facial expression dataset videos")
    p.add_argument("--max-active-video", type=int, default=int(os.getenv("MAX_ACTIVE_VIDEO", "50")), help="Max bots streaming active webcam video simultaneously")
    p.add_argument("--video-ratio",    type=float,default=float(os.getenv("VIDEO_RATIO", "1.0")), help="Ratio of bots with video enabled (e.g. 1.0 = 100% of bots)")
    p.add_argument("--video-cycle-interval", type=int, default=int(os.getenv("VIDEO_CYCLE_INTERVAL", "0")), help="Seconds between camera rotations (0 = fixed)")
    p.add_argument("--avatar-dir",     type=str,  default=os.getenv("AVATAR_DIR", "./avatars"), help="Folder containing photo portraits")
    p.add_argument("--shared-browser", action="store_true", default=False, help="Share single browser instance across bots (may cause session conflicts)")
    p.add_argument("--per-bot-browser",action="store_true", default=None, help="Launch independent browser instance per bot for complete session isolation (default: True)")
    p.add_argument("--auto-replace",   action="store_true", default=None, help="Automatically spawn fresh replacement bot if any bot disconnects or fails (default: True)")
    p.add_argument("--names-file",     type=str,  default=None)
    p.add_argument("--messages-file",  type=str,  default=None)
    
    args = p.parse_args()
    if args.no_headless:
        args.headless = False
    elif args.headless is None:
        args.headless = os.getenv("HEADLESS", "true").lower() == "true"

    if args.shared_browser:
        args.per_bot_browser = False
    elif args.per_bot_browser is None:
        args.per_bot_browser = os.getenv("PER_BOT_BROWSER", "true").lower() == "true"

    if args.auto_replace is None:
        args.auto_replace = os.getenv("AUTO_REPLACE", "true").lower() == "true"
    return args


# ── Video Pool Preparation ────────────────────────────────────

def prepare_video_pool(dataset_dir: str = "./facial_dataset", avatar_dir: str = "./avatars",
                       pool_dir: str = "./video_pool", bot_count: int = 1) -> list:
    """Scan facial expression dataset → Y4M snippets, or avatar images → Y4M."""
    dataset_path = resolve_path(dataset_dir)
    avatars_path = resolve_path(avatar_dir)
    pool_path = resolve_path(pool_dir)
    pool_path.mkdir(parents=True, exist_ok=True)

    # 1. Process Facial Expression Dataset videos if present in dataset_dir or pool_dir
    valid_vid_exts = {".mp4", ".avi", ".mov", ".webm", ".mkv", ".m4v"}
    source_dir = None
    if dataset_path.exists():
        vid_files = [f for f in dataset_path.rglob("*") if f.is_file() and f.suffix.lower() in valid_vid_exts]
        if vid_files:
            source_dir = dataset_path
    if not source_dir and pool_path.exists():
        vid_files = [f for f in pool_path.glob("*") if f.is_file() and f.suffix.lower() in valid_vid_exts]
        if vid_files:
            source_dir = pool_path

    if source_dir:
        vid_files = [f for f in source_dir.rglob("*") if f.is_file() and f.suffix.lower() in valid_vid_exts]
        if vid_files:
            try:
                from dataset_to_video import process_dataset_directory
                needed = max(bot_count, 5)
                existing_snippets = list(pool_path.glob("*.y4m"))
                if len(existing_snippets) < needed:
                    log("INFO", f"Extracting realistic snippets from facial expression dataset ({len(vid_files)} source videos)...", "SETUP")
                    processed = process_dataset_directory(str(source_dir), str(pool_path), count=needed)
                    if processed:
                        log("OK", f"Facial dataset active: {len(processed)} snippet video(s) ready in {pool_path}/", "SETUP")
                        return [str(f.resolve()) for f in sorted(pool_path.glob("*.y4m"))]
            except Exception as e:
                log("WARN", f"Facial expression dataset conversion warning: {e}", "SETUP")

    # 2. Convert any avatar photos to Y4M if present
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

def get_browser_args(mock_video: Optional[str] = None) -> list:
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

    if mock_video:
        video = resolve_path(mock_video)
        if video.exists() and video.is_file():
            args.append(f"--use-file-for-fake-video-capture={video.resolve()}")
            log("OK", f"Mock video active: {video.resolve()}", "SETUP")
        else:
            log("INFO", f"Mock video file not found at {mock_video}. Using Chrome default fake video stream.", "SETUP")
    else:
        log("INFO", "Using Chrome default fake video stream.", "SETUP")

    return args


# ══════════════════════════════════════════════════════════════
# HumanBot — Single Browser Context (Tab)
# ══════════════════════════════════════════════════════════════

class HumanBot:
    def __init__(self, name: str, context, meeting_url: str,
                 chat_min: int, chat_max: int,
                 messages: list, timeout: int, bot_index: int,
                 video_delay_min: int = 10, video_delay_max: int = 45,
                 video_on_min: int = 3, video_on_max: int = 5,
                 video_off_min: int = 60, video_off_max: int = 240,
                 video_enabled: bool = True):
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
        self.video_on_min    = video_on_min
        self.video_on_max    = video_on_max
        self.video_off_min   = video_off_min
        self.video_off_max   = video_off_max
        self.video_enabled   = video_enabled
        self.page            = None
        self.alive           = False
        self.msgs_sent       = 0
        self.joined_at       = None

        import urllib.parse
        parsed = urllib.parse.urlparse(self.url)
        qs = urllib.parse.parse_qs(parsed.query)
        self.passcode = qs.get("pwd", [""])[0]

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

        // 6. OneTrust Cookie Auto-Bypass & DOM Suppression
        try {
            const style = document.createElement('style');
            style.id = 'zomo-onetrust-suppress';
            style.textContent = `
                #onetrust-consent-sdk, #onetrust-banner-sdk, .onetrust-pc-dark-filter,
                #onetrust-group-container, .optanon-alert-box-wrapper, #onetrust-pc-sdk {
                    display: none !important;
                    visibility: hidden !important;
                    opacity: 0 !important;
                    pointer-events: none !important;
                    z-index: -99999 !important;
                }
            `;
            (document.head || document.documentElement).appendChild(style);

            const nukeOneTrust = () => {
                const acceptBtn = document.querySelector('#onetrust-accept-btn-handler') ||
                                  document.querySelector('.onetrust-close-btn-handler') ||
                                  document.querySelector('button[aria-label="Close"]');
                if (acceptBtn) {
                    try { acceptBtn.click(); } catch(e) {}
                }
                const ids = ['onetrust-consent-sdk', 'onetrust-banner-sdk', 'onetrust-pc-dark-filter', 'onetrust-group-container'];
                ids.forEach(id => {
                    const el = document.getElementById(id);
                    if (el) el.remove();
                });
                document.querySelectorAll('.onetrust-pc-dark-filter, [class*="onetrust"]').forEach(el => el.remove());
            };

            if (document.readyState === 'loading') {
                document.addEventListener('DOMContentLoaded', nukeOneTrust);
            } else {
                nukeOneTrust();
            }
            const ob = new MutationObserver(nukeOneTrust);
            ob.observe(document.documentElement, { childList: true, subtree: true });
        } catch (e) {}
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

    async def setup_audio_and_video(self):
        """Configure microphone (always muted) and ensure camera starts OFF (random bursts occur later)."""
        await self.ensure_muted()
        # Bots start with camera OFF, then randomly turn on for short instances
        await self.turn_off_video()

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

        try:
            removed = await self.page.evaluate("""() => {
                let clicked = false;
                const acceptBtn = document.querySelector('#onetrust-accept-btn-handler') ||
                                  document.querySelector('button#onetrust-accept-btn-handler') ||
                                  document.querySelector('.onetrust-close-btn-handler');
                if (acceptBtn) {
                    acceptBtn.click();
                    clicked = true;
                }
                const ids = [
                    'onetrust-banner-sdk',
                    'onetrust-consent-sdk',
                    'onetrust-pc-dark-filter',
                    'onetrust-group-container'
                ];
                ids.forEach(id => {
                    const el = document.getElementById(id);
                    if (el) { el.remove(); clicked = true; }
                });
                document.querySelectorAll('.onetrust-pc-dark-filter, [class*="onetrust"], [id*="onetrust"]').forEach(el => {
                    el.remove();
                    clicked = true;
                });
                return clicked;
            }""")
            if removed:
                return True
        except Exception:
            pass

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

        for sel in cookie_selectors:
            try:
                loc = self.page.locator(sel)
                cnt = await loc.count()
                if cnt > 0:
                    for idx in range(cnt):
                        item = loc.nth(idx)
                        if await item.is_visible():
                            try:
                                await item.click(timeout=1000)
                            except Exception:
                                try:
                                    await item.click(force=True, timeout=1000)
                                except Exception:
                                    await item.evaluate("el => el.click()")
                            self.log("ACT", f"✓ Dismissed cookie banner via: {sel}")
                            return True
            except Exception:
                continue

        return False

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
            await self.page.goto(self.url, wait_until="domcontentloaded", timeout=35000)
        except Exception as e:
            self.log("ERR", f"Navigation failed: {e}")
            return False

        await asyncio.sleep(random.uniform(1.0, 2.0))
        await self.dismiss_cookie_banner()

        # ── Step 1: Dismiss desktop app prompt / click browser join link if present ──
        browser_join = [
            "text=Join from Your Browser",
            "text=join from your browser",
            "text=Join from your browser",
            "a[href*='wc/join']",
            "a[href*='/wc/']",
            "button:has-text('Join from Your Browser')",
        ]
        for sel in browser_join:
            if await self.try_click(sel, 2000, "Browser join link"):
                await asyncio.sleep(random.uniform(1.5, 2.5))
                break

        await self.dismiss_cookie_banner()

        # ── Step 2: Fill display name (with robust waiting for React SPA) ──
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
        self.log("INFO", "Waiting for Zoom Web Client join form...")
        for attempt in range(30):
            await self.dismiss_cookie_banner()
            # If already joined or waiting, break early
            st = await self.check_join_status()
            if st in ("JOINED", "WAITING_ROOM"):
                break

            # If still on launch page, retry browser join link
            if attempt in (3, 7, 12):
                for sel in browser_join:
                    if await self.try_click(sel, 1500, "Browser join link"):
                        break

            filled = await self.find_and_fill(name_selectors, self.name)
            if filled:
                self.log("OK", f"Name entered: {self.name}")
                break
            await asyncio.sleep(1.0)

        if not filled:
            self.log("WARN", "Could not fill name field automatically. Checking if passcode or room already joined.")

        await asyncio.sleep(random.uniform(0.3, 0.7))
        await self.dismiss_cookie_banner()

        # ── Step 3: Accept Terms of Service ──
        tos_selectors = [
            "#wc_agree1",
            "input[type='checkbox'][id*='agree']",
            "input[type='checkbox']",
            "text=I agree",
        ]
        for sel in tos_selectors:
            await self.try_click(sel, 1500, "ToS checkbox")

        await asyncio.sleep(random.uniform(0.3, 0.6))

        # ── Step 4: Simulate human mouse gesture to satisfy reCAPTCHA v3 score ──
        await self.human_mouse_move()
        await asyncio.sleep(random.uniform(0.3, 0.6))

        # ── Step 5: Click Join ──
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

        # ── Step 6: Passcode Check & Auto-Fill ──
        passcode_selectors = [
            "#inputpasscode",
            "input[name='inputpasscode']",
            "input[placeholder*='passcode' i]",
            "input[placeholder*='Passcode']",
            "input[type='password']",
        ]
        await asyncio.sleep(2.0)
        for p_sel in passcode_selectors:
            try:
                loc = self.page.locator(p_sel)
                if await loc.count() > 0 and await loc.first.is_visible():
                    if getattr(self, "passcode", None):
                        self.log("INFO", "🔑 Entering meeting passcode...")
                        await loc.first.clear()
                        await self.human_type(loc.first, self.passcode)
                        for sel in join_selectors:
                            if await self.try_click(sel, 2000, "Join with Passcode"):
                                break
                    else:
                        self.log("WARN", "🔒 Passcode prompt requested. Check if passcode was provided.")
                    break
            except Exception:
                pass

        self.log("INFO", "Waiting for meeting room connection...")
        await asyncio.sleep(random.uniform(5, 8))

        # ── Step 7: Check Status & Handle Audio (with retry for BotGuard) ──
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
        if not self.page:
            return False

        # Check if input is already visible
        already_open = [
            "div.ql-editor[contenteditable='true']",
            "div[contenteditable='true']",
            "div[role='textbox']",
            "textarea[placeholder*='message' i]",
            "[aria-label*='type message' i]",
            "[class*='chat-box'] [contenteditable='true']",
        ]
        for sel in already_open:
            try:
                loc = self.page.locator(sel)
                if await loc.count() > 0 and await loc.first.is_visible():
                    return True
            except Exception:
                pass

        await self.wake_toolbar()
        await asyncio.sleep(0.3)

        # Try clicking the Chat button in toolbar
        chat_btn_selectors = [
            "#wc-footer button[aria-label*='Chat' i]",
            "#wc-footer button[aria-label*='chat' i]",
            "#wc-footer button:has-text('Chat')",
            "button[aria-label*='open the chat pane' i]",
            "button[aria-label='Chat']",
            "button[aria-label*='Chat' i]",
            "button:has-text('Chat')",
            ".footer-button-base:has-text('Chat')",
            "[class*='chat-button']",
            "[class*='ChatButton']",
            "button[title*='Chat' i]",
        ]
        for sel in chat_btn_selectors:
            if await self.try_click(sel, 1500):
                await asyncio.sleep(random.uniform(0.5, 1.0))
                break
        else:
            # Try More button menu if toolbar is compact
            more_selectors = ["#wc-footer button:has-text('More')", "#wc-footer button[aria-label*='More' i]", "button[aria-label='More']"]
            for m_sel in more_selectors:
                if await self.try_click(m_sel, 1200):
                    await asyncio.sleep(0.4)
                    await self.try_click("button:has-text('Chat'), [aria-label*='Chat' i], a:has-text('Chat')", 1500)
                    break

        # Fallback: Zoom web chat keyboard shortcut Alt+H
        try:
            await self.page.keyboard.press("Alt+h")
            await asyncio.sleep(0.6)
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
            if not self.page:
                return False

            # Ensure chat panel is open
            await self._open_chat_panel()

            # Find and use chat input
            input_selectors = [
                "div.ql-editor[contenteditable='true']",
                "div[role='textbox'][contenteditable='true']",
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
                        try:
                            await loc.first.scroll_into_view_if_needed()
                        except Exception:
                            pass
                        await loc.first.click()
                        await asyncio.sleep(0.2)

                        # Type message
                        try:
                            await loc.first.fill(message)
                        except Exception:
                            for char in message:
                                await loc.first.press(char)
                                await asyncio.sleep(max(0.015, random.gauss(0.04, 0.01)))

                        await asyncio.sleep(0.2)
                        await self.page.keyboard.press("Enter")
                        self.msgs_sent += 1
                        self.log("CHAT", f"💬 '{message}' (total: {self.msgs_sent})")
                        return True
                except Exception:
                    continue

            # JavaScript fallback injection if selectors were elusive
            try:
                sent = await self.page.evaluate("""
                    (text) => {
                        const el = document.querySelector(
                            'div.ql-editor, div[role="textbox"], div[contenteditable="true"], textarea[placeholder*="message" i], textarea'
                        );
                        if (el && el.offsetParent !== null) {
                            el.focus();
                            if (el.tagName.toLowerCase() === 'textarea' || el.tagName.toLowerCase() === 'input') {
                                el.value = text;
                                el.dispatchEvent(new Event('input', { bubbles: true }));
                            } else {
                                el.textContent = text;
                                el.dispatchEvent(new Event('input', { bubbles: true }));
                            }
                            el.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true }));
                            return true;
                        }
                        return false;
                    }
                """, message)
                if sent:
                    await self.page.keyboard.press("Enter")
                    self.msgs_sent += 1
                    self.log("CHAT", f"💬 '{message}' (total: {self.msgs_sent})")
                    return True
            except Exception:
                pass

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
            joined = False
            for attempt in range(1, 3):
                joined = await self.join()
                if joined:
                    break
                self.log("WARN", f"Join attempt {attempt} did not succeed. Retrying join with fresh page...")
                await asyncio.sleep(random.uniform(4.0, 7.0))
                try:
                    await self.page.close()
                except Exception:
                    pass
                await self.open_page()

            if not joined:
                self.log("ERR", "All join attempts failed. Exiting.")
                return

            # Schedule events
            start = time.time()
            video_is_on      = False
            # Staggered first video instance: spread across bots so they don't turn on together
            initial_video_delay = (self.index * random.randint(15, 30)) + random.randint(self.video_delay_min, self.video_delay_max)
            next_video_event = start + initial_video_delay
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

                # ── Persistent Video Health Check ──
                if self.video_enabled and now >= next_video_event:
                    if not await self.is_video_on():
                        self.log("ACT", "📹 Re-enabling webcam video stream...")
                        await self.ensure_video_on()
                    next_video_event = now + random.randint(30, 60)

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

        # ── Prepare photo portrait / facial expression video pool ──
        video_pool_files = prepare_video_pool(
            dataset_dir=getattr(self.args, "dataset_dir", "./facial_dataset"),
            avatar_dir=self.args.avatar_dir,
            pool_dir=self.args.video_pool,
            bot_count=self.args.count if getattr(self.args, "per_bot_browser", True) else 1
        )
        if video_pool_files:
            log("OK", f"Video Pool active: {len(video_pool_files)} bot video feed(s) ready.", "SETUP")

        # ── Hardware Video Concurrency ──
        max_active = getattr(self.args, "max_active_video", 50)
        ratio = getattr(self.args, "video_ratio", 1.0)
        if getattr(self.args, "count", 1) == 1:
            num_video_bots = 1
        else:
            num_video_bots = max(1, min(max_active, math.ceil(self.args.count * ratio)))

        video_bot_indices = set(random.sample(range(self.args.count), min(num_video_bots, self.args.count)))
        log("SYS", f"Hardware Saver: {len(video_bot_indices)} of {self.args.count} bot(s) will stream active webcam video.", "MANAGER")

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
            if not getattr(self.args, "per_bot_browser", True):
                shared_video = video_pool_files[0] if video_pool_files else getattr(self.args, "mock_video", "./mock_face.y4m")
                browser_args = get_browser_args(shared_video)
                self.browser = await pw.chromium.launch(
                    headless=getattr(self.args, "headless", True),
                    args=browser_args,
                    ignore_default_args=["--enable-automation"],
                )
                self.browsers.append(self.browser)
                vid_desc = Path(shared_video).name if shared_video and resolve_path(shared_video).exists() else "default fake stream"
                log("OK", f"Chromium browser launched (shared instance, video: {vid_desc}).", "MANAGER")

            # ── Spawn initial bots ──
            for i, name in enumerate(selected_names):
                is_video_bot = (i in video_bot_indices)
                await self._spawn_single_bot(pw, i, name, meeting_url, messages, video_pool_files, is_video_bot)

                # Staggered join — humans don't all join at the same time
                if i < len(selected_names) - 1:
                    delay = random.randint(
                        getattr(self.args, "join_delay_min", 8),
                        getattr(self.args, "join_delay_max", 25)
                    )
                    log("INFO", f"Next bot joins in {delay}s...", "MANAGER")
                    await asyncio.sleep(delay)

            # Optional dynamic camera rotation between bots
            cycle_sec = getattr(self.args, "video_cycle_interval", 0)
            if cycle_sec > 0 and self.args.count > 1:
                cycle_task = asyncio.create_task(self._video_cycling_loop())
                self.tasks.append(cycle_task)

            log("OK", f"All {self.args.count} initial bots spawned. Watchdog active...", "MANAGER")

            # ── Active Bot Supervisor / Auto-Replacement Watchdog ──
            start_time = time.time()
            max_timeout = getattr(self.args, "timeout", 3600)
            auto_replace = getattr(self.args, "auto_replace", True)

            try:
                while not self._shutdown.is_set():
                    await asyncio.sleep(4)
                    now = time.time()
                    if now - start_time >= max_timeout:
                        log("SYS", "Session timeout reached.", "MANAGER")
                        break

                    if auto_replace and not self._shutdown.is_set():
                        # Inspect bot tasks and detect premature exits
                        for i, (bot, task) in enumerate(list(zip(self.bots, self.tasks))):
                            if task.done() and not getattr(bot, "_replacement_spawned", False) and not self._shutdown.is_set():
                                bot._replacement_spawned = True
                                # Only replace if meeting session is still ongoing
                                if now - start_time < max_timeout - 20:
                                    used_names = {b.name for b in self.bots if b.alive}
                                    available = [n for n in names if n not in used_names]
                                    new_name = random.choice(available) if available else f"{random.choice(names)} {len(self.bots)+1}"
                                    log("WARN", f"🔄 Bot '{bot.name}' disconnected or exited. Spawning fresh replacement bot '{new_name}' in 4s...", "MANAGER")
                                    await asyncio.sleep(4)
                                    if not self._shutdown.is_set():
                                        new_idx = len(self.bots)
                                        is_video = (new_idx in video_bot_indices) or (getattr(self.args, "video_ratio", 1.0) >= 0.5)
                                        await self._spawn_single_bot(pw, new_idx, new_name, meeting_url, messages, video_pool_files, is_video)
                                        log("OK", f"✅ Replacement bot '{new_name}' deployed to maintain target farm size ({self.args.count} bots).", "MANAGER")

                    if all(t.done() for t in self.tasks) and len(self.tasks) > 0 and not auto_replace:
                        break
            except asyncio.CancelledError:
                pass
            finally:
                await self.shutdown()

    async def _spawn_single_bot(self, pw, index: int, name: str, meeting_url: str, messages: list, video_pool_files: list, is_video_bot: bool):
        VIEWPORTS = [
            {"width": 1280, "height": 720},
            {"width": 1366, "height": 768},
            {"width": 1440, "height": 900},
            {"width": 1536, "height": 864},
            {"width": 1280, "height": 800},
            {"width": 1600, "height": 900},
            {"width": 1920, "height": 1080},
        ]
        vp = VIEWPORTS[index % len(VIEWPORTS)]
        scale = random.choice([1.0, 1.25, 1.5])

        if getattr(self.args, "per_bot_browser", True):
            bot_video = video_pool_files[index % len(video_pool_files)] if video_pool_files else getattr(self.args, "mock_video", "./mock_face.y4m")
            bot_args = get_browser_args(bot_video)
            b_inst = await pw.chromium.launch(
                headless=getattr(self.args, "headless", True),
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
            chat_min        = getattr(self.args, "chat_min", 20),
            chat_max        = getattr(self.args, "chat_max", 60),
            messages        = messages,
            timeout         = getattr(self.args, "timeout", 3600),
            bot_index       = index,
            video_delay_min = getattr(self.args, "video_delay_min", 10),
            video_delay_max = getattr(self.args, "video_delay_max", 45),
            video_on_min    = getattr(self.args, "video_on_min", 3),
            video_on_max    = getattr(self.args, "video_on_max", 5),
            video_off_min   = getattr(self.args, "video_off_min", 60),
            video_off_max   = getattr(self.args, "video_off_max", 240),
            video_enabled   = is_video_bot,
        )
        self.bots.append(bot)

        # Launch bot task
        task = asyncio.create_task(bot.run())
        self.tasks.append(task)
        log("JOIN", f"Bot {index+1}/{self.args.count}: '{name}' starting (webcam: {'ON' if is_video_bot else 'OFF'})...", "MANAGER")
        return bot, task

    async def _video_cycling_loop(self):
        """Periodically rotate active webcam video between bots to simulate natural human meeting behavior."""
        interval = getattr(self.args, "video_cycle_interval", 0)
        if interval <= 0:
            return
        log("SYS", f"Dynamic camera rotation active: cycling cameras every {interval}s.", "MANAGER")
        while True:
            await asyncio.sleep(interval)
            try:
                eligible_off = [b for b in self.bots if b.alive and not b.video_enabled]
                eligible_on = [b for b in self.bots if b.alive and b.video_enabled]
                if eligible_off and eligible_on:
                    turn_off_bot = random.choice(eligible_on)
                    turn_on_bot = random.choice(eligible_off)

                    turn_off_bot.video_enabled = False
                    await turn_off_bot.turn_off_video()
                    turn_off_bot.log("ACT", "📷 Stepped away: webcam paused")

                    await asyncio.sleep(random.uniform(2.0, 5.0))

                    turn_on_bot.video_enabled = True
                    await turn_on_bot.ensure_video_on()
                    turn_on_bot.log("ACT", "📹 Turned webcam back ON (facial expression active)")
            except asyncio.CancelledError:
                break
            except Exception as e:
                log("WARN", f"Camera cycling error: {e}", "MANAGER")

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
