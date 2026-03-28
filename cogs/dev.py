"""
Dev Cog - Development tools for hot-reloading, debugging, and maintenance.
Owner-only commands for managing the bot live without restarts.
Includes real-time error monitoring and alerting.
"""
import asyncio
import sys
import traceback
from collections import deque
from datetime import datetime, timezone
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

from core.helpers import logger, Colors


# ═══════════════════════════════════════════════════════════════════════════
#                           ERROR RECORD
# ═══════════════════════════════════════════════════════════════════════════
class ErrorRecord:
	"""Stores information about an error that occurred."""
	
	def __init__(self, error_type: str, source: str, error: Exception, context: str = ""):
		self.timestamp = datetime.now(timezone.utc)
		self.error_type = error_type  # "command", "slash", "event", "voice", "task"
		self.source = source  # command name, event name, etc.
		self.error = error
		self.traceback = traceback.format_exception(type(error), error, error.__traceback__)
		self.context = context  # guild/channel/user info
	
	def short_str(self) -> str:
		"""Short summary of the error."""
		time_str = self.timestamp.strftime("%H:%M:%S")
		return f"`{time_str}` **{self.error_type}**/{self.source}: {type(self.error).__name__}"
	
	def full_str(self) -> str:
		"""Full error with traceback."""
		tb = "".join(self.traceback[-5:])  # Last 5 lines of traceback
		if len(tb) > 1500:
			tb = tb[-1500:]
		return f"**{self.error_type}** | {self.source}\n{self.context}\n```py\n{tb}\n```"


