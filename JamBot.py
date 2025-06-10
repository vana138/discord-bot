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
intents.message_content = True
intents.voice_states = True

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
    logger.info(f"Запуск HTTP-сервера на порту 8080")
    # Синхронизация команд (глобальная)
    try:
        synced = await bot.tree.sync()
        logger.info(f"Синхронизировано {len(synced)} команд: {[command.name for command in synced]}")
    except Exception as e:
        logger.error(f"Ошибка синхронизации команд: {e}")
    logger.info(f"Бот {bot.user.name}#{bot.user.discriminator} готов к работе!")

# Запуск бота
if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN", "your_discord_token_here")
    if not token or token == "your_discord_token_here":
        logger.error("DISCORD_TOKEN не установлен или указан неверно. Установите его через переменные окружения.")
    else:
        bot.loop.create_task(on_ready())
        bot.run(token)
