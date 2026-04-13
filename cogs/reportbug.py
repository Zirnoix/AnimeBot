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
from modules import i18n
from modules.app_cmd_locale import ui_str

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


def _reject_cooldown_message(user_id: int, lang: str) -> str:
    uid = str(int(user_id))
    with core.DATA_JSON_LOCK:
        st = br.load_store()
        lim = st.get("user_limits", {}).get(uid) or {}
        try:
            ru = float(lim.get("reject_until_ts") or 0)
        except (TypeError, ValueError):
            ru = 0.0
    if ru <= 0:
        return i18n.t("reportbug.reject_wait_short", lang)
    dt = datetime.fromtimestamp(ru, tz=timezone.utc)
    try:
        local = dt.astimezone(core.TIMEZONE)
        fmt = i18n.t("common.datetime_until", lang)
        until = local.strftime(fmt)
    except Exception:
        until = dt.strftime("%d/%m/%Y %H:%M UTC")
    return i18n.t("reportbug.reject_cooldown", lang, until=until)


def _daily_message(lang: str) -> str:
    return i18n.t("reportbug.daily", lang)


class BugReportModal(discord.ui.Modal):
    def __init__(self, bot: commands.Bot, lang: str) -> None:
        super().__init__(title=i18n.t("reportbug.modal_title", lang)[:45], timeout=300)
        self.bot = bot
        self.lang = lang
        self.cmd = discord.ui.TextInput(
            label=i18n.t("reportbug.modal_cmd", lang)[:45],
            placeholder=i18n.t("reportbug.modal_cmd_ph", lang)[:100],
            required=True,
            max_length=200,
            style=discord.TextStyle.short,
        )
        self.prob = discord.ui.TextInput(
            label=i18n.t("reportbug.modal_prob", lang)[:45],
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=2000,
        )
        self.exp = discord.ui.TextInput(
            label=i18n.t("reportbug.modal_exp", lang)[:45],
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=2000,
        )
        self.repro = discord.ui.TextInput(
            label=i18n.t("reportbug.modal_repro", lang)[:45],
            placeholder=i18n.t("reportbug.modal_repro_ph", lang)[:100],
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=2000,
        )
        self.add_item(self.cmd)
        self.add_item(self.prob)
        self.add_item(self.exp)
        self.add_item(self.repro)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        lg = self.lang
        ok, code = br.validate_bug_text_parts(
            str(self.cmd.value),
            str(self.prob.value),
            str(self.exp.value),
            str(self.repro.value),
        )
        if not ok:
            if code == "command_empty":
                hint = i18n.t("reportbug.hint_cmd", lg)
            elif code == "too_short":
                hint = i18n.t("reportbug.hint_total", lg, min=br.MIN_TOTAL_CHARS)
            else:
                hint = i18n.t("reportbug.hint_fields", lg, min=br.MIN_FIELD_CHARS)
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
            title=i18n.t("reportbug.preview_title", lg),
            description=body[:4000],
            color=discord.Color.orange(),
        )
        preview.set_footer(text=i18n.t("reportbug.preview_footer", lg))
        await interaction.response.send_message(
            embed=preview,
            view=SendReportView(self.bot, uid, lg),
        )


