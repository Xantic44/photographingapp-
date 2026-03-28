"""
Starboard Cog - Feature popular messages with star reactions
"""
import discord
from discord import app_commands
from discord.ext import commands

from core.helpers import Colors, logger


# ═══════════════════════════════════════════════════════════════════════════
#                              STARBOARD COG
# ═══════════════════════════════════════════════════════════════════════════
class Starboard(commands.Cog):
	"""Feature popular messages on a starboard channel."""
	
	def __init__(self, bot: commands.Bot):
		self.bot = bot
	
	def _get_config(self, guild_id: int) -> dict:
		"""Get starboard config for a guild."""
		gid = str(guild_id)
		if "starboard" not in self.bot.data:
			self.bot.data["starboard"] = {}
		if gid not in self.bot.data["starboard"]:
			self.bot.data["starboard"][gid] = {
				"channel_id": None,
				"threshold": 3,
				"emoji": "⭐",
				"self_star": False,  # Allow self-starring
				"starred_messages": {}  # original_msg_id: starboard_msg_id
			}
		return self.bot.data["starboard"][gid]
	
	def _get_star_emoji(self, count: int) -> str:
		"""Get emoji based on star count."""
		if count >= 20:
			return "🌟"
		elif count >= 10:
			return "✨"
		elif count >= 5:
			return "💫"
		return "⭐"
	
	# ─────────────────────────────────────────────────────────────────────────
	#                            COMMANDS
	# ─────────────────────────────────────────────────────────────────────────
	
	starboard_group = app_commands.Group(name="starboard", description="Configure the starboard")
	
	@starboard_group.command(name="setup", description="⭐ Set up the starboard channel")
	@app_commands.describe(channel="Channel to post starred messages")
	@app_commands.checks.has_permissions(administrator=True)
	async def starboard_setup(self, interaction: discord.Interaction, channel: discord.TextChannel):
		"""Set up the starboard channel."""
		if not interaction.guild:
			await interaction.response.send_message("Use this in a server.", ephemeral=True)
			return
		
		if not channel.permissions_for(interaction.guild.me).send_messages:
			await interaction.response.send_message("❌ I can't send messages in that channel.", ephemeral=True)
			return
		
		config = self._get_config(interaction.guild.id)
		config["channel_id"] = channel.id
		self.bot.mark_dirty()
		
		await interaction.response.send_message(
			f"✅ **Starboard configured!**\n"
			f"📌 Channel: {channel.mention}\n"
			f"⭐ Threshold: **{config['threshold']}** stars\n"
			f"React with {config['emoji']} to star messages!"
		)
	
	@starboard_group.command(name="threshold", description="🔢 Set minimum stars required")
	@app_commands.describe(count="Number of stars required (1-25)")
	@app_commands.checks.has_permissions(administrator=True)
	async def starboard_threshold(self, interaction: discord.Interaction, count: int):
		"""Set the star threshold."""
		if not interaction.guild:
			await interaction.response.send_message("Use this in a server.", ephemeral=True)
			return
		
		if count < 1 or count > 25:
			await interaction.response.send_message("❌ Threshold must be between 1 and 25.", ephemeral=True)
			return
		
		config = self._get_config(interaction.guild.id)
		config["threshold"] = count
		self.bot.mark_dirty()
		
		await interaction.response.send_message(f"✅ Starboard threshold set to **{count}** stars.")
	
	@starboard_group.command(name="emoji", description="✨ Change the star emoji")
	@app_commands.describe(emoji="Emoji to use for starring")
	@app_commands.checks.has_permissions(administrator=True)
	async def starboard_emoji(self, interaction: discord.Interaction, emoji: str):
		"""Change the starboard emoji."""
		if not interaction.guild:
			await interaction.response.send_message("Use this in a server.", ephemeral=True)
			return
		
		config = self._get_config(interaction.guild.id)
		config["emoji"] = emoji
		self.bot.mark_dirty()
		
		await interaction.response.send_message(f"✅ Starboard emoji changed to {emoji}")
	
	@starboard_group.command(name="selfstar", description="🙋 Toggle self-starring")
	@app_commands.describe(allow="Allow users to star their own messages?")
	@app_commands.checks.has_permissions(administrator=True)
	async def starboard_selfstar(self, interaction: discord.Interaction, allow: bool):
		"""Toggle self-starring."""
		if not interaction.guild:
			await interaction.response.send_message("Use this in a server.", ephemeral=True)
			return
		
		config = self._get_config(interaction.guild.id)
		config["self_star"] = allow
		self.bot.mark_dirty()
		
		status = "**enabled**" if allow else "**disabled**"
		await interaction.response.send_message(f"✅ Self-starring is now {status}.")
	
	@starboard_group.command(name="settings", description="⚙️ View starboard settings")
	async def starboard_settings(self, interaction: discord.Interaction):
		"""View current starboard settings."""
		if not interaction.guild:
			await interaction.response.send_message("Use this in a server.", ephemeral=True)
			return
		
		config = self._get_config(interaction.guild.id)
		
		channel = interaction.guild.get_channel(config["channel_id"]) if config["channel_id"] else None
		channel_text = channel.mention if channel else "*Not configured*"
		
		embed = discord.Embed(
			title="⭐ Starboard Settings",
			color=Colors.STARBOARD
		)
		embed.add_field(name="📌 Channel", value=channel_text, inline=True)
		embed.add_field(name="🔢 Threshold", value=f"**{config['threshold']}** stars", inline=True)
		embed.add_field(name="✨ Emoji", value=config["emoji"], inline=True)
		embed.add_field(name="🙋 Self-star", value="Yes" if config["self_star"] else "No", inline=True)
		embed.add_field(name="📊 Starred Messages", value=str(len(config.get("starred_messages", {}))), inline=True)
		
		await interaction.response.send_message(embed=embed)
	
	@starboard_group.command(name="disable", description="❌ Disable the starboard")
	@app_commands.checks.has_permissions(administrator=True)
	async def starboard_disable(self, interaction: discord.Interaction):
		"""Disable the starboard."""
		if not interaction.guild:
			await interaction.response.send_message("Use this in a server.", ephemeral=True)
			return
		
		config = self._get_config(interaction.guild.id)
		config["channel_id"] = None
		self.bot.mark_dirty()
		
		await interaction.response.send_message("✅ Starboard disabled.")
	
	# ─────────────────────────────────────────────────────────────────────────
	#                         EVENT LISTENERS
	# ─────────────────────────────────────────────────────────────────────────
	
	async def _update_starboard(self, payload: discord.RawReactionActionEvent, added: bool):
		"""Handle starboard updates when reactions change."""
		if not payload.guild_id:
			return
		
		guild = self.bot.get_guild(payload.guild_id)
		if not guild:
			return
		
		config = self._get_config(payload.guild_id)
		
		# Check if starboard is configured
		if not config["channel_id"]:
			return
		
		# Check if it's the star emoji
		if str(payload.emoji) != config["emoji"]:
			return
		
		starboard_channel = guild.get_channel(config["channel_id"])
		if not starboard_channel:
			return
		
		# Don't star messages in the starboard channel
		if payload.channel_id == config["channel_id"]:
			return
		
		# Get the original message
		channel = guild.get_channel(payload.channel_id)
		if not channel:
			return
		
		try:
			message = await channel.fetch_message(payload.message_id)
		except discord.NotFound:
			return
		except discord.Forbidden:
			return
		
		# Count valid star reactions
		star_reaction = None
		for reaction in message.reactions:
			if str(reaction.emoji) == config["emoji"]:
				star_reaction = reaction
				break
		
		if not star_reaction:
			star_count = 0
		else:
			star_count = star_reaction.count
			
			# Subtract self-stars if not allowed
			if not config["self_star"]:
				try:
					users = [user async for user in star_reaction.users()]
					if message.author in users:
						star_count -= 1
				except Exception:
					pass  # Failed to fetch reaction users
		
		msg_id = str(payload.message_id)
		starred_messages = config.get("starred_messages", {})
		
		# Check if already on starboard
		if msg_id in starred_messages:
			# Update existing starboard message
			try:
				sb_msg = await starboard_channel.fetch_message(starred_messages[msg_id])
				
				if star_count < config["threshold"]:
					# Remove from starboard
					await sb_msg.delete()
					del starred_messages[msg_id]
					self.bot.mark_dirty()
				else:
					# Update star count
					emoji = self._get_star_emoji(star_count)
					new_content = f"{emoji} **{star_count}** | {channel.mention}"
					await sb_msg.edit(content=new_content)
			except discord.NotFound:
				# Starboard message was deleted, remove from tracking
				del starred_messages[msg_id]
				self.bot.mark_dirty()
			except discord.Forbidden:
				pass
		else:
			# Check if meets threshold to add
			if star_count >= config["threshold"]:
				# Create starboard embed
				embed = discord.Embed(
					description=message.content[:2000] if message.content else None,
					color=Colors.STARBOARD,
					timestamp=message.created_at
				)
				embed.set_author(
					name=message.author.display_name,
					icon_url=message.author.display_avatar.url
				)
				
				# Add first image attachment
				if message.attachments:
					for att in message.attachments:
						if att.content_type and att.content_type.startswith("image"):
							embed.set_image(url=att.url)
							break
				
				# Add video/other attachment info
				if message.attachments and not embed.image:
					att_text = "\n".join(f"📎 [{a.filename}]({a.url})" for a in message.attachments[:3])
					embed.add_field(name="Attachments", value=att_text, inline=False)
				
				embed.add_field(name="📌 Source", value=f"[Jump to message]({message.jump_url})", inline=False)
				
				emoji = self._get_star_emoji(star_count)
				content = f"{emoji} **{star_count}** | {channel.mention}"
				
				try:
					sb_msg = await starboard_channel.send(content=content, embed=embed)
					starred_messages[msg_id] = sb_msg.id
					config["starred_messages"] = starred_messages
					self.bot.mark_dirty()
					logger.info(f"Added message {msg_id} to starboard with {star_count} stars")
				except discord.Forbidden:
					logger.warning(f"Missing permissions to post to starboard in {guild.name}")
	
	@commands.Cog.listener()
	async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
		"""Handle star reactions being added."""
		if payload.user_id == self.bot.user.id:
			return
		await self._update_starboard(payload, added=True)
	
	@commands.Cog.listener()
	async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
		"""Handle star reactions being removed."""
		await self._update_starboard(payload, added=False)


async def setup(bot: commands.Bot):
	await bot.add_cog(Starboard(bot))
