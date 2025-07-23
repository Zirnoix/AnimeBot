
import json
import re
import requests
from datetime import datetime

CACHE_FILE = "anime_title_cache.json"

def normalize(text):
    import unicodedata
    if not text:
        return ""
    text = ''.join(c for c in unicodedata.normalize('NFD', text)
                   if unicodedata.category(c) != 'Mn')  # Enlève les accents
    return ''.join(e for e in text.lower() if e.isalnum() or e.isspace())

def clean_title(title):
    if not title:
        return []
    base = normalize(title)
    no_extra = re.sub(r"(saison|season|s\d|2nd|second|3rd|third|final|part \d+|ver\d+|[^\w\s])", "", base, flags=re.IGNORECASE).strip()
    words = no_extra.split()
    results = {base, no_extra}
    results.update(w for w in words if len(w) > 3)
    return list(results)

def update_title_cache():
    url = "https://graphql.anilist.co"
    query = '''
    query {
      Page(perPage: 50) {
        media(type: ANIME, status_in: [RELEASING, NOT_YET_RELEASED]) {
          id
          title {
            romaji
            english
            native
          }
        }
      }
    }
    '''
    try:
        res = requests.post(url, json={"query": query})
        data = res.json()
        result = {}
        for media in data["data"]["Page"]["media"]:
            titles = []
            for val in media["title"].values():
                titles.extend(clean_title(val))
            result[media["id"]] = {"titles": list(set(titles))}
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print(f"✅ Cache AniList mis à jour : {len(result)} titres")
    except Exception as e:
        print(f"[Erreur mise à jour cache] {e}")

def load_title_cache():
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}
