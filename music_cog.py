import asyncio
import math
import random
import time
from typing import Dict, Optional

import discord
from discord import app_commands
from discord.ext import commands
import yt_dlp

# Suppress yt-dlp bug reports
yt_dlp.utils.bug_reports_message = lambda: ''

# yt-dlp configuration for audio extraction
YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'extractaudio': True,
    'audioformat': 'mp3',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': False,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'ytsearch',
    'source_address': '0.0.0.0',
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)

LOFI_STREAM_URL = "https://www.youtube.com/watch?v=jfKfPfyJRdk"  # Lofi Girl 24/7 Radio


class Song:
    """Represents a music track enqueued for playback."""

    def __init__(self, data: dict, requester: discord.Member):
        self.data = data
        self.requester = requester
        self.title = data.get('title', 'Unknown Title')
        self.url = data.get('url')
        self.webpage_url = data.get('webpage_url') or data.get('url')
        self.duration_seconds = int(data.get('duration') or 0)
        self.thumbnail = data.get('thumbnail')
        self.uploader = data.get('uploader', 'Unknown Artist')

    @property
    def formatted_duration(self) -> str:
        if self.duration_seconds == 0:
            return "🔴 Live Stream"
        minutes, seconds = divmod(self.duration_seconds, 60)
        hours, minutes = divmod(minutes, 60)
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"

    @classmethod
    async def create_source(cls, query: str, requester: discord.Member, loop: asyncio.AbstractEventLoop):
        """Extracts track info using yt-dlp asynchronously."""
        data = await loop.run_in_executor(
            None, lambda: ytdl.extract_info(query, download=False)
        )

        if 'entries' in data:
            # Took first item from a playlist or search result
            data = data['entries'][0]

        return cls(data, requester)

    @classmethod
    async def create_playlist(cls, query: str, requester: discord.Member, loop: asyncio.AbstractEventLoop):
        """Extracts playlist tracks asynchronously."""
        data = await loop.run_in_executor(
            None, lambda: ytdl.extract_info(query, download=False)
        )

        songs = []
        if 'entries' in data:
            for entry in data['entries']:
                if entry:
                    songs.append(cls(entry, requester))
        else:
            songs.append(cls(data, requester))

        return songs, data.get('title', 'Playlist')


class LoopMode:
    OFF = "Off"
    TRACK = "Track"
    QUEUE = "Queue"


class GuildMusicState:
    """Tracks state per Discord Server (Guild)."""

    def __init__(self, bot: commands.Bot, guild: discord.Guild):
        self.bot = bot
        self.guild = guild
        self.queue: list[Song] = []
        self.current: Optional[Song] = None
        self.voice_client: Optional[discord.VoiceClient] = None
        self.loop_mode: str = LoopMode.OFF
        self.volume: float = 0.8
        self.start_time: float = 0.0
        self.paused_time: float = 0.0
        self.is_paused: bool = False
        self.now_playing_message: Optional[discord.Message] = None

    def get_progress(self) -> tuple[str, float]:
        """Calculates progress bar string and elapsed ratio."""
        if not self.current or self.current.duration_seconds == 0:
            return "[🔴 Live Stream]", 1.0

        if self.is_paused:
            elapsed = self.paused_time - self.start_time
        else:
            elapsed = time.time() - self.start_time

        elapsed = max(0, min(elapsed, self.current.duration_seconds))
        ratio = elapsed / self.current.duration_seconds

        bar_length = 14
        filled = int(round(ratio * bar_length))
        bar = "▬" * filled + "🔘" + "▬" * (bar_length - filled)

        cur_min, cur_sec = divmod(int(elapsed), 60)
        tot_min, tot_sec = divmod(self.current.duration_seconds, 60)
        progress_str = f"`[{bar}]` `{cur_min:02d}:{cur_sec:02d} / {tot_min:02d}:{tot_sec:02d}`"

        return progress_str, ratio


