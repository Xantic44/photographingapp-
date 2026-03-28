import asyncio
import json
import logging
import os
import random
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks



def load_env_file(env_file: str = ".env") -> None:
	env_path = Path(env_file)
	if not env_path.exists():
		return

	for raw_line in env_path.read_text(encoding="utf-8").splitlines():
		line = raw_line.strip()
		if not line or line.startswith("#") or "=" not in line:
			continue

		key, value = line.split("=", 1)
		key = key.strip()
		value = value.strip().strip('"').strip("'")
		if key:
			os.environ.setdefault(key, value)


load_env_file()

TOKEN = os.getenv("DISCORD_TOKEN")
DATA_FILE = Path("bot_data.json")
LOG_FILE = Path("bot_debug.log")
SAVE_LOCK = asyncio.Lock()
xp_cooldown = {}
started_at = datetime.now(timezone.utc)


def configure_logging() -> logging.Logger:
	debug_enabled = os.getenv("BOT_DEBUG", "1").lower() in {"1", "true", "yes", "on"}
	level = logging.DEBUG if debug_enabled else logging.INFO

	logger = logging.getLogger("discord_bot")
	logger.setLevel(level)
	logger.handlers.clear()
	formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

	file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
	file_handler.setLevel(level)
	file_handler.setFormatter(formatter)

	stream_handler = logging.StreamHandler()
	stream_handler.setLevel(level)
	stream_handler.setFormatter(formatter)

	logger.addHandler(file_handler)
	logger.addHandler(stream_handler)
	logger.propagate = False
	return logger


logger = configure_logging()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.presences = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)


def default_data() -> dict:
	return {
		"xp": {},
		"economy": {},
		"profiles": {},
		"welcome": {},
		"tickets": {},
		"ticket_credits": {},
		"automod": {},
		"music": {},
	}


def load_data() -> dict:
	if not DATA_FILE.exists():
		return default_data()
	try:
		data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
		if isinstance(data, dict):
			return {**default_data(), **data}
	except json.JSONDecodeError:
		pass
	return default_data()


async def save_data() -> None:
	async with SAVE_LOCK:
		DATA_FILE.write_text(json.dumps(bot.data, indent=2), encoding="utf-8")


def ensure_user_entry(store: dict, guild_id: int, user_id: int, template: dict) -> dict:
	guild_key = str(guild_id)
	user_key = str(user_id)
	store.setdefault(guild_key, {})
	store[guild_key].setdefault(user_key, template.copy())
	return store[guild_key][user_key]


def xp_required_for_level(level: int) -> int:
	return 100 + (level - 1) * 25


async def get_or_create_ticket_category(guild: discord.Guild) -> discord.CategoryChannel:
	ticket_config = bot.data["tickets"].setdefault(str(guild.id), {"category_id": None, "support_role_id": None, "counter": 0})
	category_id = ticket_config.get("category_id")
	if category_id:
		category = guild.get_channel(int(category_id))
		if isinstance(category, discord.CategoryChannel):
			return category

	category = await guild.create_category("Tickets")
	ticket_config["category_id"] = category.id
	await save_data()
	return category


async def get_mutual_guild_names(user_id: int) -> list[str]:
	mutual_names = []
	for guild in bot.guilds:
		cached_member = guild.get_member(user_id)
		if cached_member:
			mutual_names.append(guild.name)
			continue

		try:
			await guild.fetch_member(user_id)
			mutual_names.append(guild.name)
		except (discord.NotFound, discord.Forbidden, discord.HTTPException):
			continue

	return mutual_names


def format_activity_lines(member: discord.Member) -> str:
	if not member.activities:
		return "None"

	lines = []
	for activity in member.activities[:5]:
		# Handle Spotify specially
		if isinstance(activity, discord.Spotify):
			artists = ", ".join(activity.artists) if activity.artists else "Unknown Artist"
			lines.append(f"🎵 **Spotify:** {activity.title} by {artists}")
			continue
		
		# Handle custom status
		if isinstance(activity, discord.CustomActivity):
			emoji = str(activity.emoji) + " " if activity.emoji else ""
			text = activity.name or "No text"
			lines.append(f"💬 **Status:** {emoji}{text}")
			continue
		
		# Handle streaming
		if isinstance(activity, discord.Streaming):
			lines.append(f"📺 **Streaming:** {activity.name} on {activity.platform or 'Unknown'}")
			continue
		
		# Handle Game activity
		if isinstance(activity, discord.Game):
			lines.append(f"🎮 **Playing:** {activity.name}")
			continue
		
		# Handle generic activities
		type_map = {
			discord.ActivityType.playing: "🎮 Playing",
			discord.ActivityType.streaming: "📺 Streaming",
			discord.ActivityType.listening: "🎧 Listening to",
			discord.ActivityType.watching: "📺 Watching",
			discord.ActivityType.competing: "🏆 Competing in",
			discord.ActivityType.custom: "💬 Status",
		}
		
		act_type = getattr(activity, "type", None)
		prefix = type_map.get(act_type, "🔹")
		name = getattr(activity, "name", None) or "Unknown"
		details = getattr(activity, "details", None)
		state = getattr(activity, "state", None)
		
		line = f"**{prefix}:** {name}"
		if details:
			line += f" — {details}"
		if state:
			line += f" ({state})"
		lines.append(line)

	return "\n".join(lines) if lines else "None"


async def format_userinfo_embed(member: discord.Member) -> discord.Embed:
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
	xp_entry = ensure_user_entry(bot.data["xp"], guild.id, member.id, {"xp": 0, "level": 1, "total_xp": 0})
	econ_entry = ensure_user_entry(bot.data["economy"], guild.id, member.id, {"funPoints": 100, "last_daily": 0, "last_work": 0})
	if "funPoints" not in econ_entry:
		econ_entry["funPoints"] = econ_entry.pop("coins", 100)
	next_xp = xp_required_for_level(xp_entry["level"])
	progress_bar = create_progress_bar(xp_entry["xp"], next_xp)

	# --- Fetch full user for banner ---
	try:
		full_user = await bot.fetch_user(member.id)
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
	profile_entry = bot.data.get("profiles", {}).get(str(guild.id), {}).get(str(member.id), {})
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


def create_progress_bar(current: int, total: int, length: int = 10) -> str:
	"""Create a visual progress bar."""
	if total <= 0:
		return "▓" * length
	filled = int((current / total) * length)
	empty = length - filled
	return "▓" * filled + "░" * empty


XP_COOLDOWN_SECONDS = 60  # Must match the cooldown in on_message


@tasks.loop(minutes=10)
async def cleanup_xp_cooldown():
	"""Remove expired entries from xp_cooldown to prevent memory growth."""
	now = time.time()
	expired = [uid for uid, ts in xp_cooldown.items() if now - ts > XP_COOLDOWN_SECONDS * 2]
	for uid in expired:
		del xp_cooldown[uid]
	if expired:
		logger.debug("Cleaned up %d expired xp_cooldown entries", len(expired))


@bot.event
async def on_ready():
	if not cleanup_xp_cooldown.is_running():
		cleanup_xp_cooldown.start()
	bot.data = load_data()
	try:
		synced = await bot.tree.sync()
		logger.info("Synced %d slash commands globally", len(synced))
	except Exception as sync_error:
		logger.exception("Failed to sync slash commands: %s", sync_error)

	logger.info("Logged in as %s", bot.user)
	logger.debug("Guild count: %s | Presence intent: %s", len(bot.guilds), bot.intents.presences)
	await bot.change_presence(activity=discord.Game(name="Type !helpme or /help"))


@bot.event
async def on_error(event_method, *args, **kwargs):
	logger.exception("Unhandled event error in %s | args=%s kwargs=%s", event_method, args, kwargs)


@bot.event
async def on_member_join(member: discord.Member):
	config = bot.data["welcome"].get(str(member.guild.id), {})
	channel_id = config.get("channel_id")
	if not channel_id:
		return

	channel = member.guild.get_channel(int(channel_id))
	if not isinstance(channel, discord.TextChannel):
		return

	template = config.get("message", "Welcome {mention} to **{server}**!")
	text = template.replace("{mention}", member.mention).replace("{server}", member.guild.name).replace("{user}", member.name)
	await channel.send(text)


@bot.event
async def on_message(message: discord.Message):
	if message.author.bot or not message.guild:
		return

	guild_id = message.guild.id
	user_id = message.author.id
	now = time.time()
	last = xp_cooldown.get((guild_id, user_id), 0)

	if now - last >= 20:
		xp_entry = ensure_user_entry(bot.data["xp"], guild_id, user_id, {"xp": 0, "level": 1, "total_xp": 0})
		gain = random.randint(8, 15)
		xp_entry["xp"] += gain
		xp_entry["total_xp"] += gain
		xp_cooldown[(guild_id, user_id)] = now

		# Passive funPoints gain for chatting
		econ_entry = ensure_user_entry(bot.data["economy"], guild_id, user_id, {"funPoints": 100, "last_daily": 0, "last_work": 0})
		if "funPoints" not in econ_entry:  # migrate old data
			econ_entry["funPoints"] = econ_entry.pop("coins", 100)
		econ_entry["funPoints"] += random.randint(1, 5)

		leveled_up = False
		while xp_entry["xp"] >= xp_required_for_level(xp_entry["level"]):
			xp_entry["xp"] -= xp_required_for_level(xp_entry["level"])
			xp_entry["level"] += 1
			leveled_up = True

		if leveled_up:
			await message.channel.send(f"🎉 {message.author.mention} leveled up to **{xp_entry['level']}**!")

		await save_data()

	automod = bot.data["automod"].get(str(guild_id), {"enabled": False, "log_channel_id": None, "blocked_words": []})
	if automod.get("enabled"):
		blocked_words = automod.get("blocked_words", [])
		content_lower = message.content.lower()
		for word in blocked_words:
			if word.lower() in content_lower:
				try:
					await message.delete()
				except discord.Forbidden:
					pass

				log_channel_id = automod.get("log_channel_id")
				if log_channel_id:
					log_channel = message.guild.get_channel(int(log_channel_id))
					if isinstance(log_channel, discord.TextChannel):
						await log_channel.send(
							f"🚨 Deleted blocked word from {message.author.mention} in {message.channel.mention}. Word: `{word}`"
						)
				break

	await bot.process_commands(message)


@bot.command()
async def ping(ctx):
	await ctx.send("Pong!")


@bot.command()
async def helpme(ctx):
	"""Categorized help command with professional embed."""
	embed = discord.Embed(
		title="📖 Bot Commands",
		description="Use `!command` for prefix commands or `/command` for slash commands.",
		color=discord.Color.blue()
	)
	embed.add_field(
		name="🔧 Utility",
		value="`!ping` `!hello` `!uptime` `!serverinfo` `!userinfo`",
		inline=False
	)
	embed.add_field(
		name="👤 Profile",
		value="`!setlocation` `!setbio` `!clearprofile` `!userdebug`",
		inline=False
	)
	embed.add_field(
		name="⭐ XP & Levels",
		value="`!rank` `/leaderboard xp`",
		inline=False
	)
	embed.add_field(
		name="💰 Economy",
		value="`!balance` `!daily` `!work` `!pay` `/leaderboard funpoints`",
		inline=False
	)
	embed.add_field(
		name="🎰 Gambling",
		value="`/coinflip` `/gamble` `/slots`",
		inline=False
	)
	embed.add_field(
		name="🎫 Tickets",
		value="`/ticket` `/close` `/ticketsetup` `/givetickets` `/checktickets`",
		inline=False
	)
	embed.add_field(
		name="🛡️ Automod",
		value="`/automod` `/addblockedword` `/setlogchannel`",
		inline=False
	)
	embed.add_field(
		name="👋 Welcome",
		value="`/setwelcome` `/setwelcomemessage`",
		inline=False
	)
	embed.add_field(
		name="🎲 Fun",
		value="`!roll` `!choose` `!remind` `!poll`",
		inline=False
	)
	embed.add_field(
		name="🎵 Music",
		value="`!play <YouTube/Spotify URL>` - Add a song\nSlash: `/play` `/skip` `/stop` `/pause` `/resume` `/queue` `/volume` `/loop` `/join` `/leave` `/shuffle` `/transferdj`",
		inline=False
	)
	embed.add_field(
		name="🔨 Moderation",
		value="`!clear` `/sendmsg` `/givefunpoints` `/removefunpoints` `/setfunpoints` `/setmusicchannel`",
		inline=False
	)
	embed.set_footer(text="Use /help for slash-only guide")
	await ctx.send(embed=embed)


@bot.command()
async def hello(ctx, member: discord.Member | None = None):
	"""Greet someone! Usage: !hello or !hello @user"""
	target = member or ctx.author
	if member:
		await ctx.send(f"Hey {target.mention}! 👋 (from {ctx.author.mention})")
	else:
		await ctx.send(f"Hey {target.mention}! 👋")


