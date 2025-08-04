# modules/anilist.py

import aiohttp
import os

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
