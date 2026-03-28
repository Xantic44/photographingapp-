"""
Suggestions Cog - User suggestion system with voting
"""
import time

import discord
from discord import app_commands
from discord.ext import commands

from core.helpers import Colors, logger


# ═══════════════════════════════════════════════════════════════════════════
#                           SUGGESTIONS COG
# ═══════════════════════════════════════════════════════════════════════════
class Suggestions(commands.Cog):
	"""User suggestion system with voting and status tracking."""
	
	def __init__(self, bot: commands.Bot):
		self.bot = bot
	
	def _get_config(self, guild_id: int) -> dict:
		"""Get suggestions config for a guild."""
		gid = str(guild_id)
		if "suggestions" not in self.bot.data:
			self.bot.data["suggestions"] = {}
		if gid not in self.bot.data["suggestions"]:
			self.bot.data["suggestions"][gid] = {
				"channel_id": None,
				"next_id": 1,
				"suggestions": {}  # {suggestion_id: data}
			}
		return self.bot.data["suggestions"][gid]
	
	def _create_suggestion_embed(self, suggestion_id: int, content: str, author: discord.Member | discord.User, status: str = "pending", staff_note: str = None) -> discord.Embed:
		"""Create suggestion embed."""
		status_info = {
			"pending": ("📋 Pending Review", Colors.SUGGESTION),
			"approved": ("✅ Approved", Colors.APPROVED),
			"denied": ("❌ Denied", Colors.DENIED),
			"implemented": ("🚀 Implemented", Colors.IMPLEMENTED),
		}
		
		title, color = status_info.get(status, status_info["pending"])
		
		embed = discord.Embed(
			title=f"Suggestion #{suggestion_id}",
			description=content,
			color=color
		)
		embed.set_author(name=author.display_name, icon_url=author.display_avatar.url if hasattr(author, 'display_avatar') else None)
		embed.add_field(name="Status", value=title, inline=True)
		
		if staff_note:
			embed.add_field(name="📝 Staff Note", value=staff_note, inline=False)
		
		embed.set_footer(text=f"Vote with 👍 or 👎")
		
		return embed
	
	# ─────────────────────────────────────────────────────────────────────────
	#                            COMMANDS
	# ─────────────────────────────────────────────────────────────────────────
	
	@app_commands.command(name="suggest", description="💡 Submit a suggestion")
	@app_commands.describe(suggestion="Your suggestion")
	async def suggest(self, interaction: discord.Interaction, suggestion: str):
		"""Submit a suggestion."""
		if not interaction.guild:
			await interaction.response.send_message("Use this in a server.", ephemeral=True)
			return
		
		config = self._get_config(interaction.guild.id)
		
		if not config["channel_id"]:
			await interaction.response.send_message(
				"❌ Suggestion channel not configured. Ask an admin to use `/suggestion setchannel`",
				ephemeral=True
			)
			return
		
		channel = interaction.guild.get_channel(config["channel_id"])
		if not channel:
			await interaction.response.send_message("❌ Suggestion channel no longer exists.", ephemeral=True)
			return
		
		suggestion_id = config["next_id"]
		config["next_id"] += 1
		
		embed = self._create_suggestion_embed(suggestion_id, suggestion, interaction.user)
		
		try:
			msg = await channel.send(embed=embed)
			await msg.add_reaction("👍")
			await msg.add_reaction("👎")
		except discord.Forbidden:
			await interaction.response.send_message("❌ I can't post in the suggestion channel.", ephemeral=True)
			return
		
		# Store suggestion data
		config["suggestions"][str(suggestion_id)] = {
			"message_id": msg.id,
			"author_id": interaction.user.id,
			"content": suggestion[:2000],
			"status": "pending",
			"staff_note": None,
			"created_at": time.time()
		}
		self.bot.mark_dirty()
		
		await interaction.response.send_message(
			f"✅ Your suggestion has been submitted! (#{suggestion_id})\n"
			f"View it in {channel.mention}",
			ephemeral=True
		)
	
	suggestion_group = app_commands.Group(name="suggestion", description="Manage suggestions")
	
	@suggestion_group.command(name="setchannel", description="📋 Set the suggestion channel")
	@app_commands.describe(channel="Channel for suggestions")
	@app_commands.checks.has_permissions(administrator=True)
	async def suggestion_setchannel(self, interaction: discord.Interaction, channel: discord.TextChannel):
		"""Set the suggestion channel."""
		if not interaction.guild:
			await interaction.response.send_message("Use this in a server.", ephemeral=True)
			return
		
		config = self._get_config(interaction.guild.id)
		config["channel_id"] = channel.id
		self.bot.mark_dirty()
		
		await interaction.response.send_message(
			f"✅ Suggestion channel set to {channel.mention}\n"
			f"Users can now use `/suggest` to submit suggestions!"
		)
	
	@suggestion_group.command(name="approve", description="✅ Approve a suggestion")
	@app_commands.describe(suggestion_id="Suggestion ID to approve", note="Optional staff note")
	@app_commands.checks.has_permissions(manage_guild=True)
	async def suggestion_approve(self, interaction: discord.Interaction, suggestion_id: int, note: str = None):
		"""Approve a suggestion."""
		await self._update_suggestion_status(interaction, suggestion_id, "approved", note)
	
	@suggestion_group.command(name="deny", description="❌ Deny a suggestion")
	@app_commands.describe(suggestion_id="Suggestion ID to deny", note="Optional reason")
	@app_commands.checks.has_permissions(manage_guild=True)
	async def suggestion_deny(self, interaction: discord.Interaction, suggestion_id: int, note: str = None):
		"""Deny a suggestion."""
		await self._update_suggestion_status(interaction, suggestion_id, "denied", note)
	
	@suggestion_group.command(name="implement", description="🚀 Mark suggestion as implemented")
	@app_commands.describe(suggestion_id="Suggestion ID", note="Optional implementation note")
	@app_commands.checks.has_permissions(manage_guild=True)
	async def suggestion_implement(self, interaction: discord.Interaction, suggestion_id: int, note: str = None):
		"""Mark suggestion as implemented."""
		await self._update_suggestion_status(interaction, suggestion_id, "implemented", note)
	
	async def _update_suggestion_status(self, interaction: discord.Interaction, suggestion_id: int, status: str, note: str = None):
		"""Update a suggestion's status."""
		if not interaction.guild:
			await interaction.response.send_message("Use this in a server.", ephemeral=True)
			return
		
		config = self._get_config(interaction.guild.id)
		sid = str(suggestion_id)
		
		if sid not in config["suggestions"]:
			await interaction.response.send_message(f"❌ Suggestion #{suggestion_id} not found.", ephemeral=True)
			return
		
		data = config["suggestions"][sid]
		data["status"] = status
		if note:
			data["staff_note"] = note[:500]
		
		# Update the message
		channel = interaction.guild.get_channel(config["channel_id"])
		if channel:
			try:
				msg = await channel.fetch_message(data["message_id"])
				author = interaction.guild.get_member(data["author_id"]) or await self.bot.fetch_user(data["author_id"])
				embed = self._create_suggestion_embed(
					suggestion_id, data["content"], author, status, data.get("staff_note")
				)
				await msg.edit(embed=embed)
			except Exception:
				pass  # Original message may be deleted
		
		self.bot.mark_dirty()
		
		status_text = {"approved": "approved ✅", "denied": "denied ❌", "implemented": "marked as implemented 🚀"}
		await interaction.response.send_message(f"Suggestion #{suggestion_id} has been {status_text[status]}")
	
	@suggestion_group.command(name="info", description="ℹ️ View suggestion info")
	@app_commands.describe(suggestion_id="Suggestion ID")
	async def suggestion_info(self, interaction: discord.Interaction, suggestion_id: int):
		"""View detailed information about a suggestion."""
		if not interaction.guild:
			await interaction.response.send_message("Use this in a server.", ephemeral=True)
			return
		
		config = self._get_config(interaction.guild.id)
		sid = str(suggestion_id)
		
		if sid not in config["suggestions"]:
			await interaction.response.send_message(f"❌ Suggestion #{suggestion_id} not found.", ephemeral=True)
			return
		
		data = config["suggestions"][sid]
		author = interaction.guild.get_member(data["author_id"])
		author_text = author.mention if author else f"User ID: {data['author_id']}"
		
		# Get vote counts from message
		upvotes = 0
		downvotes = 0
		channel = interaction.guild.get_channel(config["channel_id"])
		if channel:
			try:
				msg = await channel.fetch_message(data["message_id"])
				for reaction in msg.reactions:
					if str(reaction.emoji) == "👍":
						upvotes = reaction.count - 1  # Subtract bot's reaction
					elif str(reaction.emoji) == "👎":
						downvotes = reaction.count - 1
			except Exception:
				pass  # Couldn't fetch vote counts
		
		embed = discord.Embed(
			title=f"Suggestion #{suggestion_id}",
			description=data["content"][:1000],
			color=Colors.SUGGESTION
		)
		embed.add_field(name="Author", value=author_text, inline=True)
		embed.add_field(name="Status", value=data["status"].title(), inline=True)
		embed.add_field(name="Votes", value=f"👍 {upvotes} | 👎 {downvotes}", inline=True)
		
		if data.get("staff_note"):
			embed.add_field(name="Staff Note", value=data["staff_note"], inline=False)
		
		await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
	await bot.add_cog(Suggestions(bot))