@bot.command()
async def uptime(ctx):
	now = datetime.now(timezone.utc)
	delta = now - started_at
	total_seconds = int(delta.total_seconds())
	hours, remainder = divmod(total_seconds, 3600)
	minutes, seconds = divmod(remainder, 60)
	await ctx.send(f"Uptime: {hours}h {minutes}m {seconds}s")


@bot.command()
async def serverinfo(ctx):
	guild = ctx.guild
	if guild is None:
		await ctx.send("This command only works in a server.")
		return

	created = guild.created_at.strftime("%Y-%m-%d")
	await ctx.send(
		f"Server: **{guild.name}**\n"
		f"Members: **{guild.member_count}**\n"
		f"Channels: **{len(guild.channels)}**\n"
		f"Created: **{created}**"
	)


@bot.command()
async def userinfo(ctx, member: discord.Member | None = None):
	member = member or ctx.author
	embed = await format_userinfo_embed(member)
	await ctx.send(embed=embed)


@bot.command()
@commands.has_permissions(administrator=True)
async def syncslash(ctx):
	"""Force sync all slash commands to Discord."""
	try:
		synced = await bot.tree.sync()
		await ctx.send(f"✅ Synced {len(synced)} slash commands globally. May take up to 1 hour to appear everywhere.")
		logger.info("Manual slash sync: %d commands", len(synced))
	except Exception as e:
		await ctx.send(f"❌ Slash sync failed: {e}")
		logger.exception("Manual slash sync failed: %s", e)


async def generate_userdebug_text(member: discord.Member, guild: discord.Guild) -> str:
	"""Generate comprehensive debug dump for a user."""
	# Fetch full User object for banner/accent data
	try:
		full_user = await bot.fetch_user(member.id)
		fetch_error = None
	except discord.HTTPException as e:
		full_user = None
		fetch_error = str(e)

	# === SECTION 1: Core Identity ===
	identity_lines = [
		"=== CORE IDENTITY ===",
		f"user_id={member.id}",
		f"username={member.name}",
		f"discriminator={member.discriminator}",
		f"display_name={member.display_name}",
		f"global_name={getattr(member, 'global_name', 'N/A')}",
		f"nick_in_server={member.nick}",
		f"bot={member.bot}",
		f"system={member.system}",
		f"created_at={member.created_at} (account age)",
	]

	# === SECTION 2: Avatar/Banner ===
	avatar_lines = [
		"",
		"=== AVATAR & BANNER ===",
		f"avatar_url={member.avatar.url if member.avatar else 'default'}",
		f"display_avatar_url={member.display_avatar.url}",
		f"guild_avatar={member.guild_avatar.url if member.guild_avatar else 'none'}",
	]
	if full_user:
		avatar_lines.extend([
			f"banner_url={full_user.banner.url if full_user.banner else 'none'}",
			f"accent_color={full_user.accent_color}",
			f"accent_colour_hex={str(full_user.accent_color) if full_user.accent_color else 'none'}",
		])
	else:
		avatar_lines.append(f"fetch_user_error={fetch_error}")

	# === SECTION 3: Public Flags/Badges ===
	flags_lines = ["", "=== PUBLIC FLAGS (BADGES) ==="]
	for flag_name, enabled in member.public_flags:
		if enabled:
			flags_lines.append(f"  ✓ {flag_name}")
	if len(flags_lines) == 2:
		flags_lines.append("  (no public badges)")

	# === SECTION 4: Presence & Status ===
	presence_lines = [
		"",
		"=== PRESENCE & STATUS ===",
		f"bot_intents.presences={bot.intents.presences}",
		f"status={member.status}",
		f"raw_status={member.raw_status}",
		f"desktop_status={member.desktop_status}",
		f"mobile_status={member.mobile_status}",
		f"web_status={member.web_status}",
		f"is_on_mobile()={member.is_on_mobile()}",
		"",
		"NOTE: If all statuses show 'offline' but user is online,",
		"      check Presence Intent is enabled in Discord Developer Portal.",
	]

	# === SECTION 5: Activities (deep dump with game/Spotify detection) ===
	activity_lines = [
		"",
		"=== ACTIVITIES ===",
		f"activity_count={len(member.activities)}",
		f"primary_activity={member.activity}",  # Shortcut to most prominent activity
	]
	
	# Add diagnostic info if no activities
	if not member.activities:
		activity_lines.extend([
			"",
			"  --- NO ACTIVITIES DETECTED ---",
			"  Possible reasons:",
			"  1. User has 'Display current activity' DISABLED in Discord Settings",
			"     (Settings > Activity Privacy > Display current activity as status)",
			"  2. User is not running any detected games/apps",
			"  3. Bot's Presence Intent not enabled in Developer Portal",
			"  4. User's status is Invisible (activities hidden)",
			"  5. Discord hasn't detected the game (user needs to add it manually)",
		])
	else:
		# Show each activity with full details
		for idx, activity in enumerate(member.activities, start=1):
			activity_lines.append(f"")
			activity_lines.append(f"  --- Activity {idx} ---")
			activity_lines.append(f"    class={type(activity).__name__}")
			activity_lines.append(f"    type={activity.type}")
			activity_lines.append(f"    name={getattr(activity, 'name', 'N/A')}")
			
			# Specific handling for different activity types
			if isinstance(activity, discord.Game):
				activity_lines.append(f"    [GAME DETECTED]")
				activity_lines.append(f"    game_name={activity.name}")
				activity_lines.append(f"    start={activity.start}")
				activity_lines.append(f"    end={activity.end}")
			elif isinstance(activity, discord.Streaming):
				activity_lines.append(f"    [STREAMING DETECTED]")
				activity_lines.append(f"    platform={activity.platform}")
				activity_lines.append(f"    game={activity.game}")
				activity_lines.append(f"    url={activity.url}")
				activity_lines.append(f"    twitch_name={activity.twitch_name}")
			elif isinstance(activity, discord.Spotify):
				activity_lines.append(f"    [SPOTIFY DETECTED]")
				activity_lines.append(f"    title={activity.title}")
				activity_lines.append(f"    artist={activity.artist}")
				activity_lines.append(f"    artists={activity.artists}")
				activity_lines.append(f"    album={activity.album}")
				activity_lines.append(f"    track_id={activity.track_id}")
				activity_lines.append(f"    track_url={activity.track_url}")
				activity_lines.append(f"    duration={activity.duration}")
			elif isinstance(activity, discord.CustomActivity):
				activity_lines.append(f"    [CUSTOM STATUS]")
				activity_lines.append(f"    state={activity.state}")
				activity_lines.append(f"    emoji={activity.emoji}")
			else:
				# Generic activity / Rich Presence — dump ALL attributes
				activity_lines.append(f"    [RICH PRESENCE / OTHER]")
				for attr in dir(activity):
					if not attr.startswith('_'):
						try:
							val = getattr(activity, attr, None)
							if val is not None and not callable(val):
								activity_lines.append(f"    {attr}={val}")
						except Exception:
							pass

	# === SECTION 6: Voice State ===
	voice_lines = [
		"",
		"=== VOICE STATE (THIS SERVER ONLY) ===",
		"NOTE: Bots CANNOT see DM/group calls or voice in other servers.",
		"      If user is in a private call, this will show 'No voice state'.",
	]
	if member.voice:
		v = member.voice
		voice_lines.extend([
			f"in_voice=True",
			f"channel={v.channel} (id={v.channel.id if v.channel else 'N/A'})",
			f"channel_type={type(v.channel).__name__ if v.channel else 'N/A'}",
			f"self_mute={v.self_mute}",
			f"self_deaf={v.self_deaf}",
			f"self_stream={v.self_stream}",
			f"self_video={v.self_video}",
			f"mute={v.mute}",
			f"deaf={v.deaf}",
			f"suppress={v.suppress}",
			f"requested_to_speak_at={v.requested_to_speak_at}",
			f"afk={v.afk}",
		])
	else:
		voice_lines.append("in_voice=False (not in any voice channel in THIS server)")

	# === SECTION 7: Server Membership ===
	membership_lines = [
		"",
		"=== SERVER MEMBERSHIP ===",
		f"guild={guild.name} (id={guild.id})",
		f"joined_at={member.joined_at}",
		f"premium_since={member.premium_since} (boosting)",
		f"pending={member.pending}",
		f"timed_out_until={member.timed_out_until}",
	]

	# Join position
	if member.joined_at:
		sorted_members = sorted([m for m in guild.members if m.joined_at], key=lambda m: m.joined_at)
		join_pos = next((i + 1 for i, m in enumerate(sorted_members) if m.id == member.id), "?")
		membership_lines.append(f"join_position={join_pos}/{len(sorted_members)}")

	# === SECTION 8: Roles ===
	role_lines = ["", "=== ROLES ===", f"role_count={len(member.roles)}"]
	for role in member.roles[:20]:
		role_lines.append(f"  {role.name} (id={role.id}, color={role.color}, pos={role.position})")
	if len(member.roles) > 20:
		role_lines.append(f"  ... and {len(member.roles) - 20} more")

	# === SECTION 9: Key Permissions ===
	perms = member.guild_permissions
	perm_lines = [
		"",
		"=== KEY PERMISSIONS ===",
		f"administrator={perms.administrator}",
		f"manage_guild={perms.manage_guild}",
		f"manage_channels={perms.manage_channels}",
		f"manage_roles={perms.manage_roles}",
		f"manage_messages={perms.manage_messages}",
		f"kick_members={perms.kick_members}",
		f"ban_members={perms.ban_members}",
		f"moderate_members={perms.moderate_members}",
		f"mention_everyone={perms.mention_everyone}",
	]

	# === SECTION 10: Mutual Servers (limited to 15) ===
	mutual_lines = [
		"",
		"=== MUTUAL SERVERS ===",
		"NOTE: Bots can ONLY see servers where BOTH bot and user are members.",
		"      Discord does NOT expose a user's full server list (private data).",
	]
	mutual_guilds = [g for g in bot.guilds if g.get_member(member.id)]
	mutual_count = len(mutual_guilds)
	mutual_lines.append(f"mutual_count={mutual_count}")
	for g in mutual_guilds[:15]:
		mutual_lines.append(f"  {g.name} (id={g.id}, members={g.member_count})")
	if mutual_count > 15:
		mutual_lines.append(f"  ... and {mutual_count - 15} more servers")

	# === SECTION 11: Bot Data ===
	bot_data_lines = ["", "=== BOT STORED DATA ==="]
	xp_entry = bot.data.get("xp", {}).get(str(guild.id), {}).get(str(member.id), {})
	econ_entry = bot.data.get("economy", {}).get(str(guild.id), {}).get(str(member.id), {})
	profile_entry = bot.data.get("profiles", {}).get(str(guild.id), {}).get(str(member.id), {})
	bot_data_lines.extend([
		f"xp_data={xp_entry}",
		f"economy_data={econ_entry}",
		f"profile_data={profile_entry}",
	])

	# === Combine all ===
	all_lines = (
		identity_lines + avatar_lines + flags_lines + presence_lines +
		activity_lines + voice_lines + membership_lines + role_lines +
		perm_lines + mutual_lines + bot_data_lines
	)

	return "\n".join(all_lines)


@bot.command()
@commands.has_permissions(manage_messages=True)
async def userdebug(ctx, member: discord.Member | None = None):
	"""Comprehensive debug dump for a user — covers User + Member + Guild data."""
	member = member or ctx.author
	guild = ctx.guild

	full_text = await generate_userdebug_text(member, guild)
	chunk_size = 1800
	for start in range(0, len(full_text), chunk_size):
		chunk = full_text[start:start + chunk_size]
		await ctx.send(f"```yaml\n{chunk}\n```")


@bot.tree.command(name="userdebug", description="Comprehensive debug dump for a user")
@app_commands.checks.has_permissions(manage_messages=True)
@app_commands.describe(member="User to debug")
async def userdebug_slash(interaction: discord.Interaction, member: discord.Member | None = None):
	if not interaction.guild:
		await interaction.response.send_message("Use this in a server.", ephemeral=True)
		return

	member = member or interaction.user
	guild = interaction.guild

	full_text = await generate_userdebug_text(member, guild)
	chunk_size = 1800
	chunks = [full_text[i:i + chunk_size] for i in range(0, len(full_text), chunk_size)]

	await interaction.response.send_message(f"```yaml\n{chunks[0]}\n```", ephemeral=True)
	for chunk in chunks[1:]:
		await interaction.followup.send(f"```yaml\n{chunk}\n```", ephemeral=True)


