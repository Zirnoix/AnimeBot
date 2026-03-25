# 🤖 AnimeBot

AnimeBot est un bot Discord qui vous permet de :
- 📅 Voir les prochains épisodes d’anime à venir
- ⏰ Recevoir des rappels personnalisés avant la sortie
- 📬 Recevoir un résumé quotidien des épisodes en DM
- 🧭 Consulter le planning complet de la semaine
- 🌙 Tout ça basé sur votre compte [AniList](https://anilist.co)

---

## 🛠️ Commandes (principalement en slash)

Le bot est pensé pour les **commandes slash** (`/…`). Certaines commandes restent aussi invoquables avec le préfixe **`!`** ou une mention du bot.

Exemples courants :

- **Planning & épisodes** : `/next`, `/planning`, `/monnext`, `/monplanning`, `/decouverte`
- **Mini-jeux & quiz** : `/minijeux`, `/animequiz`, `/guessyear`, `/guessop`, …
- **Profil & stats** : `/mycard`, `/mystats`, `/mybadges`, `/checkin`, `/mission`
- **Suivi** : `/track`, `/add`, `/list`, …
- **Réglages** : `/reminder`, `/setalert`, `/setchannel`, `/linkanilist`
- **Aide** : `/help`, `/helpowner` (owner)

La liste complète et les descriptions détaillées sont dans **`/help`** une fois le bot invité.

---

## 🚀 Déploiement (Railway ou machine locale)

### Prérequis

- Python 3.10+ et dépendances : `pip install -r requirements.txt`
- Dossier **`data/`** : la base SQLite (`data/bot.db` par défaut, surchargeable avec `DB_PATH`), les JSON du bot, etc. Sur un hébergeur, montez un volume persistant sur ce dossier pour ne pas perdre l’historique.

### Variables d’environnement principales

| Variable | Rôle |
|----------|------|
| `DISCORD_BOT_TOKEN` | **Obligatoire** — token du bot |
| `OWNER_ID` | **Obligatoire** — ID Discord (nombre) du propriétaire : commandes owner, `/admin`, `is_owner`, etc. |
| `APPLICATION_ID` | ID de l’application Discord (recommandé pour les slash commands) |
| `BOT_TIMEZONE` | Fuseau pour planning / missions (défaut : `Europe/Paris`) |
| `ANILIST_USERNAME` | Compte AniList utilisé par défaut pour certaines intégrations |
| `LOG_LEVEL` | Niveau de log (`INFO`, `DEBUG`, …) |
| `DEV_GUILD_IDS` | IDs de serveurs séparés par des virgules — sync rapide des commandes slash en dev (voir `bot.py`) |
| `PORT` / `HEALTHCHECK_PORT` | Si défini (ex. **Railway** fournit `PORT`), le bot expose **`/`** et **`/health`** en HTTP `200` pour les healthchecks |

Autres options : `DB_PATH`, `ANILIST_TTL_HOURS`, `DEEPL_API_KEY`, etc. (voir `bot.py` et `modules/core.py`).

### Railway

1. Publiez ce dépôt sur GitHub
2. Allez sur [https://railway.app](https://railway.app)
3. `New Project` → `Deploy from GitHub repo`
4. Dans `Variables`, définissez au minimum `DISCORD_BOT_TOKEN` et **`OWNER_ID`**, ainsi qu’idéalement `APPLICATION_ID` et `BOT_TIMEZONE`
5. Ajoutez un **volume** pointant vers `data` si vous voulez conserver la base entre redéploiements
6. Commande de démarrage typique : `python bot.py` (selon votre `Procfile` / config Railway)

### Commandes slash

Le bot gère le sync des slash commands via la logique dans `bot.py` (sync par guilde en dev avec `DEV_GUILD_IDS`, pas de purge globale automatique pour limiter les 429). Après un gros changement de commandes, utilisez les outils admin du bot ou redeployez avec les guildes de dev configurées pour rafraîchir les commandes sur vos serveurs de test.

### CI (GitHub Actions)

Sur push ou pull request vers `main` ou `master`, le workflow [`.github/workflows/ci.yml`](.github/workflows/ci.yml) installe `requirements-dev.txt` et lance **`pytest`**.

---

Développé avec ❤️ par [Zirnoixdcoco]
