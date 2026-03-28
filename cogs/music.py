"""
Music cog - Music playback system with YouTube/Spotify support.
"""
import asyncio
import os
import random
import re
import shutil
from typing import Optional

import discord
import yt_dlp  # type: ignore[import-untyped]
from discord import app_commands
from discord.ext import commands

from core.helpers import save_data, mark_dirty, logger, Colors


# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────
YOUTUBE_REGEX = re.compile(
	r"(https?://)?(www\.)?(youtube\.com|youtu\.be)/(watch\?v=|embed/|v/|shorts/)?[\w-]+",
	re.IGNORECASE
)
SPOTIFY_REGEX = re.compile(
	r"(https?://)?(open\.)?spotify\.com/(track|album|playlist)/[\w]+",
	re.IGNORECASE
)

YTDL_OPTIONS = {
	"format": "bestaudio/best",
	"noplaylist": True,
	"quiet": True,
	"no_warnings": True,
	"default_search": "ytsearch",
	"source_address": "0.0.0.0",
	"extract_flat": False,
	"cookiefile": None,  # Add path to cookies.txt if needed
	"age_limit": 25,
	"geo_bypass": True,
	"ignoreerrors": True,
	"extractor_retries": 3,
	"js_runtimes": {"node": {}},  # Use Node.js for YouTube extraction
}

# FFmpeg path: check env var, then common locations, then PATH
FFMPEG_PATH = (
	os.getenv("FFMPEG_PATH") or
	shutil.which("ffmpeg") or
	r"C:\ffmpeg\ffmpeg-8.0.1-essentials_build\bin\ffmpeg.exe"  # Fallback
)

FFMPEG_OPTIONS = {
	"before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
	"options": "-vn",
	"executable": FFMPEG_PATH,
}


# ─────────────────────────────────────────────────────────────────────────────
# Helper classes
# ─────────────────────────────────────────────────────────────────────────────
class QueueChoiceView(discord.ui.View):
	"""View with buttons to choose between resuming saved queue or starting fresh."""
	def __init__(self, saved_count: int):
		super().__init__(timeout=60)
		self.choice: Optional[str] = None
		self.saved_count = saved_count

	@discord.ui.button(label="1️⃣ Resume Queue", style=discord.ButtonStyle.green)
	async def resume_button(self, interaction: discord.Interaction, button: discord.ui.Button):
		self.choice = "resume"
		self.stop()
		await interaction.response.defer()

	@discord.ui.button(label="2️⃣ Start Fresh", style=discord.ButtonStyle.red)
	async def fresh_button(self, interaction: discord.Interaction, button: discord.ui.Button):
		self.choice = "fresh"
		self.stop()
		await interaction.response.defer()

	async def on_timeout(self):
		self.choice = "timeout"


class Song:
	"""Represents a song in the queue."""
	def __init__(self, source_url: str, title: str, duration: int, thumbnail: str, webpage_url: str, requester: discord.Member):
		self.source_url = source_url
		self.title = title
		self.duration = duration
		self.thumbnail = thumbnail
		self.webpage_url = webpage_url
		self.requester = requester

	@property
	def duration_str(self) -> str:
		if self.duration:
			mins, secs = divmod(self.duration, 60)
			return f"{mins}:{secs:02d}"
		return "Unknown"


def linear_to_log_volume(linear: float) -> float:
	"""Convert linear volume (0-1) to logarithmic for natural perception."""
	if linear <= 0:
		return 0.0
	return max(0.0, min(1.0, (linear ** 2.5) * 0.5))


