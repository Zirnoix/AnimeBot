# modules/image.py (ajoute tout à la fin du fichier)

from PIL import Image, ImageDraw, ImageFont
import requests
from io import BytesIO
from datetime import datetime
import os

def generate_next_anime_image(title, episode, airing_time, cover_url):
    width, height = 800, 400
    bg_color = (30, 30, 30)
    font_title = ImageFont.truetype("assets/fonts/DejaVuSans.ttf", 38)
    font_info = ImageFont.truetype("assets/fonts/DejaVuSans.ttf", 24)

    image = Image.new("RGB", (width, height), color=bg_color)
    draw = ImageDraw.Draw(image)

    # Télécharger l’image de couverture
    response = requests.get(cover_url)
    cover = Image.open(BytesIO(response.content)).resize((260, 360))
    image.paste(cover, (20, 20))

    # Infos à afficher
    draw.text((300, 40), title, font=font_title, fill=(255, 255, 255))
    draw.text((300, 120), f"Épisode {episode}", font=font_info, fill=(200, 200, 200))

    dt = datetime.fromtimestamp(airing_time)
    date_str = dt.strftime("%A %d %B %Y à %Hh%M")
    draw.text((300, 170), f"Diffusion : {date_str}", font=font_info, fill=(200, 200, 200))

    buffer = BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


def save_user_card(username: str, xp: int, rank: str, path: str):
    os.makedirs("data", exist_ok=True)
    width, height = 500, 200
    image = Image.new("RGB", (width, height), color=(30, 30, 30))
    draw = ImageDraw.Draw(image)

    font_title = ImageFont.truetype("DejaVuSans.ttf", 24)
    font_text = ImageFont.truetype("DejaVuSans.ttf", 18)

    draw.text((20, 20), f"👤 {username}", font=font_title, fill=(255, 255, 255))
    draw.text((20, 70), f"XP : {xp}", font=font_text, fill=(200, 200, 200))
    draw.text((20, 100), f"🎖 Rang : {rank}", font=font_text, fill=(200, 200, 200))

    image.save(path)


def save_profile_card(username: str, rank: str, quiz_pts: int, top_ranked: bool,
                      guess_scores: dict, path: str):
    os.makedirs("data", exist_ok=True)
    width, height = 600, 300
    image = Image.new("RGB", (width, height), color=(20, 20, 25))
    draw = ImageDraw.Draw(image)

    font_title = ImageFont.truetype("DejaVuSans.ttf", 26)
    font_text = ImageFont.truetype("DejaVuSans.ttf", 18)

    draw.text((20, 20), f"🎴 Profil de {username}", font=font_title, fill=(255, 255, 255))
    draw.text((20, 70), f"🎖 Rang : {rank}", font=font_text, fill=(200, 200, 255))
    draw.text((20, 100), f"📊 Quiz Points : {quiz_pts}", font=font_text, fill=(180, 255, 180))
    draw.text((20, 130), f"🏆 Dans le top : {'Oui' if top_ranked else 'Non'}", font=font_text, fill=(255, 230, 180))

    y = 170
    draw.text((20, y), "🧩 Scores par jeu :", font=font_text, fill=(255, 255, 255))
    for game, pts in guess_scores.items():
        y += 25
        draw.text((40, y), f"{game.capitalize()} : {pts} pts", font=font_text, fill=(200, 200, 200))

    image.save(path)
