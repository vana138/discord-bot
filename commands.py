import discord
from discord import app_commands
from discord.ext import commands
from yt_dlp import YoutubeDL
import asyncio
import functools
import logging
import json
import os
import time
import shutil
import aiohttp
from cookies import generate_cookies_file, is_cookies_file_valid

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Диагностика FFmpeg
logger.info(f"FFmpeg available: {shutil.which('ffmpeg')}")

class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.voice_clients = {}
        self.current_tracks = {}
        self.current_sources = {}
        self.queue = {}
        self.loop = {}
        self.loop_queue = {}
        self.volume = {}
        self.voice_channel_ids = {}

    def ensure_cookies(self):
        if not is_cookies_file_valid():
            logger.warning("Файл cookies.txt отсутствует или устарел. Запустите deploy_bot.py на компьютере.")

    @app_commands.command(name="refresh_cookies", description="Проверяет состояние cookies.txt")
    async def refresh_cookies(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(thinking=True)
            if is_cookies_file_valid():
                await interaction.followup.send("Файл cookies.txt действителен.")
            else:
                message = (
                    "Файл cookies.txt отсутствует или устарел. На вашем компьютере:\n"
                    "1. Убедитесь, что вы вошли в YouTube в Microsoft Edge.\n"
                    "2. Откройте командную строку в папке бота.\n"
                    "3. Запустите: `python deploy_bot.py`\n"
                    "Это обновит cookies и перезапустит бота."
                )
                await interaction.followup.send(message)
        except Exception as e:
            logger.error(f"Ошибка в refresh_cookies: {e}")
            await interaction.followup.send("Произошла ошибка при проверке cookies.")

    @app_commands.command(name="play", description="Воспроизводит музыку из URL")
    async def play(self, interaction: discord.Interaction, url: str):
        try:
            await interaction.response.defer(thinking=True)
        except Exception as e:
            logger.error(f"Ошибка при defer: {e}")
            return

        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.followup.send("Вы должны быть в голосовом канале!")
            return

        voice_channel = interaction.user.voice.channel
        guild_id = interaction.guild.id
        self.voice_channel_ids[guild_id] = voice_channel.id
        try:
            if guild_id in self.voice_clients:
                vc = self.voice_clients[guild_id]
                if not vc.is_connected() or vc.channel != voice_channel:
                    await vc.disconnect(force=True)
                    del self.voice_clients[guild_id]

            if guild_id not in self.voice_clients:
                vc = await voice_channel.connect()
                self.voice_clients[guild_id] = vc
                self.volume[guild_id] = 1.0

            vc = self.voice_clients[guild_id]
            if vc.is_playing():
                self.queue.setdefault(guild_id, []).append({"url": url, "title": "Неизвестный трек"})
                await interaction.followup.send("Трек добавлен в очередь!")
                return
            await self.play_track(interaction, url)
        except Exception as e:
            logger.error(f"Ошибка подключения: {e}")
            await interaction.followup.send("Ошибка подключения к голосовому каналу.")

    async def play_track(self, interaction, url):
        guild_id = interaction.guild.id
        vc = self.voice_clients.get(guild_id)
        if not vc or not vc.is_connected():
            await interaction.followup.send("Бот не подключен к голосовому каналу!")
            return

        self.ensure_cookies()
        ydl_opts = {
            "format": "bestaudio/best",
            "noplaylist": False,
            "quiet": True,
            "socket_timeout": 15,
            "extract_flat": True,
            "retries": 10,
            "max_retries": 3,
            "playlistend": 120,
            "no_warnings": True,
            "force_generic_extractor": True,
        }
        if os.path.exists("cookies.txt"):
            ydl_opts["cookiefile"] = "cookies.txt"
        else:
            logger.warning("Файл cookies.txt не найден.")

        ydl = YoutubeDL(ydl_opts)
        loop = asyncio.get_event_loop()

        def load_cache(playlist_url):
            cache_file = "playlist_cache.json"
            if os.path.exists(cache_file):
                with open(cache_file, "r") as f:
                    cache = json.load(f)
                return cache.get(playlist_url, None)
            return None

        def save_cache(playlist_url, tracks):
            cache_file = "playlist_cache.json"
            cache = {}
            if os.path.exists(cache_file):
                with open(cache_file, "r") as f:
                    cache = json.load(f)
            cache[playlist_url] = tracks
            with open(cache_file, "w") as f:
                json.dump(cache, f)

        cached = load_cache(url)
        if cached:
            info = cached
        else:
            func = functools.partial(ydl.extract_info, url, download=False)
            try:
                info = await loop.run_in_executor(None, func)
                if "entries" in info:
                    save_cache(url, info)
            except Exception as e:
                logger.error(f"Ошибка извлечения данных: {e}")
                error_msg = "Не удалось загрузить трек. Проверьте URL."
                if "Sign in to confirm" in str(e):
                    error_msg += " Обновите cookies с помощью /refresh_cookies."
                await interaction.followup.send(error_msg)
                return

        if "entries" in info:
            first_track = info["entries"][0]
            ydl_opts_full = ydl_opts.copy()
            ydl_opts_full["extract_flat"] = False
            ydl_full = YoutubeDL(ydl_opts_full)
            func_full = functools.partial(ydl_full.extract_info, first_track["url"], download=False)
            try:
                first_track_info = await loop.run_in_executor(None, func_full)
                source = first_track_info["url"]
                title = first_track_info.get("title", "Неизвестный трек")
            except Exception as e:
                logger.error(f"Ошибка извлечения трека: {e}")
                await interaction.followup.send("Не удалось загрузить трек плейлиста.")
                return
            self.queue[guild_id] = [{"url": entry["url"], "title": entry.get("title", "Неизвестный трек")} for entry in info["entries"][1:]]
        else:
            ydl_opts_full = ydl_opts.copy()
            ydl_opts_full["extract_flat"] = False
            ydl_full = YoutubeDL(ydl_opts_full)
            func_full = functools.partial(ydl_full.extract_info, url, download=False)
            try:
                info_full = await loop.run_in_executor(None, func_full)
                source = info_full["url"]
                title = info_full.get("title", "Неизвестный трек")
            except Exception as e:
                logger.error(f"Ошибка извлечения трека: {e}")
                await interaction.followup.send("Не удалось загрузить трек.")
                return

        async with aiohttp.ClientSession() as session:
            try:
                async with session.head(source, timeout=5) as response:
                    if response.status != 200:
                        logger.error(f"URL недоступен: {response.status}")
                        await interaction.followup.send("Не удалось загрузить трек.")
                        return
            except Exception as e:
                logger.error(f"Ошибка проверки URL: {e}")
                await interaction.followup.send("Ошибка проверки URL.")
                return

        self.current_tracks[guild_id] = title
        self.current_sources[guild_id] = source
        self.loop[guild_id] = False

        ffmpeg_options = {
            'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 10',
            'options': '-vn'
        }
        vol = self.volume.get(guild_id, 1.0)
        audio_source = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(source, **ffmpeg_options), volume=vol)
        try:
            vc.play(audio_source, after=lambda e: self.bot.loop.create_task(self.after_track(guild_id)))
            await interaction.followup.send(f"Играет: **{title}**")
        except discord.ClientException as e:
            logger.error(f"Ошибка воспроизведения: {e}")
            await interaction.followup.send("Ошибка воспроизведения.")

    async def after_track(self, guild_id):
        vc = self.voice_clients.get(guild_id)
        if vc is None or not vc.is_connected():
            return
        if self.loop.get(guild_id, False):
            source = self.current_sources.get(guild_id)
            if source:
                self.bot.loop.create_task(self.play_track_from_url(guild_id, source))
        elif self.queue.get(guild_id) and len(self.queue[guild_id]) > 0:
            next_track = self.queue[guild_id].pop(0)
            self.bot.loop.create_task(self.play_track_from_url(guild_id, next_track["url"]))
        elif self.loop_queue.get(guild_id, False) and self.queue.get(guild_id):
            if len(self.queue[guild_id]) > 0:
                first_url = self.queue[guild_id][0]["url"]
                self.bot.loop.create_task(self.play_track_from_url(guild_id, first_url))

    async def play_track_from_url(self, guild_id, url):
        vc = self.voice_clients.get(guild_id)
        if not vc or not vc.is_connected():
            voice_channel_id = self.voice_channel_ids.get(guild_id)
            if voice_channel_id:
                voice_channel = self.bot.get_channel(voice_channel_id)
                if voice_channel:
                    vc = await voice_channel.connect()
                    self.voice_clients[guild_id] = vc
                else:
                    return

        self.ensure_cookies()
        ydl_opts = {
            "format": "bestaudio/best",
            "quiet": True,
            "socket_timeout": 15,
            "retries": 5,
            "max_retries": 3,
            "no_warnings": True,
        }
        if os.path.exists("cookies.txt"):
            ydl_opts["cookiefile"] = "cookies.txt"
        ydl = YoutubeDL(ydl_opts)
        loop = asyncio.get_event_loop()
        func = functools.partial(ydl.extract_info, url, download=False)
        try:
            info = await loop.run_in_executor(None, func)
            source = info["url"]
            title = info.get("title", "Неизвестный трек")
        except Exception as e:
            logger.error(f"Ошибка извлечения трека: {e}")
            self.bot.loop.create_task(self.after_track(guild_id))
            return

        async with aiohttp.ClientSession() as session:
            try:
                async with session.head(source, timeout=5) as response:
                    if response.status != 200:
                        self.bot.loop.create_task(self.after_track(guild_id))
                        return
            except Exception as e:
                logger.error(f"Ошибка проверки URL: {e}")
                self.bot.loop.create_task(self.after_track(guild_id))
                return

        self.current_tracks[guild_id] = title
        self.current_sources[guild_id] = source
        ffmpeg_options = {
            'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 10',
            'options': '-vn'
        }
        vol = self.volume.get(guild_id, 1.0)
        audio_source = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(source, **ffmpeg_options), volume=vol)
        try:
            if vc.is_playing():
                vc.stop()
                await asyncio.sleep(0.5)
            vc.play(audio_source, after=lambda e: self.bot.loop.create_task(self.after_track(guild_id)))
        except discord.ClientException as e:
            logger.error(f"Ошибка воспроизведения: {e}")

    @app_commands.command(name="nowplaying", description="Показывает текущий трек")
    async def nowplaying(self, interaction: discord.Interaction):
        title = self.current_tracks.get(interaction.guild.id, None)
        if title:
            await interaction.response.send_message(f"Сейчас играет: **{title}**")
        else:
            await interaction.response.send_message("Сейчас ничего не играет.")

    @app_commands.command(name="pause", description="Ставит музыку на паузу")
    async def pause(self, interaction: discord.Interaction):
        if interaction.guild.id in self.voice_clients:
            vc = self.voice_clients[interaction.guild.id]
            if vc.is_playing():
                vc.pause()
                await interaction.response.send_message("Музыка на паузе.")
            else:
                await interaction.response.send_message("Музыка не воспроизводится.")
        else:
            await interaction.response.send_message("Бот не в голосовом канале.")

    @app_commands.command(name="resume", description="Продолжает воспроизведение")
    async def resume(self, interaction: discord.Interaction):
        if interaction.guild.id in self.voice_clients:
            vc = self.voice_clients[interaction.guild.id]
            if vc.is_paused():
                vc.resume()
                title = self.current_tracks.get(interaction.guild.id, "Неизвестный трек")
                await interaction.response.send_message(f"Продолжено: **{title}**")
            else:
                await interaction.response.send_message("Музыка уже играет.")
        else:
            await interaction.response.send_message("Бот не в голосовом канале.")

    @app_commands.command(name="stop", description="Останавливает музыку и отключается")
    async def stop(self, interaction: discord.Interaction):
        if interaction.guild.id in self.voice_clients:
            vc = self.voice_clients[interaction.guild.id]
            await interaction.response.defer(thinking=True)
            await vc.disconnect(force=True)
            del self.voice_clients[interaction.guild.id]
            self.current_tracks.pop(interaction.guild.id, None)
            self.current_sources.pop(interaction.guild.id, None)
            await interaction.followup.send("Музыка остановлена, бот отключен.")
        else:
            await interaction.response.send_message("Бот не в голосовом канале.")

    @app_commands.command(name="skip", description="Пропускает текущий трек")
    async def skip(self, interaction: discord.Interaction):
        if interaction.guild.id in self.voice_clients:
            vc = self.voice_clients[interaction.guild.id]
            if vc.is_playing():
                vc.stop()
                await interaction.response.send_message("Трек пропущен.")
            else:
                await interaction.response.send_message("Сейчас ничего не играет.")
        else:
            await interaction.response.send_message("Бот не в голосовом канале.")

    @app_commands.command(name="seek", description="Перематывает трек (в секундах)")
    async def seek(self, interaction: discord.Interaction, seconds: int):
        if interaction.guild.id in self.voice_clients:
            vc = self.voice_clients[interaction.guild.id]
            if vc.is_playing() or vc.is_paused():
                source = self.current_sources.get(interaction.guild.id)
                if not source:
                    await interaction.response.send_message("Трек не найден!")
                    return
                vc.stop()
                ffmpeg_options = {
                    'before_options': f'-ss {seconds} -reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 10',
                    'options': '-vn'
                }
                vol = self.volume.get(interaction.guild.id, 1.0)
                new_source = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(source, **ffmpeg_options), volume=vol)
                vc.play(new_source, after=lambda e: self.bot.loop.create_task(self.after_track(interaction.guild.id)))
                await interaction.response.send_message(f"Перемотано на {seconds} секунд.")
            else:
                await interaction.response.send_message("Сейчас ничего не играет.")
        else:
            await interaction.response.send_message("Бот не в голосовом канале.")

    @app_commands.command(name="replay", description="Включает/выключает повтор трека")
    async def replay(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        self.loop[guild_id] = not self.loop.get(guild_id, False)
        status = "включен" if self.loop[guild_id] else "выключен"
        await interaction.response.send_message(f"Повтор трека {status}.")

    @app_commands.command(name="queue", description="Добавляет трек в очередь или показывает очередь")
    async def queue(self, interaction: discord.Interaction, url: str = None):
        guild_id = interaction.guild.id
        if url:
            self.queue.setdefault(guild_id, []).append({"url": url, "title": "Неизвестный трек"})
            await interaction.response.send_message("Трек добавлен в очередь!")
        elif guild_id in self.queue and self.queue[guild_id]:
            queue_list = "\n".join([f"{i+1}. {track['title']}" for i, track in enumerate(self.queue[guild_id])])
            await interaction.response.send_message(f"Очередь:\n{queue_list}")
        else:
            await interaction.response.send_message("Очередь пуста.")

    @app_commands.command(name="unqueue", description="Удаляет трек из очереди по номеру")
    async def unqueue(self, interaction: discord.Interaction, index: int):
        guild_id = interaction.guild.id
        if guild_id in self.queue and 0 <= index - 1 < len(self.queue[guild_id]):
            removed_track = self.queue[guild_id].pop(index - 1)
            await interaction.response.send_message(f"Удалён трек: {removed_track['title']}")
        else:
            await interaction.response.send_message("Неверный индекс или очередь пуста.")

    @app_commands.command(name="volume", description="Устанавливает громкость (0-100)")
    async def volume(self, interaction: discord.Interaction, volume: int):
        if not 0 <= volume <= 100:
            await interaction.response.send_message("Громкость должна быть от 0 до 100.")
            return
        guild_id = interaction.guild.id
        self.volume[guild_id] = volume / 100.0
        if guild_id in self.voice_clients and self.current_sources.get(guild_id):
            vc = self.voice_clients[guild_id]
            if hasattr(vc.source, 'volume'):
                vc.source.volume = volume / 100.0
        await interaction.response.send_message(f"Громкость установлена на {volume}%.")

    @app_commands.command(name="loopqueue", description="Включает/выключает повтор очереди")
    async def loopqueue(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        self.loop_queue[guild_id] = not self.loop_queue.get(guild_id, False)
        status = "включен" if self.loop_queue[guild_id] else "выключен"
        await interaction.response.send_message(f"Повтор очереди {status}.")

    @app_commands.command(name="clearqueue", description="Очищает очередь")
    async def clearqueue(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        self.queue[guild_id] = []
        await interaction.response.send_message("Очередь очищена.")

async def setup(bot: commands.Bot):
    await bot.add_cog(Music(bot))