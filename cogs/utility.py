"""
Utility cog - General utility and fun commands.
"""
import asyncio
import random
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from core.helpers import started_at, Colors, cute_greeting


class Utility(commands.Cog):
	"""General utility and fun commands."""

	def __init__(self, bot: commands.Bot):
		self.bot = bot

	# ─────────────────────────────────────────────────────────────────────────
	# Prefix commands
	# ─────────────────────────────────────────────────────────────────────────
	@commands.command()
	async def ping(self, ctx):
		latency_ms = round(self.bot.latency * 1000)
		embed = discord.Embed(
			description=f"🏓 **Pong!** `{latency_ms}ms`",
			color=Colors.SUCCESS if latency_ms < 200 else Colors.WARNING
		)
		await ctx.send(embed=embed)

	@commands.command()
	async def hello(self, ctx, member: discord.Member | None = None):
		target = member or ctx.author
		embed = discord.Embed(
			description=cute_greeting(target.display_name),
			color=Colors.INFO
		)
		embed.set_thumbnail(url=target.display_avatar.url)
		await ctx.send(embed=embed)

	@commands.command()
	async def uptime(self, ctx):
		now = datetime.now(timezone.utc)
		delta = now - started_at
		total_seconds = int(delta.total_seconds())
		days, remainder = divmod(total_seconds, 86400)
		hours, remainder = divmod(remainder, 3600)
		minutes, seconds = divmod(remainder, 60)
		
		time_parts = []
		if days: time_parts.append(f"**{days}**d")
		if hours: time_parts.append(f"**{hours}**h")
		if minutes: time_parts.append(f"**{minutes}**m")
		time_parts.append(f"**{seconds}**s")
		
		embed = discord.Embed(
			title="⏰ Bot Uptime",
			description=f"Online for {' '.join(time_parts)} ✨",
			color=Colors.INFO
		)
		embed.set_footer(text="Running smooth like butter~")
		await ctx.send(embed=embed)

	@commands.command()
	async def serverinfo(self, ctx):
		guild = ctx.guild
		embed = discord.Embed(title=f"✨ {guild.name}", color=Colors.INFO)
		embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
		embed.add_field(name="👑 Owner", value=guild.owner.mention if guild.owner else "Unknown", inline=True)
		embed.add_field(name="👥 Members", value=f"**{guild.member_count:,}**", inline=True)
		embed.add_field(name="💬 Channels", value=f"**{len(guild.channels)}**", inline=True)
		embed.add_field(name="🎭 Roles", value=f"**{len(guild.roles)}**", inline=True)
		embed.add_field(name="📅 Created", value=f"<t:{int(guild.created_at.timestamp())}:R>", inline=True)
		embed.add_field(name="🚀 Boosts", value=f"**{guild.premium_subscription_count}** (Lvl {guild.premium_tier})", inline=True)
		embed.set_footer(text=f"ID: {guild.id}")
		await ctx.send(embed=embed)

	@commands.command()
	async def roll(self, ctx, sides: int = 6):
		if sides < 2:
			await ctx.send("Sides must be at least 2.")
			return
		result = random.randint(1, sides)
		embed = discord.Embed(color=Colors.INFO)
		embed.description = f"🎲 Rolling a **d{sides}**...\n\n# 「 {result} 」"
		if result == sides:
			embed.set_footer(text="✨ Natural max roll!")
			embed.color = Colors.SUCCESS
		elif result == 1:
			embed.set_footer(text="💀 Critical fail...")
			embed.color = Colors.ERROR
		await ctx.send(embed=embed)

	@commands.command()
	async def choose(self, ctx, *, options: str):
		choices = [opt.strip() for opt in options.split(",") if opt.strip()]
		if len(choices) < 2:
			await ctx.send("Give at least 2 options separated by commas.")
			return
		choice = random.choice(choices)
		embed = discord.Embed(
			title="🤔 Hmm, let me think...",
			description=f"I choose: **{choice}**! ✨",
			color=Colors.INFO
		)
		embed.set_footer(text=f"From {len(choices)} options")
		await ctx.send(embed=embed)

	# ─────────────────────────────────────────────────────────────────────────
	# Slash commands
	# ─────────────────────────────────────────────────────────────────────────
	@app_commands.command(name="ping", description="🏓 Check bot latency")
	async def ping_slash(self, interaction: discord.Interaction):
		latency_ms = round(self.bot.latency * 1000)
		
		# Cute performance indicator
		if latency_ms < 100:
			status = "⚡ Lightning fast!"
		elif latency_ms < 200:
			status = "✨ Looking good!"
		elif latency_ms < 400:
			status = "🐢 A bit slow today..."
		else:
			status = "🦥 Very sleepy..."
		
		embed = discord.Embed(color=Colors.SUCCESS if latency_ms < 200 else Colors.WARNING)
		embed.add_field(name="🏓 Pong!", value=f"```{latency_ms}ms```", inline=True)
		embed.add_field(name="Status", value=status, inline=True)
		embed.set_footer(text=f"Requested by {interaction.user.display_name}")
		await interaction.response.send_message(embed=embed)

	@app_commands.command(name="hello", description="👋 Get a friendly greeting")
	async def hello_slash(self, interaction: discord.Interaction):
		embed = discord.Embed(
			description=cute_greeting(interaction.user.display_name),
			color=Colors.INFO
		)
		embed.set_thumbnail(url=interaction.user.display_avatar.url)
		await interaction.response.send_message(embed=embed)

	@app_commands.command(name="uptime", description="⏰ Check how long the bot has been running")
	async def uptime_slash(self, interaction: discord.Interaction):
		now = datetime.now(timezone.utc)
		delta = now - started_at
		total_seconds = int(delta.total_seconds())
		days, remainder = divmod(total_seconds, 86400)
		hours, remainder = divmod(remainder, 3600)
		minutes, seconds = divmod(remainder, 60)
		
		# Build time display
		time_parts = []
		if days: time_parts.append(f"**{days}**d")
		if hours: time_parts.append(f"**{hours}**h")
		if minutes: time_parts.append(f"**{minutes}**m")
		time_parts.append(f"**{seconds}**s")
		
		embed = discord.Embed(
			title="⏰ Bot Uptime",
			color=Colors.INFO
		)
		embed.add_field(name="🕐 Online For", value=" ".join(time_parts), inline=True)
		embed.add_field(name="📅 Since", value=f"<t:{int(started_at.timestamp())}:F>", inline=True)
		embed.set_footer(text="Running smooth like butter~ 🧈")
		await interaction.response.send_message(embed=embed)

	@app_commands.command(name="serverinfo", description="📊 Get detailed server information")
	async def serverinfo_slash(self, interaction: discord.Interaction):
		if not interaction.guild:
			await interaction.response.send_message("Use this in a server.", ephemeral=True)
			return
		guild = interaction.guild
		
		# Count channel types
		text_channels = len([c for c in guild.channels if isinstance(c, discord.TextChannel)])
		voice_channels = len([c for c in guild.channels if isinstance(c, discord.VoiceChannel)])
		categories = len([c for c in guild.channels if isinstance(c, discord.CategoryChannel)])
		
		# Online members
		online = sum(1 for m in guild.members if m.status != discord.Status.offline)
		
		embed = discord.Embed(
			title=f"✨ {guild.name}",
			description=guild.description or "",
			color=Colors.INFO
		)
		if guild.icon:
			embed.set_thumbnail(url=guild.icon.url)
		if guild.banner:
			embed.set_image(url=guild.banner.url)
			
		embed.add_field(name="👑 Owner", value=guild.owner.mention if guild.owner else "Unknown", inline=True)
		embed.add_field(name="👥 Members", value=f"**{guild.member_count:,}** ({online:,} online)", inline=True)
		embed.add_field(name="🎭 Roles", value=f"**{len(guild.roles) - 1}**", inline=True)
		
		embed.add_field(name="💬 Channels", value=f"📝 {text_channels} • 🔊 {voice_channels} • 📁 {categories}", inline=True)
		embed.add_field(name="🚀 Boost Level", value=f"Level **{guild.premium_tier}** ({guild.premium_subscription_count} boosts)", inline=True)
		embed.add_field(name="📅 Created", value=f"<t:{int(guild.created_at.timestamp())}:R>", inline=True)
		
		embed.set_footer(text=f"ID: {guild.id}")
		await interaction.response.send_message(embed=embed)

	@app_commands.command(name="roll", description="🎲 Roll a dice")
	@app_commands.describe(sides="Number of sides (default: 6)")
	async def roll_slash(self, interaction: discord.Interaction, sides: int = 6):
		if sides < 2:
			await interaction.response.send_message("❌ Sides must be at least 2.", ephemeral=True)
			return
		if sides > 1000:
			await interaction.response.send_message("❌ Max 1000 sides!", ephemeral=True)
			return
			
		result = random.randint(1, sides)
		
		embed = discord.Embed(color=Colors.INFO)
		embed.set_author(name=f"{interaction.user.display_name} rolls a d{sides}!", icon_url=interaction.user.display_avatar.url)
		embed.description = f"🎲 The dice tumbles...\n\n# 「 {result} 」"
		
		if result == sides:
			embed.color = Colors.SUCCESS
			embed.set_footer(text="✨ Natural max! So lucky~")
		elif result == 1:
			embed.color = Colors.ERROR
			embed.set_footer(text="💀 Critical fail... oof")
		else:
			embed.set_footer(text=f"Rolled {result}/{sides}")
			
		await interaction.response.send_message(embed=embed)

	@app_commands.command(name="choose", description="🤔 Let the bot choose for you")
	@app_commands.describe(options="Options separated by commas (e.g., pizza, sushi, burgers)")
	async def choose_slash(self, interaction: discord.Interaction, options: str):
		choices = [opt.strip() for opt in options.split(",") if opt.strip()]
		if len(choices) < 2:
			await interaction.response.send_message("❌ Give at least 2 options separated by commas.", ephemeral=True)
			return
		
		choice = random.choice(choices)
		
		embed = discord.Embed(
			title="🎱 The Oracle Speaks...",
			color=Colors.INFO
		)
		embed.add_field(name="Options", value=" • ".join(f"`{c}`" for c in choices), inline=False)
		embed.add_field(name="✨ I choose...", value=f"# {choice}", inline=False)
		embed.set_footer(text=f"Requested by {interaction.user.display_name} • The decision is final!")
		await interaction.response.send_message(embed=embed)

	@app_commands.command(name="remind", description="⏰ Set a reminder")
	@app_commands.describe(seconds="Seconds until reminder (1-86400)", message="What to remind you")
	async def remind_slash(self, interaction: discord.Interaction, seconds: int, message: str):
		if seconds < 1 or seconds > 86400:
			await interaction.response.send_message("❌ Seconds must be between 1 and 86400 (24 hours).", ephemeral=True)
			return

		# Format time nicely
		if seconds >= 3600:
			time_str = f"{seconds // 3600}h {(seconds % 3600) // 60}m"
		elif seconds >= 60:
			time_str = f"{seconds // 60}m {seconds % 60}s"
		else:
			time_str = f"{seconds}s"

		embed = discord.Embed(
			title="⏰ Reminder Set!",
			description=f"I'll remind you in **{time_str}**~",
			color=Colors.INFO
		)
		embed.add_field(name="📝 Message", value=message, inline=False)
		embed.set_footer(text=f"Reminding {interaction.user.display_name}")
		await interaction.response.send_message(embed=embed)
		
		await asyncio.sleep(seconds)
		
		remind_embed = discord.Embed(
			title="🔔 REMINDER!",
			description=f"Hey {interaction.user.mention}!\n\n**{message}**",
			color=Colors.WARNING
		)
		remind_embed.set_footer(text="You asked me to remind you about this~")
		await interaction.followup.send(embed=remind_embed)

	@app_commands.command(name="poll", description="📊 Create an interactive poll with live results")
	@app_commands.describe(
		question="Poll question",
		options="Options separated by | (e.g., Yes | No | Maybe)",
		duration="Duration in minutes (0 = no limit, max 60)"
	)
	async def poll_slash(self, interaction: discord.Interaction, question: str, options: str, duration: int = 0):
		opts = [opt.strip() for opt in options.split("|") if opt.strip()]
		if len(opts) < 2 or len(opts) > 5:
			await interaction.response.send_message("❌ Provide 2-5 options separated by |", ephemeral=True)
			return
		
		if duration < 0 or duration > 60:
			await interaction.response.send_message("❌ Duration must be 0-60 minutes", ephemeral=True)
			return

		view = PollView(question, opts, interaction.user, duration)
		embed = view.build_embed()
		
		await interaction.response.send_message(embed=embed, view=view)
		msg = await interaction.original_response()
		view.message = msg
		
		# If duration set, auto-end the poll
		if duration > 0:
			await asyncio.sleep(duration * 60)
			view.ended = True
			for item in view.children:
				item.disabled = True
			embed = view.build_embed(ended=True)
			try:
				await msg.edit(embed=embed, view=view)
			except Exception:
				pass