@bot.command()
async def setlocation(ctx, *, location: str):
	if not ctx.guild:
		await ctx.send("Use this command in a server.")
		return
	if len(location) > 100:
		await ctx.send("Location is too long (max 100 characters).")
		return

	profile = ensure_user_entry(bot.data["profiles"], ctx.guild.id, ctx.author.id, {"location": "Not set", "bio": "Not set"})
	profile["location"] = location.strip()
	await save_data()
	await ctx.send(f"✅ Saved your location as: **{profile['location']}**")


@bot.command()
async def setbio(ctx, *, bio: str):
	if not ctx.guild:
		await ctx.send("Use this command in a server.")
		return
	if len(bio) > 200:
		await ctx.send("Bio is too long (max 200 characters).")
		return

	profile = ensure_user_entry(bot.data["profiles"], ctx.guild.id, ctx.author.id, {"location": "Not set", "bio": "Not set"})
	profile["bio"] = bio.strip()
	await save_data()
	await ctx.send("✅ Saved your bio.")


@bot.command()
async def clearprofile(ctx):
	if not ctx.guild:
		await ctx.send("Use this command in a server.")
		return

	profile = ensure_user_entry(bot.data["profiles"], ctx.guild.id, ctx.author.id, {"location": "Not set", "bio": "Not set"})
	profile["location"] = "Not set"
	profile["bio"] = "Not set"
	await save_data()
	await ctx.send("✅ Cleared your custom profile fields.")


@bot.command()
async def rank(ctx, member: discord.Member | None = None):
	member = member or ctx.author
	entry = ensure_user_entry(bot.data["xp"], ctx.guild.id, member.id, {"xp": 0, "level": 1, "total_xp": 0})
	needed = xp_required_for_level(entry["level"])
	await ctx.send(
		f"📈 {member.mention} | Level **{entry['level']}** | XP **{entry['xp']} / {needed}** | Total XP **{entry['total_xp']}**"
	)


@bot.command()
async def balance(ctx, member: discord.Member | None = None):
	"""Check your or another user's funPoints balance."""
	if not ctx.guild:
		await ctx.send("Use this in a server.")
		return
	member = member or ctx.author
	entry = ensure_user_entry(bot.data["economy"], ctx.guild.id, member.id, {"funPoints": 100, "last_daily": 0, "last_work": 0})
	if "funPoints" not in entry:
		entry["funPoints"] = entry.pop("coins", 100)
	await save_data()
	await ctx.send(f"🎯 {member.mention} has **{entry['funPoints']}** funPoints.")


@bot.command()
async def daily(ctx):
	"""Claim your daily funPoints (24-hour cooldown)."""
	if not ctx.guild:
		await ctx.send("Use this in a server.")
		return

	entry = ensure_user_entry(bot.data["economy"], ctx.guild.id, ctx.author.id, {"funPoints": 100, "last_daily": 0, "last_work": 0})
	if "funPoints" not in entry:
		entry["funPoints"] = entry.pop("coins", 100)
	now = int(time.time())
	if now - entry["last_daily"] < 86400:
		remaining = 86400 - (now - entry["last_daily"])
		hours = remaining // 3600
		minutes = (remaining % 3600) // 60
		await ctx.send(f"⏳ Daily already claimed. Try again in **{hours}h {minutes}m**.")
		return

	amount = random.randint(150, 300)
	entry["funPoints"] += amount
	entry["last_daily"] = now
	await save_data()
	await ctx.send(f"🎁 You claimed **{amount}** funPoints! New balance: **{entry['funPoints']}**")


@bot.command()
async def work(ctx):
	"""Work for funPoints (1-hour cooldown)."""
	if not ctx.guild:
		await ctx.send("Use this in a server.")
		return

	entry = ensure_user_entry(bot.data["economy"], ctx.guild.id, ctx.author.id, {"funPoints": 100, "last_daily": 0, "last_work": 0})
	if "funPoints" not in entry:
		entry["funPoints"] = entry.pop("coins", 100)
	now = int(time.time())
	if now - entry["last_work"] < 3600:
		remaining = 3600 - (now - entry["last_work"])
		minutes = remaining // 60
		seconds = remaining % 60
		await ctx.send(f"⏳ You are tired. Work again in **{minutes}m {seconds}s**.")
		return

	amount = random.randint(40, 120)
	entry["funPoints"] += amount
	entry["last_work"] = now
	await save_data()
	await ctx.send(f"🛠️ You earned **{amount}** funPoints. Balance: **{entry['funPoints']}**")


@bot.command()
async def pay(ctx, member: discord.Member, amount: int):
	"""Send funPoints to another user. Usage: !pay @user 100"""
	if not ctx.guild:
		await ctx.send("Use this in a server.")
		return

	if amount < 1:
		await ctx.send("Amount must be at least 1.")
		return
	if member.bot:
		await ctx.send("You can't pay bots.")
		return
	if member.id == ctx.author.id:
		await ctx.send("You can't pay yourself.")
		return

	sender = ensure_user_entry(bot.data["economy"], ctx.guild.id, ctx.author.id, {"funPoints": 100, "last_daily": 0, "last_work": 0})
	if "funPoints" not in sender:
		sender["funPoints"] = sender.pop("coins", 100)
	if sender["funPoints"] < amount:
		await ctx.send(f"You only have **{sender['funPoints']}** funPoints.")
		return

	receiver = ensure_user_entry(bot.data["economy"], ctx.guild.id, member.id, {"funPoints": 100, "last_daily": 0, "last_work": 0})
	if "funPoints" not in receiver:
		receiver["funPoints"] = receiver.pop("coins", 100)
	sender["funPoints"] -= amount
	receiver["funPoints"] += amount
	await save_data()
	await ctx.send(f"✅ Sent **{amount}** funPoints to {member.mention}. Your balance: **{sender['funPoints']}**")


@bot.command()
async def roll(ctx, sides: int = 6):
	if sides < 2:
		await ctx.send("Sides must be at least 2.")
		return
	if sides > 1000:
		await ctx.send("Max 1000 sides.")
		return

	result = random.randint(1, sides)
	await ctx.send(f"🎲 You rolled **{result}** (1-{sides})")


@bot.command()
async def choose(ctx, *options: str):
	if len(options) < 2:
		await ctx.send("Give at least 2 options. Example: `!choose pizza sushi burgers`")
		return

	await ctx.send(f"I choose: **{random.choice(options)}**")


@bot.command()
async def remind(ctx, seconds: int, *, message: str):
	if seconds < 1 or seconds > 86400:
		await ctx.send("Seconds must be between 1 and 86400.")
		return

	await ctx.send(f"⏰ Okay {ctx.author.mention}, I will remind you in {seconds} seconds.")
	await asyncio.sleep(seconds)
	await ctx.send(f"🔔 Reminder for {ctx.author.mention}: {message}")


@bot.command()
async def poll(ctx, *, text: str):
	parts = [part.strip() for part in text.split("|")]
	if len(parts) < 3:
		await ctx.send("Use: `!poll Question | Option 1 | Option 2` (max 9 options)")
		return

	question = parts[0]
	options = parts[1:10]
	emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣"]
	lines = [f"{emojis[i]} {option}" for i, option in enumerate(options)]

	embed = discord.Embed(title="📊 Poll", description=f"**{question}**\n\n" + "\n".join(lines), color=0x5865F2)
	embed.set_footer(text=f"Started by {ctx.author}")
	msg = await ctx.send(embed=embed)
	for i in range(len(options)):
		await msg.add_reaction(emojis[i])


@bot.command()
@commands.has_permissions(manage_messages=True)
@commands.bot_has_permissions(manage_messages=True)
async def clear(ctx, amount: int):
	if amount < 1 or amount > 100:
		await ctx.send("Choose a number from 1 to 100.")
		return

	deleted = await ctx.channel.purge(limit=amount + 1)
	status_message = await ctx.send(f"🧹 Deleted {len(deleted) - 1} messages.")
	await asyncio.sleep(3)
	await status_message.delete()


# === SLASH VERSIONS OF UTILITY/FUN COMMANDS ===

@bot.tree.command(name="hello", description="Get a friendly greeting")
async def hello_slash(interaction: discord.Interaction):
	await interaction.response.send_message(f"Hey {interaction.user.mention}! 👋")


@bot.tree.command(name="uptime", description="Check bot uptime")
async def uptime_slash(interaction: discord.Interaction):
	now = datetime.now(timezone.utc)
	delta = now - started_at
	total_seconds = int(delta.total_seconds())
	hours, remainder = divmod(total_seconds, 3600)
	minutes, seconds = divmod(remainder, 60)
	await interaction.response.send_message(f"Uptime: **{hours}h {minutes}m {seconds}s**")


@bot.tree.command(name="serverinfo", description="Get server information")
async def serverinfo_slash(interaction: discord.Interaction):
	if not interaction.guild:
		await interaction.response.send_message("Use this in a server.", ephemeral=True)
		return
	guild = interaction.guild
	embed = discord.Embed(title=guild.name, color=discord.Color.blurple())
	embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
	embed.add_field(name="Owner", value=guild.owner, inline=True)
	embed.add_field(name="Members", value=guild.member_count, inline=True)
	embed.add_field(name="Channels", value=len(guild.channels), inline=True)
	embed.add_field(name="Roles", value=len(guild.roles), inline=True)
	embed.add_field(name="Created", value=guild.created_at.strftime("%Y-%m-%d"), inline=True)
	embed.add_field(name="Boosts", value=guild.premium_subscription_count, inline=True)
	await interaction.response.send_message(embed=embed)


@bot.tree.command(name="roll", description="Roll a dice")
@app_commands.describe(sides="Number of sides (default: 6)")
async def roll_slash(interaction: discord.Interaction, sides: int = 6):
	if sides < 2:
		await interaction.response.send_message("Sides must be at least 2.", ephemeral=True)
		return
	await interaction.response.send_message(f"🎲 You rolled a **{random.randint(1, sides)}** (d{sides})")


@bot.tree.command(name="choose", description="Let the bot choose for you")
@app_commands.describe(options="Options separated by commas (e.g., pizza, sushi, burgers)")
async def choose_slash(interaction: discord.Interaction, options: str):
	choices = [opt.strip() for opt in options.split(",") if opt.strip()]
	if len(choices) < 2:
		await interaction.response.send_message("Give at least 2 options separated by commas.", ephemeral=True)
		return
	await interaction.response.send_message(f"I choose: **{random.choice(choices)}**")


@bot.tree.command(name="remind", description="Set a reminder")
@app_commands.describe(seconds="Seconds until reminder (1-86400)", message="What to remind you")
async def remind_slash(interaction: discord.Interaction, seconds: int, message: str):
	if seconds < 1 or seconds > 86400:
		await interaction.response.send_message("Seconds must be between 1 and 86400.", ephemeral=True)
		return

	await interaction.response.send_message(f"⏰ Okay {interaction.user.mention}, I will remind you in {seconds} seconds.")
	await asyncio.sleep(seconds)
	await interaction.followup.send(f"🔔 Reminder for {interaction.user.mention}: {message}")


@bot.tree.command(name="poll", description="Create a poll")
@app_commands.describe(question="Poll question", options="Options separated by | (e.g., Yes | No | Maybe)")
async def poll_slash(interaction: discord.Interaction, question: str, options: str):
	opts = [opt.strip() for opt in options.split("|") if opt.strip()]
	if len(opts) < 2 or len(opts) > 9:
		await interaction.response.send_message("Provide 2-9 options separated by |", ephemeral=True)
		return

	emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣"]
	lines = [f"{emojis[i]} {opt}" for i, opt in enumerate(opts)]

	embed = discord.Embed(title="📊 Poll", description=f"**{question}**\n\n" + "\n".join(lines), color=0x5865F2)
	embed.set_footer(text=f"Started by {interaction.user}")
	await interaction.response.send_message(embed=embed)
	msg = await interaction.original_response()
	for i in range(len(opts)):
		await msg.add_reaction(emojis[i])


@bot.tree.command(name="clear", description="Delete messages in bulk")
@app_commands.checks.has_permissions(manage_messages=True)
@app_commands.checks.bot_has_permissions(manage_messages=True)
@app_commands.describe(amount="Number of messages to delete (1-100)")
async def clear_slash(interaction: discord.Interaction, amount: int):
	if amount < 1 or amount > 100:
		await interaction.response.send_message("Choose a number from 1 to 100.", ephemeral=True)
		return

	await interaction.response.defer(ephemeral=True)
	deleted = await interaction.channel.purge(limit=amount)
	await interaction.followup.send(f"🧹 Deleted **{len(deleted)}** messages.", ephemeral=True)


