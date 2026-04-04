# cogs/emoji_autosync.py
from __future__ import annotations
import os, json, asyncio, hashlib, discord
from pathlib import Path
from typing import Dict, List, Tuple
import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

from modules import i18n
from modules.app_cmd_locale import ui_str

EMOJI_PREFIX = "ab_"
ASSETS_GUILD_ID = int(os.getenv("ASSETS_GUILD_ID", "0"))
STATE_DIR = Path(os.getenv("EMOJI_STATE_DIR", "data"))

# Plusieurs racines locales possibles, scannées en récursif
_local_dirs_env = os.getenv("EMOJI_LOCAL_DIRS") or os.getenv("EMOJI_LOCAL_DIR", "assets/emojis")
LOCAL_DIRS = [Path(p.strip()) for p in _local_dirs_env.split(":") if p.strip()]

MANIFEST_URL = (os.getenv("EMOJI_MANIFEST_URL") or "").strip()
PRUNE = (os.getenv("EMOJI_PRUNE", "0").strip().lower() in {"1", "true", "yes"})
HASH_FILE = Path("data/emoji_hashes.json")
OUT_FILE = Path("data/config_emojis.json")


def _es(lg: str, key: str, **kwargs) -> str:
    return i18n.t(f"emoji_sync.{key}", lg, **kwargs)


def _sha1(b: bytes) -> str:
    return hashlib.sha1(b).hexdigest()


def _save_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _is_img(p: Path) -> bool:
    return p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".gif"}


async def _collect_source(lg: str) -> Tuple[Dict[str, bytes], List[str]]:
    """
    Retourne (source, logs) où source = {emoji_name: bytes}
    - via MANIFEST_URL si fourni, sinon via scan récursif de LOCAL_DIRS
    """
    logs: List[str] = []
    out: Dict[str, bytes] = {}

    if MANIFEST_URL:
        logs.append(_es(lg, "manifest_url", url=MANIFEST_URL))
        async with aiohttp.ClientSession() as s:
            try:
                async with s.get(MANIFEST_URL, timeout=30) as r:
                    r.raise_for_status()
                    manifest = await r.json()
            except Exception as e:
                logs.append(_es(lg, "manifest_read_fail", err=e))
                return {}, logs

            for name, url in manifest.items():
                key = f"{EMOJI_PREFIX}{str(name).lower()}"
                try:
                    async with s.get(str(url), timeout=30) as img:
                        img.raise_for_status()
                        out[key] = await img.read()
                except Exception as e:
                    logs.append(_es(lg, "manifest_dl_fail", name=name, url=url, err=e))
        logs.append(_es(lg, "manifest_loaded", n=len(out)))
        return out, logs

    roots = [str(p.resolve()) for p in LOCAL_DIRS]
    logs.append(
        _es(
            lg,
            "local_dirs",
            dirs=", ".join(roots) if roots else _es(lg, "empty_display"),
        )
    )
    for root in LOCAL_DIRS:
        if not root.exists():
            logs.append(_es(lg, "local_dir_missing", path=root))
            continue
        for p in root.rglob("*"):
            if p.is_file() and _is_img(p):
                key = f"{EMOJI_PREFIX}{p.stem.lower()}"
                try:
                    data = p.read_bytes()
                except Exception as e:
                    logs.append(_es(lg, "local_read_fail", path=p, err=e))
                    continue
                out[key] = data
    logs.append(_es(lg, "local_found", n=len(out)))
    return out, logs


async def _run_sync(bot: commands.Bot, lg: str) -> Tuple[str, Dict[str, int]]:
    lines: List[str] = []
    if not ASSETS_GUILD_ID:
        return _es(lg, "assets_missing"), {}

    guild = bot.get_guild(ASSETS_GUILD_ID)
    if not guild:
        return _es(lg, "guild_missing"), {}

    me = guild.me
    if not me or not me.guild_permissions.manage_emojis:
        lines.append(_es(lg, "no_manage_emoji"))
        return "\n".join(lines), {}

    source, src_logs = await _collect_source(lg)
    lines.extend(src_logs)

    if not source:
        lines.append(_es(lg, "empty_source"))
        return "\n".join(lines), {}

    try:
        old_hash = json.loads(HASH_FILE.read_text(encoding="utf-8"))
    except Exception:
        old_hash = {}

    existing = {e.name: e for e in guild.emojis}
    created: List[str] = []
    kept: List[str] = []

    for name, data in source.items():
        if len(data) > 256_000:
            lines.append(_es(lg, "file_too_large", name=name))
        h = _sha1(data)
        emo = existing.get(name)
        if emo and old_hash.get(name) == h:
            kept.append(f"{name} ({emo.id})")
            continue
        if emo:
            try:
                await emo.delete(reason="EmojiAutoSync replace")
            except Exception as e:
                lines.append(_es(lg, "delete_fail", name=name, err=e))
            await asyncio.sleep(0.2)
        try:
            new_emoji = await guild.create_custom_emoji(name=name, image=data, reason="EmojiAutoSync upload")
            existing[name] = new_emoji
            old_hash[name] = h
            created.append(f"{name} ({new_emoji.id})")
            await asyncio.sleep(0.3)
        except discord.HTTPException as e:
            lines.append(_es(lg, "upload_fail", name=name, err=e))

    if PRUNE:
        names_in_source = set(source.keys())
        removed: List[str] = []
        for emo in list(guild.emojis):
            if emo.name.startswith(EMOJI_PREFIX) and emo.name not in names_in_source:
                try:
                    await emo.delete(reason="EmojiAutoSync prune")
                    removed.append(f"{emo.name} ({emo.id})")
                    await asyncio.sleep(0.3)
                except Exception as e:
                    lines.append(_es(lg, "prune_fail", name=emo.name, err=e))
        if removed:
            lines.append(_es(lg, "prune_removed", items=", ".join(removed)))

    mapping = {e.name: e.id for e in guild.emojis if e.name.startswith(EMOJI_PREFIX)}
    try:
        _save_json(OUT_FILE, mapping)
        _save_json(HASH_FILE, old_hash)
    except Exception as e:
        lines.append(_es(lg, "hash_write_fail", err=e))

    if created:
        lines.append(_es(lg, "created_header", n=len(created), items=", ".join(created)))
    if kept:
        lines.append(_es(lg, "kept_header", n=len(kept), items=", ".join(kept)))
    lines.append(_es(lg, "mapping_written", path=OUT_FILE.as_posix()))
    return "\n".join(lines), mapping