class PollView(discord.ui.View):
	"""Interactive poll with live vote tracking."""
	
	def __init__(self, question: str, options: list, author: discord.User, duration: int = 0):
		super().__init__(timeout=None if duration == 0 else duration * 60 + 30)
		self.question = question
		self.options = options
		self.author = author
		self.duration = duration
		self.votes: dict[int, int] = {}  # user_id -> option_index
		self.message = None
		self.ended = False
		
		# Button colors/emojis
		colors = [
			discord.ButtonStyle.primary,
			discord.ButtonStyle.success,
			discord.ButtonStyle.danger,
			discord.ButtonStyle.secondary,
			discord.ButtonStyle.primary
		]
		emojis = ["🔵", "🟢", "🔴", "⚪", "🟣"]
		
		for i, opt in enumerate(options):
			btn = discord.ui.Button(
				label=opt[:40],
				style=colors[i],
				emoji=emojis[i],
				custom_id=f"poll_opt_{i}"
			)
			btn.callback = self.make_callback(i)
			self.add_item(btn)
	
	def make_callback(self, index: int):
		async def callback(interaction: discord.Interaction):
			if self.ended:
				await interaction.response.send_message("❌ This poll has ended!", ephemeral=True)
				return
			
			user_id = interaction.user.id
			previous = self.votes.get(user_id)
			
			if previous == index:
				# Remove vote
				del self.votes[user_id]
				await interaction.response.send_message(f"🗑️ Vote removed!", ephemeral=True)
			else:
				# Add/change vote
				self.votes[user_id] = index
				if previous is not None:
					await interaction.response.send_message(f"✅ Vote changed to **{self.options[index]}**!", ephemeral=True)
				else:
					await interaction.response.send_message(f"✅ Voted for **{self.options[index]}**!", ephemeral=True)
			
			# Update embed with new results
			embed = self.build_embed()
			await interaction.message.edit(embed=embed)
		
		return callback
	
	def build_embed(self, ended: bool = False) -> discord.Embed:
		"""Build the poll embed with current vote counts."""
		total = len(self.votes)
		
		embed = discord.Embed(
			title="📊 Poll" + (" (Ended)" if ended else ""),
			color=Colors.WARNING if ended else Colors.INFO
		)
		embed.add_field(name="❓ Question", value=f"**{self.question}**", inline=False)
		
		# Build results
		emojis = ["🔵", "🟢", "🔴", "⚪", "🟣"]
		results = []
		
		for i, opt in enumerate(self.options):
			count = sum(1 for v in self.votes.values() if v == i)
			percentage = (count / total * 100) if total > 0 else 0
			
			# Progress bar
			bar_filled = int(percentage / 10)
			bar = "█" * bar_filled + "░" * (10 - bar_filled)
			
			results.append(f"{emojis[i]} **{opt}**\n{bar} `{percentage:.0f}%` ({count} vote{'s' if count != 1 else ''})")
		
		embed.add_field(name="📋 Results", value="\n\n".join(results), inline=False)
		
		# Footer
		footer_parts = [f"Total: {total} vote{'s' if total != 1 else ''}"]
		footer_parts.append(f"Poll by {self.author.display_name}")
		if self.duration > 0 and not ended:
			footer_parts.append(f"⏱️ {self.duration} min")
		embed.set_footer(text=" • ".join(footer_parts))
		
		if self.author.display_avatar:
			embed.set_thumbnail(url=self.author.display_avatar.url)
		
		return embed

	@app_commands.command(name="clear", description="Delete messages in bulk")
	@app_commands.checks.has_permissions(manage_messages=True)
	@app_commands.checks.bot_has_permissions(manage_messages=True)
	@app_commands.describe(amount="Number of messages to delete (1-100)")
	async def clear_slash(self, interaction: discord.Interaction, amount: int):
		if amount < 1 or amount > 100:
			await interaction.response.send_message("Choose a number from 1 to 100.", ephemeral=True)
			return

		await interaction.response.defer(ephemeral=True)
		deleted = await interaction.channel.purge(limit=amount)
		await interaction.followup.send(f"🧹 Deleted **{len(deleted)}** messages.", ephemeral=True)

	@app_commands.command(name="hpbcommands", description="📖 View all bot commands with descriptions")
	async def hpbcommands(self, interaction: discord.Interaction):
		# Define all commands organized by category
		commands_data = {
			"🛠️ Utility": [
				("`/ping`", "Check bot latency"),
				("`/hello`", "Get a friendly greeting"),
				("`/uptime`", "Check how long the bot has been running"),
				("`/serverinfo`", "View server information"),
				("`/roll`", "Roll a dice (default: d6)"),
				("`/choose`", "Let the bot choose between options"),
				("`/remind`", "Set a timed reminder"),
				("`/poll`", "Create a poll with reactions"),
				("`/clear`", "Delete messages in bulk (mod only)"),
				("`/hpbcommands`", "Show this help menu"),
			],
			"👤 Profile": [
				("`/userinfo`", "View detailed user information"),
				("`/setlocation`", "Set your location on your profile"),
				("`/setbio`", "Set your bio on your profile"),
				("`/setstatus`", "Set a custom voice channel status"),
				("`/clearstatus`", "Clear your voice channel status"),
				("`/clearprofile`", "Reset your profile data"),
			],
			"📈 XP & Levels": [
				("`/rank`", "View your XP rank and level"),
				("`/leaderboard`", "View XP or funPoints leaderboard"),
			],
			"💰 Economy": [
				("`/balance`", "Check your funPoints balance"),
				("`/daily`", "Claim daily funPoints (24h cooldown)"),
				("`/work`", "Work for funPoints (1h cooldown)"),
				("`/pay`", "Send funPoints to another user"),
				("`/funleaderboard`", "See the richest users"),
			],
			"🎰 Gambling": [
				("`/coinflip`", "Flip a coin and bet funPoints"),
				("`/gamble`", "Roll dice to win/lose funPoints"),
				("`/slots`", "Spin the slot machine"),
			],
			"🎫 Tickets": [
				("`/ticketsetup`", "Set up the ticket system (admin)"),
				("`/ticket`", "Create a support ticket"),
				("`/close`", "Close a ticket"),
				("`/givetickets`", "Give ticket credits (admin)"),
				("`/checktickets`", "Check remaining ticket credits"),
				("`/removetickets`", "Remove ticket credits (admin)"),
			],
			"🛡️ Moderation": [
				("`/automod`", "Toggle automod on/off (admin)"),
				("`/addblockedword`", "Add a blocked word (admin)"),
				("`/setlogchannel`", "Set the automod log channel (admin)"),
			],
			"🎵 Music": [
				("`/play`", "Play a song from YouTube/Spotify"),
				("`/skip`", "Skip the current song"),
				("`/stop`", "Stop playback and clear queue"),
				("`/pause`", "Pause the current song"),
				("`/resume`", "Resume paused playback"),
				("`/queue`", "View the music queue"),
				("`/volume`", "Set playback volume (0-100)"),
				("`/loop`", "Toggle loop mode"),
				("`/join`", "Make the bot join your voice channel"),
				("`/leave`", "Make the bot leave voice channel"),
				("`/shuffle`", "Shuffle the queue"),
				("`/clearqueue`", "Clear all songs from queue"),
				("`/remove`", "Remove a song by position"),
				("`/setmusicchannel`", "Set music log channel (admin)"),
				("`/transferdj`", "Transfer DJ control"),
				("`/musicstatus`", "Show music system status"),
			],
			"⚙️ Admin": [
				("`/setwelcome`", "Set welcome channel (admin)"),
				("`/setwelcomemessage`", "Set welcome message (admin)"),
				("`/givefunpoints`", "Give funPoints to user (admin)"),
				("`/removefunpoints`", "Remove funPoints (admin)"),
				("`/setfunpoints`", "Set user's balance (admin)"),
			],
			"📅 Events": [
				("`/event create`", "Create a scheduled server event"),
				("`/event list`", "List all scheduled events"),
				("`/event cancel`", "Cancel a scheduled event"),
				("`/event start`", "Start an event now"),
				("`/event end`", "End an active event"),
			],
			"🔗 Linked Roles": [
				("`/linkedrole setup`", "Configure connection-linked roles"),
				("`/linkedrole claim`", "Claim roles from your connections"),
				("`/linkedrole verify`", "Verify user connection (mod)"),
				("`/linkedrole list`", "View linked role configs"),
			],
			"🎨 App Emojis": [
				("`/appemoji list`", "List bot application emojis"),
				("`/appemoji add`", "Add an application emoji (owner)"),
				("`/appemoji delete`", "Delete an application emoji"),
				("`/appemoji use`", "Send a message with app emoji"),
			],
			"🎭 Role Management": [
				("`/role give`", "Give a role to a user"),
				("`/role remove`", "Remove a role from a user"),
				("`/role info`", "Get info about a role"),
				("`/role members`", "List members with a role"),
				("`/role all`", "List all server roles"),
				("`/role create`", "Create a new role"),
				("`/role delete`", "Delete a role"),
				("`/role color`", "Change a role's color"),
				("`/role massadd`", "Give role to multiple members"),
			],
		}

		# Build embeds (multiple pages if needed)
		embed = discord.Embed(
			title="📖 HPB Bot Commands",
			description="All available slash commands organized by category.\nUse these commands by typing `/` followed by the command name.",
			color=discord.Color.blurple()
		)

		for category, cmds in commands_data.items():
			lines = [f"{cmd} — {desc}" for cmd, desc in cmds]
			embed.add_field(name=category, value="\n".join(lines), inline=False)

		embed.set_footer(text=f"Total: {sum(len(c) for c in commands_data.values())} commands • Requested by {interaction.user.display_name}")
		
		if interaction.guild and interaction.guild.icon:
			embed.set_thumbnail(url=interaction.guild.icon.url)

		await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
	await bot.add_cog(Utility(bot))
