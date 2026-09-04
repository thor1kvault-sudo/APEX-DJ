import asyncio
import re
import time
import math
import logging
import urllib.parse
import json
import functools
import aiohttp
import requests
import discord
from discord.ext import commands
from discord import app_commands
import yt_dlp

from config import EMBED_COLOR, FFMPEG_OPTIONS, YTDL_FORMAT_OPTIONS, BOT_NAME

# Full yt-dlp instance (extracts stream URLs)
ytdl = yt_dlp.YoutubeDL(YTDL_FORMAT_OPTIONS)

# Fast flat-search instance (metadata only, no stream extraction = much faster)
YTDL_FLAT_OPTIONS = {**YTDL_FORMAT_OPTIONS, 'extract_flat': 'in_playlist', 'skip_download': True}
ytdl_flat = yt_dlp.YoutubeDL(YTDL_FLAT_OPTIONS)

# LRU Cache for resolved stream URLs (avoids re-extracting the same song)
@functools.lru_cache(maxsize=128)
def _cached_extract(video_url):
    """Cache yt-dlp extraction results by URL to avoid duplicate work."""
    return ytdl.extract_info(video_url, download=False)

logger = logging.getLogger(__name__)

class Track:
    def __init__(self, title, url, duration, thumbnail, requester, artist="Unknown Artist", original_url=None):
        self.title = title
        self.url = url
        self.duration = duration
        self.thumbnail = thumbnail
        self.requester = requester
        self.artist = artist
        self.original_url = original_url or url
        self.likes = 0
        self.dislikes = 0

    @classmethod
    async def from_query(cls, query, requester):
        """Resolves Spotify, YouTube, or raw text query into one or more Track objects."""
        loop = asyncio.get_event_loop()
        
        # 1. Resolve Spotify URL if applicable
        spotify_tracks = await cls.resolve_spotify(query)
        tracks_to_process = []
        
        if spotify_tracks:
            # We have resolved Spotify track metadata
            tracks_to_process = spotify_tracks
        else:
            # Not a Spotify URL or single YouTube / text query
            tracks_to_process = [{"query": query, "title": None, "artist": None, "thumbnail": None}]

        resolved_track_objects = []

        for item in tracks_to_process:
            if "query" in item and item["query"]:
                raw_user_query = item["query"]
                search_title = item.get("title")
                spotify_thumb = item.get("thumbnail")
            else:
                track_title = item.get("title", "")
                artist_name = item.get("artist", "")
                clean_title = re.sub(r'[\(\[\{].*?[\)\]\}]', '', track_title).strip()
                primary_artist = artist_name.split(',')[0].strip() if artist_name else ""
                raw_user_query = f"{clean_title} {primary_artist}".strip() or track_title
                search_title = f"{artist_name} - {track_title}" if artist_name else track_title
                spotify_thumb = item.get("thumbnail")

            is_direct_url = "query" in item and item["query"] and (
                "youtube.com" in item["query"] or 
                "youtu.be" in item["query"] or 
                item["query"].endswith(('.mp3', '.m4a', '.wav', '.flac', '.ogg'))
            )

            data = None
            if is_direct_url:
                try:
                    data = await loop.run_in_executor(None, lambda q=item["query"]: _cached_extract(q))
                except Exception as e:
                    logger.error(f"Direct stream extraction failed: {e}")
            else:
                # 1. Smart YouTube search (picks official original audio & official labels like Think Music, Sony South, etc.)
                try:
                    video_url = await loop.run_in_executor(None, lambda q=raw_user_query: cls.search_youtube_smart(q))
                    if video_url:
                        data = await loop.run_in_executor(None, lambda u=video_url: _cached_extract(u))
                except Exception as e:
                    logger.warning(f"Smart search failed for '{raw_user_query}': {e}")

                # 2. Fast single-pass fallback
                if not data:
                    try:
                        primary_query = f"ytsearch1:{raw_user_query}" if not raw_user_query.startswith(('ytsearch:', 'ytsearch1:')) else raw_user_query
                        search_res = await loop.run_in_executor(None, lambda q=primary_query: _cached_extract(q))
                        if search_res and 'entries' in search_res and search_res['entries']:
                            data = search_res['entries'][0]
                        elif search_res and search_res.get('url'):
                            data = search_res
                    except Exception as e:
                        logger.warning(f"ytsearch1 fallback failed: {e}")

                # 3. SoundCloud fallback if YouTube is unavailable
                if not data:
                    try:
                        sc_res = await loop.run_in_executor(None, lambda q=f"scsearch1:{raw_user_query}": _cached_extract(q))
                        if sc_res and 'entries' in sc_res and sc_res['entries']:
                            data = sc_res['entries'][0]
                    except Exception as sc_err:
                        logger.warning(f"SoundCloud fallback failed: {sc_err}")






            if not data:
                continue

            stream_url = data.get('url')
            title = search_title or data.get('title', 'Unknown Track')
            artist = item.get("artist") or data.get("uploader") or data.get("artist") or "Artist"
            duration = data.get('duration', 0)
            thumbnail = spotify_thumb or data.get('thumbnail') or ""
            original_url = data.get('webpage_url') or query

            track_obj = cls(
                title=title,
                url=stream_url,
                duration=duration,
                thumbnail=thumbnail,
                requester=requester,
                artist=artist,
                original_url=original_url
            )
            resolved_track_objects.append(track_obj)

        if not resolved_track_objects:
            raise ValueError(f"Could not find or stream audio for query: `{query}`")

        return resolved_track_objects

    @staticmethod
    def select_best_original_entry(entries, raw_query):
        """Scores candidate search results to prioritize official original tracks and penalize remixes/covers."""
        if not entries:
            return None
        if len(entries) == 1:
            return entries[0]

        user_wants_remix = any(w in raw_query.lower() for w in ['remix', 'slowed', 'reverb', 'dj', 'mashup', 'cover', 'bass boosted', 'lofi', 'flip', 'edit'])
        bad_keywords = ['remix', 'slowed', 'reverb', 'dj', 'bass boosted', 'mashup', 'cover', 'lofi', 'edit', 'tik tok', 're-mix', 'status video', 'flip']
        
        scored_entries = []
        for i, entry in enumerate(entries):
            if not entry:
                continue
            title = entry.get('title', '').lower()
            uploader = entry.get('uploader', '').lower()
            score = 100 - (i * 10)  # base rank score
            
            # Penalize remixes/covers if the user didn't explicitly request one
            if not user_wants_remix:
                for bad in bad_keywords:
                    if bad in title:
                        score -= 60
            
            # Reward official song / audio tags
            if 'official audio' in title or 'official music video' in title or 'official video' in title or 'official song' in title or 'original song' in title:
                score += 35
            if 'topic' in uploader or 'vevo' in uploader or 'official' in uploader or 'records' in uploader or 'music' in uploader or 'series' in uploader:
                score += 25
                
            scored_entries.append((score, entry))

        scored_entries.sort(key=lambda x: x[0], reverse=True)
        return scored_entries[0][1]

    @staticmethod
    def search_youtube_smart(query):
        """Intelligently searches YouTube for the exact original song, prioritizing official labels and penalizing remixes/covers."""
        try:
            encoded_query = urllib.parse.quote(query)
            url = f"https://www.youtube.com/results?search_query={encoded_query}"
            req = urllib.request.Request(
                url,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
                    'Accept-Language': 'en-US,en;q=0.9'
                }
            )
            html = urllib.request.urlopen(req, timeout=4).read().decode('utf-8')
            
            m = re.search(r'var ytInitialData\s*=\s*({.+?});</script>', html)
            if not m:
                m = re.search(r'window\["ytInitialData"\]\s*=\s*({.+?});', html)
            
            candidates = []
            if m:
                data = json.loads(m.group(1))
                sections = data.get('contents', {}).get('twoColumnSearchResultsRenderer', {}).get('primaryContents', {}).get('sectionListRenderer', {}).get('contents', [])
                for sec in sections:
                    item_section = sec.get('itemSectionRenderer', {}).get('contents', [])
                    for item in item_section:
                        vr = item.get('videoRenderer')
                        if not vr:
                            continue
                        vid = vr.get('videoId')
                        title = vr.get('title', {}).get('runs', [{}])[0].get('text', '')
                        channel = vr.get('ownerText', {}).get('runs', [{}])[0].get('text', '')
                        if vid and title:
                            candidates.append({
                                'id': vid,
                                'title': title,
                                'channel': channel,
                                'url': f"https://www.youtube.com/watch?v={vid}"
                            })
            
            if candidates:
                user_wants_remix = any(w in query.lower() for w in ['remix', 'slowed', 'reverb', 'dj', 'mashup', 'cover', 'bass boosted', 'lofi'])
                bad_keywords = ['remix', 'slowed', 'reverb', 'dj', 'bass boosted', 'mashup', 'cover', 'lofi', 'edit', 'tik tok', 'status', 'flip', 'ringtone', 'whatsapp', 'bgm', 'teaser', 'trailer']
                
                scored = []
                for i, c in enumerate(candidates):
                    t = c['title'].lower()
                    ch = c['channel'].lower()
                    score = 100 - (i * 5)
                    
                    # Penalize remixes/covers/edits when user wants the original
                    if not user_wants_remix:
                        for bad in bad_keywords:
                            if bad in t:
                                score -= 50
                    
                    # Boost official songs & lyric videos
                    if any(w in t for w in ['official audio', 'official music video', 'official video', 'official song', 'full song', 'lyric video', 'official lyric']):
                        score += 40
                        
                    # Boost official Indian/International music labels & topic channels
                    if any(w in ch for w in ['topic', 'vevo', 'think music', 'sony music', 'saregama', 't-series', 'aditya music', 'lahari', 'zee music', 'muzik247', 'sun nxt', 'mass tamilan', 'speed audio', 'tips', 'anirudh', 'ar rahman', 'yuvan']):
                        score += 35
                        
                    scored.append((score, c))
                
                scored.sort(key=lambda x: x[0], reverse=True)
                return scored[0][1]['url']
        except Exception as e:
            logger.warning(f"Smart YouTube search error for '{query}': {e}")
        return None


    @staticmethod
    async def resolve_spotify(url):

        """Resolves Spotify Track, Album, or Playlist URLs with triple fallback (oEmbed, Embed Scraping, OG Meta)."""
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
        }
        
        # Follow short links or spotify.link if provided
        if "spotify.link/" in url:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.head(url, headers=headers, allow_redirects=True, timeout=aiohttp.ClientTimeout(total=3)) as r:
                        url = str(r.url)
            except Exception as e:
                logger.warning(f"Failed to follow spotify short link: {e}")

        track_match = re.search(r'track/([a-zA-Z0-9]+)', url)
        album_match = re.search(r'album/([a-zA-Z0-9]+)', url)
        playlist_match = re.search(r'playlist/([a-zA-Z0-9]+)', url)

        kind = None
        item_id = None
        if track_match:
            kind = "track"
            item_id = track_match.group(1)
        elif album_match:
            kind = "album"
            item_id = album_match.group(1)
        elif playlist_match:
            kind = "playlist"
            item_id = playlist_match.group(1)
        else:
            return None

        # METHOD 1: Embed Scraping (__NEXT_DATA__ JSON - contains full artist list and track metadata)
        embed_url = f"https://open.spotify.com/embed/{kind}/{item_id}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(embed_url, headers=headers, timeout=aiohttp.ClientTimeout(total=4)) as resp:
                    if resp.status == 200:
                        text = await resp.text()
                        script_match = re.search(r'<script id="__NEXT_DATA__" type="application/json">([^<]+)</script>', text)
                        if script_match:
                            data = json.loads(script_match.group(1))
                            entity = data.get('props', {}).get('pageProps', {}).get('state', {}).get('data', {}).get('entity', {})
                            if kind == "track":
                                title = entity.get('name') or entity.get('title')
                                artists = [a.get('name') for a in entity.get('artists', []) if isinstance(a, dict) and a.get('name')]
                                artist_name = ", ".join(artists) if artists else ""
                                covers = entity.get('coverArt', {}).get('sources', [])
                                thumbnail = covers[0]['url'] if covers else ""
                                if title:
                                    return [{"title": title, "artist": artist_name, "thumbnail": thumbnail}]
                            else:
                                tracks_data = entity.get('trackList', [])
                                results = []
                                for t in tracks_data:
                                    title = t.get('title') or t.get('name')
                                    artist = t.get('subtitle') or t.get('artist', '')
                                    results.append({"title": title, "artist": artist, "thumbnail": ""})
                                if results:
                                    return results
        except Exception as e:
            logger.warning(f"Failed fetching/parsing Spotify embed: {e}")

        # METHOD 2: Official Spotify oEmbed API (Fallback for title if embed page blocked)
        if kind == "track":
            try:
                oembed_api = f"https://open.spotify.com/oembed?url=https://open.spotify.com/track/{item_id}"
                async with aiohttp.ClientSession() as session:
                    async with session.get(oembed_api, headers=headers, timeout=aiohttp.ClientTimeout(total=3)) as resp:
                        if resp.status == 200:
                            oembed_data = await resp.json()
                            title = oembed_data.get('title')
                            author_name = oembed_data.get('author_name') or ""
                            thumbnail = oembed_data.get('thumbnail_url', '')
                            if title:
                                return [{"title": title, "artist": author_name, "thumbnail": thumbnail}]
            except Exception as e:
                logger.warning(f"oEmbed API failed for Spotify track: {e}")

        return None