@bot.tree.command(name="help", description="Show categorized command guide")
async def help_slash(interaction: discord.Interaction):
	embed = discord.Embed(
		title="📖 Slash Commands",
		description="Here are all available slash commands.",
		color=discord.Color.blue()
	)
	embed.add_field(
		name="🔧 Utility",
		value="`/ping` `/hello` `/uptime` `/serverinfo` `/userinfo`",
		inline=False
	)
	embed.add_field(
		name="👤 Profile",
		value="`/setlocation` `/setbio` `/setstatus` `/clearstatus` `/userdebug`",
		inline=False
	)
	embed.add_field(
		name="⭐ XP & Levels",
		value="`/rank` `/leaderboard xp`",
		inline=False
	)
	embed.add_field(
		name="💰 Economy",
		value="`/balance` `/daily` `/work` `/pay` `/leaderboard funpoints`",
		inline=False
	)
	embed.add_field(
		name="🎰 Gambling",
		value="`/coinflip` `/gamble` `/slots`",
		inline=False
	)
	embed.add_field(
		name="🎫 Tickets",
		value="`/ticket` `/close` `/ticketsetup` `/givetickets` `/checktickets`",
		inline=False
	)
	embed.add_field(
		name="🛡️ Automod",
		value="`/automod` `/addblockedword` `/setlogchannel`",
		inline=False
	)
	embed.add_field(
		name="👋 Welcome",
		value="`/setwelcome` `/setwelcomemessage`",
		inline=False
	)
	embed.add_field(
		name="🎲 Fun",
		value="`/roll` `/choose` `/remind` `/poll`",
		inline=False
	)
	embed.add_field(
		name="🎵 Music",
		value="`/play` `/skip` `/stop` `/pause` `/resume` `/queue` `/remove` `/volume` `/loop` `/join` `/leave` `/shuffle` `/clearqueue` `/transferdj` `/musicstatus`",
		inline=False
	)
	embed.add_field(
		name="🔨 Moderation",
		value="`/clear` `/sendmsg` `/givefunpoints` `/removefunpoints` `/setfunpoints` `/setmusicchannel`",
		inline=False
	)
	embed.set_footer(text="Use !helpme for prefix command guide")
	await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="ping", description="Check bot latency")
async def ping_slash(interaction: discord.Interaction):
	latency_ms = round(bot.latency * 1000)
	await interaction.response.send_message(f"Pong! `{latency_ms}ms`")


@bot.tree.command(name="userinfo", description="Get detailed user info")
@app_commands.describe(member="User to inspect")
async def userinfo_slash(interaction: discord.Interaction, member: discord.Member | None = None):
	member = member or interaction.user
	embed = await format_userinfo_embed(member)
	await interaction.response.send_message(embed=embed)


@bot.tree.command(name="setlocation", description="Set your custom location shown in userinfo")
@app_commands.describe(location="City/country or any text you want to show")
async def setlocation_slash(interaction: discord.Interaction, location: str):
	if not interaction.guild:
		await interaction.response.send_message("Use this in a server.", ephemeral=True)
		return
	if len(location) > 100:
		await interaction.response.send_message("Location is too long (max 100 characters).", ephemeral=True)
		return

	profile = ensure_user_entry(bot.data["profiles"], interaction.guild.id, interaction.user.id, {"location": "Not set", "bio": "Not set"})
	profile["location"] = location.strip()
	await save_data()
	await interaction.response.send_message(f"✅ Location saved: **{profile['location']}**", ephemeral=True)


@bot.tree.command(name="setbio", description="Set your custom bio shown in userinfo")
@app_commands.describe(bio="Short profile bio")
async def setbio_slash(interaction: discord.Interaction, bio: str):
	if not interaction.guild:
		await interaction.response.send_message("Use this in a server.", ephemeral=True)
		return
	if len(bio) > 200:
		await interaction.response.send_message("Bio is too long (max 200 characters).", ephemeral=True)
		return

	profile = ensure_user_entry(bot.data["profiles"], interaction.guild.id, interaction.user.id, {"location": "Not set", "bio": "Not set"})
	profile["bio"] = bio.strip()
	await save_data()
	await interaction.response.send_message("✅ Bio saved.", ephemeral=True)


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


@bot.tree.command(name="setstatus", description="Set your voice activity status")
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
	interaction: discord.Interaction,
	preset: app_commands.Choice[str] | None = None,
	custom: str | None = None
):
	if not interaction.guild:
		await interaction.response.send_message("Use this in a server.", ephemeral=True)
		return

	# Must provide at least one
	if not preset and not custom:
		await interaction.response.send_message(
			"Please choose a preset status or enter a custom one!", ephemeral=True
		)
		return

	# Custom overrides preset
	if custom:
		if len(custom) > 50:
			await interaction.response.send_message(
				"Custom status is too long (max 50 characters).", ephemeral=True
			)
			return
		status_text = custom.strip()
	else:
		status_text = STATUS_PRESETS.get(preset.value, preset.name)

	profile = ensure_user_entry(
		bot.data["profiles"], interaction.guild.id, interaction.user.id,
		{"location": "Not set", "bio": "Not set", "voice_status": None}
	)
	profile["voice_status"] = status_text
	await save_data()
	await interaction.response.send_message(f"✅ Status set: **{status_text}**", ephemeral=True)


@bot.tree.command(name="clearstatus", description="Clear your voice activity status")
async def clearstatus_slash(interaction: discord.Interaction):
	if not interaction.guild:
		await interaction.response.send_message("Use this in a server.", ephemeral=True)
		return

	profile = ensure_user_entry(
		bot.data["profiles"], interaction.guild.id, interaction.user.id,
		{"location": "Not set", "bio": "Not set", "voice_status": None}
	)
	profile["voice_status"] = None
	await save_data()
	await interaction.response.send_message("✅ Status cleared.", ephemeral=True)


@bot.tree.command(name="sendmsg", description="Send a DM to a user through the bot")
@app_commands.checks.has_permissions(manage_messages=True)
@app_commands.describe(user="User to DM", text="Message content")
async def sendmsg(interaction: discord.Interaction, user: discord.User, text: str):
	await send_dm_to_user(interaction, user, text)


@bot.tree.command(name="msg", description="Send a DM to a user through the bot")
@app_commands.checks.has_permissions(manage_messages=True)
@app_commands.describe(user="User to DM", text="Message content")
async def msg(interaction: discord.Interaction, user: discord.User, text: str):
	await send_dm_to_user(interaction, user, text)


async def send_dm_to_user(interaction: discord.Interaction, user: discord.User, text: str):
	if len(text) > 1900:
		await interaction.response.send_message("Message is too long (max 1900 characters).", ephemeral=True)
		return
	if user.bot:
		await interaction.response.send_message("Choose a real user, not a bot account.", ephemeral=True)
		return
	if user.id == interaction.user.id:
		await interaction.response.send_message("Send messages to someone else, not yourself.", ephemeral=True)
		return

	message_text = (
		f"📩 You got a message from **{interaction.user}** in **{interaction.guild.name if interaction.guild else 'a server'}**:\n\n"
		f"{text}"
	)

	try:
		dm_channel = user.dm_channel or await user.create_dm()
		await dm_channel.send(message_text)
	except discord.Forbidden:
		await interaction.response.send_message("I couldn't DM that user (their DMs may be closed).", ephemeral=True)
		return
	except discord.HTTPException:
		await interaction.response.send_message("Failed to send DM due to a Discord error. Try again.", ephemeral=True)
		return

	await interaction.response.send_message(f"✅ Sent your message to **{user}**.", ephemeral=True)


@bot.tree.command(name="rank", description="See your (or another user's) XP rank")
@app_commands.describe(member="User to inspect")
async def rank_slash(interaction: discord.Interaction, member: discord.Member | None = None):
	if not interaction.guild:
		await interaction.response.send_message("Use this in a server.", ephemeral=True)
		return
	member = member or interaction.user
	entry = ensure_user_entry(bot.data["xp"], interaction.guild.id, member.id, {"xp": 0, "level": 1, "total_xp": 0})
	needed = xp_required_for_level(entry["level"])
	await interaction.response.send_message(
		f"📈 {member.mention} | Level **{entry['level']}** | XP **{entry['xp']} / {needed}** | Total XP **{entry['total_xp']}**"
	)


@bot.tree.command(name="leaderboard", description="View XP or funPoints leaderboard")
@app_commands.describe(category="Choose xp or funpoints")
@app_commands.choices(category=[
	app_commands.Choice(name="XP", value="xp"),
	app_commands.Choice(name="funPoints", value="funpoints"),
])
async def leaderboard_slash(interaction: discord.Interaction, category: app_commands.Choice[str]):
	if not interaction.guild:
		await interaction.response.send_message("Use this in a server.", ephemeral=True)
		return

	guild_id = str(interaction.guild.id)

	if category.value == "xp":
		data = bot.data.get("xp", {}).get(guild_id, {})
		sorted_users = sorted(data.items(), key=lambda x: x[1].get("total_xp", 0), reverse=True)[:10]
		title = "🏆 XP Leaderboard"
		lines = []
		for i, (user_id, entry) in enumerate(sorted_users, 1):
			user = interaction.guild.get_member(int(user_id))
			name = user.display_name if user else f"User {user_id}"
			lines.append(f"**{i}.** {name} — Level {entry.get('level', 1)} ({entry.get('total_xp', 0)} XP)")
	else:
		data = bot.data.get("economy", {}).get(guild_id, {})
		sorted_users = sorted(data.items(), key=lambda x: x[1].get("funPoints", x[1].get("coins", 0)), reverse=True)[:10]
		title = "🎯 funPoints Leaderboard"
		lines = []
		for i, (user_id, entry) in enumerate(sorted_users, 1):
			user = interaction.guild.get_member(int(user_id))
			name = user.display_name if user else f"User {user_id}"
			lines.append(f"**{i}.** {name} — {entry.get('funPoints', entry.get('coins', 0))} funPoints")

	if not lines:
		await interaction.response.send_message("No data yet!", ephemeral=True)
		return

	embed = discord.Embed(title=title, description="\n".join(lines), color=discord.Color.gold())
	embed.set_footer(text=f"Top 10 in {interaction.guild.name}")
	await interaction.response.send_message(embed=embed)


@bot.command()
async def leaderboard(ctx, category: str = "xp"):
	"""View XP or funPoints leaderboard. Usage: !leaderboard xp or !leaderboard funpoints"""
	if not ctx.guild:
		await ctx.send("Use this in a server.")
		return

	category = category.lower()
	if category not in ("xp", "funpoints"):
		await ctx.send("Usage: `!leaderboard xp` or `!leaderboard funpoints`")
		return

	guild_id = str(ctx.guild.id)

	if category == "xp":
		data = bot.data.get("xp", {}).get(guild_id, {})
		sorted_users = sorted(data.items(), key=lambda x: x[1].get("total_xp", 0), reverse=True)[:10]
		title = "🏆 XP Leaderboard"
		lines = []
		for i, (user_id, entry) in enumerate(sorted_users, 1):
			user = ctx.guild.get_member(int(user_id))
			name = user.display_name if user else f"User {user_id}"
			lines.append(f"**{i}.** {name} — Level {entry.get('level', 1)} ({entry.get('total_xp', 0)} XP)")
	else:
		data = bot.data.get("economy", {}).get(guild_id, {})
		sorted_users = sorted(data.items(), key=lambda x: x[1].get("funPoints", x[1].get("coins", 0)), reverse=True)[:10]
		title = "🎯 funPoints Leaderboard"
		lines = []
		for i, (user_id, entry) in enumerate(sorted_users, 1):
			user = ctx.guild.get_member(int(user_id))
			name = user.display_name if user else f"User {user_id}"
			lines.append(f"**{i}.** {name} — {entry.get('funPoints', entry.get('coins', 0))} funPoints")

	if not lines:
		await ctx.send("No data yet!")
		return

	embed = discord.Embed(title=title, description="\n".join(lines), color=discord.Color.gold())
	embed.set_footer(text=f"Top 10 in {ctx.guild.name}")
	await ctx.send(embed=embed)


@bot.tree.command(name="setwelcome", description="Set the welcome channel")
@app_commands.checks.has_permissions(manage_guild=True)
@app_commands.describe(channel="Channel where welcome messages will be sent")
async def setwelcome(interaction: discord.Interaction, channel: discord.TextChannel):
	if not interaction.guild:
		await interaction.response.send_message("Use this in a server.", ephemeral=True)
		return

	entry = bot.data["welcome"].setdefault(str(interaction.guild.id), {})
	entry["channel_id"] = channel.id
	entry.setdefault("message", "Welcome {mention} to **{server}**!")
	await save_data()
	await interaction.response.send_message(f"✅ Welcome channel set to {channel.mention}")


@bot.tree.command(name="setwelcomemessage", description="Set custom welcome text")
@app_commands.checks.has_permissions(manage_guild=True)
@app_commands.describe(message="Use {mention}, {user}, and {server}")
async def setwelcomemessage(interaction: discord.Interaction, message: str):
	if not interaction.guild:
		await interaction.response.send_message("Use this in a server.", ephemeral=True)
		return

	entry = bot.data["welcome"].setdefault(str(interaction.guild.id), {})
	entry["message"] = message
	await save_data()
	await interaction.response.send_message("✅ Welcome message updated.")


