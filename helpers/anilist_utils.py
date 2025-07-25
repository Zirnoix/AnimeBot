import os
import requests
import unicodedata
import re

ANILIST_API = "https://graphql.anilist.co"
OWNER_USERNAME = os.getenv("ANILIST_USERNAME")
ANILIST_USERNAME = os.getenv("ANILIST_USERNAME")

def get_user_anilist(username: str = None):
    if username is None:
        username = ANILIST_USERNAME

    query = """
    query ($name: String) {
        User(name: $name) {
            id
            name
        }
    }
    """
    variables = {"name": username}
    response = requests.post("https://graphql.anilist.co", json={"query": query, "variables": variables})

    if response.status_code != 200:
        raise Exception("Erreur lors de la récupération de l'utilisateur AniList")

    return response.json()["data"]["User"]p
def normalize_title(title):
    nfkd = unicodedata.normalize('NFKD', title)
    cleaned = "".join(c for c in nfkd if not unicodedata.combining(c))
    cleaned = re.sub(r"[^a-zA-Z0-9]", "", cleaned).lower()
    return cleaned

def get_anilist_user_animelist(username):
    query = """
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
              id
              status
            }
          }
        }
      }
    }
    """
    variables = {"username": username}
    response = requests.post(ANILIST_API, json={"query": query, "variables": variables})
    data = response.json()

    entries = []
    try:
        for lst in data["data"]["MediaListCollection"]["lists"]:
            entries.extend(lst["entries"])
        return [entry["media"] for entry in entries]
    except Exception:
        return []
