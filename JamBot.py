import os
import discord
from discord.ext import commands
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.voice_states = True
intents.message_content = True

class JamBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="/", intents=intents, application_id="1330922461973450813")
        logger.info("Инициализация бота")

    async def setup_hook(self):
        try:
            from commands import setup
            await setup(self)
            logger.info("Команды успешно загружены")
        except Exception as e:
            logger.error(f"Ошибка в setup_hook: {e}")
            raise

    async def on_ready(self):
        logger.info(f'Бот {self.user} готов к работе!')
        try:
            synced = await self.tree.sync()
            commands_list = "\n".join([f"{cmd.name} (ID: {cmd.id})" for cmd in synced])
            logger.info(f"Синхронизировано {len(synced)} команд:\n{commands_list}")
        except Exception as e:
            logger.error(f"Ошибка синхронизации команд: {e}")

    async def on_voice_state_update(self, member, before, after):
        if member.id == self.user.id and before.channel and not after.channel:
            logger.info(f"Бот был отключён от голосового канала {before.channel.name}")

class DummyServer(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running")

def run_server():
    port = int(os.getenv("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), DummyServer)
    logger.info(f"Запуск HTTP-сервера на порту {port}")
    server.serve_forever()

try:
    threading.Thread(target=run_server, daemon=True).start()
    bot = JamBot()
    TOKEN = os.getenv("DISCORD_TOKEN")
    if not TOKEN:
        logger.error("DISCORD_TOKEN не установлен в переменных окружения!")
        raise ValueError("DISCORD_TOKEN не установлен")
    logger.info("Запуск бота")
    bot.run(TOKEN)
except Exception as e:
    logger.error(f"Ошибка при запуске бота: {e}")
    raise
    
