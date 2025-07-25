import json
import os
import pytz
import discord
import matplotlib.pyplot as plt

TIMEZONE = pytz.timezone("Europe/Paris")

import discord

def generate_genre_chart(genre_data: dict, filename: str = "genre_chart.png") -> str:
    if not genre_data:
        raise ValueError("Aucune donnée de genre fournie.")

    labels = list(genre_data.keys())
    sizes = list(genre_data.values())

    plt.figure(figsize=(6, 6))
    plt.pie(sizes, labels=labels, autopct='%1.1f%%', startangle=140)
    plt.axis('equal')
    plt.title("Répartition des genres")

    # Dossier de sortie (sûr pour Render)
    output_path = os.path.join("temp", filename)
    os.makedirs("temp", exist_ok=True)
    plt.savefig(output_path)
    plt.close()

    return output_path

def normalize_title(title: str) -> str:
    # Exemple basique
    title = title.lower()
    title = title.replace("’", "'")
    title = re.sub(r"[^\w\s]", "", title)  # retire la ponctuation
    return title.strip()

def generate_stats_embed(username, stats):
    embed = discord.Embed(title=f"📊 Stats pour {username}", color=discord.Color.blue())
    for k, v in stats.items():
        embed.add_field(name=k.replace('_', ' ').title(), value=str(v), inline=True)
    return embed

def load_json(filename, default):
    if not os.path.exists(filename):
        return default
    with open(filename, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(filename, data):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# Simule un stockage temporaire pour tests locaux
LINKED_USERS_FILE = "linked_users.json"

def get_user_anilist(user_id):
    linked_users = load_json(LINKED_USERS_FILE, {})
    return linked_users.get(str(user_id))

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

# Stub à remplacer par appel AniList réel
def get_upcoming_episodes(username):
    return []  # Remplacer par la vraie récupération AniList

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

def search_anime(query):
    return {"title": query.title(), "description": "Description factice."}

def get_top_animes():
    return ["Attack on Titan", "Fullmetal Alchemist", "Steins;Gate"]

def get_seasonal_animes():
    return ["My Hero Academia", "Jujutsu Kaisen", "Tokyo Revengers"]
