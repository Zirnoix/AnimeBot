# cogs/help.py
from __future__ import annotations
from typing import Optional, Dict, List, Tuple
import inspect
import re

import discord
from discord.ext import commands
from discord import app_commands

from modules import i18n

PER_PAGE = 24
OWNER_HINTS = ("owner", "admin", "dev", "maintenance")
SUMMARY_MAX_CHARS = 140

# ===== Sections curatées (clé i18n help.section.* ou help.section_admin.*) =====
CURATED_SECTIONS: List[Tuple[str, List[str]]] = [
    ("episodes", [
        "next", "planning", "decouverte", "monnext", "monplanning",
    ]),
    ("minigames", [
        "animequiz", "animequizmulti", "duel",
        "guessyear", "guessepisodes", "guessgenre", "guesscharacter",
        "guesswho", "chainquiz",
        "guessop", "guessopchain",
        "higherlower", "minijeux",
        "raid", "raid statut",
    ]),
    ("link", [
        "linkanilist", "verifyanilist", "unlink",
    ]),
    ("stats", [
        "mycard", "profile", "animefav", "reportbug", "mystats", "mybadges", "duelstats",
        "quiztop", "animetop", "quizlevels", "myrank", "stats",
    ]),
    ("tracker", [
        "track", "track add", "track list", "track remove", "track clear",
    ]),
    ("utils", [
        "botinfo", "vote", "ping", "recap", "setalert", "source", "uptime",
    ]),
]

ADMIN_HELP_SECTIONS: List[Tuple[str, List[str]]] = [
    ("admin_config", [
        "guide_admin", "setchannel", "setlevelupchannel", "clearlevelupchannel",
    ]),
    ("airings_list", [
        "airings", "airings all", "airings add", "airings remove", "airings list", "airings clear",
    ]),
    ("raid_config", [
        "raidconfig", "raidstart", "raidalerttest",
    ]),
]


def _desc(lang: str, raw: str) -> str:
    raw_l = raw.lower().strip()
    k1 = raw_l.replace(" ", "_")
    leaf = raw_l.split()[-1]
    for k in (k1, leaf):
        v = i18n.value(f"help.desc.{k}", lang)
        if isinstance(v, str) and v.strip():
            return v
    return "—"

# ===== Utils =====
def _is_ownerish_name(name: str) -> bool:
    low = (name or "").lower()
    return any(h in low for h in OWNER_HINTS)

def _compact_one_line(text: str, *, max_chars: int = SUMMARY_MAX_CHARS) -> str:
    if not text:
        return "—"
    t = str(text)
    markers = [
        "\nArgs:", "\nArguments:", "\nParameters:", "\nParamètres:",
        "\nReturns:", "\nReturn:", "\nNote:", "\nNotes:", "\nRemarques:",
        "\nExample:", "\nExamples:", "\nExemple:", "\nExemples:",
        "\nUsage:", "\nUsages:"
    ]
    cut = len(t)
    for m in markers:
        i = t.find(m)
        if i != -1:
            cut = min(cut, i)
    t = t[:cut]
    t = re.sub(r"```.*?```", "", t, flags=re.S)
    t = re.sub(r"`([^`]*)`", r"\1", t)
    t = t.replace("•", "-").replace("—", "-")
    lines = [ln.strip() for ln in t.splitlines() if ln.strip()]
    t = lines[0] if lines else ""
    if len(t) > max_chars:
        for sep in [". ", "! ", "? "]:
            j = t.find(sep)
            if 0 < j <= max_chars:
                t = t[:j+1]; break
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) > max_chars:
        t = t[:max_chars-1].rstrip() + "…"
    return t or "—"

def _split_fields(fields: List[Tuple[str, str]], per_page: int = PER_PAGE) -> List[List[Tuple[str,str]]]:
    chunks, cur = [], []
    for f in fields:
        cur.append(f)
        if len(cur) >= per_page:
            chunks.append(cur); cur = []
    if cur: chunks.append(cur)
    return chunks

def _normalize_query(q: str) -> str:
    return re.sub(r"\s+", " ", (q or "").strip().lstrip("/!").lower())

# ===== inventaire SLASH =====
def _all_slash_commands(bot: commands.Bot) -> Dict[str, app_commands.Command]:
    out: Dict[str, app_commands.Command] = {}
    try:
        for c in bot.tree.get_commands():  # type: ignore[attr-defined]
            if isinstance(c, app_commands.Command):
                out[c.name.lower()] = c
            elif isinstance(c, app_commands.Group):
                # indexer /groupe et /groupe sous
                out[c.name.lower()] = c  # utile pour la fiche /airings
                for sc in c.commands:
                    out[f"{c.name.lower()} {sc.name.lower()}"] = sc
    except Exception:
        pass
    return out

