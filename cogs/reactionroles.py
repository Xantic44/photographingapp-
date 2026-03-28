"""
Reaction Roles Cog - Self-assignable roles via reactions
"""
import discord
from discord import app_commands
from discord.ext import commands

from core.helpers import Colors, logger


# ═══════════════════════════════════════════════════════════════════════════
#                            REACTION ROLES COG
# ═══════════════════════════════════════════════════════════════════════════
class ReactionRoles(commands.Cog):
	"""Self-assign roles by reacting to messages."""
	
	def __init__(self, bot: commands.Bot):
		self.bot = bot
	
	def _get_reaction_roles(self, guild_id: int) -> dict:
		"""Get reaction roles config for a guild. Structure: {message_id: {emoji: role_id}}"""
		gid = str(guild_id)
		if "reaction_roles" not in self.bot.data:
			self.bot.data["reaction_roles"] = {}
		if gid not in self.bot.data["reaction_roles"]:
			self.bot.data["reaction_roles"][gid] = {}
		return self.bot.data["reaction_roles"][gid]
	
	# ─────────────────────────────────────────────────────────────────────────
	#                            COMMANDS
	# ─────────────────────────────────────────────────────────────────────────
	
	rr_group = app_commands.Group(name="reactionrole", description="Set up reaction roles")
	
	@rr_group.command(name="create", description="🎭 Create a reaction role panel")
	@app_commands.describe(
		title="Title for the embed",
		description="Description text (use \\n for new lines)"
	)
	@app_commands.checks.has_permissions(administrator=True)
	async def rr_create(self, interaction: discord.Interaction, title: str, description: str = "React to get roles!"):
		"""Create a new reaction role panel embed."""
		if not interaction.guild:
			await interaction.response.send_message("Use this in a server.", ephemeral=True)
			return
		
		# Replace literal \n with actual newlines
		description = description.replace("\\n", "\n")
		
		embed = discord.Embed(
			title=f"🎭 {title}",
			description=description,
			color=Colors.REACTION_ROLES
		)
		embed.set_footer(text="React to assign yourself a role!")
		
		await interaction.response.send_message("✅ Panel created! Now add reactions with `/reactionrole add`", ephemeral=True)
		msg = await interaction.channel.send(embed=embed)
		
		# Initialize storage for this message
		rr_data = self._get_reaction_roles(interaction.guild.id)
		rr_data[str(msg.id)] = {}
		self.bot.mark_dirty()
	
	@rr_group.command(name="add", description="➕ Add a reaction role to a message")
	@app_commands.describe(
		message_id="ID of the reaction role message",
		emoji="Emoji to react with",
		role="Role to assign when reacted"
	)
	@app_commands.checks.has_permissions(administrator=True)
	async def rr_add(self, interaction: discord.Interaction, message_id: str, emoji: str, role: discord.Role):
		"""Add a reaction role to an existing message."""
		if not interaction.guild:
			await interaction.response.send_message("Use this in a server.", ephemeral=True)
			return
		
		# Validate role
		if role >= interaction.guild.me.top_role:
			await interaction.response.send_message("❌ That role is higher than my top role.", ephemeral=True)
			return
		
		if role.managed:
			await interaction.response.send_message("❌ Can't use managed roles (bot/integration).", ephemeral=True)
			return
		
		# Try to find the message
		try:
			msg = await interaction.channel.fetch_message(int(message_id))
		except (ValueError, discord.NotFound):
			await interaction.response.send_message("❌ Message not found in this channel.", ephemeral=True)
			return
		except discord.Forbidden:
			await interaction.response.send_message("❌ I don't have permission to read that message.", ephemeral=True)
			return
		
		# Add reaction to message
		try:
			await msg.add_reaction(emoji)
		except discord.HTTPException:
			await interaction.response.send_message("❌ Invalid emoji or I can't use it.", ephemeral=True)
			return
		
		# Store in data
		rr_data = self._get_reaction_roles(interaction.guild.id)
		if message_id not in rr_data:
			rr_data[message_id] = {}
		
		# Convert custom emoji to string format
		emoji_key = str(emoji)
		rr_data[message_id][emoji_key] = role.id
		self.bot.mark_dirty()
		
		await interaction.response.send_message(
			f"✅ Added: {emoji} → {role.mention}\n"
			f"Users can now react with {emoji} to get the role!",
			allowed_mentions=discord.AllowedMentions.none()
		)
	
	@rr_group.command(name="remove", description="➖ Remove a reaction role")
	@app_commands.describe(
		message_id="ID of the reaction role message",
		emoji="Emoji to remove"
	)
	@app_commands.checks.has_permissions(administrator=True)
	async def rr_remove(self, interaction: discord.Interaction, message_id: str, emoji: str):
		"""Remove a reaction role from a message."""
		if not interaction.guild:
			await interaction.response.send_message("Use this in a server.", ephemeral=True)
			return
		
		rr_data = self._get_reaction_roles(interaction.guild.id)
		
		if message_id not in rr_data:
			await interaction.response.send_message("❌ No reaction roles configured for that message.", ephemeral=True)
			return
		
		emoji_key = str(emoji)
		if emoji_key not in rr_data[message_id]:
			await interaction.response.send_message("❌ That emoji isn't configured for that message.", ephemeral=True)
			return
		
		del rr_data[message_id][emoji_key]
		
		# Clean up empty message entries
		if not rr_data[message_id]:
			del rr_data[message_id]
		
		self.bot.mark_dirty()
		
		# Try to remove the reaction from the message
		try:
			msg = await interaction.channel.fetch_message(int(message_id))
			await msg.clear_reaction(emoji)
		except Exception:
			pass  # Message may not exist anymore
		
		await interaction.response.send_message(f"✅ Removed reaction role for {emoji}.")
	
	@rr_group.command(name="list", description="📋 List all reaction roles")
	async def rr_list(self, interaction: discord.Interaction):
		"""List all reaction role configurations."""
		if not interaction.guild:
			await interaction.response.send_message("Use this in a server.", ephemeral=True)
			return
		
		rr_data = self._get_reaction_roles(interaction.guild.id)
		
		if not rr_data:
			await interaction.response.send_message(
				"📋 **No reaction roles configured!**\n"
				"Use `/reactionrole create` to make a panel.",
				ephemeral=True
			)
			return
		
		embed = discord.Embed(
			title="🎭 Reaction Roles",
			color=Colors.REACTION_ROLES
		)
		
		for msg_id, emojis in rr_data.items():
			if not emojis:
				continue
			
			lines = []
			for emoji_str, role_id in emojis.items():
				role = interaction.guild.get_role(role_id)
				role_text = role.mention if role else f"*Deleted ({role_id})*"
				lines.append(f"{emoji_str} → {role_text}")
			
			if lines:
				embed.add_field(
					name=f"Message: {msg_id}",
					value="\n".join(lines),
					inline=False
				)
		
		if not embed.fields:
			await interaction.response.send_message("📋 No reaction roles configured!", ephemeral=True)
			return
		
		await interaction.response.send_message(embed=embed, allowed_mentions=discord.AllowedMentions.none())
	
	@rr_group.command(name="clear", description="🗑️ Remove all reaction roles from a message")
	@app_commands.describe(message_id="ID of the message to clear")
	@app_commands.checks.has_permissions(administrator=True)
	async def rr_clear(self, interaction: discord.Interaction, message_id: str):
		"""Clear all reaction roles from a message."""
		if not interaction.guild:
			await interaction.response.send_message("Use this in a server.", ephemeral=True)
			return
		
		rr_data = self._get_reaction_roles(interaction.guild.id)
		
		if message_id not in rr_data:
			await interaction.response.send_message("❌ No reaction roles on that message.", ephemeral=True)
			return
		
		count = len(rr_data[message_id])
		del rr_data[message_id]
		self.bot.mark_dirty()
		
		# Try to clear all reactions
		try:
			msg = await interaction.channel.fetch_message(int(message_id))
			await msg.clear_reactions()
		except Exception:
			pass  # Message may not exist anymore
		
		await interaction.response.send_message(f"✅ Cleared {count} reaction role(s) from that message.")
	
	# ─────────────────────────────────────────────────────────────────────────
	#                         EVENT LISTENERS
	# ─────────────────────────────────────────────────────────────────────────
	
	@commands.Cog.listener()
	async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
		"""Handle reaction adds for role assignment."""
		if payload.user_id == self.bot.user.id:
			return
		
		if not payload.guild_id:
			return
		
		guild = self.bot.get_guild(payload.guild_id)
		if not guild:
			return
		
		member = guild.get_member(payload.user_id)
		if not member or member.bot:
			return
		
		rr_data = self._get_reaction_roles(payload.guild_id)
		msg_id = str(payload.message_id)
		
		if msg_id not in rr_data:
			return
		
		emoji_key = str(payload.emoji)
		if emoji_key not in rr_data[msg_id]:
			return
		
		role_id = rr_data[msg_id][emoji_key]
		role = guild.get_role(role_id)
		
		if not role:
			return
		
		if role not in member.roles:
			try:
				await member.add_roles(role, reason="Reaction role")
				logger.info(f"Added role {role.name} to {member} via reaction roles")
			except discord.Forbidden:
				logger.warning(f"Missing permissions to add role {role.name} to {member}")
	
	@commands.Cog.listener()
	async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
		"""Handle reaction removes for role removal."""
		if not payload.guild_id:
			return
		
		guild = self.bot.get_guild(payload.guild_id)
		if not guild:
			return
		
		member = guild.get_member(payload.user_id)
		if not member or member.bot:
			return
		
		rr_data = self._get_reaction_roles(payload.guild_id)
		msg_id = str(payload.message_id)
		
		if msg_id not in rr_data:
			return
		
		emoji_key = str(payload.emoji)
		if emoji_key not in rr_data[msg_id]:
			return
		
		role_id = rr_data[msg_id][emoji_key]
		role = guild.get_role(role_id)
		
		if not role:
			return
		
		if role in member.roles:
			try:
				await member.remove_roles(role, reason="Reaction role removed")
				logger.info(f"Removed role {role.name} from {member} via reaction roles")
			except discord.Forbidden:
				logger.warning(f"Missing permissions to remove role {role.name} from {member}")


async def setup(bot: commands.Bot):
	await bot.add_cog(ReactionRoles(bot))
