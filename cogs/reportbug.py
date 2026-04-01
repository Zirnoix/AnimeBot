# cogs/reportbug.py
"""Signalement de bugs en MP (/reportbug) et gestion owner + blacklist."""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
import discord
from discord import app_commands
from discord.ext import commands

from modules import bug_report as br
from modules import core

LOG = logging.getLogger(__name__)

# Brouillon avant envoi (MP) — évite re-saisie ; pas de persistance disque
_draft_body: dict[int, str] = {}
_draft_expires: dict[int, float] = {}
_DRAFT_TTL = 3600.0

# Anti double-clic owner (rapport déjà traité)
_owner_lock: set[str] = set()


def _owner_id() -> int | None:
    raw = (os.getenv("OWNER_ID") or "").strip()
    return int(raw) if raw.isdigit() else None


def _is_owner(uid: int) -> bool:
    oid = _owner_id()
    return oid is not None and int(uid) == oid


def _cleanup_drafts() -> None:
    now = time.time()
    dead = [k for k, exp in _draft_expires.items() if exp < now]
    for k in dead:
        _draft_expires.pop(k, None)
        _draft_body.pop(k, None)


def _reject_cooldown_message(user_id: int) -> str:
    uid = str(int(user_id))
    with core.DATA_JSON_LOCK:
        st = br.load_store()
        lim = st.get("user_limits", {}).get(uid) or {}
        try:
            ru = float(lim.get("reject_until_ts") or 0)
        except (TypeError, ValueError):
            ru = 0.0
    if ru <= 0:
        return "⏳ Tu dois attendre encore un peu avant de refaire un signalement."
    dt = datetime.fromtimestamp(ru, tz=timezone.utc)
    # Afficher la fin du cooldown en heure locale
    try:
        local = dt.astimezone(core.TIMEZONE)
        until = local.strftime("%d/%m/%Y à %H:%M")
    except Exception:
        until = dt.strftime("%d/%m/%Y %H:%M UTC")
    return (
        "⏳ **Signalement temporairement indisponible**\n\n"
        "Ton dernier rapport a été **refusé** (faux bug ou inexistant). "
        "Tu pourras refaire un **`/reportbug`** après le **"
        f"{until}** (heure de Paris).\n\n"
        "Merci de ne signaler que des bugs **réels** et **vérifiables**."
    )


def _daily_message() -> str:
    return (
        "📅 **Quota journalier atteint**\n\n"
        "Tu as déjà envoyé un signalement **aujourd’hui** (fuseau horaire de Paris). "
        "Un seul report par jour — **un bug** à la fois. Réessaie **demain après minuit**."
    )


class BugReportModal(discord.ui.Modal, title="Décrire le bug"):
    def __init__(self, bot: commands.Bot) -> None:
        super().__init__(timeout=300)
        self.bot = bot
        self.cmd = discord.ui.TextInput(
            label="Commande ou système concerné",
            placeholder="Ex. /quiz, /opening, module de profil…",
            required=True,
            max_length=200,
            style=discord.TextStyle.short,
        )
        self.prob = discord.ui.TextInput(
            label="Problème observé",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=2000,
        )
        self.exp = discord.ui.TextInput(
            label="Comportement attendu",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=2000,
        )
        self.repro = discord.ui.TextInput(
            label="Étapes pour reproduire (ou « N/A »)",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=2000,
        )
        self.add_item(self.cmd)
        self.add_item(self.prob)
        self.add_item(self.exp)
        self.add_item(self.repro)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        ok, code = br.validate_bug_text_parts(
            str(self.cmd.value),
            str(self.prob.value),
            str(self.exp.value),
            str(self.repro.value),
        )
        if not ok:
            hint = (
                "Ton texte est **trop court** ou trop vague. "
                f"Détaille au moins **{br.MIN_TOTAL_CHARS} caractères** au total, "
                f"avec au moins **{br.MIN_FIELD_CHARS} caractères** dans les trois premiers champs."
            )
            await interaction.response.send_message(hint, ephemeral=True)
            return
        body = br.format_bug_body(
            str(self.cmd.value),
            str(self.prob.value),
            str(self.exp.value),
            str(self.repro.value),
        )
        uid = interaction.user.id
        _cleanup_drafts()
        _draft_body[uid] = body
        _draft_expires[uid] = time.time() + _DRAFT_TTL

        preview = discord.Embed(
            title="📋 Aperçu de ton signalement",
            description=body[:4000],
            color=discord.Color.orange(),
        )
        preview.set_footer(text="Un seul bug par report — vérifie avant d’envoyer.")
        await interaction.response.send_message(
            embed=preview,
            view=SendReportView(self.bot, uid),
        )


