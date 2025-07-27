from PIL import Image, ImageDraw, ImageFont

def create_xp_image(user_name, level, score):
    img = Image.new("RGB", (400, 100), color=(54, 57, 63))
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()
    draw.text((10, 10), f"{user_name} - Niveau: {level}", font=font, fill=(255, 255, 255))
    draw.text((10, 50), f"XP: {score}", font=font, fill=(255, 255, 255))
    path = f"/mnt/data/{user_name}_rank.png"
    img.save(path)
    return path
