import discord
from discord.ext import commands
import logging
import os
from dotenv import load_dotenv

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logger.info("Запуск JamBot версии 2025-06-13")

# Загрузка .env
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    logger.error("DISCORD_TOKEN не найден в .env")
    exit(1)

# Настройка бота
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='/', intents=intents)

@bot.event
async def on_ready():
    logger.info(f"Бот {bot.user} готов к работе!")
    try:
        bot.load_extension("commands")
        logger.info("Модуль commands загружен")
        synced = await bot.tree.sync()
        logger.info(f"Глобально синхронизировано {len(synced)} команд")
    except Exception as e:
        logger.error(f"Ошибка загрузки модуля commands: {e}")

if __name__ == "__main__":
    try:
        bot.run(TOKEN)
    except Exception as e:
        logger.error(f"Ошибка запуска бота: {e}")
