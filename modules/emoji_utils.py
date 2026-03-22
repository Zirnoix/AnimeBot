# modules/emoji_utils.py
import json
from discord.ext import commands

def _load(path="data/config_emojis.json"):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

EMOJI_IDS = _load()  # { "ab_mask_gold": 123... }

def get_emoji(bot: commands.Bot, key: str, fallback: str = "🏅") -> str:
    e_id = EMOJI_IDS.get(key)
    if not e_id:
        return fallback
    e = bot.get_emoji(int(e_id))
    return str(e) if e else fallback
