import random

def get_title(score):
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

def shuffle_choices(correct, options):
    choices = options.copy()
    if correct not in choices:
        choices.append(correct)
    random.shuffle(choices)
    return choices