class SendReportView(discord.ui.View):
    def __init__(self, bot: commands.Bot, author_id: int) -> None:
        super().__init__(timeout=600)
        self.bot = bot
        self.author_id = author_id

    @discord.ui.button(label="Envoyer le report", style=discord.ButtonStyle.success, emoji="📤")
    async def send(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Ce bouton n’est pas pour toi.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        _cleanup_drafts()
        body = _draft_body.get(self.author_id)
        if not body or _draft_expires.get(self.author_id, 0) < time.time():
            await interaction.followup.send(
                "⏱️ Ce brouillon a expiré. Relance **`/reportbug`** depuis le serveur.",
                ephemeral=True,
            )
            return
        ok, reason = br.can_user_submit_bug(self.author_id)
        if not ok:
            if reason == "blacklist":
                await interaction.followup.send(_msg_blacklist(), ephemeral=True)
                return
            if reason == "reject_cooldown":
                await interaction.followup.send(_reject_cooldown_message(self.author_id), ephemeral=True)
                return
            if reason == "daily_limit":
                await interaction.followup.send(_daily_message(), ephemeral=True)
                return
        rid = br.create_pending_report(
            self.author_id,
            str(interaction.user),
            body,
        )
        if rid is None:
            ok2, reason2 = br.can_user_submit_bug(self.author_id)
            if reason2 == "daily_limit":
                await interaction.followup.send(_daily_message(), ephemeral=True)
            elif reason2 == "reject_cooldown":
                await interaction.followup.send(_reject_cooldown_message(self.author_id), ephemeral=True)
            else:
                await interaction.followup.send(
                    "❌ Impossible d’enregistrer le signalement pour le moment. Réessaie plus tard.",
                    ephemeral=True,
                )
            return

        oid = _owner_id()
        if oid is None:
            br.rollback_report(self.author_id, rid)
            await interaction.followup.send("❌ Configuration owner invalide.", ephemeral=True)
            return
        owner = self.bot.get_user(oid) or await self.bot.fetch_user(oid)
        embed = discord.Embed(
            title=f"🐞 Nouveau bug report #{rid}",
            description=body[:4000],
            color=discord.Color.red(),
        )
        embed.add_field(name="Auteur", value=f"{interaction.user} (`{interaction.user.id}`)", inline=False)
        embed.add_field(name="État", value="**En attente** de validation", inline=True)
        embed.add_field(
            name="Date (UTC)",
            value=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            inline=True,
        )
        try:
            await owner.send(embed=embed, view=OwnerDecisionView(self.bot, rid))
        except discord.HTTPException as e:
            LOG.exception("owner DM failed for report %s: %s", rid, e)
            br.rollback_report(self.author_id, rid)
            await interaction.followup.send(
                "❌ Le propriétaire n’a pas pu être contacté en **message privé** pour le moment. "
                "Ton signalement **n’a pas été enregistré**. Réessaie plus tard.",
                ephemeral=True,
            )
            return

        _draft_body.pop(self.author_id, None)
        _draft_expires.pop(self.author_id, None)
        for child in self.children:
            child.disabled = True
        try:
            await interaction.message.edit(view=self)  # type: ignore
        except Exception:
            pass
        await interaction.followup.send(
            "✅ **Signalement envoyé** au propriétaire. Tu recevras une réponse en **message privé** "
            "dès qu’il aura traité ton rapport.",
            ephemeral=True,
        )


def _msg_blacklist() -> str:
    return (
        "🚫 **Accès au signalement désactivé**\n\n"
        "Tu n’as plus accès au système de signalement de bugs."
    )


class OwnerDecisionView(discord.ui.View):
    def __init__(self, bot: commands.Bot, report_id: int) -> None:
        super().__init__(timeout=None)
        self.bot = bot
        self.report_id = report_id

    @discord.ui.button(label="Refuser le bug", style=discord.ButtonStyle.danger, emoji="✖️")
    async def refuse(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not _is_owner(interaction.user.id):
            await interaction.response.send_message("Réservé au propriétaire du bot.", ephemeral=True)
            return
        key = f"ref:{self.report_id}"
        if key in _owner_lock:
            await interaction.response.send_message("Traitement déjà en cours.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        _owner_lock.add(key)
        try:
            ok, rep = br.refuse_report(self.report_id, interaction.user.id)
            if not ok:
                await interaction.followup.send(
                    "Ce rapport n’est plus en attente (déjà traité ou introuvable).",
                    ephemeral=True,
                )
                return
            uid = int(rep.get("user_id") or 0)
            u = self.bot.get_user(uid) or await self.bot.fetch_user(uid)
            try:
                await u.send(
                    embed=discord.Embed(
                        title="Signalement refusé",
                        description=(
                            "Ton report de bug a été **refusé** (faux bug, hors sujet ou non reproductible).\n\n"
                            "Tu ne pourras pas utiliser **`/reportbug`** pendant **7 jours**. "
                            "Merci de ne signaler que des bugs **réels** et **vérifiables**."
                        ),
                        color=discord.Color.dark_red(),
                    )
                )
            except discord.HTTPException:
                LOG.warning("impossible DM user %s refuse report %s", uid, self.report_id)
            for child in self.children:
                child.disabled = True
            try:
                await interaction.message.edit(
                    content="**Refusé** — cooldown 7 jours appliqué au joueur.",
                    embed=interaction.message.embeds[0] if interaction.message.embeds else None,
                    view=self,
                )
            except Exception:
                pass
            await interaction.followup.send("✅ Refus enregistré.", ephemeral=True)
        finally:
            _owner_lock.discard(key)

    @discord.ui.button(label="Confirmer le bug", style=discord.ButtonStyle.success, emoji="✅")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not _is_owner(interaction.user.id):
            await interaction.response.send_message("Réservé au propriétaire du bot.", ephemeral=True)
            return
        rep = br.get_report(self.report_id)
        if not rep or str(rep.get("status")) != "pending":
            await interaction.response.send_message("Ce rapport n’est plus en attente.", ephemeral=True)
            return
        emb: discord.Embed | None = None
        if interaction.message and interaction.message.embeds:
            emb = interaction.message.embeds[0].copy()
            emb.add_field(
                name="Validation",
                value="Choisis la **gravité** et si le bug était **difficile à trouver**, puis **Attribuer la récompense**.",
                inline=False,
            )
        await interaction.response.edit_message(embed=emb, view=OwnerRewardView(self.bot, self.report_id))


class OwnerRewardView(discord.ui.View):
    def __init__(self, bot: commands.Bot, report_id: int) -> None:
        super().__init__(timeout=None)
        self.bot = bot
        self.report_id = report_id
        self.severity: str | None = None
        self.bug_hard: bool | None = None

    @discord.ui.select(
        placeholder="Gravité du bug",
        options=[
            discord.SelectOption(label="Petit bug", value="petit", description="300 XP"),
            discord.SelectOption(label="Bug moyen", value="moyen", description="600 XP"),
            discord.SelectOption(label="Gros bug", value="gros", description="1000 XP"),
        ],
        row=0,
    )
    async def select_severity(self, interaction: discord.Interaction, select: discord.ui.Select) -> None:
        if not _is_owner(interaction.user.id):
            await interaction.response.send_message("Réservé au propriétaire.", ephemeral=True)
            return
        self.severity = select.values[0]
        await interaction.response.defer()

    @discord.ui.select(
        placeholder="Difficile à trouver ?",
        options=[
            discord.SelectOption(label="Non", value="0"),
            discord.SelectOption(label="Oui (+300 XP)", value="1"),
        ],
        row=1,
    )
    async def select_hard(self, interaction: discord.Interaction, select: discord.ui.Select) -> None:
        if not _is_owner(interaction.user.id):
            await interaction.response.send_message("Réservé au propriétaire.", ephemeral=True)
            return
        self.bug_hard = select.values[0] == "1"
        await interaction.response.defer()

    @discord.ui.button(label="Attribuer la récompense", style=discord.ButtonStyle.primary, row=2)
    async def apply_xp(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not _is_owner(interaction.user.id):
            await interaction.response.send_message("Réservé au propriétaire.", ephemeral=True)
            return
        if self.severity is None or self.bug_hard is None:
            await interaction.response.send_message(
                "Choisis la **gravité** et si le bug était **difficile à trouver** avant de valider.",
                ephemeral=True,
            )
            return
        key = f"ok:{self.report_id}"
        if key in _owner_lock:
            await interaction.response.send_message("Traitement déjà en cours.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        _owner_lock.add(key)
        try:
            ok, rep, xp = br.confirm_report(
                self.report_id,
                interaction.user.id,
                self.severity,
                self.bug_hard,
            )
            if not ok or not rep:
                await interaction.followup.send("❌ Impossible de confirmer (déjà traité ?).", ephemeral=True)
                return
            uid = int(rep.get("user_id") or 0)
            await core.add_xp(self.bot, None, uid, xp, announce=False)
            u = self.bot.get_user(uid) or await self.bot.fetch_user(uid)
            try:
                sev = str(rep.get("severity") or "")
                sev_fr = {"petit": "Petit bug (300 XP)", "moyen": "Bug moyen (600 XP)", "gros": "Gros bug (1000 XP)"}
                hard = bool(rep.get("hard_to_find"))
                base = xp - (br.HARD_BONUS_XP if hard else 0)
                lines = [
                    "Ton signalement a été **validé**.",
                    "",
                    f"**Gravité** : {sev_fr.get(sev, sev)}",
                    f"**Difficile à trouver** : {'Oui (+300 XP)' if hard else 'Non'}",
                    f"**Total** : **{xp} XP** (dont **{base}** de base).",
                    "",
                    "Merci d’aider à améliorer le bot !",
                ]
                await u.send(
                    embed=discord.Embed(
                        title="Bug confirmé — merci !",
                        description="\n".join(lines),
                        color=discord.Color.green(),
                    )
                )
            except discord.HTTPException:
                LOG.warning("impossible DM user %s confirm report %s", uid, self.report_id)
            for child in self.children:
                child.disabled = True
            try:
                await interaction.message.edit(
                    content=f"**Confirmé** — **{xp} XP** attribués à `{uid}`.",
                    embed=interaction.message.embeds[0] if interaction.message.embeds else None,
                    view=self,
                )
            except Exception:
                pass
            await interaction.followup.send(f"✅ OK — {xp} XP attribués.", ephemeral=True)
        finally:
            _owner_lock.discard(key)


class IntroView(discord.ui.View):
    def __init__(self, bot: commands.Bot) -> None:
        super().__init__(timeout=600)
        self.bot = bot

    @discord.ui.button(label="Rédiger mon report", style=discord.ButtonStyle.primary, emoji="📝")
    async def open_modal(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.send_modal(BugReportModal(self.bot))


class ReportBugCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    blacklist = app_commands.Group(
        name="blacklist",
        description="Blacklist des signalements de bugs (propriétaire uniquement).",
        extras={"owner_only": True},
    )

    @app_commands.command(
        name="reportbug",
        description="Signaler un bug en privé (MP) — un bug par jour, détails par message privé.",
    )
    async def reportbug(self, interaction: discord.Interaction) -> None:
        uid = interaction.user.id
        _cleanup_drafts()
        ok, reason = br.can_user_submit_bug(uid)
        if not ok:
            if reason == "blacklist":
                await interaction.response.send_message(_msg_blacklist(), ephemeral=bool(interaction.guild))
                return
            if reason == "reject_cooldown":
                await interaction.response.send_message(
                    _reject_cooldown_message(uid),
                    ephemeral=bool(interaction.guild),
                )
                return
            if reason == "daily_limit":
                await interaction.response.send_message(_daily_message(), ephemeral=bool(interaction.guild))
                return
        embed = discord.Embed(
            title="📋 Signalement de bug",
            description=(
                "Merci de participer à l’amélioration du bot.\n\n"
                "• **Un seul bug par report** — ne mélange pas plusieurs problèmes.\n"
                "• **Un signalement par jour** (reset à minuit, heure de Paris).\n"
                "• Si tu abuses ou envoies de faux signalements, tu peux être **bloqué** "
                "ou **sanctionné** 7 jours après un refus.\n\n"
                "Clique sur **Rédiger mon report** : un formulaire te demandera :\n"
                "• la commande ou le système concerné ;\n"
                "• le problème observé ;\n"
                "• le comportement attendu ;\n"
                "• les étapes pour reproduire (ou « N/A »).\n\n"
                "Ensuite, vérifie l’aperçu et envoie avec **Envoyer le report**."
            ),
            color=discord.Color.blue(),
        )
        embed.set_footer(text="AnimeBot — signalements privés (MP)")
        in_guild = interaction.guild is not None
        if not in_guild:
            await interaction.response.send_message(embed=embed, view=IntroView(self.bot))
            return
        try:
            await interaction.user.send(embed=embed, view=IntroView(self.bot))
        except discord.HTTPException:
            await interaction.response.send_message(
                "🔒 **Impossible d’ouvrir ton signalement**\n\n"
                "Tes **messages privés** sont fermés ou le bot ne peut pas t’écrire.\n\n"
                "**Ouvre tes MP** (Paramètres → Confidentialité → messages privés) pour que le bot "
                "puisse t’envoyer le formulaire **en privé**. Cela évite de publier un bug dans le "
                "serveur et limite que d’autres copient le même report.\n\n"
                "Il n’y a **pas** d’envoi dans un salon : tout passe par MP.",
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            "📬 **Regarde tes messages privés** — le bot t’a envoyé la suite pour rédiger ton signalement.",
            ephemeral=True,
        )

    @blacklist.command(name="add", description="Ajouter un utilisateur à la blacklist des signalements.")
    @app_commands.describe(user_id="Identifiant Discord (nombre) de l’utilisateur")
    async def blacklist_add(self, interaction: discord.Interaction, user_id: str) -> None:
        if not _is_owner(interaction.user.id):
            await interaction.response.send_message("❌ Réservé au propriétaire du bot.", ephemeral=True)
            return
        raw = (user_id or "").strip()
        if not raw.isdigit():
            await interaction.response.send_message("❌ ID invalide (nombre attendu).", ephemeral=True)
            return
        uid = int(raw)
        if uid == interaction.user.id:
            await interaction.response.send_message("❌ Tu ne peux pas te blacklist toi-même.", ephemeral=True)
            return
        if br.blacklist_add(uid):
            await interaction.response.send_message(f"✅ `{uid}` ajouté à la blacklist.", ephemeral=True)
        else:
            await interaction.response.send_message(f"ℹ️ `{uid}` était déjà blacklist.", ephemeral=True)

    @blacklist.command(name="remove", description="Retirer un utilisateur de la blacklist des signalements.")
    @app_commands.describe(user_id="Identifiant Discord (nombre)")
    async def blacklist_remove(self, interaction: discord.Interaction, user_id: str) -> None:
        if not _is_owner(interaction.user.id):
            await interaction.response.send_message("❌ Réservé au propriétaire du bot.", ephemeral=True)
            return
        raw = (user_id or "").strip()
        if not raw.isdigit():
            await interaction.response.send_message("❌ ID invalide.", ephemeral=True)
            return
        uid = int(raw)
        if br.blacklist_remove(uid):
            await interaction.response.send_message(f"✅ `{uid}` retiré de la blacklist.", ephemeral=True)
        else:
            await interaction.response.send_message(f"ℹ️ `{uid}` n’était pas blacklist.", ephemeral=True)

    @blacklist.command(name="list", description="Voir la blacklist des signalements (IDs).")
    async def blacklist_list(self, interaction: discord.Interaction) -> None:
        if not _is_owner(interaction.user.id):
            await interaction.response.send_message("❌ Réservé au propriétaire du bot.", ephemeral=True)
            return
        bl = br.get_blacklist()
        if not bl:
            await interaction.response.send_message("Blacklist vide.", ephemeral=True)
            return
        chunk = ", ".join(f"`{x}`" for x in bl[:50])
        more = f" (+{len(bl) - 50} autres)" if len(bl) > 50 else ""
        await interaction.response.send_message(f"**Blacklist** : {chunk}{more}", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ReportBugCog(bot))
