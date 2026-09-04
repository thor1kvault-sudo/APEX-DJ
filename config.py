import os
from dotenv import load_dotenv

load_dotenv()

# Discord Configuration
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
BOT_PREFIX = os.getenv("BOT_PREFIX", "!")
BOT_NAME = os.getenv("BOT_NAME", "APEX DJ")

# Spotify Credentials (Optional - yt-dlp can scrape metadata directly if not provided)
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID", "")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET", "")

# Visual Styling & Emojis (Matching reference screenshot design)
EMBED_COLOR = 0xED1C24  # Vibrant Red accent color matching user screenshot
DEFAULT_VOLUME = 1.0    # 100%

# FFmpeg Options - tuned for instant <50ms audio startup and stream stability
FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 2 -probesize 32768 -analyzeduration 0 -threads 4',
    'options': '-vn -sn -dn',
}


YTDL_FORMAT_OPTIONS = {
    'format': 'bestaudio[ext=m4a]/bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'geo_bypass': True,
    'socket_timeout': 6,
    'extractor_args': {
        'youtube': {
            'player_client': ['android', 'web']
        }
    }
}



