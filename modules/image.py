# modules/image.py (ajoute tout à la fin du fichier)

from PIL import Image, ImageDraw, ImageFont
import requests
from io import BytesIO
from datetime import datetime
import os

FONT_PATH = "assets/fonts/DejaVuSans.ttf"
OUTPUT_DIR = "data/cards"

os.makedirs(OUTPUT_DIR, exist_ok=True)

def generate_profile_card(user_name: str, quiz_points: int, guess_points: int, guess_year_points: int, titles: list, output_path: str = None):
    width, height = 800, 400
    card = Image.new("RGB", (width, height), (30, 30, 30))
    draw = ImageDraw.Draw(card)

    try:
        font_title = ImageFont.truetype(FONT_PATH, 36)
        font_text = ImageFont.truetype(FONT_PATH, 24)
    except:
        font_title = font_text = None  # fallback if font missing

    draw.text((30, 30), f"Profil de {user_name}", font=font_title, fill=(255, 255, 255))
    draw.text((30, 100), f"🎮 AnimeQuiz : {quiz_points} pts", font=font_text, fill=(255, 255, 255))
    draw.text((30, 150), f"🧠 Guess Genre : {guess_points} pts", font=font_text, fill=(255, 255, 255))
    draw.text((30, 200), f"📅 Guess Year : {guess_year_points} pts", font=font_text, fill=(255, 255, 255))
    draw.text((30, 250), f"🏆 Titres : {', '.join(titles) if titles else 'Aucun'}", font=font_text, fill=(255, 255, 255))

    if not output_path:
        output_path = os.path.join(OUTPUT_DIR, f"{user_name}_profile_card.png")

    card.save(output_path)
    return output_path

def generate_stats_image(stats: dict, output_path: str = None):
    width, height = 800, 600
    card = Image.new("RGB", (width, height), (40, 40, 40))
    draw = ImageDraw.Draw(card)

    try:
        font_title = ImageFont.truetype(FONT_PATH, 36)
        font_text = ImageFont.truetype(FONT_PATH, 22)
    except:
        font_title = font_text = None

    draw.text((30, 30), "📊 Statistiques Anime", font=font_title, fill=(255, 255, 255))

    y = 100
    for key, value in stats.items():
        draw.text((30, y), f"{key}: {value}", font=font_text, fill=(255, 255, 255))
        y += 40

    if not output_path:
        output_path = os.path.join(OUTPUT_DIR, "stats_card.png")

    card.save(output_path)
    return output_path
    
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
