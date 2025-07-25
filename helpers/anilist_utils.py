import os
import requests
import unicodedata
import re

ANILIST_API = "https://graphql.anilist.co"
OWNER_USERNAME = os.getenv("ANILIST_USERNAME")

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
