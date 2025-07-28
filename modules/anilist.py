import requests
import os
import random
import aiohttp
import asyncio

ANILIST_API_URL = "https://graphql.anilist.co"
HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
}

async def fetch_anilist_user_id(username):
    query = '''
    query ($name: String) {
      User(name: $name) {
        id
      }
    }
    '''
    variables = {"name": username}
    data = await fetch_anilist_data(query, variables)
    if data and "User" in data:
        return data["User"]["id"]
    return None

# Récupère le planning (prochains épisodes) pour un user donné
async def fetch_user_airing_schedule(user_id):
    query = '''
    query ($userId: Int) {
      MediaListCollection(userId: $userId, type: ANIME, status: CURRENT) {
        lists {
          entries {
            media {
              id
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
    variables = {"userId": user_id}
    data = await fetch_anilist_data(query, variables)
    results = []
    if data and "MediaListCollection" in data:
        for lst in data["MediaListCollection"]["lists"]:
            for entry in lst["entries"]:
                media = entry["media"]
                airing = media.get("nextAiringEpisode")
                if airing:
                    results.append({
                        "title": media["title"]["romaji"],
                        "airingAt": airing["airingAt"],
                        "episode": airing["episode"]
                    })
    return results

# Récupère les stats (score moyen, nombre d’animes vus, etc.)
async def fetch_user_stats(user_id):
    query = '''
    query ($userId: Int) {
      User(id: $userId) {
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
    variables = {"userId": user_id}
    data = await fetch_anilist_data(query, variables)
    if data and "User" in data:
        return data["User"]["statistics"]["anime"]
    return None

# Récupère les infos de profil Anilist
async def fetch_user_profile(username):
    query = '''
    query ($name: String) {
      User(name: $name) {
        id
        name
        siteUrl
        avatar {
          large
        }
        statistics {
          anime {
            count
            meanScore
            minutesWatched
          }
        }
      }
    }
    '''
    variables = {"name": username}
    data = await fetch_anilist_data(query, variables)
    if data and "User" in data:
        return data["User"]
    return None

# Requête principale Anilist
async def fetch_anilist_data(query, variables):
    async with aiohttp.ClientSession() as session:
        async with session.post(ANILIST_API_URL, json={"query": query, "variables": variables}) as resp:
            if resp.status == 200:
                json_data = await resp.json()
                return json_data.get("data", None)
            else:
                return None
                
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
