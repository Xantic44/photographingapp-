"""
XP cog - Experience points and leveling system.
Optimized version with passive XP.
"""
import random
import time

import discord
from discord import app_commands
from discord.ext import commands, tasks

from core.helpers import (
	get_xp_entry,
	get_economy_entry,
	save_data,
	mark_dirty,
	xp_required_for_level,
	create_progress_bar,
	xp_cooldown,
	XP_COOLDOWN_SECONDS,
	logger,
	Colors,
	cute_levelup,
)
from cogs.xp_config import (
	FUNPOINTS_PASSIVE_RANGE,
	PASSIVE_INTERVAL_MINUTES,
	PASSIVE_XP_RANGE,
	VOICE_XP_RANGE,
	XP_BASE_GAIN_RANGE,
	XP_MSG_COOLDOWN,
	get_xp_multiplier,
)


class XP(commands.Cog):
	"""Experience points and leveling system."""

	def __init__(self, bot: commands.Bot):
		self.bot = bot
		self.cleanup_task.start()
		self.passive_xp_task.start()

	def cog_unload(self):
		self.cleanup_task.cancel()
		self.passive_xp_task.cancel()

	# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
	# Background tasks
	# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
	@tasks.loop(minutes=10)
	async def cleanup_task(self):
		"""Remove expired XP cooldown entries."""
		now = time.time()
		expired = [k for k, ts in xp_cooldown.items() if now - ts > XP_COOLDOWN_SECONDS * 2]
		for k in expired:
			del xp_cooldown[k]
		if expired:
			logger.debug("Cleaned up %d expired xp_cooldown entries", len(expired))

	@cleanup_task.before_loop
	async def before_cleanup(self):
		await self.bot.wait_until_ready()

	@tasks.loop(minutes=PASSIVE_INTERVAL_MINUTES)
	async def passive_xp_task(self):
		"""Give passive XP to online members and voice users."""
		for guild in self.bot.guilds:
			levelup_messages = []
			
			for member in guild.members:
				if member.bot:
					continue
				
				xp_entry = get_xp_entry(self.bot.data["xp"], guild.id, member.id)
				multiplier = get_xp_multiplier(xp_entry["level"])
				xp_gained = 0
				
				# Passive XP for online/idle/dnd members (not offline)
				if member.status != discord.Status.offline:
					base_xp = random.randint(*PASSIVE_XP_RANGE)
					xp_gained += int(base_xp * multiplier)
				
				# Bonus XP for being in voice
				if member.voice and member.voice.channel:
					# Extra if not muted/deafened
					if not member.voice.self_deaf:
						base_xp = random.randint(*VOICE_XP_RANGE)
						xp_gained += int(base_xp * multiplier)
					else:
						xp_gained += int(random.randint(1, 4) * multiplier)  # Small amount if deafened
				
				if xp_gained > 0:
					xp_entry["xp"] += xp_gained
					xp_entry["total_xp"] += xp_gained
					
					# Check level up
					old_level = xp_entry["level"]
					while xp_entry["xp"] >= xp_required_for_level(xp_entry["level"]):
						xp_entry["xp"] -= xp_required_for_level(xp_entry["level"])
						xp_entry["level"] += 1
					
					if xp_entry["level"] > old_level:
						new_level = xp_entry["level"]
						new_multiplier = get_xp_multiplier(new_level)
						granted_roles = await self._grant_level_rewards(member, new_level)
						levelup_messages.append((member, new_level, new_multiplier, granted_roles))
			
			# Send level up notifications to configured or fallback channel
			if levelup_messages:
				channel = self._get_configured_levelup_channel(guild) or self._get_default_levelup_channel(guild)

				if channel:
					for member, new_level, new_multiplier, granted_roles in levelup_messages:
						embed = self._build_levelup_embed(
							member=member,
							new_level=new_level,
							new_multiplier=new_multiplier,
							granted_roles=granted_roles,
							footer_text='Passive XP level up',
						)
						try:
							await channel.send(embed=embed)
						except discord.Forbidden:
							pass
		await save_data(self.bot, force=True)  # Force save after passive XP distribution
		logger.debug("Distributed passive XP to all guilds")

	@passive_xp_task.before_loop
	async def before_passive_xp(self):
		await self.bot.wait_until_ready()

	# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
	# Event listeners
	# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
	@commands.Cog.listener()
	async def on_message(self, message: discord.Message):
		"""Handle XP gain from messages."""
		if message.author.bot or not message.guild:
			return

		gid, uid = message.guild.id, message.author.id
		now = time.time()

		# Check cooldown
		if now - xp_cooldown.get((gid, uid), 0) < XP_MSG_COOLDOWN:
			return

		# Update XP with level multiplier
		xp_entry = get_xp_entry(self.bot.data["xp"], gid, uid)
		multiplier = get_xp_multiplier(xp_entry["level"])
		base_gain = random.randint(*XP_BASE_GAIN_RANGE)
		gain = int(base_gain * multiplier)
		
		xp_entry["xp"] += gain
		xp_entry["total_xp"] += gain
		xp_cooldown[(gid, uid)] = now

		# Passive funPoints (also scaled)
		econ_entry = get_economy_entry(self.bot.data["economy"], gid, uid)
		econ_entry["funPoints"] += int(random.randint(*FUNPOINTS_PASSIVE_RANGE) * multiplier)

		# Check level up
		leveled = False
		while xp_entry["xp"] >= xp_required_for_level(xp_entry["level"]):
			xp_entry["xp"] -= xp_required_for_level(xp_entry["level"])
			xp_entry["level"] += 1
			leveled = True

		if leveled:
			new_level = xp_entry['level']
			new_multiplier = get_xp_multiplier(new_level)
			granted_roles = await self._grant_level_rewards(message.author, new_level)
			embed = self._build_levelup_embed(
				member=message.author,
				new_level=new_level,
				new_multiplier=new_multiplier,
				granted_roles=granted_roles,
				footer_text='Higher levels earn more XP',
			)

			channel = self._get_configured_levelup_channel(message.guild) or message.channel
			try:
				await channel.send(embed=embed)
			except discord.Forbidden:
				if channel != message.channel:
					try:
						await message.channel.send(embed=embed)
					except discord.Forbidden:
						pass
		mark_dirty()  # Will be saved by autosave task

	# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
	# Helper methods
	# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
	def _get_level_settings(self, guild_id: int) -> dict:
		"""Get level system config for a guild."""
		gid = str(guild_id)
		if 'level_settings' not in self.bot.data:
			self.bot.data['level_settings'] = {}
		if gid not in self.bot.data['level_settings']:
			self.bot.data['level_settings'][gid] = {}
		return self.bot.data['level_settings'][gid]

	def _get_configured_levelup_channel(self, guild: discord.Guild) -> discord.TextChannel | None:
		"""Get configured level-up channel if valid and sendable."""
		settings = self._get_level_settings(guild.id)
		channel_id = settings.get('levelup_channel_id')
		if not channel_id:
			return None

		channel = guild.get_channel(channel_id)
		if not isinstance(channel, discord.TextChannel):
			return None

		me = guild.me or guild.get_member(self.bot.user.id if self.bot.user else 0)
		if not me:
			return None

		perms = channel.permissions_for(me)
		if perms.send_messages and perms.embed_links:
			return channel
		return None

	def _get_default_levelup_channel(self, guild: discord.Guild) -> discord.TextChannel | None:
		"""Fallback level-up channel when no custom channel is set."""
		me = guild.me or guild.get_member(self.bot.user.id if self.bot.user else 0)
		if not me:
			return None

		system_channel = guild.system_channel
		if isinstance(system_channel, discord.TextChannel):
			perms = system_channel.permissions_for(me)
			if perms.send_messages and perms.embed_links:
				return system_channel

		for channel in guild.text_channels:
			perms = channel.permissions_for(me)
			if perms.send_messages and perms.embed_links:
				return channel
		return None

	def _build_levelup_embed(
		self,
		member: discord.Member,
		new_level: int,
		new_multiplier: float,
		granted_roles: list,
		footer_text: str,
	) -> discord.Embed:
		"""Build a more visually engaging level-up embed."""
		rank_title, rank_desc = self._get_rank_title(new_level)
		celebration = random.choice([
			'LEVEL UP ALERT',
			'NEW LEVEL UNLOCKED',
			'PROGRESS MILESTONE',
			cute_levelup(),
		])

		embed = discord.Embed(
			title=f'{celebration}  |  Level {new_level}',
			description=(
				f'**{member.mention}** just leveled up.\n'
				f'{rank_title}\n'
				f'{rank_desc}'
			),
			color=Colors.XP,
		)
		embed.set_thumbnail(url=member.display_avatar.url)
		embed.add_field(name='XP Multiplier', value=f'**{new_multiplier:.1f}x**', inline=True)
		embed.add_field(name='Next Move', value='Stay active to chain more levels.', inline=True)

		if granted_roles:
			role_text = ', '.join(role.mention for role in granted_roles)
			embed.add_field(name='Rewards Unlocked', value=role_text, inline=False)

		embed.set_footer(text=footer_text)
		return embed

	def _get_rank_title(self, level: int) -> tuple[str, str]:
		"""Get rank title and emoji based on level."""
		rank_tiers = [
			(100, "ðŸŒŸ Legendary", "You've achieved mastery!"),
			(75, "ðŸ‘‘ Royalty", "Bow down to royalty~"),
			(50, "ðŸ’Ž Diamond", "Rare and beautiful!"),
			(35, "ðŸ”¥ Blazing", "On fire!"),
			(25, "â­ Star", "A rising star!"),
			(15, "ðŸŒ» Blooming", "Growing beautifully~"),
			(10, "ðŸŒ¸ Blossom", "Starting to bloom!"),
			(5, "ðŸŒ¿ Sprout", "Growing strong!"),
			(1, "ðŸŒ± Seedling", "Just starting out~"),
		]
		for min_level, title, desc in rank_tiers:
			if level >= min_level:
				return title, desc
		return "ðŸŒ± Seedling", "Just starting out~"

	def _cute_progress_bar(self, current: int, total: int, length: int = 10) -> str:
		"""Create a cute progress bar with custom emojis."""
		if total <= 0:
			return "ðŸŸª" * length
		filled = int((current / total) * length)
		empty = length - filled
		return "ðŸŸª" * filled + "â¬œ" * empty

	def _format_rank_embed(self, member: discord.Member, entry: dict, server_rank: int = None) -> discord.Embed:
		"""Create a beautiful rank card embed."""
		level = entry["level"]
		xp = entry["xp"]
		total = entry["total_xp"]
		needed = xp_required_for_level(level)
		multiplier = get_xp_multiplier(level)
		bar = self._cute_progress_bar(xp, needed, 10)
		percent = int((xp / needed) * 100) if needed > 0 else 0
		
		rank_title, rank_desc = self._get_rank_title(level)
		
		# Build embed
		embed = discord.Embed(color=Colors.XP)
		embed.set_author(name=f"{member.display_name}'s Profile", icon_url=member.display_avatar.url)
		embed.set_thumbnail(url=member.display_avatar.url)
		
		# Main stats in a cute format
		embed.description = f"{rank_title}\n*{rank_desc}*"
		
		embed.add_field(
			name="ðŸ“Š Level",
			value=f"```\n   {level}   \n```",
			inline=True
		)
		embed.add_field(
			name="ðŸ’ª XP Boost",
			value=f"```\n {multiplier:.1f}x \n```",
			inline=True
		)
		if server_rank:
			embed.add_field(
				name="ðŸ† Rank",
				value=f"```\n  #{server_rank}  \n```",
				inline=True
			)
		else:
			embed.add_field(
				name="âœ¨ Total XP",
				value=f"```\n{total:,}\n```",
				inline=True
			)
		
		# Progress section
		embed.add_field(
			name=f"Progress to Level {level + 1}",
			value=f"{bar}\n**{xp:,}** / **{needed:,}** XP ({percent}%)",
			inline=False
		)
		
		# XP sources info
		embed.add_field(
			name="ðŸ’¡ How to earn XP",
			value="ðŸ’¬ Chat messages â€¢ ðŸŽ¤ Voice channels â€¢ ðŸŒ Being online",
			inline=False
		)
		
		embed.set_footer(text="Keep being active to level up! ðŸŒŸ")
		return embed

	def _format_rank(self, member: discord.Member, entry: dict) -> str:
		"""Format rank display string (for prefix command)."""
		level = entry["level"]
		xp = entry["xp"]
		total = entry["total_xp"]
		needed = xp_required_for_level(level)
		bar = self._cute_progress_bar(xp, needed, 8)
		return f"ðŸ“Š {member.mention} | Lv **{level}** | {bar} {xp}/{needed} XP | Total: {total:,}"

	def _build_leaderboard(self, guild: discord.Guild, category: str) -> tuple[str, list[str], list]:
		"""Build leaderboard data. Returns (title, lines, sorted_data)."""
		gid = str(guild.id)
		
		# Position emojis for top 3
		position_emojis = ["ðŸ¥‡", "ðŸ¥ˆ", "ðŸ¥‰"]

		if category == "xp":
			data = self.bot.data["xp"].get(gid, {})
			sorted_data = sorted(data.items(), key=lambda x: x[1].get("total_xp", 0), reverse=True)[:10]
			title = "âœ¨ XP Leaderboard âœ¨"
			lines = []
			for i, (uid, entry) in enumerate(sorted_data, 1):
				member = guild.get_member(int(uid))
				name = member.display_name if member else f"User {uid}"
				level = entry.get('level', 1)
				total = entry.get('total_xp', 0)
				rank_title, _ = self._get_rank_title(level)
				pos = position_emojis[i-1] if i <= 3 else f"**{i}.**"
				lines.append(f"{pos} **{name}**\nã€€ã€€Lv {level} {rank_title} â€¢ {total:,} XP")
		else:
			data = self.bot.data["economy"].get(gid, {})
			sorted_data = sorted(data.items(), key=lambda x: x[1].get("funPoints", x[1].get("coins", 0)), reverse=True)[:10]
			title = "ðŸ’° funPoints Leaderboard ðŸ’°"
			lines = []
			for i, (uid, entry) in enumerate(sorted_data, 1):
				member = guild.get_member(int(uid))
				name = member.display_name if member else f"User {uid}"
				points = entry.get("funPoints", entry.get("coins", 0))
				pos = position_emojis[i-1] if i <= 3 else f"**{i}.**"
				lines.append(f"{pos} **{name}** â€” {points:,} funPoints")

		return title, lines, sorted_data

	# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
	# Commands
	# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
	@commands.command()
	async def rank(self, ctx: commands.Context, member: discord.Member = None):
		"""Show XP rank."""
		member = member or ctx.author
		entry = get_xp_entry(self.bot.data["xp"], ctx.guild.id, member.id)
		await ctx.send(self._format_rank(member, entry))

	@app_commands.command(name="rank", description="ðŸ“Š See your XP rank and level")
	@app_commands.describe(member="User to check")
	async def rank_slash(self, interaction: discord.Interaction, member: discord.Member = None):
		if not interaction.guild:
			await interaction.response.send_message("Use this in a server.", ephemeral=True)
			return
		member = member or interaction.user
		entry = get_xp_entry(self.bot.data["xp"], interaction.guild.id, member.id)
		
		# Calculate server rank
		gid = str(interaction.guild.id)
		data = self.bot.data["xp"].get(gid, {})
		sorted_data = sorted(data.items(), key=lambda x: x[1].get("total_xp", 0), reverse=True)
		server_rank = next((i for i, (uid, _) in enumerate(sorted_data, 1) if uid == str(member.id)), None)
		
		await interaction.response.send_message(embed=self._format_rank_embed(member, entry, server_rank))

	@commands.command()
	async def leaderboard(self, ctx: commands.Context, category: str = "xp"):
		"""View XP or funPoints leaderboard."""
		if not ctx.guild:
			await ctx.send("Use this in a server.")
			return

		category = category.lower()
		if category not in ("xp", "funpoints"):
			await ctx.send("Usage: `!leaderboard xp` or `!leaderboard funpoints`")
			return

		title, lines, _ = self._build_leaderboard(ctx.guild, category)
		if not lines:
			await ctx.send("No data yet!")
			return

		color = Colors.XP if category == "xp" else Colors.ECONOMY
		embed = discord.Embed(title=title, description="\n".join(lines), color=color)
		if ctx.guild.icon:
			embed.set_thumbnail(url=ctx.guild.icon.url)
		embed.set_footer(text=f"Top 10 in {ctx.guild.name} ðŸ†")
		await ctx.send(embed=embed)

	@app_commands.command(name="leaderboard", description="ðŸ† View XP or funPoints leaderboard")
	@app_commands.describe(category="Choose xp or funpoints")
	@app_commands.choices(category=[
		app_commands.Choice(name="âœ¨ XP", value="xp"),
		app_commands.Choice(name="ðŸŽ¯ funPoints", value="funpoints"),
	])
	async def leaderboard_slash(self, interaction: discord.Interaction, category: app_commands.Choice[str]):
		if not interaction.guild:
			await interaction.response.send_message("Use this in a server.", ephemeral=True)
			return

		title, lines, sorted_data = self._build_leaderboard(interaction.guild, category.value)
		if not lines:
			await interaction.response.send_message("ðŸ“Š No data yet! Start chatting to earn XP~", ephemeral=True)
			return

		# Enhanced embed
		color = Colors.XP if category.value == "xp" else Colors.ECONOMY
		embed = discord.Embed(
			title=title,
			description="\n".join(lines),
			color=color
		)
		
		# Show requester's position using already-sorted data
		uid_key = str(interaction.user.id)
		pos = next((i for i, (uid, _) in enumerate(sorted_data, 1) if uid == uid_key), None)
		if pos:
			embed.set_footer(text=f"Your position: #{pos} â€¢ {interaction.guild.name} ðŸ†")
		else:
			embed.set_footer(text=f"Top 10 in {interaction.guild.name} ðŸ†")
		
		if interaction.guild.icon:
			embed.set_thumbnail(url=interaction.guild.icon.url)
		
		await interaction.response.send_message(embed=embed)


	# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
	#                      LEVEL REWARDS
	# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
	
	def _get_level_rewards(self, guild_id: int) -> dict:
		"""Get level rewards config for a guild."""
		gid = str(guild_id)
		if "level_rewards" not in self.bot.data:
			self.bot.data["level_rewards"] = {}
		if gid not in self.bot.data["level_rewards"]:
			self.bot.data["level_rewards"][gid] = {}
		return self.bot.data["level_rewards"][gid]
	
	async def _grant_level_rewards(self, member: discord.Member, new_level: int) -> list:
		"""Grant any earned level rewards. Returns list of granted roles."""
		rewards = self._get_level_rewards(member.guild.id)
		granted = []
		
		for level_str, role_id in rewards.items():
			level = int(level_str)
			if level <= new_level:
				role = member.guild.get_role(role_id)
				if role and role not in member.roles:
					try:
						await member.add_roles(role, reason=f"Level reward for reaching level {level}")
						granted.append(role)
					except discord.Forbidden:
						pass
		
		return granted
	
	setlevel_group = app_commands.Group(name='setlevel', description='Configure level-up channel')

	@setlevel_group.command(name='channel', description='Set or clear level-up announcement channel')
	@app_commands.describe(channel='Channel for level-up announcements (leave empty to clear)')
	@app_commands.checks.has_permissions(administrator=True)
	async def setlevel_channel(self, interaction: discord.Interaction, channel: discord.TextChannel | None = None):
		if not interaction.guild:
			await interaction.response.send_message('Use this in a server.', ephemeral=True)
			return

		settings = self._get_level_settings(interaction.guild.id)
		me = interaction.guild.me or interaction.guild.get_member(self.bot.user.id if self.bot.user else 0)
		if not me:
			await interaction.response.send_message('I could not verify my permissions right now.', ephemeral=True)
			return

		if channel is None:
			settings.pop('levelup_channel_id', None)
			self.bot.mark_dirty()
			await interaction.response.send_message('Level-up channel cleared. New level-up messages will use fallback channels.')
			return

		perms = channel.permissions_for(me)
		if not (perms.send_messages and perms.embed_links):
			await interaction.response.send_message('I need Send Messages and Embed Links in that channel.', ephemeral=True)
			return

		settings['levelup_channel_id'] = channel.id
		self.bot.mark_dirty()
		await interaction.response.send_message(
			f'Level-up announcements will now be posted in {channel.mention}.',
			allowed_mentions=discord.AllowedMentions.none(),
		)

	levelrole_group = app_commands.Group(name="levelrole", description="Configure level rewards")
	
	@levelrole_group.command(name="add", description="ðŸŽ Add a role reward for reaching a level")
	@app_commands.describe(level="Level required to earn the role", role="Role to award")
	@app_commands.checks.has_permissions(administrator=True)
	async def levelrole_add(self, interaction: discord.Interaction, level: int, role: discord.Role):
		if not interaction.guild:
			await interaction.response.send_message("Use this in a server.", ephemeral=True)
			return
		
		if level < 1:
			await interaction.response.send_message("âŒ Level must be 1 or higher.", ephemeral=True)
			return
		
		if role >= interaction.guild.me.top_role:
			await interaction.response.send_message("âŒ That role is higher than my top role. I can't assign it.", ephemeral=True)
			return
		
		if role.managed:
			await interaction.response.send_message("âŒ That's a managed role (bot/integration). Can't use it.", ephemeral=True)
			return
		
		rewards = self._get_level_rewards(interaction.guild.id)
		rewards[str(level)] = role.id
		self.bot.mark_dirty()
		
		await interaction.response.send_message(
			f"âœ… **Level {level}** â†’ {role.mention}\n"
			f"Users reaching level {level} will automatically receive this role!",
			allowed_mentions=discord.AllowedMentions.none()
		)
	
	@levelrole_group.command(name="remove", description="âŒ Remove a level reward")
	@app_commands.describe(level="Level to remove reward from")
	@app_commands.checks.has_permissions(administrator=True)
	async def levelrole_remove(self, interaction: discord.Interaction, level: int):
		if not interaction.guild:
			await interaction.response.send_message("Use this in a server.", ephemeral=True)
			return
		
		rewards = self._get_level_rewards(interaction.guild.id)
		level_str = str(level)
		
		if level_str not in rewards:
			await interaction.response.send_message(f"âŒ No reward configured for level {level}.", ephemeral=True)
			return
		
		del rewards[level_str]
		self.bot.mark_dirty()
		
		await interaction.response.send_message(f"âœ… Removed level reward for level **{level}**.")
	
	@levelrole_group.command(name="list", description="ðŸ“‹ List all level rewards")
	async def levelrole_list(self, interaction: discord.Interaction):
		if not interaction.guild:
			await interaction.response.send_message("Use this in a server.", ephemeral=True)
			return
		
		rewards = self._get_level_rewards(interaction.guild.id)
		
		if not rewards:
			await interaction.response.send_message(
				"ðŸ“‹ **No level rewards configured!**\n"
				"Use `/levelrole add <level> <role>` to set up rewards.",
				ephemeral=True
			)
			return
		
		# Sort by level
		sorted_rewards = sorted(rewards.items(), key=lambda x: int(x[0]))
		
		lines = []
		for level_str, role_id in sorted_rewards:
			role = interaction.guild.get_role(role_id)
			role_text = role.mention if role else f"*Deleted Role ({role_id})*"
			lines.append(f"**Level {level_str}** â†’ {role_text}")
		
		embed = discord.Embed(
			title="ðŸŽ Level Rewards",
			description="\n".join(lines),
			color=Colors.XP
		)
		embed.set_footer(text=f"Total: {len(rewards)} reward(s) configured")
		
		await interaction.response.send_message(embed=embed, allowed_mentions=discord.AllowedMentions.none())


async def setup(bot: commands.Bot):
	await bot.add_cog(XP(bot))
