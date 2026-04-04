# cogs/guild_locale.py — langue serveur (FR/EN), message d'accueil + /language
from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from modules import core, i18n, locale_store
from modules.app_cmd_locale import ui_str

LOG = logging.getLogger(__name__)


def _welcome_embed(guild: discord.Guild) -> discord.Embed:
    lang = locale_store.get_guild_lang(guild.id)
    prefix = "/"
    em = discord.Embed(
        title=i18n.t("welcome.title", lang),
        description=i18n.t("welcome.description", lang),
        color=discord.Color.blurple(),
    )
    em.add_field(
        name=i18n.t("welcome.field_what", lang),
        value=i18n.t("welcome.field_what_value", lang),
        inline=False,
    )
    em.add_field(
        name=i18n.t("welcome.field_help", lang),
        value=i18n.t("welcome.field_help_value", lang, prefix=prefix),
        inline=False,
    )
    em.set_footer(text=i18n.t("welcome.footer", lang))
    return em


class WelcomeLanguageSelect(discord.ui.Select):
    def __init__(self, guild_id: int, lang: str) -> None:
        self.guild_id = guild_id
        super().__init__(
            placeholder=i18n.t("welcome.select_placeholder", lang)[:150],
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(
                    label=i18n.t("welcome.select_fr", lang)[:100],
                    value="fr",
                    emoji="🇫🇷",
                ),
                discord.SelectOption(
                    label=i18n.t("welcome.select_en", lang)[:100],
                    value="en",
                    emoji="🇬🇧",
                ),
            ],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if not interaction.guild or interaction.guild.id != self.guild_id:
            await interaction.response.send_message("❌", ephemeral=True)
            return
        if not interaction.user.guild_permissions.administrator:
            gl = locale_store.get_guild_lang(interaction.guild.id)
            await interaction.response.send_message(
                i18n.t("welcome.select_need_perm", gl),
                ephemeral=True,
            )
            return

        choice = self.values[0]
        prev = locale_store.get_guild_lang(interaction.guild.id)
        locale_store.set_guild_lang(interaction.guild.id, choice)

        if choice == "fr":
            msg = (
                i18n.t("welcome.already_fr", "fr")
                if prev == "fr"
                else i18n.t("welcome.set_fr_confirm", "fr")
            )
        else:
            msg = (
                i18n.t("welcome.already_en", "en")
                if prev == "en"
                else i18n.t("welcome.set_en_confirm", "en")
            )

        await interaction.response.send_message(msg, ephemeral=True)


class WelcomeLanguageView(discord.ui.View):
    def __init__(self, guild_id: int, lang: str) -> None:
        super().__init__(timeout=3600)
        self.add_item(WelcomeLanguageSelect(guild_id, lang))


class GuildLocale(commands.Cog):
    """Langue par serveur + accueil à l'invitation."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild) -> None:
        await self._send_welcome(guild)

    async def _send_welcome(self, guild: discord.Guild) -> None:
        try:
            ch = guild.system_channel
            if ch is None or not ch.permissions_for(guild.me).send_messages:
                ch = next(
                    (
                        c
                        for c in guild.text_channels
                        if c.permissions_for(guild.me).send_messages
                        and c.permissions_for(guild.me).embed_links
                    ),
                    None,
                )
            if not ch:
                return
            lang = locale_store.get_guild_lang(guild.id)
            view = WelcomeLanguageView(guild.id, lang)
            await ch.send(embed=_welcome_embed(guild), view=view)
        except Exception as e:
            LOG.warning("Welcome message failed for guild %s: %s", guild.id, e)

    @commands.hybrid_command(
        name="language",
        description=ui_str("language.cmd_description"),
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(lang=ui_str("language.param_description"))
    @app_commands.choices(
        lang=[
            app_commands.Choice(name=ui_str("slash.choice_lang_fr"), value="fr"),
            app_commands.Choice(name=ui_str("slash.choice_lang_en"), value="en"),
        ]
    )
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def language_cmd(self, ctx: commands.Context, lang: str) -> None:
        if ctx.guild is None:
            return
        await core.maybe_defer_hybrid(ctx, ephemeral=bool(ctx.interaction))
        locale_store.set_guild_lang(ctx.guild.id, lang)
        lbl = i18n.t(f"language.lang_name_{lang}", lang)
        msg = i18n.t("language.success", lang, label=lbl)
        if ctx.interaction:
            await ctx.send(msg, ephemeral=True)
        else:
            await ctx.send(msg)

    @language_cmd.error
    async def language_cmd_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        if isinstance(error, commands.MissingPermissions):
            lg = i18n.guild_lang(ctx.guild)
            if ctx.interaction and not ctx.interaction.response.is_done():
                await ctx.interaction.response.send_message(
                    i18n.t("language.need_administrator", lg),
                    ephemeral=True,
                )
            elif ctx.interaction:
                await ctx.interaction.followup.send(
                    i18n.t("language.need_administrator", lg),
                    ephemeral=True,
                )
            else:
                await ctx.send(i18n.t("language.need_administrator", lg))
            return
        if isinstance(error, commands.NoPrivateMessage):
            if ctx.interaction and not ctx.interaction.response.is_done():
                await ctx.interaction.response.send_message(
                    i18n.t("language.need_guild", "fr"),
                    ephemeral=True,
                )
            return


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(GuildLocale(bot))