class MusicControlView(discord.ui.View):
    """Interactive Discord UI Buttons for controlling playback."""

    def __init__(self, cog: 'MusicCog', state: GuildMusicState):
        super().__init__(timeout=None)
        self.cog = cog
        self.state = state

    @discord.ui.button(emoji="⏯️", style=discord.ButtonStyle.primary, custom_id="apex_play_pause")
    async def play_pause_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.state.voice_client or not self.state.voice_client.is_connected():
            return await interaction.response.send_message("❌ I am not connected to a voice channel.", ephemeral=True)

        if self.state.voice_client.is_paused():
            self.state.voice_client.resume()
            self.state.is_paused = False
            self.state.start_time += time.time() - self.state.paused_time
            await interaction.response.send_message("▶️ Resumed playback.", ephemeral=True)
        elif self.state.voice_client.is_playing():
            self.state.voice_client.pause()
            self.state.is_paused = True
            self.state.paused_time = time.time()
            await interaction.response.send_message("⏸️ Paused playback.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Nothing is currently playing.", ephemeral=True)

    @discord.ui.button(emoji="⏭️", style=discord.ButtonStyle.secondary, custom_id="apex_skip")
    async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.state.voice_client and (self.state.voice_client.is_playing() or self.state.voice_client.is_paused()):
            self.state.voice_client.stop()
            await interaction.response.send_message("⏭️ Skipped current track.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Nothing to skip.", ephemeral=True)

    @discord.ui.button(emoji="⏹️", style=discord.ButtonStyle.danger, custom_id="apex_stop")
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.state.queue.clear()
        self.state.loop_mode = LoopMode.OFF
        if self.state.voice_client:
            self.state.voice_client.stop()
            await self.state.voice_client.disconnect()
            self.state.voice_client = None
        await interaction.response.send_message("⏹️ Stopped playback, cleared queue, and left voice channel.", ephemeral=True)

    @discord.ui.button(emoji="🔁", style=discord.ButtonStyle.secondary, custom_id="apex_loop")
    async def loop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        modes = [LoopMode.OFF, LoopMode.TRACK, LoopMode.QUEUE]
        next_index = (modes.index(self.state.loop_mode) + 1) % len(modes)
        self.state.loop_mode = modes[next_index]
        await interaction.response.send_message(f"🔁 Loop mode set to: **{self.state.loop_mode}**", ephemeral=True)

    @discord.ui.button(emoji="🔀", style=discord.ButtonStyle.secondary, custom_id="apex_shuffle")
    async def shuffle_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if len(self.state.queue) < 2:
            return await interaction.response.send_message("❌ Need at least 2 tracks in queue to shuffle.", ephemeral=True)
        random.shuffle(self.state.queue)
        await interaction.response.send_message("🔀 Queue shuffled successfully!", ephemeral=True)

    @discord.ui.button(emoji="📜", style=discord.ButtonStyle.secondary, custom_id="apex_queue")
    async def queue_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = self.cog.create_queue_embed(self.state)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(emoji="🔉", style=discord.ButtonStyle.secondary, custom_id="apex_vol_down")
    async def vol_down_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.state.volume = max(0.1, self.state.volume - 0.1)
        if self.state.voice_client and self.state.voice_client.source:
            self.state.voice_client.source.volume = self.state.volume
        await interaction.response.send_message(f"🔉 Volume decreased to **{int(self.state.volume * 100)}%**", ephemeral=True)

    @discord.ui.button(emoji="🔊", style=discord.ButtonStyle.secondary, custom_id="apex_vol_up")
    async def vol_up_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.state.volume = min(1.0, self.state.volume + 0.1)
        if self.state.voice_client and self.state.voice_client.source:
            self.state.voice_client.source.volume = self.state.volume
        await interaction.response.send_message(f"🔊 Volume increased to **{int(self.state.volume * 100)}%**", ephemeral=True)


