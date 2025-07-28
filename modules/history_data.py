import datetime

# Dictionnaire d'exemples d'événements historiques liés aux animés
HISTORY_DATA = {
    "07-27": [
        "✨ 2002 : Diffusion de l’épisode final de *Naruto* au Japon.",
        "📚 1995 : Sortie du manga *Great Teacher Onizuka*."
    ],
    "12-25": [
        "🎄 Joyeux Noël ! Peu d’animes diffusés ce jour-là."
    ],
    # Ajoute ici les autres dates au format MM-JJ
}

def get_today_anime_facts():
    today = datetime.datetime.now().strftime("%m-%d")
    return HISTORY_DATA.get(today, [])