class MusicPlayer:
	"""Per-guild music player with queue management."""
	def __init__(self, guild: discord.Guild, bot: commands.Bot):
		self.guild = guild
		self.bot = bot
		self.queue: list[Song] = []
		self.current: Optional[Song] = None
		self.voice_client: Optional[discord.VoiceClient] = None
		self.loop = False
		self._linear_volume = 0.5
		self.dj: Optional[int] = None
		self._play_next_lock = asyncio.Lock()

	@property
	def volume(self) -> float:
		return linear_to_log_volume(self._linear_volume)

	@volume.setter
	def volume(self, value: float):
		self._linear_volume = max(0.0, min(1.0, value))

	async def play_next(self) -> bool:
		"""Play the next song in queue. Returns True if playback started successfully."""
		async with self._play_next_lock:
			if self.loop and self.current:
				song = self.current
			elif self.queue:
				song = self.queue.pop(0)
			else:
				self.current = None
				return False

			self.current = song

			# Check voice connection FIRST
			if not self.voice_client:
				logger.error("play_next called but voice_client is None")
				return False
			
			if not self.voice_client.is_connected():
				logger.error("play_next called but voice_client is not connected")
				return False

			# Refresh the audio URL (YouTube URLs expire)
			try:
				logger.info("Refreshing audio URL for: %s", song.title)
				opts = YTDL_OPTIONS.copy()
				with yt_dlp.YoutubeDL(opts) as ydl:
					info = ydl.extract_info(song.webpage_url, download=False)
					if info:
						# Handle playlist/search results
						if 'entries' in info:
							info = info['entries'][0] if info['entries'] else None
						if info and "url" in info:
							song.source_url = info["url"]
							logger.info("Got audio URL successfully")
			except Exception as e:
				logger.error("Failed to refresh audio URL: %s", e)
				# Try to skip to next song if refresh failed
				if self.queue:
					asyncio.run_coroutine_threadsafe(self.play_next(), self.bot.loop)
				return False

			if not song.source_url:
				logger.error("No source URL for song: %s", song.title)
				if self.queue:
					asyncio.run_coroutine_threadsafe(self.play_next(), self.bot.loop)
				return False

			# Double-check connection before playing
			if self.voice_client and self.voice_client.is_connected():
				try:
					logger.info("Starting FFmpeg playback...")
					source = discord.PCMVolumeTransformer(
						discord.FFmpegPCMAudio(song.source_url, **FFMPEG_OPTIONS),
						volume=self.volume
					)

					def after_playing(error):
						if error:
							logger.error("Playback error: %s", error)
						asyncio.run_coroutine_threadsafe(self.play_next(), self.bot.loop)

					self.voice_client.play(source, after=after_playing)
					logger.info("Playback started for: %s", song.title)
					asyncio.run_coroutine_threadsafe(
						self._log_now_playing(song),
						self.bot.loop
					)
					return True
				except Exception as e:
					logger.error("Failed to start playback: %s", e)
					if self.queue:
						asyncio.run_coroutine_threadsafe(self.play_next(), self.bot.loop)
					return False
			else:
				logger.error("Voice client disconnected before playback could start")
				return False

	async def _log_now_playing(self, song: Song):
		"""Log the currently playing song to the music log channel."""
		guild_id = str(self.guild.id)
		music_data = self.bot.data["music"].get(guild_id, {})
		log_channel_id = music_data.get("log_channel")

		if log_channel_id:
			channel = self.guild.get_channel(log_channel_id)
			if channel:
				embed = discord.Embed(
					title="🎵 Now Playing",
					description=f"**[{song.title}]({song.webpage_url})**",
					color=discord.Color.green()
				)
				embed.add_field(name="Duration", value=song.duration_str, inline=True)
				embed.add_field(name="Requested by", value=song.requester.mention, inline=True)
				embed.add_field(name="Queue", value=f"{len(self.queue)} songs remaining", inline=True)
				if song.thumbnail:
					embed.set_thumbnail(url=song.thumbnail)
				try:
					await channel.send(embed=embed)
				except discord.Forbidden:
					pass

	async def _log_song_added(self, song: Song, position: int):
		"""Log when a song is added to the queue."""
		guild_id = str(self.guild.id)
		music_data = self.bot.data["music"].get(guild_id, {})
		log_channel_id = music_data.get("log_channel")

		if log_channel_id:
			channel = self.guild.get_channel(log_channel_id)
			if channel:
				embed = discord.Embed(
					title="➕ Song Added to Queue",
					description=f"**[{song.title}]({song.webpage_url})**",
					color=discord.Color.blue()
				)
				embed.add_field(name="Duration", value=song.duration_str, inline=True)
				embed.add_field(name="Position", value=f"#{position}", inline=True)
				embed.add_field(name="Added by", value=song.requester.mention, inline=True)
				if song.thumbnail:
					embed.set_thumbnail(url=song.thumbnail)
				try:
					await channel.send(embed=embed)
				except discord.Forbidden:
					pass

	def stop(self):
		"""Stop playback and clear queue."""
		self.queue.clear()
		self.current = None
		self.loop = False
		if self.voice_client and self.voice_client.is_playing():
			self.voice_client.stop()

	def save_queue(self):
		"""Save the current queue to persistent storage."""
		guild_id = str(self.guild.id)
		self.bot.data["music"].setdefault(guild_id, {})

		songs_to_save = []
		if self.current:
			songs_to_save.append({
				"title": self.current.title,
				"duration": self.current.duration,
				"thumbnail": self.current.thumbnail,
				"webpage_url": self.current.webpage_url,
				"requester_id": self.current.requester.id
			})
		for song in self.queue:
			songs_to_save.append({
				"title": song.title,
				"duration": song.duration,
				"thumbnail": song.thumbnail,
				"webpage_url": song.webpage_url,
				"requester_id": song.requester.id
			})

		self.bot.data["music"][guild_id]["saved_queue"] = songs_to_save
		self.bot.data["music"][guild_id]["saved_volume"] = self._linear_volume

	def has_saved_queue(self) -> bool:
		guild_id = str(self.guild.id)
		saved = self.bot.data["music"].get(guild_id, {}).get("saved_queue", [])
		return len(saved) > 0

	def get_saved_queue_count(self) -> int:
		guild_id = str(self.guild.id)
		return len(self.bot.data["music"].get(guild_id, {}).get("saved_queue", []))

	def clear_saved_queue(self):
		guild_id = str(self.guild.id)
		if guild_id in self.bot.data["music"]:
			self.bot.data["music"][guild_id]["saved_queue"] = []


