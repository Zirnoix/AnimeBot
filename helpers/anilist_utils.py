# helpers/anilist_utils.py
import os
import requests
import random
import re
from helpers.json_utils import load_json, save_json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

logger.info("✅ anilist_utils.py a bien été importé")
OWNER_USERNAME = os.getenv("ANILIST_USERNAME")
logger.info(f"✅ OWNER_USERNAME = {OWNER_USERNAME}")

QUIZ_FILE = "quiz_scores.json"

def get_user_anilist(user_id):
    linked_users = load_json("linked_users.json", {})
    return linked_users.get(str(user_id))


def get_anilist_user_animelist(username):
    print(f"🔍 Récupération de la liste d'animes pour: {username}")

    query = '''
    query ($username: String) {
      MediaListCollection(userName: $username, type: ANIME) {
        lists {
          entries {
            media {
              title {
                romaji
                english
                native
              }
              status
              format
            }
            status
          }
        }
      }
    }
    '''

    variables = {"username": username}

    response = requests.post(
        'https://graphql.anilist.co',
        json={'query': query, 'variables': variables},
        headers={'Content-Type': 'application/json'}
    )

    if response.status_code != 200:
        print(f"❌ Erreur lors de la requête Anilist ({response.status_code}): {response.text}")
        return []

    data = response.json()
    print("📦 Réponse brute d'Anilist:", data)

    entries = data.get("data", {}).get("MediaListCollection", {}).get("lists", [])
    if not entries:
        print(f"⚠️ Aucune entrée 'lists' pour l'utilisateur {username}.")
        return []

    anime_titles = set()

    for group in entries:
        for entry in group.get("entries", []):
            media = entry.get("media")
            if not media:
                continue

            titles = media.get("title")
            if not titles:
                continue

            for key in ("romaji", "english", "native"):
                title_value = titles.get(key)
                if title_value:
                    anime_titles.add(title_value.lower())

    result = list(anime_titles)
    print(f"✅ {len(result)} anime(s) trouvés pour {username}")
    return result



def get_anime_list():
    username = os.getenv("ANILIST_USERNAME")
    if not username:
        raise ValueError("ANILIST_USERNAME is not set in environment variables.")
    return [anime.title() for anime in get_anilist_user_animelist(username)]


def normalize_title(title: str) -> str:
    title = title.lower()
    title = title.replace("’", "'")
    title = re.sub(r"[^\w\s]", "", title)
    return title.strip()


def update_score(user_id, success):
    scores = load_json(QUIZ_FILE, {})
    if user_id not in scores:
        scores[user_id] = {"points": 0, "games": 0}

    scores[user_id]["games"] += 1
    if success:
        scores[user_id]["points"] += 1

    save_json(QUIZ_FILE, scores)