# ═══════════════════════════════════════════════════════════════════════════
#                              DEV COG
# ═══════════════════════════════════════════════════════════════════════════
class Dev(commands.Cog):
	"""Developer tools for managing the bot live."""
	
	def __init__(self, bot: commands.Bot):
		self.bot = bot
		self.cog_errors: dict[str, str] = {}  # Track failed cogs
		
		# Error monitoring
		self.error_log: deque[ErrorRecord] = deque(maxlen=50)  # Last 50 errors
		self.error_count = 0
		self.dm_alerts = True  # Send DM to owner on errors
		self.alert_cooldown: dict[str, datetime] = {}  # Prevent spam
		
		# Start tasks
		self.auto_reload_watch.start()
		self.error_summary_task.start()
	
	def cog_unload(self):
		self.auto_reload_watch.cancel()
		self.error_summary_task.cancel()
	
	async def cog_check(self, ctx: commands.Context) -> bool:
		"""Only bot owner can use these commands."""
		return await self.bot.is_owner(ctx.author)
	
	# ─────────────────────────────────────────────────────────────────────────
	#                           ERROR TRACKING
	# ─────────────────────────────────────────────────────────────────────────
	
	def record_error(self, error_type: str, source: str, error: Exception, context: str = ""):
		"""Record an error for monitoring."""
		record = ErrorRecord(error_type, source, error, context)
		self.error_log.append(record)
		self.error_count += 1
		logger.error("ERROR_MONITOR: [%s] %s - %s: %s", 
					 error_type, source, type(error).__name__, str(error)[:100])
		
		# Schedule DM alert (rate-limited)
		if self.dm_alerts:
			asyncio.create_task(self._send_error_alert(record))
	
	async def _send_error_alert(self, record: ErrorRecord):
		"""Send error alert to bot owner via DM."""
		# Rate limit: max 1 alert per error source per 60 seconds
		key = f"{record.error_type}:{record.source}"
		now = datetime.now(timezone.utc)
		
		if key in self.alert_cooldown:
			elapsed = (now - self.alert_cooldown[key]).total_seconds()
			if elapsed < 60:
				return
		
		self.alert_cooldown[key] = now
		
		try:
			app_info = await self.bot.application_info()
			owner = app_info.owner
			
			embed = discord.Embed(
				title="⚠️ Error Alert",
				description=record.full_str()[:2000],
				color=Colors.ERROR,
				timestamp=record.timestamp
			)
			embed.set_footer(text=f"Total errors: {self.error_count}")
			
			await owner.send(embed=embed)
		except Exception as e:
			logger.warning("Failed to send error alert DM: %s", e)
	
	# ─────────────────────────────────────────────────────────────────────────
	#                           ERROR LISTENERS
	# ─────────────────────────────────────────────────────────────────────────
	
	@commands.Cog.listener()
	async def on_command_error(self, ctx: commands.Context, error: commands.CommandError):
		"""Track prefix command errors."""
		# Ignore command not found
		if isinstance(error, commands.CommandNotFound):
			return
		
		context = f"Guild: {ctx.guild.id if ctx.guild else 'DM'} | User: {ctx.author}"
		self.record_error("command", ctx.command.name if ctx.command else "unknown", error, context)
	
	@commands.Cog.listener()
	async def on_error(self, event: str, *args, **kwargs):
		"""Track event errors."""
		error = sys.exc_info()[1]
		if error:
			self.record_error("event", event, error)
	
	# ─────────────────────────────────────────────────────────────────────────
	#                              TASKS
	# ─────────────────────────────────────────────────────────────────────────
	
	@tasks.loop(seconds=30)
	async def auto_reload_watch(self):
		"""Auto-retry loading failed cogs periodically."""
		if not self.cog_errors:
			return
		
		for cog_name in list(self.cog_errors.keys()):
			try:
				await self.bot.load_extension(cog_name)
				logger.info("Auto-reloaded previously failed cog: %s", cog_name)
				del self.cog_errors[cog_name]
			except Exception:
				pass  # Still failing, will try again next cycle
	
	@tasks.loop(minutes=5)
	async def error_summary_task(self):
		"""Periodic error summary (if errors occurred)."""
		# Count errors in last 5 minutes
		now = datetime.now(timezone.utc)
		recent = [e for e in self.error_log if (now - e.timestamp).total_seconds() < 300]
		
		if len(recent) >= 5:  # Alert if 5+ errors in 5 minutes
			logger.warning("ERROR_MONITOR: %d errors in the last 5 minutes!", len(recent))
	
	@auto_reload_watch.before_loop
	async def before_auto_reload(self):
		await self.bot.wait_until_ready()
	
	@error_summary_task.before_loop
	async def before_error_summary(self):
		await self.bot.wait_until_ready()
	
	@commands.command(name="reload", hidden=True)
	async def reload_cog(self, ctx: commands.Context, cog: str = None):
		"""Reload a cog or all cogs. Usage: !reload [cog_name]"""
		if cog is None:
			# Reload all cogs
			results = []
			for cog_name in list(self.bot.extensions.keys()):
				if cog_name == "cogs.dev":
					continue  # Skip reloading self
				try:
					await self.bot.reload_extension(cog_name)
					results.append(f"✅ {cog_name}")
				except Exception as e:
					results.append(f"❌ {cog_name}: {str(e)[:50]}")
			
			await ctx.send(f"**Reload Results:**\n" + "\n".join(results))
		else:
			# Reload specific cog
			cog_path = f"cogs.{cog}" if not cog.startswith("cogs.") else cog
			try:
				await self.bot.reload_extension(cog_path)
				await ctx.send(f"✅ Reloaded `{cog_path}`")
				
				# Remove from error tracking
				if cog_path in self.cog_errors:
					del self.cog_errors[cog_path]
			except commands.ExtensionNotLoaded:
				# Try loading instead
				try:
					await self.bot.load_extension(cog_path)
					await ctx.send(f"✅ Loaded `{cog_path}` (was not loaded)")
				except Exception as e:
					await ctx.send(f"❌ Failed to load `{cog_path}`: {e}")
			except Exception as e:
				await ctx.send(f"❌ Failed to reload `{cog_path}`: {e}")
	
	@commands.command(name="load", hidden=True)
	async def load_cog(self, ctx: commands.Context, cog: str):
		"""Load a cog. Usage: !load cog_name"""
		cog_path = f"cogs.{cog}" if not cog.startswith("cogs.") else cog
		try:
			await self.bot.load_extension(cog_path)
			await ctx.send(f"✅ Loaded `{cog_path}`")
		except commands.ExtensionAlreadyLoaded:
			await ctx.send(f"⚠️ `{cog_path}` is already loaded. Use `!reload {cog}` instead.")
		except Exception as e:
			await ctx.send(f"❌ Failed to load `{cog_path}`: {e}")
	
	@commands.command(name="unload", hidden=True)
	async def unload_cog(self, ctx: commands.Context, cog: str):
		"""Unload a cog. Usage: !unload cog_name"""
		cog_path = f"cogs.{cog}" if not cog.startswith("cogs.") else cog
		if cog_path == "cogs.dev":
			await ctx.send("❌ Cannot unload the dev cog!")
			return
		try:
			await self.bot.unload_extension(cog_path)
			await ctx.send(f"✅ Unloaded `{cog_path}`")
		except Exception as e:
			await ctx.send(f"❌ Failed to unload `{cog_path}`: {e}")
	
	@commands.command(name="sync", hidden=True)
	async def sync_commands(self, ctx: commands.Context, guild_id: Optional[int] = None):
		"""Sync slash commands. Usage: !sync [guild_id]"""
		async with ctx.typing():
			try:
				if guild_id:
					guild = discord.Object(id=guild_id)
					synced = await self.bot.tree.sync(guild=guild)
					await ctx.send(f"✅ Synced {len(synced)} commands to guild {guild_id}")
				else:
					synced = await self.bot.tree.sync()
					await ctx.send(f"✅ Synced {len(synced)} global commands")
			except Exception as e:
				await ctx.send(f"❌ Sync failed: {e}")
	
	# ─────────────────────────────────────────────────────────────────────────
	#                           DEBUG COMMANDS
	# ─────────────────────────────────────────────────────────────────────────
	
	@commands.command(name="cogs", hidden=True)
	async def list_cogs(self, ctx: commands.Context):
		"""List all loaded and failed cogs."""
		loaded = list(self.bot.extensions.keys())
		failed = list(self.cog_errors.keys())
		
		embed = discord.Embed(title="🔧 Cog Status", color=Colors.INFO)
		
		loaded_text = "\n".join(f"✅ `{c}`" for c in sorted(loaded)) or "None"
		embed.add_field(name=f"Loaded ({len(loaded)})", value=loaded_text[:1024], inline=False)
		
		if failed:
			failed_text = "\n".join(f"❌ `{c}`" for c in sorted(failed))
			embed.add_field(name=f"Failed ({len(failed)})", value=failed_text[:1024], inline=False)
		
		await ctx.send(embed=embed)
	
	@commands.command(name="debug", hidden=True)
	async def debug_info(self, ctx: commands.Context):
		"""Show debug information about the bot."""
		import platform
		
		embed = discord.Embed(title="🐛 Debug Info", color=Colors.WARNING)
		
		# System info
		embed.add_field(
			name="📊 System",
			value=f"Python: `{sys.version.split()[0]}`\n"
				  f"discord.py: `{discord.__version__}`\n"
				  f"Platform: `{platform.system()}`",
			inline=True
		)
		
		# Bot stats
		embed.add_field(
			name="🤖 Bot",
			value=f"Latency: `{round(self.bot.latency * 1000)}ms`\n"
				  f"Guilds: `{len(self.bot.guilds)}`\n"
				  f"Users: `{sum(g.member_count or 0 for g in self.bot.guilds)}`",
			inline=True
		)
		
		# Cog stats
		total_cogs = len(self.bot.extensions)
		failed_cogs = len(self.cog_errors)
		embed.add_field(
			name="🔧 Cogs",
			value=f"Loaded: `{total_cogs}`\n"
				  f"Failed: `{failed_cogs}`\n"
				  f"Commands: `{len(list(self.bot.tree.walk_commands()))}`",
			inline=True
		)
		
		# Memory
		try:
			import psutil
			process = psutil.Process()
			memory = process.memory_info().rss / 1024 / 1024
			embed.add_field(name="💾 Memory", value=f"`{memory:.1f} MB`", inline=True)
		except ImportError:
			pass
		
		# Failed cogs details
		if self.cog_errors:
			error_text = "\n".join(f"❌ `{c}`: {e[:50]}" for c, e in self.cog_errors.items())
			embed.add_field(name="⚠️ Failed Cogs", value=error_text[:1024], inline=False)
		
		await ctx.send(embed=embed)
	
	@commands.command(name="errors", hidden=True)
	async def show_errors(self, ctx: commands.Context, cog: str = None):
		"""Show detailed error for a failed cog."""
		if cog is None:
			if not self.cog_errors:
				await ctx.send("✅ No cog errors recorded!")
				return
			
			errors = "\n".join(f"**{c}**: {e[:100]}..." for c, e in self.cog_errors.items())
			await ctx.send(f"**Failed Cogs:**\n{errors}")
		else:
			cog_path = f"cogs.{cog}" if not cog.startswith("cogs.") else cog
			error = self.cog_errors.get(cog_path)
			if error:
				# Truncate for Discord
				if len(error) > 1900:
					error = error[:1900] + "..."
				await ctx.send(f"**Error for `{cog_path}`:**\n```\n{error}\n```")
			else:
				await ctx.send(f"No error recorded for `{cog_path}`")
	
	@commands.command(name="eval", hidden=True)
	async def eval_code(self, ctx: commands.Context, *, code: str):
		"""Evaluate Python code. DANGEROUS - owner only."""
		# Remove code blocks if present
		if code.startswith("```") and code.endswith("```"):
			code = code[3:-3]
			if code.startswith("py"):
				code = code[2:]
		code = code.strip()
		
		# Create environment
		env = {
			"bot": self.bot,
			"ctx": ctx,
			"discord": discord,
			"commands": commands,
			"asyncio": asyncio,
		}
		env.update(globals())
		
		try:
			result = eval(code, env)
			if asyncio.iscoroutine(result):
				result = await result
			
			if result is not None:
				output = str(result)
				if len(output) > 1900:
					output = output[:1900] + "..."
				await ctx.send(f"```py\n{output}\n```")
			else:
				await ctx.message.add_reaction("✅")
		except Exception as e:
			await ctx.send(f"```py\n{type(e).__name__}: {e}\n```")
	
	# ─────────────────────────────────────────────────────────────────────────
	#                        ERROR MONITORING COMMANDS
	# ─────────────────────────────────────────────────────────────────────────
	
	@commands.command(name="errorlog", hidden=True)
	async def error_log_cmd(self, ctx: commands.Context, count: int = 10):
		"""Show recent errors. Usage: !errorlog [count]"""
		if not self.error_log:
			await ctx.send("✅ No errors recorded!")
			return
		
		count = min(count, len(self.error_log), 25)
		recent = list(self.error_log)[-count:]
		
		embed = discord.Embed(
			title=f"🔴 Recent Errors ({count}/{len(self.error_log)})",
			color=Colors.ERROR,
			description="\n".join(e.short_str() for e in reversed(recent))
		)
		embed.set_footer(text=f"Total errors since start: {self.error_count}")
		
		await ctx.send(embed=embed)
	
	@commands.command(name="errordetail", hidden=True)
	async def error_detail(self, ctx: commands.Context, index: int = -1):
		"""Show full details of an error. Usage: !errordetail [index]"""
		if not self.error_log:
			await ctx.send("✅ No errors recorded!")
			return
		
		try:
			record = list(self.error_log)[index]
		except IndexError:
			await ctx.send(f"❌ Invalid index. Range: 0 to {len(self.error_log)-1}")
			return
		
		embed = discord.Embed(
			title=f"🔴 Error Detail",
			color=Colors.ERROR,
			timestamp=record.timestamp
		)
		embed.add_field(name="Type", value=record.error_type, inline=True)
		embed.add_field(name="Source", value=record.source, inline=True)
		embed.add_field(name="Error", value=type(record.error).__name__, inline=True)
		
		if record.context:
			embed.add_field(name="Context", value=record.context[:1024], inline=False)
		
		tb = "".join(record.traceback[-10:])
		if len(tb) > 1000:
			tb = tb[-1000:]
		embed.add_field(name="Traceback", value=f"```py\n{tb}\n```"[:1024], inline=False)
		
		await ctx.send(embed=embed)
	
	@commands.command(name="clearerrors", hidden=True)
	async def clear_errors(self, ctx: commands.Context):
		"""Clear the error log."""
		count = len(self.error_log)
		self.error_log.clear()
		self.error_count = 0
		await ctx.send(f"✅ Cleared {count} errors from log.")
	
	@commands.command(name="alerts", hidden=True)
	async def toggle_alerts(self, ctx: commands.Context, state: str = None):
		"""Toggle DM error alerts. Usage: !alerts [on/off]"""
		if state is None:
			status = "enabled" if self.dm_alerts else "disabled"
			await ctx.send(f"📬 DM alerts are currently **{status}**. Use `!alerts on` or `!alerts off`.")
		elif state.lower() in ("on", "true", "yes", "1", "enable"):
			self.dm_alerts = True
			await ctx.send("✅ DM error alerts **enabled**. You'll receive DMs when errors occur.")
		elif state.lower() in ("off", "false", "no", "0", "disable"):
			self.dm_alerts = False
			await ctx.send("✅ DM error alerts **disabled**.")
		else:
			await ctx.send("❌ Invalid state. Use `on` or `off`.")
	
	@commands.command(name="monitor", hidden=True)
	async def monitor_status(self, ctx: commands.Context):
		"""Show error monitoring status and stats."""
		now = datetime.now(timezone.utc)
		
		# Count errors by time period
		last_5min = sum(1 for e in self.error_log if (now - e.timestamp).total_seconds() < 300)
		last_hour = sum(1 for e in self.error_log if (now - e.timestamp).total_seconds() < 3600)
		
		# Count by type
		by_type: dict[str, int] = {}
		for e in self.error_log:
			by_type[e.error_type] = by_type.get(e.error_type, 0) + 1
		
		embed = discord.Embed(
			title="📊 Error Monitor Status",
			color=Colors.INFO
		)
		
		embed.add_field(
			name="⏱️ Error Rates",
			value=f"Last 5 min: `{last_5min}`\n"
				  f"Last hour: `{last_hour}`\n"
				  f"Total: `{self.error_count}`",
			inline=True
		)
		
		if by_type:
			type_text = "\n".join(f"`{k}`: {v}" for k, v in sorted(by_type.items()))
			embed.add_field(name="📁 By Type", value=type_text, inline=True)
		
		embed.add_field(
			name="⚙️ Settings",
			value=f"DM Alerts: `{'on' if self.dm_alerts else 'off'}`\n"
				  f"Log Size: `{len(self.error_log)}/50`",
			inline=True
		)
		
		# Show most recent error
		if self.error_log:
			latest = list(self.error_log)[-1]
			embed.add_field(
				name="🔴 Latest Error",
				value=latest.short_str(),
				inline=False
			)
		
		await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
	"""Enhanced setup with error tracking."""
	dev_cog = Dev(bot)
	await bot.add_cog(dev_cog)
	
	# Track any previously failed cogs during initial load
	# This is called after the cog is added, so it has access to the bot
	logger.info("Dev cog loaded - hot reload available via !reload")
