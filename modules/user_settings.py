# modules/user_settings.py

import json
import os

SETTINGS_FILE = "data/user_settings.json"


def load_settings():
    if not os.path.exists(SETTINGS_FILE):
        return {}
    with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_settings(settings):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)


def get_user_settings(user_id: str):
    settings = load_settings()
    return settings.get(str(user_id), {})


def update_user_setting(user_id: str, key: str, value):
    settings = load_settings()
    user_id_str = str(user_id)
    if user_id_str not in settings:
        settings[user_id_str] = {}
    settings[user_id_str][key] = value
    save_settings(settings)


def reset_user_settings(user_id: str):
    settings = load_settings()
    user_id_str = str(user_id)
    if user_id_str in settings:
        del settings[user_id_str]
    save_settings(settings)
