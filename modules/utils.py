import json

def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def get_user_level(score):
    if score >= 100:
        return "🌌 Légende"
    elif score >= 80:
        return "🔥 Champion"
    elif score >= 60:
        return "🎯 Expert"
    elif score >= 40:
        return "📚 Connaisseur"
    elif score >= 20:
        return "🌱 Amateur"
    else:
        return "👶 Débutant"
