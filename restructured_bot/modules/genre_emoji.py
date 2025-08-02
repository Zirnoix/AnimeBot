# restructured_bot/modules/genre_emoji.py

import os
from PIL import Image

EMOJI_DIR = os.path.join(os.path.dirname(__file__), "..", "Emojis")

# Cache emoji file names at load time
EMOJI_MAP = {}
for filename in os.listdir(EMOJI_DIR):
    if filename.lower().endswith(".png"):
        genre = os.path.splitext(filename)[0]  # "Action.png" -> "Action"
        EMOJI_MAP[genre] = os.path.join(EMOJI_DIR, filename)

def get_emoji_image(genre: str) -> str | None:
    """
    Returns the file path to the emoji image for the given genre.
    If no matching image exists, returns None.
    """
    return EMOJI_MAP.get(genre)

def genre_emojis(genres: list[str]) -> list[str]:
    """
    Returns a list of paths to emoji images matching the given genres.
    """
    return [path for g in genres if (path := get_emoji_image(g))]
