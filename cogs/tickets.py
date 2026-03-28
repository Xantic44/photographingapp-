"""
Tickets cog - Support ticket system with transcripts.
"""
import asyncio
import io
from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands

from core.helpers import save_data, mark_dirty, get_or_create_ticket_category, Colors


class Tickets(commands.Cog):
	"""Support ticket system."""

	def __init__(self, bot: commands.Bot):
		self.bot = bot
	
	def _get_config(self, guild_id: int) -> dict:
		"""Get ticket config for a guild."""
		gid = str(guild_id)
		if gid not in self.bot.data["tickets"]:
			self.bot.data["tickets"][gid] = {
				"category_id": None,
				"support_role_id": None,
				"counter": 0,
				"transcript_channel_id": None
			}
		elif "transcript_channel_id" not in self.bot.data["tickets"][gid]:
			self.bot.data["tickets"][gid]["transcript_channel_id"] = None
		return self.bot.data["tickets"][gid]
	
	async def _generate_transcript(self, channel: discord.TextChannel) -> str:
		"""Generate HTML transcript of a ticket channel."""
		messages = []
		async for msg in channel.history(limit=500, oldest_first=True):
			timestamp = msg.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")
			author = f"{msg.author.display_name} ({msg.author})"
			content = msg.content or ""
			
			# Handle embeds
			if msg.embeds:
				for embed in msg.embeds:
					if embed.title:
						content += f"\n[Embed: {embed.title}]"
					if embed.description:
						content += f"\n{embed.description[:200]}"
			
			# Handle attachments
			if msg.attachments:
				for att in msg.attachments:
					content += f"\n[Attachment: {att.filename}]"
			
			if content.strip():
				messages.append({
					"timestamp": timestamp,
					"author": author,
					"avatar": str(msg.author.display_avatar.url) if hasattr(msg.author, 'display_avatar') else "",
					"content": content,
					"bot": msg.author.bot
				})
		
		# Generate HTML
		html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>Transcript - {channel.name}</title>
