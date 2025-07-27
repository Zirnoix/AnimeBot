import random

def get_random_anime_data():
    animes = [
        {"title": "Attack on Titan", "image": "https://cdn.myanimelist.net/images/anime/10/47347.jpg"},
        {"title": "My Hero Academia", "image": "https://cdn.myanimelist.net/images/anime/10/78745.jpg"},
        {"title": "Naruto", "image": "https://cdn.myanimelist.net/images/anime/13/17405.jpg"},
        {"title": "One Piece", "image": "https://cdn.myanimelist.net/images/anime/6/73245.jpg"}
    ]
    return random.choice(animes)
