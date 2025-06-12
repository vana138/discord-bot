import discord
from discord.ext import commands
import logging
import os
import asyncio
import time

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Настройка бота
intents = discord.Intents.default()
intents.voice_states = True  # Для работы с голосовыми каналами

bot = commands.Bot(command_prefix="!", intents=intents)

# Загрузка Cog
async def load():
    try:
        await bot.load_extension("commands")
        logger.info("Cog 'Music' успешно загружен")
    except Exception as e:
        logger.error(f"Ошибка загрузки Cog: {e}")

# Событие при готовности бота
@bot.event
async def on_ready():
    logger.info("Инициализация бота")
    start_time = time.time()
    await load()
    logger.info(f"Cog загружен за {time.time() - start_time:.2f} секунд")
    try:
        synced = await bot.tree.sync()
        logger.info(f"Синхронизировано {len(synced)} команд")
    except Exception as e:
        logger.error(f"Ошибка синхронизации команд: {e}")
    logger.info(f"Бот {bot.user.name}#{bot.user.discriminator} готов к работе!")

# Асинхронная главная функция
async def main():
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        logger.error("DISCORD_TOKEN не установлен. Установите его через переменные окружения.")
    else:
        logger.info("Запуск бота с токеном...")
        await bot.start(token)

# Запуск бота
if __name__ == "__main__":
    asyncio.run(main())