class EmojiAutoSync(commands.Cog):
    """Auto-sync au démarrage + commandes /emojidiag et /syncemojis."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._done = False

    async def _authorized(self, interaction: discord.Interaction) -> bool:
        OWNER_IDS = {int(x) for x in os.getenv("OWNER_IDS", "").replace(" ", "").split(",") if x.isdigit()}
        try:
            if await self.bot.is_owner(interaction.user):
                return True
        except Exception:
            pass
        if interaction.user.id in OWNER_IDS:
            return True
        perms = getattr(interaction.user, "guild_permissions", None)
        if perms and perms.administrator:
            return True
        return False

    @app_commands.command(name="emojimap", description=ui_str("slash.emoji_emojimap"))
    async def emojimap(self, interaction: discord.Interaction):
        lg = i18n.interaction_lang(interaction)
        if not await self._authorized(interaction):
            return await interaction.response.send_message(_es(lg, "denied"), ephemeral=True)

        if not OUT_FILE.exists():
            return await interaction.response.send_message(_es(lg, "no_file"), ephemeral=True)

        try:
            await interaction.response.send_message(
                content=_es(lg, "here_mapping"),
                file=discord.File(OUT_FILE.as_posix(), filename="config_emojis.json"),
                ephemeral=True,
            )
        except Exception:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
            try:
                await interaction.user.send(file=discord.File(OUT_FILE.as_posix(), filename="config_emojis.json"))
                await interaction.followup.send(_es(lg, "dm_ok"), ephemeral=True)
            except Exception as ex:
                await interaction.followup.send(_es(lg, "dm_fail", err=ex), ephemeral=True)

    @commands.Cog.listener()
    async def on_ready(self):
        if self._done:
            return
        self._done = True
        if not ASSETS_GUILD_ID:
            print(_es("fr", "startup_no_assets"))
            return
        msg, _ = await _run_sync(self.bot, "fr")
        print(msg)

    @app_commands.command(name="emojidiag", description=ui_str("slash.emoji_emojidiag"))
    async def emojidiag(self, interaction: discord.Interaction):
        lg = i18n.interaction_lang(interaction)
        if not await self._authorized(interaction):
            return await interaction.response.send_message(_es(lg, "denied"), ephemeral=True)

        lines: List[str] = []
        lines.append(_es(lg, "diag_assets_line", id=ASSETS_GUILD_ID))
        g = self.bot.get_guild(ASSETS_GUILD_ID)
        lines.append(_es(lg, "diag_guild_found", v=bool(g)))
        if g and g.me:
            lines.append(_es(lg, "diag_manage", v=g.me.guild_permissions.manage_emojis))
        lines.append(_es(lg, "diag_manifest", url=MANIFEST_URL or _es(lg, "empty_display")))
        lines.append(
            _es(
                lg,
                "diag_local",
                dirs=", ".join(str(p.resolve()) for p in LOCAL_DIRS) if LOCAL_DIRS else _es(lg, "empty_display"),
            )
        )

        source, src_logs = await _collect_source(lg)
        lines.extend(src_logs)
        sample = ", ".join(list(source.keys())[:10]) if source else _es(lg, "empty_display")
        lines.append(_es(lg, "diag_samples", sample=sample))

        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @app_commands.command(name="syncemojis", description=ui_str("slash.emoji_syncemojis"))
    async def syncemojis(self, interaction: discord.Interaction):
        lg = i18n.interaction_lang(interaction)
        if not await self._authorized(interaction):
            return await interaction.response.send_message(_es(lg, "denied"), ephemeral=True)
        await interaction.response.defer(ephemeral=True, thinking=True)
        msg, _mapping = await _run_sync(self.bot, lg)
        await interaction.followup.send(msg, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(EmojiAutoSync(bot))
