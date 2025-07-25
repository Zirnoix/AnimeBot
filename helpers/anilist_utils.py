import os
import requests
import random
import re
import logging

from helpers.json_utils import load_json, save_json

# Configuration du logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Récupère le nom d'utilisateur Anilist
OWNER_USERNAME = os.getenv("ANILIST_USERNAME")
QUIZ_FILE = "quiz_scores.json"

logger.info("✅ anilist_utils.py a bien été importé")
logger.info(f"✅ OWNER_USERNAME = {OWNER_USERNAME}")


def get_user_anilist(user_id):
    linked_users = load_json("linked_users.json", {})
    return linked_users.get(str(user_id))


def get_anilist_user_animelist(username):
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
        logger.error(f"❌ Erreur Anilist : {response.text}")
        return []

    data = response.json()
    entries = data["data"]["MediaListCollection"]["lists"]

    anime_titles = set()

    for group in entries:
        for entry in group["entries"]:
            media = entry.get("media")
            if not media:
                logger.warning(f"❌ Pas de media dans l'entrée : {entry}")
                continue

            titles = media.get("title")
            if not titles:
                logger.warning(f"❌ Pas de titre dans media : {media}")
                continue

            logger.info(f"✅ Titre détecté : {titles}")

            for key in ("romaji", "english", "native"):
                if titles.get(key):
                    anime_titles.add(titles[key].lower())

    return list(anime_titles)


def get_anime_list():
    if not OWNER_USERNAME:
        logger.error("❌ OWNER_USERNAME est vide ou non défini.")
        return []

    anime_titles = get_anilist_user_animelist(OWNER_USERNAME)

    if not anime_titles:
        logger.warning(f"⚠️ Aucun anime récupéré pour {OWNER_USERNAME}")
        return []

    formatted_titles = [anime.title() for anime in anime_titles if isinstance(anime, str)]

    logger.info(f"🎉 {len(formatted_titles)} animés chargés pour {OWNER_USERNAME}")
    return formatted_titles


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
