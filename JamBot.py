import os
import discord
from discord.ext import commands
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.voice_states = True
intents.message_content = True

class JamBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="/", intents=intents, application_id="1330922461973450813")

    async def setup_hook(self):
        from commands import setup
        await setup(self)

    async def on_ready(self):
        print(f'Бот {self.user} готов к работе!')
        try:
            synced = await self.tree.sync()
            commands_list = "\n".join([f"{cmd.name} (ID: {cmd.id})" for cmd in synced])
            print(f"Синхронизировано {len(synced)} команд:\n{commands_list}")
        except Exception as e:
            print(f"Ошибка синхронизации команд: {e}")

class DummyServer(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running")

def run_server():
    port = int(os.getenv("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), DummyServer)
    server.serve_forever()

threading.Thread(target=run_server, daemon=True).start()

bot = JamBot()
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise ValueError("DISCORD_TOKEN не установлен в переменных окружения!")
bot.run(TOKEN)
