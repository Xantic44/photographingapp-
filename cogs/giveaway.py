"""
Giveaway Cog - Create and manage giveaways with live countdown
"""
import asyncio
import random
import re
import time
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands, tasks

from core.helpers import Colors, logger


# ═══════════════════════════════════════════════════════════════════════════
#                             GIVEAWAY VIEW
# ═══════════════════════════════════════════════════════════════════════════
class GiveawayView(discord.ui.View):
	"""Interactive giveaway view with button entry."""
	
	def __init__(self, cog, msg_id: str = None):
		super().__init__(timeout=None)
		self.cog = cog
		self.msg_id = msg_id
	
	@discord.ui.button(label="Enter Giveaway!", style=discord.ButtonStyle.success, emoji="🎉", custom_id="giveaway:enter")
	async def enter_button(self, interaction: discord.Interaction, button: discord.ui.Button):
		"""Handle giveaway entry."""
		if not self.msg_id:
			# Find msg_id from the interaction message
			self.msg_id = str(interaction.message.id)
		
		giveaways = self.cog._get_giveaways()
		data = giveaways.get(self.msg_id)
		
		if not data:
			await interaction.response.send_message("❌ This giveaway no longer exists.", ephemeral=True)
			return
		
		if data.get("ended"):
			await interaction.response.send_message("❌ This giveaway has ended!", ephemeral=True)
			return
		
		user_id = interaction.user.id
		
		# Can't enter own giveaway
		if user_id == data["host_id"]:
			await interaction.response.send_message("❌ You can't enter your own giveaway!", ephemeral=True)
			return
		
		entries = data.get("entries", [])
		
		if user_id in entries:
			# Remove entry
			entries.remove(user_id)
			data["entries"] = entries
			self.cog.bot.mark_dirty()
			await interaction.response.send_message("🗑️ You left the giveaway!", ephemeral=True)
		else:
			# Add entry
			entries.append(user_id)
			data["entries"] = entries
			self.cog.bot.mark_dirty()
			await interaction.response.send_message("🎉 You entered the giveaway! Good luck!", ephemeral=True)


