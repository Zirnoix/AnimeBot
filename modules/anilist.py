# modules/anilist.py

import aiohttp
import os
import requests

ANILIST_USERNAME = os.getenv("ANILIST_USERNAME")
ANILIST_API_URL = "https://graphql.anilist.co"

async def fetch_anilist(query: str, variables: dict = None):
    async with aiohttp.ClientSession() as session:
        async with session.post(ANILIST_API_URL, json={"query": query, "variables": variables or {}}, headers={"Content-Type": "application/json"}) as response:
            if response.status != 200:
                raise Exception(f"Erreur AniList: {response.status}")
            return await response.json()

def format_anime_title(anime):
    return anime["title"].get("romaji") or anime["title"].get("english") or anime["title"].get("native") or "Titre inconnu"

def format_anime_url(anime_id):
    return f"https://anilist.co/anime/{anime_id}"

def get_anime_format_emoji(anime_format: str):
    format_emojis = {
        "TV": "📺",
        "MOVIE": "🎬",
        "OVA": "📀",
        "ONA": "💻",
        "SPECIAL": "✨",
        "MUSIC": "🎵",
    }
    return format_emojis.get(anime_format.upper(), "❓")

async def get_anilist_user_id(username: str):
    query = """
    query ($name: String) {
      User(name: $name) {
        id
      }
    }
    """
    variables = {"name": username}
    data = await fetch_anilist(query, variables)
    return data["data"]["User"]["id"] if data["data"].get("User") else None

def get_random_characters(n=4):
    characters = []
    tries = 0
    while len(characters) < n and tries < 10:
        page = random.randint(1, 1000)
        query = '''
        query ($page: Int) {
          Page(page: $page, perPage: 1) {
            characters(sort: FAVOURITES_DESC) {
              name {
                full
              }
              image {
                large
              }
            }
          }
        }
        '''
        response = requests.post(
            "https://graphql.anilist.co",
            json={"query": query, "variables": {"page": page}},
            headers={"Content-Type": "application/json"}
        )
        try:
            data = response.json()["data"]["Page"]["characters"][0]
            if data["name"]["full"] not in [c["name"]["full"] for c in characters]:
                characters.append(data)
        except Exception:
            pass
        tries += 1
    return characters

def get_random_title():
    page = random.randint(1, 10000)
    query = '''
    query ($page: Int) {
      Page(page: $page, perPage: 1) {
        media(type: ANIME, isAdult: false, sort: POPULARITY_DESC) {
          title {
            romaji
          }
        }
      }
    }
    '''
    response = requests.post(
        "https://graphql.anilist.co",
        json={"query": query, "variables": {"page": page}},
        headers={"Content-Type": "application/json"}
    )
    try:
        return response.json()["data"]["Page"]["media"][0]["title"]["romaji"]
    except Exception:
        return "Inconnu"

async def get_next_airing_anime_data():
    query = '''
    query {
      Page(perPage: 1) {
        media(type: ANIME, sort: NEXT_AIRING_EPISODE) {
          title {
            romaji
          }
          coverImage {
            large
          }
          nextAiringEpisode {
            episode
            airingAt
          }
        }
      }
    }
    '''

    async with aiohttp.ClientSession() as session:
        async with session.post("https://graphql.anilist.co", json={"query": query}) as response:
            if response.status != 200:
                return None
            data = await response.json()

    anime = data["data"]["Page"]["media"][0]
    return {
        "title": anime["title"]["romaji"],
        "episode": anime["nextAiringEpisode"]["episode"],
        "airing_time": anime["nextAiringEpisode"]["airingAt"],
        "cover_url": anime["coverImage"]["large"]
    }
