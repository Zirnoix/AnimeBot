"""
Panneau unique /owner pour le propriétaire du bot (OWNER_ID).
"""
from __future__ import annotations

import os

import discord
from discord import app_commands
from discord.ext import commands

from modules import i18n, owner_actions
from modules.app_cmd_locale import ui_str

LOG = __import__("logging").getLogger(__name__)


def _is_owner_id(user_id: int) -> bool:
    raw = os.getenv("OWNER_ID", "").strip()
    return raw.isdigit() and int(raw) == int(user_id)


class OwnerActionSelect(discord.ui.Select):
    def __init__(self, bot: commands.Bot, lang: str) -> None:
        self.lang = lang
        opts: list[discord.SelectOption] = []
        for val, label, desc in owner_actions.ACTIONS:
            opts.append(
                discord.SelectOption(
                    label=label[:100],
                    description=(desc[:100] if desc else None),
                    value=val,
                )
            )
        super().__init__(
            placeholder=i18n.t("owner.select_placeholder", lang)[:150],
            min_values=1,
            max_values=1,
            options=opts[:25],
        )
        self.bot = bot

    async def callback(self, interaction: discord.Interaction) -> None:
        lg = i18n.guild_lang(interaction.guild)
        if not _is_owner_id(interaction.user.id):
            await interaction.response.send_message(i18n.t("owner.denied", lg), ephemeral=True)
            return
        key = self.values[0]
        runner = owner_actions.RUNNERS.get(key)
        if not runner:
            await interaction.response.send_message(i18n.t("owner.unknown_action", lg), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        try:
            await runner(self.bot, interaction)
        except Exception as e:
            LOG.exception("owner action %s: %s", key, e)
            try:
                await interaction.followup.send(
                    i18n.t("owner.err", lg, err=f"{type(e).__name__}: {e}")[:2000],
                    ephemeral=True,
                )
            except Exception:
                pass


class OwnerHubView(discord.ui.View):
    def __init__(self, bot: commands.Bot, lang: str) -> None:
        super().__init__(timeout=600)
        self.add_item(OwnerActionSelect(bot, lang))


class OwnerHub(commands.Cog):
    """Regroupe les outils propriétaire sous /owner."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.command(name="setavatar", hidden=True)
    @commands.is_owner()
    async def set_avatar_prefix(self, ctx: commands.Context) -> None:
        """Préfixe uniquement : !setavatar + image jointe (pas de slash)."""
        lg = i18n.ctx_lang(ctx)
        if not ctx.message.attachments:
            await ctx.send(i18n.t("owner.setavatar_need", lg))
            return
        try:
            avatar_bytes = await ctx.message.attachments[0].read()
            await self.bot.user.edit(avatar=avatar_bytes)
            await ctx.send(i18n.t("owner.setavatar_ok", lg))
        except Exception as e:
            await ctx.send(i18n.t("owner.err", lg, err=str(e))[:2000])

    @app_commands.command(
        name="owner",
        description=ui_str("owner.cmd_desc"),
    )
    async def owner_panel(self, interaction: discord.Interaction) -> None:
        lg = i18n.guild_lang(interaction.guild)
        if not _is_owner_id(interaction.user.id):
            await interaction.response.send_message(
                i18n.t("owner.panel_denied", lg),
                ephemeral=True,
            )
            return
        lines = [f"**{label}** — {desc}" for _, label, desc in owner_actions.ACTIONS]
        embed = discord.Embed(
            title=i18n.t("owner.panel_title", lg),
            description=(i18n.t("owner.panel_desc", lg) + "\n".join(lines)[:4000]),
            color=discord.Color.dark_teal(),
        )
        embed.set_footer(text=i18n.t("owner.panel_footer", lg))
        await interaction.response.send_message(
            embed=embed,
            view=OwnerHubView(self.bot, lg),
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(OwnerHub(bot))
