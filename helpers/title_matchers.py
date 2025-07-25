import re
import unicodedata

def normalize(text):
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("utf-8")
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", "", text)
    text = re.sub(r"\b(season|s\d+|ii|iii|iv|v|ova|movie|special)\b", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

def generate_aliases(titles):
    aliases = set()

    for t in titles.values():
        if t:
            aliases.add(normalize(t))

    # Exemple d'abréviations :
    if "boku no hero academia" in aliases:
        aliases.add("bnha")
    if "shingeki no kyojin" in aliases or "attack on titan" in aliases:
        aliases.update({"aot", "snk"})
    if "one piece" in aliases:
        aliases.add("op")
    if "kimetsu no yaiba" in aliases or "demon slayer" in aliases:
        aliases.add("kny")

    return aliases

