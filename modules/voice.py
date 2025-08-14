# modules/voice.py
from __future__ import annotations
import asyncio
import os
import discord

FFMPEG_BIN = os.getenv("FFMPEG_BIN", "ffmpeg")

def make_source(path: str, duration_sec: int = 20, seek_start: int = 0) -> discord.FFmpegPCMAudio:
    # -ss <sec> = seek au début, -t <sec> = durée
    return discord.FFmpegPCMAudio(
        path,
        executable=FFMPEG_BIN,
        before_options=f"-ss {int(seek_start)} -t {int(duration_sec)}",
        options="-vn"
    )

async def play_clip_in_channel(
    channel: discord.VoiceChannel,
    filepath: str,
    duration_sec: int = 20,
    disconnect_after: bool = True,
) -> None:
    """
    Rejoint le salon vocal, joue un extrait, puis (optionnel) se déconnecte.
    S'il est déjà connecté dans cette guilde, réutilise la connexion.
    """
    # 1) reuse or connect
    vc: discord.VoiceClient | None = channel.guild.voice_client
    if vc and vc.channel != channel:
        try:
            await vc.move_to(channel)
        except Exception:
            try:
                await vc.disconnect(force=True)
            except Exception:
                pass
            vc = None

    if vc is None:
        vc = await channel.connect()

    # 2) stop any current audio
    if vc.is_playing():
        vc.stop()

    # 3) play
    source = make_source(filepath, duration_sec=duration_sec)
    vc.play(source)

    # 4) attendre la fin OU max (durée + marge)
    # (FFmpeg coupera à duration_sec, on ajoute un petit buffer)
    max_wait = duration_sec + 3
    for _ in range(max_wait * 10):
        await asyncio.sleep(0.1)
        if not vc.is_playing():
            break

    # 5) optionnel: déconnecter
    if disconnect_after:
        try:
            await vc.disconnect()
        except Exception:
            pass