# ===== Autocomplete /help <commande> : SLASH ONLY =====
async def _ac_help_command(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    bot = interaction.client  # type: ignore
    cur = _normalize_query(current)

    pool: List[Tuple[str, str]] = []
    try:
        for full in _all_slash_commands(bot).keys():
            pool.append((f"/{full}", full))
    except Exception:
        pass

    seen: set[str] = set()
    out: List[app_commands.Choice[str]] = []

    def match(v: str) -> bool:
        if not cur:
            return True
        v = v.lower()
        return v.startswith(cur) or cur in v

    for disp, value in pool:
        key = _normalize_query(value)
        if key in seen:
            continue
        if match(key):
            out.append(app_commands.Choice(name=disp[:100], value=value))
            seen.add(key)
        if len(out) >= 20:
            break

    if not out:
        for disp, value in pool[:10]:
            key = _normalize_query(value)
            if key in seen:
                continue
            out.append(app_commands.Choice(name=disp[:100], value=value))
            if len(out) >= 10:
                break
    return out

# ===== Vues (navigation) =====
class HelpNavigator(discord.ui.View):
    def __init__(
        self,
        pages: List[discord.Embed],
        labels: List[str],
        *,
        timeout: float = 300.0,
        help_cmd: str = "help",
        lang: str = "fr",
    ):
        super().__init__(timeout=timeout)
        self.pages = pages
        self.labels = labels
        self.index = 0
        self.help_cmd = help_cmd
        self.lang = lang
        self.jump_select.placeholder = i18n.t("help.ui.placeholder_jump", lang)[:150]
        self.close_button.label = i18n.t("help.ui.btn_close", lang)[:80]
        options = [discord.SelectOption(label=lbl, value=str(i)) for i, lbl in enumerate(self.labels[:25])]
        self.jump_select.options = options
        if len(self.pages) <= 1:
            self.prev_button.disabled = True
            self.next_button.disabled = True
            self.jump_select.disabled = True

    @discord.ui.button(emoji="◀️", style=discord.ButtonStyle.secondary)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.index = (self.index - 1) % len(self.pages)
        await interaction.response.edit_message(embed=self._with_footer(self.pages[self.index]), view=self)

    @discord.ui.button(emoji="▶️", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.index = (self.index + 1) % len(self.pages)
        await interaction.response.edit_message(embed=self._with_footer(self.pages[self.index]), view=self)

    @discord.ui.select(placeholder="Aller à…")
    async def jump_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        try:
            self.index = int(select.values[0])
        except Exception:
            self.index = 0
        await interaction.response.edit_message(embed=self._with_footer(self.pages[self.index]), view=self)

    @discord.ui.button(label="Fermer", style=discord.ButtonStyle.danger)
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)

    def _with_footer(self, em: discord.Embed) -> discord.Embed:
        em = em.copy()
        em.set_footer(text=i18n.t(
            "help.ui.footer_page", self.lang,
            cur=self.index + 1, total=len(self.pages), cmd=self.help_cmd,
        ))
        return em


class CoreHelpView(discord.ui.View):
    def __init__(self, build_curated_pages_cb, *, ephemeral: bool, help_cmd: str = "help", lang: str = "fr"):
        super().__init__(timeout=180.0)
        self.build_curated_pages_cb = build_curated_pages_cb
        self.ephemeral = ephemeral
        self.help_cmd = help_cmd
        self.lang = lang
        self.show_all_dm.label = i18n.t("help.ui.btn_all_dm", lang)[:80]
        self.close_button.label = i18n.t("help.ui.btn_close", lang)[:80]

    @discord.ui.button(label="Voir tout (MP)", style=discord.ButtonStyle.primary)
    async def show_all_dm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        try:
            pages, labels = self.build_curated_pages_cb()
            nav = HelpNavigator(pages, labels, help_cmd=self.help_cmd, lang=self.lang)
            first = nav._with_footer(pages[0])
            await interaction.user.send(embed=first, view=nav)
            await interaction.followup.send(i18n.t("help.ui.dm_sent_ok", self.lang), ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send(i18n.t("help.ui.dm_forbidden", self.lang), ephemeral=True)
        except Exception:
            await interaction.followup.send(i18n.t("help.ui.dm_error", self.lang), ephemeral=True)

    @discord.ui.button(label="Fermer", style=discord.ButtonStyle.danger)
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)

# ===== Cog =====
class Help(commands.Cog):
    """Aide du bot : /help (Essentiel + MP curaté), /help_admin (admins), /help <commande>. Owner : /owner."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _build_pages_from_sections(
        self,
        sections: List[Tuple[str, List[str]]],
        *,
        lang: str,
        help_cmd: str = "help",
        admin_sections: bool = False,
    ) -> Tuple[List[discord.Embed], List[str]]:
        slash_map = _all_slash_commands(self.bot)
        pages: List[discord.Embed] = []
        labels: List[str] = []
        ns = i18n.t("help.ui.not_slash_suffix", lang)
        hint = i18n.t("help.ui.page_detail_hint", lang, help_cmd=help_cmd)
        sub_lbl = i18n.t("help.ui.subcommands_label", lang)
        section_prefix = "help.section_admin" if admin_sections else "help.section"
        color = discord.Color.purple() if admin_sections else discord.Color.blurple()

        def has_slash(key: str) -> bool:
            k = key.lower()
            return k in slash_map

        for section_key, keys in sections:
            section_title = i18n.t(f"{section_prefix}.{section_key}", lang)
            fields: List[Tuple[str, str]] = []

            show_children_individually = section_key in ("tracker", "airings_list")

            for raw in keys:
                disp = f"/{raw}"
                leaf = raw.split()[-1].lower()

                if " " in raw:
                    if show_children_individually:
                        desc = _compact_one_line(_desc(lang, raw))
                        if has_slash(raw):
                            fields.append((disp, desc))
                        else:
                            fields.append((disp, f"{desc}{ns}"))
                    continue

                desc_parent = _compact_one_line(_desc(lang, raw))
                if show_children_individually:
                    if has_slash(raw):
                        fields.append((disp, desc_parent))
                    else:
                        fields.append((disp, f"{desc_parent}{ns}"))
                else:
                    children = [k for k in keys if k.startswith(raw + " ")]
                    subs = [c.split()[-1] for c in children if has_slash(c)]
                    if has_slash(raw):
                        if subs:
                            fields.append((disp, _compact_one_line(f"{desc_parent} · {sub_lbl} {', '.join(subs)}")))
                        else:
                            fields.append((disp, desc_parent))
                    else:
                        fields.append((disp, f"{desc_parent}{ns}"))

            if not fields:
                continue
            chunks = _split_fields(fields)
            for idx, chunk in enumerate(chunks):
                em = discord.Embed(
                    title=section_title,
                    description=hint,
                    color=color,
                )
                for n, v in chunk:
                    em.add_field(name=n, value=v, inline=False)
                pages.append(em)
                labels.append(section_title if len(chunks) == 1 else f"{section_title} ({idx+1}/{len(chunks)})")

        if not pages:
            brief = i18n.t("help.ui.brief_help_title", lang)
            pages = [discord.Embed(
                title=brief,
                description=i18n.t("help.ui.no_slash", lang),
                color=discord.Color.red(),
            )]
            labels = [brief]

        return pages, labels

    def _build_curated_pages(self, lang: str) -> Tuple[List[discord.Embed], List[str]]:
        return self._build_pages_from_sections(CURATED_SECTIONS, lang=lang, help_cmd="help", admin_sections=False)

    def _build_admin_curated_pages(self, lang: str) -> Tuple[List[discord.Embed], List[str]]:
        return self._build_pages_from_sections(ADMIN_HELP_SECTIONS, lang=lang, help_cmd="help_admin", admin_sections=True)

    # --- pages owner/admin (slash only)
    def _build_owner_pages(self, lang: str) -> Tuple[List[discord.Embed], List[str]]:
        def _is_ownerish_appcmd(full_name: str, sc: app_commands.Command) -> bool:
            # 1) tag explicite
            if getattr(sc, "extras", {}).get("owner_only"):
                return True
            # 2) heuristique nom
            if _is_ownerish_name(full_name):
                return True
            # 3) checks (owner / admin / has_permissions)
            for check in (getattr(sc, "checks", []) or []):
                meta = (getattr(check, "__name__", "") + " " + getattr(check, "__qualname__", "")).lower()
                if "owner" in meta or "is_owner" in meta:
                    return True
                if "administrator" in meta or "has_permissions" in meta or "manage_guild" in meta:
                    return True
                try:
                    src = inspect.getsource(check).lower()
                    if "owner" in src or "is_owner" in src:
                        return True
                    if "administrator" in src or "has_permissions" in src or "manage_guild" in src:
                        return True
                except Exception:
                    pass
            return False

        slash_map = _all_slash_commands(self.bot)
        owner_slash = [(full, sc) for full, sc in slash_map.items() if _is_ownerish_appcmd(full, sc)]
        owner_slash.sort(key=lambda x: x[0])

        if not owner_slash:
            return [
                discord.Embed(
                    title=i18n.t("help.ui.owner_title", lang),
                    description=i18n.t("help.ui.owner_empty", lang),
                    color=discord.Color.red(),
                ),
            ], [i18n.t("help.ui.label_owner_page", lang)]

        fields = []
        for full, sc in owner_slash:
            desc = (sc.description or "").strip() or _desc(lang, full)
            fields.append((f"/{full}", _compact_one_line(desc)))

        pages: List[discord.Embed] = []
        labels: List[str] = []
        split = _split_fields(fields)
        lbl_base = i18n.t("help.ui.label_owner_page", lang)
        for idx, chunk in enumerate(split):
            em = discord.Embed(
                title=i18n.t("help.ui.owner_title", lang),
                description=i18n.t("help.ui.owner_desc", lang),
                color=discord.Color.dark_gold(),
            )
            for n, v in chunk:
                em.add_field(name=n, value=v, inline=False)
            pages.append(em)
            labels.append(lbl_base if len(split) == 1 else f"{lbl_base} ({idx+1}/{len(split)})")
        return pages, labels

    async def _send_embed_ctx_or_itx(self, ctx_or_itx, *, embed: discord.Embed = None, view: discord.ui.View = None, content: str = None, ephemeral: bool = False):
        if hasattr(ctx_or_itx, "response"):
            await ctx_or_itx.response.send_message(content=content, embed=embed, view=view, ephemeral=ephemeral)
        else:
            await ctx_or_itx.send(content=content, embed=embed, view=view)

    # --- Détail /help <commande> (privilégie slash)
    async def _send_command_help(self, ctx_or_itx, raw_name: str, ephemeral: bool, *, lang: str):
        q = _normalize_query(raw_name)
        if not q:
            return await self._send_embed_ctx_or_itx(
                ctx_or_itx, content=i18n.t("help.ui.unknown_command", lang), ephemeral=ephemeral,
            )

        slash_map = _all_slash_commands(self.bot)

        sc = slash_map.get(q)
        if not sc:
            for full, cmd in slash_map.items():
                if full == q or full.startswith(q) or full.endswith(" " + q):
                    sc = cmd
                    q = full
                    break

        if sc:
            shown = f"/{q}"
            desc = (sc.description or "").strip() or _desc(lang, q)
            em = discord.Embed(
                title=i18n.t("help.ui.cmd_help_title", lang, cmd=shown),
                description=desc,
                color=discord.Color.blurple(),
            )
            try:
                params = getattr(sc, "parameters", None)
                if params:
                    lines = []
                    for p in params:
                        opt = f"[{p.display_name}]" if p.required is False else f"<{p.display_name}>"
                        typ = getattr(p, 'type', None)
                        typname = getattr(typ, 'name', None) or str(typ)
                        lines.append(f"• {opt} — {p.description or typname}")
                    if lines:
                        em.add_field(
                            name=i18n.t("help.ui.embed_params", lang),
                            value="\n".join(lines)[:1024],
                            inline=False,
                        )
                ex = shown
                if params:
                    ex += " " + " ".join(f"<{p.display_name}>" if p.required else f"[{p.display_name}]" for p in params)
                em.add_field(name=i18n.t("help.ui.embed_example", lang), value=f"`{ex}`", inline=False)
            except Exception:
                pass
            return await self._send_embed_ctx_or_itx(ctx_or_itx, embed=em, ephemeral=ephemeral)

        return await self._send_embed_ctx_or_itx(
            ctx_or_itx,
            content=i18n.t("help.ui.slash_not_found", lang),
            ephemeral=ephemeral,
        )

    # --- Commandes publiques d’aide
    @commands.hybrid_command(name="help", description="Aide Essentiel. /help [commande] pour le détail.")
    @app_commands.describe(commande="Nom d'une commande slash pour l'aide détaillée (auto-complétion).")
    @app_commands.autocomplete(commande=_ac_help_command)
    async def help(self, ctx: commands.Context, commande: Optional[str] = None):
        is_slash = bool(getattr(ctx, "interaction", None))
        target = ctx.interaction if is_slash else ctx
        ephemeral_ok = is_slash and ctx.guild is not None
        lg = i18n.ctx_lang(ctx)

        if commande:
            await self._send_command_help(target, commande, ephemeral=ephemeral_ok, lang=lg)
            return

        em = discord.Embed(
            title=i18n.t("help.ui.essential_title", lg),
            description=i18n.t("help.ui.essential_desc", lg),
            color=discord.Color.blurple(),
        )
        picks = [
            ("/minijeux", _desc(lg, "minijeux")),
            ("/next", _desc(lg, "next")),
            ("/planning", _desc(lg, "planning")),
            ("/mycard", _desc(lg, "mycard")),
            ("/profile", _desc(lg, "profile")),
            ("/animefav", _desc(lg, "animefav")),
            ("/reportbug", _desc(lg, "reportbug")),
            ("/mystats", _desc(lg, "mystats")),
            ("/linkanilist", _desc(lg, "linkanilist")),
            ("/recap", _desc(lg, "recap")),
            ("/setalert", _desc(lg, "setalert")),
            ("/botinfo", _desc(lg, "botinfo")),
            ("/vote", _desc(lg, "vote")),
        ]
        for name, desc in picks:
            em.add_field(name=name, value=_compact_one_line(desc), inline=False)
        em.set_footer(text=i18n.t("help.ui.essential_footer", lg))

        if ctx.guild is None and not is_slash:
            em.add_field(
                name=i18n.t("help.ui.mp_hint_title", lg),
                value=i18n.t("help.ui.mp_hint_help", lg),
                inline=False,
            )
            await ctx.send(embed=em)
            return

        view = CoreHelpView(
            lambda: self._build_curated_pages(lg),
            ephemeral=ephemeral_ok,
            help_cmd="help",
            lang=lg,
        )
        await self._send_embed_ctx_or_itx(target, embed=em, view=view, ephemeral=ephemeral_ok)

    @commands.hybrid_command(
        name="help_admin",
        description="Aide administrateur : configuration serveur, /airings, raid (réservé aux admins).",
    )
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    @app_commands.describe(commande="Nom d'une commande slash pour l'aide détaillée (auto-complétion).")
    @app_commands.autocomplete(commande=_ac_help_command)
    async def help_admin(self, ctx: commands.Context, commande: Optional[str] = None):
        is_slash = bool(getattr(ctx, "interaction", None))
        target = ctx.interaction if is_slash else ctx
        ephemeral_ok = is_slash and ctx.guild is not None
        lg = i18n.ctx_lang(ctx)

        if commande:
            await self._send_command_help(target, commande, ephemeral=ephemeral_ok, lang=lg)
            return

        em = discord.Embed(
            title=i18n.t("help.ui.admin_title", lg),
            description=i18n.t("help.ui.admin_desc", lg),
            color=discord.Color.dark_gold(),
        )
        picks = [
            ("/guide_admin", _desc(lg, "guide_admin")),
            ("/airings", _desc(lg, "airings")),
            ("/raidconfig", _desc(lg, "raidconfig")),
            ("/setchannel", _desc(lg, "setchannel")),
        ]
        for name, desc in picks:
            em.add_field(name=name, value=_compact_one_line(desc), inline=False)
        em.set_footer(text=i18n.t("help.ui.admin_footer", lg))

        if ctx.guild is None and not is_slash:
            em.add_field(
                name=i18n.t("help.ui.mp_hint_title", lg),
                value=i18n.t("help.ui.mp_hint_admin", lg),
                inline=False,
            )
            await ctx.send(embed=em)
            return

        view = CoreHelpView(
            lambda: self._build_admin_curated_pages(lg),
            ephemeral=ephemeral_ok,
            help_cmd="help_admin",
            lang=lg,
        )
        await self._send_embed_ctx_or_itx(target, embed=em, view=view, ephemeral=ephemeral_ok)

async def setup(bot: commands.Bot):
    # retirer toute ancienne commande textuelle `help` si présente
    try:
        bot.remove_command("help")
    except Exception:
        pass
    try:
        bot.tree.remove_command("help")
    except Exception:
        pass
    try:
        bot.tree.remove_command("help_admin")
    except Exception:
        pass

    await bot.add_cog(Help(bot))
    # Optionnel : forcer la synchro des slash ici
    # try:
    #     await bot.tree.sync()
    # except Exception:
    #     pass