@bot.tree.command(name="balance", description="Check funPoints balance")
@app_commands.describe(member="Optional member to check")
async def balance(interaction: discord.Interaction, member: discord.Member | None = None):
	if not interaction.guild:
		await interaction.response.send_message("Use this in a server.", ephemeral=True)
		return

	member = member or interaction.user
	entry = ensure_user_entry(bot.data["economy"], interaction.guild.id, member.id, {"funPoints": 100, "last_daily": 0, "last_work": 0})
	if "funPoints" not in entry:
		entry["funPoints"] = entry.pop("coins", 100)
	await save_data()
	await interaction.response.send_message(f"🎯 {member.mention} has **{entry['funPoints']}** funPoints.")


@bot.tree.command(name="daily", description="Claim daily funPoints")
async def daily(interaction: discord.Interaction):
	if not interaction.guild:
		await interaction.response.send_message("Use this in a server.", ephemeral=True)
		return

	entry = ensure_user_entry(bot.data["economy"], interaction.guild.id, interaction.user.id, {"funPoints": 100, "last_daily": 0, "last_work": 0})
	if "funPoints" not in entry:
		entry["funPoints"] = entry.pop("coins", 100)
	now = int(time.time())
	if now - entry["last_daily"] < 86400:
		remaining = 86400 - (now - entry["last_daily"])
		hours = remaining // 3600
		minutes = (remaining % 3600) // 60
		await interaction.response.send_message(f"⏳ Daily already claimed. Try again in {hours}h {minutes}m.", ephemeral=True)
		return

	amount = random.randint(150, 300)
	entry["funPoints"] += amount
	entry["last_daily"] = now
	await save_data()
	await interaction.response.send_message(f"🎁 You claimed **{amount}** funPoints! New balance: **{entry['funPoints']}**")


@bot.tree.command(name="work", description="Work for funPoints (cooldown: 1 hour)")
async def work(interaction: discord.Interaction):
	if not interaction.guild:
		await interaction.response.send_message("Use this in a server.", ephemeral=True)
		return

	entry = ensure_user_entry(bot.data["economy"], interaction.guild.id, interaction.user.id, {"funPoints": 100, "last_daily": 0, "last_work": 0})
	if "funPoints" not in entry:
		entry["funPoints"] = entry.pop("coins", 100)
	now = int(time.time())
	if now - entry["last_work"] < 3600:
		remaining = 3600 - (now - entry["last_work"])
		minutes = remaining // 60
		await interaction.response.send_message(f"⏳ You are tired. Work again in {minutes}m.", ephemeral=True)
		return

	amount = random.randint(40, 120)
	entry["funPoints"] += amount
	entry["last_work"] = now
	await save_data()
	await interaction.response.send_message(f"🛠️ You earned **{amount}** funPoints. Balance: **{entry['funPoints']}**")


@bot.tree.command(name="pay", description="Send funPoints to another user")
@app_commands.describe(member="User to pay", amount="funPoints to transfer")
async def pay(interaction: discord.Interaction, member: discord.Member, amount: int):
	if not interaction.guild:
		await interaction.response.send_message("Use this in a server.", ephemeral=True)
		return
	if amount <= 0:
		await interaction.response.send_message("Amount must be more than 0.", ephemeral=True)
		return
	if member.bot or member.id == interaction.user.id:
		await interaction.response.send_message("Pick another real user.", ephemeral=True)
		return

	sender = ensure_user_entry(bot.data["economy"], interaction.guild.id, interaction.user.id, {"funPoints": 100, "last_daily": 0, "last_work": 0})
	receiver = ensure_user_entry(bot.data["economy"], interaction.guild.id, member.id, {"funPoints": 100, "last_daily": 0, "last_work": 0})
	if "funPoints" not in sender:
		sender["funPoints"] = sender.pop("coins", 100)
	if "funPoints" not in receiver:
		receiver["funPoints"] = receiver.pop("coins", 100)
	if sender["funPoints"] < amount:
		await interaction.response.send_message("You do not have enough funPoints.", ephemeral=True)
		return

	sender["funPoints"] -= amount
	receiver["funPoints"] += amount
	await save_data()
	await interaction.response.send_message(f"💸 Sent **{amount}** funPoints to {member.mention}.")


# --- GAMBLING COMMANDS ---

@bot.tree.command(name="coinflip", description="Flip a coin and bet funPoints (50/50 odds)")
@app_commands.describe(amount="Amount to bet", choice="Heads or Tails")
@app_commands.choices(choice=[
	app_commands.Choice(name="Heads", value="heads"),
	app_commands.Choice(name="Tails", value="tails"),
])
async def coinflip(interaction: discord.Interaction, amount: int, choice: app_commands.Choice[str]):
	if not interaction.guild:
		await interaction.response.send_message("Use this in a server.", ephemeral=True)
		return
	if amount <= 0:
		await interaction.response.send_message("Bet must be more than 0.", ephemeral=True)
		return

	entry = ensure_user_entry(bot.data["economy"], interaction.guild.id, interaction.user.id, {"funPoints": 100, "last_daily": 0, "last_work": 0})
	if "funPoints" not in entry:
		entry["funPoints"] = entry.pop("coins", 100)
	if entry["funPoints"] < amount:
		await interaction.response.send_message("You don't have enough funPoints.", ephemeral=True)
		return

	result = random.choice(["heads", "tails"])
	won = (choice.value == result)

	if won:
		entry["funPoints"] += amount
		emoji = "🎉"
		outcome = f"You won **{amount}** funPoints!"
	else:
		entry["funPoints"] -= amount
		emoji = "😢"
		outcome = f"You lost **{amount}** funPoints."

	await save_data()
	await interaction.response.send_message(f"🪙 The coin landed on **{result.capitalize()}**! {emoji}\n{outcome}\nBalance: **{entry['funPoints']}** funPoints")


@bot.tree.command(name="gamble", description="Gamble funPoints (45% win chance, 2x payout)")
@app_commands.describe(amount="Amount to gamble")
async def gamble(interaction: discord.Interaction, amount: int):
	if not interaction.guild:
		await interaction.response.send_message("Use this in a server.", ephemeral=True)
		return
	if amount <= 0:
		await interaction.response.send_message("Amount must be more than 0.", ephemeral=True)
		return

	entry = ensure_user_entry(bot.data["economy"], interaction.guild.id, interaction.user.id, {"funPoints": 100, "last_daily": 0, "last_work": 0})
	if "funPoints" not in entry:
		entry["funPoints"] = entry.pop("coins", 100)
	if entry["funPoints"] < amount:
		await interaction.response.send_message("You don't have enough funPoints.", ephemeral=True)
		return

	roll = random.randint(1, 100)
	won = roll <= 45  # 45% chance to win

	if won:
		winnings = amount * 2
		entry["funPoints"] += amount  # Net gain is amount (since they bet amount, win 2x)
		emoji = "🎰"
		outcome = f"You rolled **{roll}** and won **{winnings}** funPoints! (2x your bet)"
	else:
		entry["funPoints"] -= amount
		emoji = "💸"
		outcome = f"You rolled **{roll}** and lost **{amount}** funPoints."

	await save_data()
	await interaction.response.send_message(f"{emoji} {outcome}\nBalance: **{entry['funPoints']}** funPoints")


@bot.tree.command(name="slots", description="Play slots for funPoints")
@app_commands.describe(amount="Amount to bet")
async def slots(interaction: discord.Interaction, amount: int):
	if not interaction.guild:
		await interaction.response.send_message("Use this in a server.", ephemeral=True)
		return
	if amount <= 0:
		await interaction.response.send_message("Bet must be more than 0.", ephemeral=True)
		return

	entry = ensure_user_entry(bot.data["economy"], interaction.guild.id, interaction.user.id, {"funPoints": 100, "last_daily": 0, "last_work": 0})
	if "funPoints" not in entry:
		entry["funPoints"] = entry.pop("coins", 100)
	if entry["funPoints"] < amount:
		await interaction.response.send_message("You don't have enough funPoints.", ephemeral=True)
		return

	symbols = ["🍒", "🍋", "🍊", "🍇", "⭐", "💎", "7️⃣"]
	weights = [25, 20, 18, 15, 12, 7, 3]  # Lower weight = rarer
	reels = random.choices(symbols, weights=weights, k=3)

	# Calculate winnings
	multiplier = 0
	if reels[0] == reels[1] == reels[2]:
		if reels[0] == "7️⃣":
			multiplier = 10  # Jackpot!
		elif reels[0] == "💎":
			multiplier = 5
		elif reels[0] == "⭐":
			multiplier = 4
		else:
			multiplier = 3
	elif reels[0] == reels[1] or reels[1] == reels[2]:
		multiplier = 1.5

	display = " | ".join(reels)

	if multiplier > 0:
		winnings = int(amount * multiplier)
		net_gain = winnings - amount
		entry["funPoints"] += net_gain
		if multiplier == 10:
			result = f"🎰 **JACKPOT!!!** 🎰\n[ {display} ]\nYou won **{winnings}** funPoints! (10x)"
		else:
			result = f"🎰 [ {display} ] 🎰\n🎉 You won **{winnings}** funPoints! ({multiplier}x)"
	else:
		entry["funPoints"] -= amount
		result = f"🎰 [ {display} ] 🎰\n😢 No match. You lost **{amount}** funPoints."

	await save_data()
	await interaction.response.send_message(f"{result}\nBalance: **{entry['funPoints']}** funPoints")


# --- ADMIN FUNPOINTS COMMANDS ---

@bot.tree.command(name="givefunpoints", description="[Admin] Give funPoints to a user")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(member="User to give funPoints to", amount="Amount of funPoints")
async def givefunpoints(interaction: discord.Interaction, member: discord.Member, amount: int):
	if not interaction.guild:
		await interaction.response.send_message("Use this in a server.", ephemeral=True)
		return
	if amount <= 0:
		await interaction.response.send_message("Amount must be more than 0.", ephemeral=True)
		return
	if member.bot:
		await interaction.response.send_message("Can't give funPoints to bots.", ephemeral=True)
		return

	entry = ensure_user_entry(bot.data["economy"], interaction.guild.id, member.id, {"funPoints": 100, "last_daily": 0, "last_work": 0})
	if "funPoints" not in entry:
		entry["funPoints"] = entry.pop("coins", 100)
	entry["funPoints"] += amount
	await save_data()
	await interaction.response.send_message(f"✅ Gave **{amount}** funPoints to {member.mention}. New balance: **{entry['funPoints']}**")


@bot.tree.command(name="removefunpoints", description="[Admin] Remove funPoints from a user")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(member="User to remove funPoints from", amount="Amount of funPoints")
async def removefunpoints(interaction: discord.Interaction, member: discord.Member, amount: int):
	if not interaction.guild:
		await interaction.response.send_message("Use this in a server.", ephemeral=True)
		return
	if amount <= 0:
		await interaction.response.send_message("Amount must be more than 0.", ephemeral=True)
		return
	if member.bot:
		await interaction.response.send_message("Can't remove funPoints from bots.", ephemeral=True)
		return

	entry = ensure_user_entry(bot.data["economy"], interaction.guild.id, member.id, {"funPoints": 100, "last_daily": 0, "last_work": 0})
	if "funPoints" not in entry:
		entry["funPoints"] = entry.pop("coins", 100)
	entry["funPoints"] = max(0, entry["funPoints"] - amount)
	await save_data()
	await interaction.response.send_message(f"✅ Removed **{amount}** funPoints from {member.mention}. New balance: **{entry['funPoints']}**")


@bot.tree.command(name="setfunpoints", description="[Admin] Set a user's funPoints balance")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(member="User to set funPoints for", amount="New funPoints balance")
async def setfunpoints(interaction: discord.Interaction, member: discord.Member, amount: int):
	if not interaction.guild:
		await interaction.response.send_message("Use this in a server.", ephemeral=True)
		return
	if amount < 0:
		await interaction.response.send_message("Amount can't be negative.", ephemeral=True)
		return
	if member.bot:
		await interaction.response.send_message("Can't set funPoints for bots.", ephemeral=True)
		return

	entry = ensure_user_entry(bot.data["economy"], interaction.guild.id, member.id, {"funPoints": 100, "last_daily": 0, "last_work": 0})
	entry["funPoints"] = amount
	await save_data()
	await interaction.response.send_message(f"✅ Set {member.mention}'s funPoints to **{amount}**.")


@bot.tree.command(name="ticketsetup", description="Configure support role for tickets")
@app_commands.checks.has_permissions(manage_guild=True)
@app_commands.describe(support_role="Role that can access tickets")
async def ticketsetup(interaction: discord.Interaction, support_role: discord.Role):
	if not interaction.guild:
		await interaction.response.send_message("Use this in a server.", ephemeral=True)
		return

	entry = bot.data["tickets"].setdefault(str(interaction.guild.id), {"category_id": None, "support_role_id": None, "counter": 0})
	entry["support_role_id"] = support_role.id
	await save_data()
	await interaction.response.send_message(f"✅ Ticket support role set to {support_role.mention}.")


