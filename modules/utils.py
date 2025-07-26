import json

def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

def get_xp_bar(current, total, length=20):
    filled = int(length * current // total)
    bar = "█" * filled + "—" * (length - filled)
    return f"[{bar}] {current}/{total}"