class MusicCog(commands.Cog):
    """Core APEX DJ Music Cog handling audio playback and slash commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.states: Dict[int, GuildMusicState] = {}

    def get_state(self, guild: discord.Guild) -> GuildMusicState:
        if guild.id not in self.states:
            self.states[guild.id] = GuildMusicState(self.bot, guild)
        return self.states[guild.id]

    def create_now_playing_embed(self, state: GuildMusicState) -> discord.Embed:
        song = state.current
        if not song:
            return discord.Embed(title="APEX DJ", description="Nothing playing right now.", color=0x2b2d31)

        progress_bar, _ = state.get_progress()

        embed = discord.Embed(
            title="🎶 Now Playing",
            description=f"**[{song.title}]({song.webpage_url})**",
            color=0x5865f2
        )
        embed.set_author(name="APEX DJ • Music Player", icon_url=self.bot.user.avatar.url if self.bot.user.avatar else None)
        embed.add_field(name="Artist / Channel", value=f"`{song.uploader}`", inline=True)
        embed.add_field(name="Duration", value=f"`{song.formatted_duration}`", inline=True)
        embed.add_field(name="Requested By", value=song.requester.mention, inline=True)
        embed.add_field(name="Progress", value=progress_bar, inline=False)

        status_text = f"Volume: `{int(state.volume * 100)}%` | Loop: `{state.loop_mode}` | Queue: `{len(state.queue)} tracks`"
        embed.set_footer(text=status_text)

        if song.thumbnail:
            embed.set_thumbnail(url=song.thumbnail)

        return embed

    def create_queue_embed(self, state: GuildMusicState) -> discord.Embed:
        embed = discord.Embed(title="📜 Music Queue", color=0x5865f2)

        if state.current:
            embed.add_field(
                name="🔊 Currently Playing",
                value=f"**[{state.current.title}]({state.current.webpage_url})** | `{state.current.formatted_duration}` (Requested by {state.current.requester.mention})",
                inline=False
            )

        if not state.queue:
            embed.add_field(name="Up Next", value="*The queue is currently empty. Add tracks using `/play`!*", inline=False)
        else:
            queue_list = []
            for idx, song in enumerate(state.queue[:10], start=1):
                queue_list.append(f"`{idx}.` **[{song.title}]({song.webpage_url})** | `{song.formatted_duration}`")

            queue_str = "\n".join(queue_list)
            if len(state.queue) > 10:
                queue_str += f"\n\n*...and {len(state.queue) - 10} more track(s)*"

            embed.add_field(name="Up Next", value=queue_str, inline=False)

        embed.set_footer(text=f"Loop Mode: {state.loop_mode} | Total Tracks: {len(state.queue)}")
        return embed

    async def play_next(self, guild: discord.Guild, text_channel: Optional[discord.TextChannel] = None):
        state = self.get_state(guild)

        if not state.voice_client or not state.voice_client.is_connected():
            return

        # Handle Loop modes
        if state.current and state.loop_mode == LoopMode.TRACK:
            # Re-enqueue current track at top
            state.queue.insert(0, state.current)
        elif state.current and state.loop_mode == LoopMode.QUEUE:
            # Re-enqueue current track at bottom
            state.queue.append(state.current)

        if not state.queue:
            state.current = None
            if text_channel:
                embed = discord.Embed(
                    title="⏹️ Queue Finished",
                    description="Finished playing all songs in queue. Leaving voice channel in 3 minutes if idle.",
                    color=0xfee75c
                )
                await text_channel.send(embed=embed)

            # Schedule auto-disconnect after 3 minutes idle
            await asyncio.sleep(180)
            if state.voice_client and not state.voice_client.is_playing() and not state.queue:
                await state.voice_client.disconnect()
                state.voice_client = None
            return

        state.current = state.queue.pop(0)

        try:
            audio_source = discord.FFmpegPCMAudio(state.current.url, **FFMPEG_OPTIONS)
            transformed_source = discord.PCMVolumeTransformer(audio_source, volume=state.volume)
        except Exception as e:
            if text_channel:
                await text_channel.send(f"❌ Error loading track `{state.current.title}`: {e}")
            await self.play_next(guild, text_channel)
            return

        def after_playing(error):
            if error:
                print(f"Playback error in guild {guild.id}: {error}")
            coro = self.play_next(guild, text_channel)
            asyncio.run_coroutine_threadsafe(coro, self.bot.loop)

        state.start_time = time.time()
        state.is_paused = False
        state.voice_client.play(transformed_source, after=after_playing)

        if text_channel:
            embed = self.create_now_playing_embed(state)
            view = MusicControlView(self, state)
            state.now_playing_message = await text_channel.send(embed=embed, view=view)

    async def ensure_voice(self, interaction: discord.Interaction) -> Optional[discord.VoiceClient]:
        """Ensures the user is in a voice channel and connects the bot."""
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message("❌ You must be in a Voice Channel to use music commands!", ephemeral=True)
            return None

        voice_channel = interaction.user.voice.channel
        state = self.get_state(interaction.guild)

        if state.voice_client and state.voice_client.is_connected():
            if state.voice_client.channel.id != voice_channel.id:
                await state.voice_client.move_to(voice_channel)
        else:
            state.voice_client = await voice_channel.connect()

        return state.voice_client

    # --- Slash Commands ---

    @app_commands.command(name="play", description="Play a song or playlist from YouTube/Url")
    @app_commands.describe(query="Song title, YouTube search terms, or music URL")
    async def play_cmd(self, interaction: discord.Interaction, query: str):
        await interaction.response.defer()

        voice_client = await self.ensure_voice(interaction)
        if not voice_client:
            return

        state = self.get_state(interaction.guild)

        try:
            if "list=" in query:
                songs, playlist_title = await Song.create_playlist(query, interaction.user, self.bot.loop)
                for s in songs:
                    state.queue.append(s)

                embed = discord.Embed(
                    title="🎶 Playlist Enqueued",
                    description=f"Added **{len(songs)} tracks** from **{playlist_title}** to the queue.",
                    color=0x57f287
                )
                await interaction.followup.send(embed=embed)
            else:
                song = await Song.create_source(query, interaction.user, self.bot.loop)
                state.queue.append(song)

                if voice_client.is_playing() or voice_client.is_paused():
                    embed = discord.Embed(
                        title="🎵 Added to Queue",
                        description=f"**[{song.title}]({song.webpage_url})**",
                        color=0x57f287
                    )
                    embed.add_field(name="Position in Queue", value=f"`#{len(state.queue)}`", inline=True)
                    embed.add_field(name="Duration", value=f"`{song.formatted_duration}`", inline=True)
                    if song.thumbnail:
                        embed.set_thumbnail(url=song.thumbnail)
                    await interaction.followup.send(embed=embed)
                else:
                    embed = discord.Embed(
                        title="🔎 Loading Track",
                        description=f"Starting playback for **[{song.title}]({song.webpage_url})**...",
                        color=0x5865f2
                    )
                    await interaction.followup.send(embed=embed)

            if not voice_client.is_playing() and not voice_client.is_paused():
                await self.play_next(interaction.guild, interaction.channel)

        except Exception as e:
            await interaction.followup.send(f"❌ Could not process song query: `{e}`")

    @app_commands.command(name="lofi", description="Play 24/7 Lofi Hip Hop live stream radio")
    async def lofi_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer()
        voice_client = await self.ensure_voice(interaction)
        if not voice_client:
            return

        state = self.get_state(interaction.guild)
        song = await Song.create_source(LOFI_STREAM_URL, interaction.user, self.bot.loop)
        state.queue.insert(0, song)

        if voice_client.is_playing() or voice_client.is_paused():
            voice_client.stop()

        await interaction.followup.send("☕ Playing 24/7 Lofi Chill Radio!")
        await self.play_next(interaction.guild, interaction.channel)

    @app_commands.command(name="nowplaying", description="Show the currently playing song with interactive controls")
    async def nowplaying_cmd(self, interaction: discord.Interaction):
        state = self.get_state(interaction.guild)
        if not state.current:
            return await interaction.response.send_message("❌ Nothing is currently playing.", ephemeral=True)

        embed = self.create_now_playing_embed(state)
        view = MusicControlView(self, state)
        await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command(name="queue", description="Display the current music queue")
    async def queue_cmd(self, interaction: discord.Interaction):
        state = self.get_state(interaction.guild)
        embed = self.create_queue_embed(state)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="skip", description="Skip the current playing song")
    async def skip_cmd(self, interaction: discord.Interaction):
        state = self.get_state(interaction.guild)
        if state.voice_client and (state.voice_client.is_playing() or state.voice_client.is_paused()):
            state.voice_client.stop()
            await interaction.response.send_message("⏭️ Skipped current track.")
        else:
            await interaction.response.send_message("❌ Nothing to skip.", ephemeral=True)

    @app_commands.command(name="pause", description="Pause audio playback")
    async def pause_cmd(self, interaction: discord.Interaction):
        state = self.get_state(interaction.guild)
        if state.voice_client and state.voice_client.is_playing():
            state.voice_client.pause()
            state.is_paused = True
            state.paused_time = time.time()
            await interaction.response.send_message("⏸️ Playback paused.")
        else:
            await interaction.response.send_message("❌ Audio is not playing.", ephemeral=True)

    @app_commands.command(name="resume", description="Resume paused audio playback")
    async def resume_cmd(self, interaction: discord.Interaction):
        state = self.get_state(interaction.guild)
        if state.voice_client and state.voice_client.is_paused():
            state.voice_client.resume()
            state.is_paused = False
            state.start_time += time.time() - state.paused_time
            await interaction.response.send_message("▶️ Playback resumed.")
        else:
            await interaction.response.send_message("❌ Audio is not paused.", ephemeral=True)

    @app_commands.command(name="stop", description="Stop music, clear queue, and leave voice channel")
    async def stop_cmd(self, interaction: discord.Interaction):
        state = self.get_state(interaction.guild)
        state.queue.clear()
        state.loop_mode = LoopMode.OFF
        if state.voice_client:
            state.voice_client.stop()
            await state.voice_client.disconnect()
            state.voice_client = None
        await interaction.response.send_message("⏹️ Stopped music playback and cleared queue.")

    @app_commands.command(name="loop", description="Toggle loop mode (Off / Track / Queue)")
    @app_commands.choices(mode=[
        app_commands.Choice(name="Off", value="Off"),
        app_commands.Choice(name="Track", value="Track"),
        app_commands.Choice(name="Queue", value="Queue")
    ])
    async def loop_cmd(self, interaction: discord.Interaction, mode: app_commands.Choice[str]):
        state = self.get_state(interaction.guild)
        state.loop_mode = mode.value
        await interaction.response.send_message(f"🔁 Loop mode set to **{state.loop_mode}**.")

    @app_commands.command(name="shuffle", description="Shuffle the current song queue")
    async def shuffle_cmd(self, interaction: discord.Interaction):
        state = self.get_state(interaction.guild)
        if len(state.queue) < 2:
            return await interaction.response.send_message("❌ Need at least 2 songs in queue to shuffle.", ephemeral=True)

        random.shuffle(state.queue)
        await interaction.response.send_message("🔀 Queue shuffled!")

    @app_commands.command(name="volume", description="Set audio playback volume (1 - 100%)")
    @app_commands.describe(level="Volume level from 1 to 100")
    async def volume_cmd(self, interaction: discord.Interaction, level: int):
        if level < 1 or level > 100:
            return await interaction.response.send_message("❌ Volume level must be between 1 and 100.", ephemeral=True)

        state = self.get_state(interaction.guild)
        state.volume = level / 100.0
        if state.voice_client and state.voice_client.source:
            state.voice_client.source.volume = state.volume

        await interaction.response.send_message(f"🔊 Volume set to **{level}%**.")

    @app_commands.command(name="join", description="Join your current voice channel")
    async def join_cmd(self, interaction: discord.Interaction):
        voice_client = await self.ensure_voice(interaction)
        if voice_client:
            await interaction.response.send_message(f"🔊 Joined **{voice_client.channel.name}**!")

    @app_commands.command(name="leave", description="Disconnect from the voice channel")
    async def leave_cmd(self, interaction: discord.Interaction):
        state = self.get_state(interaction.guild)
        if state.voice_client:
            await state.voice_client.disconnect()
            state.voice_client = None
            state.queue.clear()
            await interaction.response.send_message("👋 Disconnected from voice channel.")
        else:
            await interaction.response.send_message("❌ Not connected to any voice channel.", ephemeral=True)

    @app_commands.command(name="clear", description="Clear all songs from the queue")
    async def clear_cmd(self, interaction: discord.Interaction):
        state = self.get_state(interaction.guild)
        state.queue.clear()
        await interaction.response.send_message("🗑️ Queue cleared.")

    @app_commands.command(name="remove", description="Remove a specific track from queue by index number")
    @app_commands.describe(index="Position number in queue (e.g. 1 for first item)")
    async def remove_cmd(self, interaction: discord.Interaction, index: int):
        state = self.get_state(interaction.guild)
        if index < 1 or index > len(state.queue):
            return await interaction.response.send_message("❌ Invalid index number.", ephemeral=True)

        removed_song = state.queue.pop(index - 1)
        await interaction.response.send_message(f"🗑️ Removed **{removed_song.title}** from position #{index}.")


async def setup(bot: commands.Bot):
    await bot.add_cog(MusicCog(bot))
