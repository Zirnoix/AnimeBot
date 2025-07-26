from PIL import Image, ImageDraw, ImageFont, ImageFilter
import os

FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

def create_xp_image(username, level, xp_bar, avatar_path):
    width, height = 500, 160
    image = Image.new("RGB", (width, height), (30, 30, 30))
    draw = ImageDraw.Draw(image)

    try:
        font_title = ImageFont.truetype(FONT_PATH, 24)
        font_info = ImageFont.truetype(FONT_PATH, 18)
    except:
        font_title = font_info = None

    draw.text((160, 20), f"{username}", font=font_title, fill=(255, 255, 255))
    draw.text((160, 60), f"Niveau : {level}", font=font_info, fill=(200, 200, 200))
    draw.text((160, 90), f"{xp_bar}", font=font_info, fill=(180, 180, 255))

    try:
        avatar = Image.open(avatar_path).convert("RGBA").resize((120, 120))
        mask = Image.new("L", avatar.size, 0)
        draw_mask = ImageDraw.Draw(mask)
        draw_mask.ellipse((0, 0, 120, 120), fill=255)
        avatar.putalpha(mask)
        image.paste(avatar, (20, 20), avatar)
    except:
        pass

    return image
