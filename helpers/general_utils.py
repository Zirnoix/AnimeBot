# helpers/general_utils.py
import pytz
import discord
from helpers.json_utils import load_json
import requests
import datetime

TIMEZONE = pytz.timezone("Europe/Paris")

def genre_emoji(genres):
    emoji_map = {
        "Action": "🔥", "Fantasy": "✨", "Romance": "💖",
        "Drama": "🎭", "Comedy": "😂", "Horror": "👻",
        "Sci-Fi": "🚀", "Slice of Life": "🌸", "Sports": "⚽",
        "Music": "🎵", "Supernatural": "👽", "Mecha": "🤖",
        "Psychological": "🔮", "Adventure": "🌍", "Thriller": "💥",
        "Ecchi": "😳"
    }
    return " ".join(emoji_map.get(g, "📺") for g in genres[:3])

def get_user_stats(username):
    return {
        "completed": 42,
        "watching": 10,
        "dropped": 2,
        "plan_to_watch": 15
    }

def get_user_genres(user_id):
    data = load_json("user_genres.json", {})
    return data.get(str(user_id), [])

def get_user_genre_chart(username):
    return {
        "Action": 10, "Comedy": 7, "Drama": 5
    }

def get_all_user_genres():
    return [
        "Action", "Adventure", "Comedy", "Drama", "Ecchi", "Fantasy", "Horror",
        "Mecha", "Music", "Psychological", "Romance", "Sci-Fi", "Slice of Life",
        "Sports", "Supernatural", "Thriller"
    ]

def get_upcoming_episodes(username):
    query = '''
    query ($username: String) {
      MediaListCollection(userName: $username, type: ANIME, status_in: [CURRENT, PLANNING]) {
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
    variables = {"username": username}

    response = requests.post(
        "https://graphql.anilist.co",
        json={"query": query, "variables": variables},
        headers={"Content-Type": "application/json"}
    )

    if response.status_code != 200:
        return []

    data = response.json()
    episodes = []

    for group in data["data"]["MediaListCollection"]["lists"]:
        for entry in group["entries"]:
            media = entry["media"]
            airing = media.get("nextAiringEpisode")
            if airing:
                episodes.append({
                    "title": media["title"]["romaji"],
                    "airing_at": datetime.datetime.fromtimestamp(airing["airingAt"]),
                    "episode": airing["episode"]
                })

    # Trier les épisodes les plus proches dans le futur
    episodes.sort(key=lambda ep: ep["airing_at"])
    return episodes

def search_anime(query):
    return {"title": query.title(), "description": "Description factice."}

def get_top_animes():
    return ["Attack on Titan", "Fullmetal Alchemist", "Steins;Gate"]

def get_seasonal_animes():
    return ["My Hero Academia", "Jujutsu Kaisen", "Tokyo Revengers"]
