# cogs/botinfo.py
from __future__ import annotations
import os
import platform
from datetime import datetime, timezone
import discord
from discord import app_commands
from discord.ext import commands

from modules import core, i18n
from modules.app_cmd_locale import ui_str


def _format_uptime(delta_seconds: float) -> str:
    s = int(delta_seconds)
    d, s = divmod(s, 86400)
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    parts = []
    if d:
        parts.append(f"{d}j")
    if h:
        parts.append(f"{h}h")
    if m:
        parts.append(f"{m}m")
    parts.append(f"{s}s")
    return " ".join(parts)


class BotInfo(commands.Cog):
    """Commande /botinfo avec version, latence, serveurs, uptime, etc."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        if not hasattr(self.bot, "_launch_time"):
            self.bot._launch_time = datetime.now(timezone.utc)

    @app_commands.command(name="botinfo", description=ui_str("slash.botinfo"))
    async def botinfo(self, interaction: discord.Interaction):
        lg = i18n.guild_lang(interaction.guild)
        version = os.getenv("BOT_VERSION")
        if not version:
            version = getattr(core, "__version__", None)
        version = version or "dev"

        guilds = len(self.bot.guilds)
        members = sum((g.member_count or 0) for g in self.bot.guilds)
        ping_ms = round(self.bot.latency * 1000)
        launch = getattr(self.bot, "_launch_time", datetime.now(timezone.utc))
        uptime = _format_uptime((datetime.now(timezone.utc) - launch).total_seconds())

        embed = discord.Embed(
            title=i18n.t("botinfo.embed_title", lg),
            description=i18n.t("botinfo.embed_desc", lg),
            color=discord.Color.blurple(),
        )
        embed.add_field(name=i18n.t("botinfo.field_version", lg), value=f"`v{version}`", inline=True)
        embed.add_field(name=i18n.t("botinfo.field_latency", lg), value=f"`{ping_ms} ms`", inline=True)
        embed.add_field(name=i18n.t("botinfo.field_uptime", lg), value=f"`{uptime}`", inline=True)

        embed.add_field(name=i18n.t("botinfo.field_guilds", lg), value=f"`{guilds}`", inline=True)
        embed.add_field(name=i18n.t("botinfo.field_members", lg), value=f"`{members}`", inline=True)
        embed.add_field(name=i18n.t("botinfo.field_python", lg), value=f"`{platform.python_version()}`", inline=True)

        anilist_ok = getattr(self.bot, "anilist_online", None)
        if anilist_ok is not None:
            av = i18n.t("botinfo.field_anilist_ok", lg) if anilist_ok else i18n.t("botinfo.field_anilist_bad", lg)
            embed.add_field(
                name=i18n.t("botinfo.field_anilist", lg),
                value=f"`{av}`",
                inline=True,
            )

        embed.add_field(
            name=i18n.t("botinfo.field_slash", lg),
            value=i18n.t("botinfo.field_slash_val", lg),
            inline=False,
        )

        embed.add_field(
            name=i18n.t("botinfo.field_vote", lg),
            value=i18n.t("botinfo.field_vote_val", lg),
            inline=False,
        )

        embed.add_field(
            name=i18n.t("botinfo.field_bug", lg),
            value=i18n.t("botinfo.field_bug_val", lg),
            inline=False,
        )

        try:
            uid = interaction.user.id
            linked = core.get_linked_username(uid)
            if linked:
                embed.add_field(
                    name=i18n.t("botinfo.field_al_linked", lg),
                    value=i18n.t("botinfo.field_al_val_linked", lg, name=linked),
                    inline=False,
                )
            else:
                embed.add_field(
                    name=i18n.t("botinfo.field_al_linked", lg),
                    value=i18n.t("botinfo.field_al_val_unlinked", lg),
                    inline=False,
                )
        except Exception:
            pass

        embed.set_footer(text=i18n.t("botinfo.footer", lg))
        try:
            if self.bot.user and self.bot.user.display_avatar:
                embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        except Exception:
            pass

        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(BotInfo(bot))
