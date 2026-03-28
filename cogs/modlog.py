"""
Modlog cog - Comprehensive server activity monitoring and user surveillance.
Provides detailed user analysis, activity tracking, and raw data inspection.
Enhanced with user history tracking, mutual server detection, and webhook alerts.
"""
from datetime import datetime, timezone
from typing import Optional
import re
import aiohttp

import discord
from discord import app_commands
from discord.ext import commands

from core.helpers import save_data, mark_dirty, Colors, logger


class Modlog(commands.Cog):
	"""Comprehensive server activity monitoring and surveillance."""

	def __init__(self, bot: commands.Bot):
		self.bot = bot
		self.bot.data.setdefault("modlog", {})
		self.bot.data.setdefault("user_history", {})  # Cross-server user tracking
		# Cache deleted/edited messages
		self._deleted_cache: dict[int, list[dict]] = {}
		self._edit_cache: dict[int, list[dict]] = {}

	# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
	# User History Tracking
	# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

	def _get_user_history(self, guild_id: int, user_id: int) -> dict:
		"""Get stored history for a user in a guild."""
		gid = str(guild_id)
		uid = str(user_id)
		self.bot.data["user_history"].setdefault(gid, {})
		return self.bot.data["user_history"][gid].get(uid, {})

	def _save_user_history(self, guild_id: int, user_id: int, data: dict):
		"""Save user history data."""
		gid = str(guild_id)
		uid = str(user_id)
		self.bot.data["user_history"].setdefault(gid, {})
		self.bot.data["user_history"][gid][uid] = data
		mark_dirty()

	def _record_user_join(self, member: discord.Member):
		"""Record a user joining the server."""
		history = self._get_user_history(member.guild.id, member.id)
		
		joins = history.get("joins", [])
		joins.append({
			"timestamp": datetime.now(timezone.utc).isoformat(),
			"username": str(member),
			"display_name": member.display_name,
			"avatar_hash": member.avatar.key if member.avatar else None,
		})
		
		history["joins"] = joins[-10:]  # Keep last 10 joins
		history["last_username"] = str(member)
		history["last_seen"] = datetime.now(timezone.utc).isoformat()
		history["user_id"] = member.id
		
		self._save_user_history(member.guild.id, member.id, history)

	def _record_user_leave(self, member: discord.Member):
		"""Record a user leaving the server with their data."""
		history = self._get_user_history(member.guild.id, member.id)
		
		leaves = history.get("leaves", [])
		leaves.append({
			"timestamp": datetime.now(timezone.utc).isoformat(),
			"username": str(member),
			"roles": [r.name for r in member.roles if r.name != "@everyone"],
			"nickname": member.nick,
		})
		
		history["leaves"] = leaves[-10:]  # Keep last 10 leaves
		history["last_username"] = str(member)
		history["last_seen"] = datetime.now(timezone.utc).isoformat()
		history["last_roles"] = [r.name for r in member.roles if r.name != "@everyone"]
		history["last_nickname"] = member.nick
		
		# Store activity data before they leave
		activity = self._get_member_activity_data(member)
		history["last_activity"] = activity
		
		self._save_user_history(member.guild.id, member.id, history)

	# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
	# Mutual Server Detection
	# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

	def _get_mutual_servers(self, user: discord.User | discord.Member) -> list[dict]:
		"""Get servers where both the bot and the user are present."""
		mutual = []
		for guild in self.bot.guilds:
			member = guild.get_member(user.id)
			if member:
				mutual.append({
					"name": guild.name,
					"id": guild.id,
					"member_count": guild.member_count,
					"joined_at": member.joined_at.isoformat() if member.joined_at else None,
					"nickname": member.nick,
					"roles": len(member.roles) - 1,
				})
		return mutual

	# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
	# Webhook Alert System
	# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

	async def _send_webhook_alert(self, guild: discord.Guild, embed: discord.Embed, alert_type: str):
		"""Send an alert to the configured webhook."""
		config = self.bot.data["modlog"].get(str(guild.id), {})
		webhook_url = config.get("alert_webhook")
		
		if not webhook_url:
			return
		
		# Check if this alert type is enabled
		alert_types = config.get("webhook_alerts", {})
		if not alert_types.get(alert_type, True):
			return
		
		try:
			async with aiohttp.ClientSession() as session:
				webhook = discord.Webhook.from_url(webhook_url, session=session)
				await webhook.send(
					embed=embed,
					username=f"{self.bot.user.name} Alerts",
					avatar_url=self.bot.user.display_avatar.url
				)
		except Exception as e:
			logger.error(f"Failed to send webhook alert: {e}")

	def _get_log_channel(self, guild: discord.Guild) -> Optional[discord.TextChannel]:
		"""Get the configured modlog channel for a guild."""
		config = self.bot.data["modlog"].get(str(guild.id), {})
		channel_id = config.get("channel_id")
		if channel_id:
			channel = guild.get_channel(channel_id)
			if isinstance(channel, discord.TextChannel):
				return channel
		return None

	def _is_enabled(self, guild: discord.Guild, event: str) -> bool:
		"""Check if a specific event type is enabled for logging."""
		config = self.bot.data["modlog"].get(str(guild.id), {})
		events = config.get("events", {})
		return events.get(event, True)

	async def _log_event(self, guild: discord.Guild, embed: discord.Embed, event_type: str, raw_data: str = None):
		"""Send a log embed to the modlog channel if enabled."""
		if not self._is_enabled(guild, event_type):
			return

		channel = self._get_log_channel(guild)
		if channel:
			try:
				await channel.send(embed=embed)
				# Optionally send raw data as a code block
				if raw_data and self._is_enabled(guild, "raw_data"):
					await channel.send(f"```\n{raw_data[:1900]}\n```")
			except discord.Forbidden:
				pass

	def _get_user_flags(self, user: discord.User | discord.Member) -> list[str]:
		"""Extract all public flags from a user."""
		flags = []
		pf = user.public_flags
		
		flag_map = {
			"staff": "ðŸ‘” Discord Staff",
			"partner": "ðŸ¤ Partner",
			"hypesquad": "ðŸ  HypeSquad Events",
			"bug_hunter": "ðŸ› Bug Hunter",
			"bug_hunter_level_2": "ðŸ› Bug Hunter Lvl 2",
			"hypesquad_bravery": "ðŸ’œ HypeSquad Bravery",
			"hypesquad_brilliance": "ðŸ§¡ HypeSquad Brilliance",
			"hypesquad_balance": "ðŸ’š HypeSquad Balance",
			"early_supporter": "ðŸ‘‘ Early Supporter",
			"verified_bot": "âœ… Verified Bot",
			"verified_bot_developer": "ðŸ¤– Verified Bot Dev",
			"discord_certified_moderator": "ðŸ›¡ï¸ Certified Mod",
			"active_developer": "ðŸ’» Active Developer",
			"spammer": "ðŸš« Flagged Spammer",
		}
		
		for attr, label in flag_map.items():
			if getattr(pf, attr, False):
				flags.append(label)
		
		return flags

	def _get_member_activity_data(self, member: discord.Member) -> dict:
		"""Get all bot-tracked activity for a member."""
		guild_id = str(member.guild.id)
		user_id = str(member.id)
		
		data = {
			"xp": 0,
			"level": 1,
			"messages": 0,
			"balance": 0,
			"bank": 0,
			"tickets_created": 0,
			"warnings": [],
		}
		
		# XP data
		if "xp" in self.bot.data:
			xp_data = self.bot.data["xp"].get(guild_id, {}).get(user_id, {})
			data["xp"] = xp_data.get("xp", 0)
			data["level"] = xp_data.get("level", 1)
			data["messages"] = xp_data.get("messages", 0)
		
		# Economy data
		if "economy" in self.bot.data:
			econ_data = self.bot.data["economy"].get(guild_id, {}).get(user_id, {})
			data["balance"] = econ_data.get("balance", 0)
			data["bank"] = econ_data.get("bank", 0)
		
		# Profile data
		if "profiles" in self.bot.data:
			profile = self.bot.data["profiles"].get(guild_id, {}).get(user_id, {})
			data["profile_status"] = profile.get("status", None)
			data["profile_bio"] = profile.get("bio", None)
		
		return data

	# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
	# Enhanced Event Listeners with Raw Data
	# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
	
	@commands.Cog.listener()
	async def on_message_edit(self, before: discord.Message, after: discord.Message):
		"""Log message edits with full details."""
		if before.author.bot or not before.guild:
			return
		if before.content == after.content:
			return

		embed = discord.Embed(
			title="âœï¸ Message Edited",
			color=Colors.WARNING,
			timestamp=datetime.now(timezone.utc)
		)
		embed.set_author(name=str(before.author), icon_url=before.author.display_avatar.url)
		embed.add_field(name="Before", value=before.content[:1024] or "*empty*", inline=False)
		embed.add_field(name="After", value=after.content[:1024] or "*empty*", inline=False)
		embed.add_field(name="Channel", value=f"{before.channel.mention}\n`#{before.channel.name}`", inline=True)
		embed.add_field(name="Message Link", value=f"[Jump]({after.jump_url})", inline=True)
		embed.set_footer(text=f"User ID: {before.author.id} | Msg ID: {before.id}")

		# Raw data for logging
		raw = f"""[MESSAGE_EDIT]
User: {before.author} ({before.author.id})
Channel: #{before.channel.name} ({before.channel.id})
Message ID: {before.id}
Timestamp: {datetime.now(timezone.utc).isoformat()}
Before Length: {len(before.content)}
After Length: {len(after.content)}
Before Content: {before.content[:500]}
After Content: {after.content[:500]}"""

		await self._log_event(before.guild, embed, "message_edit", raw)

		# Cache for snipe
		self._edit_cache.setdefault(before.guild.id, []).insert(0, {
			"author": str(before.author),
			"author_id": before.author.id,
			"author_avatar": before.author.display_avatar.url,
			"before": before.content,
			"after": after.content,
			"channel_id": before.channel.id,
			"message_id": before.id,
			"timestamp": datetime.now(timezone.utc).isoformat()
		})
		self._edit_cache[before.guild.id] = self._edit_cache[before.guild.id][:50]

	@commands.Cog.listener()
	async def on_message_delete(self, message: discord.Message):
		"""Log message deletions with full details."""
		if message.author.bot or not message.guild:
			return

		embed = discord.Embed(
			title="ðŸ—‘ï¸ Message Deleted",
			color=Colors.ERROR,
			timestamp=datetime.now(timezone.utc)
		)
		embed.set_author(name=str(message.author), icon_url=message.author.display_avatar.url)
		embed.add_field(name="Content", value=message.content[:1024] or "*no text content*", inline=False)
		embed.add_field(name="Channel", value=f"{message.channel.mention}\n`#{message.channel.name}`", inline=True)
		embed.add_field(name="Created", value=f"<t:{int(message.created_at.timestamp())}:R>", inline=True)
		
		if message.attachments:
			attachment_list = "\n".join([f"â€¢ {a.filename} ({a.size} bytes)" for a in message.attachments[:5]])
			embed.add_field(name="ðŸ“Ž Attachments", value=attachment_list, inline=False)
		
		if message.stickers:
			sticker_names = ", ".join([s.name for s in message.stickers])
			embed.add_field(name="ðŸŽŸï¸ Stickers", value=sticker_names, inline=True)
		
		if message.embeds:
			embed.add_field(name="ðŸ“¦ Embeds", value=f"{len(message.embeds)} embed(s)", inline=True)
		
		if message.reference:
			embed.add_field(name="â†©ï¸ Reply To", value=f"Message ID: `{message.reference.message_id}`", inline=True)
		
		embed.set_footer(text=f"User ID: {message.author.id} | Msg ID: {message.id}")

		# Raw data
		raw = f"""[MESSAGE_DELETE]
User: {message.author} ({message.author.id})
Channel: #{message.channel.name} ({message.channel.id})
Message ID: {message.id}
Created At: {message.created_at.isoformat()}
Deleted At: {datetime.now(timezone.utc).isoformat()}
Content Length: {len(message.content)}
Attachments: {len(message.attachments)}
Attachment URLs: {', '.join([a.url for a in message.attachments])}
Content: {message.content[:800]}"""

		await self._log_event(message.guild, embed, "message_delete", raw)

		# Cache for snipe
		self._deleted_cache.setdefault(message.guild.id, []).insert(0, {
			"author": str(message.author),
			"author_id": message.author.id,
			"author_avatar": message.author.display_avatar.url,
			"content": message.content,
			"channel_id": message.channel.id,
			"message_id": message.id,
			"timestamp": datetime.now(timezone.utc).isoformat(),
		})
		self._deleted_cache[message.guild.id] = self._deleted_cache[message.guild.id][:50]

	@commands.Cog.listener()
	async def on_member_join(self, member: discord.Member):
		"""Log member joins and keep history."""
		if member.bot:
			return
		self._record_user_join(member)

		embed = discord.Embed(
			title='Member Joined',
			description=f'{member.mention} joined the server.',
			color=Colors.SUCCESS,
			timestamp=datetime.now(timezone.utc)
		)
		embed.set_author(name=str(member), icon_url=member.display_avatar.url)
		embed.set_footer(text=f'User ID: {member.id}')
		raw = f'[JOIN] User: {member} ({member.id}) | Guild: {member.guild.name} ({member.guild.id})'
		await self._log_event(member.guild, embed, 'member_join', raw)

	@commands.Cog.listener()
	async def on_member_remove(self, member: discord.Member):
		"""Log member leaves and keep history snapshot."""
		if member.bot:
			return
		self._record_user_leave(member)

		embed = discord.Embed(
			title='Member Left',
			description=f'{member.mention} left the server.',
			color=Colors.ERROR,
			timestamp=datetime.now(timezone.utc)
		)
		embed.set_author(name=str(member), icon_url=member.display_avatar.url)
		embed.set_footer(text=f'User ID: {member.id}')
		raw = f'[LEAVE] User: {member} ({member.id}) | Guild: {member.guild.name} ({member.guild.id})'
		await self._log_event(member.guild, embed, 'member_leave', raw)

	@commands.Cog.listener()
	async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
		"""Log voice joins, leaves, and moves."""
		if member.bot:
			return
		if before.channel == after.channel:
			return

		embed = None
		raw = ''
		if before.channel is None and after.channel is not None:
			embed = discord.Embed(
				title='Voice Join',
				description=f'{member.mention} joined **{after.channel.name}**.',
				color=Colors.SUCCESS,
				timestamp=datetime.now(timezone.utc)
			)
			raw = f'[VOICE_JOIN] User: {member} ({member.id}) | Channel: {after.channel.name} ({after.channel.id})'
		elif before.channel is not None and after.channel is None:
			embed = discord.Embed(
				title='Voice Leave',
				description=f'{member.mention} left **{before.channel.name}**.',
				color=Colors.ERROR,
				timestamp=datetime.now(timezone.utc)
			)
			raw = f'[VOICE_LEAVE] User: {member} ({member.id}) | Channel: {before.channel.name} ({before.channel.id})'
		elif before.channel != after.channel:
			embed = discord.Embed(
				title='Voice Move',
				description=f'{member.mention} moved **{before.channel.name}** -> **{after.channel.name}**.',
				color=Colors.INFO,
				timestamp=datetime.now(timezone.utc)
			)
			raw = f'[VOICE_MOVE] User: {member} ({member.id}) | From: {before.channel.name} | To: {after.channel.name}'

		if embed:
			embed.set_author(name=str(member), icon_url=member.display_avatar.url)
			embed.set_footer(text=f'User ID: {member.id}')
			await self._log_event(member.guild, embed, 'voice_activity', raw)

	@commands.Cog.listener()
	async def on_member_update(self, before: discord.Member, after: discord.Member):
		"""Log nickname and role changes."""
		if before.bot:
			return

		if before.nick != after.nick:
			embed = discord.Embed(
				title='Nickname Changed',
				description=f'{after.mention} changed nickname.',
				color=Colors.WARNING,
				timestamp=datetime.now(timezone.utc)
			)
			embed.add_field(name='Before', value=before.nick or 'None', inline=True)
			embed.add_field(name='After', value=after.nick or 'None', inline=True)
			embed.set_footer(text=f'User ID: {after.id}')
			raw = f'[NICK_CHANGE] User: {after} ({after.id}) | Before: {before.nick} | After: {after.nick}'
			await self._log_event(after.guild, embed, 'nickname_change', raw)

		before_roles = {r.id for r in before.roles}
		after_roles = {r.id for r in after.roles}
		if before_roles != after_roles:
			added = [r.mention for r in after.roles if r.id not in before_roles and r.name != '@everyone']
			removed = [r.mention for r in before.roles if r.id not in after_roles and r.name != '@everyone']
			if added or removed:
				embed = discord.Embed(
					title='Roles Updated',
					description=f'Role changes for {after.mention}.',
					color=Colors.INFO,
					timestamp=datetime.now(timezone.utc)
				)
				if added:
					embed.add_field(name='Added', value=' '.join(added)[:1024], inline=False)
				if removed:
					embed.add_field(name='Removed', value=' '.join(removed)[:1024], inline=False)
				embed.set_footer(text=f'User ID: {after.id}')
				raw = f'[ROLE_CHANGE] User: {after} ({after.id}) | Added: {added} | Removed: {removed}'
				await self._log_event(after.guild, embed, 'role_change', raw)

	async def on_member_ban(self, guild: discord.Guild, user: discord.User):
		"""Log bans."""
		embed = discord.Embed(
			title="ðŸ”¨ Member Banned",
			description=f"{user.mention} ({user})",
			color=0x000000,
			timestamp=datetime.now(timezone.utc)
		)
		embed.set_thumbnail(url=user.display_avatar.url)
		embed.set_footer(text=f"User ID: {user.id}")
		
		raw = f"[BAN] User: {user} ({user.id}) | Guild: {guild.name} ({guild.id})"
		await self._log_event(guild, embed, "ban", raw)

	@commands.Cog.listener()
	async def on_member_unban(self, guild: discord.Guild, user: discord.User):
		"""Log unbans."""
		embed = discord.Embed(
			title="ðŸ”“ Member Unbanned",
			description=f"{user.mention} ({user})",
			color=Colors.SUCCESS,
			timestamp=datetime.now(timezone.utc)
		)
		embed.set_thumbnail(url=user.display_avatar.url)
		embed.set_footer(text=f"User ID: {user.id}")
		
		raw = f"[UNBAN] User: {user} ({user.id}) | Guild: {guild.name} ({guild.id})"
		await self._log_event(guild, embed, "unban", raw)

	# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
	# Commands
	# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

	@app_commands.command(name="setmodlog", description="ðŸ“‹ Set the moderation log channel")
	@app_commands.checks.has_permissions(manage_guild=True)
	@app_commands.describe(channel="Channel for moderation logs")
	async def setmodlog(self, interaction: discord.Interaction, channel: discord.TextChannel):
		guild_id = str(interaction.guild.id)
		self.bot.data["modlog"].setdefault(guild_id, {})
		self.bot.data["modlog"][guild_id]["channel_id"] = channel.id
		mark_dirty()
		
		embed = discord.Embed(
			title="âœ… Modlog Channel Set!",
			description=f"Server activity will be logged to {channel.mention}",
			color=Colors.SUCCESS
		)
		embed.add_field(
			name="ðŸ“‹ Logged Events",
			value="â€¢ Message edits/deletes\nâ€¢ Member joins/leaves\nâ€¢ Nickname/role changes\nâ€¢ Voice activity\nâ€¢ Bans/Unbans",
			inline=False
		)
		embed.set_footer(text="Use /modlogtoggle to enable/disable events â€¢ /modlograw for raw data toggle")
		await interaction.response.send_message(embed=embed)

	@app_commands.command(name="modlogtoggle", description="âš™ï¸ Toggle specific modlog events on/off")
	@app_commands.checks.has_permissions(manage_guild=True)
	@app_commands.describe(event="Event type to toggle")
	@app_commands.choices(event=[
		app_commands.Choice(name="âœï¸ Message Edits", value="message_edit"),
		app_commands.Choice(name="ðŸ—‘ï¸ Message Deletes", value="message_delete"),
		app_commands.Choice(name="ðŸ“¥ Member Joins", value="member_join"),
		app_commands.Choice(name="ðŸ“¤ Member Leaves", value="member_leave"),
		app_commands.Choice(name="ðŸ“ Nickname Changes", value="nickname_change"),
		app_commands.Choice(name="ðŸ·ï¸ Role Changes", value="role_change"),
	])
	async def modlogtoggle(self, interaction: discord.Interaction, event: app_commands.Choice[str]):
		guild_id = str(interaction.guild.id)
		config = self.bot.data["modlog"].setdefault(guild_id, {})
		events = config.setdefault("events", {})
		
		current = events.get(event.value, True)
		events[event.value] = not current
		mark_dirty()
		
		status = "âœ… Enabled" if events[event.value] else "âŒ Disabled"
		embed = discord.Embed(
			title=f"{event.name} {status}",
			color=Colors.SUCCESS if events[event.value] else Colors.WARNING
		)
		await interaction.response.send_message(embed=embed)

	@app_commands.command(name="modlograw", description="âš™ï¸ Toggle raw data logging (detailed text logs)")
	@app_commands.checks.has_permissions(manage_guild=True)
	async def modlograw(self, interaction: discord.Interaction):
		guild_id = str(interaction.guild.id)
		config = self.bot.data["modlog"].setdefault(guild_id, {})
		events = config.setdefault("events", {})
		
		current = events.get("raw_data", False)
		events["raw_data"] = not current
		mark_dirty()
		
		status = "âœ… Enabled" if events["raw_data"] else "âŒ Disabled"
		embed = discord.Embed(
			title=f"ðŸ“„ Raw Data Logging {status}",
			description="When enabled, each log will include a code block with raw technical data.",
			color=Colors.SUCCESS if events["raw_data"] else Colors.WARNING
		)
		await interaction.response.send_message(embed=embed)

	@app_commands.command(name="alertwebhook", description="ðŸ”” Set webhook URL for critical security alerts")
	@app_commands.checks.has_permissions(administrator=True)
	@app_commands.describe(
		webhook_url="Discord webhook URL (leave empty to disable)",
	)
	async def alertwebhook(self, interaction: discord.Interaction, webhook_url: str = None):
		"""Configure webhook for security alerts."""
		guild_id = str(interaction.guild.id)
		config = self.bot.data["modlog"].setdefault(guild_id, {})
		
		if not webhook_url:
			# Disable webhook
			config.pop("alert_webhook", None)
			mark_dirty()
			await interaction.response.send_message("ðŸ”• Alert webhook disabled.", ephemeral=True)
			return
		
		# Validate webhook URL
		if not webhook_url.startswith("https://discord.com/api/webhooks/"):
			await interaction.response.send_message(
				"âŒ Invalid webhook URL. Must be a Discord webhook URL.",
				ephemeral=True
			)
			return
		
		config["alert_webhook"] = webhook_url
		mark_dirty()
		
		embed = discord.Embed(
			title="ðŸ”” Alert Webhook Configured",
			description="Critical security alerts will be sent to your webhook.",
			color=Colors.SUCCESS
		)
		embed.add_field(
			name="ðŸ“‹ Alert Types",
			value="â€¢ ðŸš¨ High-risk user joins\nâ€¢ ðŸ”’ Mass bans/kicks\nâ€¢ âš ï¸ Raid detection\nâ€¢ ðŸ“¤ Important user leaves",
			inline=False
		)
		
		# Test the webhook
		try:
			async with aiohttp.ClientSession() as session:
				webhook = discord.Webhook.from_url(webhook_url, session=session)
				test_embed = discord.Embed(
					title="ðŸ”” Webhook Test",
					description="This is a test alert from the modlog system.",
					color=Colors.INFO
				)
				await webhook.send(
					embed=test_embed,
					username=f"{self.bot.user.name} Alerts",
					avatar_url=self.bot.user.display_avatar.url
				)
			embed.add_field(name="âœ… Test", value="Webhook test sent successfully!", inline=False)
		except Exception as e:
			embed.add_field(name="âš ï¸ Warning", value=f"Could not send test: {e}", inline=False)
		
		await interaction.response.send_message(embed=embed, ephemeral=True)

	@app_commands.command(name="userhistory", description="ðŸ“œ View a user's join/leave history in this server")
	@app_commands.checks.has_permissions(moderate_members=True)
	@app_commands.describe(user_id="User ID to check (works for users not in server)")
	async def userhistory(self, interaction: discord.Interaction, user_id: str):
		"""View stored history for a user."""
		try:
			uid = int(user_id.strip())
		except ValueError:
			await interaction.response.send_message("Invalid user ID.", ephemeral=True)
			return
		
		history = self._get_user_history(interaction.guild.id, uid)
		
		if not history:
			await interaction.response.send_message(
				f"No history found for user ID `{uid}` in this server.",
				ephemeral=True
			)
			return
		
		# Try to get user info
		try:
			user = await self.bot.fetch_user(uid)
			username = str(user)
			avatar_url = user.display_avatar.url
		except Exception:
			username = history.get("last_username", f"Unknown ({uid})")
			avatar_url = None
		
		embed = discord.Embed(
			title=f"ðŸ“œ User History: {username}",
			color=Colors.INFO,
			timestamp=datetime.now(timezone.utc)
		)
		if avatar_url:
			embed.set_thumbnail(url=avatar_url)
		
		# Join history
		joins = history.get("joins", [])
		if joins:
			join_text = ""
			for j in joins[-5:]:  # Last 5 joins
				ts = datetime.fromisoformat(j["timestamp"])
				join_text += f"â€¢ <t:{int(ts.timestamp())}:D> as `{j.get('username', 'Unknown')}`\n"
			embed.add_field(name=f"ðŸ“¥ Joins ({len(joins)} total)", value=join_text or "None", inline=False)
		
		# Leave history
		leaves = history.get("leaves", [])
		if leaves:
			leave_text = ""
			for l in leaves[-5:]:  # Last 5 leaves
				ts = datetime.fromisoformat(l["timestamp"])
				leave_text += f"â€¢ <t:{int(ts.timestamp())}:D> with {len(l.get('roles', []))} roles\n"
			embed.add_field(name=f"ðŸ“¤ Leaves ({len(leaves)} total)", value=leave_text or "None", inline=False)
		
		# Last known info
		last_activity = history.get("last_activity", {})
		if last_activity:
			embed.add_field(
				name="ðŸ“Š Last Activity",
				value=f"Level: {last_activity.get('level', 1)}\nXP: {last_activity.get('xp', 0):,}\nMessages: {last_activity.get('messages', 0):,}\nBalance: {last_activity.get('balance', 0):,}",
				inline=True
			)
		
		if history.get("last_roles"):
			embed.add_field(
				name="ðŸ·ï¸ Last Roles",
				value=", ".join(history["last_roles"][:10]) or "None",
				inline=True
			)
		
		embed.set_footer(text=f"User ID: {uid}")
		await interaction.response.send_message(embed=embed, ephemeral=True)

	@app_commands.command(name="snipe", description="ðŸ‘€ View recently deleted messages")
	@app_commands.checks.has_permissions(manage_messages=True)
	@app_commands.describe(all_channels="Show from all channels, not just current")
	async def snipe(self, interaction: discord.Interaction, all_channels: bool = False):
		guild_id = interaction.guild.id
		deleted = self._deleted_cache.get(guild_id, [])
		
		if not all_channels:
			deleted = [d for d in deleted if d["channel_id"] == interaction.channel.id]
		
		deleted = deleted[:10]
		
		if not deleted:
			await interaction.response.send_message("No recently deleted messages found.", ephemeral=True)
			return

		embed = discord.Embed(
			title="ðŸ—‘ï¸ Recently Deleted Messages",
			color=Colors.INFO
		)
		
		for i, msg in enumerate(deleted[:5], 1):
			content = msg["content"][:150] if msg["content"] else "*no text*"
			channel = self.bot.get_channel(msg["channel_id"])
			channel_name = f"#{channel.name}" if channel else "Unknown"
			
			value = f"{content}"
			if msg.get("attachments"):
				value += f"\nðŸ“Ž {len(msg['attachments'])} attachment(s)"
			value += f"\n`{channel_name}` â€¢ <t:{int(datetime.fromisoformat(msg['timestamp']).timestamp())}:R>"
			
			embed.add_field(
				name=f"{i}. {msg['author']} (`{msg['author_id']}`)",
				value=value,
				inline=False
			)
		
		embed.set_footer(text=f"Showing {len(deleted[:5])}/{len(deleted)} â€¢ Only cached while bot is online")
		await interaction.response.send_message(embed=embed, ephemeral=True)
