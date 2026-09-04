import os
import sys
import asyncio
import logging
import io
import re
import discord
from discord.ext import commands

from config import DISCORD_TOKEN, BOT_PREFIX, BOT_NAME

# UTF-8 stdout setup for Windows Console to support emojis cleanly
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("APEX_DJ_BOT")

# Use Standard Intents with Voice States & Message Content explicitly enabled
intents = discord.Intents.default()
intents.voice_states = True
intents.guilds = True
intents.message_content = True


bot = commands.Bot(command_prefix=BOT_PREFIX, intents=intents)

# Regex patterns for auto link detection (matches YouTube, Spotify, spotify.link)
URL_REGEX = re.compile(
    r'https?://(?:www\.)?(?:youtube\.com|youtu\.be|open\.spotify\.com|spotify\.link)/[^\s]+'
)


@bot.event
async def on_ready():
    logger.info("==================================================")
    logger.info(f"🤖 Bot Logged In as: {bot.user.name} ({bot.user.id})")
    logger.info(f"Connected to {len(bot.guilds)} Guild(s)")
    logger.info("==================================================")

    # Sync Slash Commands globally for EVERY member in your server!
    try:
        synced = await bot.tree.sync()
        logger.info(f"Synced {len(synced)} Slash Commands globally for ALL server members!")
    except Exception as e:
        logger.error(f"Failed to sync slash commands: {e}")

    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.listening,
            name="Spotify & YouTube | Use /play"
        )
    )

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    await bot.process_commands(message)

    # Auto-play link detection for any user pasting YouTube/Spotify link
    if not message.content.startswith(BOT_PREFIX):
        match = URL_REGEX.search(message.content)
        if match:
            url = match.group(0)
            if message.author.voice and message.author.voice.channel:
                music_cog = bot.get_cog("MusicCog")
                if music_cog:
                    # Instant visual feedback so user knows bot reacted immediately
                    try:
                        await message.add_reaction("🎶")
                    except Exception:
                        pass

                    logger.info(f"Auto-detected link from {message.author.name}: {url}")
                    player = music_cog.get_player(message.guild)
                    player.text_channel = message.channel
                    voice_channel = message.author.voice.channel

                    async def connect_voice():
                        if not player.voice_client or not player.voice_client.is_connected():
                            player.voice_client = await voice_channel.connect(timeout=10.0, reconnect=True, self_deaf=False)
                        elif player.voice_client.channel != voice_channel:

                            await player.voice_client.move_to(voice_channel)

                    async def resolve_tracks():
                        from music_cog import Track
                        return await Track.from_query(url, message.author)

                    try:
                        _, tracks = await asyncio.gather(connect_voice(), resolve_tracks())
                        player.queue.extend(tracks)
                        
                        if not player.voice_client.is_playing() and not player.voice_client.is_paused():
                            await player.play_next()
                        else:
                            count = len(tracks)
                            msg = f"➕ Auto-queued: **{tracks[0].title}**" if count == 1 else f"➕ Auto-queued **{count} tracks**!"
                            await message.channel.send(msg)
                            await player.update_now_playing_message()
                    except Exception as e:
                        logger.error(f"Auto link processing failed: {e}")
                        try:
                            await message.channel.send(f"❌ Could not play track: {e}")
                        except Exception:
                            pass

from aiohttp import web

async def start_health_check_server():
    """Starts a lightweight web server on $PORT for Render health checks."""
    port = int(os.getenv("PORT", 8080))
    app = web.Application()
    app.router.add_get("/", lambda r: web.Response(text="🤖 APEX DJ Bot is running & healthy!"))
    app.router.add_get("/health", lambda r: web.Response(text="OK", status=200))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"🌐 Render Health Check HTTP Server active on port {port}")

async def main():
    if not DISCORD_TOKEN or DISCORD_TOKEN == "YOUR_DISCORD_BOT_TOKEN_HERE":
        logger.error("❌ CRITICAL: DISCORD_TOKEN is missing in .env file!")
        logger.error("Please add your Bot Token to .env before starting.")
        return

    await start_health_check_server()
    await bot.load_extension("music_cog")
    await bot.start(DISCORD_TOKEN)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot execution terminated by user.")
