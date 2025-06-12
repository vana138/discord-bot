import discord
from discord.ext import commands
import logging
import os
from dotenv import load_dotenv

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

# Настройка бота
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='/', intents=intents)

@bot.event
async def on_ready():
    logger.info(f"Бот {bot.user} готов к работе!")
    try:
        synced = await bot.tree.sync()
        logger.info(f"Синхронизировано {len(synced)} команд")
    except Exception as e:
        logger.error(f"Ошибка синхронизации команд: {e}")

async def load_cogs():
    for filename in os.listdir("./"):
        if filename.endswith(".py") and filename != "JamBot.py" and filename != "cookies.py" and filename != "deploy_bot.py":
            try:
                await bot.load_extension(filename[:-3])
                logger.info(f"Загружен модуль: {filename}")
            except Exception as e:
                logger.error(f"Ошибка загрузки модуля {filename}: {e}")

async def main():
    await load_cogs()
    await bot.start(DISCORD_TOKEN)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())