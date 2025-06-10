#commands.py

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
import random
import re
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logging.getLogger('googleapiclient.discovery_cache').setLevel(logging.WARNING)

# Диагностика FFmpeg
logger.info(f"FFmpeg available: {shutil.which('ffmpeg')}")

# Список user-agent'ов
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.101 Safari/537.36",
]

class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.voice_clients = {}
        self.current_tracks = {}
        self.current_sources = []
        self.queue = {}
        self.loop = {}
        self.volume = {}
        self.voice_channel_ids = {}
        self.youtube = None
        self.cookies_path = os.path.join("config", "cookies.txt")
        
        # Настройка OAuth для YouTube API
        scopes = ["https://www.googleapis.com/auth/youtube.readonly"]
        credentials = None
        token_path = "token.json"
        
        if os.path.exists(token_path):
            credentials = Credentials.from_authorized_user_file(token_path, scopes)
        
        if not credentials or not credentials.valid:
            if credentials and credentials.expired and credentials.refresh_token:
                credentials.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    "client_secret.json", scopes=scopes
                )
                # Для локального тестирования, для Render нужно загрузить token.json
                credentials = flow.run_local_server(port=8080)
            with open(token_path, "w") as token_file:
                token_file.write(credentials.to_json())
        
        if credentials:
            self.youtube = build("youtube", "v3", credentials=credentials)
            logger.info("YouTube API инициализирован через OAuth")
        else:
            logger.warning("Не удалось инициализировать YouTube API через OAuth")
        
        if not os.path.exists(self.cookies_path):
            logger.warning(f"Файл cookies не найден по пути {self.cookies_path}")

    def get_ydl_opts(self):
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
            "user_agent": random.choice(USER_AGENTS),
            "default_search": "ytsearch",
            "no_check_certificate": True,
        }
        proxy = os.getenv("HTTP_PROXY")
        if proxy:
            ydl_opts["proxy"] = proxy
            logger.info(f"Используется прокси: {proxy}")
        if os.path.exists(self.cookies_path):
            ydl_opts["cookies"] = self.cookies_path
            logger.info(f"Используются cookies из {self.cookies_path}")
        return ydl_opts

    async def check_video_access(self, video_id):
        if not self.youtube:
            logger.warning("YouTube API не инициализирован")
            return None

        cache_file = "video_cache.json"
        cache = {}
        if os.path.exists(cache_file):
            with open(cache_file, "r", encoding="utf-8") as f:
                cache = json.load(f)
        if video_id in cache:
            logger.info(f"Используем кэш для видео: {video_id}")
            return cache[video_id]

        try:
            request = self.youtube.videos().list(
                part="snippet,contentDetails,status",
                id=video_id
            )
            response = await asyncio.get_event_loop().run_in_executor(None, request.execute)
            if response.get("items"):
                video = response["items"][0]
                video_info = {
                    "title": video["snippet"].get("title", "Unknown Title"),
                    "is_playable": video["status"].get("embeddable", False),
                    "requires_auth": False
                }
                cache[video_id] = video_info
                with open(cache_file, "w", encoding="utf-8") as f:
                    json.dump(cache, f, ensure_ascii=False, indent=2)
                return video_info
            else:
                logger.error(f"Видео с ID {video_id} не найдено")
                return None
        except HttpError as e:
            logger.error(f"Ошибка YouTube API: {e}")
            if "quota" in str(e).lower():
                logger.error("Превышена квота YouTube API")
                return {"error": "Quota exceeded"}
            elif "403" in str(e):
                return {"error": "Access restricted", "requires_auth": True}
            return None

    @app_commands.command(name="play", description="Воспроизводит музыку из указанного URL")
    async def play(self, interaction: discord.Interaction, url: str):
        defer_start = time.time()
        try:
            await interaction.response.defer(thinking=True)
            logger.info(f"Defer выполнен за {time.time() - defer_start:.2f} секунд")
        except Exception as e:
            logger.error(f"Ошибка при defer: {e}")
            return

        start_time = time.time()

        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.followup.send("Вы должны быть в голосовом канале!")
            return

        video_id = None
        if "youtu.be" in url or "youtube.com" in url:
            match = re.search(r"(?:v=|youtu\.be\/)([\w\-_]+)", url)
            if match:
                video_id = match.group(1)

        title = "Неизвестный трек"
        is_playable = True
        if video_id and self.youtube:
            video_info = await self.check_video_access(video_id)
            if video_info:
                if video_info.get("error"):
                    if video_info["error"] == "Quota exceeded":
                        await interaction.followup.send("Превышена квота YouTube API. Попробуйте позже.")
                        return
                    elif video_info["error"] == "Access restricted":
                        await interaction.followup.send("Видео требует входа в аккаунт YouTube. Убедитесь, что cookies настроены.")
                        return
                else:
                    title = video_info["title"]
                    is_playable = video_info["is_playable"]
                    if not is_playable:
                        await interaction.followup.send("Видео не поддерживает воспроизведение.")
                        return

        voice_channel = interaction.user.voice.channel
        guild_id = interaction.guild.id
        self.voice_channel_ids[guild_id] = voice_channel.id
        try:
            if guild_id in self.voice_clients:
                vc = self.voice_clients[guild_id]
                if not vc.is_connected():
                    await vc.disconnect(force=True)
                    del self.voice_clients[guild_id]
                elif vc.channel != voice_channel:
                    await vc.disconnect(force=True)
                    del self.voice_clients[guild_id]

            if guild_id not in self.voice_clients:
                vc = await voice_channel.connect(reconnect=True, timeout=5.0)
                self.voice_clients[guild_id] = vc
                self.volume[guild_id] = 1.0
                logger.info(f"Подключено к голосовому каналу {voice_channel.name} за {time.time() - start_time:.2f} секунд")
            else:
                vc = self.voice_clients[guild_id]

            if vc.is_playing():
                self.queue.setdefault(guild_id, []).append({"url": url, "title": title})
                await interaction.followup.send("Трек добавлен в очередь!")
                return
            await self.play_track(interaction, url, title=title)
        except Exception as e:
            logger.error(f"Ошибка подключения к голосовому каналу: {e}")
            await interaction.followup.send(f"Ошибка подключения: {str(e)}")

    async def play_track(self, interaction, url: str, title: str):
        guild_id = interaction.guild.id
        vc = self.voice_clients.get(guild_id)
        if not vc or not vc.is_connected():
            await interaction.followup.send("Бот не подключен к голосовому каналу!")
            return

        ydl_opts = self.get_ydl_opts()
        ydl = YoutubeDL(ydl_opts)
        loop = asyncio.get_event_loop()

        def load_cache(playlist_url):
            cache_file = "playlist_cache.json"
            if os.path.exists(cache_file):
                with open(cache_file, "r", encoding="utf-8") as f:
                    cache = json.load(f)
                return cache.get(playlist_url, None)
            return None

        def save_cache(playlist_url, tracks):
            cache_file = "playlist_cache.json"
            cache = {}
            if os.path.exists(cache_file):
                with open(cache_file, "r", encoding="utf-8") as f:
                    cache = json.load(f)
            cache[playlist_url] = tracks
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False, indent=2)

        cached = load_cache(url)
        if cached:
            logger.info(f"Используем кэш для {url}")
            info = cached
        else:
            try:
                logger.info(f"Начинаем извлечение данных для URL: {url}")
                start_time = time.time()
                func = functools.partial(ydl.extract_info, url, download=False)
                info = await loop.run_in_executor(None, func)
                logger.info(f"Данные извлечены за {time.time() - start_time:.2f} секунд")
                if "entries" in info:
                    save_cache(url, info)
            except Exception as e:
                logger.error(f"Ошибка при извлечении данных: {e}")
                error_msg = "Не удалось загрузить видео или плейлист. Проверьте URL."
                if "Sign in to confirm you’re not a bot" in str(e):
                    error_msg = "Видео требует входа в аккаунт YouTube. Убедитесь, что файл cookies.txt настроен."
                elif "Requested format is not available" in str(e):
                    error_msg += " Запрошенный формат недоступен."
                await interaction.followup.send(error_msg)
                return

        if "entries" in info:
            first_track = info["entries"][0]
            ydl_opts_full = self.get_ydl_opts()
            ydl_opts_full["extract_flat"] = False
            ydl_full = YoutubeDL(ydl_opts_full)
            try:
                start_time = time.time()
                func_full = functools.partial(ydl_full.extract_info, first_track["url"], download=False)
                first_track_info = await loop.run_in_executor(None, func_full)
                logger.info(f"Первый трек извлечён за {time.time() - start_time:.2f} секунд")
                source = first_track_info["url"]
                title = first_track_info.get("title", title)
            except Exception as e:
                logger.error(f"Ошибка при извлечении первого трека: {e}")
                error_msg = "Не удалось загрузить первый трек плейлиста."
                if "Sign in to confirm you’re not a bot" in str(e):
                    error_msg = "Видео требует входа в аккаунт YouTube. Убедитесь, что файл cookies.txt настроен."
                elif "Requested format is not available" in str(e):
                    error_msg += " Запрошенный формат недоступен."
                await interaction.followup.send(error_msg)
                return
            self.queue[guild_id] = [{"url": entry["url"], "title": entry.get("title", "Неизвестный трек")} for entry in info["entries"][1:]]
        else:
            ydl_opts_full = self.get_ydl_opts()
            ydl_opts_full["extract_flat"] = False
            ydl_full = YoutubeDL(ydl_opts_full)
            try:
                start_time = time.time()
                func_full = functools.partial(ydl_full.extract_info, url, download=False)
                info_full = await loop.run_in_executor(None, func_full)
                logger.info(f"Одиночный трек извлечён за {time.time() - start_time:.2f} секунд")
                source = info_full["url"]
                title = info_full.get("title", title)
            except Exception as e:
                logger.error(f"Ошибка при извлечении трека: {e}")
                error_msg = "Не удалось загрузить трек."
                if "Sign in to confirm you’re not a bot" in str(e):
                    error_msg = "Видео требует входа в аккаунт YouTube. Убедитесь, что файл cookies.txt настроен."
                elif "Requested format is not available" in str(e):
                    error_msg += " Запрошенный формат недоступен."
                await interaction.followup.send(error_msg)
                return

        async with aiohttp.ClientSession() as session:
            try:
                async with session.head(source, timeout=5) as response:
                    if response.status != 200:
                        logger.error(f"URL недоступен: {source}, статус: {response.status}")
                        await interaction.followup.send("Не удалось загрузить видео. Попробуйте другой URL.")
                        return
            except aiohttp.ClientError as e:
                logger.error(f"Ошибка при проверке URL: {e}")
                await interaction.followup.send("Ошибка при проверке URL.")
                return

        self.current_tracks[guild_id] = title
        self.current_sources.append(source)
        self.loop[guild_id] = False

        ffmpeg_options = {
            'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 10',
            'options': '-vn -bufsize 1M'
        }
        vol = self.volume.get(guild_id, 1.0)
        audio_source = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(source, **ffmpeg_options), volume=vol)
        try:
            vc.play(audio_source, after=lambda e: self.bot.loop.create_task(self.after_track(guild_id)))
            logger.info(f"Воспроизведение начато: {title}")
            await interaction.followup.send(f"Играет сейчас: **{title}**")
        except discord.ClientException as e:
            logger.error(f"Ошибка воспроизведения: {e}")
            await interaction.followup.send("Ошибка воспроизведения. Попробуйте снова.")

    async def after_track(self, guild_id):
        vc = self.voice_clients.get(guild_id)
        if not vc or not vc.is_connected():
            logger.info(f"Нет активного соединения для guild_id {guild_id}")
            return
        if self.loop.get(guild_id, False):
            source = self.current_sources[-1]
            if source:
                self.bot.loop.create_task(self.play_track_from_url(guild_id, source))
        elif self.queue.get(guild_id) and len(self.queue.get(guild_id)) > 0:
            next_track = self.queue[guild_id].pop(0)
            self.bot.loop.create_task(self.play_track_from_url(guild_id, next_track["url"]))
        elif self.loop.get(guild_id, False) and self.queue.get(guild_id):
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
                    try:
                        vc = await voice_channel.connect(reconnect=True, timeout=5.0)
                        self.voice_clients[guild_id] = vc
                        logger.info(f"Переподключено к голосовому каналу {voice_channel.name}")
                    except Exception as e:
                        logger.error(f"Не удалось переподключиться: {e}")
                        return
                else:
                    logger.error("Голосовой канал не найден")
                    return
            else:
                logger.error("ID голосового канала не сохранён")
                return

        logger.info(f"Попытка воспроизвести трек для guild_id {guild_id}, URL: {url}")
        ydl_opts = self.get_ydl_opts()
        ydl_opts["extract_flat"] = False
        ydl = YoutubeDL(ydl_opts)
        loop = asyncio.get_event_loop()
        try:
            start_time = time.time()
            func = functools.partial(ydl.extract_info, url, download=False)
            info = await loop.run_in_executor(None, func)
            logger.info(f"Трек извлечён за {time.time() - start_time:.2f} секунд")
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
                        logger.error(f"URL недоступен: {source}, статус: {response.status}")
                        self.bot.loop.create_task(self.after_track(guild_id))
                        return
            except aiohttp.ClientError as e:
                logger.error(f"Ошибка при проверке URL: {e}")
                self.bot.loop.create_task(self.after_track(guild_id))
                return

        self.current_tracks[guild_id] = title
        self.current_sources.append(source)
        ffmpeg_options = {
            'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 10',
            'options': '-vn -bufsize 1M'
        }
        vol = self.volume.get(guild_id, 1.0)
        audio_source = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(source, **ffmpeg_options), volume=vol)
        try:
            if vc.is_playing():
                vc.stop()
                await asyncio.sleep(0.5)
            vc.play(audio_source, after=lambda e: self.bot.loop.create_task(self.after_track(guild_id)))
            logger.info(f"Воспроизведение начато: {title}")
        except discord.ClientException as e:
            logger.error(f"Ошибка воспроизведения: {e}")
            return

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
                await interaction.response.send_message("Музыка поставлена на паузу.")
            else:
                await interaction.response.send_message("Музыка не воспроизводится.")
        else:
            await interaction.response.send_message("Бот не подключен к голосовому каналу.")

    @app_commands.command(name="resume", description="Продолжает воспроизведение музыки")
    async def resume(self, interaction: discord.Interaction):
        if interaction.guild.id in self.voice_clients:
            vc = self.voice_clients[interaction.guild.id]
            if vc.is_paused():
                vc.resume()
                title = self.current_tracks.get(interaction.guild.id, "Неизвестный трек")
                await interaction.response.send_message(f"Воспроизведение продолжено: **{title}**")
            else:
                await interaction.response.send_message("Музыка уже воспроизводится.")
        else:
            await interaction.response.send_message("Бот не подключен к голосовому каналу.")

    @app_commands.command(name="stop", description="Останавливает воспроизведение и отключает бота от канала")
    async def stop(self, interaction: discord.Interaction):
        if interaction.guild.id in self.voice_clients:
            vc = self.voice_clients[interaction.guild.id]
            await interaction.response.defer(thinking=True)
            await vc.disconnect(force=True)
            del self.voice_clients[interaction.guild.id]
            self.current_tracks.pop(interaction.guild.id, None)
            self.current_sources.clear()
            await interaction.followup.send("Воспроизведение остановлено и бот отключен от канала.")
        else:
            await interaction.response.send_message("Бот не подключен к голосовому каналу.")

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
            await interaction.response.send_message("Бот не подключен к голосовому каналу.")

    @app_commands.command(name="seek", description="Перематывает трек на указанное время (в секундах)")
    async def seek(self, interaction: discord.Interaction, seconds: int):
        if interaction.guild.id in self.voice_clients:
            vc = self.voice_clients[interaction.guild.id]
            if vc.is_playing() or vc.is_paused():
                source = self.current_sources[-1] if self.current_sources else None
                if not source:
                    await interaction.response.send_message("Текущий трек не найден!")
                    return
                vc.stop()
                ffmpeg_options = {
                    'before_options': f'-ss {seconds} -reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 10',
                    'options': '-vn -bufsize 1M'
                }
                vol = self.volume.get(interaction.guild.id, 1.0)
                new_source = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(source, **ffmpeg_options), volume=vol)
                vc.play(new_source, after=lambda e: self.bot.loop.create_task(self.after_track(interaction.guild.id)))
                await interaction.response.send_message(f"Перемотано на {seconds} секунд.")
            else:
                await interaction.response.send_message("Сейчас ничего не играет.")
        else:
            await interaction.response.send_message("Бот не подключен к голосовому каналу.")

    @app_commands.command(name="replay", description="Включает или выключает повтор текущего трека")
    async def replay(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        self.loop[guild_id] = not self.loop.get(guild_id, False)
        status = "включен" if self.loop[guild_id] else "выключен"
        await interaction.response.send_message(f"Режим повтора {status}.")

    @app_commands.command(name="queue", description="Добавляет трек в очередь или показывает список")
    async def queue(self, interaction: discord.Interaction, url: str = None):
        guild_id = interaction.guild.id
        if url:
            self.queue.setdefault(guild_id, []).append({"url": url, "title": "Неизвестный трек"})
            await interaction.response.send_message("Трек добавлен в очередь!")
        elif guild_id in self.queue and self.queue[guild_id]:
            queue_list = "\n".join([f"{i+1}. {track['title']}" for i, track in enumerate(self.queue[guild_id])])
            await interaction.response.send_message(f"Очередь треков:\n{queue_list}")
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

    @app_commands.command(name="volume", description="Изменяет громкость воспроизведения (0-100)")
    async def volume(self, interaction: discord.Interaction, vol: int):
        if not 0 <= vol <= 100:
            await interaction.response.send_message("Уровень громкости должен быть от 0 до 100.")
            return
        guild_id = interaction.guild.id
        self.volume[guild_id] = vol / 100.0
        if guild_id in self.voice_clients and self.current_sources:
            vc = self.voice_clients[guild_id]
            if hasattr(vc.source, 'volume'):
                vc.source.volume = vol / 100.0
                await interaction.response.send_message(f"Громкость установлена на {vol}%.")
                return
        await interaction.response.send_message(f"Громкость установлена на {vol}%.")

    @app_commands.command(name="loopqueue", description="Включает или выключает повтор всей очереди")
    async def loopqueue(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        self.loop[guild_id] = not self.loop.get(guild_id, False)
        status = "включён" if self.loop[guild_id] else "выключен"
        await interaction.response.send_message(f"Режим повтора очереди {status}.")

    @app_commands.command(name="clearqueue", description="Очищает очередь треков")
    async def clearqueue(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        self.queue[guild_id] = []
        await interaction.response.send_message("Очередь очищена.")
