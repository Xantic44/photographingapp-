"""
Welcome cog - Welcome message system.
"""
import discord
from discord import app_commands
from discord.ext import commands

from core.helpers import save_data, mark_dirty, Colors


class Welcome(commands.Cog):
	"""Welcome message system."""

	def __init__(self, bot: commands.Bot):
		self.bot = bot

	@commands.Cog.listener()
	async def on_member_join(self, member: discord.Member):
		"""Send welcome message when a member joins."""
		config = self.bot.data["welcome"].get(str(member.guild.id), {})
		channel_id = config.get("channel_id")
		if not channel_id:
			return

		channel = member.guild.get_channel(int(channel_id))
		if not isinstance(channel, discord.TextChannel):
			return

		# Create beautiful welcome embed
		custom_message = config.get("message", "Welcome to our community! We're glad to have you here~")
		text = custom_message.replace("{mention}", member.mention).replace("{server}", member.guild.name).replace("{user}", member.name)
		
		embed = discord.Embed(
			title="🌟 Welcome to the Server! 🌟",
			description=f"Hey {member.mention}!\n\n{text}",
			color=Colors.SUCCESS
		)
		embed.set_thumbnail(url=member.display_avatar.url)
		embed.add_field(name="👥 Member #", value=f"**{member.guild.member_count}**", inline=True)
		embed.add_field(name="📝 Account Age", value=f"<t:{int(member.created_at.timestamp())}:R>", inline=True)
		embed.set_footer(text=f"Joined {member.guild.name} • Have fun! 💕")
		if member.guild.icon:
			embed.set_author(name=member.guild.name, icon_url=member.guild.icon.url)
		
		await channel.send(embed=embed)

	@app_commands.command(name="setwelcome", description="👋 Set the welcome channel")
	@app_commands.checks.has_permissions(manage_guild=True)
	@app_commands.describe(channel="Channel where welcome messages will be sent")
	async def setwelcome(self, interaction: discord.Interaction, channel: discord.TextChannel):
		if not interaction.guild:
			await interaction.response.send_message("Use this in a server.", ephemeral=True)
			return

		config = self.bot.data["welcome"].setdefault(str(interaction.guild.id), {})
		config["channel_id"] = channel.id
		mark_dirty()
		
		embed = discord.Embed(
			title="✅ Welcome Channel Set!",
			description=f"New members will be greeted in {channel.mention}",
			color=Colors.SUCCESS
		)
		embed.set_footer(text="Use /setwelcomemessage to customize the greeting!")
		await interaction.response.send_message(embed=embed)

	@app_commands.command(name="setwelcomemessage", description="✍️ Set custom welcome text")
	@app_commands.checks.has_permissions(manage_guild=True)
	@app_commands.describe(message="Welcome message ({mention}, {user}, {server} placeholders)")
	async def setwelcomemessage(self, interaction: discord.Interaction, message: str):
		if not interaction.guild:
			await interaction.response.send_message("Use this in a server.", ephemeral=True)
			return

		config = self.bot.data["welcome"].setdefault(str(interaction.guild.id), {})
		config["message"] = message
		mark_dirty()
		
		# Preview
		preview = message.replace("{mention}", interaction.user.mention).replace("{server}", interaction.guild.name).replace("{user}", interaction.user.name)
		
		embed = discord.Embed(
			title="✅ Welcome Message Updated!",
			color=Colors.SUCCESS
		)
		embed.add_field(name="📝 Template", value=f"```{message}```", inline=False)
		embed.add_field(name="👁️ Preview", value=preview, inline=False)
		embed.set_footer(text="Placeholders: {mention}, {user}, {server}")
		await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
	await bot.add_cog(Welcome(bot))
