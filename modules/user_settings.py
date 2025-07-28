import json
import os

USER_SETTINGS_FILE = "linked_users.json"

def load_user_settings():
    if os.path.exists(USER_SETTINGS_FILE):
        with open(USER_SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_user_settings(data):
    with open(USER_SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_anilist_username(user_id):
    data = load_user_settings()
    return data.get(str(user_id))

def link_anilist_account(user_id, username):
    data = load_user_settings()
    data[str(user_id)] = username
    save_user_settings(data)

def unlink_anilist_account(user_id):
    data = load_user_settings()
    if str(user_id) in data:
        del data[str(user_id)]
        save_user_settings(data)
