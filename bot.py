import asyncio
import os
import sys

from aiohttp import web
import discord
from discord.ext import commands
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
PORT = int(os.getenv("PORT", 8080))
COMMAND_PREFIX = os.getenv("COMMAND_PREFIX", "!")

# Set up Gateway Intents
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.guilds = True

bot = commands.Bot(command_prefix=COMMAND_PREFIX, intents=intents)


async def handle_healthcheck(request):
    """Simple HTTP endpoint for Render web service keep-alive health checks."""
    return web.Response(text="APEX DJ is online and running!", status=200)


async def start_web_server():
    """Starts a lightweight HTTP server on PORT for cloud platforms like Render."""
    app = web.Application()
    app.router.add_get('/', handle_healthcheck)
    app.router.add_get('/health', handle_healthcheck)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    print(f"[Web] Keep-alive Web Server running on port {PORT}")


@bot.event
async def on_ready():
    print("--------------------------------------------------")
    print(f"[Bot] Logged in as: {bot.user.name} (ID: {bot.user.id})")
    print(f"[Bot] PyNaCl & Voice Support: Enabled")
    print("--------------------------------------------------")

    # Set Custom Bot Activity
    activity = discord.Activity(
        type=discord.ActivityType.listening,
        name="/play | APEX DJ 🎶"
    )
    await bot.change_presence(activity=activity, status=discord.Status.online)

    # Sync Slash Commands across all servers
    try:
        synced = await bot.tree.sync()
        print(f"[Bot] Synced {len(synced)} Slash Command(s) globally.")
    except Exception as e:
        print(f"[Bot] Failed to sync slash commands: {e}")


@bot.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    """Auto-disconnect if the bot is left alone in a voice channel."""
    if member.id == bot.user.id:
        return

    # Check if voice state change happened in bot's voice channel
    guild = member.guild
    voice_client = guild.voice_client

    if voice_client and voice_client.channel:
        channel = voice_client.channel
        # Count non-bot members in channel
        human_members = [m for m in channel.members if not m.bot]
        if len(human_members) == 0:
            # Wait 30 seconds before disconnecting if no one rejoins
            await asyncio.sleep(30)
            human_members_check = [m for m in channel.members if not m.bot]
            if len(human_members_check) == 0 and voice_client.is_connected():
                await voice_client.disconnect()
                print(f"[Bot] Disconnected from empty voice channel in {guild.name}")


async def main():
    if not TOKEN or TOKEN == "your_discord_bot_token_here":
        print("❌ ERROR: DISCORD_TOKEN is missing or not configured in .env file!")
        print("Please set your DISCORD_TOKEN in .env and restart.")
        sys.exit(1)

    async with bot:
        # Load Music Cog
        await bot.load_extension("music_cog")
        
        # Start web server for cloud keep-alive
        await start_web_server()

        # Start Discord Bot
        await bot.start(TOKEN)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Bot shutting down...")
