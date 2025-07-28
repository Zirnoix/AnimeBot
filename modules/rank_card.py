# modules/rank_card.py

from PIL import Image, ImageDraw, ImageFont
import requests
from io import BytesIO
import os

def generate_rank_card(username, level, xp, next_level_xp, avatar_url):
    width, height = 600, 150
    card = Image.new("RGBA", (width, height), (30, 30, 30))
    draw = ImageDraw.Draw(card)

    try:
        avatar_resp = requests.get(avatar_url)
        avatar = Image.open(BytesIO(avatar_resp.content)).resize((100, 100)).convert("RGBA")
    except:
        avatar = Image.new("RGBA", (100, 100), (100, 100, 100))

    card.paste(avatar, (20, 25), avatar)

    font_path = os.path.join("assets", "fonts", "arial.ttf")
    font_large = ImageFont.truetype(font_path, 20)
    font_small = ImageFont.truetype(font_path, 16)

    draw.text((140, 30), username, font=font_large, fill=(255, 255, 255))
    draw.text((140, 60), f"Niveau: {level}", font=font_small, fill=(200, 200, 200))
    draw.text((140, 85), f"XP: {xp}/{next_level_xp}", font=font_small, fill=(200, 200, 200))

    bar_x = 140
    bar_y = 115
    bar_width = 400
    bar_height = 15
    progress = int((xp / next_level_xp) * bar_width)

    draw.rectangle((bar_x, bar_y, bar_x + bar_width, bar_y + bar_height), fill=(80, 80, 80))
    draw.rectangle((bar_x, bar_y, bar_x + progress, bar_y + bar_height), fill=(100, 200, 100))

    output = BytesIO()
    card.save(output, format="PNG")
    output.seek(0)
    return output
