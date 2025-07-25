import os
import re

def normalize_title(title: str) -> str:
    title = title.lower()
    title = title.replace("’", "'")
    title = re.sub(r"[^\w\s]", "", title)
    return title.strip()

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

