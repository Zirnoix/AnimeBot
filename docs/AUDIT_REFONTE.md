# Audit & refonte — AnimeBot

Document vivant : inventaire **complet** des fichiers Python (58), rôles, dépendances, et suivi des évolutions.  
*Dernière mise à jour : refonte partielle (centralisation barres ▰▱, module `text_bars`).*

## Cartographie

- **Point d’entrée** : `bot.py` — intents, chargement des cogs, slash global, garde anti-abus (`modules.abuse`), webhook Top.gg optionnel.
- **Données & API** : `modules/core.py` — gros module (XP, niveaux, AniList, mini-scores, caches, SQLite partiel, etc.).
- **Cogs** : une responsabilité par fichier (voir tableau ci-dessous).
- **Tests** : `tests/` — à exécuter après tout changement transversal.

## Liste des fichiers `.py` (aucun omis)

| Fichier | Rôle |
|--------|------|
| `bot.py` | Lancement bot, sync commandes, événements globaux |
| `cogs/__init__.py` | Package cogs |
| `cogs/admin_anilist.py` | Admin / refresh stats AniList |
| `cogs/airings_admin.py` | Admin diffusions |
| `cogs/alerts.py` | Alertes utilisateur |
| `cogs/anilist_sync.py` | Sync / tâches AniList |
| `cogs/botinfo.py` | Commande infos bot |
| `cogs/community_games.py` | Jeux communauté |
| `cogs/discovery.py` | Découverte contenu |
| `cogs/emoji_autosync.py` | Sync emojis |
| `cogs/emoji_status.py` | Statut emojis |
| `cogs/engagement.py` | Missions quotidiennes, check-in |
| `cogs/episodes.py` | Épisodes |
| `cogs/events.py` | Événements Discord / onboarding texte |
| `cogs/help.py` | Aide commandes |
| `cogs/link.py` | Lien AniList, duelstats |
| `cogs/minigames.py` | Mini-jeux divers |
| `cogs/opening.py` | Guess OP / chaînes |
| `cogs/owner_hub.py` | Panneau owner |
| `cogs/presence.py` | Présence / statut |
| `cogs/profile.py` | mycard, profile, mybadges, animetop |
| `cogs/quiz.py` | Quiz image |
| `cogs/quiz_reset.py` | Reset quiz |
| `cogs/reminder_digest.py` | Rappels digest |
| `cogs/reportbug.py` | Signalement bugs |
| `cogs/stats.py` | mystats, stats AniList |
| `cogs/tracker.py` | Tracker utilisateur |
| `cogs/utils.py` | Utilitaires cog |
| `cogs/vote.py` | Top.gg vote |
| `modules/__init__.py` | Package (vide) |
| `modules/abuse.py` | Limitation slash flood |
| `modules/anilist_gate.py` | Garde accès AniList |
| `modules/animethemes.py` | API AnimeThemes |
| `modules/badge_helpers.py` | Compteurs badges |
| `modules/badges.py` | Définition badges |
| `modules/bug_report.py` | Stockage bugs |
| `modules/core.py` | Cœur données / XP / AniList / jeux |
| `modules/emoji_utils.py` | Résolution emojis custom |
| `modules/guessop_catalog.py` | Catalogue Guess OP |
| `modules/higherlower_combine.py` | Logique H/L |
| `modules/image.py` | Génération carte mycard |
| `modules/mission_definitions.py` | Définitions missions |
| `modules/mission_logic.py` | Logique missions |
| `modules/minigame_lock.py` | Verrous mini-jeux |
| `modules/owner_actions.py` | Actions owner |
| `modules/text_bars.py` | **Barres texte ▰▱ unifiées** |
| `modules/topgg_vote.py` | Persistance votes Top.gg |
| `modules/user_reply.py` | Réponses utilisateur (utilitaire) |
| `modules/voice.py` | Vocal |
| `scripts/verify_bot_commands.py` | Vérif commandes |
| `scripts/verify_local.py` | Vérif locale |
| `scripts/test_animethemes.py` | Test AnimeThemes |
| `scripts/fetch_openings.py` | Fetch openings |
| `tests/conftest.py` | Pytest fixtures |
| `tests/test_badge_helpers.py` | Tests badges |
| `tests/test_mission_definitions.py` | Tests définitions missions |
| `tests/test_mission_logic.py` | Tests logique missions |
| `tests/test_title_matching.py` | Tests titres |
| `tools/make_hybrid.py` | Outil hybrid |

## Dépendances principales

```
bot.py
  └── cogs/* → modules/core.py, modules/* (badges, abuse, …)
modules/core.py ← la plupart des cogs (couplage fort : à traiter progressivement)
```

## Refontes réalisées (session)

- **`modules/text_bars.py`** :
  - `pct_bar()` générique (choix des caractères rempli / vide) ;
  - `pct_bar_parallelogram()` (▰▱) : badges, stats, missions, XP profil, `core.get_xp_bar` ;
  - `pct_bar_blocks()` (█░) : timer Guess OP, PV boss raid ;
  - constantes `FILLED_PAR`, `EMPTY_PAR`, `FILLED_BLOCK`, `EMPTY_BLOCK`.

## Pistes prioritaires (roadmap)

1. **Réduire la taille de `core.py`** : scinder par domaine (AniList, XP, mini-scores) sans casser les imports.
2. **Typage & ruff** : introduire `ruff` / `mypy` en CI (déjà `ci.yml` à étendre).
3. **Textes** : repasser `help.py` et `events.py` à la suite des évolutions de commandes.
4. **Duplication** : `fmt_int` vs `_fmt_number` — factoriser dans `modules/formatting.py` si besoin.

## Vérifications

```bash
python -m compileall .
pytest tests/
```
