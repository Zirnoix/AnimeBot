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
        "minigame_busy": (
            "Tu as déjà une partie ou une question en attente — réponds-y (ou attends la fin) "
            "avant d’en lancer une autre."
        ),
        "guessgenre_cooldown": (
            "⏳ Attends encore **{remaining}s** avant de relancer le **Guess genre** "
            "(`/guessgenre` ou `/minijeux`)."
        ),
    }
    common_en = {
        "slash_only": "This command is **slash-only** — use `/{name}` in the command bar.",
        "weekdays": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
        "abuse_rate_limit": "⏳ Too many commands — try again in **{seconds}s**.",
        "minigame_busy": (
            "You already have a game or question pending — answer it (or wait for it to finish) "
            "before starting another."
        ),
        "guessgenre_cooldown": (
            "⏳ Wait **{remaining}s** more before launching **Guess genre** again (`/guessgenre` or `/minijeux`)."
        ),
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
            "🎁 **XP :** **{xp}** de base + bonus **série** (jours consécutifs avec au moins un vote) "
            "+ **fidélité** (palier selon le **nombre total** de votes enregistrés) "
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
            "{base} base + {sb} **série** (jours d’affilée) + {lb} **fidélité** (total de votes) = **{sub}** XP avant multi.{wk}\n"
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
            "🎁 **XP:** **{xp}** base + **streak** (consecutive days with at least one vote) "
            "+ **loyalty** (milestones from your **lifetime** vote count) "
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
            "{base} base + {sb} **streak** (consecutive days) + {lb} **loyalty** (lifetime votes) = **{sub}** XP before multi.{wk}\n"
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

    fr["link"] = {
        "not_found": "❌ Aucun compte AniList trouvé avec ce pseudo.",
        "already_same": "ℹ️ Ton compte est déjà lié à **{existing}**.",
        "already_other": (
            "Tu es déjà lié à **{existing}**.\n"
            "Utilise **`/unlink`**, puis refais **`/linkanilist`** pour changer de pseudo AniList."
        ),
        "taken_other_discord": (
            "❌ Ce pseudo AniList est **déjà lié** à un autre compte Discord.\n"
            "Si c’est bien ton profil, contacte le support du bot : le lien doit être libéré."
        ),
        "step1_body": (
            "**Étape 1/2** — pseudo **{resolved}** reconnu sur AniList.\n\n"
            "1. Ouvre ton profil AniList → **Paramètres** → colle exactement ce code dans "
            "**« About » / « À propos »** (bio publique) :\n```{token}```\n"
            "2. Enregistre, puis lance **`/verifyanilist`** ici.\n\n"
            "_Le code expire après **30 minutes**. Tu peux le retirer de ta bio une fois lié._"
        ),
        "verify_none": "❌ Aucune vérification en cours. Commence par **`/linkanilist <pseudo>`**.",
        "verify_expired": "❌ Code expiré (30 min). Relance **`/linkanilist`** avec ton pseudo.",
        "verify_not_in_bio": (
            "❌ Je ne vois pas encore le code **`{token}`** sur le profil **{username}**.\n"
            "Vérifie la section **About** (publique), enregistre, attends quelques secondes, réessaie."
        ),
        "error_taken": "❌ Ce pseudo AniList vient d’être lié ailleurs. Réessaie ou contacte un admin.",
        "error_save": "❌ Impossible d’enregistrer le lien pour le moment.",
        "step2_ok": "✅ **Étape 2/2** — compte **{username}** confirmé et lié à ton Discord !",
        "unlink_ok": "🔗 Ton lien AniList a bien été supprimé.",
        "unlink_none": "❌ Aucun compte AniList n'était lié à ce profil.",
        "duel_usage": "❌ Utilise : **`/duelstats @ami`** pour lancer un duel de stats.",
        "duel_both_link": "❗ Les deux joueurs doivent avoir lié leur compte avec `/linkanilist`.",
        "duel_fetch_error": "❌ Impossible de récupérer les statistiques AniList.",
        "duel_l_completed": "Complétés",
        "duel_l_watching": "En cours",
        "duel_l_episodes": "Épisodes vus",
        "duel_l_days": "Jours visionnés",
        "duel_l_mean_bonus": "Note moy. (bonus)",
        "duel_title": "⚔️ Duel AniList",
        "duel_desc": (
            "**{n_a}** · `{user1}`  ×  **{n_b}** · `{user2}`\n"
            "Engagement réel (pas genre / pas moyenne biaisée)."
        ),
        "duel_field_board": "🎮 Tableau",
        "duel_field_verdict": "🏆 Verdict",
        "duel_footer": "AniList · /linkanilist · note bonus si 0 < moy. < 100 pour les deux",
        "duel_author": "Arène stats",
        "duel_win": "**{winner}** gagne **{hi}**–**{lo}**",
        "duel_draw": "**Match nul** · **{p}**–**{p2}**",
    }
    en["link"] = {
        "not_found": "❌ No AniList account found with that username.",
        "already_same": "ℹ️ Your account is already linked to **{existing}**.",
        "already_other": (
            "You’re already linked to **{existing}**.\n"
            "Use **`/unlink`**, then **`/linkanilist`** again to change your AniList username."
        ),
        "taken_other_discord": (
            "❌ That AniList username is **already linked** to another Discord account.\n"
            "If it’s really yours, contact bot support — the link must be cleared first."
        ),
        "step1_body": (
            "**Step 1/2** — username **{resolved}** found on AniList.\n\n"
            "1. Open your AniList profile → **Settings** → paste this code in "
            "**About** (public bio) :\n```{token}```\n"
            "2. Save, then run **`/verifyanilist`** here.\n\n"
            "_The code expires after **30 minutes**. You can remove it from your bio once linked._"
        ),
        "verify_none": "❌ No verification in progress. Start with **`/linkanilist <username>`**.",
        "verify_expired": "❌ Code expired (30 min). Run **`/linkanilist`** again with your username.",
        "verify_not_in_bio": (
            "❌ I still don’t see the code **`{token}`** on **{username}**’s profile.\n"
            "Check the public **About** section, save, wait a few seconds, try again."
        ),
        "error_taken": "❌ That AniList username was just linked elsewhere. Retry or contact an admin.",
        "error_save": "❌ Could not save the link right now.",
        "step2_ok": "✅ **Step 2/2** — account **{username}** confirmed and linked to your Discord!",
        "unlink_ok": "🔗 Your AniList link was removed.",
        "unlink_none": "❌ No AniList account was linked to this profile.",
        "duel_usage": "❌ Use: **`/duelstats @friend`** to start a stats duel.",
        "duel_both_link": "❗ Both players must link their account with `/linkanilist`.",
        "duel_fetch_error": "❌ Could not fetch AniList statistics.",
        "duel_l_completed": "Completed",
        "duel_l_watching": "Watching",
        "duel_l_episodes": "Episodes watched",
        "duel_l_days": "Days watched",
        "duel_l_mean_bonus": "Mean score (bonus)",
        "duel_title": "⚔️ AniList duel",
        "duel_desc": (
            "**{n_a}** · `{user1}`  ×  **{n_b}** · `{user2}`\n"
            "Real engagement (not genre / not a skewed average)."
        ),
        "duel_field_board": "🎮 Scoreboard",
        "duel_field_verdict": "🏆 Result",
        "duel_footer": "AniList · /linkanilist · bonus mean if 0 < avg < 100 for both",
        "duel_author": "Stats arena",
        "duel_win": "**{winner}** wins **{hi}**–**{lo}**",
        "duel_draw": "**Draw** · **{p}**–**{p2}**",
    }

    fr["stats"] = {
        "embed_partial": "ℹ️ Profil **partiel** : chiffres **approximatifs** (source liste).",
        "embed_sheet": "🔗 Fiche · [**{display}**]({site_url})",
        "embed_user": "👤 **{display}**",
        "field_activity": "🎬 Activité",
        "activity_lines": (
            "• **{prefix}{count}** titres (comptés)\n"
            "• **{prefix}{watch_time}** de visionnage\n"
            "• **{prefix}{note}**/100 note moyenne"
        ),
        "field_list": "📚 Liste",
        "list_lines": (
            "• **{completed}** terminés\n"
            "• **{current}** en cours\n"
            "• **{total}** entrées au total"
        ),
        "field_fav_genre": "❤️ Genre favori (profil)",
        "field_completion": "📈 Complétion (terminés / entrées)",
        "completion_bar": "{bar} **{pct}%**",
        "field_top_genres": "🎭 Top genres (sur ton profil)",
        "genre_row": "▸ **{gn}** · {c} · _{p}%_",
        "footer_requested": "Demandé par {name}",
        "footer_linked_vote": "Compte lié · 💡 Soutiens AnimeBot avec **`/vote`** (Top.gg)",
        "footer_link_hint": "/linkanilist pour /mystats sans pseudo, récaps MP, /monnext…",
        "user_not_found": "❌ Utilisateur AniList **{pseudo}** introuvable.",
        "not_linked": "🔗 Tu n’as pas lié ton compte AniList. Utilise **/linkanilist <pseudo>**.",
        "time_dash": "—",
        "time_days": "{n} j",
        "time_one_day": "1 j {h} h",
        "time_hours": "{h} h",
    }
    en["stats"] = {
        "embed_partial": "ℹ️ **Partial** profile: **approximate** numbers (from list).",
        "embed_sheet": "🔗 Profile · [**{display}**]({site_url})",
        "embed_user": "👤 **{display}**",
        "field_activity": "🎬 Activity",
        "activity_lines": (
            "• **{prefix}{count}** titles (counted)\n"
            "• **{prefix}{watch_time}** watch time\n"
            "• **{prefix}{note}**/100 mean score"
        ),
        "field_list": "📚 List",
        "list_lines": (
            "• **{completed}** completed\n"
            "• **{current}** watching\n"
            "• **{total}** total entries"
        ),
        "field_fav_genre": "❤️ Favorite genre (profile)",
        "field_completion": "📈 Completion (completed / entries)",
        "completion_bar": "{bar} **{pct}%**",
        "field_top_genres": "🎭 Top genres (on your profile)",
        "genre_row": "▸ **{gn}** · {c} · _{p}%_",
        "footer_requested": "Requested by {name}",
        "footer_linked_vote": "Linked account · 💡 Support AnimeBot with **`/vote`** (Top.gg)",
        "footer_link_hint": "/linkanilist for /mystats without username, DM recaps, /monnext…",
        "user_not_found": "❌ AniList user **{pseudo}** not found.",
        "not_linked": "🔗 You haven’t linked your AniList account. Use **/linkanilist <username>**.",
        "time_dash": "—",
        "time_days": "{n}d",
        "time_one_day": "1d {h}h",
        "time_hours": "{h}h",
    }

    fr["recap"] = {
        "embed_title": "📬 Récap quotidien — « Sorties du jour »",
        "embed_desc": (
            "Configure le **même** récap MP que l’embed **« Sorties du … »** (liste à puces, "
            "pas l’ancien message détaillé supprimé).\n\n"
            "Un **message privé** chaque jour à l’heure choisie, selon **ton** compte AniList.\n\n"
            "• Compte lié : {link_txt}\n"
            "• État : **{state}** · heure : **`{hh}`** (fuseau du bot)\n\n"
            "Boutons ci-dessous : activer, désactiver, ou **saisir l’heure** (HH:MM). "
            "Tu peux aussi régler l’heure avec **`/setalert`**. Utilise **Fermer** quand tu as terminé."
        ),
        "embed_footer": "/setalert HH:MM · /linkanilist",
        "link_none": "_(aucun — utilise `/linkanilist`)_",
        "state_on": "activé",
        "state_off": "désactivé",
        "modal_title": "Heure du récap MP",
        "modal_label_time": "Heure (HH:MM)",
        "modal_ph_time": "ex. 08:00, 21:30",
        "err_not_yours": "❌ Ce panneau n’est pas pour toi.",
        "err_not_yours_form": "❌ Ce formulaire n’est pas pour toi.",
        "err_invalid_time": (
            "❌ Heure invalide. Utilise **HH:MM** (ex. `08:00`, `21:30`). Réessaie avec **`/recap`**."
        ),
        "btn_enable": "Activer (heure actuelle)",
        "btn_disable": "Désactiver",
        "btn_time": "Choisir l’heure (HH:MM)",
        "btn_close": "Fermer",
        "disabled_msg": "⏹️ Récap **désactivé**. Tu peux rouvrir **`/recap`** pour le rallumer.",
        "closed_msg": "✅ Panneau fermé. Rouvre **`/recap`** pour modifier.",
        "err_generic": "❌ Erreur `/recap` : `{detail}`",
        "setalert_bad": "❌ Format invalide. Exemple : `08:00`",
        "setalert_ok": "⏰ Heure réglée sur **{heure}** (fuseau du bot) — utilisée par le récap **`/recap`**.",
    }
    en["recap"] = {
        "embed_title": "📬 Daily recap — “Today’s releases”",
        "embed_desc": (
            "Configure the **same** DM recap as the **“Releases on …”** embed (bullet list, "
            "not the old detailed message).\n\n"
            "**One private message** each day at the time you pick, based on **your** AniList account.\n\n"
            "• Linked account: {link_txt}\n"
            "• State: **{state}** · time: **`{hh}`** (bot timezone)\n\n"
            "Buttons below: enable, disable, or **enter the time** (HH:MM). "
            "You can also set the time with **`/setalert`**. Use **Close** when done."
        ),
        "embed_footer": "/setalert HH:MM · /linkanilist",
        "link_none": "_(none — use `/linkanilist`)_",
        "state_on": "on",
        "state_off": "off",
        "modal_title": "Recap DM time",
        "modal_label_time": "Time (HH:MM)",
        "modal_ph_time": "e.g. 08:00, 21:30",
        "err_not_yours": "❌ This panel isn’t for you.",
        "err_not_yours_form": "❌ This form isn’t for you.",
        "err_invalid_time": (
            "❌ Invalid time. Use **HH:MM** (e.g. `08:00`, `21:30`). Try again with **`/recap`**."
        ),
        "btn_enable": "Enable (current time)",
        "btn_disable": "Disable",
        "btn_time": "Set time (HH:MM)",
        "btn_close": "Close",
        "disabled_msg": "⏹️ Recap **disabled**. Run **`/recap`** again to turn it back on.",
        "closed_msg": "✅ Panel closed. Open **`/recap`** again to change settings.",
        "err_generic": "❌ `/recap` error: `{detail}`",
        "setalert_bad": "❌ Invalid format. Example: `08:00`",
        "setalert_ok": "⏰ Time set to **{heure}** (bot timezone) — used by **`/recap`**.",
    }

    fr["tracker"] = {
        "clear_not_you": "Ce menu n’est pas pour toi.",
        "clear_yes": "Oui, tout supprimer",
        "clear_no": "Non",
        "clear_done": "✅ **Liste vidée.**",
        "clear_dm": "✅ Ta liste de suivi a été **complètement vidée**.",
        "clear_cancel": "❌ **Annulé.**",
        "dm_forbidden": (
            "⚠️ Impossible de t'envoyer un MP. Active-les pour ce serveur (Confidentialité & sécurité)."
        ),
        "dm_error": "⚠️ Impossible d'envoyer le MP (erreur inconnue).",
        "list_empty": "📭 Tu ne suis aucun anime actuellement.\nUtilise **{usage}** pour commencer.",
        "list_sent": "📬 Message envoyé en **message privé**.",
        "list_title": "📌 Animes suivis par {name}",
        "list_footer_page": "Page {cur}/{total}",
        "list_dm_confirm": "📬 Liste envoyée en **message privé**.",
        "add_no_results": (
            "❌ Aucun résultat AniList pour **{anime}**.\n"
            "Essaie un **autre mot-clé** (début du titre romaji, mot distinctif…)."
        ),
        "pick_title": "📌 Quel anime suivre ?",
        "pick_desc": (
            "Choisis un titre : réponds avec le **numéro** **dans ce salon** (30 s). "
            "Tu recevras un **MP** quand un **nouvel épisode** sort.\n"
            "_Ton message avec le numéro sera supprimé pour limiter le bruit._"
        ),
        "field_ep_upcoming": "Épisode {ep} à venir",
        "field_episodes": "{n} épisodes",
        "timeout_pick": "⏰ Temps écoulé, aucun anime ajouté.",
        "already_following": "⚠️ Tu suis déjà **{title}**.",
        "added_title": "📺 Ajouté à ton suivi",
        "added_desc": (
            "**{title}** — tu recevras un **message privé** avec une **carte** quand un **épisode sort** "
            "(fenêtre ~18 h après la diffusion ; pas d’alerte « X minutes avant »).\n"
            "Gère ta liste avec **`/track list`** / **`/track remove`**."
        ),
        "field_details": "Détails",
        "detail_next": "• Prochain : Épisode {ep}",
        "detail_eps": "• Épisodes : {n}",
        "detail_status": "• Statut : {status}",
        "details_sent": "📬 Détails envoyés en **message privé**.",
        "remove_empty": "❌ Ta liste est vide.",
        "remove_none": "❌ Aucun anime trouvé pour **{anime}** dans ta liste.",
        "remove_multi_title": "🔍 Plusieurs correspondances trouvées",
        "remove_multi_desc": "Réponds avec le **numéro** à retirer (30s). Ton message sera **supprimé** après.",
        "timeout_remove": "⏰ Temps écoulé, aucun anime retiré.",
        "removed_ok": "✅ **{title}** a été retiré de ta liste.",
        "remove_confirm": "📬 Confirmation envoyée en **message privé**.",
        "clear_empty": "📭 Ta liste est déjà vide.",
        "clear_prompt": "⚠️ **Supprimer toute ta liste de suivi ?**",
        "alert_release": "📺 **Sortie** — **{title}** · Épisode **{ep}**",
    }
    en["tracker"] = {
        "clear_not_you": "This menu isn’t for you.",
        "clear_yes": "Yes, delete everything",
        "clear_no": "No",
        "clear_done": "✅ **List cleared.**",
        "clear_dm": "✅ Your tracking list has been **fully cleared**.",
        "clear_cancel": "❌ **Cancelled.**",
        "dm_forbidden": (
            "⚠️ I can’t DM you. Enable DMs for this server (Privacy & Safety)."
        ),
        "dm_error": "⚠️ Could not send the DM (unknown error).",
        "list_empty": "📭 You’re not following any anime yet.\nUse **{usage}** to start.",
        "list_sent": "📬 Message sent in **DMs**.",
        "list_title": "📌 Anime you follow — {name}",
        "list_footer_page": "Page {cur}/{total}",
        "list_dm_confirm": "📬 List sent in **DMs**.",
        "add_no_results": (
            "❌ No AniList results for **{anime}**.\n"
            "Try another **keyword** (start of romaji title, distinctive word…)."
        ),
        "pick_title": "📌 Which anime to follow?",
        "pick_desc": (
            "Pick one: reply with the **number** **in this channel** (30 s). "
            "You’ll get a **DM** when a **new episode** airs.\n"
            "_Your number message will be deleted to reduce noise._"
        ),
        "field_ep_upcoming": "Episode {ep} upcoming",
        "field_episodes": "{n} episodes",
        "timeout_pick": "⏰ Time’s up — no anime added.",
        "already_following": "⚠️ You’re already following **{title}**.",
        "added_title": "📺 Added to your list",
        "added_desc": (
            "**{title}** — you’ll get a **private message** with a **card** when an **episode airs** "
            "(~18 h window after air time; no “X minutes before” alert).\n"
            "Manage your list with **`/track list`** / **`/track remove`**."
        ),
        "field_details": "Details",
        "detail_next": "• Next: Episode {ep}",
        "detail_eps": "• Episodes: {n}",
        "detail_status": "• Status: {status}",
        "details_sent": "📬 Details sent in **DMs**.",
        "remove_empty": "❌ Your list is empty.",
        "remove_none": "❌ No anime found for **{anime}** in your list.",
        "remove_multi_title": "🔍 Multiple matches",
        "remove_multi_desc": "Reply with the **number** to remove (30s). Your message will be **deleted** after.",
        "timeout_remove": "⏰ Time’s up — nothing removed.",
        "removed_ok": "✅ **{title}** was removed from your list.",
        "remove_confirm": "📬 Confirmation sent in **DMs**.",
        "clear_empty": "📭 Your list is already empty.",
        "clear_prompt": "⚠️ **Delete your entire tracking list?**",
        "alert_release": "📺 **Out now** — **{title}** · Episode **{ep}**",
    }

    _rb_fr = json.loads((ROOT / "scripts" / "_reportbug_fr.json").read_text(encoding="utf-8"))
    _rb_en = json.loads((ROOT / "scripts" / "_reportbug_en.json").read_text(encoding="utf-8"))
    fr["reportbug"] = _rb_fr
    en["reportbug"] = _rb_en

    _qz_fr = json.loads((ROOT / "scripts" / "_quiz_fr.json").read_text(encoding="utf-8"))
    fr["quiz"] = _qz_fr
    _qz_en = json.loads((ROOT / "scripts" / "_quiz_en.json").read_text(encoding="utf-8"))
    en["quiz"] = _qz_en

    _mg_fr = json.loads((ROOT / "scripts" / "_minigames_fr.json").read_text(encoding="utf-8"))
    fr["minigames"] = _mg_fr
    _mg_en = json.loads((ROOT / "scripts" / "_minigames_en.json").read_text(encoding="utf-8"))
    en["minigames"] = _mg_en

    _op_fr = json.loads((ROOT / "scripts" / "_opening_fr.json").read_text(encoding="utf-8"))
    fr["opening"] = _op_fr
    _op_en = json.loads((ROOT / "scripts" / "_opening_en.json").read_text(encoding="utf-8"))
    en["opening"] = _op_en

    _eg_fr = json.loads((ROOT / "scripts" / "_engagement_fr.json").read_text(encoding="utf-8"))
    fr["engagement"] = _eg_fr
    _eg_en = json.loads((ROOT / "scripts" / "_engagement_en.json").read_text(encoding="utf-8"))
    en["engagement"] = _eg_en

    _pf_fr = json.loads((ROOT / "scripts" / "_profile_fr.json").read_text(encoding="utf-8"))
    fr["profile"] = _pf_fr
    _pf_en = json.loads((ROOT / "scripts" / "_profile_en.json").read_text(encoding="utf-8"))
    en["profile"] = _pf_en

    _cg_fr = json.loads((ROOT / "scripts" / "_community_games_fr.json").read_text(encoding="utf-8"))
    fr["community_games"] = _cg_fr
    _cg_en = json.loads((ROOT / "scripts" / "_community_games_en.json").read_text(encoding="utf-8"))
    en["community_games"] = _cg_en

    _es_fr = json.loads((ROOT / "scripts" / "_emoji_sync_fr.json").read_text(encoding="utf-8"))
    fr["emoji_sync"] = _es_fr
    _es_en = json.loads((ROOT / "scripts" / "_emoji_sync_en.json").read_text(encoding="utf-8"))
    en["emoji_sync"] = _es_en

    fr["airings_admin"] = {
        "guild_only_short": "❌ Utilisable seulement sur un serveur.",
        "guild_only_cmd": "❌ Commande utilisable seulement sur un serveur.",
        "select_none": "Aucun animé sélectionné.",
        "select_none_rm": "Aucune sélection.",
        "no_valid_id": "Aucun ID/indice valide reconnu.",
        "modal_title": "Sélection manuelle",
        "modal_label": "IDs AniList ou index de page (ex: 1,2,12345)",
        "modal_ph": "Exemples : 1,3,7  ou  1535, 21087",
        "modal_empty": "Entrée vide.",
        "manual_refresh_fail": "{verb} : **{n}** élément(s). Impossible de rafraîchir la vue (`{err}`). Rouvre `/airings all`.",
        "manual_ok": "{verb} : **{n}** élément(s).",
        "verb_add": "✅ Ajouté",
        "verb_rm": "🗑️ Retiré",
        "ph_add": "➕ Ajouter à la liste du serveur…",
        "ph_remove": "🗑️ Retirer de la liste du serveur…",
        "opt_empty_page": "(rien sur cette page)",
        "opt_none_tracked": "(aucun suivi sur cette page)",
        "opt_ep_id": "Ep. {ep} · id {mid}",
        "add_many_ok": "✅ **{n}** animé(s) ajouté(s) à la **liste du serveur**.",
        "add_refresh_fail": "✅ **{n}** ajout(s). Impossible de rafraîchir la vue (`{err}`). Rouvre `/airings all`.",
        "remove_many_ok": "🗑️ **{n}** animé(s) retiré(s) de la **liste du serveur**.",
        "remove_refresh_fail": "🗑️ **{n}** retrait(s). Impossible de rafraîchir la vue (`{err}`). Rouvre `/airings all`.",
        "embed_title": "🎛️ Sorties à venir ({days} jours)",
        "embed_desc": (
            "Liste **AniList** des prochains épisodes (non adulte). "
            "**✅** = déjà dans la **liste du serveur** (utilisée par `/next` et `/planning` en mode serveur).\n"
            "Menus pour ajouter ou retirer ; boutons **toute la page** ou **IDs manuels**."
        ),
        "embed_footer": "Liens → fiche AniList · jusqu’à 25 titres/page (plusieurs blocs si nécessaire)",
        "line_entry": "**{i}.** {mark} [{title}]({url}) — Ep **{ep}**",
        "page_empty": "(aucun élément sur cette page)",
        "field_page": "Page {cur}/{total} · {n} animé(s)",
        "field_part": "Page {cur}/{total} · partie {ci}/{parts}",
        "btn_page_add": "Toute la page → liste",
        "btn_page_rm": "Toute la page → retirer",
        "btn_manual_add": "IDs manuels (ajout)",
        "btn_manual_rm": "IDs manuels (retrait)",
        "btn_close": "Fermer",
        "page_add_ok": "✅ **{n}** nouvelle(s) entrée(s) ajoutée(s) (page entière).",
        "page_add_fail": "✅ **{n}** ajout(s), mais mise à jour de la vue impossible (`{err}`). Rouvre `/airings all`.",
        "page_rm_ok": "🗑️ **{n}** animé(s) retiré(s) (page entière).",
        "page_rm_fail": "🗑️ **{n}** retrait(s), mais mise à jour de la vue impossible (`{err}`). Rouvre `/airings all`.",
        "admin_required": "❌ Admin requis.",
        "need_guild": "❌ Cette commande doit être utilisée dans un serveur.",
        "no_episodes_window": "📭 Aucun épisode global sur {days} jours.",
        "list_empty": "Aucun animé suivi. Utilise `/airings all` pour en ajouter.",
        "list_title": "✅ Liste du serveur (/next, /planning « serveur »)",
        "list_desc": (
            "Animés ajoutés par les admins via `/airings` (menus, page entière ou ID). "
            "Ce n’est **pas** toutes les sorties AniList — seulement ce que le serveur suit."
        ),
        "list_footer_more": "... et {n} autres",
        "list_line": "{i}. **{name}** — ID `{mid}`  {url}",
        "add_need_url": "Donne une **URL AniList** ou un **ID**.",
        "add_not_found": "Animé introuvable ou échec d’ajout.",
        "add_one_ok": "✅ Ajouté **{name}** (`{mid}`)",
        "remove_one_ok": "🗑️ Retiré id `{mid}`.",
        "remove_not_in": "Cet id n’était pas dans la liste du serveur.",
        "clear_ok": "🧹 Whitelist vidée ({n} entrées supprimées).",
    }
    en["airings_admin"] = {
        "guild_only_short": "❌ Server only.",
        "guild_only_cmd": "❌ This command works only in a server.",
        "select_none": "No anime selected.",
        "select_none_rm": "Nothing selected.",
        "no_valid_id": "No valid ID or index.",
        "modal_title": "Manual selection",
        "modal_label": "AniList IDs or page indices (e.g. 1,2,12345)",
        "modal_ph": "Examples: 1,3,7  or  1535, 21087",
        "modal_empty": "Empty input.",
        "manual_refresh_fail": "{verb}: **{n}** item(s). Could not refresh the view (`{err}`). Reopen `/airings all`.",
        "manual_ok": "{verb}: **{n}** item(s).",
        "verb_add": "✅ Added",
        "verb_rm": "🗑️ Removed",
        "ph_add": "➕ Add to server list…",
        "ph_remove": "🗑️ Remove from server list…",
        "opt_empty_page": "(nothing on this page)",
        "opt_none_tracked": "(none tracked on this page)",
        "opt_ep_id": "Ep. {ep} · id {mid}",
        "add_many_ok": "✅ **{n}** anime added to the **server list**.",
        "add_refresh_fail": "✅ **{n}** added. Could not refresh the view (`{err}`). Reopen `/airings all`.",
        "remove_many_ok": "🗑️ **{n}** anime removed from the **server list**.",
        "remove_refresh_fail": "🗑️ **{n}** removed. Could not refresh the view (`{err}`). Reopen `/airings all`.",
        "embed_title": "🎛️ Upcoming releases ({days} days)",
        "embed_desc": (
            "**AniList** list of upcoming episodes (non-adult). "
            "**✅** = already on the **server list** (used by `/next` and `/planning` in server mode).\n"
            "Menus to add/remove; **whole page** or **manual IDs**."
        ),
        "embed_footer": "Links → AniList page · up to 25 titles/page (multiple blocks if needed)",
        "line_entry": "**{i}.** {mark} [{title}]({url}) — Ep **{ep}**",
        "page_empty": "(nothing on this page)",
        "field_page": "Page {cur}/{total} · {n} anime",
        "field_part": "Page {cur}/{total} · part {ci}/{parts}",
        "btn_page_add": "Whole page → add",
        "btn_page_rm": "Whole page → remove",
        "btn_manual_add": "Manual IDs (add)",
        "btn_manual_rm": "Manual IDs (remove)",
        "btn_close": "Close",
        "page_add_ok": "✅ **{n}** new entries added (full page).",
        "page_add_fail": "✅ **{n}** added, but the view couldn’t update (`{err}`). Reopen `/airings all`.",
        "page_rm_ok": "🗑️ **{n}** anime removed (full page).",
        "page_rm_fail": "🗑️ **{n}** removed, but the view couldn’t update (`{err}`). Reopen `/airings all`.",
        "admin_required": "❌ Administrator required.",
        "need_guild": "❌ This command must be used in a server.",
        "no_episodes_window": "📭 No global episodes in the next {days} days.",
        "list_empty": "No anime tracked. Use `/airings all` to add some.",
        "list_title": "✅ Server list (/next, /planning “server”)",
        "list_desc": (
            "Anime added by admins via `/airings` (menus, full page or ID). "
            "This is **not** all AniList releases — only what the server follows."
        ),
        "list_footer_more": "... and {n} more",
        "list_line": "{i}. **{name}** — ID `{mid}`  {url}",
        "add_need_url": "Provide an **AniList URL** or **numeric ID**.",
        "add_not_found": "Anime not found or add failed.",
        "add_one_ok": "✅ Added **{name}** (`{mid}`)",
        "remove_one_ok": "🗑️ Removed id `{mid}`.",
        "remove_not_in": "That id was not on the server list.",
        "clear_ok": "🧹 Server list cleared ({n} entries removed).",
    }

    fr["episodes"] = {
        "ack_dm": "📬 Je t’ai envoyé ça en MP.",
        "dm_closed": "❌ Impossible d’ouvrir un MP avec toi. Active tes messages privés puis réessaie.",
        "err_planning": "⚠️ Impossible de récupérer le planning global.\n`{detail}`",
        "err_next": "⚠️ Impossible de récupérer le prochain épisode.\n`{detail}`",
        "no_ep_week": "📭 Aucun épisode prévu ({scope}) cette semaine.",
        "no_next_week": "📭 Aucun épisode à venir ({scope}) trouvé cette semaine.",
        "scope_server": "liste du serveur",
        "scope_global": "global",
        "planning_title": "📅 Planning {day} ({scope})",
        "field_day": "{day} · {n} sortie(s)",
        "field_day_part": "{day} · partie {ci}/{parts}",
        "date_unknown": "date inconnue",
        "not_linked": "🔗 Tu n’as pas lié ton compte AniList. Utilise **/linkanilist <pseudo>**.",
        "err_monnext_fetch": "⚠️ Impossible de récupérer tes prochains épisodes.\n`{detail}`",
        "err_monplanning_fetch": "⚠️ Impossible de récupérer ton planning.\n`{detail}`",
        "monnext_empty": (
            "📭 Aucun **prochain épisode annoncé** pour ta liste **En cours / Répété** sur AniList.\n"
            "• Seules les séries avec une date d’épisode côté AniList (`nextAiringEpisode`) apparaissent ici.\n"
            "• Ta liste doit être **publique** pour que le bot puisse la lire.\n"
            "• Si l’API venait de planter, réessaie avec **`rafraichir: Oui`** sur cette commande."
        ),
        "monplanning_empty": (
            "📭 Pas de **prochain épisode annoncé** sur AniList pour tes entrées **En cours / Répété** "
            "(liste **privée**, titres sans date d’épisode publiée sur AniList, ou cache obsolète).\n"
            "Réessaie avec **`rafraichir: Oui`** si besoin."
        ),
        "monplanning_title": "📅 Ton planning {day}",
        "field_mon_part": "{day} · {n} sortie(s)",
        "field_mon_part2": "{day} · partie {ci}/{parts}",
    }
    en["episodes"] = {
        "ack_dm": "📬 Sent to your DMs.",
        "dm_closed": "❌ I can’t open a DM with you. Enable DMs and try again.",
        "err_planning": "⚠️ Could not fetch the global schedule.\n`{detail}`",
        "err_next": "⚠️ Could not fetch the next episode.\n`{detail}`",
        "no_ep_week": "📭 No episodes scheduled ({scope}) this week.",
        "no_next_week": "📭 No upcoming episodes ({scope}) found this week.",
        "scope_server": "server list",
        "scope_global": "global",
        "planning_title": "📅 Schedule {day} ({scope})",
        "field_day": "{day} · {n} release(s)",
        "field_day_part": "{day} · part {ci}/{parts}",
        "date_unknown": "unknown date",
        "not_linked": "🔗 You haven’t linked your AniList account. Use **/linkanilist <username>**.",
        "err_monnext_fetch": "⚠️ Could not fetch your upcoming episodes.\n`{detail}`",
        "err_monplanning_fetch": "⚠️ Could not fetch your schedule.\n`{detail}`",
        "monnext_empty": (
            "📭 No **upcoming episode** announced for your **Watching / Repeating** list on AniList.\n"
            "• Only shows with an episode date on AniList (`nextAiringEpisode`) appear here.\n"
            "• Your list must be **public** for the bot to read it.\n"
            "• If the API was down, retry with **`refresh: Yes`** on this command."
        ),
        "monplanning_empty": (
            "📭 No **upcoming episode** on AniList for your **Watching / Repeating** entries "
            "(**private** list, titles without a published episode date, or stale cache).\n"
            "Try again with **`refresh: Yes`** if needed."
        ),
        "monplanning_title": "📅 Your schedule — {day}",
        "field_mon_part": "{day} · {n} release(s)",
        "field_mon_part2": "{day} · part {ci}/{parts}",
    }

    for path, data in ((fr_path, fr), (en_path, en)):
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("OK", fr_path, en_path)


if __name__ == "__main__":
    main()
