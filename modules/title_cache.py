import json
import os

CACHE_PATH = "data/title_cache.json"

def load_cache():
    if not os.path.exists(CACHE_PATH):
        return {}
    with open(CACHE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def save_cache(cache):
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=4)

def get_cached_title(anime_id, default=None):
    cache = load_cache()
    return cache.get(str(anime_id), default)

def set_cached_title(anime_id, title):
    cache = load_cache()
    cache[str(anime_id)] = title
    save_cache(cache)