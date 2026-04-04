"""Génère scripts/_community_games_fr.json et _community_games_en.json (usage ponctuel)."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent

FR = {
    "guild_only": "❌ Serveur uniquement.",
    "err_invalid_server": "❌ Serveur invalide.",
    "err_hhmm_format": "❌ Format attendu : **`HH:MM`** (ex. `20:30`).",
    "err_bad_time": "❌ Heure invalide.",
    "err_wrong_guild": "❌ Mauvais serveur.",
    "err_admin": "❌ Administrateur requis.",
    "err_text_channel": "❌ Choisis un salon **texte** (ou annonces).",
    "err_channel_this_guild": "❌ Le salon doit être sur **ce** serveur.",
    "raid_save_ok": "✅ La configuration du **raid boss** a bien été enregistrée.",
    "ph_channel": "Salon des annonces et du combat",
    "ph_weekday": "Jour de la semaine (fuseau du bot)",
    "ph_hour": "Heure (0–23)",
    "ph_minute": "Minutes (pas de 5 — ou bouton HH:MM)",
    "modal_title": "Horaire du raid (HH:MM)",
    "modal_label": "Heure (fuseau du bot)",
    "modal_ph": "Ex. 20:30",
    "btn_auto_on": "🤖 Auto : ON",
    "btn_auto_off": "⛔ Auto : OFF",
    "btn_hhmm": "🕐 Heure HH:MM",
    "btn_save": "💾 Enregistrer",
    "btn_close": "Fermer",
    "status_title": "⚔️ Raid boss — statut",
    "status_desc": "Résumé pour **ce serveur** (fuseau du bot).",
    "status_ch_none": "— *non configuré* — ouvre **`/raidconfig`** et choisis un **salon**.",
    "status_field_ch": "📍 Salon",
    "status_field_slot": "📅 Créneau hebdo",
    "status_field_auto": "🤖 Lancement auto",
    "status_field_next": "⏱️ Créneau pris en compte par le bot",
    "status_field_alert": "🔔 Alerte @here (~1 h avant)",
    "status_field_alert_need_ch": "— *Ouvre **`/raidconfig`** et choisis un **salon** — sinon aucune annonce.*",
    "status_field_raidstart": "🎯 /raidstart (manuel)",
    "status_raidstart_used": "🔒 Déjà utilisé cette semaine (`{wk}`).",
    "status_raidstart_ok": "✅ Disponible (`{wk}`) — 1× par semaine / serveur.",
    "status_auto_on": "**Oui** — rappel ~1 h avant + combat à l’heure.",
    "status_auto_off": "**Non** — utilise `/raidstart` manuel.",
    "status_footer": "Fuseau : BOT_TIMEZONE · Les heures utilisent une localisation correcte (pytz). Logs « raid alert 1h » en INFO.",
    "config_help_title": "⚙️ Raid — aide",
    "config_help_desc": (
        "Utilise **`/raidconfig`** pour ouvrir le **panneau interactif** (menus + boutons).\n\n"
        "• **Salon** : alerte ~1 h avant + messages de combat.\n"
        "• **Sans auto** : les admins utilisent **`/raidstart`**.\n"
        "• **`/raid statut`** (éphémère) : récap sans modifier la config."
    ),
    "config_panel_title": "⚙️ Raid boss — configuration",
    "config_panel_desc": (
        "Choisis les options ci‑dessous — **chaque changement est enregistré** tout de suite.\n"
        "**Salon** · **jour** · **heure** · **minutes** (pas de 5) · boutons **Auto** · **HH:MM** pour une minute précise.\n"
        "**Enregistrer** ferme le panneau avec une confirmation · **Fermer** ferme sans message."
    ),
    "raid_invite_nope": "❌ Ce n’est pas ton invitation.",
    "raid_already_running": "Un raid est déjà en cours sur ce serveur.",
    "raid_week_limit_hit": "❌ La limite **1 × /raidstart par semaine** a déjà été atteinte pour ce serveur.",
    "raid_start_ok": (
        "✅ **Raid lancé** dans {mention}.\n"
        "• Semaine ISO enregistrée : **{wk}** — tu ne pourras plus utiliser **`/raidstart`** "
        "sur ce serveur avant la **semaine prochaine**.\n"
        "• Le raid **automatique** (option **Auto : ON** dans **`/raidconfig`**) n’est pas affecté."
    ),
    "raid_cancel_embed": "Annulé — aucun raid lancé.",
    "raid_cancel_short": "Annulé.",
    "phase_victory": "Victoire !",
    "phase_low": "Le boss **vacille** — encore quelques coups !",
    "phase_mid": "Le boss **blessé** — la pression monte !",
    "phase_high": "Le combat fait rage.",
    "phase_full": "Le boss tient le front… pour l’instant.",
    "mode_not_yours": "❌ Ce menu n’est pas pour toi.",
    "mode_already": "✅ Tu as **déjà choisi** le mode pour ce raid.",
    "mode_saved": (
        "✅ Mode enregistré : **{label}** ({tier})\n"
        "• Dégâts par bonne réponse (tirage) : **~{lo}–{hi}**\n"
        "• Bonus **XP coup final** si tu achèves le boss : **+{fin}** (hors répartition dégâts / MVP / temps)."
    ),
    "join_btn": "✅ S'inscrire au raid",
    "join_already": "✅ Tu es **déjà inscrit(e)** à ce raid. Attends la fin du timer d’inscription.",
    "join_ok": "Tu es enregistré(e) pour ce raid. **{n}** participants pour l’instant.",
    "join_embed_title": "🎮 Choix du mini-jeu (visible par toi seul)",
    "join_embed_desc": (
        "Sélectionne le **type de défi** pour **toutes** tes manches.\n"
        "• **Facile** = personnage (4 choix) et **genre** — erreurs = **moins de dégâts** si tu finis par trouver. "
        "**Moyen** = année, épisodes, plus populaire (idem). "
        "**Difficile** = **affiche** (tu tapes le titre dans le salon, comme **`/animequiz`**) et **qui est-ce** flou.\n"
        "• Modes plus durs → **dégâts** et **bonus coup final** plus élevés.\n"
        "• _Sans choix avant la fin du timer d’inscription → mode **{default_mode}**._"
    ),
    "hub_btn": "🎯 Recevoir ma manche (défi perso)",
    "hub_round_over": "Cette manche est terminée.",
    "hub_not_participant": "Tu n’étais pas inscrit(e) au début du raid. Tu peux regarder le combat dans le salon.",
    "hub_round_done": "Tu as déjà terminé ta manche (réponse donnée ou temps écoulé).",
    "hub_has_challenge": "Tu as déjà un défi en cours — regarde tes messages **éphémères** au-dessus.",
    "hub_burst": "⏳ Trop de clics — réessaie dans **{s}s**.",
    "hub_load_fail": "❌ Impossible de charger un défi. Réessaie.",
    "emb_gw_title": "🕵️ Qui est-ce ? (raid)",
    "emb_gw_fallback": "Tape le nom du personnage dans ce salon.",
    "emb_aq_title": "🖼️ Quel anime ? (raid — mode difficile)",
    "emb_aq_fallback": "Tape le titre dans ce salon.",
    "emb_hl_title": "⬆️⬇️ Quel anime est le plus populaire ?",
    "emb_hl_fallback": "Réponds correctement pour infliger des dégâts.",
    "emb_generic_title": "🎭 Ton défi (personnel)",
    "emb_generic_fallback": "Réponds correctement pour infliger des dégâts.",
    "not_your_challenge": "❌ Ce n’est pas ton défi.",
    "boss_dead_answer": "🏆 Le boss est déjà vaincu — cette réponse n’a pas été comptée.",
    "success_dmg": "**+{dmg:,}** dégâts au boss · **{ms}** ms",
    "success_penalty": "_Tirage de base {base:,} → **×{mult:.0%}** après **{w}** erreur(s)._",
    "challenge_gc": (
        "Manche **{rn}/{mr}** — clique sur le **bon** personnage.\n"
        "Indice anime : _{hint}_\n"
        "*(Mauvais choix = ce bouton disparaît pour toi seul.)*"
    ),
    "challenge_gy": (
        "Manche **{rn}/{mr}** — en quelle année **{title}** a-t-il commencé ?\n"
        "*(Mauvais choix = bouton désactivé.)*"
    ),
    "challenge_ge": (
        "Manche **{rn}/{mr}** — combien d’épisodes pour **{title}** ?\n"
        "*(Mauvais choix = bouton désactivé.)*"
    ),
    "challenge_gg": (
        "Manche **{rn}/{mr}** — quel genre parmi ces choix correspond à **{title}** ?\n"
        "*(Un seul est valide ici — format liste AniList.)*"
    ),
    "challenge_hl": (
        "Manche **{rn}/{mr}** — lequel est le **plus populaire** sur AniList ?\n"
        "Clique sur **1️⃣** ou **2️⃣** pour choisir :\n\n"
        "**1️⃣** {t1}\n"
        "**2️⃣** {t2}"
    ),
    "hl_pop_label": "Le plus populaire : {winner}",
    "hl_anilist": "Popularité AniList",
    "challenge_aq": (
        "Manche **{rn}/{mr}** — **quel est cet anime** d’après l’affiche ?\n"
        "➜ **Tape le titre dans ce salon** (comme **`/animequiz`** : FR / EN / JP / synonymes).\n"
        "**Une tentative** — ~{secs} s. Ta réponse sera **supprimée** tout de suite.\n"
        "• `jsp` / pass = abandon (**0** dégâts)."
    ),
    "challenge_gw": (
        "Manche **{rn}/{mr}** — **tape le nom du personnage dans ce salon** (comme **`/guesswho`**).\n"
        "Indice anime : _{hint}_ · **Une tentative** — ~{secs} s.\n"
        "_Ta réponse sera **supprimée** du salon dès envoi (si le bot a « Gérer les messages »), pour limiter les spoilers._"
    ),
    "hub_line_hp": "{emoji} **{hp:,}** / **{maxhp:,}** HP · **{pct}%**",
    "hub_line_bar": "`{bar}`",
    "hub_dmg_total": "⚔️ Dégâts infligés au total : **{dmg:,}** · Combattants : **{n}**",
    "hub_round_line": "**Manche {cur}/{mx}** — ~{secs} s · bouton **Recevoir ma manche** ci-dessous.",
    "hub_journal": "**📜 Journal (récent)**",
    "hub_title": "{emoji} Raid boss — Manche {cur}/{mx}",
    "hit_finisher_short": "💥 **{name}** — **coup final** **{dmg:,}** dégâts ! Le boss tombe.",
    "hit_normal_short": "⚔️ **{name}** · **{dmg:,}** dégâts — il reste **{hp:,}** PV (**{pct}%**).",
    "hit_finisher": (
        "💥 **{name}** — **coup final** : **{dmg:,}** dégâts !\n"
        "🏆 Le boss s’effondre — **{maxhp:,}** PV au total."
    ),
    "hit_high": (
        "⚔️ **{name}** frappe pour **{dmg:,}** ! Le boss tient encore (**{hp:,}** PV, **{pct}%**).\n"
        "🔊 _La mêlée fait rage._"
    ),
    "hit_mid": (
        "💢 **{name}** inflige **{dmg:,}** — le boss recule ! **{hp:,}** PV (**{pct}%**).\n"
        "🔥 _On le sent vaciller._"
    ),
    "hit_low": (
        "🩸 **{name}** — **{dmg:,}** dégâts ! Plus que **{hp:,}** PV (**{pct}%**).\n"
        "⚡ _Encore un effort !_"
    ),
    "raid_cancel_no_players": "❌ **Raid annulé** — aucun participant inscrit.",
    "raid_start_body": (
        "✅ **{n}** participant(s) — le boss a **{hp}** HP "
        "(_{per} × {n} selon l’équipe_).\n"
        "• Jusqu’à **{maxr}** manches — timer **~{secs} s** max **par manche** "
        "si quelqu’un n’a pas encore répondu.\n"
        "• Les **dégâts par bonne réponse** dépendent du **mode** choisi à l’inscription (voir ton message éphémère) "
        "— les modes plus difficiles frappent plus fort.\n"
        "• Les **coups** et le **journal** (embed) montrent le combat ; les erreurs / temps écoulé restent dans le journal."
    ),
    "hub_boss_dead": "🏆 **Boss vaincu !**",
    "final_intro": "**Coup final** : **{name}** ({mode}) — **+{xp}** XP bonus.",
    "timeup_title": "⏰ Temps écoulé",
    "timeup_desc": "C’était **{name}**.",
    "wrong_title": "❌ Pas la bonne réponse",
    "wrong_desc": "La réponse était **{name}**.",
    "already_dead_title": "🏆 Boss déjà vaincu",
    "already_dead_desc": "Cette réponse n’a pas été comptée.",
    "good_title": "✅ Bonne réponse !",
    "round_all_answered": "✅ **Tout le monde a répondu** — enchaînement…",
    "round_early_msg": "⏩ **Manche {n}** terminée (tout le monde a participé) — **{hp}** HP restants.",
    "round_timeout_msg": "⏰ **Fin de la manche {n}** — le boss tient encore (**{hp}** HP).",
    "force_finish": (
        "🔥 **Dernière salve collective !** Le raid se termine : le boss tombe "
        "(**{hp}** HP restants comptés comme vaincus)."
    ),
    "victory_title": "🏁 Raid terminé",
    "victory_summary": (
        "**{np}** joueur(s) · **{nr}** manche(s) · durée **~{dur}** · "
        "dégâts infligés **{td}** (boss **{maxhp}** HP)"
    ),
    "victory_xp_header": "**XP par participant**",
    "xp_line": "• **{name}** — **+{xp}** XP{badges} — {dmg} dégâts",
    "badge_mvp": "MVP dégâts",
    "badge_fast": "meilleur temps (1 manche)",
    "badge_fin": "coup final (+{xp} XP)",
    "footer_mvp": "MVP : {name}",
    "footer_fast": "Plus rapide : {name} ({ms} ms)",
    "footer_fin": "Coup final : {name} (+{xp} XP)",
    "promo": (
        "⚔️ **BOSS RAID (hebdo)** — Inscription ouverte **~{join}s** "
        "_(délai **fixe** depuis le lancement ; il ne se prolonge pas à chaque inscription)_.\n"
        "• Chaque inscrit a **son propre** défi (boutons en **message privé au salon**).\n"
        "• **Dégâts aléatoires** par bonne réponse : fourchette selon le **mode** choisi à l’inscription.\n"
        "• Jusqu’à **{maxr}** manches ; PV du boss = **nombre d’inscrits** × {per_player}.\n"
        "• Tout le monde a **terminé** son défi (réussi, faux, ou temps écoulé) → manche suivante sans attendre la fin du timer.\n"
        "• XP : base + part des dégâts + MVP + meilleur temps sur une manche + coup final."
    ),
    "signup_title": "📋 Inscription",
    "signup_desc": "Clique pour participer au combat. **Salon vocal non requis.**",
    "alert_1h": "@here ⏰ **Boss Raid** dans **1 h** — préparez-vous (quiz / persos AniList) !",
    "raid_no_channel": (
        "❌ Aucun salon de raid configuré. Ouvre **`/raidconfig`** et choisis un **salon** dans le menu."
    ),
    "raid_limit_cmd": (
        "❌ **Limite atteinte** : **`/raidstart`** est utilisable **une seule fois par semaine** "
        "par serveur (semaine ISO **{wk}**). Réessaie la semaine prochaine.\n"
        "_Le raid **automatique** (**Auto : ON** dans **`/raidconfig`**) n’est pas compté dans cette limite._"
    ),
    "raid_confirm_title": "⚔️ Confirmer le lancement du raid",
    "raid_confirm_desc": (
        "Tu t’apprêtes à lancer un **Boss Raid** immédiat.\n\n"
        "• **Après confirmation**, ce serveur ne pourra plus utiliser **`/raidstart`** jusqu’à la "
        "**semaine prochaine** (limite **1 × par semaine ISO**, ici : **{wk}**).\n"
        "• Le **raid auto** hebdomadaire (**Auto : ON** dans **`/raidconfig`**) **n’est pas** consommé par cette limite.\n\n"
        "**Salon du raid :** {ch}\n\n"
        "Clique **Confirmer** seulement si tu en acceptes les conditions."
    ),
    "btn_confirm_start": "🚀 Confirmer le lancement",
    "btn_cancel": "Annuler",
    "test_alert": "@here 🧪 **TEST** — dans 1 h ce serait l’alerte avant le **Boss Raid**.",
    "test_forbidden": "❌ Je ne peux pas envoyer de message dans {ch}. Vérifie les permissions du bot.",
    "test_err": "❌ Erreur : `{err}`",
    "test_ok": "✅ Message de test envoyé dans {ch}.",
    "chain_no_quiz": "❌ Module quiz indisponible.",
    "chain_intro": (
        "⛓️ **Chain quiz** — une bonne réponse enchaîne avec une difficulté supérieure. "
        "Erreur ou `jsp` = fin. Tape le titre de l’anime (FR/EN/JP)."
    ),
    "chain_round": "⛓️ Chain · Manche {n} ({diff})",
    "chain_desc": "**{sec}s** — quel est cet anime ?",
    "chain_timeout": "⏰ Fin de chaîne à **{streak}** bonne(s) réponse(s).",
    "chain_skip": "⏭️ Arrêt — chaîne : **{streak}** · XP gagné : **{xp}**.",
    "chain_ok": "✅ +**{xp}** XP · Chaîne **{streak}** — prochaine manche !",
    "chain_wrong": "❌ C’était **{title}**. Chaîne terminée : **{streak}** · XP total : **{xp}**.",
    "gw_no_char": "❌ Pas de personnage.",
    "gw_title": "🕵️ Qui est-ce ?",
    "gw_desc": "**{diff}** — en cas de victoire : **+{xp} XP**.\nTape le **nom du personnage** ({sec} s). Indice anime : _{hint}_",
    "gw_footer_list": "Personnage tiré depuis ta liste AniList (complété, en cours, relecture, en pause).",
    "gw_footer_global": "Liste AniList vide ou indisponible — tirage global (popularité).",
    "gw_timeout": "⏰ Temps écoulé — c’était **{name}** _(difficulté **{diff}**, récompense prévue **+{xp} XP**)_.",
    "gw_win": "✅ Bravo ! C’était **{name}** — tu gagnes **+{xp} XP** _(**{diff}**)_.",
    "gw_lose": "❌ Ce n’était pas ça — la réponse était **{name}** _(**{diff}** aurait rapporté **+{xp} XP**)_.",
    "diff_easy": "Facile",
    "diff_normal": "Normal",
    "diff_hard": "Difficile",
}

_EN_RAW = {
    "guild_only": "❌ Server only.",
    "err_invalid_server": "❌ Invalid server.",
    "err_hhmm_format": "❌ Expected format: **`HH:MM`** (e.g. `20:30`).",
    "err_bad_time": "❌ Invalid time.",
    "err_wrong_guild": "❌ Wrong server.",
    "err_admin": "❌ Administrator required.",
    "err_text_channel": "❌ Pick a **text** channel (or announcements).",
    "err_channel_this_guild": "❌ The channel must be on **this** server.",
    "raid_save_ok": "✅ **Boss raid** settings saved.",
    "ph_channel": "Announcements & battle channel",
    "ph_weekday": "Weekday (bot timezone)",
    "ph_hour": "Hour (0–23)",
    "ph_minute": "Minutes (steps of 5 — or HH:MM button)",
    "modal_title": "Raid time (HH:MM)",
    "modal_label": "Time (bot timezone)",
    "modal_ph": "e.g. 20:30",
    "btn_auto_on": "🤖 Auto: ON",
    "btn_auto_off": "⛔ Auto: OFF",
    "btn_hhmm": "🕐 Time HH:MM",
    "btn_save": "💾 Save",
    "btn_close": "Close",
    "status_title": "⚔️ Boss raid — status",
    "status_desc": "Summary for **this server** (bot timezone).",
    "status_ch_none": "— *not set* — open **`/raidconfig`** and pick a **channel**.",
    "status_field_ch": "📍 Channel",
    "status_field_slot": "📅 Weekly slot",
    "status_field_auto": "🤖 Auto start",
    "status_field_next": "⏱️ Next slot the bot uses",
    "status_field_alert": "🔔 @here alert (~1 h before)",
    "status_field_alert_need_ch": "— *Open **`/raidconfig`** and pick a **channel** — otherwise no announcement.*",
    "status_field_raidstart": "🎯 /raidstart (manual)",
    "status_raidstart_used": "🔒 Already used this week (`{wk}`).",
    "status_raidstart_ok": "✅ Available (`{wk}`) — 1× per week / server.",
    "status_auto_on": "**Yes** — reminder ~1 h before + fight on time.",
    "status_auto_off": "**No** — use `/raidstart` manually.",
    "status_footer": "Timezone: BOT_TIMEZONE · Times use correct localization (pytz). “raid alert 1h” logs at INFO.",
    "config_help_title": "⚙️ Raid — help",
    "config_help_desc": (
        "Use **`/raidconfig`** to open the **interactive panel** (menus + buttons).\n\n"
        "• **Channel**: ~1 h alert + battle messages.\n"
        "• **Without auto**: admins use **`/raidstart`**.\n"
        "• **`/raid statut`** (ephemeral): recap without changing settings."
    ),
    "config_panel_title": "⚙️ Boss raid — configuration",
    "config_panel_desc": (
        "Pick options below — **each change saves** immediately.\n"
        "**Channel** · **weekday** · **hour** · **minutes** (steps of 5) · **Auto** buttons · **HH:MM** for exact minute.\n"
        "**Save** closes the panel with a confirmation · **Close** closes without a message."
    ),
    "raid_invite_nope": "❌ This isn’t your invite.",
    "raid_already_running": "A raid is already running on this server.",
    "raid_week_limit_hit": "❌ The **1 × /raidstart per week** limit was already reached for this server.",
    "raid_start_ok": (
        "✅ **Raid started** in {mention}.\n"
        "• ISO week recorded: **{wk}** — you can’t use **`/raidstart`** on this server again until **next week**.\n"
        "• **Automatic** raid (**Auto: ON** in **`/raidconfig`**) is **not** affected."
    ),
    "raid_cancel_embed": "Cancelled — no raid started.",
    "raid_cancel_short": "Cancelled.",
    "phase_victory": "Victory!",
    "phase_low": "The boss **staggers** — a few more hits!",
    "phase_mid": "The boss is **wounded** — pressure rises!",
    "phase_high": "The battle rages.",
    "phase_full": "The boss holds the line… for now.",
    "mode_not_yours": "❌ This menu isn’t for you.",
    "mode_already": "✅ You’ve **already chosen** the mode for this raid.",
    "mode_saved": (
        "✅ Mode saved: **{label}** ({tier})\n"
        "• Damage per correct answer (roll): **~{lo}–{hi}**\n"
        "• **Finisher XP** bonus if you finish the boss: **+{fin}** (excluding damage / MVP / time split)."
    ),
    "join_btn": "✅ Join the raid",
    "join_already": "✅ You’re **already signed up** for this raid. Wait for the signup timer to end.",
    "join_ok": "You’re registered for this raid. **{n}** participants so far.",
    "join_embed_title": "🎮 Pick your minigame (only you see this)",
    "join_embed_desc": (
        "Choose the **challenge type** for **all** your rounds.\n"
        "• **Easy** = character (4 choices) and **genre** — wrong picks = **less damage** if you eventually get it. "
        "**Medium** = year, episodes, higher/lower (same). "
        "**Hard** = **screenshot** (type the title in channel like **`/animequiz`**) and blurred **guess who**.\n"
        "• Harder modes → **more damage** and **higher finisher** bonus.\n"
        "• _If you don’t pick before signup ends → **{default_mode}**._"
    ),
    "hub_btn": "🎯 Get my round (personal challenge)",
    "hub_round_over": "This round is over.",
    "hub_not_participant": "You weren’t signed up at the start of the raid. You can watch the fight in the channel.",
    "hub_round_done": "You already finished your round (answered or time ran out).",
    "hub_has_challenge": "You already have a challenge open — check your **ephemeral** messages above.",
    "hub_burst": "⏳ Too many clicks — try again in **{s}s**.",
    "hub_load_fail": "❌ Couldn’t load a challenge. Try again.",
    "emb_gw_title": "🕵️ Guess who? (raid)",
    "emb_gw_fallback": "Type the character name in this channel.",
    "emb_aq_title": "🖼️ Which anime? (raid — hard mode)",
    "emb_aq_fallback": "Type the title in this channel.",
    "emb_hl_title": "⬆️⬇️ Which anime is more popular?",
    "emb_hl_fallback": "Answer correctly to deal damage.",
    "emb_generic_title": "🎭 Your challenge (personal)",
    "emb_generic_fallback": "Answer correctly to deal damage.",
    "not_your_challenge": "❌ Not your challenge.",
    "boss_dead_answer": "🏆 The boss is already defeated — this answer wasn’t counted.",
    "success_dmg": "**+{dmg:,}** damage to the boss · **{ms}** ms",
    "success_penalty": "_Base roll {base:,} → **×{mult:.0%}** after **{w}** wrong pick(s)._",
    "challenge_gc": (
        "Round **{rn}/{mr}** — click the **correct** character.\n"
        "Anime hint: _{hint}_\n"
        "*(Wrong pick = that button disappears for you only.)*"
    ),
    "challenge_gy": (
        "Round **{rn}/{mr}** — in what year did **{title}** start?\n"
        "*(Wrong pick = button disabled.)*"
    ),
    "challenge_ge": (
        "Round **{rn}/{mr}** — how many episodes for **{title}**?\n"
        "*(Wrong pick = button disabled.)*"
    ),
    "challenge_gg": (
        "Round **{rn}/{mr}** — which genre among these matches **{title}**?\n"
        "*(Only one is valid — AniList list format.)*"
    ),
    "challenge_hl": (
        "Round **{rn}/{mr}** — which is **more popular** on AniList?\n"
        "Click **1️⃣** or **2️⃣**:\n\n"
        "**1️⃣** {t1}\n"
        "**2️⃣** {t2}"
    ),
    "hl_pop_label": "More popular: {winner}",
    "hl_anilist": "AniList popularity",
    "challenge_aq": (
        "Round **{rn}/{mr}** — **which anime** is this from the cover?\n"
        "➜ **Type the title in this channel** (like **`/animequiz`**: EN / JP / synonyms).\n"
        "**One try** — ~{secs} s. Your message will be **deleted** right away.\n"
        "• `jsp` / pass = forfeit (**0** damage)."
    ),
    "challenge_gw": (
        "Round **{rn}/{mr}** — **type the character name in this channel** (like **`/guesswho`**).\n"
        "Anime hint: _{hint}_ · **One try** — ~{secs} s.\n"
        "_Your message may be **deleted** (if the bot can manage messages) to reduce spoilers._"
    ),
    "hub_line_hp": "{emoji} **{hp:,}** / **{maxhp:,}** HP · **{pct}%**",
    "hub_line_bar": "`{bar}`",
    "hub_dmg_total": "⚔️ Total damage dealt: **{dmg:,}** · Fighters: **{n}**",
    "hub_round_line": "**Round {cur}/{mx}** — ~{secs} s · **Get my round** button below.",
    "hub_journal": "**📜 Recent log**",
    "hub_title": "{emoji} Boss raid — Round {cur}/{mx}",
    "hit_finisher_short": "💥 **{name}** — **finisher** **{dmg:,}** damage! The boss falls.",
    "hit_normal_short": "⚔️ **{name}** · **{dmg:,}** damage — **{hp:,}** HP left (**{pct}%**).",
    "hit_finisher": (
        "💥 **{name}** — **finisher**: **{dmg:,}** damage!\n"
        "🏆 The boss collapses — **{maxhp:,}** HP total."
    ),
    "hit_high": (
        "⚔️ **{name}** hits for **{dmg:,}**! The boss still stands (**{hp:,}** HP, **{pct}%**).\n"
        "🔊 _The melee rages._"
    ),
    "hit_mid": (
        "💢 **{name}** deals **{dmg:,}** — the boss staggers! **{hp:,}** HP (**{pct}%**).\n"
        "🔥 _You can feel it waver._"
    ),
    "hit_low": (
        "🩸 **{name}** — **{dmg:,}** damage! Only **{hp:,}** HP left (**{pct}%**).\n"
        "⚡ _One more push!_"
    ),
    "raid_cancel_no_players": "❌ **Raid cancelled** — no one signed up.",
    "raid_start_body": (
        "✅ **{n}** participant(s) — the boss has **{hp}** HP "
        "(_{per} × {n} for the team_).\n"
        "• Up to **{maxr}** rounds — **~{secs} s** max **per round** "
        "if someone hasn’t answered yet.\n"
        "• **Damage per correct answer** depends on the **mode** you picked at signup (see your ephemeral message) "
        "— harder modes hit harder.\n"
        "• **Hits** and the **log** (embed) show the fight; mistakes / timeouts stay in the log."
    ),
    "hub_boss_dead": "🏆 **Boss defeated!**",
    "final_intro": "**Finisher**: **{name}** ({mode}) — **+{xp}** XP bonus.",
    "timeup_title": "⏰ Time’s up",
    "timeup_desc": "It was **{name}**.",
    "wrong_title": "❌ Wrong answer",
    "wrong_desc": "The answer was **{name}**.",
    "already_dead_title": "🏆 Boss already down",
    "already_dead_desc": "This answer wasn’t counted.",
    "good_title": "✅ Correct!",
    "round_all_answered": "✅ **Everyone answered** — next round…",
    "round_early_msg": "⏩ **Round {n}** over (everyone played) — **{hp}** HP left.",
    "round_timeout_msg": "⏰ **Round {n}** over — the boss still stands (**{hp}** HP).",
    "force_finish": (
        "🔥 **Final salvo!** The raid ends: the boss falls "
        "(**{hp}** HP left counted as defeated)."
    ),
    "victory_title": "🏁 Raid over",
    "victory_summary": (
        "**{np}** player(s) · **{nr}** round(s) · duration **~{dur}** · "
        "damage dealt **{td}** (boss **{maxhp}** HP)"
    ),
    "victory_xp_header": "**XP per participant**",
    "xp_line": "• **{name}** — **+{xp}** XP{badges} — {dmg} damage",
    "badge_mvp": "MVP damage",
    "badge_fast": "fastest time (1 round)",
    "badge_fin": "finisher (+{xp} XP)",
    "footer_mvp": "MVP: {name}",
    "footer_fast": "Fastest: {name} ({ms} ms)",
    "footer_fin": "Finisher: {name} (+{xp} XP)",
    "promo": (
        "⚔️ **BOSS RAID (weekly)** — Signups open **~{join}s** "
        "_(**fixed** timer from start; it doesn’t extend with each signup)_.\n"
        "• Each player gets their **own** challenge (**ephemeral** in the channel).\n"
        "• **Random damage** per correct answer: range depends on **mode** at signup.\n"
        "• Up to **{maxr}** rounds; boss HP = **players** × {per_player}.\n"
        "• When **everyone** finishes (success, fail, or timeout) → next round without waiting for the timer.\n"
        "• XP: base + damage share + MVP + fastest round + finisher."
    ),
    "signup_title": "📋 Signup",
    "signup_desc": "Click to join the fight. **Voice not required.**",
    "alert_1h": "@here ⏰ **Boss Raid** in **1 h** — get ready (quiz / AniList chars)!",
    "raid_no_channel": (
        "❌ No raid channel configured. Open **`/raidconfig`** and pick a **channel** in the menu."
    ),
    "raid_limit_cmd": (
        "❌ **Limit reached**: **`/raidstart`** can only be used **once per week** "
        "per server (ISO week **{wk}**). Try again next week.\n"
        "_**Auto** weekly raid (**Auto: ON** in **`/raidconfig`**) doesn’t count toward this limit._"
    ),
    "raid_confirm_title": "⚔️ Confirm raid start",
    "raid_confirm_desc": (
        "You’re about to start an immediate **Boss Raid**.\n\n"
        "• **After confirming**, this server can’t use **`/raidstart`** again until **next week** "
        "(**1 × per ISO week**, here: **{wk}**).\n"
        "• **Auto** weekly raid (**Auto: ON** in **`/raidconfig`**) is **not** consumed by this limit.\n\n"
        "**Raid channel:** {ch}\n\n"
        "Click **Confirm** only if you accept."
    ),
    "btn_confirm_start": "🚀 Confirm start",
    "btn_cancel": "Cancel",
    "test_alert": "@here 🧪 **TEST** — in 1 h this would be the **Boss Raid** alert.",
    "test_forbidden": "❌ I can’t send a message in {ch}. Check bot permissions.",
    "test_err": "❌ Error: `{err}`",
    "test_ok": "✅ Test message sent in {ch}.",
    "chain_no_quiz": "❌ Quiz module unavailable.",
    "chain_intro": (
        "⛓️ **Chain quiz** — each correct answer bumps difficulty. "
        "Wrong answer or `jsp` = stop. Type the anime title (FR/EN/JP)."
    ),
    "chain_round": "⛓️ Chain · Round {n} ({diff})",
    "chain_desc": "**{sec}s** — what anime is this?",
    "chain_timeout": "⏰ Chain ends at **{streak}** correct answer(s).",
    "chain_skip": "⏭️ Stop — streak: **{streak}** · XP gained: **{xp}**.",
    "chain_ok": "✅ +**{xp}** XP · Streak **{streak}** — next round!",
    "chain_wrong": "❌ It was **{title}**. Chain over: **{streak}** · Total XP: **{xp}**.",
    "gw_no_char": "❌ No character.",
    "gw_title": "🕵️ Guess who?",
    "gw_desc": "**{diff}** — on win: **+{xp} XP**.\nType the **character name** ({sec} s). Anime hint: _{hint}_",
    "gw_footer_list": "Character from your AniList (completed, watching, rewatching, paused).",
    "gw_footer_global": "AniList empty or unavailable — global draw (popularity).",
    "gw_timeout": "⏰ Time’s up — it was **{name}** _(difficulty **{diff}**, reward **+{xp} XP**)_",
    "gw_win": "✅ Nice! It was **{name}** — you earn **+{xp} XP** _(**{diff}**)_",
    "gw_lose": "❌ Not quite — the answer was **{name}** _( **{diff}** would have given **+{xp} XP**)_",
    "diff_easy": "Easy",
    "diff_normal": "Normal",
    "diff_hard": "Hard",
}
EN = {k: _EN_RAW[k] for k in FR}

def main() -> None:
    (ROOT / "_community_games_fr.json").write_text(
        json.dumps(FR, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (ROOT / "_community_games_en.json").write_text(
        json.dumps(EN, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("OK", len(FR), "keys")

if __name__ == "__main__":
    main()
