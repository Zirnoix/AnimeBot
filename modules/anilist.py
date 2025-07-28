# modules/anilist.py

import requests
import random

ANILIST_API_URL = "https://graphql.anilist.co"

HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
}

def run_query(query, variables=None):
    response = requests.post(ANILIST_API_URL, json={"query": query, "variables": variables}, headers=HEADERS)
    if response.status_code != 200:
        print("Erreur API Anilist:", response.text)
        return None
    return response.json()


def get_user_stats(username):
    query = '''
    query ($username: String) {
      User(name: $username) {
        statistics {
          anime {
            count
            meanScore
            minutesWatched
            episodesWatched
          }
        }
      }
    }
    '''
    data = run_query(query, {"username": username})
    if not data:
        return None
    return data.get("data", {}).get("User", {}).get("statistics", {}).get("anime", None)


def get_next_airing_episodes(username):
    query = '''
    query ($username: String) {
      MediaListCollection(userName: $username, type: ANIME, status: CURRENT) {
        lists {
          entries {
            media {
              title {
                romaji
              }
              nextAiringEpisode {
                airingAt
                episode
              }
            }
          }
        }
      }
    }
    '''
    data = run_query(query, {"username": username})
    if not data:
        return []

    episodes = []
    lists = data["data"]["MediaListCollection"]["lists"]
    for group in lists:
        for entry in group["entries"]:
            media = entry["media"]
            next_ep = media.get("nextAiringEpisode")
            if next_ep:
                episodes.append({
                    "title": media["title"]["romaji"],
                    "airingAt": next_ep["airingAt"],
                    "episode": next_ep["episode"]
                })

    return sorted(episodes, key=lambda x: x["airingAt"])


def get_next_episode_for_user(anilist_username):
    episodes = get_next_airing_episodes(anilist_username)
    return episodes[0] if episodes else None


def get_random_anime():
    page = random.randint(1, 500)
    query = '''
    query ($page: Int) {
      Page(page: $page, perPage: 1) {
        media(type: ANIME, isAdult: false, sort: SCORE_DESC) {
          id
          title {
            romaji
            english
            native
          }
          description(asHtml: false)
          coverImage {
            large
          }
        }
      }
    }
    '''
    data = run_query(query, {"page": page})
    if data:
        return data["data"]["Page"]["media"][0]
    return None


def get_upcoming_episodes(user_anilist_id):
    query = '''
    query ($userId: Int) {
      MediaListCollection(userId: $userId, type: ANIME, status_in: [CURRENT, PLANNING]) {
        lists {
          entries {
            media {
              title {
                romaji
              }
              nextAiringEpisode {
                airingAt
                episode
              }
            }
          }
        }
      }
    }
    '''
    data = run_query(query, {"userId": user_anilist_id})
    if not data:
        return []

    episodes = []
    for lst in data["data"]["MediaListCollection"]["lists"]:
        for entry in lst["entries"]:
            media = entry["media"]
            next_ep = media.get("nextAiringEpisode")
            if next_ep:
                episodes.append({
                    "title": media["title"]["romaji"],
                    "airingAt": next_ep["airingAt"],
                    "episode": next_ep["episode"]
                })
    return episodes


def get_duel_stats(username):
    query = '''
    query ($username: String) {
      User(name: $username) {
        statistics {
          anime {
            genres {
              genre
              count
              meanScore
              minutesWatched
            }
          }
        }
      }
    }
    '''
    data = run_query(query, {"username": username})
    if not data:
        return []
    return data["data"]["User"]["statistics"]["anime"]["genres"]