def create_progress_bar(current, total, length=14):
    """Creates visual progress bar matching reference screenshot UI."""
    if total <= 0:
        percent = 0
    else:
        percent = min(1.0, max(0.0, current / total))
    
    pos = int(round(percent * length))
    bar = ""
    for i in range(length):
        if i == pos:
            bar += "🔘"
        else:
            bar += "▬"
    
    mins_curr, secs_curr = divmod(int(current), 60)
    mins_tot, secs_tot = divmod(int(total), 60)
    time_str = f"{mins_curr}:{secs_curr:02d} / {mins_tot}:{secs_tot:02d}"
    
    return f"{bar} {time_str}"


class MusicControlView(discord.ui.View):
    """Interactive button layout exactly matching the user's uploaded demo image."""

    def __init__(self, player):
        super().__init__(timeout=None)
        self.player = player
        self.update_button_states()

    def update_button_states(self):
        # Row 1 Pause/Resume toggle
        if self.player.voice_client and self.player.voice_client.is_paused():
            self.pause_resume_btn.label = "Resume"
            self.pause_resume_btn.emoji = "▶"
        else:
            self.pause_resume_btn.label = "Pause"
            self.pause_resume_btn.emoji = "⏸"

        # Row 2 AutoPlay status label
        if self.player.autoplay:
            self.autoplay_btn.style = discord.ButtonStyle.green
        else:
            self.autoplay_btn.style = discord.ButtonStyle.red

        # Row 0 Loop button status label
        if self.player.loop_mode == "track":
            self.loop_status_text = "Track"
        elif self.player.loop_mode == "queue":
            self.loop_status_text = "Queue"
        else:
            self.loop_status_text = "Off"

    @discord.ui.button(label="Like", style=discord.ButtonStyle.red, emoji="❤️", row=0)
    async def like_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.player.current_track:
            self.player.current_track.likes += 1
            await interaction.response.send_message(
                f"❤️ You liked **{self.player.current_track.title}**!", ephemeral=True
            )
        else:
            await interaction.response.send_message("No track is currently playing.", ephemeral=True)

    @discord.ui.button(label="Pause", style=discord.ButtonStyle.red, emoji="⏸", row=1)
    async def pause_resume_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.player.voice_client:
            return await interaction.response.send_message("Not connected to voice channel.", ephemeral=True)

        if self.player.voice_client.is_playing():
            self.player.voice_client.pause()
            button.label = "Resume"
            button.emoji = "▶"
            await interaction.response.send_message("⏸ Playback paused.", ephemeral=True)
        elif self.player.voice_client.is_paused():
            self.player.voice_client.resume()
            button.label = "Pause"
            button.emoji = "⏸"
            await interaction.response.send_message("▶ Playback resumed.", ephemeral=True)
        else:
            await interaction.response.send_message("Nothing is playing.", ephemeral=True)
        await self.player.update_now_playing_message()

    @discord.ui.button(label="Skip", style=discord.ButtonStyle.red, emoji="⏭", row=1)
    async def skip_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.player.voice_client and (self.player.voice_client.is_playing() or self.player.voice_client.is_paused()):
            self.player.voice_client.stop()
            await interaction.response.send_message("⏭ Skipped track.", ephemeral=True)
        else:
            await interaction.response.send_message("Nothing to skip.", ephemeral=True)

    @discord.ui.button(label="Stop", style=discord.ButtonStyle.red, emoji="⏹", row=1)
    async def stop_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.player.queue.clear()
        self.player.autoplay = False
        self.player.current_track = None
        if self.player.now_playing_msg:
            try:
                await self.player.now_playing_msg.delete()
            except Exception:
                pass
            self.player.now_playing_msg = None
        if self.player.voice_client:
            await self.player.voice_client.disconnect()
            self.player.voice_client = None
        await interaction.response.send_message("⏹ Stopped playback and cleared queue.", ephemeral=True)


    @discord.ui.button(label="AutoPlay", style=discord.ButtonStyle.red, emoji="🔄", row=2)
    async def autoplay_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.player.autoplay = not self.player.autoplay
        status = "Enabled" if self.player.autoplay else "Disabled"
        button.style = discord.ButtonStyle.green if self.player.autoplay else discord.ButtonStyle.red
        await interaction.response.send_message(f"🔄 AutoPlay is now **{status}**.", ephemeral=True)
        await self.player.update_now_playing_message()

    @discord.ui.button(label="Dashboard", style=discord.ButtonStyle.red, emoji="🎛", row=2)
    async def dashboard_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="🎛 DJ Dashboard",
            color=EMBED_COLOR,
            description="Control center & current queue overview."
        )
        embed.add_field(name="Volume", value=f"{int(self.player.volume * 100)}%", inline=True)
        embed.add_field(name="Loop Mode", value=f"{self.player.loop_mode.capitalize()}", inline=True)
        embed.add_field(name="AutoPlay", value=f"{'ON' if self.player.autoplay else 'OFF'}", inline=True)
        
        queue_text = "Queue is empty."
        if self.player.queue:
            queue_text = "\n".join([f"`{i+1}.` {t.title}" for i, t in enumerate(self.player.queue[:5])])
            if len(self.player.queue) > 5:
                queue_text += f"\n*...and {len(self.player.queue) - 5} more.*"
        
        embed.add_field(name="Up Next", value=queue_text, inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Love this", style=discord.ButtonStyle.red, emoji="👍", row=3)
    async def love_this_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("👍 Glad you loved this song!", ephemeral=True)

    @discord.ui.button(label="Not for me", style=discord.ButtonStyle.red, emoji="👎", row=3)
    async def not_for_me_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("👎 Feedback recorded. We'll skip or play better tracks next!", ephemeral=True)


class MusicPlayer:
    """Manages music state per guild."""

    def __init__(self, cog, guild):
        self.cog = cog
        self.guild = guild
        self.queue = []
        self.current_track = None
        self.voice_client = None
        self.volume = 1.0
        self.loop_mode = "off"  # "off", "track", "queue"
        self.autoplay = False
        self.now_playing_msg = None
        self.start_time = 0
        self.update_task = None
        self.text_channel = None

    async def play_next(self, send_msg=False):
        if not self.voice_client or not self.voice_client.is_connected():
            return

        if self.loop_mode == "track" and self.current_track:
            track = self.current_track
        elif self.queue:
            track = self.queue.pop(0)
            if self.loop_mode == "queue" and self.current_track:
                self.queue.append(self.current_track)
        elif self.autoplay and self.current_track:
            # AutoPlay logic: fetch related track
            query = f"ytsearch:songs like {self.current_track.title} {self.current_track.artist}"
            try:
                track = await Track.from_query(query, self.cog.bot.user)
            except Exception as e:
                logger.error(f"Autoplay query failed: {e}")
                track = None
        else:
            self.current_track = None
            if self.now_playing_msg:
                try:
                    await self.now_playing_msg.delete()
                except Exception:
                    pass
                self.now_playing_msg = None
            return

        if not track:
            return

        self.current_track = track
        
        # Audio source setup
        try:
            audio_source = discord.FFmpegPCMAudio(track.url, **FFMPEG_OPTIONS)
            transformed_source = discord.PCMVolumeTransformer(audio_source, volume=self.volume)

            def after_playing(error):
                if error:
                    logger.error(f"Error in playback: {error}")
                coro = self.play_next(send_msg=True)
                fut = asyncio.run_coroutine_threadsafe(coro, self.cog.bot.loop)
                try:
                    fut.result()
                except Exception as ex:
                    logger.error(f"Error handling after_playing: {ex}")

            self.start_time = time.time()
            self.voice_client.play(transformed_source, after=after_playing)
            if send_msg:
                await self.send_now_playing_message()
        except Exception as e:
            logger.error(f"Error starting audio playback: {e}")
            if self.text_channel:
                await self.text_channel.send(f"❌ Playback error: {e}")
            await self.play_next(send_msg=True)


    async def send_now_playing_message(self):
        if not self.current_track or not self.text_channel:
            return

        embed = self.build_now_playing_embed()
        view = MusicControlView(self)

        try:
            if self.now_playing_msg:
                await self.now_playing_msg.delete()
        except Exception:
            pass

        try:
            self.now_playing_msg = await self.text_channel.send(embed=embed, view=view)
        except Exception as e:
            logger.error(f"Failed to send now playing message: {e}")

    def build_now_playing_embed(self):
        track = self.current_track
        elapsed = time.time() - self.start_time if self.voice_client and self.voice_client.is_playing() else 0
        
        embed = discord.Embed(
            title="Now playing",
            color=EMBED_COLOR
        )
        
        # Track Title / Artist
        track_link = f"[{track.title}]({track.original_url})" if track.original_url else track.title
        embed.description = f"### {track_link}\n"
        
        # Details section (exact screenshot styling)
        req_mention = track.requester.mention if hasattr(track.requester, 'mention') else str(track.requester)
        vc_name = self.voice_client.channel.name if self.voice_client and self.voice_client.channel else "Voice Channel"
        guild_name = self.guild.name
        
        embed.description += f"• **Added by** {req_mention}\n"
        embed.description += f"• 🔊 **🍀 | {guild_name}** (`{vc_name}`)\n\n"
        
        # Metadata Stats Line
        loop_str = self.loop_mode.capitalize()
        embed.description += f"Queue Size: `{len(self.queue)}` · Volume: `{int(self.volume * 100)}%` · Loop: `{loop_str}`\n\n"
        
        # Progress Bar
        progress_str = create_progress_bar(elapsed, track.duration)
        embed.description += f"{progress_str}"

        if track.thumbnail:
            embed.set_thumbnail(url=track.thumbnail)

        return embed

    async def update_now_playing_message(self):
        if self.now_playing_msg and self.current_track:
            try:
                embed = self.build_now_playing_embed()
                view = MusicControlView(self)
                await self.now_playing_msg.edit(embed=embed, view=view)
            except Exception:
                pass


class MusicCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.players = {}

    def get_player(self, guild):
        if guild.id not in self.players:
            self.players[guild.id] = MusicPlayer(self, guild)
        return self.players[guild.id]

    async def ensure_voice(self, ctx_or_interaction):
        is_interaction = isinstance(ctx_or_interaction, discord.Interaction)
        user = ctx_or_interaction.user if is_interaction else ctx_or_interaction.author
        guild = ctx_or_interaction.guild

        if not user.voice or not user.voice.channel:
            msg = "❌ You must be connected to a voice channel to use music commands!"
            if is_interaction:
                try:
                    await ctx_or_interaction.response.send_message(msg, ephemeral=True)
                except Exception:
                    await ctx_or_interaction.followup.send(msg, ephemeral=True)
            else:
                await ctx_or_interaction.send(msg)
            return None, None

        player = self.get_player(guild)
        voice_channel = user.voice.channel

        if not player.voice_client or not player.voice_client.is_connected():
            player.voice_client = await voice_channel.connect(timeout=10.0, reconnect=True, self_deaf=False)
        elif player.voice_client.channel != voice_channel:
            await player.voice_client.move_to(voice_channel)

        return player, voice_channel

    # ==================== SLASH COMMANDS ====================

    @app_commands.command(name="play", description="Play a song or playlist from YouTube or Spotify link/name.")
    @app_commands.describe(query="Song name, YouTube URL, or Spotify track/playlist link")
    async def slash_play(self, interaction: discord.Interaction, query: str):
        # 1. Immediately defer with thinking state so Discord never times out
        await interaction.response.defer(thinking=True)

        user = interaction.user
        guild = interaction.guild
        if not user.voice or not user.voice.channel:
            return await interaction.followup.send("❌ You must be connected to a voice channel first!", ephemeral=True)

        player = self.get_player(guild)
        player.text_channel = interaction.channel
        voice_channel = user.voice.channel

        # 2. Parallel connect and resolve
        async def connect_voice():
            guild_vc = guild.voice_client
            if not guild_vc or not guild_vc.is_connected():
                player.voice_client = await voice_channel.connect(timeout=8.0, reconnect=True, self_deaf=False)
            elif guild_vc.channel.id != voice_channel.id:
                await guild_vc.move_to(voice_channel)
                player.voice_client = guild_vc
            else:
                player.voice_client = guild_vc

        async def resolve_tracks():
            return await Track.from_query(query, interaction.user)


        try:
            voice_task = asyncio.create_task(connect_voice())
            track_task = asyncio.create_task(resolve_tracks())
            await voice_task
            tracks = await track_task
        except Exception as e:
            logger.error(f"Play command error: {e}")
            return await interaction.followup.send(f"❌ Failed to process: {e}")

        if not tracks:
            return await interaction.followup.send("❌ No tracks found for that query.")

        player.queue.extend(tracks)

        if not player.voice_client.is_playing() and not player.voice_client.is_paused():
            await player.play_next(send_msg=False)
            if player.current_track:
                embed = player.build_now_playing_embed()
                view = MusicControlView(player)
                try:
                    msg = await interaction.followup.send(embed=embed, view=view)
                    player.now_playing_msg = msg
                except Exception as ex:
                    logger.error(f"Followup send embed error: {ex}")
        else:
            count = len(tracks)
            msg_text = f"➕ Added **{tracks[0].title}** to queue (Position #{len(player.queue)})!" if count == 1 else f"➕ Added **{count} tracks** to queue!"
            await interaction.followup.send(msg_text)
            await player.update_now_playing_message()


    @app_commands.command(name="skip", description="Skip the current song.")
    async def slash_skip(self, interaction: discord.Interaction):
        player = self.get_player(interaction.guild)
        if player.voice_client and (player.voice_client.is_playing() or player.voice_client.is_paused()):
            player.voice_client.stop()
            await interaction.response.send_message("⏭ Skipped current song!")
        else:
            await interaction.response.send_message("❌ Nothing is currently playing.", ephemeral=True)

    @app_commands.command(name="pause", description="Pause song playback.")
    async def slash_pause(self, interaction: discord.Interaction):
        player = self.get_player(interaction.guild)
        if player.voice_client and player.voice_client.is_playing():
            player.voice_client.pause()
            await player.update_now_playing_message()
            await interaction.response.send_message("⏸ Paused playback.")
        else:
            await interaction.response.send_message("❌ Cannot pause (nothing playing or already paused).", ephemeral=True)

    @app_commands.command(name="resume", description="Resume paused playback.")
    async def slash_resume(self, interaction: discord.Interaction):
        player = self.get_player(interaction.guild)
        if player.voice_client and player.voice_client.is_paused():
            player.voice_client.resume()
            await player.update_now_playing_message()
            await interaction.response.send_message("▶ Resumed playback.")
        else:
            await interaction.response.send_message("❌ Playback is not paused.", ephemeral=True)

    @app_commands.command(name="stop", description="Stop music and clear queue.")
    async def slash_stop(self, interaction: discord.Interaction):
        player = self.get_player(interaction.guild)
        player.queue.clear()
        player.autoplay = False
        if player.voice_client:
            await player.voice_client.disconnect()
            player.voice_client = None
        await interaction.response.send_message("⏹ Stopped playing and left voice channel.")

    @app_commands.command(name="queue", description="Show current song queue.")
    async def slash_queue(self, interaction: discord.Interaction):
        player = self.get_player(interaction.guild)
        embed = discord.Embed(title="🎶 Music Queue", color=EMBED_COLOR)
        if player.current_track:
            embed.add_field(name="Now Playing", value=f"**{player.current_track.title}**", inline=False)
        
        if player.queue:
            q_list = "\n".join([f"`{i+1}.` {t.title}" for i, t in enumerate(player.queue[:10])])
            if len(player.queue) > 10:
                q_list += f"\n*...and {len(player.queue) - 10} more.*"
            embed.add_field(name="Up Next", value=q_list, inline=False)
        else:
            embed.add_field(name="Up Next", value="No songs in queue.", inline=False)

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="nowplaying", description="Show the current playing song UI.")
    async def slash_nowplaying(self, interaction: discord.Interaction):
        player = self.get_player(interaction.guild)
        if player.current_track:
            embed = player.build_now_playing_embed()
            view = MusicControlView(player)
            await interaction.response.send_message(embed=embed, view=view)
        else:
            await interaction.response.send_message("❌ Nothing is currently playing.", ephemeral=True)

    @app_commands.command(name="volume", description="Adjust playback volume (1-100%).")
    @app_commands.describe(level="Volume level from 1 to 100")
    async def slash_volume(self, interaction: discord.Interaction, level: int):
        if not (1 <= level <= 100):
            return await interaction.response.send_message("❌ Volume must be between 1 and 100.", ephemeral=True)
        player = self.get_player(interaction.guild)
        player.volume = level / 100.0
        if player.voice_client and player.voice_client.source:
            player.voice_client.source.volume = player.volume
        await player.update_now_playing_message()
        await interaction.response.send_message(f"🔊 Volume set to **{level}%**.")

    @app_commands.command(name="loop", description="Set loop mode (off / track / queue).")
    @app_commands.choices(mode=[
        app_commands.Choice(name="Off", value="off"),
        app_commands.Choice(name="Track", value="track"),
        app_commands.Choice(name="Queue", value="queue")
    ])
    async def slash_loop(self, interaction: discord.Interaction, mode: app_commands.Choice[str]):
        player = self.get_player(interaction.guild)
        player.loop_mode = mode.value
        await player.update_now_playing_message()
        await interaction.response.send_message(f"🔂 Loop mode set to **{mode.name}**.")

    @app_commands.command(name="autoplay", description="Toggle endless autoplay recommendation.")
    async def slash_autoplay(self, interaction: discord.Interaction):
        player = self.get_player(interaction.guild)
        player.autoplay = not player.autoplay
        status = "Enabled" if player.autoplay else "Disabled"
        await player.update_now_playing_message()
        await interaction.response.send_message(f"🔄 AutoPlay is now **{status}**.")

    # ==================== PREFIX COMMANDS ====================

    @commands.command(name="play", aliases=["p"])
    async def prefix_play(self, ctx, *, query: str):
        player, vc = await self.ensure_voice(ctx)
        if not player:
            return

        player.text_channel = ctx.channel
        async with ctx.typing():
            try:
                tracks = await Track.from_query(query, ctx.author)
                player.queue.extend(tracks)
                
                if not player.voice_client.is_playing() and not player.voice_client.is_paused():
                    await player.play_next()
                else:
                    count = len(tracks)
                    msg = f"➕ Added **{tracks[0].title}** to queue!" if count == 1 else f"➕ Added **{count} tracks** to queue!"
                    await ctx.send(msg)
                    await player.update_now_playing_message()
            except Exception as e:
                logger.error(f"Prefix play error: {e}")
                await ctx.send(f"❌ Error playing track: {e}")

    @commands.command(name="skip", aliases=["s"])
    async def prefix_skip(self, ctx):
        player = self.get_player(ctx.guild)
        if player.voice_client and (player.voice_client.is_playing() or player.voice_client.is_paused()):
            player.voice_client.stop()
            await ctx.send("⏭ Skipped!")
        else:
            await ctx.send("❌ Nothing playing.")

    @commands.command(name="stop")
    async def prefix_stop(self, ctx):
        player = self.get_player(ctx.guild)
        player.queue.clear()
        player.autoplay = False
        if player.voice_client:
            await player.voice_client.disconnect()
            player.voice_client = None
        await ctx.send("⏹ Stopped and left voice channel.")


async def setup(bot):
    await bot.add_cog(MusicCog(bot))