# ─────────────────────────────────────────────────────────────────────────────
# Music Cog
# ─────────────────────────────────────────────────────────────────────────────
class Music(commands.Cog):
	"""Music playback system."""

	def __init__(self, bot: commands.Bot):
		self.bot = bot
		self.players: dict[int, MusicPlayer] = {}

	def get_player(self, guild: discord.Guild) -> MusicPlayer:
		"""Get or create a music player for a guild."""
		if guild.id not in self.players:
			self.players[guild.id] = MusicPlayer(guild, self.bot)
		return self.players[guild.id]

	def can_control(self, member: discord.Member, player: MusicPlayer) -> bool:
		"""Check if a member can control music playback."""
		if member.guild_permissions.administrator:
			return True
		if member.guild_permissions.manage_guild:
			return True
		if member.guild_permissions.manage_channels:
			return True
		if player.dj == member.id:
			return True
		if player.dj is None:
			return True
		return False

	async def extract_song_info(self, url: str, requester: discord.Member) -> Optional[Song]:
		"""Extract song information from a URL using yt-dlp."""
		try:
			# Use fresh options dict to avoid state issues
			opts = YTDL_OPTIONS.copy()
			
			with yt_dlp.YoutubeDL(opts) as ydl:
				logger.info("Extracting info from: %s", url)
				info = await asyncio.get_event_loop().run_in_executor(
					None, lambda: ydl.extract_info(url, download=False)
				)
				
				if info:
					# Handle search results
					if 'entries' in info:
						info = info['entries'][0] if info['entries'] else None
					
					if info:
						song = Song(
							source_url=info.get("url", ""),
							title=info.get("title", "Unknown"),
							duration=info.get("duration", 0) or 0,
							thumbnail=info.get("thumbnail", ""),
							webpage_url=info.get("webpage_url", url),
							requester=requester
						)
						logger.info("Extracted song: %s", song.title)
						return song
				
				logger.warning("No info extracted from URL: %s", url)
		except Exception as e:
			logger.error("Failed to extract song info from %s: %s", url, str(e))
		return None

	def is_valid_url(self, url: str) -> bool:
		"""Check if URL is a valid YouTube or Spotify link."""
		return bool(YOUTUBE_REGEX.match(url) or SPOTIFY_REGEX.match(url))

	# ─────────────────────────────────────────────────────────────────────────
	# Prefix commands
	# ─────────────────────────────────────────────────────────────────────────
	@commands.command(name="play")
	async def play_prefix(self, ctx: commands.Context, *, url: str = None):
		"""Play a song from YouTube or Spotify."""
		if url is None:
			await ctx.send("Please provide a YouTube or Spotify URL. Usage: `!play <URL>`")
			return

		if not self.is_valid_url(url):
			await ctx.send("❌ Invalid URL! Only **YouTube** and **Spotify** links are accepted.")
			return

		if not ctx.author.voice or not ctx.author.voice.channel:
			await ctx.send("❌ You must be in a voice channel to use this command.")
			return

		player = self.get_player(ctx.guild)

		if not player.voice_client or not player.voice_client.is_connected():
			try:
				player.voice_client = await ctx.author.voice.channel.connect()
				player.dj = ctx.author.id
			except Exception as e:
				await ctx.send(f"❌ Failed to join voice channel: {e}")
				return

		async with ctx.typing():
			song = await self.extract_song_info(url, ctx.author)
			if not song:
				await ctx.send("❌ Failed to extract song information. Please check the URL.")
				return

			player.queue.append(song)
			position = len(player.queue)
			await player._log_song_added(song, position)

			if player.voice_client.is_playing() or player.current:
				await ctx.send(f"✅ Added to queue at position #{position}: **{song.title}** ({song.duration_str})")
			else:
				await ctx.send(f"🎵 Now playing: **{song.title}** ({song.duration_str})")
				await player.play_next()

	# ─────────────────────────────────────────────────────────────────────────
	# Slash commands
	# ─────────────────────────────────────────────────────────────────────────
	@app_commands.command(name="play", description="Play a song (YouTube/Spotify URLs only)")
	@app_commands.describe(url="YouTube or Spotify URL")
	async def play_slash(self, interaction: discord.Interaction, url: str):
		"""Slash command to play a song from YouTube or Spotify, with robust error handling and efficient logic."""
		try:
			# Quick validation checks
			if not self.is_valid_url(url):
				await interaction.response.send_message("❌ Invalid URL! Only **YouTube** and **Spotify** links are accepted.", ephemeral=True)
				return

			if not interaction.user.voice or not interaction.user.voice.channel:
				await interaction.response.send_message("❌ You must be in a voice channel to use this command.", ephemeral=True)
				return

			player = self.get_player(interaction.guild)
			needs_connect = not player.voice_client or not player.voice_client.is_connected()
			saved_queue_count = player.get_saved_queue_count()

			# Saved queue UI flow
			if needs_connect and saved_queue_count > 0:
				import random
				festive_colors = [
					discord.Color.from_rgb(255, 183, 94),   # Orange
					discord.Color.from_rgb(255, 99, 132),   # Pink
					discord.Color.from_rgb(54, 209, 220),   # Blue
					discord.Color.from_rgb(255, 234, 167),  # Yellow
					discord.Color.from_rgb(120, 255, 120),  # Green
					discord.Color.from_rgb(186, 104, 200),  # Purple
				]
				color = random.choice(festive_colors)
				music_emoji = "🎵"
				queue_emoji = "📝"
				resume_emoji = "▶️"
				start_emoji = "🆕"
				star_emoji = "✨"
				divider = "━━━━━━━━━━━━━━━━━━━━"
				view = QueueChoiceView(saved_queue_count)
				embed = discord.Embed(
					title=f"{queue_emoji} Resume Previous Queue?",
					description=(
						f"{music_emoji} **{saved_queue_count}** songs from a previous session were found!\n\n"
						f"{resume_emoji} **1️⃣ Resume Queue** — Restore saved songs + add your new song\n"
						f"{start_emoji} **2️⃣ Start Fresh** — Clear saved songs and just play your song\n\n"
						f"{divider}\n"
						f"{star_emoji} **Tip:** You can queue multiple songs and control playback with `/queue`, `/skip`, `/pause`, `/resume`! {star_emoji}"
					),
					color=color
				)
				embed.set_footer(text="Choose an option below.")
				await interaction.response.send_message(embed=embed, view=view)
				await view.wait()

				if view.choice == "timeout":
					await interaction.edit_original_response(content="⏱️ Timed out. Use `/play` again.", view=None)
					return

				voice_channel = interaction.user.voice.channel
				try:
					player.voice_client = await voice_channel.connect(timeout=10.0, reconnect=True)
					player.dj = interaction.user.id
					if not player.voice_client or not player.voice_client.is_connected():
						await interaction.edit_original_response(content="❌ Failed to connect to voice channel.", view=None)
						return
				except Exception as e:
					await interaction.edit_original_response(content=f"❌ Failed to join voice channel: {e}", view=None)
					return

				# Restore or clear saved queue
				if view.choice == "resume":
					guild_id = str(interaction.guild.id)
					saved_data = self.bot.data["music"].get(guild_id, {})
					saved_queue = saved_data.get("saved_queue", [])
					saved_volume = saved_data.get("saved_volume", 0.5)
					player._linear_volume = saved_volume
					for song_data in saved_queue:
						song = Song(
							source_url="",
							title=song_data["title"],
							duration=song_data.get("duration", 0),
							thumbnail=song_data.get("thumbnail", ""),
							webpage_url=song_data["webpage_url"],
							requester=interaction.user
						)
						player.queue.append(song)
				player.clear_saved_queue()
				mark_dirty()

				# Add new song
				new_song = await self.extract_song_info(url, interaction.user)
				if not new_song:
					await interaction.edit_original_response(content="❌ Failed to extract song information.", view=None)
					return
				player.queue.append(new_song)
				position = len(player.queue)
				await player._log_song_added(new_song, position)

				# Feedback
				if view.choice == "resume":
					await interaction.edit_original_response(
						content=f"✅ Restored **{saved_queue_count}** songs + added **{new_song.title}** at #{position}\n🎵 Starting playback...",
						view=None
					)
				else:
					await interaction.edit_original_response(
						content=f"🎵 Starting: **{new_song.title}** ({new_song.duration_str})",
						view=None
					)
				if not player.voice_client.is_playing() and not player.current:
					success = await player.play_next()
					if not success:
						await interaction.followup.send("❌ Failed to start playback. Check bot logs.")
				return

			# Normal flow - defer for long operations
			await interaction.response.defer()
			voice_channel = interaction.user.voice.channel
			if needs_connect:
				try:
					player.voice_client = await voice_channel.connect(timeout=10.0, reconnect=True)
					player.dj = interaction.user.id
					if not player.voice_client or not player.voice_client.is_connected():
						await interaction.followup.send("❌ Failed to connect to voice channel. The bot may not have permission.")
						return
				except Exception as e:
					await interaction.followup.send(f"❌ Failed to join voice channel: {e}")
					return

			song = await self.extract_song_info(url, interaction.user)
			if not song:
				await interaction.followup.send("❌ Failed to extract song information. Please check the URL.")
				return
			player.queue.append(song)
			position = len(player.queue)
			await player._log_song_added(song, position)

			if player.voice_client.is_playing() or player.current:
				await interaction.followup.send(f"✅ Added to queue at position #{position}: **{song.title}** ({song.duration_str})")
			else:
				success = await player.play_next()
				if success:
					await interaction.followup.send(f"🎵 Now playing: **{song.title}** ({song.duration_str})")
				else:
					if not player.voice_client or not player.voice_client.is_connected():
						await interaction.followup.send("❌ Lost connection to voice channel. Please try again.")
					else:
						await interaction.followup.send("❌ Failed to start playback. Check bot logs for details.")
		except Exception as exc:
			logger.error(f"Unexpected error in /play: {exc}", exc_info=True)
			try:
				if not interaction.response.is_done():
					await interaction.response.send_message("❌ An unexpected error occurred while processing your request.", ephemeral=True)
				else:
					await interaction.followup.send("❌ An unexpected error occurred while processing your request.", ephemeral=True)
			except Exception:
				pass

	@app_commands.command(name="skip", description="Skip the current song")
	async def skip_slash(self, interaction: discord.Interaction):
		player = self.get_player(interaction.guild)

		if not self.can_control(interaction.user, player):
			await interaction.response.send_message("❌ Only the DJ or moderators can skip songs.", ephemeral=True)
			return

		if not player.voice_client or not player.voice_client.is_connected():
			await interaction.response.send_message("❌ Not connected to a voice channel.", ephemeral=True)
			return

		if not player.current:
			await interaction.response.send_message("❌ Nothing is currently playing.", ephemeral=True)
			return

		skipped_title = player.current.title
		player.voice_client.stop()
		await interaction.response.send_message(f"⏭️ Skipped: **{skipped_title}**")

	@app_commands.command(name="stop", description="Stop playback and clear the queue")
	async def stop_slash(self, interaction: discord.Interaction):
		player = self.get_player(interaction.guild)

		if not self.can_control(interaction.user, player):
			await interaction.response.send_message("❌ Only the DJ or moderators can stop playback.", ephemeral=True)
			return

		if not player.voice_client or not player.voice_client.is_connected():
			await interaction.response.send_message("❌ Not connected to a voice channel.", ephemeral=True)
			return

		player.stop()
		await interaction.response.send_message("⏹️ Stopped playback and cleared the queue.")

	@app_commands.command(name="pause", description="Pause the current song")
	async def pause_slash(self, interaction: discord.Interaction):
		player = self.get_player(interaction.guild)

		if not self.can_control(interaction.user, player):
			await interaction.response.send_message("❌ Only the DJ or moderators can pause playback.", ephemeral=True)
			return

		if not player.voice_client or not player.voice_client.is_playing():
			await interaction.response.send_message("❌ Nothing is currently playing.", ephemeral=True)
			return

		player.voice_client.pause()
		await interaction.response.send_message("⏸️ Paused playback.")

	@app_commands.command(name="resume", description="Resume paused playback")
	async def resume_slash(self, interaction: discord.Interaction):
		player = self.get_player(interaction.guild)

		if not self.can_control(interaction.user, player):
			await interaction.response.send_message("❌ Only the DJ or moderators can resume playback.", ephemeral=True)
			return

		if not player.voice_client or not player.voice_client.is_paused():
			await interaction.response.send_message("❌ Playback is not paused.", ephemeral=True)
			return

		player.voice_client.resume()
		await interaction.response.send_message("▶️ Resumed playback.")

	@app_commands.command(name="queue", description="View the current music queue")
	async def queue_slash(self, interaction: discord.Interaction):
		player = self.get_player(interaction.guild)
		import random
		festive_colors = [
			discord.Color.from_rgb(255, 183, 94),   # Orange
			discord.Color.from_rgb(255, 99, 132),   # Pink
			discord.Color.from_rgb(54, 209, 220),   # Blue
			discord.Color.from_rgb(255, 234, 167),  # Yellow
			discord.Color.from_rgb(120, 255, 120),  # Green
			discord.Color.from_rgb(186, 104, 200),  # Purple
		]
		color = random.choice(festive_colors)
		music_emoji = "🎵"
		queue_emoji = "📝"
		nowplaying_emoji = "🎧"
		upnext_emoji = "⏭️"
		divider = "━━━━━━━━━━━━━━━━━━━━"
		embed = discord.Embed(
			title=f"{music_emoji} Server Music Queue",
			color=color
		)
		if player.current:
			embed.add_field(
				name=f"{nowplaying_emoji} Now Playing",
				value=(
					f"**[{player.current.title}]({player.current.webpage_url})**\n"
					f"`{player.current.duration_str}` | Requested by {player.current.requester.mention}"
				),
				inline=False
			)
		if player.queue:
			queue_text = ""
			for i, song in enumerate(player.queue[:10], 1):
				queue_text += (
					f"`{i}.` **[{song.title}]({song.webpage_url})**\n"
					f"`{song.duration_str}` | Requested by {song.requester.mention}\n"
				)
			if len(player.queue) > 10:
				queue_text += f"\n*...and {len(player.queue) - 10} more songs*"
			embed.add_field(name=f"{upnext_emoji} Up Next", value=queue_text, inline=False)
		else:
			if not player.current:
				embed.description = f"The queue is empty. Use `/play` to add songs! {music_emoji}"
		embed.set_footer(text=f"🔁 Loop: {'On' if player.loop else 'Off'} | 🔊 Volume: {int(player._linear_volume * 100)}%")
		embed.add_field(name=divider, value="Enjoy your music! 🎶", inline=False)
		await interaction.response.send_message(embed=embed)

	@app_commands.command(name="volume", description="Set playback volume (0-100)")
	@app_commands.describe(level="Volume level from 0 to 100")
	async def volume_slash(self, interaction: discord.Interaction, level: app_commands.Range[int, 0, 100]):
		player = self.get_player(interaction.guild)

		if not self.can_control(interaction.user, player):
			await interaction.response.send_message("❌ Only the DJ or moderators can change volume.", ephemeral=True)
			return

		player.volume = level / 100
		if player.voice_client and player.voice_client.source:
			player.voice_client.source.volume = player.volume

		await interaction.response.send_message(f"🔊 Volume set to **{level}%**")

	@app_commands.command(name="loop", description="Toggle loop mode for the current song")
	async def loop_slash(self, interaction: discord.Interaction):
		player = self.get_player(interaction.guild)

		if not self.can_control(interaction.user, player):
			await interaction.response.send_message("❌ Only the DJ or moderators can toggle loop.", ephemeral=True)
			return

		player.loop = not player.loop
		status = "enabled" if player.loop else "disabled"
		await interaction.response.send_message(f"🔁 Loop mode **{status}**")

	@app_commands.command(name="join", description="Make the bot join your voice channel")
	async def join_slash(self, interaction: discord.Interaction):
		if not interaction.user.voice or not interaction.user.voice.channel:
			await interaction.response.send_message("❌ You must be in a voice channel.", ephemeral=True)
			return

		player = self.get_player(interaction.guild)
		voice_channel = interaction.user.voice.channel

		if player.voice_client and player.voice_client.is_connected():
			if player.voice_client.channel == voice_channel:
				await interaction.response.send_message("✅ Already in your voice channel!", ephemeral=True)
				return
			await player.voice_client.move_to(voice_channel)
			await interaction.response.send_message(f"🔊 Moved to **{voice_channel.name}**")
		else:
			saved_count = player.get_saved_queue_count()
			if saved_count > 0:
				view = QueueChoiceView(saved_count)
				await interaction.response.send_message(
					f"📋 Found **{saved_count}** songs from a previous session!\n\n"
					f"**1️⃣ Resume Queue** - Restore the saved songs\n"
					f"**2️⃣ Start Fresh** - Clear saved songs and start new",
					view=view
				)
				await view.wait()

				if view.choice == "timeout":
					await interaction.edit_original_response(content="⏱️ Timed out. Use `/join` again to choose.", view=None)
					return

				# Show connecting message
				await interaction.edit_original_response(content="🔄 Connecting to voice channel...", view=None)
				
				try:
					player.voice_client = await voice_channel.connect(timeout=15.0, reconnect=True)
					player.dj = interaction.user.id
				except asyncio.TimeoutError:
					await interaction.edit_original_response(content="❌ Timed out connecting to voice. Check bot permissions (Connect, Speak).")
					return
				except Exception as e:
					logger.error("Voice connect error: %s", e)
					await interaction.edit_original_response(content=f"❌ Failed to connect: {e}")
					return

				if view.choice == "resume":
					guild_id = str(interaction.guild.id)
					saved_data = self.bot.data["music"].get(guild_id, {})
					saved_queue = saved_data.get("saved_queue", [])
					saved_volume = saved_data.get("saved_volume", 0.5)
					player._linear_volume = saved_volume

					for song_data in saved_queue:
						song = Song(
							source_url="",
							title=song_data["title"],
							duration=song_data.get("duration", 0),
							thumbnail=song_data.get("thumbnail", ""),
							webpage_url=song_data["webpage_url"],
							requester=interaction.user
						)
						player.queue.append(song)

					player.clear_saved_queue()
					mark_dirty()
					await interaction.edit_original_response(
						content=f"🔊 Joined **{voice_channel.name}**\n✅ Restored **{saved_count}** songs! Use `/play` to start or add more.",
						view=None
					)
					if not player.voice_client.is_playing() and not player.current:
						await player.play_next()
				else:
					player.clear_saved_queue()
					mark_dirty()
					await interaction.edit_original_response(
						content=f"🔊 Joined **{voice_channel.name}**\n🆕 Starting fresh! Use `/play` to add songs.",
						view=None
					)
			else:
				# Simple join without saved queue - defer first
				await interaction.response.defer()
				try:
					player.voice_client = await voice_channel.connect(timeout=15.0, reconnect=True)
					player.dj = interaction.user.id
					await interaction.followup.send(f"🔊 Joined **{voice_channel.name}**")
				except asyncio.TimeoutError:
					await interaction.followup.send("❌ Timed out connecting to voice. Check bot permissions (Connect, Speak).")
				except Exception as e:
					logger.error("Voice connect error: %s", e)
					await interaction.followup.send(f"❌ Failed to connect: {e}")

	@app_commands.command(name="leave", description="Make the bot leave the voice channel")
	async def leave_slash(self, interaction: discord.Interaction):
		player = self.get_player(interaction.guild)

		if not self.can_control(interaction.user, player):
			await interaction.response.send_message("❌ Only the DJ or moderators can disconnect the bot.", ephemeral=True)
			return

		if not player.voice_client or not player.voice_client.is_connected():
			await interaction.response.send_message("❌ Not connected to a voice channel.", ephemeral=True)
			return

		channel_name = player.voice_client.channel.name

		has_songs = player.current or player.queue
		if has_songs:
			player.save_queue()
			await save_data(self.bot, force=True)  # Force save queue on disconnect

		player.stop()
		await player.voice_client.disconnect()
		player.voice_client = None
		player.dj = None

		if has_songs:
			await interaction.response.send_message(f"👋 Left **{channel_name}**\n💾 Queue saved! You'll be asked to restore it when using `/join` or `/play` next time.")
		else:
			await interaction.response.send_message(f"👋 Left **{channel_name}**")

	@app_commands.command(name="shuffle", description="Shuffle the queue")
	async def shuffle_slash(self, interaction: discord.Interaction):
		player = self.get_player(interaction.guild)

		if not self.can_control(interaction.user, player):
			await interaction.response.send_message("❌ Only the DJ or moderators can shuffle the queue.", ephemeral=True)
			return

		if len(player.queue) < 2:
			await interaction.response.send_message("❌ Not enough songs in queue to shuffle.", ephemeral=True)
			return

		random.shuffle(player.queue)
		await interaction.response.send_message(f"🔀 Shuffled **{len(player.queue)}** songs in the queue!")

	@app_commands.command(name="clearqueue", description="Clear all songs from the queue")
	async def clearqueue_slash(self, interaction: discord.Interaction):
		player = self.get_player(interaction.guild)

		if not self.can_control(interaction.user, player):
			await interaction.response.send_message("❌ Only the DJ or moderators can clear the queue.", ephemeral=True)
			return

		count = len(player.queue)
		player.queue.clear()
		await interaction.response.send_message(f"🗑️ Cleared **{count}** songs from the queue.")

	@app_commands.command(name="remove", description="Remove a song from the queue by position")
	@app_commands.describe(position="Queue position (1 = first song in queue)")
	async def remove_slash(self, interaction: discord.Interaction, position: app_commands.Range[int, 1, 100]):
		player = self.get_player(interaction.guild)

		if not self.can_control(interaction.user, player):
			await interaction.response.send_message("❌ Only the DJ or moderators can remove songs.", ephemeral=True)
			return

		if position > len(player.queue):
			await interaction.response.send_message(f"❌ Invalid position. Queue only has **{len(player.queue)}** songs.", ephemeral=True)
			return

		removed = player.queue.pop(position - 1)
		await interaction.response.send_message(f"🗑️ Removed **{removed.title}** from position #{position}")

	@app_commands.command(name="setmusicchannel", description="Set the music log channel (admin only)")
	@app_commands.describe(channel="The channel for music logs and queue updates")
	@app_commands.checks.has_permissions(administrator=True)
	async def setmusicchannel_slash(self, interaction: discord.Interaction, channel: discord.TextChannel):
		guild_id = str(interaction.guild.id)
		self.bot.data["music"].setdefault(guild_id, {})
		self.bot.data["music"][guild_id]["log_channel"] = channel.id
		mark_dirty()

		overwrites = {
			interaction.guild.default_role: discord.PermissionOverwrite(
				send_messages=False,
				add_reactions=True,
				read_messages=True
			),
			interaction.guild.me: discord.PermissionOverwrite(
				send_messages=True,
				embed_links=True,
				attach_files=True
			),
		}

		try:
			await channel.edit(overwrites=overwrites)
			await interaction.response.send_message(
				f"✅ Music log channel set to {channel.mention}\n"
				f"Permissions configured: Only admins and the bot can write there.",
				ephemeral=True
			)
		except discord.Forbidden:
			await interaction.response.send_message(
				f"✅ Music log channel set to {channel.mention}\n"
				f"⚠️ Could not update channel permissions. Please configure them manually.",
				ephemeral=True
			)

	@app_commands.command(name="transferdj", description="Transfer DJ control to another user")
	@app_commands.describe(member="The user to transfer DJ to")
	async def transferdj_slash(self, interaction: discord.Interaction, member: discord.Member):
		player = self.get_player(interaction.guild)

		if not self.can_control(interaction.user, player):
			await interaction.response.send_message("❌ Only the current DJ or moderators can transfer DJ.", ephemeral=True)
			return

		if member.bot:
			await interaction.response.send_message("❌ Cannot transfer DJ to a bot.", ephemeral=True)
			return

		if member.id == interaction.user.id:
			await interaction.response.send_message("❌ You cannot transfer DJ to yourself.", ephemeral=True)
			return

		player.dj = member.id
		await interaction.response.send_message(f"🎧 {member.mention} is now the DJ!")

	@app_commands.command(name="musicstatus", description="🎵 Show music system status")
	async def musicstatus_slash(self, interaction: discord.Interaction):
		player = self.get_player(interaction.guild)
		guild_id = str(interaction.guild.id)
		music_data = self.bot.data["music"].get(guild_id, {})
		log_channel_id = music_data.get("log_channel")

		embed = discord.Embed(title="🎵 Music Status", color=Colors.MUSIC)

		if player.voice_client and player.voice_client.is_connected():
			embed.add_field(name="Connected to", value=player.voice_client.channel.mention, inline=True)
		else:
			embed.add_field(name="Connected to", value="Not connected", inline=True)

		if player.current:
			embed.add_field(name="Now Playing", value=player.current.title[:50], inline=True)
		else:
			embed.add_field(name="Now Playing", value="Nothing", inline=True)

		embed.add_field(name="Queue", value=f"{len(player.queue)} songs", inline=True)
		embed.add_field(name="Volume", value=f"{int(player._linear_volume * 100)}%", inline=True)
		embed.add_field(name="Loop", value="On" if player.loop else "Off", inline=True)

		if player.dj:
			dj_member = interaction.guild.get_member(player.dj)
			embed.add_field(name="DJ", value=dj_member.mention if dj_member else "Unknown", inline=True)
		else:
			embed.add_field(name="DJ", value="None", inline=True)

		if log_channel_id:
			log_channel = interaction.guild.get_channel(log_channel_id)
			embed.add_field(name="Log Channel", value=log_channel.mention if log_channel else "Not found", inline=True)
		else:
			embed.add_field(name="Log Channel", value="Not set", inline=True)

		saved_count = player.get_saved_queue_count()
		if saved_count > 0:
			embed.add_field(name="Saved Queue", value=f"{saved_count} songs (offered on next `/join` or `/play`)", inline=True)

		await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
	# Check for voice dependencies
	try:
		import nacl  # noqa: F401
		logger.info("PyNaCl is installed - voice encryption available")
	except ImportError:
		logger.warning("PyNaCl not installed - voice may not work! Run: pip install PyNaCl")
	
	# Check opus
	if discord.opus.is_loaded():
		logger.info("Opus codec is loaded")
	else:
		# Try to load opus
		try:
			discord.opus.load_opus("opus")
			logger.info("Opus codec loaded successfully")
		except Exception:
			logger.warning("Opus codec not loaded - voice playback may fail")
	
	await bot.add_cog(Music(bot))