#sniping deleted messages and edited messages, with options to view from all channels or just the current one. The commands display the author, content, channel, and how long ago the message was deleted or edited.
	@app_commands.command(name="editsnipe", description="ðŸ‘€ View recently edited messages")
	@app_commands.checks.has_permissions(manage_messages=True)
	@app_commands.describe(all_channels="Show from all channels, not just current")
	async def editsnipe(self, interaction: discord.Interaction, all_channels: bool = False):
		guild_id = interaction.guild.id
		edits = self._edit_cache.get(guild_id, [])
		
		if not all_channels:
			edits = [e for e in edits if e["channel_id"] == interaction.channel.id]
		
		edits = edits[:10]
		
		if not edits:
			await interaction.response.send_message("No recently edited messages found.", ephemeral=True)
			return

		embed = discord.Embed(
			title="âœï¸ Recently Edited Messages",
			color=Colors.WARNING
		)
		
		for i, msg in enumerate(edits[:5], 1):
			before = msg["before"][:80] if msg["before"] else "*empty*"
			after = msg["after"][:80] if msg["after"] else "*empty*"
			channel = self.bot.get_channel(msg["channel_id"])
			channel_name = f"#{channel.name}" if channel else "Unknown"
			# Display the before and after content, along with the channel and how long ago it was edited.
			embed.add_field(
				name=f"{i}. {msg['author']} (`{msg['author_id']}`)",
				value=f"**Before:** {before}\n**After:** {after}\n`{channel_name}` â€¢ <t:{int(datetime.fromisoformat(msg['timestamp']).timestamp())}:R>",
				inline=False
			)
		#displaying the 5 most recent edits, with a footer indicating how many total edits are cached and that this data is only available while the bot is online (since it's stored in memory).
		embed.set_footer(text=f"Showing {len(edits[:5])}/{len(edits)} â€¢ Only cached while bot is online")
		await interaction.response.send_message(embed=embed, ephemeral=True)

	@app_commands.command(name="inspect", description="ðŸ” Comprehensive user investigation and analysis")
	@app_commands.checks.has_permissions(moderate_members=True)
	@app_commands.describe(member="User to inspect")
	async def inspect(self, interaction: discord.Interaction, member: discord.Member):
		#detailed user inspection command that compiles a comprehensive profile of a member, including account age, join date, risk factors, badges, current status, and bot-tracked activity data. This command provides moderators with an in-depth overview of a user's history and potential risk indicators in a single embed.
		"""Full user surveillance and information."""
		account_age = (datetime.now(timezone.utc) - member.created_at).days
		server_age = (datetime.now(timezone.utc) - member.joined_at).days if member.joined_at else 0
		
		embed = discord.Embed(
			title=f"ðŸ” User Intelligence: {member}",
			color=Colors.PROFILE,
			timestamp=datetime.now(timezone.utc)
		)
		embed.set_thumbnail(url=member.display_avatar.url)

		# Identity info
		embed.add_field(
			name="ðŸªª Identity",
			value=f"**Username:** `{member.name}`\n**Display:** `{member.display_name}`\n**Nickname:** `{member.nick or 'None'}`",
			inline=True
		)
		
		# Timestamps
		embed.add_field(
			name="ðŸ“… Timestamps",
			value=f"**Created:** <t:{int(member.created_at.timestamp())}:D>\n**Joined:** <t:{int(member.joined_at.timestamp()) if member.joined_at else 0}:D>\n**Age:** {account_age}d / {server_age}d",
			inline=True
		)

		# Risk assessment
		risks = []
		risk_score = 0
		
		if account_age < 1:
			risks.append("ðŸš¨ Account < 1 day")
			risk_score += 30
		elif account_age < 7:
			risks.append(f"âš ï¸ New account ({account_age}d)")
			risk_score += 15
		elif account_age < 30:
			risks.append(f"ðŸ“ Account < 30 days")
			risk_score += 5
		
		if not member.avatar:
			risks.append("âš ï¸ Default avatar")
			risk_score += 10
		
		if member.public_flags.spammer:
			risks.append("ðŸš« FLAGGED SPAMMER")
			risk_score += 50
		
		if member.pending:
			risks.append("â³ Pending verification")
			risk_score += 5
		
		# Suspicious patterns
		sus_patterns = [r'discord\.gg', r'free.*nitro', r'\.gift', r'claim.*reward']
		for p in sus_patterns:
			if re.search(p, member.name.lower()) or re.search(p, (member.nick or "").lower()):
				risks.append("âš ï¸ Suspicious name pattern")
				risk_score += 20
				break
		
		risk_level = "ðŸŸ¢ Low" if risk_score < 15 else "ðŸŸ¡ Medium" if risk_score < 30 else "ðŸ”´ High"
		embed.add_field(
			name=f"ðŸš¨ Risk Analysis ({risk_level} - {risk_score}pts)",
			value="\n".join(risks) if risks else "âœ… No risk indicators",
			inline=False
		)

		# Badges/Flags
		flags = self._get_user_flags(member)
		if flags:
			embed.add_field(name="ðŸ… Badges", value="\n".join(flags), inline=True)

		# Current status
		status_emoji = {"online": "ðŸŸ¢", "idle": "ðŸŸ¡", "dnd": "ðŸ”´", "offline": "âš«"}
		status_str = f"{status_emoji.get(str(member.status), 'âšª')} {str(member.status).title()}"
		
		activities = []
		for activity in member.activities:
			if isinstance(activity, discord.Spotify):
				activities.append(f"ðŸŽµ {activity.title} - {activity.artist}")
			elif isinstance(activity, discord.Game):
				activities.append(f"ðŸŽ® {activity.name}")
			elif isinstance(activity, discord.Streaming):
				activities.append(f"ðŸ“º Streaming: {activity.name}")
			elif isinstance(activity, discord.CustomActivity):
				if activity.name:
					activities.append(f"ðŸ’¬ {activity.name}")
		
		status_val = status_str
		if activities:
			status_val += "\n" + "\n".join(activities[:3])
		if member.voice:
			status_val += f"\nðŸ”Š In: {member.voice.channel.mention}"
		
		embed.add_field(name="ðŸ“¡ Status", value=status_val, inline=True)

		# Bot activity data
		activity_data = self._get_member_activity_data(member)
		embed.add_field(
			name="ðŸ“Š Bot Activity",
			value=f"**Level:** {activity_data['level']}\n**XP:** {activity_data['xp']:,}\n**Messages:** {activity_data['messages']:,}\n**Balance:** ðŸ’° {activity_data['balance']:,}",
			inline=True
		)

		# Roles
		roles = [r.mention for r in sorted(member.roles[1:], key=lambda r: r.position, reverse=True)][:12]
		if roles:
			embed.add_field(name=f"ðŸ·ï¸ Roles ({len(member.roles) - 1})", value=" ".join(roles), inline=False)

		# Mutual servers
		mutual_servers = self._get_mutual_servers(member)
		if len(mutual_servers) > 1:  # More than just this server
			other_servers = [s for s in mutual_servers if s["id"] != member.guild.id][:5]
			if other_servers:
				server_list = ", ".join([f"**{s['name']}**" for s in other_servers])
				embed.add_field(name=f"ðŸŒ Mutual Servers ({len(other_servers)})", value=server_list, inline=False)
		
		# User history in this server
		user_history = self._get_user_history(member.guild.id, member.id)
		if user_history.get("leaves"):
			leave_count = len(user_history.get("leaves", []))
			join_count = len(user_history.get("joins", []))
			embed.add_field(
				name="ðŸ“œ Server History",
				value=f"**Joins:** {join_count} | **Leaves:** {leave_count}\nâš ï¸ This user has left and rejoined before",
				inline=False
			)

		# Key permissions
		key_perms = []
		perms = member.guild_permissions
		if perms.administrator:
			key_perms.append("ðŸ‘‘ Administrator")
		if perms.manage_guild:
			key_perms.append("âš™ï¸ Manage Server")
		if perms.manage_roles:
			key_perms.append("ðŸ·ï¸ Manage Roles")
		if perms.manage_channels:
			key_perms.append("ðŸ“‚ Manage Channels")
		if perms.ban_members:
			key_perms.append("ðŸ”¨ Ban")
		if perms.kick_members:
			key_perms.append("ðŸ‘¢ Kick")
		if perms.moderate_members:
			key_perms.append("ðŸ›¡ï¸ Timeout")
		if perms.manage_messages:
			key_perms.append("âœ‰ï¸ Manage Messages")
		
		if key_perms:
			embed.add_field(name="ðŸ” Permissions", value=" â€¢ ".join(key_perms), inline=False)

		embed.set_footer(text=f"User ID: {member.id}")
		await interaction.response.send_message(embed=embed)

	@app_commands.command(name="useraudit", description="ðŸ“„ Raw technical data dump for a user")
	@app_commands.checks.has_permissions(administrator=True)
	@app_commands.describe(member="User to audit")
	async def useraudit(self, interaction: discord.Interaction, member: discord.Member):
		"""Export raw technical data about a user."""
		activity_data = self._get_member_activity_data(member)
		
		raw_data = f"""â•”â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•—
â•‘                      USER AUDIT REPORT                           â•‘
â• â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•£
â•‘ IDENTITY
â•‘ â”œâ”€ Username: {member.name}
â•‘ â”œâ”€ Display Name: {member.display_name}
â•‘ â”œâ”€ Nickname: {member.nick or 'None'}
â•‘ â”œâ”€ Discriminator: {member.discriminator}
â•‘ â”œâ”€ Global Name: {member.global_name or 'None'}
â•‘ â””â”€ Bot: {member.bot}
â• â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•£
â•‘ IDS (RAW)
â•‘ â”œâ”€ User ID: {member.id}
â•‘ â”œâ”€ Guild ID: {member.guild.id}
â•‘ â”œâ”€ Avatar Hash: {member.avatar.key if member.avatar else 'None'}
â•‘ â””â”€ Banner Hash: {member.banner.key if member.banner else 'None'}
â• â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•£
â•‘ TIMESTAMPS
â•‘ â”œâ”€ Created: {member.created_at.isoformat()}
â•‘ â”œâ”€ Joined: {member.joined_at.isoformat() if member.joined_at else 'Unknown'}
â•‘ â”œâ”€ Created Unix: {int(member.created_at.timestamp())}
â•‘ â”œâ”€ Joined Unix: {int(member.joined_at.timestamp()) if member.joined_at else 0}
â•‘ â”œâ”€ Account Age: {(datetime.now(timezone.utc) - member.created_at).days} days
â•‘ â””â”€ Server Age: {(datetime.now(timezone.utc) - member.joined_at).days if member.joined_at else 0} days
â• â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•£
â•‘ FLAGS & STATUS
â•‘ â”œâ”€ Public Flags (int): {member.public_flags.value}
â•‘ â”œâ”€ Status: {member.status}
â•‘ â”œâ”€ Is Pending: {member.pending}
â•‘ â”œâ”€ Is Timed Out: {member.is_timed_out()}
â•‘ â”œâ”€ Desktop Status: {member.desktop_status}
â•‘ â”œâ”€ Mobile Status: {member.mobile_status}
â•‘ â””â”€ Web Status: {member.web_status}
â• â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•£
â•‘ PERMISSIONS
â•‘ â”œâ”€ Permission Value: {member.guild_permissions.value}
â•‘ â”œâ”€ Administrator: {member.guild_permissions.administrator}
â•‘ â”œâ”€ Manage Guild: {member.guild_permissions.manage_guild}
â•‘ â”œâ”€ Ban Members: {member.guild_permissions.ban_members}
â•‘ â”œâ”€ Kick Members: {member.guild_permissions.kick_members}
â•‘ â””â”€ Moderate Members: {member.guild_permissions.moderate_members}
â• â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•£
â•‘ BOT TRACKED DATA
â•‘ â”œâ”€ Level: {activity_data['level']}
â•‘ â”œâ”€ XP: {activity_data['xp']}
â•‘ â”œâ”€ Messages: {activity_data['messages']}
â•‘ â”œâ”€ Balance: {activity_data['balance']}
â•‘ â”œâ”€ Bank: {activity_data['bank']}
â•‘ â”œâ”€ Profile Status: {activity_data.get('profile_status', 'None')}
â•‘ â””â”€ Profile Bio: {activity_data.get('profile_bio', 'None')}
â• â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•£
â•‘ ROLES ({len(member.roles) - 1})"""
		
		for role in sorted(member.roles[1:], key=lambda r: r.position, reverse=True)[:15]:
			raw_data += f"\nâ•‘ â”œâ”€ {role.name} ({role.id})"
		
		raw_data += f"""
â• â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•£
â•‘ AVATAR URLS
â•‘ â”œâ”€ Avatar: {member.avatar.url if member.avatar else 'Default'}
â•‘ â”œâ”€ Display: {member.display_avatar.url}
â•‘ â””â”€ Guild Avatar: {member.guild_avatar.url if member.guild_avatar else 'None'}
â•šâ•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
Generated: {datetime.now(timezone.utc).isoformat()}"""

		# Split if too long
		if len(raw_data) > 1900:
			await interaction.response.send_message(f"```\n{raw_data[:1900]}\n```", ephemeral=True)
			await interaction.followup.send(f"```\n{raw_data[1900:]}\n```", ephemeral=True)
		else:
			await interaction.response.send_message(f"```\n{raw_data}\n```", ephemeral=True)

	@app_commands.command(name="lookup", description="ðŸ”Ž Look up any user by ID (even if not in server)")
	@app_commands.checks.has_permissions(moderate_members=True)
	@app_commands.describe(user_id="The user ID to look up")
	async def lookup(self, interaction: discord.Interaction, user_id: str):
		"""Look up a user by ID, even if they're not in the server."""
		try:
			uid = int(user_id.strip())
		except ValueError:
			await interaction.response.send_message("Invalid user ID format.", ephemeral=True)
			return
		
		await interaction.response.defer(ephemeral=True)
		
		# Try to get as member first
		member = interaction.guild.get_member(uid)
		
		if member:
			# They're in the server, use full info
			await self.inspect.callback(self, interaction, member)
			return
		
		# Try to fetch as user (with full profile data)
		try:
			user = await self.bot.fetch_user(uid)
		except discord.NotFound:
			await interaction.followup.send(f"âŒ No user found with ID `{uid}`", ephemeral=True)
			return
		except discord.HTTPException as e:
			await interaction.followup.send(f"âŒ Failed to fetch user: {e}", ephemeral=True)
			return
		
		# Check if banned
		is_banned = False
		ban_reason = None
		try:
			ban_entry = await interaction.guild.fetch_ban(user)
			is_banned = True
			ban_reason = ban_entry.reason
		except discord.NotFound:
			pass
		except discord.Forbidden:
			pass
		
		account_age = (datetime.now(timezone.utc) - user.created_at).days
		
		# Determine embed color based on accent color or status
		embed_color = Colors.ERROR if is_banned else (user.accent_color or Colors.WARNING)
		
		embed = discord.Embed(
			title=f"ðŸ”Ž User Lookup: {user}",
			description="âš ï¸ This user is **not in this server**",
			color=embed_color,
			timestamp=datetime.now(timezone.utc)
		)
		
		# Set avatar
		embed.set_thumbnail(url=user.display_avatar.url)
		
		# Display all public attributes of discord.User
		user_fields = [
			("ID", user.id),
			("Name", user.name),
			("Display Name", user.display_name),
			("Global Name", getattr(user, "global_name", None)),
			("Discriminator", user.discriminator),
			("Bot", user.bot),
			("System", user.system),
			("Accent Color", f"#{user.accent_color.value:06x}" if user.accent_color else None),
			("Avatar", user.avatar.url if user.avatar else None),
			("Avatar Hash", user.avatar.key if user.avatar else None),
			("Avatar Decoration", getattr(user, "avatar_decoration", None)),
			("Avatar Decoration SKU ID", getattr(user, "avatar_decoration_sku_id", None)),
			("Banner", user.banner.url if user.banner else None),
			("Banner Hash", user.banner.key if user.banner else None),
			("Default Avatar", user.default_avatar.url if user.default_avatar else None),
			("Created At", user.created_at.isoformat()),
			("Mention", user.mention),
			("Mutual Guilds", len(user.mutual_guilds) if hasattr(user, "mutual_guilds") else None),
			("Public Flags", user.public_flags.value),
			("Collectibles", getattr(user, "collectibles", None)),
			("Color", getattr(user, "color", None)),
			("Colour", getattr(user, "colour", None)),
			("Primary Guild", getattr(user, "primary_guild", None)),
			("DM Channel", user.dm_channel),
			("Pins", getattr(user, "pins", None)),
			("History", getattr(user, "history", None)),
			("Send", getattr(user, "send", None)),
			("Typing", getattr(user, "typing", None)),
			("Fetch Message", getattr(user, "fetch_message", None)),
		]
		# Filter out None values
		user_fields = [(k, v) for k, v in user_fields if v is not None]
		field_text = "\n".join([f"**{k}:** {v}" for k, v in user_fields])
		embed.add_field(name="ðŸ§¾ All User Fields", value=field_text or "No data", inline=False)
		
		# Flags/Badges - expanded
		flags = []
		pf = user.public_flags
		
		flag_map = {
			"staff": ("ðŸ‘”", "Discord Staff"),
			"partner": ("ðŸ¤", "Partner"),
			"hypesquad": ("ðŸ ", "HypeSquad Events"),
			"bug_hunter": ("ðŸ›", "Bug Hunter"),
			"bug_hunter_level_2": ("ðŸ›â­", "Bug Hunter Lvl 2"),
			"hypesquad_bravery": ("ðŸ’œ", "Bravery"),
			"hypesquad_brilliance": ("ðŸ§¡", "Brilliance"),
			"hypesquad_balance": ("ðŸ’š", "Balance"),
			"early_supporter": ("ðŸ‘‘", "Early Supporter"),
			"verified_bot": ("âœ…", "Verified Bot"),
			"verified_bot_developer": ("ðŸ¤–", "Verified Bot Dev"),
			"discord_certified_moderator": ("ðŸ›¡ï¸", "Certified Moderator"),
			"active_developer": ("ðŸ’»", "Active Developer"),
			"spammer": ("ðŸš«", "SPAMMER"),
			"team_user": ("ðŸ‘¥", "Team User"),
			"system": ("âš™ï¸", "System"),
		}
		
		for attr, (emoji, label) in flag_map.items():
			if getattr(pf, attr, False):
				flags.append(f"{emoji} {label}")
		
		# Show raw flag value for investigation
		if flags:
			embed.add_field(
				name=f"ðŸ… Badges ({len(flags)})",
				value="\n".join(flags) + f"\n`Raw: {pf.value}`",
				inline=True
			)
		else:
			embed.add_field(
				name="ðŸ… Badges",
				value=f"No public badges\n`Raw: {pf.value}`",
				inline=True
			)
		
		# Ban status (prominent)
		if is_banned:
			embed.add_field(
				name="ðŸ”¨ BAN STATUS",
				value=f"**ðŸš¨ BANNED FROM THIS SERVER**\nReason: {ban_reason or 'No reason provided'}",
				inline=False
			)
		
		# Risk Analysis
		risks = []
		risk_score = 0
		
		if account_age < 1:
			risks.append(f"ðŸ”´ Brand new account (< 1 day)")
			risk_score += 30
		elif account_age < 7:
			risks.append(f"ðŸŸ  Very new account ({account_age} days)")
			risk_score += 20
		elif account_age < 30:
			risks.append(f"ðŸŸ¡ New account ({account_age} days)")
			risk_score += 10
		
		if not user.avatar:
			risks.append("âš ï¸ Default avatar")
			risk_score += 10
		
		if not user.banner and not user.accent_color:
			risks.append("âš ï¸ No profile customization")
			risk_score += 5
		
		if pf.spammer:
			risks.append("ðŸš« **FLAGGED AS SPAMMER BY DISCORD**")
			risk_score += 50
		
		if user.bot and not pf.verified_bot:
			risks.append("âš ï¸ Unverified bot")
			risk_score += 15
		
		# Suspicious ID patterns (very old or very new snowflakes)
		if uid < 100000000000000000:  # Created before Discord (suspicious)
			risks.append("ðŸ”´ Suspiciously old ID")
			risk_score += 40
		
		risk_level = "ðŸŸ¢ Low" if risk_score < 15 else "ðŸŸ¡ Medium" if risk_score < 30 else "ðŸ”´ High"
		
		risk_text = f"**Score:** {risk_score}/100 ({risk_level})"
		if risks:
			risk_text += "\n" + "\n".join(risks)
		else:
			risk_text += "\nâœ… No risk indicators found"
		
		embed.add_field(name="ðŸš¨ Risk Analysis", value=risk_text, inline=False)
		
		# Mutual servers (where bot can see them)
		mutual_servers = self._get_mutual_servers(user)
		if mutual_servers:
			server_list = "\n".join([f"â€¢ **{s['name']}** ({s['member_count']:,} members)" for s in mutual_servers[:5]])
			if len(mutual_servers) > 5:
				server_list += f"\n... and {len(mutual_servers) - 5} more"
			embed.add_field(name=f"ðŸŒ Mutual Servers ({len(mutual_servers)})", value=server_list, inline=False)
		else:
			embed.add_field(name="ðŸŒ Mutual Servers", value="None visible to bot", inline=False)
		
		# User history in this server (from bot data)
		user_history = self._get_user_history(interaction.guild.id, uid)
		if user_history:
			join_count = len(user_history.get("joins", []))
			leave_count = len(user_history.get("leaves", []))
			last_activity = user_history.get("last_activity", {})
			
			history_text = f"**Joins:** {join_count} | **Leaves:** {leave_count}\n"
			if user_history.get("last_seen"):
				try:
					last_seen = datetime.fromisoformat(user_history["last_seen"])
					history_text += f"**Last Seen:** <t:{int(last_seen.timestamp())}:R>\n"
				except Exception:
					pass
			if last_activity.get("level", 1) > 1:
				history_text += f"**Last Level:** {last_activity.get('level', 1)} | **XP:** {last_activity.get('xp', 0):,}"
			
			embed.add_field(name="ðŸ“œ Server History", value=history_text, inline=False)
		
		# Raw data for investigation
		raw_lines = [
			f"User ID: {user.id}",
			f"Created: {user.created_at.isoformat()}",
			f"Avatar: {user.avatar.key if user.avatar else 'None'}",
			f"Banner: {user.banner.key if user.banner else 'None'}",
			f"Accent: {f'#{user.accent_color.value:06x}' if user.accent_color else 'None'}",
			f"Flags: {pf.value}",
			f"Bot: {user.bot} | System: {user.system}",
		]
		embed.add_field(
			name="ðŸ“ Raw Data",
			value=f"```\n{chr(10).join(raw_lines)}\n```",
			inline=False
		)
		
		embed.set_footer(text=f"User ID: {user.id} â€¢ Lookup by {interaction.user}")
		await interaction.followup.send(embed=embed, ephemeral=True)

	@app_commands.command(name="snipedeletes", description="ðŸ“‹ Export recent deleted messages as text")
	@app_commands.checks.has_permissions(administrator=True)
	@app_commands.describe(count="Number of messages to export (max 50)")
	async def snipedeletes(self, interaction: discord.Interaction, count: int = 20):
		"""Export deleted message cache as raw text."""
		guild_id = interaction.guild.id
		deleted = self._deleted_cache.get(guild_id, [])[:min(count, 50)]
		
		if not deleted:
			await interaction.response.send_message("No deleted messages cached.", ephemeral=True)
			return
		
		output = f"DELETED MESSAGES EXPORT - {interaction.guild.name}\nGenerated: {datetime.now(timezone.utc).isoformat()}\n{'='*60}\n\n"
		
		for i, msg in enumerate(deleted, 1):
			channel = self.bot.get_channel(msg["channel_id"])
			output += f"[{i}] {msg['author']} ({msg['author_id']})\n"
			output += f"    Channel: #{channel.name if channel else 'Unknown'} ({msg['channel_id']})\n"
			output += f"    Time: {msg['timestamp']}\n"
			output += f"    Content: {msg['content'][:300]}\n"
			if msg.get("attachments"):
				output += f"    Attachments: {len(msg['attachments'])}\n"
				for att in msg["attachments"][:3]:
					output += f"      - {att.get('filename', 'unknown')} ({att.get('size', 0)} bytes)\n"
			output += "\n"
		
		if len(output) > 1900:
			# Send as file
			import io
			file = discord.File(io.BytesIO(output.encode()), filename=f"deleted_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
			await interaction.response.send_message("ðŸ“‹ Export attached:", file=file, ephemeral=True)
		else:
			await interaction.response.send_message(f"```\n{output}\n```", ephemeral=True)


async def setup(bot: commands.Bot):
	await bot.add_cog(Modlog(bot))
