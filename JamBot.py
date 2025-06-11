#JamBot.py

import discord
from discord.ext import commands
import logging
import os
import asyncio

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Настройка бота
intents = discord.Intents.default()
intents.voice_states = True  # Сохранён для работы с голосовыми каналами

bot = commands.Bot(command_prefix="!", intents=intents)

# Загрузка Cog
async def load():
    await bot.load_extension("commands")
    logger.info("Cog 'Music' успешно загружен")

# Событие при готовности бота
@bot.event
async def on_ready():
    logger.info("Инициализация бота")
    await load()
    logger.info("Запуск бота")
    logger.info("Запуск HTTP-сервера на порту 8080")
    # Синхронизация команд (глобальная)
    try:
        synced = await bot.tree.sync()
        logger.info(f"Синхронизировано {len(synced)} команд:")
        for command in synced:
            logger.info(f"- {command.name}")
    except Exception as e:
        logger.error(f"Ошибка синхронизации команд: {e}")
    logger.info(f"Бот {bot.user.name}#{bot.user.discriminator} готов к работе!")

# Асинхронная главная функция (исправлена)
async def main():
    token = os.getenv("DISCORD_TOKEN", "your_discord_token_here")
    if not token or token == "your_discord_token_here":
        logger.error("DISCORD_TOKEN не установлен или указан неверно. Установите его через переменные окружения.")
    else:
        await bot.start(token)  # Используем await bot.start() напрямую

# Запуск бота
if __name__ == "__main__":
    asyncio.run(main())
