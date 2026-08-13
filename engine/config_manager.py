"""
Zomo Config Manager
Handles loading, saving, and validating JSON configuration for the Zoom Bot engine.
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

# Base directory for config and presets
BASE_DIR = Path(__file__).resolve().parent.parent
PRESETS_DIR = BASE_DIR / "presets"
CONFIG_FILE = BASE_DIR / "config.json"

# Default configuration values
DEFAULT_CONFIG: Dict[str, Any] = {
    "timing": {
        "min_chat_interval": 15,
        "max_chat_interval": 45,
        "min_cam_delay": 30,
        "max_cam_delay": 90,
        "typing_speed": 0.05,
        "human_jitter": 2.0,
        "mouse_move_duration": 0.3,
    },
    "coordinates": {
        "join_button": {"x": 960, "y": 550},
        "chat_icon": {"x": 850, "y": 1000},
        "camera_icon": {"x": 200, "y": 1000},
        "chat_input": {"x": 400, "y": 950},
    },
    "execution": {
        "mode": "shortcut",  # "shortcut" or "coordinate"
        "skip_join": False,
        "auto_camera": True,
        "auto_chat": True,
        "simulation_mode": False,  # Dry run without actual clicks
    },
    "shortcuts": {
        "toggle_video": "alt+v",
        "toggle_chat": "alt+h",
        "toggle_mute": "alt+a",
    },
    "active_preset": "casual",
    "custom_messages": [],
}


def deep_merge(base: dict, override: dict) -> dict:
    """Deep merge override into base, returning a new dict."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config() -> Dict[str, Any]:
    """Load configuration from disk, falling back to defaults for missing keys."""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                user_config = json.load(f)
            return deep_merge(DEFAULT_CONFIG, user_config)
        except (json.JSONDecodeError, IOError) as e:
            print(f"[ConfigManager] Error loading config: {e}. Using defaults.")
    return DEFAULT_CONFIG.copy()


def save_config(config: Dict[str, Any]) -> None:
    """Save configuration to disk."""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
    except IOError as e:
        print(f"[ConfigManager] Error saving config: {e}")


def load_presets() -> Dict[str, Any]:
    """Load all message presets from the presets directory."""
    presets = {}
    if PRESETS_DIR.exists():
        for file in PRESETS_DIR.glob("*.json"):
            try:
                with open(file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if "presets" in data:
                        presets.update(data["presets"])
                    else:
                        # Single preset file
                        presets[file.stem] = data
            except (json.JSONDecodeError, IOError) as e:
                print(f"[ConfigManager] Error loading preset {file}: {e}")
    return presets


def save_preset(name: str, messages: List[str], description: str = "") -> None:
    """Save a custom preset to disk."""
    PRESETS_DIR.mkdir(parents=True, exist_ok=True)
    filepath = PRESETS_DIR / f"{name}.json"
    data = {
        "presets": {
            name: {
                "name": name,
                "description": description,
                "messages": messages,
            }
        }
    }
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except IOError as e:
        print(f"[ConfigManager] Error saving preset {name}: {e}")


def get_active_messages(config: Dict[str, Any]) -> List[str]:
    """Get the active message list based on current config."""
    # Custom messages take priority if they exist
    custom = config.get("custom_messages", [])
    if custom:
        return custom

    # Otherwise load from active preset
    preset_name = config.get("active_preset", "casual")
    presets = load_presets()
    if preset_name in presets:
        return presets[preset_name].get("messages", [])

    # Ultimate fallback
    return ["Hi everyone!", "Thanks for sharing.", "Great presentation!"]


def get_screen_presets() -> Dict[str, Dict[str, Dict[str, int]]]:
    """Return coordinate presets for common screen resolutions."""
    return {
        "1920x1080": {
            "join_button": {"x": 960, "y": 550},
            "chat_icon": {"x": 850, "y": 1000},
            "camera_icon": {"x": 200, "y": 1000},
            "chat_input": {"x": 400, "y": 950},
        },
        "2560x1440": {
            "join_button": {"x": 1280, "y": 733},
            "chat_icon": {"x": 1133, "y": 1333},
            "camera_icon": {"x": 267, "y": 1333},
            "chat_input": {"x": 533, "y": 1267},
        },
        "3840x2160": {
            "join_button": {"x": 1920, "y": 1100},
            "chat_icon": {"x": 1700, "y": 2000},
            "camera_icon": {"x": 400, "y": 2000},
            "chat_input": {"x": 800, "y": 1900},
        },
    }
