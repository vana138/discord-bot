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

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.voice_clients = {}         # voice_client по guild_id
        self.current_tracks = {}        # название текущего трека по guild_id
        self.current_sources = {}       # прямой URL аудио по guild_id
        self.queue = {}                 # очередь треков (URL) по guild_id
        self.loop = {}                  # повтор текущего трека (bool) по guild_id
        self.loop_queue = {}            # повтор всей очереди (bool) по guild_id
        self.volume = {}                # уровень громкости (float, 1.0 по умолчанию) по guild_id

    @app_commands.command(name="play", description="Воспроизводит музыку из указанного URL")
async def play(self, interaction: discord.Interaction, url: str):
    # Немедленно откладываем ответ, чтобы избежать ошибки Unknown Interaction
    await interaction.response.defer(thinking=True)
    
    if not interaction.user.voice or not interaction.user.voice.channel:
        await interaction.followup.send("Вы должны находиться в голосовом канале!")
        return

    voice_channel = interaction.user.voice.channel
    try:
        if interaction.guild.id not in self.voice_clients or not self.voice_clients[interaction.guild.id].is_connected():
            vc = await voice_channel.connect()
            self.voice_clients[interaction.guild.id] = vc
            self.volume[interaction.guild.id] = 1.0
        else:
            vc = self.voice_clients[interaction.guild.id]
        if vc.is_playing():
            self.queue.setdefault(interaction.guild.id, []).append({"url": url, "title": "Неизвестный трек"})
            await interaction.followup.send("Трек добавлен в очередь!")
            return
    except Exception as e:
        await interaction.followup.send(f"Ошибка подключения к голосовому каналу: {e}")
        return

    await self.play_track(interaction, url)

    async def play_track(self, interaction, url):
        vc = self.voice_clients[interaction.guild.id]
        ydl_opts = {
    "format": "bestaudio",
    "noplaylist": False,
    "quiet": True,
    "socket_timeout": 10,  # Уменьшено
    "extract_flat": True,
    "retries": 10,  # Увеличено
    "playlistend": 120,  # Уменьшено для ускорения
    "no_warnings": True,
    "proxy": "http://8.212.168.170:3128",  # Новый прокси (проверь актуальность)
}
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

        # Проверяем кэш
        cached = load_cache(url)
        if cached:
            logger.info(f"Используем кэш для {url}")
            info = cached
        else:
            func = functools.partial(ydl.extract_info, url, download=False)
            try:
                logger.info(f"Начинаем извлечение данных для URL: {url}")
                start_time = time.time()
                info = await loop.run_in_executor(None, func)
                logger.info(f"Данные извлечены за {time.time() - start_time:.2f} секунд")
                if "entries" in info:
                    save_cache(url, info)  # Сохраняем в кэш
            except Exception as e:
                await interaction.followup.send(f"Ошибка при извлечении данных: {e}")
                return

        if "entries" in info:  # Если это плейлист
            first_track = info["entries"][0]
            # Извлекаем полные метаданные только для первого трека
            ydl_opts_full = {
                "format": "bestaudio",
                "quiet": True,
                "socket_timeout": 15,
                "retries": 5,
                "no_warnings": True,
                "proxy": "http://8.212.168.170:8888",  # Тот же прокси
            }
            ydl_full = YoutubeDL(ydl_opts_full)
            func_full = functools.partial(ydl_full.extract_info, first_track["url"], download=False)
            try:
                start_time = time.time()
                first_track_info = await loop.run_in_executor(None, func_full)
                logger.info(f"Первый трек извлечён за {time.time() - start_time:.2f} секунд")
                source = first_track_info["url"]
                title = first_track_info.get("title", "Неизвестный трек")
            except Exception as e:
                await interaction.followup.send(f"Ошибка при извлечении первого трека: {e}")
                return
            # Добавляем остальные треки в очередь
            self.queue[interaction.guild.id] = [{"url": entry["url"], "title": entry.get("title", "Неизвестный трек")} for entry in info["entries"][1:]]
        else:  # Если это одиночное видео
            ydl_opts_full = {
                "format": "bestaudio",
                "quiet": True,
                "socket_timeout": 15,
                "retries": 5,
                "no_warnings": True,
                "proxy": "http://51.15.242.202:8888",  # Тот же прокси
            }
            ydl_full = YoutubeDL(ydl_opts_full)
            func_full = functools.partial(ydl_full.extract_info, url, download=False)
            try:
                start_time = time.time()
                info_full = await loop.run_in_executor(None, func_full)
                logger.info(f"Одиночный трек извлечён за {time.time() - start_time:.2f} секунд")
                source = info_full["url"]
                title = info_full.get("title", "Неизвестный трек")
            except Exception as e:
                await interaction.followup.send(f"Ошибка при извлечении трека: {e}")
                return

        self.current_tracks[interaction.guild.id] = title
        self.current_sources[interaction.guild.id] = source
        self.loop[interaction.guild.id] = False

        ffmpeg_options = {
            'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -bufsize 128k',
            'options': '-vn'
        }
        vol = self.volume.get(interaction.guild.id, 1.0)
        audio_source = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(source, **ffmpeg_options), volume=vol)
        vc.play(audio_source, after=lambda e: self.bot.loop.create_task(self.after_track(interaction.guild.id)))
        await interaction.followup.send(f"Играет сейчас: **{title}**")

    async def after_track(self, guild_id):
        vc = self.voice_clients.get(guild_id)
        if vc is None:
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
        if not vc:
            return
        ydl_opts = {
            "format": "bestaudio",
            "quiet": True,
            "socket_timeout": 15,
            "retries": 5,
            "no_warnings": True,
            "proxy": "http://51.15.242.202:8888",  # Тот же прокси
        }
        ydl = YoutubeDL(ydl_opts)
        loop = asyncio.get_event_loop()
        func = functools.partial(ydl.extract_info, url, download=False)
        try:
            start_time = time.time()
            info = await loop.run_in_executor(None, func)
            logger.info(f"Трек из очереди извлечён за {time.time() - start_time:.2f} секунд")
            source = info["url"]
            title = info.get("title", "Неизвестный трек")
        except Exception as e:
            logger.error(f"Ошибка при извлечении трека из очереди: {e}")
            self.bot.loop.create_task(self.after_track(guild_id))  # Пропускаем трек
            return

        self.current_tracks[guild_id] = title
        self.current_sources[guild_id] = source
        ffmpeg_options = {
            'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -bufsize 128k',
            'options': '-vn'
        }
        vol = self.volume.get(guild_id, 1.0)
        audio_source = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(source, **ffmpeg_options), volume=vol)
        vc.play(audio_source, after=lambda e: self.bot.loop.create_task(self.after_track(guild_id)))

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
            await vc.disconnect()
            del self.voice_clients[interaction.guild.id]
            self.current_tracks.pop(interaction.guild.id, None)
            self.current_sources.pop(interaction.guild.id, None)
            await interaction.response.send_message("Воспроизведение остановлено и бот отключен от канала.")
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
                source = self.current_sources.get(interaction.guild.id)
                if not source:
                    await interaction.response.send_message("Текущий трек не найден!")
                    return
                vc.stop()
                ffmpeg_options = {'before_options': f'-ss {seconds} -reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -bufsize 128k', 'options': '-vn'}
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
            await interaction.response.send_message(f"Удален трек: {removed_track['title']}")
        else:
            await interaction.response.send_message("Неверный индекс или очередь пуста.")

    @app_commands.command(name="volume", description="Изменяет громкость воспроизведения (0-100)")
    async def volume(self, interaction: discord.Interaction, vol: int):
        if not 0 <= vol <= 100:
            await interaction.response.send_message("Уровень громкости должен быть от 0 до 100.")
            return
        guild_id = interaction.guild.id
        self.volume[guild_id] = vol / 100.0
        if guild_id in self.voice_clients and self.current_sources.get(guild_id):
            vc = self.voice_clients[guild_id]
            if hasattr(vc.source, 'volume'):
                vc.source.volume = vol / 100.0
                await interaction.response.send_message(f"Громкость установлена на {vol}%.")
                return
        await interaction.response.send_message(f"Громкость установлена на {vol}%.")

    @app_commands.command(name="loopqueue", description="Включает или выключает повтор всей очереди")
    async def loopqueue(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        self.loop_queue[guild_id] = not self.loop_queue.get(guild_id, False)
        status = "включен" if self.loop_queue[guild_id] else "выключен"
        await interaction.response.send_message(f"Режим повтора очереди {status}.")

    @app_commands.command(name="clearqueue", description="Очищает очередь треков")
    async def clearqueue(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        self.queue[guild_id] = []
        await interaction.response.send_message("Очередь очищена.")

async def setup(bot: commands.Bot):
    await bot.add_cog(Music(bot))
    print("Команды зарегистрированы и готовы к использованию.")
