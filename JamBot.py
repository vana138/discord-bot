import os
import discord
from discord.ext import commands
import logging
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
if not DISCORD_TOKEN:
    logger.error("DISCORD_TOKEN не найден в переменных окружения!")
    raise ValueError("Укажите DISCORD_TOKEN в .env")

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
bot = commands.Bot(command_prefix='/', intents=intents)

@bot.event
async def on_ready():
    logger.info(f"Бот {bot.user} готов к работе!")
    try:
        synced = await bot.tree.sync()
        logger.info(f"Глобально синхронизировано {len(synced)} команд")
    except Exception as e:
        logger.error(f"Ошибка глобальной синхронизации команд: {e}")

async def load_cogs():
    loaded_cogs = 0
    for filename in os.listdir("./"):
        if filename.endswith(".py") and filename != "JamBot.py" and filename != "cookies.py" and filename != "deploy_bot.py":
            try:
                await bot.load_extension(filename[:-3])
                logger.info(f"Загружен модуль: {filename}")
                loaded_cogs += 1
            except Exception as e:
                logger.error(f"Ошибка загрузки модуля {filename}: {e}")
    logger.info(f"Загружено {loaded_cogs} модулей")

async def main():
    try:
        await load_cogs()
        await bot.start(DISCORD_TOKEN)
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
