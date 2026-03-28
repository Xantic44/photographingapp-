"""
Extension and command-registration smoke checks for the bot.

This script does not connect to Discord. It attempts to load all configured
extensions and verifies key slash commands are registered.
"""
from __future__ import annotations

import ast
import asyncio
import copy
import logging
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import discord
from discord.ext import commands


ROOT = Path(__file__).resolve().parent
BOT_FILE = ROOT / "bot.py"

BASE_DATA = {
	"xp": {},
	"economy": {},
	"profiles": {},
	"welcome": {},
	"tickets": {},
	"ticket_credits": {},
	"automod": {},
	"music": {},
}

REQUIRED_COMMANDS = {"rank", "leaderboard", "levelrole", "setlevel"}


@dataclass
class SmokeResult:
	loaded: list[str]
	failed: list[tuple[str, str]]
	missing_commands: list[str]
	command_count: int


def _read_cogs_from_bot_file() -> list[str]:
	source = BOT_FILE.read_text(encoding="utf-8-sig")
	tree = ast.parse(source, filename=str(BOT_FILE))
	for node in tree.body:
		if isinstance(node, ast.Assign):
			for target in node.targets:
				if isinstance(target, ast.Name) and target.id == "COGS":
					if isinstance(node.value, ast.List):
						values: list[str] = []
						for elt in node.value.elts:
							if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
								values.append(elt.value)
						if values:
							return values
	raise RuntimeError("Could not read COGS list from bot.py")


async def run_smoke_checks() -> SmokeResult:
	cogs = _read_cogs_from_bot_file()

	intents = discord.Intents.default()
	bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)
	bot.started_at = datetime.now(timezone.utc)
	bot.data = copy.deepcopy(BASE_DATA)
	bot.mark_dirty = lambda: None

	loaded: list[str] = []
	failed: list[tuple[str, str]] = []
	logging.disable(logging.CRITICAL)
	try:
		async with bot:
			for extension in cogs:
				try:
					await bot.load_extension(extension)
					loaded.append(extension)
				except Exception:  # noqa: BLE001 - report exact traceback below
					failed.append((extension, traceback.format_exc()))

			names = {cmd.name for cmd in bot.tree.get_commands()}
			missing = sorted(REQUIRED_COMMANDS - names)

			for extension in list(bot.extensions.keys()):
				try:
					await bot.unload_extension(extension)
				except Exception:
					pass
	finally:
		logging.disable(logging.NOTSET)

	return SmokeResult(
		loaded=loaded,
		failed=failed,
		missing_commands=missing,
		command_count=len(names),
	)


def main() -> int:
	print("[smoke] Running extension load checks...")
	result = asyncio.run(run_smoke_checks())

	print(f"[smoke] Extensions loaded: {len(result.loaded)}")
	if result.failed:
		print(f"[smoke] Extensions failed: {len(result.failed)}")
		for extension, tb in result.failed:
			print(f"  - {extension}")
			print(tb)
	else:
		print("[smoke] Extensions failed: 0")

	print(f"[smoke] Registered slash commands: {result.command_count}")
	if result.missing_commands:
		print(f"[smoke] Missing required commands: {', '.join(result.missing_commands)}")
	else:
		print("[smoke] Required commands present: OK")

	if result.failed or result.missing_commands:
		print("[smoke] FAILED")
		return 1

	print("[smoke] PASSED")
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