@bot.tree.command(name="ticket", description="Create a private support ticket (costs 1 credit)")
@app_commands.describe(reason="Reason for the ticket")
async def ticket(interaction: discord.Interaction, reason: str):
	if not interaction.guild:
		await interaction.response.send_message("Use this in a server.", ephemeral=True)
		return

	guild = interaction.guild
	guild_id = str(guild.id)
	user_id = str(interaction.user.id)

	# Check ticket credits
	credits_store = bot.data.setdefault("ticket_credits", {}).setdefault(guild_id, {})
	user_credits = credits_store.get(user_id, 0)

	if user_credits < 1:
		await interaction.response.send_message(
			"❌ You don't have any ticket credits. Ask an admin to give you tickets with `/givetickets`.",
			ephemeral=True
		)
		return

	# Deduct 1 credit
	credits_store[user_id] = user_credits - 1

	entry = bot.data["tickets"].setdefault(guild_id, {"category_id": None, "support_role_id": None, "counter": 0})
	category = await get_or_create_ticket_category(guild)
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
	await save_data()

	await interaction.response.send_message(f"🎫 Ticket created: {channel.mention}", ephemeral=True)
	await channel.send(f"{interaction.user.mention} created this ticket.\nReason: **{reason}**\nUse `/close` to close it.")


@bot.tree.command(name="close", description="Close the current ticket channel")
async def close(interaction: discord.Interaction):
	if not interaction.guild or not isinstance(interaction.channel, discord.TextChannel):
		await interaction.response.send_message("Use this in a ticket channel.", ephemeral=True)
		return
	if not interaction.channel.name.startswith("ticket-"):
		await interaction.response.send_message("This is not a ticket channel.", ephemeral=True)
		return

	await interaction.response.send_message("🔒 Closing ticket in 5 seconds...")
	await asyncio.sleep(5)
	await interaction.channel.delete(reason=f"Closed by {interaction.user}")


@bot.tree.command(name="givetickets", description="Give ticket credits to a user")
@app_commands.checks.has_permissions(manage_guild=True)
@app_commands.describe(user="User to give tickets to", amount="Number of ticket credits")
async def givetickets(interaction: discord.Interaction, user: discord.Member, amount: int):
	if not interaction.guild:
		await interaction.response.send_message("Use this in a server.", ephemeral=True)
		return

	if amount < 1:
		await interaction.response.send_message("Amount must be at least 1.", ephemeral=True)
		return

	guild_id = str(interaction.guild.id)
	user_id = str(user.id)

	credits_store = bot.data.setdefault("ticket_credits", {}).setdefault(guild_id, {})
	current = credits_store.get(user_id, 0)
	credits_store[user_id] = current + amount
	await save_data()

	await interaction.response.send_message(
		f"🎫 Gave **{amount}** ticket credit(s) to {user.mention}. They now have **{credits_store[user_id]}** tickets."
	)


@bot.tree.command(name="checktickets", description="Check ticket credits")
@app_commands.describe(user="User to check (leave empty for yourself)")
async def checktickets(interaction: discord.Interaction, user: discord.Member | None = None):
	if not interaction.guild:
		await interaction.response.send_message("Use this in a server.", ephemeral=True)
		return

	target = user or interaction.user
	guild_id = str(interaction.guild.id)
	user_id = str(target.id)

	credits_store = bot.data.setdefault("ticket_credits", {}).setdefault(guild_id, {})
	credits = credits_store.get(user_id, 0)

	await interaction.response.send_message(f"🎫 {target.mention} has **{credits}** ticket credit(s).")


@bot.tree.command(name="removetickets", description="Remove ticket credits from a user")
@app_commands.checks.has_permissions(manage_guild=True)
@app_commands.describe(user="User to remove tickets from", amount="Number to remove")
async def removetickets(interaction: discord.Interaction, user: discord.Member, amount: int):
	if not interaction.guild:
		await interaction.response.send_message("Use this in a server.", ephemeral=True)
		return

	if amount < 1:
		await interaction.response.send_message("Amount must be at least 1.", ephemeral=True)
		return

	guild_id = str(interaction.guild.id)
	user_id = str(user.id)

	credits_store = bot.data.setdefault("ticket_credits", {}).setdefault(guild_id, {})
	current = credits_store.get(user_id, 0)
	new_balance = max(0, current - amount)
	credits_store[user_id] = new_balance
	await save_data()

	await interaction.response.send_message(
		f"🎫 Removed **{min(amount, current)}** ticket credit(s) from {user.mention}. They now have **{new_balance}** tickets."
	)


@bot.tree.command(name="automod", description="Turn automod on or off")
@app_commands.checks.has_permissions(manage_guild=True)
@app_commands.describe(enabled="Enable (true) or disable (false)")
async def automod(interaction: discord.Interaction, enabled: bool):
	if not interaction.guild:
		await interaction.response.send_message("Use this in a server.", ephemeral=True)
		return

	entry = bot.data["automod"].setdefault(str(interaction.guild.id), {"enabled": False, "log_channel_id": None, "blocked_words": []})
	entry["enabled"] = enabled
	await save_data()
	await interaction.response.send_message(f"✅ Automod is now {'enabled' if enabled else 'disabled'}.")


@bot.tree.command(name="addblockedword", description="Add a blocked word for automod")
@app_commands.checks.has_permissions(manage_guild=True)
async def addblockedword(interaction: discord.Interaction, word: str):
	if not interaction.guild:
		await interaction.response.send_message("Use this in a server.", ephemeral=True)
		return

	clean_word = word.strip().lower()
	if not clean_word:
		await interaction.response.send_message("Word cannot be empty.", ephemeral=True)
		return

	entry = bot.data["automod"].setdefault(str(interaction.guild.id), {"enabled": False, "log_channel_id": None, "blocked_words": []})
	if clean_word not in entry["blocked_words"]:
		entry["blocked_words"].append(clean_word)
	await save_data()
	await interaction.response.send_message(f"✅ Added blocked word: `{clean_word}`")


@bot.tree.command(name="setlogchannel", description="Set automod log channel")
@app_commands.checks.has_permissions(manage_guild=True)
async def setlogchannel(interaction: discord.Interaction, channel: discord.TextChannel):
	if not interaction.guild:
		await interaction.response.send_message("Use this in a server.", ephemeral=True)
		return

	entry = bot.data["automod"].setdefault(str(interaction.guild.id), {"enabled": False, "log_channel_id": None, "blocked_words": []})
	entry["log_channel_id"] = channel.id
	await save_data()
	await interaction.response.send_message(f"✅ Automod logs will be sent to {channel.mention}")


@bot.event
async def on_command_error(ctx, error):
	# Don't log CommandNotFound (spam)
	if isinstance(error, commands.CommandNotFound):
		return

	logger.exception(
		"Prefix command error | command=%s author=%s guild=%s channel=%s",
		getattr(ctx.command, "qualified_name", "unknown"),
		ctx.author,
		getattr(ctx.guild, "id", None),
		getattr(ctx.channel, "id", None),
		exc_info=error,
	)

	if isinstance(error, commands.MissingRequiredArgument):
		await ctx.send("Missing arguments. Use `!helpme` to see command usage.")
		return
	if isinstance(error, commands.BadArgument):
		await ctx.send("Invalid argument type. Use `!helpme` for examples.")
		return
	if isinstance(error, commands.MissingPermissions):
		await ctx.send("You do not have permission to use this command.")
		return
	if isinstance(error, commands.BotMissingPermissions):
		await ctx.send("I need more permissions to do that.")
		return

	await ctx.send("Something went wrong running that command.")


# ═══════════════════════════════════════════════════════════════════════════════
# MUSIC SYSTEM
# ═══════════════════════════════════════════════════════════════════════════════

YOUTUBE_REGEX = re.compile(
	r"(https?://)?(www\.)?(youtube\.com|youtu\.be)/(watch\?v=|embed/|v/|shorts/)?[\w-]+",
	re.IGNORECASE
)
SPOTIFY_REGEX = re.compile(
	r"(https?://)?(open\.)?spotify\.com/(track|album|playlist)/[\w]+",
	re.IGNORECASE
)

YTDL_OPTIONS = {
	"format": "bestaudio/best",
	"noplaylist": True,
	"quiet": True,
	"no_warnings": True,
	"default_search": "ytsearch",
	"source_address": "0.0.0.0",
	"extract_flat": False,
}

FFMPEG_PATH = r"C:\ffmpeg\ffmpeg-8.0.1-essentials_build\bin\ffmpeg.exe"

FFMPEG_OPTIONS = {
	"before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
	"options": "-vn",
	"executable": FFMPEG_PATH,
}


class QueueChoiceView(discord.ui.View):
	"""View with buttons to choose between resuming saved queue or starting fresh."""
	def __init__(self, saved_count: int):
		super().__init__(timeout=60)
		self.choice: Optional[str] = None
		self.saved_count = saved_count

	@discord.ui.button(label="1️⃣ Resume Queue", style=discord.ButtonStyle.green)
	async def resume_button(self, interaction: discord.Interaction, button: discord.ui.Button):
		self.choice = "resume"
		self.stop()
		await interaction.response.defer()

	@discord.ui.button(label="2️⃣ Start Fresh", style=discord.ButtonStyle.red)
	async def fresh_button(self, interaction: discord.Interaction, button: discord.ui.Button):
		self.choice = "fresh"
		self.stop()
		await interaction.response.defer()

	async def on_timeout(self):
		self.choice = "timeout"


class Song:
	"""Represents a song in the queue."""
	def __init__(self, source_url: str, title: str, duration: int, thumbnail: str, webpage_url: str, requester: discord.Member):
		self.source_url = source_url
		self.title = title
		self.duration = duration
		self.thumbnail = thumbnail
		self.webpage_url = webpage_url
		self.requester = requester

	@property
	def duration_str(self) -> str:
		if self.duration:
			mins, secs = divmod(self.duration, 60)
			return f"{mins}:{secs:02d}"
		return "Unknown"


def linear_to_log_volume(linear: float) -> float:
	"""Convert linear volume (0-1) to logarithmic for natural perception."""
	if linear <= 0:
		return 0.0
	# Use logarithmic curve: more granular at low volumes
	return max(0.0, min(1.0, (linear ** 2.5) * 0.5))


