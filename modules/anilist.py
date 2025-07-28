import requests
import random
import os

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
    variables = {"username": username}
    data = run_query(query, variables)
    if not data:
        return None
    return data["data"]["User"]["statistics"]["anime"]


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
    for group in data["data"]["MediaListCollection"]["lists"]:
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


def get_next_episode_for_user(username):
    episodes = get_next_airing_episodes(username)
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


def get_upcoming_episodes(user_id):
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
    data = run_query(query, {"userId": user_id})
    if not data:
        return []
    episodes = []
    for group in data["data"]["MediaListCollection"]["lists"]:
        for entry in group["entries"]:
            media = entry["media"]
            next_ep = media.get("nextAiringEpisode")
            if next_ep:
                episodes.append({
                    "title": media["title"]["romaji"],
                    "airingAt": next_ep["airingAt"],
                    "episode": next_ep["episode"]
                })
    return episodes


def get_duel_stats(user1, user2):
    query = '''
    query ($user1: String, $user2: String) {
      u1: User(name: $user1) {
        statistics {
          anime {
            count
            meanScore
            episodesWatched
          }
        }
      }
      u2: User(name: $user2) {
        statistics {
          anime {
            count
            meanScore
            episodesWatched
          }
        }
      }
    }
    '''
    variables = {"user1": user1, "user2": user2}
    data = run_query(query, variables)
    if not data:
        return None
    return {
        "user1": data["data"]["u1"]["statistics"]["anime"],
        "user2": data["data"]["u2"]["statistics"]["anime"]
    }
