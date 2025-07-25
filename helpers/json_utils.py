import json
import os

def load_json(filename, default=None):
    if not os.path.exists(filename):
        return default if default is not None else {}
    with open(filename, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(filename, data):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
