import json
import os

CACHE_FILE = "anime_title_cache.json"

def load_title_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_title_cache(cache):
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

def add_title_to_cache(anime_id, title):
    cache = load_title_cache()
    cache[str(anime_id)] = title
    save_title_cache(cache)

def get_title_from_cache(anime_id):
    cache = load_title_cache()
    return cache.get(str(anime_id))
