# Gestion des emoTIER_EMOJIS = {
    "Débutant": "👶",
    "Amateur": "🌱",
    "Connaisseur": "📚",
    "Expert": "🎯",
    "Champion": "🔥",
    "Légende": "🌌",

}

EMOJIS = {
    "success": "✅",
    "error": "❌",
    "loading": "⌛",
    "star": "⭐",
    "calendar": "📅",
    "clock": "🕒",
    "link": "🔗",
    "warning": "⚠️",
    "info": "ℹ️"
}


def get_title(score):
    if score >= 100:
        return "Légende"
    elif score >= 80:
        return "Champion"
    elif score >= 60:
        return "Expert"
    elif score >= 40:
        return "Connaisseur"
    elif score >= 20:
        return "Amateur"
    else:
        return "Débutant"


def get_emoji_for_title(title):
    return TIER_EMOJIS.get(title, "❔")jis ici