# ═══════════════════════════════════════════════════════════════════════════
#                             GIVEAWAY COG
# ═══════════════════════════════════════════════════════════════════════════
class Giveaway(commands.Cog):
	"""Create and manage giveaways with live countdown."""
	
	def __init__(self, bot: commands.Bot):
		self.bot = bot
		self.check_giveaways.start()
		self.update_giveaway_timers.start()
		# Register persistent view
		self.bot.add_view(GiveawayView(self))
	
	def cog_unload(self):
		self.check_giveaways.cancel()
		self.update_giveaway_timers.cancel()
	
	def _get_giveaways(self) -> dict:
		"""Get giveaways data. Structure: {message_id: giveaway_data}"""
		if "giveaways" not in self.bot.data:
			self.bot.data["giveaways"] = {}
		return self.bot.data["giveaways"]
	
	def _parse_duration(self, duration_str: str) -> int | None:
		"""Parse duration string like '1h30m' into seconds."""
		pattern = r'(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?'
		match = re.fullmatch(pattern, duration_str.lower().strip())
		
		if not match or not any(match.groups()):
			return None
		
		days, hours, mins, secs = match.groups()
		total = 0
		if days:
			total += int(days) * 86400
		if hours:
			total += int(hours) * 3600
		if mins:
			total += int(mins) * 60
		if secs:
			total += int(secs)
		
		return total if total > 0 else None
	
	def _format_countdown(self, end_time: float) -> str:
		"""Format remaining time with visual countdown."""
		remaining = int(end_time - time.time())
		if remaining <= 0:
			return "⏰ **ENDED**"
		
		days = remaining // 86400
		hours = (remaining % 86400) // 3600
		mins = (remaining % 3600) // 60
		secs = remaining % 60
		
		if days > 0:
			return f"⏰ **{days}**d **{hours}**h **{mins}**m"
		elif hours > 0:
			return f"⏰ **{hours}**h **{mins}**m **{secs}**s"
		elif mins > 0:
			return f"⏰ **{mins}**m **{secs}**s"
		else:
			return f"⏰ **{secs}**s"
	
	def _create_progress_bar(self, total_seconds: float, elapsed_seconds: float) -> str:
		"""Create a visual progress bar for time remaining."""
		if total_seconds <= 0:
			return "░░░░░░░░░░░░░░░░░░░░"
		
		progress = min(elapsed_seconds / total_seconds, 1.0)
		filled = int(progress * 20)
		empty = 20 - filled
		
		# Use different colors based on time left
		remaining_pct = 1 - progress
		if remaining_pct > 0.5:
			bar = "🟩" * empty + "⬛" * filled
		elif remaining_pct > 0.25:
			bar = "🟨" * empty + "⬛" * filled
		else:
			bar = "🟥" * empty + "⬛" * filled
		
		return bar
	
	def _create_giveaway_embed(self, prize: str, end_time: float, start_time: float, host: discord.Member | discord.User, winners: int, entries: list = None, ended: bool = False, winner_list: list = None) -> discord.Embed:
		"""Create a beautiful giveaway embed."""
		entries = entries or []
		
		if ended:
			# Ended giveaway embed
			embed = discord.Embed(
				title="🎊 GIVEAWAY ENDED 🎊",
				color=Colors.GIVEAWAY_ENDED
			)
			
			embed.add_field(
				name="🎁 Prize",
				value=f"```{prize}```",
				inline=False
			)
			
			if winner_list:
				winner_text = "\n".join(f"🏆 {w.mention}" for w in winner_list)
				embed.add_field(
					name=f"🎉 Winner{'s' if len(winner_list) > 1 else ''}",
					value=winner_text,
					inline=False
				)
			else:
				embed.add_field(
					name="😢 No Winners",
					value="Not enough entries",
					inline=False
				)
			
			embed.add_field(
				name="📊 Stats",
				value=f"👥 **{len(entries)}** participants",
				inline=True
			)
			
		else:
			# Active giveaway embed
			embed = discord.Embed(
				title="🎉 ✨ GIVEAWAY ✨ 🎉",
				color=Colors.GIVEAWAY
			)
			
			# Prize section with styling
			embed.add_field(
				name="🎁 Prize",
				value=f"```{prize}```",
				inline=False
			)
			
			# Time remaining with visual countdown
			now = time.time()
			elapsed = now - start_time
			total = end_time - start_time
			progress_bar = self._create_progress_bar(total, elapsed)
			countdown = self._format_countdown(end_time)
			
			embed.add_field(
				name="⏳ Time Remaining",
				value=f"{countdown}\n{progress_bar}",
				inline=False
			)
			
			# Entries and winners info
			embed.add_field(
				name="👥 Entries",
				value=f"**{len(entries)}**",
				inline=True
			)
			embed.add_field(
				name="🏆 Winners",
				value=f"**{winners}**",
				inline=True
			)
			embed.add_field(
				name="🎯 Chance",
				value=f"**{min(100, round(winners / max(len(entries), 1) * 100, 1))}%**" if entries else "**100%**",
				inline=True
			)
			
			# How to enter
			embed.add_field(
				name="📝 How to Enter",
				value="Click the **Enter Giveaway!** button below!",
				inline=False
			)
		
		# Footer with host info
		embed.set_footer(
			text=f"Hosted by {host.display_name}",
			icon_url=host.display_avatar.url if hasattr(host, 'display_avatar') else None
		)
		embed.timestamp = datetime.fromtimestamp(end_time, tz=timezone.utc)
		
		return embed
	
	# ─────────────────────────────────────────────────────────────────────────
	#                              TASKS
	# ─────────────────────────────────────────────────────────────────────────
	
	@tasks.loop(seconds=10)
	async def update_giveaway_timers(self):
		"""Update giveaway embeds with live countdown."""
		giveaways = self._get_giveaways()
		
		for msg_id, data in list(giveaways.items()):
			if data.get("ended"):
				continue
			
			# Don't update if ending in less than 15 seconds (check_giveaways will handle it)
			remaining = data["end_time"] - time.time()
			if remaining < 15:
				continue
			
			try:
				guild = self.bot.get_guild(data["guild_id"])
				if not guild:
					continue
				
				channel = guild.get_channel(data["channel_id"])
				if not channel:
					continue
				
				message = await channel.fetch_message(int(msg_id))
				host = guild.get_member(data["host_id"]) or await self.bot.fetch_user(data["host_id"])
				
				embed = self._create_giveaway_embed(
					data["prize"],
					data["end_time"],
					data.get("start_time", data["end_time"] - 3600),
					host,
					data["winners"],
					entries=data.get("entries", [])
				)
				
				await message.edit(embed=embed)
				
			except Exception:
				pass  # Message might be deleted or inaccessible
			
			# Small delay between updates to avoid rate limits
			await asyncio.sleep(0.5)
	
	@update_giveaway_timers.before_loop
	async def before_update_timers(self):
		await self.bot.wait_until_ready()
	
	@tasks.loop(seconds=5)
	async def check_giveaways(self):
		"""Check for ended giveaways."""
		giveaways = self._get_giveaways()
		ended_ids = []
		
		for msg_id, data in list(giveaways.items()):
			if data.get("ended"):
				continue
			
			if time.time() >= data["end_time"]:
				await self._end_giveaway(msg_id, data)
				ended_ids.append(msg_id)
		
		if ended_ids:
			self.bot.mark_dirty()
	
	@check_giveaways.before_loop
	async def before_check_giveaways(self):
		await self.bot.wait_until_ready()
	
	async def _end_giveaway(self, msg_id: str, data: dict):
		"""End a giveaway and pick winners."""
		guild = self.bot.get_guild(data["guild_id"])
		if not guild:
			return
		
		channel = guild.get_channel(data["channel_id"])
		if not channel:
			return
		
		try:
			message = await channel.fetch_message(int(msg_id))
		except Exception:
			return  # Message deleted
		
		# Get participants from entries list
		entries = data.get("entries", [])
		participants = []
		for user_id in entries:
			member = guild.get_member(user_id)
			if member and not member.bot:
				participants.append(member)
		
		# Pick winners
		winner_count = min(data["winners"], len(participants))
		winners = random.sample(participants, winner_count) if participants else []
		
		# Update giveaway data
		data["ended"] = True
		data["winner_ids"] = [w.id for w in winners]
		
		# Update embed with disabled view
		host = guild.get_member(data["host_id"]) or await self.bot.fetch_user(data["host_id"])
		embed = self._create_giveaway_embed(
			data["prize"],
			data["end_time"],
			data.get("start_time", data["end_time"] - 3600),
			host,
			data["winners"],
			entries=entries,
			ended=True,
			winner_list=winners
		)
		
		# Create ended view with disabled button
		view = discord.ui.View()
		btn = discord.ui.Button(label="Giveaway Ended", style=discord.ButtonStyle.secondary, emoji="🔒", disabled=True)
		view.add_item(btn)
		
		try:
			await message.edit(embed=embed, view=view)
		except Exception:
			pass  # Message edit may fail
		
		# Announce winners with confetti
		if winners:
			winner_mentions = ", ".join(w.mention for w in winners)
			try:
				await channel.send(
					f"🎊🎉 **CONGRATULATIONS** 🎉🎊\n\n"
					f"{winner_mentions}\n\n"
					f"You won **{data['prize']}**!\n"
					f"🎁 Contact {host.mention} to claim your prize!",
					reference=message
				)
			except Exception:
				pass  # Channel send may fail
		else:
			try:
				await channel.send(
					f"😢 The giveaway for **{data['prize']}** ended with no valid entries.",
					reference=message
				)
			except Exception:
				pass
		
		logger.info(f"Ended giveaway {msg_id} - {len(winners)} winner(s) from {len(entries)} entries")
	
	# ─────────────────────────────────────────────────────────────────────────
	#                            COMMANDS
	# ─────────────────────────────────────────────────────────────────────────
	
	giveaway_group = app_commands.Group(name="giveaway", description="Manage giveaways")
	
	@giveaway_group.command(name="start", description="🎉 Start a new giveaway")
	@app_commands.describe(
		duration="Duration (e.g., 1h, 30m, 1d12h)",
		prize="What you're giving away",
		winners="Number of winners (default: 1)"
	)
	@app_commands.checks.has_permissions(manage_guild=True)
	async def giveaway_start(self, interaction: discord.Interaction, duration: str, prize: str, winners: int = 1):
		"""Start a new giveaway."""
		if not interaction.guild:
			await interaction.response.send_message("Use this in a server.", ephemeral=True)
			return
		
		# Parse duration
		seconds = self._parse_duration(duration)
		if not seconds:
			await interaction.response.send_message(
				"❌ Invalid duration format! Examples: `1h`, `30m`, `1d12h`, `2h30m`",
				ephemeral=True
			)
			return
		
		if seconds < 30:
			await interaction.response.send_message("❌ Giveaway must be at least 30 seconds.", ephemeral=True)
			return
		
		if seconds > 604800:  # 7 days
			await interaction.response.send_message("❌ Giveaway can't be longer than 7 days.", ephemeral=True)
			return
		
		if winners < 1 or winners > 20:
			await interaction.response.send_message("❌ Winners must be between 1 and 20.", ephemeral=True)
			return
		
		start_time = time.time()
		end_time = start_time + seconds
		
		# Create embed
		embed = self._create_giveaway_embed(prize, end_time, start_time, interaction.user, winners, entries=[])
		
		# Create view with enter button
		view = GiveawayView(self)
		
		await interaction.response.send_message("🎉 Giveaway created!", ephemeral=True)
		msg = await interaction.channel.send(embed=embed, view=view)
		
		# Update view with message ID
		view.msg_id = str(msg.id)
		
		# Store giveaway data
		giveaways = self._get_giveaways()
		giveaways[str(msg.id)] = {
			"guild_id": interaction.guild.id,
			"channel_id": interaction.channel.id,
			"host_id": interaction.user.id,
			"prize": prize[:200],
			"winners": winners,
			"start_time": start_time,
			"end_time": end_time,
			"ended": False,
			"entries": [],
			"winner_ids": []
		}
		self.bot.mark_dirty()
		
		logger.info(f"Started giveaway {msg.id} for '{prize}' ending in {duration}")
	
	@giveaway_group.command(name="end", description="⏹️ End a giveaway early")
	@app_commands.describe(message_id="ID of the giveaway message")
	@app_commands.checks.has_permissions(manage_guild=True)
	async def giveaway_end(self, interaction: discord.Interaction, message_id: str):
		"""End a giveaway early."""
		if not interaction.guild:
			await interaction.response.send_message("Use this in a server.", ephemeral=True)
			return
		
		giveaways = self._get_giveaways()
		
		if message_id not in giveaways:
			await interaction.response.send_message("❌ Giveaway not found.", ephemeral=True)
			return
		
		data = giveaways[message_id]
		
		if data["ended"]:
			await interaction.response.send_message("❌ That giveaway has already ended.", ephemeral=True)
			return
		
		await interaction.response.defer(ephemeral=True)
		await self._end_giveaway(message_id, data)
		self.bot.mark_dirty()
		
		await interaction.followup.send("✅ Giveaway ended!", ephemeral=True)
	
	@giveaway_group.command(name="reroll", description="🔄 Reroll giveaway winners")
	@app_commands.describe(message_id="ID of the giveaway message", count="Number of new winners (default: 1)")
	@app_commands.checks.has_permissions(manage_guild=True)
	async def giveaway_reroll(self, interaction: discord.Interaction, message_id: str, count: int = 1):
		"""Reroll winners for an ended giveaway."""
		if not interaction.guild:
			await interaction.response.send_message("Use this in a server.", ephemeral=True)
			return
		
		giveaways = self._get_giveaways()
		
		if message_id not in giveaways:
			await interaction.response.send_message("❌ Giveaway not found.", ephemeral=True)
			return
		
		data = giveaways[message_id]
		
		if not data["ended"]:
			await interaction.response.send_message("❌ That giveaway hasn't ended yet.", ephemeral=True)
			return
		
		# Get participants from entries (excluding previous winners)
		previous_winners = set(data.get("winner_ids", []))
		entries = data.get("entries", [])
		participants = []
		
		for user_id in entries:
			if user_id not in previous_winners:
				member = interaction.guild.get_member(user_id)
				if member and not member.bot:
					participants.append(member)
		
		if not participants:
			await interaction.response.send_message("❌ No valid participants to reroll.", ephemeral=True)
			return
		
		# Pick new winners
		winner_count = min(count, len(participants))
		winners = random.sample(participants, winner_count)
		
		winner_mentions = ", ".join(w.mention for w in winners)
		await interaction.response.send_message(
			f"🎊🎉 **REROLL** 🎉🎊\n\nNew winner(s): {winner_mentions}\n🎁 Prize: **{data['prize']}**!"
		)
	
	@giveaway_group.command(name="list", description="📋 List active giveaways")
	async def giveaway_list(self, interaction: discord.Interaction):
		"""List all active giveaways in the server."""
		if not interaction.guild:
			await interaction.response.send_message("Use this in a server.", ephemeral=True)
			return
		
		giveaways = self._get_giveaways()
		active = []
		
		for msg_id, data in giveaways.items():
			if data["guild_id"] == interaction.guild.id and not data["ended"]:
				active.append((msg_id, data))
		
		if not active:
			await interaction.response.send_message("📋 No active giveaways in this server.", ephemeral=True)
			return
		
		embed = discord.Embed(
			title="🎉 Active Giveaways",
			color=Colors.GIVEAWAY
		)
		
		for msg_id, data in active[:10]:  # Max 10
			channel = interaction.guild.get_channel(data["channel_id"])
			channel_text = channel.mention if channel else "Unknown"
			countdown = self._format_countdown(data["end_time"])
			entries = len(data.get("entries", []))
			
			embed.add_field(
				name=f"🎁 {data['prize'][:50]}",
				value=f"📍 {channel_text}\n{countdown}\n👥 {entries} entries • 🏆 {data['winners']} winner(s)\n`ID: {msg_id}`",
				inline=False
			)
		
		await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
	await bot.add_cog(Giveaway(bot))
