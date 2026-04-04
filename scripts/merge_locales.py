"""Fusionne les blocs i18n dans modules/locales/fr.json et en.json (usage dev)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules import core  # noqa: E402


def _pairs(tuples: list[tuple[int, str]]) -> list[list]:
    return [[a, b] for a, b in tuples]


TITLES_GLOBAL_EN = [
    [0, "👶 Novice"],
    [3, "🌱 Initiate"],
    [6, "📗 Beginner"],
    [9, "🔧 Practitioner"],
    [12, "🧭 Explorer"],
    [15, "🎯 Approved"],
    [20, "⚔️ Aspirant"],
    [25, "🏹 Disciple"],
    [30, "🛡️ Knight"],
    [37, "🧠 Strategist"],
    [44, "🔥 Master"],
    [51, "🌪️ Virtuoso"],
    [58, "💎 Elite"],
    [65, "🌟 Heroic"],
    [72, "🐉 Archon"],
    [79, "⚡ Dominant"],
    [86, "🌌 Mythic"],
    [93, "🏆 Paragon"],
    [100, "👑 Sovereign"],
    [107, "🗼 Eminence"],
    [114, "🜲 Arcanist"],
    [121, "🪽 Seraph"],
    [128, "☄️ Sidereal"],
    [135, "🜚 Transcendent"],
    [142, "🛐 Divine"],
    [150, "♾️ Apotheosis"],
]

TITLES_QUIZ_EN = [
    [0, "👶 Newcomer"],
    [5, "🌱 Apprentice"],
    [10, "📘 Amateur"],
    [15, "📚 Confirmed Otaku"],
    [20, "🎯 Expert"],
    [25, "🔥 Otaku Master"],
    [30, "🧠 Sensei"],
    [35, "🧩 Strategist"],
    [40, "🏆 Champion"],
    [45, "🌟 Local Legend"],
    [50, "💎 National Legend"],
    [55, "🗿 Anime Icon"],
    [60, "🐉 Myth"],
    [65, "🛐 Otaku God"],
    [70, "☄️ Universal Divinity"],
    [75, "🔮 Omniscient Otaku"],
    [80, "⚡ Master of Lightning"],
    [85, "🌌 Galactic Traveler"],
    [90, "🏮 Anime Guardian"],
    [95, "🎭 Master of Illusions"],
    [100, "👑 King of Otakus"],
]


def main() -> None:
    fr_path = ROOT / "modules" / "locales" / "fr.json"
    en_path = ROOT / "modules" / "locales" / "en.json"
    fr = json.loads(fr_path.read_text(encoding="utf-8"))
    en = json.loads(en_path.read_text(encoding="utf-8"))

    common_fr = {
        "slash_only": "Cette commande est réservée au **slash** : utilise `/{name}` dans la barre de commandes.",
        "weekdays": ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"],
        "abuse_rate_limit": "⏳ Trop de commandes en peu de temps — réessaie dans **{seconds}s**.",
    }
    common_en = {
        "slash_only": "This command is **slash-only** — use `/{name}` in the command bar.",
        "weekdays": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
        "abuse_rate_limit": "⏳ Too many commands — try again in **{seconds}s**.",
    }

    xp_fr = {
        "titles_global": _pairs(core.LEVEL_TITLES_GLOBAL),
        "titles_quiz": _pairs(core.LEVEL_TITLES_QUIZ),
        "announce_new_title": "🎉 **<@{user_id}>** débloque un **nouveau titre** : **{title}** _(niveau **{level}**)_ !",
        "announce_quiz_title": "📚 **<@{user_id}>** débloque un **nouveau titre quiz** : **{title}** _(score **{score}** pts)_ !",
    }
    xp_en = {
        "titles_global": TITLES_GLOBAL_EN,
        "titles_quiz": TITLES_QUIZ_EN,
        "announce_new_title": "🎉 **<@{user_id}>** unlocked a **new title**: **{title}** _(level **{level}**)_!",
        "announce_quiz_title": "📚 **<@{user_id}>** unlocked a **new quiz title**: **{title}** _(score **{score}** pts)_!",
    }

    fr["common"] = common_fr
    en["common"] = common_en
    fr["xp"] = xp_fr
    en["xp"] = xp_en

    fr["utils"] = {
        "ping": "🏓 Pong ! Latence : **{latency} ms**",
        "uptime": "⏳ Uptime : **{days}j {hours}h {minutes}m {seconds}s**",
        "source": "📦 Code source du bot : https://github.com/Zirnoix/AnimeBot",
        "need_guild": "❌ Cette commande doit être utilisée dans un serveur.",
        "setchannel_ok": (
            "✅ Ce salon recevra les **cartes « sortie d’épisode »** pour **ce serveur**.\n"
            "• Liste des animés suivis : **`/airings`** (ex. **`/airings all`** pour les admins).\n"
            "• **Indépendant** du salon du **raid boss** (`/raidconfig`).\n"
            "• Si tu n’as **aucune** annonce alors que la liste est remplie : vérifie les **permissions** du bot "
            "dans ce salon, et que l’API AniList répond (les annonces utilisent la fenêtre après diffusion)."
        ),
        "setlevelup_ok": (
            "✅ Ce salon recevra les **annonces** suivantes (au lieu du salon où la partie a lieu) :\n"
            "• **Nouveau titre global** (XP `/profile`, `/myrank`) — une annonce par **palier de titre**, pas à chaque niveau.\n"
            "• **Nouveau titre quiz** (score des quiz solo `/animequiz`, `/animequizmulti`) — mêmes paliers que sur la carte.\n"
            "• Pour revenir au comportement par défaut : **`/clearlevelupchannel`**."
        ),
        "clearlevelup_ok": (
            "✅ Les montées de niveau XP seront à nouveau annoncées **dans le salon où la partie a lieu** "
            "(ou pas annoncées si l’XP est donnée sans salon)."
        ),
        "config_err": "❌ Une erreur s'est produite lors de la configuration.",
        "clearlevelup_err": "❌ Une erreur s'est produite.",
    }
    en["utils"] = {
        "ping": "🏓 Pong! Latency: **{latency} ms**",
        "uptime": "⏳ Uptime: **{days}d {hours}h {minutes}m {seconds}s**",
        "source": "📦 Bot source code: https://github.com/Zirnoix/AnimeBot",
        "need_guild": "❌ This command must be used in a server.",
        "setchannel_ok": (
            "✅ This channel will receive **episode release cards** for **this server**.\n"
            "• Tracked anime list: **`/airings`** (e.g. **`/airings all`** for admins).\n"
            "• **Independent** from the **raid boss** channel (`/raidconfig`).\n"
            "• If you get **no** alerts while the list is filled: check **bot permissions** here, "
            "and that the AniList API responds (alerts use the post-air window)."
        ),
        "setlevelup_ok": (
            "✅ This channel will receive the following **announcements** (instead of the channel where play happens):\n"
            "• **New global title** (XP `/profile`, `/myrank`) — one announcement per **title tier**, not every level.\n"
            "• **New quiz title** (solo quiz score `/animequiz`, `/animequizmulti`) — same tiers as on the card.\n"
            "• To reset default behaviour: **`/clearlevelupchannel`**."
        ),
        "clearlevelup_ok": (
            "✅ Level-up announcements will again be posted **in the channel where the game happened** "
            "(or not announced if XP was granted without a channel)."
        ),
        "config_err": "❌ An error occurred while saving settings.",
        "clearlevelup_err": "❌ An error occurred.",
    }

    fr["botinfo"] = {
        "embed_title": "AnimeBot — Informations",
        "embed_desc": "Merci d’utiliser AnimeBot 💙",
        "field_version": "Version",
        "field_latency": "Latence",
        "field_uptime": "Uptime",
        "field_guilds": "Serveurs",
        "field_members": "Membres (approx.)",
        "field_python": "Python",
        "field_anilist_ok": "joignable",
        "field_anilist_bad": "dégradée / hors ligne",
        "field_anilist": "API AniList",
        "field_slash": "Commandes /",
        "field_slash_val": "Les slash peuvent mettre **1–2 min** à apparaître après l’invitation du bot.",
        "field_vote": "⭐ Soutenir AnimeBot",
        "field_vote_val": (
            "**`/vote`** — vote gratuit sur **Top.gg** (visibilité + **XP** bonus sur ta carte). "
            "Pense à y passer de temps en temps ; rappel MP optionnel dans la commande."
        ),
        "field_bug": "🐞 Signaler un bug",
        "field_bug_val": (
            "**`/reportbug`** — signale un bug en **MP** ; si tu aides à corriger un vrai problème, "
            "tu peux gagner de l’**XP** (voir aussi **`/mycard`** si tu as déjà des bugs validés)."
        ),
        "field_al_linked": "Ton compte AniList",
        "field_al_val_linked": "Lié : **`{name}`**",
        "field_al_val_unlinked": "Non lié — **`/linkanilist`** puis **`/verifyanilist`** pour stats, récaps MP, `/mystats` rapide…",
        "footer": "/help · /vote · /reportbug · /airings · /linkanilist",
    }
    en["botinfo"] = {
        "embed_title": "AnimeBot — Info",
        "embed_desc": "Thanks for using AnimeBot 💙",
        "field_version": "Version",
        "field_latency": "Latency",
        "field_uptime": "Uptime",
        "field_guilds": "Servers",
        "field_members": "Members (approx.)",
        "field_python": "Python",
        "field_anilist_ok": "reachable",
        "field_anilist_bad": "degraded / offline",
        "field_anilist": "AniList API",
        "field_slash": "Slash commands",
        "field_slash_val": "Slash commands can take **1–2 min** to show after inviting the bot.",
        "field_vote": "⭐ Support AnimeBot",
        "field_vote_val": (
            "**`/vote`** — free vote on **Top.gg** (visibility + bonus **XP** on your card). "
            "Drop by from time to time; optional DM reminder in the command."
        ),
        "field_bug": "🐞 Report a bug",
        "field_bug_val": (
            "**`/reportbug`** — report a bug in **DMs**; if you help fix a real issue, you can earn **XP** "
            "(see **`/mycard`** if you already have validated reports)."
        ),
        "field_al_linked": "Your AniList account",
        "field_al_val_linked": "Linked: **`{name}`**",
        "field_al_val_unlinked": "Not linked — **`/linkanilist`** then **`/verifyanilist`** for stats, DM recaps, quick `/mystats`…",
        "footer": "/help · /vote · /reportbug · /airings · /linkanilist",
    }

    fr["alerts"] = {
        "release_header": "📺 **Sortie** — l’épisode est disponible !",
        "fallback_line": "{header}\n**{title}** — Épisode **{ep}** • {when}",
    }
    en["alerts"] = {
        "release_header": "📺 **Out** — the episode is available!",
        "fallback_line": "{header}\n**{title}** — Episode **{ep}** • {when}",
    }

    fr["admin_anilist"] = {
        "sync_none": "Aucun compte AniList lié trouvé.",
        "sync_done": "Sync terminée : **{ok}/{total}** comptes rafraîchis.",
        "no_user": "Aucun username AniList lié/valide à synchroniser.",
        "embed_title": "AniList Sync",
        "field_user": "Utilisateur",
        "f_completed": "✅ Completed (MLC)",
        "f_current": "📺 En cours (MLC)",
        "f_total": "📚 Total entrées (MLC)",
        "f_prof": "🎬 Animés vus (profil)",
        "f_mean": "⭐ Note moyenne",
        "f_genre": "🎭 Genre favori",
        "footer_force": "Force refresh",
        "footer_ttl": "TTL {ttl}h",
    }
    en["admin_anilist"] = {
        "sync_none": "No linked AniList accounts found.",
        "sync_done": "Sync done: **{ok}/{total}** accounts refreshed.",
        "no_user": "No linked/valid AniList username to sync.",
        "embed_title": "AniList Sync",
        "field_user": "User",
        "f_completed": "✅ Completed (MLC)",
        "f_current": "📺 Current (MLC)",
        "f_total": "📚 Total entries (MLC)",
        "f_prof": "🎬 Watched (profile)",
        "f_mean": "⭐ Mean score",
        "f_genre": "🎭 Favorite genre",
        "footer_force": "Force refresh",
        "footer_ttl": "TTL {ttl}h",
    }

    fr["emoji_status"] = {
        "denied": "⛔ Accès refusé.",
        "no_guild": "❌ Guild d'assets introuvable.",
        "empty": "Aucun emoji.",
        "cmd_desc": "Liste les emojis synchronisés.",
        "whoami_desc": "Debug: infos d’autorisation.",
    }
    en["emoji_status"] = {
        "denied": "⛔ Access denied.",
        "no_guild": "❌ Assets server not found.",
        "empty": "No emojis.",
        "cmd_desc": "List synced emojis.",
        "whoami_desc": "Debug: authorization info.",
    }

    fr["presence"] = {
        "scenes": [
            "/help — guide & nouveautés",
            "Toujours en développement — idées bienvenues",
            "Quiz · AniList · sorties · mini-jeux",
            "Boss raid, devinettes, duels… voir /help",
            "Une question ? Commence par /help",
            "Améliorations régulières — restez à l’affût",
            "Lien AniList, rappels, stats : /help",
            "/reportbug — XP bonus (vrai bug)",
            "Bug repéré ? /reportbug",
        ],
        "version_suffix": "v{v} · AnimeBot",
    }
    en["presence"] = {
        "scenes": [
            "/help — guide & news",
            "Always improving — ideas welcome",
            "Quiz · AniList · releases · minigames",
            "Raid boss, guessing games, duels… see /help",
            "Questions? Start with /help",
            "Regular updates — stay tuned",
            "AniList link, reminders, stats: /help",
            "/reportbug — bonus XP (real bugs)",
            "Found a bug? /reportbug",
        ],
        "version_suffix": "v{v} · AnimeBot",
    }

    fr["owner"] = {
        "denied": "❌ Réservé au propriétaire du bot.",
        "unknown_action": "❌ Action inconnue.",
        "err": "❌ Erreur : `{err}`",
        "panel_denied": "❌ Réservé au **propriétaire** du bot (`OWNER_ID` sur l’hébergeur).",
        "panel_title": "🔧 Panneau propriétaire",
        "panel_desc": (
            "Choisis une action dans le menu ci-dessous. Tout est **éphémère** (visible par toi seul).\n\n"
        ),
        "panel_footer": "Outils owner regroupés ici — Guess OP, stats, aide MP, etc.",
        "select_placeholder": "Choisir une action…",
        "setavatar_need": "❌ Envoie l’image **dans le même message** que **`!setavatar`**.",
        "setavatar_ok": "✅ Avatar du bot mis à jour.",
        "cmd_desc": "Panneau propriétaire : debug, stats, tests (OWNER_ID uniquement).",
    }
    en["owner"] = {
        "denied": "❌ Owner only.",
        "unknown_action": "❌ Unknown action.",
        "err": "❌ Error: `{err}`",
        "panel_denied": "❌ **Owner** only (`OWNER_ID` on the host).",
        "panel_title": "🔧 Owner panel",
        "panel_desc": (
            "Pick an action below. Everything is **ephemeral** (only you see it).\n\n"
        ),
        "panel_footer": "Owner tools — Guess OP, stats, DM help, etc.",
        "select_placeholder": "Choose an action…",
        "setavatar_need": "❌ Send the image **in the same message** as **`!setavatar`**.",
        "setavatar_ok": "✅ Bot avatar updated.",
        "cmd_desc": "Owner panel: debug, stats, tests (OWNER_ID only).",
    }

    fr["vote"] = {
        "cmd_desc": "⭐ Soutenir le bot sur Top.gg (XP bonus) — lien, cooldown, rappel MP.",
        "not_for_you": "❌ Ce panneau n’est pas pour toi.",
        "rem_on": "✅ Rappel MP **activé** — tu recevras un message quand le cooldown Top.gg sera passé.",
        "rem_off": "✅ Rappel MP **désactivé**.",
        "dm_reminder": (
            "🗳️ Tu peux **revoter** pour **AnimeBot** sur Top.gg — "
            "ça aide le bot à être visible !\n{url}\n\n"
            "_(Rappel désactivable avec `/vote` → bouton.)_"
        ),
        "status_none": (
            "Tu n’as pas encore de vote enregistré par le bot (après ton **premier** vote sur Top.gg, le cooldown s’affichera ici)."
        ),
        "eta_cooldown": "Cooldown Top.gg : **{remaining}** après chaque vote.",
        "status_ready": "✅ Tu **peux voter** (cooldown écoulé).",
        "status_wait": "⏳ Prochain vote possible dans **{remaining}**.",
        "last_vote": "Dernier vote enregistré : <t:{ts}:R>.",
        "hook_warn": (
            "\n\n⚠️ Les récompenses automatiques nécessitent `TOPGG_WEBHOOK_SECRET` + URL webhook sur Top.gg "
            "(voir doc projet / `.env.example`)."
        ),
        "reward_line": (
            "🎁 **XP :** **{xp}** de base + bonus **série** + **fidélité** "
            "· multiplicateur week-end possible."
        ),
        "stats_line": (
            "📊 **Tes votes :** **{total}** enregistré(s) · série **{streak}** j · record **{best}** "
            "_(mis à jour après chaque vote reçu par le bot)._"
        ),
        "intro": (
            "**Gratuit**, sans inscription spéciale : le bouton **ci-dessous** ouvre Top.gg. "
            "Ça aide le bot à être **mieux classé** et découvert."
        ),
        "rem_state": "🔔 Rappel MP quand tu peux revoter : **{state}** (boutons).",
        "rem_on_state": "activé",
        "rem_off_state": "désactivé",
        "embed_title": "⭐ Soutiens AnimeBot (Top.gg)",
        "embed_footer": "Pense à /vote de temps en temps — merci 💙 · Cooldown & fuseau configurables",
        "btn_vote": "🗳️ Voter sur Top.gg",
        "btn_rem_on": "🔔 Activer rappel MP",
        "btn_rem_off": "🔕 Désactiver le rappel",
        "recap_title": "🎉 Récap de ton dernier vote (toi seul·e le vois ici)",
        "recap_body": (
            "**+{xp} XP** ajoutés sur ta carte.\n"
            "{base} base + {sb} série + {lb} fidélité = **{sub}** XP avant multi.{wk}\n"
            "Série **{st}** j · record **{bst}** · **{tv}** votes au total."
        ),
        "recap_weekend": "\n_Bonus week-end appliqué sur le total._",
        "fmt_now": "maintenant",
        "fmt_soon": "bientôt",
    }
    fr["raid"] = {
        "mode": {
            "guesscharacter": "Personnage (4 choix)",
            "guessyear": "Année de diffusion",
            "guessepisodes": "Nombre d’épisodes",
            "guessgenre": "Genre",
            "higherlower": "Plus populaire (2 animés)",
            "animequiz": "Anime — affiche",
            "guesswho": "Qui est-ce ? (flou + nom)",
        },
        "tier": {"easy": "Facile", "medium": "Moyen", "hard": "Difficile"},
        "mode_tier": {
            "guesscharacter": "easy",
            "guessyear": "medium",
            "guessepisodes": "medium",
            "guessgenre": "easy",
            "higherlower": "medium",
            "animequiz": "hard",
            "guesswho": "hard",
        },
        "mode_desc": "~{lo}–{hi} dmg · coup final +{fin} XP",
        "select_placeholder": "🎯 Type de mini-jeu pour ce raid…",
    }
    en["raid"] = {
        "mode": {
            "guesscharacter": "Character (4 choices)",
            "guessyear": "Air year",
            "guessepisodes": "Episode count",
            "guessgenre": "Genre",
            "higherlower": "More popular (2 anime)",
            "animequiz": "Anime — screenshot",
            "guesswho": "Guess who? (blur + name)",
        },
        "tier": {"easy": "Easy", "medium": "Medium", "hard": "Hard"},
        "mode_tier": {
            "guesscharacter": "easy",
            "guessyear": "medium",
            "guessepisodes": "medium",
            "guessgenre": "easy",
            "higherlower": "medium",
            "animequiz": "hard",
            "guesswho": "hard",
        },
        "mode_desc": "~{lo}–{hi} dmg · finisher +{fin} XP",
        "select_placeholder": "🎯 Minigame type for this raid…",
    }

    en["vote"] = {
        "cmd_desc": "⭐ Support the bot on Top.gg (bonus XP) — link, cooldown, DM reminder.",
        "not_for_you": "❌ This panel isn’t for you.",
        "rem_on": "✅ DM reminder **enabled** — you’ll get a message when the Top.gg cooldown is over.",
        "rem_off": "✅ DM reminder **disabled**.",
        "dm_reminder": (
            "🗳️ You can **vote again** for **AnimeBot** on Top.gg — "
            "it helps visibility!\n{url}\n\n"
            "_(Disable reminder via `/vote` → button.)_"
        ),
        "status_none": (
            "No vote recorded yet by the bot (after your **first** Top.gg vote, the cooldown will show here)."
        ),
        "eta_cooldown": "Top.gg cooldown: **{remaining}** after each vote.",
        "status_ready": "✅ You **can vote** (cooldown over).",
        "status_wait": "⏳ Next vote in **{remaining}**.",
        "last_vote": "Last recorded vote: <t:{ts}:R>.",
        "hook_warn": (
            "\n\n⚠️ Auto rewards need `TOPGG_WEBHOOK_SECRET` + webhook URL on Top.gg "
            "(see project docs / `.env.example`)."
        ),
        "reward_line": (
            "🎁 **XP:** **{xp}** base + **streak** + **loyalty** bonuses "
            "· weekend multiplier possible."
        ),
        "stats_line": (
            "📊 **Your votes:** **{total}** recorded · streak **{streak}** d · best **{best}** "
            "_(updated after each vote received by the bot)._"
        ),
        "intro": (
            "**Free**, no special signup: the **button below** opens Top.gg. "
            "It helps the bot rank and get discovered."
        ),
        "rem_state": "🔔 DM reminder when you can vote again: **{state}** (buttons).",
        "rem_on_state": "on",
        "rem_off_state": "off",
        "embed_title": "⭐ Support AnimeBot (Top.gg)",
        "embed_footer": "Visit /vote from time to time — thanks 💙 · Cooldown & timezone configurable",
        "btn_vote": "🗳️ Vote on Top.gg",
        "btn_rem_on": "🔔 Enable DM reminder",
        "btn_rem_off": "🔕 Disable reminder",
        "recap_title": "🎉 Your last vote recap (only you see this)",
        "recap_body": (
            "**+{xp} XP** added to your card.\n"
            "{base} base + {sb} streak + {lb} loyalty = **{sub}** XP before multi.{wk}\n"
            "Streak **{st}** d · best **{bst}** · **{tv}** votes total."
        ),
        "recap_weekend": "\n_Weekend bonus applied to the total._",
        "fmt_now": "now",
        "fmt_soon": "soon",
    }

    import json as _json

    _desc_fr = _json.loads((ROOT / "scripts" / "_help_desc_fr.json").read_text(encoding="utf-8"))
    _desc_en = _json.loads((ROOT / "scripts" / "_help_desc_en.json").read_text(encoding="utf-8"))
    fr.setdefault("help", {})["desc"] = _desc_fr
    en.setdefault("help", {})["desc"] = _desc_en

    fr["help"]["section"] = {
        "episodes": "📺 Pages Episodes",
        "minigames": "🎯 Pages MiniGames",
        "link": "🔗 Pages Link",
        "stats": "📊 Pages Statistiques",
        "tracker": "🧭 Pages Tracker",
        "utils": "🧰 Pages Utils",
    }
    en["help"]["section"] = {
        "episodes": "📺 Episodes",
        "minigames": "🎯 Minigames",
        "link": "🔗 Link",
        "stats": "📊 Statistics",
        "tracker": "🧭 Tracker",
        "utils": "🧰 Utilities",
    }
    fr["help"]["section_admin"] = {
        "admin_config": "🛠️ Configuration & guide admin",
        "airings_list": "📺 Liste serveur (/airings)",
        "raid_config": "⚔️ Raid (configuration)",
    }
    en["help"]["section_admin"] = {
        "admin_config": "🛠️ Configuration & admin guide",
        "airings_list": "📺 Server list (/airings)",
        "raid_config": "⚔️ Raid (configuration)",
    }
    fr["help"]["ui"] = {
        "footer_page": "Page {cur}/{total} — /{cmd} <commande> pour le détail.",
        "placeholder_jump": "Aller à…",
        "btn_close": "Fermer",
        "btn_all_dm": "Voir tout (MP)",
        "dm_sent_ok": "📬 Aide complète envoyée en message privé.",
        "dm_forbidden": "❌ Impossible d’envoyer un MP (vérifie tes paramètres).",
        "dm_error": "❌ MP non envoyé (erreur inconnue).",
        "unknown_command": "Commande inconnue.",
        "slash_not_found": "❌ Commande slash introuvable. Vérifie l’orthographe ou tape `/help` pour la liste.",
        "embed_params": "Paramètres",
        "embed_example": "Exemple",
        "page_detail_hint": "Tape `/{help_cmd} <commande>` pour une fiche détaillée.",
        "not_slash_suffix": " *(non dispo en slash)*",
        "no_slash": "Aucune commande slash détectée.",
        "brief_help_title": "Aide",
        "essential_title": "📖 Aide — Essentiel",
        "essential_desc": (
            "Commandes principales — **slash** `/…` uniquement.\n"
            "• `/help <commande>` : détail · bouton **Voir tout** : liste complète en MP (depuis un serveur).\n"
            "• **Administrateurs** : `/help_admin` (config serveur, liste /airings, raid)."
        ),
        "essential_footer": "/help <commande> · commandes en slash",
        "mp_hint_title": "ℹ️ MP",
        "mp_hint_help": "Pour le bouton **Voir tout**, utilise `/help` dans un serveur.",
        "mp_hint_admin": "Pour le bouton **Voir tout**, utilise `/help_admin` dans un serveur.",
        "admin_title": "🛠️ Aide — Administrateurs",
        "admin_desc": (
            "Commandes réservées aux **administrateurs** du serveur — **slash** `/…` uniquement.\n"
            "• `/help_admin <commande>` : détail · bouton **Voir tout** : liste complète en MP."
        ),
        "admin_footer": "/help_admin <commande> · commandes en slash",
        "owner_title": "🔐 Aide — Owner/Admin",
        "owner_empty": "Aucune commande restreinte détectée.",
        "owner_desc": "Commandes réservées au propriétaire du bot ou aux administrateurs (slash).",
        "cmd_help_title": "🛈 Aide — {cmd}",
        "subcommands_label": "Sous-commandes:",
        "label_owner_page": "Owner",
    }
    en["help"]["ui"] = {
        "footer_page": "Page {cur}/{total} — /{cmd} <command> for details.",
        "placeholder_jump": "Go to…",
        "btn_close": "Close",
        "btn_all_dm": "View all (DM)",
        "dm_sent_ok": "📬 Full help sent to your DMs.",
        "dm_forbidden": "❌ Could not send a DM (check your privacy settings).",
        "dm_error": "❌ DM not sent (unknown error).",
        "unknown_command": "Unknown command.",
        "slash_not_found": "❌ Slash command not found. Check spelling or use `/help` for the list.",
        "embed_params": "Parameters",
        "embed_example": "Example",
        "page_detail_hint": "Use `/{help_cmd} <command>` for a detailed card.",
        "not_slash_suffix": " *(not available as slash)*",
        "no_slash": "No slash commands detected.",
        "brief_help_title": "Help",
        "essential_title": "📖 Help — Essentials",
        "essential_desc": (
            "Main commands — **slash** `/…` only.\n"
            "• `/help <command>`: details · **View all** button: full list in DMs (from a server).\n"
            "• **Administrators**: `/help_admin` (server config, /airings list, raid)."
        ),
        "essential_footer": "/help <command> · slash commands",
        "mp_hint_title": "ℹ️ DMs",
        "mp_hint_help": "For the **View all** button, use `/help` in a server.",
        "mp_hint_admin": "For the **View all** button, use `/help_admin` in a server.",
        "admin_title": "🛠️ Help — Administrators",
        "admin_desc": (
            "Commands for **server administrators** only — **slash** `/…` only.\n"
            "• `/help_admin <command>`: details · **View all** button: full list in DMs."
        ),
        "admin_footer": "/help_admin <command> · slash commands",
        "owner_title": "🔐 Help — Owner/Admin",
        "owner_empty": "No restricted commands detected.",
        "owner_desc": "Commands reserved for the bot owner or administrators (slash).",
        "cmd_help_title": "🛈 Help — {cmd}",
        "subcommands_label": "Subcommands:",
        "label_owner_page": "Owner",
    }

    for path, data in ((fr_path, fr), (en_path, en)):
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("OK", fr_path, en_path)


if __name__ == "__main__":
    main()
