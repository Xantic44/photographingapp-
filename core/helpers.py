"""
Shared helper functions and utilities for the bot.
"""
import asyncio
import json
import logging
import os
import random
import time
from datetime import datetime, timezone
from pathlib import Path

import discord

# ─────────────────────────────────────────────────────────────────────────────
# Global state
# ─────────────────────────────────────────────────────────────────────────────
DATA_FILE = Path("bot_data.json")
LOG_FILE = Path("bot_debug.log")
SAVE_LOCK = asyncio.Lock()
xp_cooldown: dict[tuple[int, int], float] = {}
started_at = datetime.now(timezone.utc)

# Dirty flag for optimized saving - only save when data changes
_data_dirty = False

XP_COOLDOWN_SECONDS = 60

# Default templates for user data
ECONOMY_TEMPLATE = {"funPoints": 100, "last_daily": 0, "last_work": 0}
XP_TEMPLATE = {"xp": 0, "level": 1, "total_xp": 0}

# Cooldown constants (in seconds)
DAILY_COOLDOWN = 86400  # 24 hours
WORK_COOLDOWN = 3600    # 1 hour


# ─────────────────────────────────────────────────────────────────────────────
# Visual constants & cute messages
# ─────────────────────────────────────────────────────────────────────────────
class Colors:
    """Consistent color palette for embeds."""
    # Core colors
    SUCCESS = 0x57F287      # Green
    ERROR = 0xED4245        # Red
    WARNING = 0xFEE75C      # Yellow
    INFO = 0x5865F2         # Blurple
    
    # Feature-specific colors
    ECONOMY = 0xF1C40F      # Gold
    XP = 0x9B59B6           # Purple
    MUSIC = 0x1DB954        # Spotify green
    TICKET = 0xE91E63       # Pink
    PROFILE = 0x3498DB      # Blue
    STARBOARD = 0xFFD700    # Gold
    REACTION_ROLES = 0xE91E63  # Pink
    AFK = 0x95A5A6          # Gray
    GIVEAWAY = 0xFF69B4     # Hot pink
    GIVEAWAY_ENDED = 0x808080  # Gray
    SUGGESTION = 0x3498DB   # Blue
    APPROVED = 0x2ECC71     # Green
    DENIED = 0xE74C3C       # Red
    IMPLEMENTED = 0x9B59B6  # Purple
    MODLOG = 0xFF6B35       # Orange


# Cute random message pools
GREETINGS = [
    "Hewwo {name}! ✨", "Hiya {name}~! 💫", "Hey there {name}! 🌟",
    "Yo {name}! What's up? 👋", "Hi hi {name}~! 💕", "Ohai {name}! 🎀",
    "Greetings {name}! ⭐", "{name}! Nice to see you! 🌸",
]

DAILY_MESSAGES = [
    "Here's your daily treat! 🍪", "Your daily goodies await~! ✨",
    "Rise and grind! 💪", "Another day, another bag! 💰",
    "The bot gods smile upon you! 🌟", "Ka-ching! Daily claimed! 🎰",
]

WORK_MESSAGES = [
    ("👨‍💻", "You coded for 8 hours straight!"),
    ("🍕", "You delivered pizzas around town!"),
    ("📦", "You sorted packages at the warehouse!"),
    ("🎮", "You streamed games for your fans!"),
    ("☕", "You worked a shift at the café!"),
    ("🎨", "You sold your art commissions!"),
    ("📚", "You tutored some students!"),
    ("🛠️", "You fixed some neighbor's stuff!"),
    ("🎵", "You busked in the town square!"),
    ("🌾", "You helped on a farm!"),
]

WIN_CELEBRATIONS = [
    "🎉 WINNER WINNER!", "💰 CHA-CHING!", "🌟 LUCKY YOU!",
    "✨ JACKPOT VIBES!", "🎊 BIG W!", "💫 BLESSED RNG!",
]

LOSS_CONDOLENCES = [
    "😢 Better luck next time...", "💸 Oof, that hurts...",
    "😅 The house always wins...", "🥲 We go again...",
    "😔 RNG wasn't on your side...", "💔 So close yet so far...",
]

LEVEL_UP_MESSAGES = [
    "YOU LEVELED UP! 🎉", "DING! Level up! ⬆️", "POWER UP! 💪",
    "NEW LEVEL UNLOCKED! 🔓", "LEVEL UP, GAMER! 🎮", "EVOLUTION! ✨",
]


def cute_greeting(name: str) -> str:
    """Get a random cute greeting."""
    return random.choice(GREETINGS).format(name=name)


def cute_daily() -> str:
    """Get a random daily claim message."""
    return random.choice(DAILY_MESSAGES)


def cute_work() -> tuple[str, str]:
    """Get a random work scenario (emoji, message)."""
    return random.choice(WORK_MESSAGES)


def cute_win() -> str:
    """Get a random win celebration."""
    return random.choice(WIN_CELEBRATIONS)


def cute_loss() -> str:
    """Get a random loss condolence."""
    return random.choice(LOSS_CONDOLENCES)


def cute_levelup() -> str:
    """Get a random level up message."""
    return random.choice(LEVEL_UP_MESSAGES)


