import os
from discord.ext import commands
import discord

class JamBot(commands.Bot):
    async def setup_hook(self):
        from commands import setup
        await setup(self)
        print(f"Бот {self.user} готов к работе!")
        await self.tree.sync()
        print("Синхронизировано", len(self.tree.get_commands()), "команд:")
        for command in self.tree.get_commands():
            print(f"{command.name} (ID: {command.id})")

    async def on_ready(self):
        print(f"Бот {self.user} подключён к Discord!")

intents = discord.Intents.default()
intents.message_content = True
bot = JamBot(command_prefix='/', intents=intents)
TOKEN = os.getenv("DISCORD_TOKEN")  # Читаем токен из переменной окружения
bot.run(TOKEN)
