"""
AFK Cog - Set AFK status and auto-respond when mentioned
"""
import time

import discord
from discord import app_commands
from discord.ext import commands

from core.helpers import Colors, logger


# ═══════════════════════════════════════════════════════════════════════════
#                               AFK COG
# ═══════════════════════════════════════════════════════════════════════════
class AFK(commands.Cog):
	"""Set AFK status and auto-respond when mentioned."""
	
	def __init__(self, bot: commands.Bot):
		self.bot = bot
	
	def _get_afk_data(self) -> dict:
		"""Get AFK data. Structure: {user_id: {"reason": str, "since": timestamp}}"""
		if "afk" not in self.bot.data:
			self.bot.data["afk"] = {}
		return self.bot.data["afk"]
	
	def _format_duration(self, seconds: float) -> str:
		"""Format duration into human readable string."""
		seconds = int(seconds)
		if seconds < 60:
			return f"{seconds}s"
		elif seconds < 3600:
			mins = seconds // 60
			return f"{mins}m"
		elif seconds < 86400:
			hours = seconds // 3600
			mins = (seconds % 3600) // 60
			return f"{hours}h {mins}m"
		else:
			days = seconds // 86400
			hours = (seconds % 86400) // 3600
			return f"{days}d {hours}h"
	
	# ─────────────────────────────────────────────────────────────────────────
	#                            COMMANDS
	# ─────────────────────────────────────────────────────────────────────────
	
	@app_commands.command(name="afk", description="💤 Set your AFK status")
	@app_commands.describe(reason="Reason for being AFK (optional)")
	async def afk(self, interaction: discord.Interaction, reason: str = "AFK"):
		"""Set yourself as AFK."""
		afk_data = self._get_afk_data()
		uid = str(interaction.user.id)
		
		afk_data[uid] = {
			"reason": reason[:200],  # Limit reason length
			"since": time.time()
		}
		self.bot.mark_dirty()
		
		embed = discord.Embed(
			title="💤 AFK Set",
			description=f"I've set your AFK status.\n**Reason:** {reason}",
			color=Colors.AFK
		)
		embed.set_footer(text="You'll be removed from AFK when you send a message")
		
		await interaction.response.send_message(embed=embed)
		
		# Try to add [AFK] to nickname
		if interaction.guild:
			member = interaction.guild.get_member(interaction.user.id)
			if member:
				try:
					if not member.display_name.startswith("[AFK]"):
						new_nick = f"[AFK] {member.display_name}"[:32]
						await member.edit(nick=new_nick, reason="AFK status")
				except discord.Forbidden:
					pass  # Can't change nickname
	
	# ─────────────────────────────────────────────────────────────────────────
	#                         EVENT LISTENERS
	# ─────────────────────────────────────────────────────────────────────────
	
	@commands.Cog.listener()
	async def on_message(self, message: discord.Message):
		"""Handle AFK returns and mentions."""
		if message.author.bot:
			return
		
		if not message.guild:
			return
		
		afk_data = self._get_afk_data()
		uid = str(message.author.id)
		
		# Check if user was AFK and is now returning
		if uid in afk_data:
			duration = time.time() - afk_data[uid]["since"]
			del afk_data[uid]
			self.bot.mark_dirty()
			
			# Remove [AFK] from nickname
			try:
				if message.author.display_name.startswith("[AFK]"):
					new_nick = message.author.display_name[6:].strip() or None
					await message.author.edit(nick=new_nick, reason="Returned from AFK")
			except discord.Forbidden:
				pass
			
			try:
				await message.reply(
					f"👋 Welcome back! You were AFK for **{self._format_duration(duration)}**.",
					delete_after=5,
					mention_author=False
				)
			except discord.Forbidden:
				pass
			
			return
		
		# Check if message mentions any AFK users
		if message.mentions:
			afk_responses = []
			for mentioned in message.mentions:
				mentioned_id = str(mentioned.id)
				if mentioned_id in afk_data:
					data = afk_data[mentioned_id]
					duration = self._format_duration(time.time() - data["since"])
					afk_responses.append(
						f"💤 **{mentioned.display_name}** is AFK: {data['reason']} ({duration})"
					)
			
			if afk_responses:
				try:
					await message.reply(
						"\n".join(afk_responses[:3]),  # Max 3 AFK notifications
						delete_after=10,
						mention_author=False
					)
				except discord.Forbidden:
					pass


async def setup(bot: commands.Bot):
	await bot.add_cog(AFK(bot))
