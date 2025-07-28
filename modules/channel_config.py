import json
import os

CHANNEL_CONFIG_FILE = "channel_config.json"

def load_channel_config():
    if os.path.exists(CHANNEL_CONFIG_FILE):
        with open(CHANNEL_CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_channel_config(data):
    with open(CHANNEL_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def set_notification_channel(guild_id, channel_id):
    data = load_channel_config()
    data[str(guild_id)] = channel_id
    save_channel_config(data)

def get_notification_channel(guild_id):
    data = load_channel_config()
    return data.get(str(guild_id))

def remove_notification_channel(guild_id):
    data = load_channel_config()
    if str(guild_id) in data:
        del data[str(guild_id)]
        save_channel_config(data)
