"""
Profile cog - User profile, userinfo, and status commands.
"""
import discord
from discord import app_commands
from discord.ext import commands

from core.helpers import (
    mark_dirty,
    ensure_user_entry,
    save_data,
    xp_required_for_level,
    create_progress_bar,
    format_activity_lines,
    Colors,
)


# Status presets with emojis
STATUS_PRESETS = {
	"chilling": "😌 Chilling",
	"gaming": "🎮 Gaming",
	"studying": "📚 Studying",
	"brb": "🔄 Be Right Back",
	"watching": "👀 Kollar på grejer",
	"working": "💼 Working",
	"listening": "🎧 Listening to Music",
	"coding": "💻 Coding",
	"eating": "🍕 Eating",
	"sleeping": "😴 Sleeping",
}


class Profile(commands.Cog):
	"""User profile and status commands."""

	def __init__(self, bot: commands.Bot):
		self.bot = bot

	async def format_userinfo_embed(self, member: discord.Member) -> discord.Embed:
		"""Create a polished, clean userinfo embed."""
		guild = member.guild

		# --- Status with emoji ---
		status_emojis = {
			discord.Status.online: "🟢",
			discord.Status.idle: "🟡",
			discord.Status.dnd: "🔴",
			discord.Status.offline: "⚫",
			discord.Status.invisible: "⚫",
		}
		status_emoji = status_emojis.get(member.status, "⚪")
		status_name = str(member.status).replace("dnd", "Do Not Disturb").replace("_", " ").title()
		status_text = f"{status_emoji} {status_name}"

		# --- Platform detection ---
		platforms = []
		if str(member.desktop_status) != "offline":
			platforms.append("🖥️ Desktop")
		if str(member.mobile_status) != "offline":
			platforms.append("📱 Mobile")
		if str(member.web_status) != "offline":
			platforms.append("🌐 Web")
		platform_text = ", ".join(platforms) if platforms else "Unknown"

		# --- Activity ---
		activity_text = format_activity_lines(member)

		# --- Voice ---
		if member.voice and member.voice.channel:
			voice_text = f"🔊 {member.voice.channel.mention}"
			if member.voice.self_mute:
				voice_text += " (Muted)"
			if member.voice.self_deaf:
				voice_text += " (Deafened)"
		else:
			voice_text = "Not in voice"

		# --- Roles (compact) ---
		roles = [role.mention for role in reversed(member.roles) if role.name != "@everyone"]
		if len(roles) > 10:
			role_text = ", ".join(roles[:10]) + f" (+{len(roles) - 10} more)"
		elif roles:
			role_text = ", ".join(roles)
		else:
			role_text = "None"

		# --- Join position ---
		if member.joined_at:
			joined_members = sorted([m for m in guild.members if m.joined_at], key=lambda m: m.joined_at)
			join_position = next((i + 1 for i, m in enumerate(joined_members) if m.id == member.id), "?")
		else:
			join_position = "?"

		# --- Key permissions ---
		perms = member.guild_permissions
		perm_list = []
		if perms.administrator:
			perm_list.append("👑 Admin")
		else:
			if perms.manage_guild:
				perm_list.append("⚙️ Manage Server")
			if perms.manage_messages:
				perm_list.append("💬 Manage Messages")
			if perms.kick_members:
				perm_list.append("👢 Kick")
			if perms.ban_members:
				perm_list.append("🔨 Ban")
		perm_text = ", ".join(perm_list) if perm_list else "Standard"

		# --- XP & Economy ---
		xp_entry = ensure_user_entry(self.bot.data["xp"], guild.id, member.id, {"xp": 0, "level": 1, "total_xp": 0})
		econ_entry = ensure_user_entry(self.bot.data["economy"], guild.id, member.id, {"funPoints": 100, "last_daily": 0, "last_work": 0})
		if "funPoints" not in econ_entry:
			econ_entry["funPoints"] = econ_entry.pop("coins", 100)
		next_xp = xp_required_for_level(xp_entry["level"])
		progress_bar = create_progress_bar(xp_entry["xp"], next_xp)

		# --- Fetch full user for banner ---
		try:
			full_user = await self.bot.fetch_user(member.id)
		except discord.HTTPException:
			full_user = member

		# --- Badges ---
		badge_emojis = {
			"staff": "👨‍💼",
			"partner": "🤝",
			"hypesquad": "🏠",
			"bug_hunter": "🐛",
			"bug_hunter_level_2": "🐛🐛",
			"hypesquad_bravery": "🟣",
			"hypesquad_brilliance": "🟠",
			"hypesquad_balance": "🟢",
			"early_supporter": "💎",
			"verified_bot_developer": "🤖",
			"active_developer": "🛠️",
			"discord_certified_moderator": "🛡️",
		}
		badges = []
		for flag_name, enabled in member.public_flags:
			if enabled:
				emoji = badge_emojis.get(flag_name, "✨")
				badges.append(emoji)
		badge_text = " ".join(badges[:8]) if badges else "None"

		# --- Build embed ---
		embed = discord.Embed(color=member.color if member.color != discord.Color.default() else discord.Color.blurple())
		embed.set_author(name=f"{member}", icon_url=member.display_avatar.url)
		embed.set_thumbnail(url=member.display_avatar.url)

		# Main info section
		embed.add_field(name="📋 General", value=(
			f"**ID:** `{member.id}`\n"
			f"**Nickname:** {member.nick or 'None'}\n"
			f"**Bot:** {'Yes' if member.bot else 'No'}"
		), inline=True)

		embed.add_field(name="📅 Dates", value=(
			f"**Created:** <t:{int(member.created_at.timestamp())}:R>\n"
			f"**Joined:** <t:{int(member.joined_at.timestamp())}:R>\n"
			f"**Position:** #{join_position}"
		) if member.joined_at else "Unknown", inline=True)

		embed.add_field(name="🎭 Status", value=(
			f"{status_text}\n"
			f"**Platform:** {platform_text}"
		), inline=True)

		# Activity
		if activity_text != "None":
			embed.add_field(name="🎯 Activity", value=activity_text[:1024], inline=False)

		# Custom voice status from profile
		profile_entry = self.bot.data.get("profiles", {}).get(str(guild.id), {}).get(str(member.id), {})
		voice_status = profile_entry.get("voice_status")
		custom_bio = profile_entry.get("bio", "Not set")
		custom_location = profile_entry.get("location", "Not set")

		# Voice section with custom status
		if voice_text != "Not in voice":
			voice_display = voice_text
			if voice_status:
				voice_display += f"\n**Doing:** {voice_status}"
			embed.add_field(name="🔊 Voice", value=voice_display, inline=True)
		elif voice_status:
			# Show status even when not in voice
			embed.add_field(name="💭 Status", value=voice_status, inline=True)

		# Profile info section
		if custom_bio != "Not set" or custom_location != "Not set":
			profile_lines = []
			if custom_location != "Not set":
				profile_lines.append(f"📍 {custom_location}")
			if custom_bio != "Not set":
				profile_lines.append(f"✏️ {custom_bio}")
			embed.add_field(name="📝 Profile", value="\n".join(profile_lines), inline=True)

		# Progression
		embed.add_field(name="📈 Progression", value=(
			f"**Level {xp_entry['level']}** {progress_bar} `{xp_entry['xp']}/{next_xp} XP`\n"
			f"**Total XP:** {xp_entry['total_xp']:,} | **funPoints:** {econ_entry['funPoints']:,}"
		), inline=False)

		# Roles
		embed.add_field(name=f"🏷️ Roles [{len(roles)}]", value=role_text[:1024], inline=False)

		# Permissions & Badges
		embed.add_field(name="🔐 Permissions", value=perm_text, inline=True)
		embed.add_field(name="🎖️ Badges", value=badge_text, inline=True)

		# Boosting
		if member.premium_since:
			embed.add_field(name="💎 Boosting", value=f"Since <t:{int(member.premium_since.timestamp())}:R>", inline=True)

		# Links
		links = [f"[Avatar]({member.display_avatar.url})"]
		if getattr(full_user, "banner", None):
			links.append(f"[Banner]({full_user.banner.url})")
		embed.add_field(name="🔗 Links", value=" • ".join(links), inline=False)

		embed.set_footer(text=f"Top Role: {member.top_role.name}")
		return embed

	async def generate_userdebug_text(self, member: discord.Member, guild: discord.Guild) -> str:
		"""Generate comprehensive debug text for a user."""
		try:
			fetched_user = await self.bot.fetch_user(member.id)
		except discord.HTTPException:
			fetched_user = member

		# Build debug sections
		lines = []
		
		# Identity
		lines.extend([
			"=== IDENTITY ===",
			f"user_id={member.id}",
			f"username={member.name}",
			f"discriminator={member.discriminator}",
			f"display_name={member.display_name}",
			f"global_name={member.global_name}",
			f"nick={member.nick}",
			f"bot={member.bot}",
			f"system={member.system}",
			f"created_at={member.created_at}",
		])

		# Status
		lines.extend([
			"",
			"=== PRESENCE ===",
			f"status={member.status}",
			f"desktop_status={member.desktop_status}",
			f"mobile_status={member.mobile_status}",
			f"web_status={member.web_status}",
			f"activity_count={len(member.activities)}",
		])

		# Activities
		for idx, act in enumerate(member.activities, 1):
			lines.append(f"  activity_{idx}: type={act.type}, name={getattr(act, 'name', 'N/A')}")

		# Voice
		lines.extend(["", "=== VOICE ==="])
		if member.voice:
			v = member.voice
			lines.extend([
				f"channel={v.channel}",
				f"self_mute={v.self_mute}",
				f"self_deaf={v.self_deaf}",
			])
		else:
			lines.append("in_voice=False")

		# Roles
		lines.extend(["", "=== ROLES ===", f"role_count={len(member.roles)}"])
		for role in member.roles[:15]:
			lines.append(f"  {role.name} (id={role.id})")
		if len(member.roles) > 15:
			lines.append(f"  ... and {len(member.roles) - 15} more")

		# Bot data
		lines.extend([
			"",
			"=== BOT DATA ===",
			f"xp={self.bot.data.get('xp', {}).get(str(guild.id), {}).get(str(member.id), {})}",
			f"economy={self.bot.data.get('economy', {}).get(str(guild.id), {}).get(str(member.id), {})}",
			f"profile={self.bot.data.get('profiles', {}).get(str(guild.id), {}).get(str(member.id), {})}",
		])

		return "\n".join(lines)

	# ─────────────────────────────────────────────────────────────────────────
	# Prefix commands
	# ─────────────────────────────────────────────────────────────────────────
	@commands.command()
	async def userinfo(self, ctx, member: discord.Member | None = None):
		member = member or ctx.author
		embed = await self.format_userinfo_embed(member)
		await ctx.send(embed=embed)

	@commands.command()
	async def setlocation(self, ctx, *, location: str):
		if len(location) > 100:
			await ctx.send("Location is too long (max 100 characters).")
			return
		profile = ensure_user_entry(self.bot.data["profiles"], ctx.guild.id, ctx.author.id, {"location": "Not set", "bio": "Not set"})
		profile["location"] = location.strip()
		mark_dirty()
		await ctx.send(f"✅ Location saved: **{profile['location']}**")

	@commands.command()
	async def setbio(self, ctx, *, bio: str):
		if len(bio) > 200:
			await ctx.send("Bio is too long (max 200 characters).")
			return
		profile = ensure_user_entry(self.bot.data["profiles"], ctx.guild.id, ctx.author.id, {"location": "Not set", "bio": "Not set"})
		profile["bio"] = bio.strip()
		mark_dirty()
		await ctx.send("✅ Bio saved.")

	@commands.command()
	async def clearprofile(self, ctx):
		profile = ensure_user_entry(self.bot.data["profiles"], ctx.guild.id, ctx.author.id, {"location": "Not set", "bio": "Not set"})
		profile["location"] = "Not set"
		profile["bio"] = "Not set"
		profile["voice_status"] = None
		mark_dirty()
		await ctx.send("✅ Profile cleared.")

	@commands.command()
	@commands.has_permissions(manage_messages=True)
	async def userdebug(self, ctx, member: discord.Member | None = None):
		member = member or ctx.author
		full_text = await self.generate_userdebug_text(member, ctx.guild)
		chunk_size = 1800
		for start in range(0, len(full_text), chunk_size):
			chunk = full_text[start:start + chunk_size]
			await ctx.send(f"```yaml\n{chunk}\n```")

	# ─────────────────────────────────────────────────────────────────────────
	# Slash commands
	# ─────────────────────────────────────────────────────────────────────────
	@app_commands.command(name="userinfo", description="Get detailed user info")
	@app_commands.describe(member="User to inspect")
	async def userinfo_slash(self, interaction: discord.Interaction, member: discord.Member | None = None):
		member = member or interaction.user
		embed = await self.format_userinfo_embed(member)
		await interaction.response.send_message(embed=embed)

	@app_commands.command(name="setlocation", description="📍 Set your custom location shown in userinfo")
	@app_commands.describe(location="City/country or any text you want to show")
	async def setlocation_slash(self, interaction: discord.Interaction, location: str):
		if not interaction.guild:
			await interaction.response.send_message("Use this in a server.", ephemeral=True)
			return
		if len(location) > 100:
			await interaction.response.send_message("❌ Location is too long (max 100 characters).", ephemeral=True)
			return

		profile = ensure_user_entry(self.bot.data["profiles"], interaction.guild.id, interaction.user.id, {"location": "Not set", "bio": "Not set"})
		profile["location"] = location.strip()
		mark_dirty()
		
		embed = discord.Embed(
			title="📍 Location Updated!",
			description=f"Your location is now: **{profile['location']}**",
			color=Colors.PROFILE
		)
		embed.set_footer(text="This shows up in your /userinfo card~")
		await interaction.response.send_message(embed=embed, ephemeral=True)

	@app_commands.command(name="setbio", description="✏️ Set your custom bio shown in userinfo")
	@app_commands.describe(bio="Short profile bio")
	async def setbio_slash(self, interaction: discord.Interaction, bio: str):
		if not interaction.guild:
			await interaction.response.send_message("Use this in a server.", ephemeral=True)
			return
		if len(bio) > 200:
			await interaction.response.send_message("❌ Bio is too long (max 200 characters).", ephemeral=True)
			return

		profile = ensure_user_entry(self.bot.data["profiles"], interaction.guild.id, interaction.user.id, {"location": "Not set", "bio": "Not set"})
		profile["bio"] = bio.strip()
		mark_dirty()
		
		embed = discord.Embed(
			title="✏️ Bio Updated!",
			description=f"> {profile['bio']}",
			color=Colors.PROFILE
		)
		embed.set_footer(text="This shows up in your /userinfo card~")
		await interaction.response.send_message(embed=embed, ephemeral=True)

	@app_commands.command(name="setstatus", description="Set your voice activity status")
	@app_commands.describe(
		preset="Choose a preset status",
		custom="Or set a custom status (overrides preset)"
	)
	@app_commands.choices(preset=[
		app_commands.Choice(name="😌 Chilling", value="chilling"),
		app_commands.Choice(name="🎮 Gaming", value="gaming"),
		app_commands.Choice(name="📚 Studying", value="studying"),
		app_commands.Choice(name="🔄 Be Right Back", value="brb"),
		app_commands.Choice(name="👀 Kollar på grejer", value="watching"),
		app_commands.Choice(name="💼 Working", value="working"),
		app_commands.Choice(name="🎧 Listening to Music", value="listening"),
		app_commands.Choice(name="💻 Coding", value="coding"),
		app_commands.Choice(name="🍕 Eating", value="eating"),
		app_commands.Choice(name="😴 Sleeping", value="sleeping"),
	])
	async def setstatus_slash(
		self,
		interaction: discord.Interaction,
		preset: app_commands.Choice[str] | None = None,
		custom: str | None = None
	):
		if not interaction.guild:
			await interaction.response.send_message("Use this in a server.", ephemeral=True)
			return

		if not preset and not custom:
			await interaction.response.send_message(
				"Please choose a preset status or enter a custom one!", ephemeral=True
			)
			return

		if custom:
			if len(custom) > 50:
				await interaction.response.send_message(
					"❌ Custom status is too long (max 50 characters).", ephemeral=True
				)
				return
			status_text = custom.strip()
		else:
			status_text = STATUS_PRESETS.get(preset.value, preset.name)

		profile = ensure_user_entry(
			self.bot.data["profiles"], interaction.guild.id, interaction.user.id,
			{"location": "Not set", "bio": "Not set", "voice_status": None}
		)
		profile["voice_status"] = status_text
		mark_dirty()
		
		embed = discord.Embed(
			title="💭 Status Set!",
			description=f"**{status_text}**",
			color=Colors.PROFILE
		)
		embed.set_footer(text="Others can see this in your profile~")
		await interaction.response.send_message(embed=embed, ephemeral=True)

	@app_commands.command(name="clearstatus", description="🗑️ Clear your voice activity status")
	async def clearstatus_slash(self, interaction: discord.Interaction):
		if not interaction.guild:
			await interaction.response.send_message("Use this in a server.", ephemeral=True)
			return

		profile = ensure_user_entry(
			self.bot.data["profiles"], interaction.guild.id, interaction.user.id,
			{"location": "Not set", "bio": "Not set", "voice_status": None}
		)
		profile["voice_status"] = None
		mark_dirty()
		
		embed = discord.Embed(
			title="🗑️ Status Cleared",
			description="Your voice status has been removed.",
			color=Colors.WARNING
		)
		await interaction.response.send_message(embed=embed, ephemeral=True)

	@app_commands.command(name="userdebug", description="Comprehensive debug dump for a user")
	@app_commands.checks.has_permissions(manage_messages=True)
	@app_commands.describe(member="User to debug")
	async def userdebug_slash(self, interaction: discord.Interaction, member: discord.Member | None = None):
		if not interaction.guild:
			await interaction.response.send_message("Use this in a server.", ephemeral=True)
			return

		member = member or interaction.user
		full_text = await self.generate_userdebug_text(member, interaction.guild)
		chunk_size = 1800
		chunks = [full_text[i:i + chunk_size] for i in range(0, len(full_text), chunk_size)]

		await interaction.response.send_message(f"```yaml\n{chunks[0]}\n```", ephemeral=True)
		for chunk in chunks[1:]:
			await interaction.followup.send(f"```yaml\n{chunk}\n```", ephemeral=True)


async def setup(bot: commands.Bot):
	await bot.add_cog(Profile(bot))
