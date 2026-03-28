"""
Main Discord bot entry point.
Loads all cogs and handles startup/shutdown.
"""
import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

import discord
from discord import app_commands
from discord.ext import commands

from core.helpers import configure_logging, load_data, save_data, mark_dirty, is_dirty, logger


# ─────────────────────────────────────────────────────────────────────────────
# Environment Loading
# ─────────────────────────────────────────────────────────────────────────────
def load_env_file(env_file: str = ".env") -> None:
	"""Load environment variables from .env file."""
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


# ─────────────────────────────────────────────────────────────────────────────
# Bot Setup
# ─────────────────────────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.presences = True
intents.voice_states = True  # Required for voice channel operations

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)
bot.started_at = datetime.now(timezone.utc)
bot.data = load_data()  # Load data early so cogs can access it
bot.mark_dirty = mark_dirty  # Attach to bot so cogs can use self.bot.mark_dirty()


# ─────────────────────────────────────────────────────────────────────────────
# Cog Loading
# ─────────────────────────────────────────────────────────────────────────────
COGS = [
	"cogs.dev",  # Load dev cog first for hot-reload support
	"cogs.utility",
	"cogs.profile",
	"cogs.xp",
	"cogs.economy",
	"cogs.welcome",
	"cogs.tickets",
	"cogs.music",
	"cogs.events",
	"cogs.modlog",
	"cogs.moderation",
	"cogs.reactionroles",
	"cogs.starboard",
	"cogs.afk",
	"cogs.giveaway",
	"cogs.suggestions",
	"cogs.apis",
	"cogs.birthday",
	"cogs.scheduler",
]

AUTOSAVE_INTERVAL = 60  # Save every 60 seconds if dirty


async def load_extensions():
	"""Load all cog extensions with detailed error tracking."""
	import traceback
	
	loaded = []
	failed = []
	
	logger.info("═" * 50)
	logger.info("LOADING COGS...")
	logger.info("═" * 50)
	
	for cog in COGS:
		try:
			await bot.load_extension(cog)
			loaded.append(cog)
			logger.info("✅ Loaded: %s", cog)
		except Exception as e:
			failed.append((cog, str(e)))
			logger.error("❌ FAILED: %s", cog)
			logger.error("   Error: %s", e)
			# Print full traceback for debugging
			logger.error("   Traceback:\n%s", traceback.format_exc())
			
			# Track in dev cog if loaded
			if "cogs.dev" in [c for c, _ in failed]:
				continue  # Dev cog itself failed
			dev_cog = bot.get_cog("Dev")
			if dev_cog:
				dev_cog.cog_errors[cog] = traceback.format_exc()
	
	logger.info("═" * 50)
	logger.info("COG LOADING COMPLETE")
	logger.info("  Loaded: %d | Failed: %d", len(loaded), len(failed))
	if failed:
		logger.warning("  Failed cogs: %s", [c for c, _ in failed])
		logger.info("  Use !reload <cog> to retry after fixing")
	logger.info("═" * 50)


# ─────────────────────────────────────────────────────────────────────────────
# Events
# ─────────────────────────────────────────────────────────────────────────────
@bot.event
async def on_ready():
	"""Called when the bot is ready."""
	logger.info("Data already loaded from bot_data.json")

	try:
		synced_global = await bot.tree.sync()
		logger.info("Synced %d global slash commands", len(synced_global))

		# Also sync per guild so newly added commands appear immediately.
		for guild in bot.guilds:
			synced_guild = await bot.tree.sync(guild=guild)
			logger.info("Synced %d guild slash commands to %s (%s)", len(synced_guild), guild.name, guild.id)
	except Exception as e:
		logger.error("Failed to sync commands: %s", e)

	logger.info("Bot is ready! Logged in as %s (ID: %s)", bot.user.name, bot.user.id)
	logger.info("Connected to %d guilds", len(bot.guilds))
	
	# Set activity
	activity = discord.Activity(type=discord.ActivityType.watching, name="you level up!")
	await bot.change_presence(activity=activity)
	
	# Start autosave task
	if not hasattr(bot, '_autosave_task') or bot._autosave_task.done():
		bot._autosave_task = asyncio.create_task(autosave_loop())


async def autosave_loop():
	"""Periodically save data if it has changed."""
	await bot.wait_until_ready()
	while not bot.is_closed():
		await asyncio.sleep(AUTOSAVE_INTERVAL)
		if is_dirty():
			await save_data(bot, force=True)
			logger.debug("Autosaved data")


@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
	"""Handle prefix command errors."""
	if isinstance(error, commands.CommandNotFound):
		return
	if isinstance(error, commands.MissingPermissions):
		await ctx.send("You don't have permission to use this command.")
		return
	if isinstance(error, commands.MissingRequiredArgument):
		await ctx.send(f"Missing required argument: {error.param.name}")
		return
	if isinstance(error, commands.BadArgument):
		await ctx.send(f"Invalid argument: {error}")
		return
	
	logger.exception("Command error in %s: %s", ctx.command, error)
	await ctx.send("An error occurred while executing the command.")


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
	"""Handle slash command errors."""
	logger.exception(
		"Slash command error | command=%s user=%s guild=%s channel=%s",
		interaction.command.name if interaction.command else "unknown",
		interaction.user,
		getattr(interaction.guild, "id", None),
		getattr(interaction.channel, "id", None),
		exc_info=error,
	)
	
	# Forward to Dev cog error monitor
	dev_cog = bot.get_cog("Dev")
	if dev_cog and hasattr(dev_cog, "record_error"):
		context = f"Guild: {getattr(interaction.guild, 'id', 'DM')} | User: {interaction.user} | Channel: {getattr(interaction.channel, 'id', 'N/A')}"
		dev_cog.record_error("slash", interaction.command.name if interaction.command else "unknown", error, context)

	if isinstance(error, app_commands.MissingPermissions):
		message = "You need server permissions to use this command."
	else:
		message = "Slash command failed. Check permissions and try again."

	try:
		if interaction.response.is_done():
			await interaction.followup.send(message, ephemeral=True)
		else:
			await interaction.response.send_message(message, ephemeral=True)
	except Exception:
		pass  # Interaction may have expired


# ─────────────────────────────────────────────────────────────────────────────
# Main Entry Point
# ─────────────────────────────────────────────────────────────────────────────
async def main():
	"""Main entry point for the bot."""
	if not TOKEN:
		raise RuntimeError("Set DISCORD_TOKEN in .env before running the bot.")
	
	async with bot:
		await load_extensions()
		try:
			await bot.start(TOKEN)
		finally:
			# Save data before shutdown
			logger.info("Shutting down - saving data...")
			await save_data(bot, force=True)


if __name__ == "__main__":
	asyncio.run(main())
