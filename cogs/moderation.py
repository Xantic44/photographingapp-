"""
Moderation cog - Essential moderation commands (warn, kick, ban, timeout, warnings).
Includes warning history tracking and mod action logging.
"""
from datetime import datetime, timezone, timedelta
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from core.helpers import mark_dirty, Colors


class Moderation(commands.Cog):
	"""Essential moderation commands."""

	def __init__(self, bot: commands.Bot):
		self.bot = bot
		self.bot.data.setdefault("moderation", {})

	def _get_warnings(self, guild_id: str, user_id: str) -> list:
		"""Get all warnings for a user."""
		guild_data = self.bot.data["moderation"].setdefault(guild_id, {})
		user_data = guild_data.setdefault(user_id, {"warnings": []})
		return user_data.get("warnings", [])

	def _add_warning(self, guild_id: str, user_id: str, moderator_id: int, reason: str) -> int:
		"""Add a warning and return the warning count."""
		guild_data = self.bot.data["moderation"].setdefault(guild_id, {})
		user_data = guild_data.setdefault(user_id, {"warnings": []})
		
		warning = {
			"id": len(user_data["warnings"]) + 1,
			"moderator_id": moderator_id,
			"reason": reason,
			"timestamp": datetime.now(timezone.utc).isoformat()
		}
		user_data["warnings"].append(warning)
		mark_dirty()
		return len(user_data["warnings"])

	def _clear_warnings(self, guild_id: str, user_id: str) -> int:
		"""Clear all warnings for a user. Returns number cleared."""
		guild_data = self.bot.data["moderation"].get(guild_id, {})
		user_data = guild_data.get(user_id, {"warnings": []})
		count = len(user_data.get("warnings", []))
		user_data["warnings"] = []
		mark_dirty()
		return count

	def _remove_warning(self, guild_id: str, user_id: str, warning_id: int) -> bool:
		"""Remove a specific warning by ID. Returns True if found."""
		guild_data = self.bot.data["moderation"].get(guild_id, {})
		user_data = guild_data.get(user_id, {"warnings": []})
		warnings = user_data.get("warnings", [])
		
		for i, w in enumerate(warnings):
			if w["id"] == warning_id:
				warnings.pop(i)
				mark_dirty()
				return True
		return False

	async def _log_action(self, guild: discord.Guild, embed: discord.Embed):
		"""Log moderation action to modlog channel if set."""
		modlog_config = self.bot.data.get("modlog", {}).get(str(guild.id), {})
		channel_id = modlog_config.get("channel_id")
		if channel_id:
			channel = guild.get_channel(channel_id)
			if channel:
				try:
					await channel.send(embed=embed)
				except discord.Forbidden:
					pass

	# ─────────────────────────────────────────────────────────────────────────
	# Warning Commands
	# ─────────────────────────────────────────────────────────────────────────

	@app_commands.command(name="warn", description="⚠️ Warn a user")
	@app_commands.checks.has_permissions(moderate_members=True)
	@app_commands.describe(
		member="User to warn",
		reason="Reason for the warning"
	)
	async def warn(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
		if member.bot:
			await interaction.response.send_message("❌ Cannot warn bots.", ephemeral=True)
			return
		
		if member.top_role >= interaction.user.top_role and interaction.user != interaction.guild.owner:
			await interaction.response.send_message("❌ Cannot warn someone with equal or higher role.", ephemeral=True)
			return

		guild_id = str(interaction.guild.id)
		user_id = str(member.id)
		
		warn_count = self._add_warning(guild_id, user_id, interaction.user.id, reason)

		# Create embed
		embed = discord.Embed(
			title="⚠️ Warning Issued",
			color=Colors.WARNING,
			timestamp=datetime.now(timezone.utc)
		)
		embed.set_thumbnail(url=member.display_avatar.url)
		embed.add_field(name="👤 User", value=f"{member.mention}\n`{member}`", inline=True)
		embed.add_field(name="👮 Moderator", value=f"{interaction.user.mention}", inline=True)
		embed.add_field(name="📋 Reason", value=reason, inline=False)
		embed.add_field(name="⚠️ Total Warnings", value=f"**{warn_count}**", inline=True)
		embed.set_footer(text=f"User ID: {member.id}")

		await interaction.response.send_message(embed=embed)

		# Try to DM the user
		try:
			dm_embed = discord.Embed(
				title=f"⚠️ Warning in {interaction.guild.name}",
				description=f"You have been warned by a moderator.",
				color=Colors.WARNING
			)
			dm_embed.add_field(name="📋 Reason", value=reason, inline=False)
			dm_embed.add_field(name="⚠️ Total Warnings", value=f"**{warn_count}**", inline=True)
			await member.send(embed=dm_embed)
		except discord.Forbidden:
			pass

		# Log to modlog
		await self._log_action(interaction.guild, embed)

	@app_commands.command(name="warnings", description="📋 View warnings for a user")
	@app_commands.checks.has_permissions(moderate_members=True)
	@app_commands.describe(member="User to check warnings for")
	async def warnings(self, interaction: discord.Interaction, member: discord.Member):
		guild_id = str(interaction.guild.id)
		user_id = str(member.id)
		
		warnings = self._get_warnings(guild_id, user_id)

		embed = discord.Embed(
			title=f"📋 Warnings for {member}",
			color=Colors.WARNING if warnings else Colors.SUCCESS,
			timestamp=datetime.now(timezone.utc)
		)
		embed.set_thumbnail(url=member.display_avatar.url)

		if not warnings:
			embed.description = "✅ This user has no warnings!"
		else:
			for w in warnings[-10:]:  # Show last 10
				mod = interaction.guild.get_member(w["moderator_id"])
				mod_name = str(mod) if mod else f"Unknown ({w['moderator_id']})"
				timestamp = datetime.fromisoformat(w["timestamp"])
				embed.add_field(
					name=f"#{w['id']} - <t:{int(timestamp.timestamp())}:R>",
					value=f"**Reason:** {w['reason']}\n**By:** {mod_name}",
					inline=False
				)
			
			if len(warnings) > 10:
				embed.set_footer(text=f"Showing 10/{len(warnings)} warnings")
			else:
				embed.set_footer(text=f"Total: {len(warnings)} warning(s)")

		await interaction.response.send_message(embed=embed)

	@app_commands.command(name="clearwarnings", description="🗑️ Clear all warnings for a user")
	@app_commands.checks.has_permissions(administrator=True)
	@app_commands.describe(member="User to clear warnings for")
	async def clearwarnings(self, interaction: discord.Interaction, member: discord.Member):
		guild_id = str(interaction.guild.id)
		user_id = str(member.id)
		
		count = self._clear_warnings(guild_id, user_id)

		embed = discord.Embed(
			title="🗑️ Warnings Cleared",
			description=f"Removed **{count}** warning(s) from {member.mention}",
			color=Colors.SUCCESS,
			timestamp=datetime.now(timezone.utc)
		)
		embed.set_footer(text=f"Cleared by {interaction.user}")
		
		await interaction.response.send_message(embed=embed)

	@app_commands.command(name="delwarn", description="❌ Delete a specific warning by ID")
	@app_commands.checks.has_permissions(moderate_members=True)
	@app_commands.describe(
		member="User to remove warning from",
		warning_id="Warning ID number to remove"
	)
	async def delwarn(self, interaction: discord.Interaction, member: discord.Member, warning_id: int):
		guild_id = str(interaction.guild.id)
		user_id = str(member.id)
		
		if self._remove_warning(guild_id, user_id, warning_id):
			embed = discord.Embed(
				title="✅ Warning Removed",
				description=f"Removed warning #{warning_id} from {member.mention}",
				color=Colors.SUCCESS
			)
		else:
			embed = discord.Embed(
				title="❌ Warning Not Found",
				description=f"No warning with ID #{warning_id} found for {member.mention}",
				color=Colors.ERROR
			)
		
		await interaction.response.send_message(embed=embed)

	# ─────────────────────────────────────────────────────────────────────────
	# Kick Command
	# ─────────────────────────────────────────────────────────────────────────

	@app_commands.command(name="kick", description="👢 Kick a user from the server")
	@app_commands.checks.has_permissions(kick_members=True)
	@app_commands.describe(
		member="User to kick",
		reason="Reason for the kick"
	)
	async def kick(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
		if member.bot and not interaction.user.guild_permissions.administrator:
			await interaction.response.send_message("❌ Cannot kick bots without admin permission.", ephemeral=True)
			return
		
		if member.top_role >= interaction.user.top_role and interaction.user != interaction.guild.owner:
			await interaction.response.send_message("❌ Cannot kick someone with equal or higher role.", ephemeral=True)
			return

		if not interaction.guild.me.guild_permissions.kick_members:
			await interaction.response.send_message("❌ I don't have permission to kick members.", ephemeral=True)
			return

		if member.top_role >= interaction.guild.me.top_role:
			await interaction.response.send_message("❌ Cannot kick someone with a role higher than mine.", ephemeral=True)
			return

		# Try to DM before kick
		try:
			dm_embed = discord.Embed(
				title=f"👢 Kicked from {interaction.guild.name}",
				description=f"You have been kicked from the server.",
				color=Colors.ERROR
			)
			dm_embed.add_field(name="📋 Reason", value=reason, inline=False)
			await member.send(embed=dm_embed)
		except discord.Forbidden:
			pass

		await member.kick(reason=f"{reason} | By: {interaction.user}")

		embed = discord.Embed(
			title="👢 User Kicked",
			color=Colors.ERROR,
			timestamp=datetime.now(timezone.utc)
		)
		embed.set_thumbnail(url=member.display_avatar.url)
		embed.add_field(name="👤 User", value=f"{member.mention}\n`{member}`", inline=True)
		embed.add_field(name="👮 Moderator", value=f"{interaction.user.mention}", inline=True)
		embed.add_field(name="📋 Reason", value=reason, inline=False)
		embed.set_footer(text=f"User ID: {member.id}")

		await interaction.response.send_message(embed=embed)
		await self._log_action(interaction.guild, embed)

	# ─────────────────────────────────────────────────────────────────────────
	# Ban Commands
	# ─────────────────────────────────────────────────────────────────────────

	@app_commands.command(name="ban", description="🔨 Ban a user from the server")
	@app_commands.checks.has_permissions(ban_members=True)
	@app_commands.describe(
		member="User to ban",
		reason="Reason for the ban",
		delete_days="Days of messages to delete (0-7)"
	)
	async def ban(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided", delete_days: int = 0):
		if member.id == interaction.user.id:
			await interaction.response.send_message("❌ You cannot ban yourself.", ephemeral=True)
			return
		
		if member.top_role >= interaction.user.top_role and interaction.user != interaction.guild.owner:
			await interaction.response.send_message("❌ Cannot ban someone with equal or higher role.", ephemeral=True)
			return

		if not interaction.guild.me.guild_permissions.ban_members:
			await interaction.response.send_message("❌ I don't have permission to ban members.", ephemeral=True)
			return

		if member.top_role >= interaction.guild.me.top_role:
			await interaction.response.send_message("❌ Cannot ban someone with a role higher than mine.", ephemeral=True)
			return

		delete_days = max(0, min(7, delete_days))

		# Try to DM before ban
		try:
			dm_embed = discord.Embed(
				title=f"🔨 Banned from {interaction.guild.name}",
				description=f"You have been banned from the server.",
				color=0x000000
			)
			dm_embed.add_field(name="📋 Reason", value=reason, inline=False)
			await member.send(embed=dm_embed)
		except discord.Forbidden:
			pass

		await member.ban(reason=f"{reason} | By: {interaction.user}", delete_message_days=delete_days)

		embed = discord.Embed(
			title="🔨 User Banned",
			color=0x000000,
			timestamp=datetime.now(timezone.utc)
		)
		embed.set_thumbnail(url=member.display_avatar.url)
		embed.add_field(name="👤 User", value=f"{member.mention}\n`{member}`", inline=True)
		embed.add_field(name="👮 Moderator", value=f"{interaction.user.mention}", inline=True)
		embed.add_field(name="📋 Reason", value=reason, inline=False)
		if delete_days > 0:
			embed.add_field(name="🗑️ Messages Deleted", value=f"Last {delete_days} day(s)", inline=True)
		embed.set_footer(text=f"User ID: {member.id}")

		await interaction.response.send_message(embed=embed)
		await self._log_action(interaction.guild, embed)

	@app_commands.command(name="unban", description="🔓 Unban a user by ID")
	@app_commands.checks.has_permissions(ban_members=True)
	@app_commands.describe(
		user_id="User ID to unban",
		reason="Reason for the unban"
	)
	async def unban(self, interaction: discord.Interaction, user_id: str, reason: str = "No reason provided"):
		try:
			uid = int(user_id.strip())
		except ValueError:
			await interaction.response.send_message("❌ Invalid user ID.", ephemeral=True)
			return

		try:
			ban_entry = await interaction.guild.fetch_ban(discord.Object(id=uid))
			user = ban_entry.user
		except discord.NotFound:
			await interaction.response.send_message("❌ This user is not banned.", ephemeral=True)
			return

		await interaction.guild.unban(user, reason=f"{reason} | By: {interaction.user}")

		embed = discord.Embed(
			title="🔓 User Unbanned",
			color=Colors.SUCCESS,
			timestamp=datetime.now(timezone.utc)
		)
		embed.set_thumbnail(url=user.display_avatar.url)
		embed.add_field(name="👤 User", value=f"{user.mention}\n`{user}`", inline=True)
		embed.add_field(name="👮 Moderator", value=f"{interaction.user.mention}", inline=True)
		embed.add_field(name="📋 Reason", value=reason, inline=False)
		embed.set_footer(text=f"User ID: {user.id}")

		await interaction.response.send_message(embed=embed)
		await self._log_action(interaction.guild, embed)

	# ─────────────────────────────────────────────────────────────────────────
	# Timeout Commands
	# ─────────────────────────────────────────────────────────────────────────

	@app_commands.command(name="timeout", description="⏰ Timeout a user (mute)")
	@app_commands.checks.has_permissions(moderate_members=True)
	@app_commands.describe(
		member="User to timeout",
		duration="Duration (e.g., 10m, 1h, 1d, 1w)",
		reason="Reason for the timeout"
	)
	async def timeout(self, interaction: discord.Interaction, member: discord.Member, duration: str, reason: str = "No reason provided"):
		if member.bot:
			await interaction.response.send_message("❌ Cannot timeout bots.", ephemeral=True)
			return
		
		if member.top_role >= interaction.user.top_role and interaction.user != interaction.guild.owner:
			await interaction.response.send_message("❌ Cannot timeout someone with equal or higher role.", ephemeral=True)
			return

		if member.top_role >= interaction.guild.me.top_role:
			await interaction.response.send_message("❌ Cannot timeout someone with a role higher than mine.", ephemeral=True)
			return

		# Parse duration
		duration_map = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
		try:
			unit = duration[-1].lower()
			amount = int(duration[:-1])
			if unit not in duration_map:
				raise ValueError
			seconds = amount * duration_map[unit]
			if seconds > 2419200:  # Max 28 days
				seconds = 2419200
			delta = timedelta(seconds=seconds)
		except (ValueError, IndexError):
			await interaction.response.send_message("❌ Invalid duration format. Use: 10m, 1h, 1d, 1w", ephemeral=True)
			return

		await member.timeout(delta, reason=f"{reason} | By: {interaction.user}")

		embed = discord.Embed(
			title="⏰ User Timed Out",
			color=Colors.WARNING,
			timestamp=datetime.now(timezone.utc)
		)
		embed.set_thumbnail(url=member.display_avatar.url)
		embed.add_field(name="👤 User", value=f"{member.mention}\n`{member}`", inline=True)
		embed.add_field(name="👮 Moderator", value=f"{interaction.user.mention}", inline=True)
		embed.add_field(name="⏱️ Duration", value=duration, inline=True)
		embed.add_field(name="📋 Reason", value=reason, inline=False)
		embed.set_footer(text=f"User ID: {member.id}")

		await interaction.response.send_message(embed=embed)

		# Try to DM
		try:
			dm_embed = discord.Embed(
				title=f"⏰ Timed Out in {interaction.guild.name}",
				description=f"You have been timed out for **{duration}**.",
				color=Colors.WARNING
			)
			dm_embed.add_field(name="📋 Reason", value=reason, inline=False)
			await member.send(embed=dm_embed)
		except discord.Forbidden:
			pass

		await self._log_action(interaction.guild, embed)

	@app_commands.command(name="untimeout", description="🔊 Remove timeout from a user")
	@app_commands.checks.has_permissions(moderate_members=True)
	@app_commands.describe(
		member="User to remove timeout from",
		reason="Reason for removing timeout"
	)
	async def untimeout(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
		if not member.is_timed_out():
			await interaction.response.send_message("❌ This user is not timed out.", ephemeral=True)
			return

		await member.timeout(None, reason=f"{reason} | By: {interaction.user}")

		embed = discord.Embed(
			title="🔊 Timeout Removed",
			color=Colors.SUCCESS,
			timestamp=datetime.now(timezone.utc)
		)
		embed.set_thumbnail(url=member.display_avatar.url)
		embed.add_field(name="👤 User", value=f"{member.mention}\n`{member}`", inline=True)
		embed.add_field(name="👮 Moderator", value=f"{interaction.user.mention}", inline=True)
		embed.add_field(name="📋 Reason", value=reason, inline=False)
		embed.set_footer(text=f"User ID: {member.id}")

		await interaction.response.send_message(embed=embed)
		await self._log_action(interaction.guild, embed)

	# ─────────────────────────────────────────────────────────────────────────
	# Utility Commands
	# ─────────────────────────────────────────────────────────────────────────

	@app_commands.command(name="slowmode", description="🐌 Set channel slowmode")
	@app_commands.checks.has_permissions(manage_channels=True)
	@app_commands.describe(seconds="Slowmode delay in seconds (0 to disable)")
	async def slowmode(self, interaction: discord.Interaction, seconds: int):
		if not isinstance(interaction.channel, discord.TextChannel):
			await interaction.response.send_message("❌ Can only set slowmode in text channels.", ephemeral=True)
			return

		seconds = max(0, min(21600, seconds))  # 0 to 6 hours
		await interaction.channel.edit(slowmode_delay=seconds)

		if seconds == 0:
			embed = discord.Embed(
				title="🐌 Slowmode Disabled",
				description=f"Slowmode has been disabled in {interaction.channel.mention}",
				color=Colors.SUCCESS
			)
		else:
			embed = discord.Embed(
				title="🐌 Slowmode Enabled",
				description=f"Slowmode set to **{seconds}** seconds in {interaction.channel.mention}",
				color=Colors.INFO
			)

		await interaction.response.send_message(embed=embed)

	@app_commands.command(name="lock", description="🔒 Lock a channel")
	@app_commands.checks.has_permissions(manage_channels=True)
	@app_commands.describe(reason="Reason for locking")
	async def lock(self, interaction: discord.Interaction, reason: str = "No reason provided"):
		if not isinstance(interaction.channel, discord.TextChannel):
			await interaction.response.send_message("❌ Can only lock text channels.", ephemeral=True)
			return

		overwrite = interaction.channel.overwrites_for(interaction.guild.default_role)
		overwrite.send_messages = False
		await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)

		embed = discord.Embed(
			title="🔒 Channel Locked",
			description=f"{interaction.channel.mention} has been locked.",
			color=Colors.ERROR,
			timestamp=datetime.now(timezone.utc)
		)
		embed.add_field(name="📋 Reason", value=reason, inline=False)
		embed.set_footer(text=f"Locked by {interaction.user}")

		await interaction.response.send_message(embed=embed)
		await self._log_action(interaction.guild, embed)

	@app_commands.command(name="unlock", description="🔓 Unlock a channel")
	@app_commands.checks.has_permissions(manage_channels=True)
	async def unlock(self, interaction: discord.Interaction):
		if not isinstance(interaction.channel, discord.TextChannel):
			await interaction.response.send_message("❌ Can only unlock text channels.", ephemeral=True)
			return

		overwrite = interaction.channel.overwrites_for(interaction.guild.default_role)
		overwrite.send_messages = None
		await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)

		embed = discord.Embed(
			title="🔓 Channel Unlocked",
			description=f"{interaction.channel.mention} has been unlocked.",
			color=Colors.SUCCESS
		)
		embed.set_footer(text=f"Unlocked by {interaction.user}")

		await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
	await bot.add_cog(Moderation(bot))
