import os
import subprocess
import discord
from discord.ext import commands



intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.voice_states = True
intents.message_content = True

class JamBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents, application_id="1330922461973450813")

    async def setup_hook(self):
        from commands import setup
        await setup(self)

    async def on_ready(self):
        print(f'Бот {self.user} готов к работе!')
        try:
            synced = await self.tree.sync()
            # Форматируем вывод команд в столбик
            commands_list = "\n".join([f"{cmd.name} (ID: {cmd.id})" for cmd in synced])
            print(f"Синхронизировано {len(synced)} команд:\n{commands_list}")
        except Exception as e:
            print(f"Ошибка синхронизации команд: {e}")
            
TOKEN = os.getenv("MTMzMDkyMjQ2MTk3MzQ1MDgxMw.GwDDOR.VxwMSg8G2F54kRNNR2wxXVOQ0vMv6NTC3KN7_g")
bot = JamBot()
bot.run(TOKEN)