class MusicPlayer:
	"""Per-guild music player with queue management."""
	def __init__(self, guild: discord.Guild):
		self.guild = guild
		self.queue: list[Song] = []
		self.current: Optional[Song] = None
		self.voice_client: Optional[discord.VoiceClient] = None
		self.loop = False
		self._linear_volume = 0.5  # User-facing volume (0-1)
		self.dj: Optional[int] = None  # User ID of whoever summoned the bot
		self._play_next_lock = asyncio.Lock()

	@property
	def volume(self) -> float:
		"""Get the actual audio volume (logarithmically scaled)."""
		return linear_to_log_volume(self._linear_volume)

	@volume.setter
	def volume(self, value: float):
		"""Set linear volume (will be converted to log for playback)."""
		self._linear_volume = max(0.0, min(1.0, value))

	async def play_next(self):
		"""Play the next song in queue."""
		async with self._play_next_lock:
			if self.loop and self.current:
				song = self.current
			elif self.queue:
				song = self.queue.pop(0)
			else:
				self.current = None
				return

			self.current = song

			try:
				import yt_dlp
				with yt_dlp.YoutubeDL(YTDL_OPTIONS) as ydl:
					info = ydl.extract_info(song.webpage_url, download=False)
					if "url" in info:
						song.source_url = info["url"]
			except Exception as e:
				logger.error("Failed to refresh audio URL: %s", e)

			if self.voice_client and self.voice_client.is_connected():
				source = discord.PCMVolumeTransformer(
					discord.FFmpegPCMAudio(song.source_url, **FFMPEG_OPTIONS),
					volume=self.volume
				)

				def after_playing(error):
					if error:
						logger.error("Playback error: %s", error)
					asyncio.run_coroutine_threadsafe(self.play_next(), bot.loop)

				self.voice_client.play(source, after=after_playing)

				# Log to music channel
				asyncio.run_coroutine_threadsafe(
					self._log_now_playing(song),
					bot.loop
				)

	async def _log_now_playing(self, song: Song):
		"""Log the currently playing song to the music log channel."""
		guild_id = str(self.guild.id)
		music_data = bot.data["music"].get(guild_id, {})
		log_channel_id = music_data.get("log_channel")

		if log_channel_id:
			channel = self.guild.get_channel(log_channel_id)
			if channel:
				embed = discord.Embed(
					title="🎵 Now Playing",
					description=f"**[{song.title}]({song.webpage_url})**",
					color=discord.Color.green()
				)
				embed.add_field(name="Duration", value=song.duration_str, inline=True)
				embed.add_field(name="Requested by", value=song.requester.mention, inline=True)
				embed.add_field(name="Queue", value=f"{len(self.queue)} songs remaining", inline=True)
				if song.thumbnail:
					embed.set_thumbnail(url=song.thumbnail)
				try:
					await channel.send(embed=embed)
				except discord.Forbidden:
					pass

	async def _log_song_added(self, song: Song, position: int):
		"""Log when a song is added to the queue."""
		guild_id = str(self.guild.id)
		music_data = bot.data["music"].get(guild_id, {})
		log_channel_id = music_data.get("log_channel")

		if log_channel_id:
			channel = self.guild.get_channel(log_channel_id)
			if channel:
				embed = discord.Embed(
					title="➕ Song Added to Queue",
					description=f"**[{song.title}]({song.webpage_url})**",
					color=discord.Color.blue()
				)
				embed.add_field(name="Duration", value=song.duration_str, inline=True)
				embed.add_field(name="Position", value=f"#{position}", inline=True)
				embed.add_field(name="Added by", value=song.requester.mention, inline=True)
				if song.thumbnail:
					embed.set_thumbnail(url=song.thumbnail)
				try:
					await channel.send(embed=embed)
				except discord.Forbidden:
					pass

	def stop(self):
		"""Stop playback and clear queue."""
		self.queue.clear()
		self.current = None
		self.loop = False
		if self.voice_client and self.voice_client.is_playing():
			self.voice_client.stop()

	def save_queue(self):
		"""Save the current queue to persistent storage."""
		guild_id = str(self.guild.id)
		bot.data["music"].setdefault(guild_id, {})
		
		# Save current song + queue
		songs_to_save = []
		if self.current:
			songs_to_save.append({
				"title": self.current.title,
				"duration": self.current.duration,
				"thumbnail": self.current.thumbnail,
				"webpage_url": self.current.webpage_url,
				"requester_id": self.current.requester.id
			})
		for song in self.queue:
			songs_to_save.append({
				"title": song.title,
				"duration": song.duration,
				"thumbnail": song.thumbnail,
				"webpage_url": song.webpage_url,
				"requester_id": song.requester.id
			})
		
		bot.data["music"][guild_id]["saved_queue"] = songs_to_save
		bot.data["music"][guild_id]["saved_volume"] = self._linear_volume
		# Note: save_data() should be called after this (async)

	def has_saved_queue(self) -> bool:
		"""Check if there's a saved queue to restore."""
		guild_id = str(self.guild.id)
		saved = bot.data["music"].get(guild_id, {}).get("saved_queue", [])
		return len(saved) > 0

	def get_saved_queue_count(self) -> int:
		"""Get number of songs in saved queue."""
		guild_id = str(self.guild.id)
		return len(bot.data["music"].get(guild_id, {}).get("saved_queue", []))

	def clear_saved_queue(self):
		"""Clear the saved queue."""
		guild_id = str(self.guild.id)
		if guild_id in bot.data["music"]:
			bot.data["music"][guild_id]["saved_queue"] = []


# Store music players per guild
music_players: dict[int, MusicPlayer] = {}


def get_music_player(guild: discord.Guild) -> MusicPlayer:
	"""Get or create a music player for a guild."""
	if guild.id not in music_players:
		music_players[guild.id] = MusicPlayer(guild)
	return music_players[guild.id]


def can_control_music(member: discord.Member, player: MusicPlayer) -> bool:
	"""Check if a member can control music playback."""
	# Admins and mods can always control
	if member.guild_permissions.administrator:
		return True
	if member.guild_permissions.manage_guild:
		return True
	if member.guild_permissions.manage_channels:
		return True
	# The DJ (person who summoned the bot) can control
	if player.dj == member.id:
		return True
	# If no DJ set, allow anyone
	if player.dj is None:
		return True
	return False


async def extract_song_info(url: str, requester: discord.Member) -> Optional[Song]:
	"""Extract song information from a URL using yt-dlp."""
	try:
		import yt_dlp
		with yt_dlp.YoutubeDL(YTDL_OPTIONS) as ydl:
			info = await asyncio.get_event_loop().run_in_executor(
				None, lambda: ydl.extract_info(url, download=False)
			)
			if info:
				return Song(
					source_url=info.get("url", ""),
					title=info.get("title", "Unknown"),
					duration=info.get("duration", 0),
					thumbnail=info.get("thumbnail", ""),
					webpage_url=info.get("webpage_url", url),
					requester=requester
				)
	except Exception as e:
		logger.error("Failed to extract song info from %s: %s", url, e)
	return None


def is_valid_music_url(url: str) -> bool:
	"""Check if URL is a valid YouTube or Spotify link."""
	return bool(YOUTUBE_REGEX.match(url) or SPOTIFY_REGEX.match(url))


# Music prefix command
@bot.command(name="play")
async def play_prefix(ctx: commands.Context, *, url: str = None):
	"""Play a song from YouTube or Spotify. Usage: !play <YouTube/Spotify URL>"""
	if url is None:
		await ctx.send("Please provide a YouTube or Spotify URL. Usage: `!play <URL>`")
		return

	if not is_valid_music_url(url):
		await ctx.send("❌ Invalid URL! Only **YouTube** and **Spotify** links are accepted.")
		return

	if not ctx.author.voice or not ctx.author.voice.channel:
		await ctx.send("❌ You must be in a voice channel to use this command.")
		return

	player = get_music_player(ctx.guild)

	# Join voice channel if not connected
	if not player.voice_client or not player.voice_client.is_connected():
		try:
			player.voice_client = await ctx.author.voice.channel.connect()
			player.dj = ctx.author.id  # Set DJ to whoever summoned the bot
		except Exception as e:
			await ctx.send(f"❌ Failed to join voice channel: {e}")
			return

	# Extract song info
	async with ctx.typing():
		song = await extract_song_info(url, ctx.author)
		if not song:
			await ctx.send("❌ Failed to extract song information. Please check the URL.")
			return

		# Add to queue
		player.queue.append(song)
		position = len(player.queue)

		# Log song added
		await player._log_song_added(song, position)

		if player.voice_client.is_playing() or player.current:
			await ctx.send(f"✅ Added to queue at position #{position}: **{song.title}** ({song.duration_str})")
		else:
			await ctx.send(f"🎵 Now playing: **{song.title}** ({song.duration_str})")
			await player.play_next()


# Music slash commands
@bot.tree.command(name="play", description="Play a song (YouTube/Spotify URLs only)")
@app_commands.describe(url="YouTube or Spotify URL")
async def play_slash(interaction: discord.Interaction, url: str):
	if not is_valid_music_url(url):
		await interaction.response.send_message("❌ Invalid URL! Only **YouTube** and **Spotify** links are accepted.", ephemeral=True)
		return

	if not interaction.user.voice or not interaction.user.voice.channel:
		await interaction.response.send_message("❌ You must be in a voice channel to use this command.", ephemeral=True)
		return

	player = get_music_player(interaction.guild)
	needs_connect = not player.voice_client or not player.voice_client.is_connected()

	# Check for saved queue if we need to connect
	if needs_connect and player.get_saved_queue_count() > 0:
		saved_count = player.get_saved_queue_count()
		view = QueueChoiceView(saved_count)
		await interaction.response.send_message(
			f"📋 Found **{saved_count}** songs from a previous session!\n\n"
			f"**1️⃣ Resume Queue** - Restore saved songs + add your new song\n"
			f"**2️⃣ Start Fresh** - Clear saved songs and just play your song",
			view=view
		)
		await view.wait()

		if view.choice == "timeout":
			await interaction.edit_original_response(content="⏱️ Timed out. Use `/play` again.", view=None)
			return

		# Connect to voice
		try:
			player.voice_client = await interaction.user.voice.channel.connect()
			player.dj = interaction.user.id
		except Exception as e:
			await interaction.edit_original_response(content=f"❌ Failed to join voice channel: {e}", view=None)
			return

		if view.choice == "resume":
			# Restore the queue first
			guild_id = str(interaction.guild.id)
			saved_data = bot.data["music"].get(guild_id, {})
			saved_queue = saved_data.get("saved_queue", [])
			saved_volume = saved_data.get("saved_volume", 0.5)
			player._linear_volume = saved_volume

			for song_data in saved_queue:
				song = Song(
					source_url="",
					title=song_data["title"],
					duration=song_data.get("duration", 0),
					thumbnail=song_data.get("thumbnail", ""),
					webpage_url=song_data["webpage_url"],
					requester=interaction.user
				)
				player.queue.append(song)

		player.clear_saved_queue()
		await save_data()

		# Now add the new song
		new_song = await extract_song_info(url, interaction.user)
		if not new_song:
			await interaction.edit_original_response(content="❌ Failed to extract song information.", view=None)
			return

		player.queue.append(new_song)
		position = len(player.queue)
		await player._log_song_added(new_song, position)

		if view.choice == "resume":
			await interaction.edit_original_response(
				content=f"✅ Restored **{saved_count}** songs + added **{new_song.title}** at #{position}\n🎵 Starting playback...",
				view=None
			)
		else:
			await interaction.edit_original_response(
				content=f"🎵 Now playing: **{new_song.title}** ({new_song.duration_str})",
				view=None
			)

		if not player.voice_client.is_playing() and not player.current:
			await player.play_next()
		return

	# Normal flow - no saved queue or already connected
	await interaction.response.defer()

	if needs_connect:
		try:
			player.voice_client = await interaction.user.voice.channel.connect()
			player.dj = interaction.user.id
		except Exception as e:
			await interaction.followup.send(f"❌ Failed to join voice channel: {e}")
			return

	song = await extract_song_info(url, interaction.user)
	if not song:
		await interaction.followup.send("❌ Failed to extract song information. Please check the URL.")
		return

	player.queue.append(song)
	position = len(player.queue)
	await player._log_song_added(song, position)

	if player.voice_client.is_playing() or player.current:
		await interaction.followup.send(f"✅ Added to queue at position #{position}: **{song.title}** ({song.duration_str})")
	else:
		await interaction.followup.send(f"🎵 Now playing: **{song.title}** ({song.duration_str})")
		await player.play_next()


@bot.tree.command(name="skip", description="Skip the current song")
async def skip_slash(interaction: discord.Interaction):
	player = get_music_player(interaction.guild)

	if not can_control_music(interaction.user, player):
		await interaction.response.send_message("❌ Only the DJ or moderators can skip songs.", ephemeral=True)
		return

	if not player.voice_client or not player.voice_client.is_connected():
		await interaction.response.send_message("❌ Not connected to a voice channel.", ephemeral=True)
		return

	if not player.current:
		await interaction.response.send_message("❌ Nothing is currently playing.", ephemeral=True)
		return

	skipped_title = player.current.title
	player.voice_client.stop()  # This triggers play_next via the after callback
	await interaction.response.send_message(f"⏭️ Skipped: **{skipped_title}**")


@bot.tree.command(name="stop", description="Stop playback and clear the queue")
async def stop_slash(interaction: discord.Interaction):
	player = get_music_player(interaction.guild)

	if not can_control_music(interaction.user, player):
		await interaction.response.send_message("❌ Only the DJ or moderators can stop playback.", ephemeral=True)
		return

	if not player.voice_client or not player.voice_client.is_connected():
		await interaction.response.send_message("❌ Not connected to a voice channel.", ephemeral=True)
		return

	player.stop()
	await interaction.response.send_message("⏹️ Stopped playback and cleared the queue.")


@bot.tree.command(name="pause", description="Pause the current song")
async def pause_slash(interaction: discord.Interaction):
	player = get_music_player(interaction.guild)

	if not can_control_music(interaction.user, player):
		await interaction.response.send_message("❌ Only the DJ or moderators can pause playback.", ephemeral=True)
		return

	if not player.voice_client or not player.voice_client.is_playing():
		await interaction.response.send_message("❌ Nothing is currently playing.", ephemeral=True)
		return

	player.voice_client.pause()
	await interaction.response.send_message("⏸️ Paused playback.")


@bot.tree.command(name="resume", description="Resume paused playback")
async def resume_slash(interaction: discord.Interaction):
	player = get_music_player(interaction.guild)

	if not can_control_music(interaction.user, player):
		await interaction.response.send_message("❌ Only the DJ or moderators can resume playback.", ephemeral=True)
		return

	if not player.voice_client or not player.voice_client.is_paused():
		await interaction.response.send_message("❌ Playback is not paused.", ephemeral=True)
		return

	player.voice_client.resume()
	await interaction.response.send_message("▶️ Resumed playback.")


