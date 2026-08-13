"""
Zomo Multi-Bot — Zoom Web Client Automation via Playwright
Runs headless Chromium inside Docker containers to join Zoom meetings
as independent browser-based participants with fake media streams.

Usage:
  python zoom_web_bot.py \
    --meeting-url "https://zoom.us/j/1234567890?pwd=abc" \
    --name "Bot_1" \
    --chat-interval-min 15 \
    --chat-interval-max 45 \
    --messages "Hi everyone!" "Great point!" "Thanks for sharing."
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

# ── Logging ──────────────────────────────────────────────────

def log(level: str, msg: str, bot_name: str = "BOT"):
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    color_map = {
        "INFO": "\033[96m",   # cyan
        "OK":   "\033[92m",   # green
        "WARN": "\033[93m",   # yellow
        "ERR":  "\033[91m",   # red
        "CHAT": "\033[95m",   # magenta
        "ACT":  "\033[94m",   # blue
    }
    c = color_map.get(level, "\033[0m")
    print(f"{c}[{ts}] [{bot_name}] [{level}]\033[0m {msg}", flush=True)


# ── Argument Parsing ─────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(description="Zomo Multi-Bot: Zoom Web Client Participant")

    parser.add_argument("--meeting-url", type=str,
                        default=os.getenv("MEETING_URL", ""),
                        help="Zoom meeting join URL")
    parser.add_argument("--name", type=str,
                        default=os.getenv("BOT_NAME", f"Participant_{random.randint(100, 999)}"),
                        help="Display name for this bot")
    parser.add_argument("--chat-interval-min", type=int,
                        default=int(os.getenv("CHAT_INTERVAL_MIN", "15")),
                        help="Minimum seconds between chat messages")
    parser.add_argument("--chat-interval-max", type=int,
                        default=int(os.getenv("CHAT_INTERVAL_MAX", "45")),
                        help="Maximum seconds between chat messages")
    parser.add_argument("--messages", nargs="*",
                        default=None,
                        help="List of chat messages to randomly send")
    parser.add_argument("--headless", action="store_true",
                        default=None,
                        help="Run browser in headless mode")
    parser.add_argument("--no-headless", action="store_true",
                        default=False,
                        help="Run browser with visible windows")
    parser.add_argument("--mock-video", type=str,
                        default=os.getenv("MOCK_VIDEO", "/app/mock_face.y4m"),
                        help="Path to mock video file for fake webcam")
    parser.add_argument("--timeout", type=int,
                        default=int(os.getenv("BOT_TIMEOUT", "3600")),
                        help="Max runtime in seconds before auto-exit (default: 1 hour)")

    args = parser.parse_args()
    if args.no_headless:
        args.headless = False
    elif args.headless is None:
        args.headless = os.getenv("HEADLESS", "true").lower() == "true"

    # Load messages from env if not passed via CLI
    if not args.messages:
        env_msgs = os.getenv("CHAT_MESSAGES", "")
        if env_msgs:
            try:
                args.messages = json.loads(env_msgs)
            except json.JSONDecodeError:
                args.messages = [m.strip() for m in env_msgs.split("|") if m.strip()]

    # Fallback messages
    if not args.messages:
        args.messages = [
            "Hi everyone!",
            "Can you hear me?",
            "Great presentation!",
            "Interesting point.",
            "Thanks for sharing.",
            "I agree with that.",
            "Sorry I'm late.",
            "Good morning!",
            "Sounds good to me.",
            "Thanks for the update."
        ]

    return args


# ── Bot Logic ────────────────────────────────────────────────

async def human_type(page, selector, text, bot_name="BOT"):
    """Type text character by character with realistic delays."""
    element = page.locator(selector)
    await element.click()
    await asyncio.sleep(random.uniform(0.2, 0.5))

    for char in text:
        await element.press(char if len(char) == 1 else char)
        await asyncio.sleep(random.uniform(0.03, 0.12))

    await asyncio.sleep(random.uniform(0.1, 0.3))


async def dismiss_cookie_banner(page, bot_name="BOT"):
    """Aggressively dismiss or DOM-remove any cookie consent popups/overlays."""
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
            loc = page.locator(sel)
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
                        log("ACT", f"✓ Dismissed cookie banner via: {sel}", bot_name)
                        clicked = True
                        await asyncio.sleep(0.3)
                        break
        except Exception:
            continue

    # Failsafe: DOM removal of OneTrust backdrop/banner elements if still present
    try:
        await page.evaluate("""() => {
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


async def safe_click(page, selector, bot_name="BOT", timeout=5000, description="element"):
    """Safely click an element if it exists and is visible."""
    try:
        locator = page.locator(selector)
        await locator.wait_for(state="visible", timeout=timeout)
        await asyncio.sleep(random.uniform(0.2, 0.6))
        try:
            await locator.first.click(timeout=2000)
        except Exception:
            await locator.first.click(force=True, timeout=2000)
        log("ACT", f"Clicked: {description}", bot_name)
        return True
    except Exception:
        return False


async def wait_for_any(page, selectors, timeout=30000):
    """Wait for any of the given selectors to appear. Returns the first match."""
    for _ in range(int(timeout / 500)):
        for sel in selectors:
            try:
                loc = page.locator(sel)
                if await loc.count() > 0 and await loc.first.is_visible():
                    return sel
            except Exception:
                pass
        await asyncio.sleep(0.5)
    return None


async def is_meeting_alive(page):
    """Check if we're still in the meeting (not kicked or ended)."""
    # Common indicators that the meeting has ended
    end_indicators = [
        "text=This meeting has been ended",
        "text=The host has ended the meeting",
        "text=You have been removed from this meeting",
        "text=Meeting has ended",
        "text=The meeting has ended",
        "[class*='meeting-ended']",
    ]
    for sel in end_indicators:
        try:
            loc = page.locator(sel)
            if await loc.count() > 0 and await loc.first.is_visible():
                return False
        except Exception:
            pass
    return True


async def join_meeting(page, meeting_url, bot_name, mock_video_path):
    """Navigate to Zoom web client and join the meeting."""

    # Convert standard Zoom invite links to web client format
    # https://zoom.us/j/12345?pwd=abc → https://zoom.us/wc/join/12345?pwd=abc
    web_url = meeting_url
    if "/j/" in web_url and "/wc/" not in web_url:
        web_url = web_url.replace("/j/", "/wc/join/")
    elif "/wc/" not in web_url:
        # Try appending /wc/join/ path
        log("WARN", f"Non-standard URL format. Attempting direct navigation.", bot_name)

    log("INFO", f"Navigating to: {web_url}", bot_name)
    await page.goto(web_url, wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(random.uniform(1.5, 3.0))

    await dismiss_cookie_banner(page, bot_name)

    # ── Step 1: Dismiss "Open Zoom Meetings" desktop app prompt ──
    # Try clicking "Join from Your Browser" or "Cancel" on the launch dialog
    browser_join_selectors = [
        "text=Join from Your Browser",
        "text=join from your browser",
        "text=Join from your browser",
        "#joinBtn",
        "a[href*='wc/join']",
        "text=Cancel",
    ]

    for sel in browser_join_selectors:
        clicked = await safe_click(page, sel, bot_name, timeout=3000,
                                   description="Browser join link")
        if clicked:
            await asyncio.sleep(random.uniform(1, 2))
            break

    await asyncio.sleep(random.uniform(1, 2))
    await dismiss_cookie_banner(page, bot_name)

    # ── Step 2: Fill in the display name ──
    name_selectors = [
        "#inputname",
        "input[placeholder*='name']",
        "input[placeholder*='Name']",
        "input#join-confno-name",
        "[id*='name']",
    ]

    for sel in name_selectors:
        try:
            loc = page.locator(sel)
            if await loc.count() > 0 and await loc.first.is_visible():
                await loc.first.clear()
                await human_type(page, sel, bot_name, bot_name)
                log("OK", f"Entered name: {bot_name}", bot_name)
                break
        except Exception:
            continue

    await asyncio.sleep(random.uniform(0.5, 1.5))

    # ── Step 3: Accept Terms of Service ──
    tos_selectors = [
        "#wc_agree1",
        "input[type='checkbox']",
        "text=I agree",
        "[class*='terms'] input",
    ]
    for sel in tos_selectors:
        await safe_click(page, sel, bot_name, timeout=2000, description="Terms checkbox")

    await asyncio.sleep(random.uniform(0.3, 0.8))

    # ── Step 4: Click Join ──
    join_selectors = [
        "#joinBtn",
        "button:has-text('Join')",
        "button:has-text('join')",
        "input[value='Join']",
        "[class*='join-btn']",
        "button[type='submit']",
    ]

    for sel in join_selectors:
        clicked = await safe_click(page, sel, bot_name, timeout=3000, description="Join button")
        if clicked:
            break

    log("INFO", "Waiting for meeting room to load...", bot_name)
    await asyncio.sleep(random.uniform(5, 10))

    # ── Step 5: Handle audio/video permission prompts ──
    # A. Click toolbar "Join Audio" if modal is not open
    toolbar_audio = [
        "button:has-text('Join Audio')",
        "[aria-label*='join audio' i]",
        ".footer-button-base:has-text('Join Audio')",
        "#wc-footer button:has-text('Join Audio')",
        ".join-audio-container",
    ]
    for sel in toolbar_audio:
        clicked = await safe_click(page, sel, bot_name, timeout=3000, description="Toolbar Join Audio")
        if clicked:
            await asyncio.sleep(random.uniform(0.8, 1.5))
            break

    # B. Click "Join Audio by Computer" inside the modal dialog
    modal_audio = [
        "button:has-text('Join Audio by Computer')",
        "button:has-text('Computer Audio')",
        "button.join-audio-by-win-btn",
        "[aria-label*='Join Audio by Computer' i]",
        "[aria-label*='Computer Audio' i]",
    ]
    for sel in modal_audio:
        clicked = await safe_click(page, sel, bot_name, timeout=4000, description="Join Audio by Computer")
        if clicked:
            await asyncio.sleep(random.uniform(0.8, 1.5))
            break

    # C. Start webcam video feed
    await ensure_video_on(page, bot_name)

    await asyncio.sleep(random.uniform(1, 2))

    # Dismiss any remaining modals
    dismiss_selectors = [
        "button:has-text('Got it')",
        "button:has-text('OK')",
        "button:has-text('Close')",
        "button:has-text('Later')",
        "[class*='modal-close']",
        "[aria-label='Close']",
    ]
    for sel in dismiss_selectors:
        await safe_click(page, sel, bot_name, timeout=1500, description="Dismiss modal")

    log("OK", "Join sequence completed.", bot_name)


async def ensure_video_on(page, bot_name="BOT"):
    """Start video feed in Zoom web client."""
    try:
        video_selectors = [
            "button:has-text('Start Video')",
            "button[aria-label*='start' i][aria-label*='video' i]",
            "[aria-label*='start my video' i]",
            "[aria-label*='Start Video' i]",
            ".footer-button-base:has-text('Start Video')",
            "#wc-footer button:has-text('Start Video')",
            ".video-control-button--off",
            "button[class*='video-btn']",
        ]
        for sel in video_selectors:
            clicked = await safe_click(page, sel, bot_name, timeout=3000, description="Start Video")
            if clicked:
                await asyncio.sleep(0.8)
                # Handle preview modal if present
                for p_sel in ["button:has-text('Join with Video')", "button:has-text('Start Video')"]:
                    await safe_click(page, p_sel, bot_name, timeout=1500, description="Preview Video")
                log("OK", "📹 Webcam video stream started.", bot_name)
                return True

        # Keyboard fallback
        await page.keyboard.press("Alt+v")
        await asyncio.sleep(0.5)
        log("ACT", "📹 Video toggled via keyboard shortcut [Alt+V]", bot_name)
        return True
    except Exception as e:
        log("WARN", f"Could not start video: {e}", bot_name)
        return False


async def send_chat_message(page, message, bot_name):
    """Open chat panel and send a message."""
    try:
        # Try to open chat panel
        chat_open_selectors = [
            "button:has-text('Chat')",
            "[aria-label='open the chat pane']",
            "[aria-label='Chat']",
            "[class*='chat-button']",
            "button[data-tab='chat']",
        ]

        for sel in chat_open_selectors:
            clicked = await safe_click(page, sel, bot_name, timeout=2000, description="Chat button")
            if clicked:
                await asyncio.sleep(random.uniform(0.5, 1.0))
                break

        # Find the chat input
        chat_input_selectors = [
            "[class*='chat-box'] textarea",
            "textarea[placeholder*='message']",
            "textarea[placeholder*='Message']",
            "[class*='chat-input'] textarea",
            "[class*='chat'] textarea",
            "textarea[aria-label*='chat']",
            "textarea[aria-label*='Chat']",
            "#chatInputBox textarea",
            "#wc-container-right textarea",
            "div[class*='chat'] textarea",
        ]

        for sel in chat_input_selectors:
            try:
                loc = page.locator(sel)
                if await loc.count() > 0:
                    await loc.first.click()
                    await asyncio.sleep(random.uniform(0.2, 0.5))

                    # Type with human-like delays
                    for char in message:
                        await loc.first.press(char)
                        await asyncio.sleep(random.uniform(0.03, 0.10))

                    await asyncio.sleep(random.uniform(0.2, 0.5))
                    await loc.first.press("Enter")

                    log("CHAT", f"Sent: '{message}'", bot_name)
                    return True
            except Exception:
                continue

        log("WARN", "Could not find chat input field.", bot_name)
        return False

    except Exception as e:
        log("ERR", f"Chat error: {e}", bot_name)
        return False


async def run_bot(args):
    """Main bot execution flow."""
    from playwright.async_api import async_playwright

    bot_name = args.name
    log("INFO", f"Starting bot: {bot_name}", bot_name)
    log("INFO", f"Meeting URL: {args.meeting_url}", bot_name)
    log("INFO", f"Chat interval: {args.chat_interval_min}-{args.chat_interval_max}s", bot_name)
    log("INFO", f"Messages loaded: {len(args.messages)}", bot_name)
    log("INFO", f"Headless: {args.headless}", bot_name)
    log("INFO", f"Timeout: {args.timeout}s", bot_name)

    if not args.meeting_url:
        log("ERR", "No meeting URL provided! Set --meeting-url or MEETING_URL env var.", bot_name)
        sys.exit(1)

    async with async_playwright() as p:
        # Browser launch args for fake media
        launch_args = [
            "--autoplay-policy=no-user-gesture-required",
            "--use-fake-ui-for-media-stream",
            "--use-fake-device-for-media-stream",
            "--enable-usermedia-screen-capturing",
            "--allow-file-access-from-files",
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-web-security",
            "--disable-features=IsolateOrigins,site-per-process",
        ]

        # Add mock video file if it exists
        script_dir = Path(__file__).resolve().parent
        mock_video = Path(args.mock_video)
        if not mock_video.exists() and (script_dir / args.mock_video).exists():
            mock_video = script_dir / args.mock_video
        elif not mock_video.exists() and (script_dir / mock_video.name).exists():
            mock_video = script_dir / mock_video.name

        if mock_video.exists():
            launch_args.append(f"--use-file-for-fake-video-capture={mock_video.resolve()}")
            log("OK", f"Mock video loaded: {mock_video.resolve()}", bot_name)
        else:
            log("WARN", f"Mock video not found at {mock_video}. Using Chrome default color bars.", bot_name)

        # Launch browser
        browser = await p.chromium.launch(
            headless=args.headless,
            args=launch_args,
        )

        context = await browser.new_context(
            permissions=["camera", "microphone"],
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 720},
            ignore_https_errors=True,
        )

        page = await context.new_page()

        # Grant permissions
        await context.grant_permissions(["camera", "microphone"])

        try:
            # ── Phase 1: Join Meeting ──
            await join_meeting(page, args.meeting_url, bot_name, args.mock_video)

            # ── Phase 2: Verify we are in the meeting ──
            log("INFO", "Checking if meeting room loaded...", bot_name)
            await asyncio.sleep(random.uniform(3, 6))

            if not await is_meeting_alive(page):
                log("ERR", "Meeting appears to have ended or bot was rejected.", bot_name)
                return

            log("OK", "✅ Bot is in the meeting!", bot_name)

            # ── Phase 3: Main behavior loop ──
            start_time = time.time()
            messages_sent = 0
            next_chat_at = time.time() + random.randint(
                args.chat_interval_min, args.chat_interval_max
            )

            log("INFO", f"Next chat in {int(next_chat_at - time.time())}s", bot_name)

            while True:
                now = time.time()
                elapsed = now - start_time

                # Check timeout
                if elapsed >= args.timeout:
                    log("WARN", f"Timeout reached ({args.timeout}s). Exiting.", bot_name)
                    break

                # Check if meeting is still alive
                if not await is_meeting_alive(page):
                    log("WARN", "Meeting ended or bot removed. Exiting.", bot_name)
                    break

                # Send chat message
                if now >= next_chat_at:
                    msg = random.choice(args.messages)
                    success = await send_chat_message(page, msg, bot_name)

                    if success:
                        messages_sent += 1
                        log("INFO", f"Total messages sent: {messages_sent}", bot_name)

                    interval = random.randint(args.chat_interval_min, args.chat_interval_max)
                    next_chat_at = now + interval
                    log("INFO", f"Next chat in {interval}s", bot_name)

                # Small sleep to avoid busy loop
                await asyncio.sleep(1)

        except Exception as e:
            log("ERR", f"Fatal error: {e}", bot_name)
        finally:
            log("INFO", "Closing browser...", bot_name)
            await browser.close()
            log("OK", f"Bot exited. Messages sent: {messages_sent if 'messages_sent' in dir() else 0}", bot_name)


# ── Entry Point ──────────────────────────────────────────────

def main():
    args = parse_args()

    # Handle graceful shutdown
    def signal_handler(sig, frame):
        log("WARN", "Received shutdown signal. Exiting...", args.name)
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    asyncio.run(run_bot(args))


if __name__ == "__main__":
    main()
