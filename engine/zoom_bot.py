"""
Zomo ZoomBot Engine
Refactored bot with state machine, live callbacks, safety controls,
hybrid shortcut/coordinate execution, and simulation mode.
"""

import pyautogui
import pyperclip
import time
import random
import threading
from enum import Enum
from typing import Callable, Dict, Any, List, Optional
from datetime import datetime

from engine.config_manager import load_config, get_active_messages


class BotState(str, Enum):
    IDLE = "idle"
    JOINING = "joining"
    WAITING = "waiting"
    ACTIVE = "active"
    CAMERA_LIVE = "camera_live"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"


class ZoomBot:
    """
    Robust Zoom meeting bot with:
    - State machine for lifecycle tracking
    - Live event callbacks (for WebSocket streaming)
    - Hybrid execution: keyboard shortcuts OR coordinate clicking
    - Simulation mode for dry runs
    - Emergency stop via thread event
    - Humanized timing and mouse jitter
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None, log_callback: Optional[Callable] = None):
        self.config = config or load_config()
        self.log_callback = log_callback

        # State
        self.state = BotState.IDLE
        self.camera_on = False
        self.messages_sent = 0
        self.start_time: Optional[float] = None
        self.next_chat_time: float = 0
        self.next_cam_time: float = 0

        # Thread control
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        # Safety: disable pyautogui pause and enable failsafe
        pyautogui.PAUSE = 0.05
        pyautogui.FAILSAFE = True

    # ── Logging ──────────────────────────────────────────────

    def _log(self, level: str, message: str):
        """Emit a log entry via callback and print."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        entry = {
            "timestamp": timestamp,
            "level": level,
            "message": message,
            "state": self.state.value,
            "messages_sent": self.messages_sent,
            "camera_on": self.camera_on,
        }
        print(f"[{timestamp}] [{level.upper()}] {message}")
        if self.log_callback:
            try:
                self.log_callback(entry)
            except Exception:
                pass

    # ── Mouse & Keyboard Actions ─────────────────────────────

    def _click(self, x: int, y: int):
        """Click at coordinates with human-like jitter. Respects simulation mode."""
        if self.config["execution"].get("simulation_mode", False):
            self._log("sim", f"Simulated click at ({x}, {y})")
            return

        jitter = self.config["timing"].get("human_jitter", 2.0)
        duration = self.config["timing"].get("mouse_move_duration", 0.3)

        target_x = x + random.uniform(-jitter, jitter)
        target_y = y + random.uniform(-jitter, jitter)

        pyautogui.moveTo(target_x, target_y, duration=duration)
        time.sleep(random.uniform(0.05, 0.15))
        pyautogui.click()
        time.sleep(random.uniform(0.1, 0.3))

    def _hotkey(self, combo: str):
        """Press a hotkey combo like 'alt+v'. Respects simulation mode."""
        if self.config["execution"].get("simulation_mode", False):
            self._log("sim", f"Simulated hotkey: {combo}")
            return

        keys = combo.lower().split("+")
        pyautogui.hotkey(*keys)
        time.sleep(random.uniform(0.2, 0.5))

    def _type_message(self, message: str):
        """Type a message using clipboard paste for reliability."""
        if self.config["execution"].get("simulation_mode", False):
            self._log("sim", f"Simulated type: '{message}'")
            return

        pyperclip.copy(message)
        time.sleep(random.uniform(0.05, 0.15))
        pyautogui.hotkey("ctrl", "v")
        time.sleep(random.uniform(0.1, 0.2))
        pyautogui.press("enter")
        time.sleep(random.uniform(0.3, 0.8))

    # ── Bot Actions ──────────────────────────────────────────

    def _connect_audio(self):
        """Connect/unmute audio using configured mode."""
        mode = self.config["execution"].get("mode", "shortcut")
        if mode == "shortcut":
            shortcut = self.config["shortcuts"].get("toggle_mute", "alt+a")
            self._log("action", f"Connecting audio via shortcut: {shortcut}")
            self._hotkey(shortcut)
        else:
            coords = self.config["coordinates"].get("audio_icon", {"x": 100, "y": 1000})
            self._log("action", f"Clicking audio icon at ({coords['x']}, {coords['y']})")
            self._click(coords["x"], coords["y"])

    def _toggle_video(self):
        """Turn on/off camera using configured mode."""
        mode = self.config["execution"].get("mode", "shortcut")
        if mode == "shortcut":
            shortcut = self.config["shortcuts"].get("toggle_video", "alt+v")
            self._log("action", f"Toggling video via shortcut: {shortcut}")
            self._hotkey(shortcut)
        else:
            coords = self.config["coordinates"]["camera_icon"]
            self._log("action", f"Clicking camera icon at ({coords['x']}, {coords['y']})")
            self._click(coords["x"], coords["y"])

    def _open_chat(self):
        """Open the chat panel using configured mode."""
        mode = self.config["execution"].get("mode", "shortcut")
        if mode == "shortcut":
            shortcut = self.config["shortcuts"].get("toggle_chat", "alt+h")
            self._log("action", f"Opening chat via shortcut: {shortcut}")
            self._hotkey(shortcut)
        else:
            coords = self.config["coordinates"]["chat_icon"]
            self._log("action", f"Clicking chat icon at ({coords['x']}, {coords['y']})")
            self._click(coords["x"], coords["y"])

    def _click_chat_input(self):
        """Click the chat input field (coordinate mode only)."""
        if self.config["execution"].get("mode", "shortcut") == "coordinate":
            coords = self.config["coordinates"]["chat_input"]
            self._click(coords["x"], coords["y"])
            time.sleep(random.uniform(0.2, 0.5))

    def _send_chat_message(self):
        """Pick a random message and send it."""
        messages = get_active_messages(self.config)
        if not messages:
            self._log("warn", "No messages available to send.")
            return

        msg = random.choice(messages)
        self._log("chat", f"Sending: '{msg}'")

        self._open_chat()
        time.sleep(random.uniform(0.5, 1.0))
        self._click_chat_input()
        self._type_message(msg)

        self.messages_sent += 1
        self._log("info", f"Message sent (total: {self.messages_sent})")

    def _join_meeting(self):
        """Click the join button in the lobby."""
        if self.config["execution"].get("skip_join", False):
            self._log("info", "Skipping join (skip_join enabled).")
            return

        self._set_state(BotState.JOINING)
        coords = self.config["coordinates"]["join_button"]
        self._log("action", f"Clicking Join at ({coords['x']}, {coords['y']})")
        self._click(coords["x"], coords["y"])
        time.sleep(random.uniform(2, 5))

    # ── State Management ─────────────────────────────────────

    def _set_state(self, new_state: BotState):
        """Update bot state and notify via callback."""
        old_state = self.state
        self.state = new_state
        self._log("state", f"State: {old_state.value} → {new_state.value}")

    # ── Public Control Methods ───────────────────────────────

    def start(self):
        """Start the bot in a background thread."""
        if self._thread and self._thread.is_alive():
            self._log("warn", "Bot is already running.")
            return

        self._stop_event.clear()
        self._pause_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._log("info", "Bot thread started.")

    def stop(self):
        """Signal the bot to stop."""
        self._log("info", "Stop signal received.")
        self._stop_event.set()
        self._pause_event.set()  # Unpause if paused so the loop can exit
        self._set_state(BotState.STOPPED)

    def pause(self):
        """Pause the bot loop."""
        if self.state in (BotState.ACTIVE, BotState.CAMERA_LIVE):
            self._pause_event.set()
            self._set_state(BotState.PAUSED)
            self._log("info", "Bot paused.")

    def resume(self):
        """Resume the bot loop."""
        if self.state == BotState.PAUSED:
            self._pause_event.clear()
            self._set_state(BotState.ACTIVE if not self.camera_on else BotState.CAMERA_LIVE)
            self._log("info", "Bot resumed.")

    def update_config(self, new_config: Dict[str, Any]):
        """Hot-update configuration while running."""
        self.config = new_config
        self._log("info", "Configuration updated live.")

    def get_status(self) -> Dict[str, Any]:
        """Return current bot status snapshot."""
        elapsed = 0
        if self.start_time:
            elapsed = round(time.time() - self.start_time, 1)

        next_chat_in = 0
        next_cam_in = 0
        if self.start_time:
            current = time.time() - self.start_time
            next_chat_in = max(0, round(self.next_chat_time - current, 1))
            if not self.camera_on:
                next_cam_in = max(0, round(self.next_cam_time - current, 1))

        return {
            "state": self.state.value,
            "elapsed": elapsed,
            "messages_sent": self.messages_sent,
            "camera_on": self.camera_on,
            "next_chat_in": next_chat_in,
            "next_cam_in": next_cam_in,
            "simulation_mode": self.config["execution"].get("simulation_mode", False),
        }

    # ── Main Run Loop ────────────────────────────────────────

    def _run(self):
        """Main bot execution loop."""
        try:
            self._set_state(BotState.IDLE)
            self.messages_sent = 0
            self.camera_on = False

            # Step 1: Join meeting
            self._join_meeting()

            # Step 2: Wait for meeting to load and connect audio
            self._set_state(BotState.WAITING)
            load_wait = random.uniform(5, 10)
            self._log("info", f"Waiting {load_wait:.1f}s for meeting to load...")
            time.sleep(load_wait)
            self._connect_audio()

            # Step 3: Set up timers
            self.start_time = time.time()
            timing = self.config["timing"]

            self.next_chat_time = random.randint(
                timing["min_chat_interval"], timing["max_chat_interval"]
            )
            self.next_cam_time = random.randint(
                timing["min_cam_delay"], timing["max_cam_delay"]
            )

            self._set_state(BotState.ACTIVE)
            self._log("info", f"Active! Next chat in {self.next_chat_time}s, camera in {self.next_cam_time}s")

            # Step 4: Main loop
            while not self._stop_event.is_set():
                # Handle pause
                while self._pause_event.is_set() and not self._stop_event.is_set():
                    time.sleep(0.5)

                if self._stop_event.is_set():
                    break

                elapsed = time.time() - self.start_time

                # Camera activation
                if (
                    self.config["execution"].get("auto_camera", True)
                    and not self.camera_on
                    and elapsed >= self.next_cam_time
                ):
                    self._toggle_video()
                    self.camera_on = True
                    self._set_state(BotState.CAMERA_LIVE)
                    self._log("info", "🎥 Camera is now LIVE!")

                # Chat messages
                if (
                    self.config["execution"].get("auto_chat", True)
                    and elapsed >= self.next_chat_time
                ):
                    self._send_chat_message()
                    self.next_chat_time = elapsed + random.randint(
                        timing["min_chat_interval"], timing["max_chat_interval"]
                    )
                    self._log("info", f"Next chat in {self.next_chat_time - elapsed:.0f}s")

                time.sleep(0.5)

        except pyautogui.FailSafeException:
            self._log("error", "⚠️ FailSafe triggered! Mouse moved to corner. Stopping.")
            self._set_state(BotState.ERROR)
        except Exception as e:
            self._log("error", f"Unexpected error: {e}")
            self._set_state(BotState.ERROR)
        finally:
            if self.state != BotState.ERROR:
                self._set_state(BotState.STOPPED)
            self._log("info", "Bot loop ended.")
