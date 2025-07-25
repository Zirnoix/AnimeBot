# helpers/general_utils.py
import pytz
import discord
from helpers.json_utils import load_json

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
    return []

def search_anime(query):
    return {"title": query.title(), "description": "Description factice."}

def get_top_animes():
    return ["Attack on Titan", "Fullmetal Alchemist", "Steins;Gate"]

def get_seasonal_animes():
    return ["My Hero Academia", "Jujutsu Kaisen", "Tokyo Revengers"]
