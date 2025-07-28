import json
import os

LINKED_USERS_FILE = "linked_users.json"
TRACKED_ANIME_FILE = "tracked_anime.json"

# ---------- LIENS ANILIST ----------

def load_user_settings():
    if os.path.exists(LINKED_USERS_FILE):
        with open(LINKED_USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_user_settings(data):
    with open(LINKED_USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def link_anilist_account(user_id, username):
    data = load_user_settings()
    data[str(user_id)] = username
    save_user_settings(data)

def unlink_anilist_account(user_id):
    data = load_user_settings()
    if str(user_id) in data:
        del data[str(user_id)]
        save_user_settings(data)

def get_anilist_username(user_id):
    data = load_user_settings()
    return data.get(str(user_id))

# ---------- TRACKING ANIMES ----------

def load_tracked_anime():
    if os.path.exists(TRACKED_ANIME_FILE):
        with open(TRACKED_ANIME_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_tracked_anime(data):
    with open(TRACKED_ANIME_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def track_anime(user_id, anime_id):
    data = load_tracked_anime()
    user_id = str(user_id)
    if user_id not in data:
        data[user_id] = []
    if anime_id not in data[user_id]:
        data[user_id].append(anime_id)
    save_tracked_anime(data)

def untrack_anime(user_id, anime_id):
    data = load_tracked_anime()
    user_id = str(user_id)
    if user_id in data and anime_id in data[user_id]:
        data[user_id].remove(anime_id)
        save_tracked_anime(data)

def get_tracked_anime(user_id):
    data = load_tracked_anime()
    return data.get(str(user_id), [])
