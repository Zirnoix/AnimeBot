import requests
import os
import random

ANILIST_API_URL = "https://graphql.anilist.co"
HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
}

def run_query(query, variables=None):
    response = requests.post(ANILIST_API_URL, json={"query": query, "variables": variables}, headers=HEADERS)
    if response.status_code != 200:
        print("❌ Erreur API Anilist:", response.text)
        return None
    return response.json()

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
    if data:
        user_data = data.get("data", {}).get("User", {})
        return user_data.get("statistics", {}).get("anime", None)
    return None

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
    results = []
    if data:
        entries = data.get("data", {}).get("MediaListCollection", {}).get("lists", [])
        for group in entries:
            for entry in group["entries"]:
                media = entry["media"]
                airing = media.get("nextAiringEpisode")
                if airing:
                    results.append({
                        "title": media["title"]["romaji"],
                        "airingAt": airing["airingAt"],
                        "episode": airing["episode"]
                    })
    return sorted(results, key=lambda x: x["airingAt"])

def get_next_episode_for_user(username):
    episodes = get_next_airing_episodes(username)
    return episodes[0] if episodes else None

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
    episodes = []
    if data:
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

def get_duel_stats(user1, user2):
    stats1 = get_user_stats(user1)
    stats2 = get_user_stats(user2)
    if not stats1 or not stats2:
        return None
    return {
        "user1": {
            "name": user1,
            "episodes": stats1.get("episodesWatched", 0),
            "minutes": stats1.get("minutesWatched", 0),
            "count": stats1.get("count", 0),
            "score": stats1.get("meanScore", 0)
        },
        "user2": {
            "name": user2,
            "episodes": stats2.get("episodesWatched", 0),
            "minutes": stats2.get("minutesWatched", 0),
            "count": stats2.get("count", 0),
            "score": stats2.get("meanScore", 0)
        }
    }