class SendReportView(discord.ui.View):
    def __init__(self, bot: commands.Bot, author_id: int, lang: str) -> None:
        super().__init__(timeout=600)
        self.bot = bot
        self.author_id = author_id
        self.lang = lang
        self.send.label = i18n.t("reportbug.btn_send", lang)[:80]

    @discord.ui.button(label="Send report", style=discord.ButtonStyle.success, emoji="📤")
    async def send(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        lg = self.lang
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(i18n.t("reportbug.btn_not_you", lg), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        _cleanup_drafts()
        body = _draft_body.get(self.author_id)
        if not body or _draft_expires.get(self.author_id, 0) < time.time():
            await interaction.followup.send(
                i18n.t("reportbug.draft_expired", lg),
                ephemeral=True,
            )
            return
        ok, reason = br.can_user_submit_bug(self.author_id)
        if not ok:
            if reason == "blacklist":
                await interaction.followup.send(_msg_blacklist(lg), ephemeral=True)
                return
            if reason == "reject_cooldown":
                await interaction.followup.send(_reject_cooldown_message(self.author_id, lg), ephemeral=True)
                return
            if reason == "daily_limit":
                await interaction.followup.send(_daily_message(lg), ephemeral=True)
                return
        rid = br.create_pending_report(
            self.author_id,
            str(interaction.user),
            body,
        )
        if rid is None:
            ok2, reason2 = br.can_user_submit_bug(self.author_id)
            if reason2 == "daily_limit":
                await interaction.followup.send(_daily_message(lg), ephemeral=True)
            elif reason2 == "reject_cooldown":
                await interaction.followup.send(_reject_cooldown_message(self.author_id, lg), ephemeral=True)
            else:
                await interaction.followup.send(
                    i18n.t("reportbug.save_fail", lg),
                    ephemeral=True,
                )
            return

        oid = _owner_id()
        if oid is None:
            br.rollback_report(self.author_id, rid)
            await interaction.followup.send(i18n.t("reportbug.owner_config", lg), ephemeral=True)
            return
        # Panneau owner : même logique que l’utilisateur (serveur ou locale Discord en MP)
        owner_lang = i18n.interaction_lang(interaction)
        owner = self.bot.get_user(oid) or await self.bot.fetch_user(oid)
        embed = discord.Embed(
            title=i18n.t("reportbug.embed_new_title", owner_lang, rid=rid),
            description=body[:4000],
            color=discord.Color.red(),
        )
        embed.add_field(
            name=i18n.t("reportbug.embed_author", owner_lang),
            value=f"{interaction.user} (`{interaction.user.id}`)",
            inline=False,
        )
        embed.add_field(
            name=i18n.t("reportbug.embed_state", owner_lang),
            value=i18n.t("reportbug.embed_state_pending", owner_lang),
            inline=True,
        )
        embed.add_field(
            name=i18n.t("reportbug.embed_date_utc", owner_lang),
            value=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            inline=True,
        )
        embed.set_footer(text=i18n.t("reportbug.embed_footer_owner", owner_lang))
        try:
            await owner.send(embed=embed, view=OwnerDecisionView(self.bot, rid, owner_lang))
        except discord.HTTPException as e:
            LOG.exception("owner DM failed for report %s: %s", rid, e)
            br.rollback_report(self.author_id, rid)
            await interaction.followup.send(
                i18n.t("reportbug.owner_dm_fail", lg),
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
            i18n.t("reportbug.sent_ok", lg),
            ephemeral=True,
        )


def _msg_blacklist(lang: str) -> str:
    return i18n.t("reportbug.blacklist", lang)


class OwnerDecisionView(discord.ui.View):
    def __init__(self, bot: commands.Bot, report_id: int, lang: str) -> None:
        super().__init__(timeout=None)
        self.bot = bot
        self.report_id = report_id
        self.lang = lang
        self.dismiss_no_sanction.label = i18n.t("reportbug.btn_dismiss", lang)[:80]
        self.refuse.label = i18n.t("reportbug.btn_refuse", lang)[:80]
        self.confirm.label = i18n.t("reportbug.btn_confirm_bug", lang)[:80]

    @discord.ui.button(
        label="Dismiss (not a bug)",
        style=discord.ButtonStyle.secondary,
        emoji="🔍",
        row=0,
    )
    async def dismiss_no_sanction(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """Déjà réglé, API, redémarrage, cas rare : pas de cooldown 7 jours."""
        lg = self.lang
        if not _is_owner(interaction.user.id):
            await interaction.response.send_message(i18n.t("reportbug.owner_only", lg), ephemeral=True)
            return
        key = f"dis:{self.report_id}"
        if key in _owner_lock:
            await interaction.response.send_message(i18n.t("reportbug.processing", lg), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        _owner_lock.add(key)
        try:
            ok, rep = br.dismiss_report_no_sanction(self.report_id, interaction.user.id)
            if not ok:
                await interaction.followup.send(
                    i18n.t("reportbug.report_gone", lg),
                    ephemeral=True,
                )
                return
            uid = int(rep.get("user_id") or 0)
            u = self.bot.get_user(uid) or await self.bot.fetch_user(uid)
            try:
                await u.send(
                    embed=discord.Embed(
                        title=i18n.t("reportbug.dismiss_title", lg),
                        description=i18n.t("reportbug.dismiss_body", lg),
                        color=discord.Color.blue(),
                    )
                )
            except discord.HTTPException:
                LOG.warning("impossible DM user %s dismiss report %s", uid, self.report_id)
            for child in self.children:
                child.disabled = True
            try:
                await interaction.message.edit(
                    content=i18n.t("reportbug.dismiss_edit", lg),
                    embed=interaction.message.embeds[0] if interaction.message.embeds else None,
                    view=self,
                )
            except Exception:
                pass
            await interaction.followup.send(i18n.t("reportbug.dismiss_followup", lg), ephemeral=True)
        finally:
            _owner_lock.discard(key)

    @discord.ui.button(label="Reject (7d cooldown)", style=discord.ButtonStyle.danger, emoji="✖️", row=1)
    async def refuse(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        lg = self.lang
        if not _is_owner(interaction.user.id):
            await interaction.response.send_message(i18n.t("reportbug.owner_only", lg), ephemeral=True)
            return
        key = f"ref:{self.report_id}"
        if key in _owner_lock:
            await interaction.response.send_message(i18n.t("reportbug.processing", lg), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        _owner_lock.add(key)
        try:
            ok, rep = br.refuse_report(self.report_id, interaction.user.id)
            if not ok:
                await interaction.followup.send(
                    i18n.t("reportbug.report_gone", lg),
                    ephemeral=True,
                )
                return
            uid = int(rep.get("user_id") or 0)
            u = self.bot.get_user(uid) or await self.bot.fetch_user(uid)
            try:
                await u.send(
                    embed=discord.Embed(
                        title=i18n.t("reportbug.refuse_title", lg),
                        description=i18n.t("reportbug.refuse_body", lg),
                        color=discord.Color.dark_red(),
                    )
                )
            except discord.HTTPException:
                LOG.warning("impossible DM user %s refuse report %s", uid, self.report_id)
            for child in self.children:
                child.disabled = True
            try:
                await interaction.message.edit(
                    content=i18n.t("reportbug.refuse_edit", lg),
                    embed=interaction.message.embeds[0] if interaction.message.embeds else None,
                    view=self,
                )
            except Exception:
                pass
            await interaction.followup.send(i18n.t("reportbug.refuse_followup", lg), ephemeral=True)
        finally:
            _owner_lock.discard(key)

    @discord.ui.button(label="Confirm bug", style=discord.ButtonStyle.success, emoji="✅", row=1)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        lg = self.lang
        if not _is_owner(interaction.user.id):
            await interaction.response.send_message(i18n.t("reportbug.owner_only", lg), ephemeral=True)
            return
        rep = br.get_report(self.report_id)
        if not rep or str(rep.get("status")) != "pending":
            await interaction.response.send_message(i18n.t("reportbug.pending_only", lg), ephemeral=True)
            return
        emb: discord.Embed | None = None
        if interaction.message and interaction.message.embeds:
            emb = interaction.message.embeds[0].copy()
            emb.add_field(
                name=i18n.t("reportbug.validation_field", lg),
                value=i18n.t("reportbug.validation_hint", lg),
                inline=False,
            )
        await interaction.response.edit_message(embed=emb, view=OwnerRewardView(self.bot, self.report_id, lg))


class OwnerRewardView(discord.ui.View):
    def __init__(self, bot: commands.Bot, report_id: int, lang: str) -> None:
        super().__init__(timeout=None)
        self.bot = bot
        self.report_id = report_id
        self.lang = lang
        self.report_type: str = "bug"
        self.severity: str | None = None
        self.bug_hard: bool | None = None
        self.select_type.placeholder = i18n.t("reportbug.type_placeholder", lang)[:150]
        self.select_severity.placeholder = i18n.t("reportbug.sev_placeholder", lang)[:150]
        self.select_hard.placeholder = i18n.t("reportbug.hard_placeholder", lang)[:150]
        self.apply_xp.label = i18n.t("reportbug.btn_apply_xp", lang)[:80]
        topts = self.select_type.options
        if len(topts) >= 2:
            topts[0].label = i18n.t("reportbug.type_bug", lang)[:100]
            topts[1].label = i18n.t("reportbug.type_translation", lang)[:100]
        opts = self.select_severity.options
        if len(opts) >= 3:
            opts[0].label = i18n.t("reportbug.sev_small", lang)[:100]
            opts[0].description = i18n.t("reportbug.sev_small_desc", lang)[:100]
            opts[1].label = i18n.t("reportbug.sev_med", lang)[:100]
            opts[1].description = i18n.t("reportbug.sev_med_desc", lang)[:100]
            opts[2].label = i18n.t("reportbug.sev_big", lang)[:100]
            opts[2].description = i18n.t("reportbug.sev_big_desc", lang)[:100]
        hopts = self.select_hard.options
        if len(hopts) >= 2:
            hopts[0].label = i18n.t("reportbug.hard_no", lang)[:100]
            hopts[1].label = i18n.t("reportbug.hard_yes", lang)[:100]

    @discord.ui.select(
        placeholder="—",
        options=[
            discord.SelectOption(label="—", value="bug"),
            discord.SelectOption(label="—", value="translation"),
        ],
        row=0,
    )
    async def select_type(self, interaction: discord.Interaction, select: discord.ui.Select) -> None:
        lg = self.lang
        if not _is_owner(interaction.user.id):
            await interaction.response.send_message(i18n.t("reportbug.owner_only_short", lg), ephemeral=True)
            return
        self.report_type = select.values[0]
        await interaction.response.defer()

    @discord.ui.select(
        placeholder="—",
        options=[
            discord.SelectOption(label="—", value="petit", description="—"),
            discord.SelectOption(label="—", value="moyen", description="—"),
            discord.SelectOption(label="—", value="gros", description="—"),
        ],
        row=1,
    )
    async def select_severity(self, interaction: discord.Interaction, select: discord.ui.Select) -> None:
        lg = self.lang
        if not _is_owner(interaction.user.id):
            await interaction.response.send_message(i18n.t("reportbug.owner_only_short", lg), ephemeral=True)
            return
        self.severity = select.values[0]
        await interaction.response.defer()

    @discord.ui.select(
        placeholder="—",
        options=[
            discord.SelectOption(label="—", value="0"),
            discord.SelectOption(label="—", value="1"),
        ],
        row=2,
    )
    async def select_hard(self, interaction: discord.Interaction, select: discord.ui.Select) -> None:
        lg = self.lang
        if not _is_owner(interaction.user.id):
            await interaction.response.send_message(i18n.t("reportbug.owner_only_short", lg), ephemeral=True)
            return
        self.bug_hard = select.values[0] == "1"
        await interaction.response.defer()

    @discord.ui.button(label="Apply reward", style=discord.ButtonStyle.primary, row=3)
    async def apply_xp(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        lg = self.lang
        if not _is_owner(interaction.user.id):
            await interaction.response.send_message(i18n.t("reportbug.owner_only_short", lg), ephemeral=True)
            return
        if self.severity is None or self.bug_hard is None:
            await interaction.response.send_message(
                i18n.t("reportbug.pick_sev_hard", lg),
                ephemeral=True,
            )
            return
        key = f"ok:{self.report_id}"
        if key in _owner_lock:
            await interaction.response.send_message(i18n.t("reportbug.processing", lg), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        _owner_lock.add(key)
        try:
            ok, rep, xp = br.confirm_report(
                self.report_id,
                interaction.user.id,
                self.severity,
                self.bug_hard,
                self.report_type,
            )
            if not ok or not rep:
                await interaction.followup.send(i18n.t("reportbug.confirm_fail", lg), ephemeral=True)
                return
            uid = int(rep.get("user_id") or 0)
            await core.add_xp(self.bot, None, uid, xp, announce=False)
            u = self.bot.get_user(uid) or await self.bot.fetch_user(uid)
            try:
                sev = str(rep.get("severity") or "")
                sev_map = {
                    "petit": i18n.t("reportbug.sev_label_petit", lg),
                    "moyen": i18n.t("reportbug.sev_label_moyen", lg),
                    "gros": i18n.t("reportbug.sev_label_gros", lg),
                }
                hard = bool(rep.get("hard_to_find"))
                base = xp - (br.HARD_BONUS_XP if hard else 0)
                hard_txt = (
                    i18n.t("reportbug.confirm_user_hard_yes", lg)
                    if hard
                    else i18n.t("reportbug.confirm_user_hard_no", lg)
                )
                lines = [
                    i18n.t(
                        "reportbug.confirm_user_line1_translation" if self.report_type == "translation" else "reportbug.confirm_user_line1",
                        lg,
                    ),
                    "",
                    i18n.t("reportbug.confirm_user_sev", lg, label=sev_map.get(sev, sev)),
                    i18n.t("reportbug.confirm_user_hard", lg, hard=hard_txt),
                    i18n.t("reportbug.confirm_user_total", lg, xp=xp, base=base),
                    "",
                    i18n.t("reportbug.confirm_user_thanks", lg),
                ]
                await u.send(
                    embed=discord.Embed(
                        title=i18n.t(
                            "reportbug.confirm_user_title_translation" if self.report_type == "translation" else "reportbug.confirm_user_title",
                            lg,
                        ),
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
                    content=i18n.t(
                        "reportbug.confirm_edit_translation" if self.report_type == "translation" else "reportbug.confirm_edit",
                        lg,
                        xp=xp,
                        uid=uid,
                    ),
                    embed=interaction.message.embeds[0] if interaction.message.embeds else None,
                    view=self,
                )
            except Exception:
                pass
            await interaction.followup.send(i18n.t("reportbug.confirm_followup", lg, xp=xp), ephemeral=True)
        finally:
            _owner_lock.discard(key)


class IntroView(discord.ui.View):
    def __init__(self, bot: commands.Bot, lang: str) -> None:
        super().__init__(timeout=600)
        self.bot = bot
        self.lang = lang
        self.open_modal.label = i18n.t("reportbug.btn_compose", lang)[:80]

    @discord.ui.button(label="Write report", style=discord.ButtonStyle.primary, emoji="📝")
    async def open_modal(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.send_modal(BugReportModal(self.bot, self.lang))


class ReportBugCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    blacklist = app_commands.Group(
        name="blacklist",
        description=ui_str("slash.reportbug_blacklist_group"),
        extras={"owner_only": True},
    )

    @app_commands.command(
        name="reportbug",
        description=ui_str("slash.reportbug"),
    )
    async def reportbug(self, interaction: discord.Interaction) -> None:
        uid = interaction.user.id
        lg = i18n.interaction_lang(interaction)
        _cleanup_drafts()
        ok, reason = br.can_user_submit_bug(uid)
        if not ok:
            if reason == "blacklist":
                await interaction.response.send_message(_msg_blacklist(lg), ephemeral=bool(interaction.guild))
                return
            if reason == "reject_cooldown":
                await interaction.response.send_message(
                    _reject_cooldown_message(uid, lg),
                    ephemeral=bool(interaction.guild),
                )
                return
            if reason == "daily_limit":
                await interaction.response.send_message(_daily_message(lg), ephemeral=bool(interaction.guild))
                return
        embed = discord.Embed(
            title=i18n.t("reportbug.intro_title", lg),
            description=i18n.t("reportbug.intro_body", lg),
            color=discord.Color.blue(),
        )
        embed.set_footer(text=i18n.t("reportbug.intro_footer", lg))
        in_guild = interaction.guild is not None
        if not in_guild:
            await interaction.response.send_message(embed=embed, view=IntroView(self.bot, lg))
            return
        try:
            await interaction.user.send(embed=embed, view=IntroView(self.bot, lg))
        except discord.HTTPException:
            await interaction.response.send_message(
                i18n.t("reportbug.dm_blocked", lg),
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            i18n.t("reportbug.dm_sent_hint", lg),
            ephemeral=True,
        )

    @blacklist.command(name="add", description=ui_str("slash.reportbug_bl_add"))
    @app_commands.describe(user_id=ui_str("slash.reportbug_bl_user_param"))
    async def blacklist_add(self, interaction: discord.Interaction, user_id: str) -> None:
        lg = i18n.interaction_lang(interaction)
        if not _is_owner(interaction.user.id):
            await interaction.response.send_message(i18n.t("reportbug.bl_owner", lg), ephemeral=True)
            return
        raw = (user_id or "").strip()
        if not raw.isdigit():
            await interaction.response.send_message(i18n.t("reportbug.bl_id_bad", lg), ephemeral=True)
            return
        uid = int(raw)
        if uid == interaction.user.id:
            await interaction.response.send_message(i18n.t("reportbug.bl_self", lg), ephemeral=True)
            return
        if br.blacklist_add(uid):
            await interaction.response.send_message(i18n.t("reportbug.bl_added", lg, uid=uid), ephemeral=True)
        else:
            await interaction.response.send_message(i18n.t("reportbug.bl_already", lg, uid=uid), ephemeral=True)

    @blacklist.command(name="remove", description=ui_str("slash.reportbug_bl_remove"))
    @app_commands.describe(user_id=ui_str("slash.reportbug_bl_user_param_short"))
    async def blacklist_remove(self, interaction: discord.Interaction, user_id: str) -> None:
        lg = i18n.interaction_lang(interaction)
        if not _is_owner(interaction.user.id):
            await interaction.response.send_message(i18n.t("reportbug.bl_owner", lg), ephemeral=True)
            return
        raw = (user_id or "").strip()
        if not raw.isdigit():
            await interaction.response.send_message(i18n.t("reportbug.bl_id_bad_short", lg), ephemeral=True)
            return
        uid = int(raw)
        if br.blacklist_remove(uid):
            await interaction.response.send_message(i18n.t("reportbug.bl_removed", lg, uid=uid), ephemeral=True)
        else:
            await interaction.response.send_message(i18n.t("reportbug.bl_not_in", lg, uid=uid), ephemeral=True)

    @blacklist.command(name="list", description=ui_str("slash.reportbug_bl_list"))
    async def blacklist_list(self, interaction: discord.Interaction) -> None:
        lg = i18n.interaction_lang(interaction)
        if not _is_owner(interaction.user.id):
            await interaction.response.send_message(i18n.t("reportbug.bl_owner", lg), ephemeral=True)
            return
        bl = br.get_blacklist()
        if not bl:
            await interaction.response.send_message(i18n.t("reportbug.bl_empty", lg), ephemeral=True)
            return
        chunk = ", ".join(f"`{x}`" for x in bl[:50])
        more = f" (+{len(bl) - 50} autres)" if len(bl) > 50 else ""
        await interaction.response.send_message(
            i18n.t("reportbug.bl_list", lg, chunk=chunk, more=more),
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ReportBugCog(bot))
