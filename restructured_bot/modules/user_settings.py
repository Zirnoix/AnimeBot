# restructured_bot/modules/user_settings.py

import os
import json
from .core import ensure_data_dir, USER_SETTINGS_FILE

def load_user_settings() -> dict:
    """Load user-specific settings (reminders, summaries, etc.)."""
    ensure_data_dir()
    if not os.path.exists(USER_SETTINGS_FILE):
        return {}
    with open(USER_SETTINGS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_user_settings(settings: dict) -> None:
    """Save the user settings to disk."""
    ensure_data_dir()
    with open(USER_SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)

def set_user_setting(user_id: int, key: str, value) -> None:
    """Update a specific setting for a user."""
    settings = load_user_settings()
    uid = str(user_id)
    if uid not in settings:
        settings[uid] = {}
    settings[uid][key] = value
    save_user_settings(settings)

def get_user_setting(user_id: int, key: str, default=None):
    """Retrieve a user's setting, with optional fallback."""
    return load_user_settings().get(str(user_id), {}).get(key, default)

def toggle_user_setting(user_id: int, key: str) -> bool:
    """Toggle a boolean setting and return the new value."""
    current = get_user_setting(user_id, key, False)
    new_value = not current
    set_user_setting(user_id, key, new_value)
    return new_value
