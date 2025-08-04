# modules/image.py

from PIL import Image, ImageDraw, ImageFont
import os
import io

BASE_WIDTH = 800
BASE_HEIGHT = 400
FONTS_PATH = "assets/fonts"
FONT_PATH_DEFAULT = os.path.join(FONTS_PATH, "OpenSans-Bold.ttf")


def generate_text_image(text: str, title: str = "", width: int = BASE_WIDTH, height: int = BASE_HEIGHT) -> io.BytesIO:
    image = Image.new("RGB", (width, height), color=(30, 30, 30))
    draw = ImageDraw.Draw(image)

    try:
        title_font = ImageFont.truetype(FONT_PATH_DEFAULT, 32)
        text_font = ImageFont.truetype(FONT_PATH_DEFAULT, 24)
    except:
        title_font = ImageFont.load_default()
        text_font = ImageFont.load_default()

    if title:
        draw.text((width // 2, 30), title, font=title_font, fill="white", anchor="mm")

    lines = text.split("\n")
    y_text = 100
    for line in lines:
        draw.text((width // 2, y_text), line, font=text_font, fill="white", anchor="mm")
        y_text += 40

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


def save_user_card(username: str, xp: int, rank: str, output_path: str):
    image = Image.new("RGB", (600, 300), color=(15, 15, 15))
    draw = ImageDraw.Draw(image)

    try:
        font_title = ImageFont.truetype(FONT_PATH_DEFAULT, 28)
        font_info = ImageFont.truetype(FONT_PATH_DEFAULT, 22)
    except:
        font_title = ImageFont.load_default()
        font_info = ImageFont.load_default()

    draw.text((20, 30), f"{username}", font=font_title, fill="white")
    draw.text((20, 90), f"XP: {xp}", font=font_info, fill="white")
    draw.text((20, 130), f"Titre: {rank}", font=font_info, fill="white")

    image.save(output_path)


def ensure_asset_dirs():
    os.makedirs("assets/fonts", exist_ok=True)
    os.makedirs("assets/img", exist_ok=True)
    os.makedirs("data", exist_ok=True)
    os.makedirs("cogs", exist_ok=True)
    os.makedirs("modules", exist_ok=True)
