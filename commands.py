import discord
from discord import app_commands
from discord.ext import commands
import yt_dlp as youtube_dl
import asyncio
import logging
import aiohttp

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.voice_clients = {}
        self.current_tracks = {}
        self.queue = {}
        self.volume = {}

    @app_commands.command(name="play", description="Воспроизводит музыку из указанного URL")
    async def play(self, interaction: discord.Interaction, url: str):
        await interaction.response.defer(thinking=True)
        
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.followup.send("Вы должны быть в голосовом канале!")
            return

        voice_channel = interaction.user.voice.channel
        guild_id = interaction.guild.id

        # Подключение к голосовому каналу
        if guild_id not in self.voice_clients:
            try:
                vc = await voice_channel.connect(timeout=5.0, reconnect=True)
                self.voice_clients[guild_id] = vc
                self.volume[guild_id] = 1.0
                logger.info(f"Подключено к голосовому каналу {voice_channel.name}")
            except Exception as e:
                logger.error(f"Ошибка подключения: {e}")
                await interaction.followup.send("Не удалось подключиться к голосовому каналу.")
                return
        else:
            vc = self.voice_clients[guild_id]

        # Если что-то уже играет, добавляем в очередь
        if vc.is_playing():
            self.queue.setdefault(guild_id, []).append({"url": url, "title": "Неизвестный трек"})
            await interaction.followup.send("Трек добавлен в очередь!")
            return

        await self.play_track(interaction, url, "Неизвестный трек")

    async def play_track(self, interaction, url: str, title: str):
        guild_id = interaction.guild.id
        vc = self.voice_clients.get(guild_id)
        if not vc or not vc.is_connected():
            await interaction.followup.send("Бот не подключен к голосовому каналу!")
            return

        # Опции для yt-dlp
        ydl_opts = {
            'format': 'bestaudio/best',
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
            'socket_timeout': 10,
        }

        try:
            with youtube_dl.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                source = info['url']
                title = info.get('title', title)
        except Exception as e:
            logger.error(f"Ошибка извлечения аудио: {e}")
            await interaction.followup.send("Не удалось загрузить аудио. Попробуйте другой URL.")
            return

        # Проверка доступности URL
        async with aiohttp.ClientSession() as session:
            try:
                async with session.head(source, timeout=5) as response:
                    if response.status != 200:
                        logger.error(f"URL недоступен: {source}, статус: {response.status}")
                        await interaction.followup.send("Не удалось загрузить аудио. Попробуйте другой URL.")
                        return
            except aiohttp.ClientError as e:
                logger.error(f"Ошибка проверки URL: {e}")
                await interaction.followup.send("Не удалось проверить аудио. Попробуйте другой URL.")
                return

        self.current_tracks[guild_id] = title
        ffmpeg_options = {
            'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
            'options': '-vn'
        }
        audio_source = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(source, **ffmpeg_options), volume=self.volume.get(guild_id, 1.0))
        vc.play(audio_source, after=lambda e: self.bot.loop.create_task(self.after_track(guild_id)))
        logger.info(f"Воспроизведение начато: {title}")
        await interaction.followup.send(f"Играет сейчас: **{title}**")

    async def after_track(self, guild_id):
        vc = self.voice_clients.get(guild_id)
        if not vc or not vc.is_connected():
            logger.info(f"Нет активного соединения для guild_id {guild_id}")
            return
        if self.queue.get(guild_id) and len(self.queue[guild_id]) > 0:
            next_track = self.queue[guild_id].pop(0)
            await self.play_track_from_url(guild_id, next_track["url"], next_track["title"])
        else:
            await vc.disconnect()
            del self.voice_clients[guild_id]
            logger.info(f"Очередь пуста, отключение от guild_id {guild_id}")

    async def play_track_from_url(self, guild_id, url, title):
        vc = self.voice_clients.get(guild_id)
        if not vc or not vc.is_connected():
            logger.error("Голосовой клиент не подключен")
            return

        ydl_opts = {
            'format': 'bestaudio/best',
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
            'socket_timeout': 10,
        }

        try:
            with youtube_dl.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                source = info['url']
                title = info.get('title', title)
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
                logger.error(f"Ошибка проверки URL: {e}")
                self.bot.loop.create_task(self.after_track(guild_id))
                return

        self.current_tracks[guild_id] = title
        ffmpeg_options = {
            'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
            'options': '-vn'
        }
        audio_source = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(source, **ffmpeg_options), volume=self.volume.get(guild_id, 1.0))
        if vc.is_playing():
            vc.stop()
        vc.play(audio_source, after=lambda e: self.bot.loop.create_task(self.after_track(guild_id)))
        logger.info(f"Воспроизведение начато: {title}")

    @app_commands.command(name="pause", description="Ставит музыку на паузу")
    async def pause(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        if guild_id in self.voice_clients:
            vc = self.voice_clients[guild_id]
            if vc.is_playing():
                vc.pause()
                await interaction.response.send_message("Музыка поставлена на паузу.")
            else:
                await interaction.response.send_message("Музыка не воспроизводится.")
        else:
            await interaction.response.send_message("Бот не подключен к голосовому каналу.")

    @app_commands.command(name="resume", description="Продолжает воспроизведение музыки")
    async def resume(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        if guild_id in self.voice_clients:
            vc = self.voice_clients[guild_id]
            if vc.is_paused():
                vc.resume()
                await interaction.response.send_message("Воспроизведение продолжено.")
            else:
                await interaction.response.send_message("Музыка уже воспроизводится.")
        else:
            await interaction.response.send_message("Бот не подключен к голосовому каналу.")

    @app_commands.command(name="stop", description="Останавливает воспроизведение и отключает бота")
    async def stop(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        if guild_id in self.voice_clients:
            vc = self.voice_clients[guild_id]
            await vc.disconnect()
            del self.voice_clients[guild_id]
            self.current_tracks.pop(guild_id, None)
            self.queue.pop(guild_id, None)
            await interaction.response.send_message("Воспроизведение остановлено и бот отключен.")
        else:
            await interaction.response.send_message("Бот не подключен к голосовому каналу.")

    @app_commands.command(name="queue", description="Добавляет трек в очередь или показывает очередь")
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

    @app_commands.command(name="clearqueue", description="Очищает очередь треков")
    async def clearqueue(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        self.queue[guild_id] = []
        await interaction.response.send_message("Очередь очищена.")

async def setup(bot):
    await bot.add_cog(Music(bot))
    logger.info("Cog 'Music' зарегистрирован")
