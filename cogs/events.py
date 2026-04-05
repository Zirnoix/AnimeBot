# cogs/onboarding.py
from __future__ import annotations

import discord
from discord.ext import commands
from discord import app_commands

from modules import i18n
from modules import locale_store
from modules.app_cmd_locale import ui_str

SUPPORT_DISCORD = "@zirnoix"
SUPPORT_ID = "180389173985804288"


def make_intro_embed(guild: discord.Guild | None, lang: str) -> discord.Embed:
    em = discord.Embed(
        title=i18n.t("intro.title", lang),
        description=i18n.t("intro.lead", lang),
        color=discord.Color.blurple(),
    )
    if guild:
        em.set_footer(text=i18n.t("intro.footer_server", lang, name=guild.name))
    em.add_field(
        name=i18n.t("intro.field_config", lang),
        value=i18n.t("intro.admin_value", lang),
        inline=False,
    )
    em.add_field(
        name=i18n.t("intro.field_players", lang),
        value=i18n.t("intro.minigames_value", lang),
        inline=False,
    )
    em.add_field(
        name=i18n.t("intro.field_tutorial", lang),
        value=i18n.t("intro.extra_tips", lang),
        inline=False,
    )
    em.add_field(
        name=i18n.t("intro.field_support", lang),
        value=i18n.t("intro.contact", lang, support=SUPPORT_DISCORD, sid=SUPPORT_ID),
        inline=False,
    )
    return em


class Onboarding(commands.Cog):
    """Envoie un MP concis au propriétaire du serveur + /guide (DM)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---- DM à l'owner quand le bot rejoint une guilde (1 message unique) ----
    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        try:
            owner = guild.owner
            if not owner:
                return
            lg = locale_store.get_guild_lang(guild.id)
            try:
                await owner.send(embed=make_intro_embed(guild, lg))
            except discord.Forbidden:
                # Si l'owner bloque ses MP : on poste un message minimaliste dans un salon autorisé
                ch = guild.system_channel or next(
                    (c for c in guild.text_channels if c.permissions_for(guild.me).send_messages),  # type: ignore
                    None,
                )
                if ch:
                    await ch.send(
                        i18n.t(
                            "intro.guild_join_blocked",
                            lg,
                            mention=owner.mention,
                        )
                    )
        except Exception:
            # ne pas casser le flux de démarrage si un DM échoue
            pass

    # ---- /guide : détaillé, pensé pour **MP**. Utilisable depuis un serveur -> redirige en MP. ----
    @app_commands.command(
        name="guide",
        description=ui_str("slash.guide"),
    )
    async def guide(self, interaction: discord.Interaction):
        try:
            lg = i18n.interaction_lang(interaction)
            # Si lancé depuis un serveur, prévenir en ephemeral puis envoyer en MP
            if interaction.guild:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        i18n.t("guide.send_dm", lg),
                        ephemeral=True,
                    )
                else:
                    await interaction.followup.send(
                        i18n.t("guide.send_dm", lg),
                        ephemeral=True,
                    )
            else:
                # En MP, les réponses « éphémères » ne sont pas supportées comme en salon.
                await interaction.response.defer(ephemeral=False)

            user = interaction.user

            e_xp = discord.Embed(
                title=i18n.t("guide.embed_xp_title", lg),
                description=i18n.t("guide.embed_xp_desc", lg),
                color=discord.Color.orange(),
            )

            e_mini = discord.Embed(
                title=i18n.t("guide.embed_mini_title", lg),
                description=i18n.t("guide.embed_mini_desc", lg),
                color=discord.Color.purple(),
            )

            e_anilist = discord.Embed(
                title=i18n.t("guide.embed_anilist_title", lg),
                description=i18n.t("guide.embed_anilist_desc", lg),
                color=discord.Color.green(),
            )

            e_reminders = discord.Embed(
                title=i18n.t("guide.embed_reminders_title", lg),
                description=i18n.t("guide.embed_reminders_desc", lg),
                color=discord.Color.gold(),
            )

            e_misc = discord.Embed(
                title=i18n.t("guide.embed_misc_title", lg),
                description=i18n.t("guide.embed_misc_desc", lg),
                color=discord.Color.teal(),
            )

            e_support = discord.Embed(
                title=i18n.t("guide.embed_support_title", lg),
                description=i18n.t(
                    "guide.embed_support_desc",
                    lg,
                    support=SUPPORT_DISCORD,
                    sid=SUPPORT_ID,
                ),
                color=discord.Color.dark_teal(),
            )

            await user.send(embeds=[e_xp, e_mini, e_anilist, e_reminders, e_misc, e_support])

            if not interaction.guild:
                await interaction.followup.send(
                    i18n.t("guide.sent_ok", lg),
                    ephemeral=False,
                )

        except discord.Forbidden:
            lg = i18n.interaction_lang(interaction)
            if interaction.response.is_done():
                await interaction.followup.send(
                    i18n.t("guide.err_dm_blocked", lg),
                    ephemeral=bool(interaction.guild),
                )
            else:
                await interaction.response.send_message(
                    i18n.t("guide.err_dm_blocked", lg),
                    ephemeral=bool(interaction.guild),
                )
        except Exception as e:
            lg = i18n.interaction_lang(interaction)
            err = i18n.t("guide.err_generic", lg, err=type(e).__name__)
            if interaction.response.is_done():
                await interaction.followup.send(err, ephemeral=bool(interaction.guild))
            else:
                await interaction.response.send_message(err, ephemeral=bool(interaction.guild))

    @app_commands.command(
        name="guide_admin",
        description=ui_str("slash.guide_admin"),
    )
    @app_commands.default_permissions(administrator=True)
    async def guide_admin(self, interaction: discord.Interaction) -> None:
        lg = i18n.interaction_lang(interaction)
        if not interaction.guild:
            await interaction.response.send_message(
                i18n.t("guide_admin.need_guild", lg),
                ephemeral=True,
            )
            return
        try:
            await interaction.response.send_message(
                i18n.t("guide_admin.send_dm", lg),
                ephemeral=True,
            )
            user = interaction.user

            e_srv = discord.Embed(
                title=i18n.t("guide_admin.embed_srv_title", lg),
                description=i18n.t("guide_admin.embed_srv_desc", lg),
                color=discord.Color.blurple(),
            )
            e_note = discord.Embed(
                title=i18n.t("guide_admin.embed_note_title", lg),
                description=i18n.t("guide_admin.embed_note_desc", lg),
                color=discord.Color.dark_teal(),
            )
            e_sup = discord.Embed(
                title=i18n.t("guide_admin.embed_support_title", lg),
                description=i18n.t(
                    "guide_admin.embed_support_desc",
                    lg,
                    support=SUPPORT_DISCORD,
                    sid=SUPPORT_ID,
                ),
                color=discord.Color.dark_teal(),
            )
            await user.send(embeds=[e_srv, e_note, e_sup])
        except discord.Forbidden:
            lg = i18n.interaction_lang(interaction)
            if interaction.response.is_done():
                await interaction.followup.send(
                    i18n.t("guide_admin.err_dm_blocked", lg),
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    i18n.t("guide_admin.err_dm_blocked_short", lg),
                    ephemeral=True,
                )
        except Exception as e:
            lg = i18n.interaction_lang(interaction)
            err = i18n.t("guide.err_generic", lg, err=type(e).__name__)
            if interaction.response.is_done():
                await interaction.followup.send(err, ephemeral=True)
            else:
                await interaction.response.send_message(err, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Onboarding(bot))