# ─────────────────────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────────────────────
def configure_logging() -> logging.Logger:
	"""Configure and return the bot logger."""
	debug_enabled = os.getenv("BOT_DEBUG", "1").lower() in {"1", "true", "yes", "on"}
	level = logging.DEBUG if debug_enabled else logging.INFO

	logger = logging.getLogger("discord_bot")
	logger.setLevel(level)
	logger.handlers.clear()
	formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

	stream_handler = logging.StreamHandler()
	stream_handler.setLevel(level)
	stream_handler.setFormatter(formatter)

	logger.addHandler(stream_handler)
	try:
		file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
		file_handler.setLevel(level)
		file_handler.setFormatter(formatter)
		logger.addHandler(file_handler)
	except PermissionError:
		# Another running process may hold an exclusive lock on the log file (common on Windows).
		logger.warning("Could not open %s for logging; continuing with console logging only.", LOG_FILE)

	logger.propagate = False
	
	# Enable discord.py voice/gateway debugging for live monitoring
	discord_voice_logger = logging.getLogger("discord.voice_client")
	discord_voice_logger.setLevel(logging.DEBUG)
	discord_voice_logger.addHandler(stream_handler)
	
	discord_gateway_logger = logging.getLogger("discord.gateway")
	discord_gateway_logger.setLevel(logging.DEBUG)
	discord_gateway_logger.addHandler(stream_handler)
	
	return logger


logger = configure_logging()


# ─────────────────────────────────────────────────────────────────────────────
# Data persistence
# ─────────────────────────────────────────────────────────────────────────────
def default_data() -> dict:
	"""Return default structure for bot data."""
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
	"""Load bot data from JSON file."""
	if not DATA_FILE.exists():
		return default_data()
	try:
		data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
		if isinstance(data, dict):
			return {**default_data(), **data}
	except json.JSONDecodeError:
		pass
	return default_data()


async def save_data(bot, force: bool = False) -> None:
	"""Save bot data to JSON file.
	
	Args:
		bot: The bot instance with data to save
		force: If True, save immediately. If False, only save if dirty.
	"""
	global _data_dirty
	if not force and not _data_dirty:
		return  # No changes to save
	
	async with SAVE_LOCK:
		DATA_FILE.write_text(json.dumps(bot.data, indent=2), encoding="utf-8")
		_data_dirty = False


def mark_dirty() -> None:
	"""Mark data as dirty so it will be saved on next autosave."""
	global _data_dirty
	_data_dirty = True


def is_dirty() -> bool:
	"""Check if data needs saving."""
	return _data_dirty


# ─────────────────────────────────────────────────────────────────────────────
# User data helpers
# ─────────────────────────────────────────────────────────────────────────────
def ensure_user_entry(store: dict, guild_id: int, user_id: int, template: dict) -> dict:
	"""Ensure a user entry exists in the given store with the provided template."""
	guild_key = str(guild_id)
	user_key = str(user_id)
	store.setdefault(guild_key, {})
	store[guild_key].setdefault(user_key, template.copy())
	return store[guild_key][user_key]


def get_economy_entry(data: dict, guild_id: int, user_id: int) -> dict:
	"""Get an economy entry with automatic coins->funPoints migration."""
	entry = ensure_user_entry(data, guild_id, user_id, ECONOMY_TEMPLATE)
	if "funPoints" not in entry:
		entry["funPoints"] = entry.pop("coins", 100)
	return entry


def get_xp_entry(data: dict, guild_id: int, user_id: int) -> dict:
	"""Get an XP entry for a user."""
	return ensure_user_entry(data, guild_id, user_id, XP_TEMPLATE)


def format_cooldown(remaining: int) -> str:
	"""Format remaining seconds as human-readable time."""
	if remaining >= 3600:
		hours = remaining // 3600
		minutes = (remaining % 3600) // 60
		return f"{hours}h {minutes}m"
	elif remaining >= 60:
		return f"{remaining // 60}m"
	return f"{remaining}s"


def xp_required_for_level(level: int) -> int:
	"""Calculate XP required for a given level."""
	return 100 + (level - 1) * 25


def create_progress_bar(current: int, total: int, length: int = 10) -> str:
	"""Create a visual progress bar."""
	if total <= 0:
		return "▓" * length
	filled = int((current / total) * length)
	empty = length - filled
	return "▓" * filled + "░" * empty


# ─────────────────────────────────────────────────────────────────────────────
# Activity formatting
# ─────────────────────────────────────────────────────────────────────────────
def format_activity_lines(member: discord.Member) -> str:
	"""Format a member's activities for display."""
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


# ─────────────────────────────────────────────────────────────────────────────
# Ticket helpers
# ─────────────────────────────────────────────────────────────────────────────
async def get_or_create_ticket_category(bot, guild: discord.Guild) -> discord.CategoryChannel:
	"""Get or create the tickets category for a guild."""
	ticket_config = bot.data["tickets"].setdefault(str(guild.id), {"category_id": None, "support_role_id": None, "counter": 0})
	category_id = ticket_config.get("category_id")
	if category_id:
		category = guild.get_channel(int(category_id))
		if isinstance(category, discord.CategoryChannel):
			return category

	category = await guild.create_category("Tickets")
	ticket_config["category_id"] = category.id
	await save_data(bot)
	return category


# ─────────────────────────────────────────────────────────────────────────────
# Mutual guilds
# ─────────────────────────────────────────────────────────────────────────────
async def get_mutual_guild_names(bot, user_id: int) -> list[str]:
	"""Get list of guild names shared with a user."""
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
