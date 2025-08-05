# modules/channel_config.py

import json
import os

CONFIG_FILE = "data/channel_config.json"

def load_config():
    if not os.path.exists(CONFIG_FILE):
        return {}
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_config(config):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

def set_channel(guild_id: str, key: str, channel_id: int):
    config = load_config()
    guild_id = str(guild_id)
    if guild_id not in config:
        config[guild_id] = {}
    config[guild_id][key] = channel_id
    save_config(config)

def get_channel(guild_id: str, key: str):
    config = load_config()
    return config.get(str(guild_id), {}).get(key)

def clear_channel(guild_id: str, key: str):
    config = load_config()
    if str(guild_id) in config and key in config[str(guild_id)]:
        del config[str(guild_id)][key]
        save_config(config)

# ✅ Ajout pour compatibilité avec tracker.py / scheduler.py
def get_configured_channel_id(guild_id: int):
    return get_channel(guild_id, "anilist_tracking")