<style>
body {{ font-family: 'Segoe UI', Arial, sans-serif; background: #36393f; color: #dcddde; margin: 0; padding: 20px; }}
.header {{ background: #2f3136; padding: 20px; border-radius: 8px; margin-bottom: 20px; }}
.header h1 {{ color: #fff; margin: 0 0 10px 0; }}
.header p {{ color: #72767d; margin: 5px 0; }}
.message {{ display: flex; padding: 10px 0; border-bottom: 1px solid #40444b; }}
.message:hover {{ background: #32353b; }}
.avatar {{ width: 40px; height: 40px; border-radius: 50%; margin-right: 15px; }}
.content {{ flex: 1; }}
.author {{ font-weight: 600; color: #fff; }}
.author.bot {{ color: #5865f2; }}
.timestamp {{ color: #72767d; font-size: 12px; margin-left: 10px; }}
.text {{ margin-top: 5px; white-space: pre-wrap; word-wrap: break-word; }}
</style>
</head>
<body>
<div class="header">
<h1>📩 Ticket Transcript</h1>
<p><strong>Channel:</strong> #{channel.name}</p>
<p><strong>Generated:</strong> {datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")}</p>
<p><strong>Messages:</strong> {len(messages)}</p>
</div>
"""
		
		for msg in messages:
			bot_class = "bot" if msg["bot"] else ""
			html += f"""
<div class="message">
<img src="{msg['avatar']}" class="avatar" onerror="this.style.display='none'">
<div class="content">
<span class="author {bot_class}">{msg['author']}</span>
<span class="timestamp">{msg['timestamp']}</span>
<div class="text">{msg['content']}</div>
</div>
</div>
"""
		
		html += "</body></html>"
		return html

	@app_commands.command(name="ticketsetup", description="⚙️ Configure support role for tickets")
	@app_commands.checks.has_permissions(manage_guild=True)
	@app_commands.describe(support_role="Role that can access tickets")
	async def ticketsetup(self, interaction: discord.Interaction, support_role: discord.Role):
		if not interaction.guild:
			await interaction.response.send_message("Use this in a server.", ephemeral=True)
			return

		config = self._get_config(interaction.guild.id)
		config["support_role_id"] = support_role.id
		mark_dirty()
		
		embed = discord.Embed(
			title="✅ Ticket System Configured!",
			description=f"Support role set to {support_role.mention}",
			color=Colors.SUCCESS
		)
		embed.add_field(name="📝 How it works", value="Users with ticket credits can create tickets with `/ticket`", inline=False)
		embed.set_footer(text="Use /givetickets to give users ticket credits!")
		await interaction.response.send_message(embed=embed)
	
	@app_commands.command(name="tickettranscripts", description="📜 Set transcript log channel")
	@app_commands.checks.has_permissions(manage_guild=True)
	@app_commands.describe(channel="Channel to save transcripts (leave empty to disable)")
	async def tickettranscripts(self, interaction: discord.Interaction, channel: discord.TextChannel = None):
		if not interaction.guild:
			await interaction.response.send_message("Use this in a server.", ephemeral=True)
			return
		
		config = self._get_config(interaction.guild.id)
		
		if channel:
			config["transcript_channel_id"] = channel.id
			mark_dirty()
			await interaction.response.send_message(
				f"✅ Ticket transcripts will be saved to {channel.mention}\n"
				f"Transcripts will also be DM'd to ticket creators."
			)
		else:
			config["transcript_channel_id"] = None
			mark_dirty()
			await interaction.response.send_message(
				"✅ Transcript logging disabled.\n"
				"Transcripts will still be DM'd to ticket creators."
			)

	@app_commands.command(name="ticket", description="🎫 Create a private support ticket")
	@app_commands.describe(reason="Reason for the ticket")
	async def ticket(self, interaction: discord.Interaction, reason: str):
		if not interaction.guild:
			await interaction.response.send_message("Use this in a server.", ephemeral=True)
			return

		guild = interaction.guild
		guild_id = str(guild.id)
		user_id = str(interaction.user.id)

		# Check ticket credits
		credits_store = self.bot.data.setdefault("ticket_credits", {}).setdefault(guild_id, {})
		user_credits = credits_store.get(user_id, 0)

		if user_credits < 1:
			embed = discord.Embed(
				title="❌ No Ticket Credits!",
				description="You don't have any ticket credits.\n\nAsk an admin to give you tickets with `/givetickets`.",
				color=Colors.ERROR
			)
			embed.set_footer(text="Ticket credits are required to create support tickets!")
			await interaction.response.send_message(embed=embed, ephemeral=True)
			return

		# Deduct 1 credit
		credits_store[user_id] = user_credits - 1

		entry = self.bot.data["tickets"].setdefault(guild_id, {"category_id": None, "support_role_id": None, "counter": 0})
		category = await get_or_create_ticket_category(self.bot, guild)
		entry["counter"] += 1
		ticket_number = entry["counter"]

		overwrites = {
			guild.default_role: discord.PermissionOverwrite(view_channel=False),
			interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
		}
		support_role_id = entry.get("support_role_id")
		if support_role_id:
			role = guild.get_role(int(support_role_id))
			if role:
				overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

		channel_name = f"ticket-{ticket_number:04d}"
		channel = await guild.create_text_channel(channel_name, category=category, overwrites=overwrites)
		mark_dirty()

		# Response to user
		embed = discord.Embed(
			title="🎫 Ticket Created!",
			description=f"Your ticket has been created: {channel.mention}",
			color=Colors.TICKET
		)
		embed.add_field(name="📋 Ticket #", value=f"`{ticket_number:04d}`", inline=True)
		embed.add_field(name="💳 Remaining Credits", value=f"**{credits_store[user_id]}**", inline=True)
		embed.set_footer(text="A support member will be with you shortly! 💕")
		await interaction.response.send_message(embed=embed, ephemeral=True)
		
		# Welcome message in ticket channel
		welcome_embed = discord.Embed(
			title="📩 New Support Ticket",
			description=f"Welcome {interaction.user.mention}!\n\nThank you for reaching out. A support team member will assist you shortly.",
			color=Colors.TICKET
		)
		welcome_embed.add_field(name="📝 Reason", value=reason, inline=False)
		welcome_embed.add_field(name="🔒 Close Ticket", value="Use `/close` when you're done!", inline=False)
		welcome_embed.set_footer(text=f"Ticket #{ticket_number:04d}")
		welcome_embed.set_thumbnail(url=interaction.user.display_avatar.url)
		await channel.send(embed=welcome_embed)

	@app_commands.command(name="close", description="🔒 Close the current ticket channel")
	async def close(self, interaction: discord.Interaction):
		if not interaction.guild or not isinstance(interaction.channel, discord.TextChannel):
			await interaction.response.send_message("Use this in a ticket channel.", ephemeral=True)
			return
		if not interaction.channel.name.startswith("ticket-"):
			await interaction.response.send_message("❌ This is not a ticket channel.", ephemeral=True)
			return

		await interaction.response.defer()
		
		# Generate transcript
		config = self._get_config(interaction.guild.id)
		transcript_html = await self._generate_transcript(interaction.channel)
		
		# Create file
		transcript_file = discord.File(
			io.BytesIO(transcript_html.encode('utf-8')),
			filename=f"transcript-{interaction.channel.name}.html"
		)
		
		# Send to transcript channel if configured
		transcript_sent = False
		if config.get("transcript_channel_id"):
			transcript_channel = interaction.guild.get_channel(config["transcript_channel_id"])
			if transcript_channel:
				embed = discord.Embed(
					title="📜 Ticket Transcript",
					description=f"**Channel:** #{interaction.channel.name}\n**Closed by:** {interaction.user.mention}",
					color=Colors.TICKET,
					timestamp=discord.utils.utcnow()
				)
				embed.set_footer(text="Download the HTML file to view the transcript")
				try:
					await transcript_channel.send(embed=embed, file=transcript_file)
					transcript_sent = True
					# Recreate file for user DM
					transcript_file = discord.File(
						io.BytesIO(transcript_html.encode('utf-8')),
						filename=f"transcript-{interaction.channel.name}.html"
					)
				except discord.Forbidden:
					pass
		
		# Try to DM transcript to ticket creator
		# Find the user from channel topic or first non-bot message
		ticket_creator = None
		async for msg in interaction.channel.history(limit=10, oldest_first=True):
			if not msg.author.bot and msg.mentions:
				ticket_creator = msg.mentions[0]
				break
			elif not msg.author.bot:
				ticket_creator = msg.author
				break
		
		if ticket_creator and not ticket_creator.bot:
			try:
				dm_embed = discord.Embed(
					title="📜 Your Ticket Transcript",
					description=f"Your ticket in **{interaction.guild.name}** has been closed.\n\nAttached is a transcript of the conversation.",
					color=Colors.TICKET
				)
				await ticket_creator.send(embed=dm_embed, file=transcript_file)
			except discord.Forbidden:
				pass  # Can't DM user
		
		embed = discord.Embed(
			title="🔒 Closing Ticket...",
			description="This ticket will be closed in **5 seconds**.\n\nThank you for using our support system! 💕",
			color=Colors.WARNING
		)
		if transcript_sent:
			embed.add_field(name="📜 Transcript", value="Saved to transcript channel", inline=False)
		embed.set_footer(text=f"Closed by {interaction.user.display_name}")
		await interaction.followup.send(embed=embed)
		await asyncio.sleep(5)
		await interaction.channel.delete(reason=f"Closed by {interaction.user}")

	@app_commands.command(name="givetickets", description="🎁 Give ticket credits to a user")
	@app_commands.checks.has_permissions(manage_guild=True)
	@app_commands.describe(user="User to give tickets to", amount="Number of ticket credits")
	async def givetickets(self, interaction: discord.Interaction, user: discord.Member, amount: int):
		if not interaction.guild:
			await interaction.response.send_message("Use this in a server.", ephemeral=True)
			return

		if amount < 1:
			await interaction.response.send_message("❌ Amount must be at least 1.", ephemeral=True)
			return

		guild_id = str(interaction.guild.id)
		user_id = str(user.id)

		credits_store = self.bot.data.setdefault("ticket_credits", {}).setdefault(guild_id, {})
		current = credits_store.get(user_id, 0)
		credits_store[user_id] = current + amount
		mark_dirty()

		embed = discord.Embed(
			title="🎫 Ticket Credits Granted!",
			color=Colors.SUCCESS
		)
		embed.add_field(name="👤 User", value=user.mention, inline=True)
		embed.add_field(name="➕ Given", value=f"**+{amount}**", inline=True)
		embed.add_field(name="💳 Total", value=f"**{credits_store[user_id]}**", inline=True)
		embed.set_footer(text=f"Granted by {interaction.user.display_name}")
		embed.set_thumbnail(url=user.display_avatar.url)
		await interaction.response.send_message(embed=embed)

	@app_commands.command(name="checktickets", description="💳 Check ticket credits")
	@app_commands.describe(user="User to check (leave empty for yourself)")
	async def checktickets(self, interaction: discord.Interaction, user: discord.Member | None = None):
		if not interaction.guild:
			await interaction.response.send_message("Use this in a server.", ephemeral=True)
			return

		target = user or interaction.user
		guild_id = str(interaction.guild.id)
		user_id = str(target.id)

		credits_store = self.bot.data.setdefault("ticket_credits", {}).setdefault(guild_id, {})
		credits = credits_store.get(user_id, 0)

		embed = discord.Embed(
			title="🎫 Ticket Credits",
			color=Colors.TICKET
		)
		embed.set_author(name=target.display_name, icon_url=target.display_avatar.url)
		embed.add_field(name="💳 Balance", value=f"```{credits} credits```", inline=False)
		
		if credits == 0:
			embed.set_footer(text="No credits! Ask an admin for some 💕")
		else:
			embed.set_footer(text=f"Use /ticket to create a support ticket!")
		
		await interaction.response.send_message(embed=embed)

	@app_commands.command(name="removetickets", description="➖ Remove ticket credits from a user")
	@app_commands.checks.has_permissions(manage_guild=True)
	@app_commands.describe(user="User to remove tickets from", amount="Number to remove")
	async def removetickets(self, interaction: discord.Interaction, user: discord.Member, amount: int):
		if not interaction.guild:
			await interaction.response.send_message("Use this in a server.", ephemeral=True)
			return

		if amount < 1:
			await interaction.response.send_message("❌ Amount must be at least 1.", ephemeral=True)
			return

		guild_id = str(interaction.guild.id)
		user_id = str(user.id)

		credits_store = self.bot.data.setdefault("ticket_credits", {}).setdefault(guild_id, {})
		current = credits_store.get(user_id, 0)
		removed = min(amount, current)
		new_balance = max(0, current - amount)
		credits_store[user_id] = new_balance
		mark_dirty()

		embed = discord.Embed(
			title="🎫 Ticket Credits Removed",
			color=Colors.WARNING
		)
		embed.add_field(name="👤 User", value=user.mention, inline=True)
		embed.add_field(name="➖ Removed", value=f"**-{removed}**", inline=True)
		embed.add_field(name="💳 Remaining", value=f"**{new_balance}**", inline=True)
		embed.set_footer(text=f"Removed by {interaction.user.display_name}")
		await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
	await bot.add_cog(Tickets(bot))