@bot.tree.command(name="queue", description="View the current music queue")
async def queue_slash(interaction: discord.Interaction):
	player = get_music_player(interaction.guild)

	embed = discord.Embed(title="🎵 Music Queue", color=discord.Color.purple())

	if player.current:
		embed.add_field(
			name="Now Playing",
			value=f"**[{player.current.title}]({player.current.webpage_url})** ({player.current.duration_str})\nRequested by {player.current.requester.mention}",
			inline=False
		)

	if player.queue:
		queue_text = ""
		for i, song in enumerate(player.queue[:10], 1):
			queue_text += f"`{i}.` **{song.title}** ({song.duration_str}) - {song.requester.mention}\n"
		if len(player.queue) > 10:
			queue_text += f"\n*...and {len(player.queue) - 10} more songs*"
		embed.add_field(name="Up Next", value=queue_text, inline=False)
	else:
		if not player.current:
			embed.description = "The queue is empty. Use `/play` to add songs!"

	embed.set_footer(text=f"Loop: {'On' if player.loop else 'Off'} | Volume: {int(player._linear_volume * 100)}%")
	await interaction.response.send_message(embed=embed)


@bot.tree.command(name="volume", description="Set playback volume (0-100)")
@app_commands.describe(level="Volume level from 0 to 100")
async def volume_slash(interaction: discord.Interaction, level: app_commands.Range[int, 0, 100]):
	player = get_music_player(interaction.guild)

	if not can_control_music(interaction.user, player):
		await interaction.response.send_message("❌ Only the DJ or moderators can change volume.", ephemeral=True)
		return

	player.volume = level / 100
	if player.voice_client and player.voice_client.source:
		player.voice_client.source.volume = player.volume

	await interaction.response.send_message(f"🔊 Volume set to **{level}%**")


@bot.tree.command(name="loop", description="Toggle loop mode for the current song")
async def loop_slash(interaction: discord.Interaction):
	player = get_music_player(interaction.guild)

	if not can_control_music(interaction.user, player):
		await interaction.response.send_message("❌ Only the DJ or moderators can toggle loop.", ephemeral=True)
		return

	player.loop = not player.loop
	status = "enabled" if player.loop else "disabled"
	await interaction.response.send_message(f"🔁 Loop mode **{status}**")


@bot.tree.command(name="join", description="Make the bot join your voice channel")
async def join_slash(interaction: discord.Interaction):
	if not interaction.user.voice or not interaction.user.voice.channel:
		await interaction.response.send_message("❌ You must be in a voice channel.", ephemeral=True)
		return

	player = get_music_player(interaction.guild)

	if player.voice_client and player.voice_client.is_connected():
		if player.voice_client.channel == interaction.user.voice.channel:
			await interaction.response.send_message("✅ Already in your voice channel!", ephemeral=True)
			return
		await player.voice_client.move_to(interaction.user.voice.channel)
		await interaction.response.send_message(f"🔊 Moved to **{interaction.user.voice.channel.name}**")
	else:
		# Check for saved queue before connecting
		saved_count = player.get_saved_queue_count()
		if saved_count > 0:
			view = QueueChoiceView(saved_count)
			await interaction.response.send_message(
				f"📋 Found **{saved_count}** songs from a previous session!\n\n"
				f"**1️⃣ Resume Queue** - Restore the saved songs\n"
				f"**2️⃣ Start Fresh** - Clear saved songs and start new",
				view=view
			)
			await view.wait()

			if view.choice == "timeout":
				await interaction.edit_original_response(content="⏱️ Timed out. Use `/join` again to choose.", view=None)
				return

			# Connect to voice
			player.voice_client = await interaction.user.voice.channel.connect()
			player.dj = interaction.user.id

			if view.choice == "resume":
				# Restore the queue
				guild_id = str(interaction.guild.id)
				saved_data = bot.data["music"].get(guild_id, {})
				saved_queue = saved_data.get("saved_queue", [])
				saved_volume = saved_data.get("saved_volume", 0.5)
				player._linear_volume = saved_volume

				for song_data in saved_queue:
					song = Song(
						source_url="",
						title=song_data["title"],
						duration=song_data.get("duration", 0),
						thumbnail=song_data.get("thumbnail", ""),
						webpage_url=song_data["webpage_url"],
						requester=interaction.user
					)
					player.queue.append(song)

				player.clear_saved_queue()
				await save_data()
				await interaction.edit_original_response(
					content=f"🔊 Joined **{interaction.user.voice.channel.name}**\n✅ Restored **{saved_count}** songs! Use `/play` to start or add more.",
					view=None
				)
				# Start playing
				if not player.voice_client.is_playing() and not player.current:
					await player.play_next()
			else:
				# Start fresh
				player.clear_saved_queue()
				await save_data()
				await interaction.edit_original_response(
					content=f"🔊 Joined **{interaction.user.voice.channel.name}**\n🆕 Starting fresh! Use `/play` to add songs.",
					view=None
				)
		else:
			player.voice_client = await interaction.user.voice.channel.connect()
			player.dj = interaction.user.id
			await interaction.response.send_message(f"🔊 Joined **{interaction.user.voice.channel.name}**")


@bot.tree.command(name="leave", description="Make the bot leave the voice channel")
async def leave_slash(interaction: discord.Interaction):
	player = get_music_player(interaction.guild)

	if not can_control_music(interaction.user, player):
		await interaction.response.send_message("❌ Only the DJ or moderators can disconnect the bot.", ephemeral=True)
		return

	if not player.voice_client or not player.voice_client.is_connected():
		await interaction.response.send_message("❌ Not connected to a voice channel.", ephemeral=True)
		return

	channel_name = player.voice_client.channel.name
	
	# Save queue before leaving
	has_songs = player.current or player.queue
	if has_songs:
		player.save_queue()
		await save_data()
	
	player.stop()
	await player.voice_client.disconnect()
	player.voice_client = None
	player.dj = None  # Clear DJ when leaving

	if has_songs:
		await interaction.response.send_message(f"👋 Left **{channel_name}**\n💾 Queue saved! You'll be asked to restore it when using `/join` or `/play` next time.")
	else:
		await interaction.response.send_message(f"👋 Left **{channel_name}**")


@bot.tree.command(name="shuffle", description="Shuffle the queue")
async def shuffle_slash(interaction: discord.Interaction):
	player = get_music_player(interaction.guild)

	if not can_control_music(interaction.user, player):
		await interaction.response.send_message("❌ Only the DJ or moderators can shuffle the queue.", ephemeral=True)
		return

	if len(player.queue) < 2:
		await interaction.response.send_message("❌ Not enough songs in queue to shuffle.", ephemeral=True)
		return

	random.shuffle(player.queue)
	await interaction.response.send_message(f"🔀 Shuffled **{len(player.queue)}** songs in the queue!")


@bot.tree.command(name="clearqueue", description="Clear all songs from the queue")
async def clearqueue_slash(interaction: discord.Interaction):
	player = get_music_player(interaction.guild)

	if not can_control_music(interaction.user, player):
		await interaction.response.send_message("❌ Only the DJ or moderators can clear the queue.", ephemeral=True)
		return

	count = len(player.queue)
	player.queue.clear()
	await interaction.response.send_message(f"🗑️ Cleared **{count}** songs from the queue.")


@bot.tree.command(name="remove", description="Remove a song from the queue by position")
@app_commands.describe(position="Queue position (1 = first song in queue)")
async def remove_slash(interaction: discord.Interaction, position: app_commands.Range[int, 1, 100]):
	player = get_music_player(interaction.guild)

	if not can_control_music(interaction.user, player):
		await interaction.response.send_message("❌ Only the DJ or moderators can remove songs.", ephemeral=True)
		return

	if position > len(player.queue):
		await interaction.response.send_message(f"❌ Invalid position. Queue only has **{len(player.queue)}** songs.", ephemeral=True)
		return

	removed = player.queue.pop(position - 1)
	await interaction.response.send_message(f"🗑️ Removed **{removed.title}** from position #{position}")


@bot.tree.command(name="setmusicchannel", description="Set the music log channel (admin only)")
@app_commands.describe(channel="The channel for music logs and queue updates")
@app_commands.checks.has_permissions(administrator=True)
async def setmusicchannel_slash(interaction: discord.Interaction, channel: discord.TextChannel):
	guild_id = str(interaction.guild.id)
	bot.data["music"].setdefault(guild_id, {})
	bot.data["music"][guild_id]["log_channel"] = channel.id
	await save_data()

	# Set channel permissions: only admin and bot can send messages
	overwrites = {
		interaction.guild.default_role: discord.PermissionOverwrite(
			send_messages=False,
			add_reactions=True,
			read_messages=True
		),
		interaction.guild.me: discord.PermissionOverwrite(
			send_messages=True,
			embed_links=True,
			attach_files=True
		),
	}

	try:
		await channel.edit(overwrites=overwrites)
		await interaction.response.send_message(
			f"✅ Music log channel set to {channel.mention}\n"
			f"Permissions configured: Only admins and the bot can write there.",
			ephemeral=True
		)
	except discord.Forbidden:
		await interaction.response.send_message(
			f"✅ Music log channel set to {channel.mention}\n"
			f"⚠️ Could not update channel permissions. Please configure them manually.",
			ephemeral=True
		)


@bot.tree.command(name="transferdj", description="Transfer DJ control to another user")
@app_commands.describe(member="The user to transfer DJ to")
async def transferdj_slash(interaction: discord.Interaction, member: discord.Member):
	player = get_music_player(interaction.guild)

	# Only current DJ or admins can transfer
	if not can_control_music(interaction.user, player):
		await interaction.response.send_message("❌ Only the current DJ or moderators can transfer DJ.", ephemeral=True)
		return

	if member.bot:
		await interaction.response.send_message("❌ Cannot transfer DJ to a bot.", ephemeral=True)
		return

	if member.id == interaction.user.id:
		await interaction.response.send_message("❌ You cannot transfer DJ to yourself.", ephemeral=True)
		return

	player.dj = member.id
	await interaction.response.send_message(f"🎧 {member.mention} is now the DJ!")


@bot.tree.command(name="musicstatus", description="Show music system status")
async def musicstatus_slash(interaction: discord.Interaction):
	player = get_music_player(interaction.guild)
	guild_id = str(interaction.guild.id)
	music_data = bot.data["music"].get(guild_id, {})
	log_channel_id = music_data.get("log_channel")

	embed = discord.Embed(title="🎵 Music Status", color=discord.Color.blurple())

	# Connection status
	if player.voice_client and player.voice_client.is_connected():
		embed.add_field(name="Connected to", value=player.voice_client.channel.mention, inline=True)
	else:
		embed.add_field(name="Connected to", value="Not connected", inline=True)

	# Now playing
	if player.current:
		embed.add_field(name="Now Playing", value=player.current.title[:50], inline=True)
	else:
		embed.add_field(name="Now Playing", value="Nothing", inline=True)

	# Queue
	embed.add_field(name="Queue", value=f"{len(player.queue)} songs", inline=True)

	# Settings
	embed.add_field(name="Volume", value=f"{int(player._linear_volume * 100)}%", inline=True)
	embed.add_field(name="Loop", value="On" if player.loop else "Off", inline=True)

	# DJ
	if player.dj:
		dj_member = interaction.guild.get_member(player.dj)
		embed.add_field(name="DJ", value=dj_member.mention if dj_member else "Unknown", inline=True)
	else:
		embed.add_field(name="DJ", value="None", inline=True)

	# Log channel
	if log_channel_id:
		log_channel = interaction.guild.get_channel(log_channel_id)
		embed.add_field(name="Log Channel", value=log_channel.mention if log_channel else "Not found", inline=True)
	else:
		embed.add_field(name="Log Channel", value="Not set", inline=True)

	# Saved queue
	saved_count = player.get_saved_queue_count()
	if saved_count > 0:
		embed.add_field(name="Saved Queue", value=f"{saved_count} songs (offered on next `/join` or `/play`)", inline=True)

	await interaction.response.send_message(embed=embed)


# Global slash command error handler
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
	logger.exception(
		"Slash command error | command=%s user=%s guild=%s channel=%s",
		interaction.command.name if interaction.command else "unknown",
		interaction.user,
		getattr(interaction.guild, "id", None),
		getattr(interaction.channel, "id", None),
		exc_info=error,
	)

	if isinstance(error, app_commands.MissingPermissions):
		message = "You need server permissions to use this command."
		if interaction.response.is_done():
			await interaction.followup.send(message, ephemeral=True)
		else:
			await interaction.response.send_message(message, ephemeral=True)
		return
	if interaction.response.is_done():
		await interaction.followup.send("Slash command failed. Check permissions and try again.", ephemeral=True)
	else:
		await interaction.response.send_message("Slash command failed. Check permissions and try again.", ephemeral=True)


if not TOKEN:
	raise RuntimeError("Set DISCORD_TOKEN in .env before running the bot.")

bot.run(TOKEN)
