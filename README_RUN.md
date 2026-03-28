# Discord Bot Runbook

## Start the bot
- CMD: `run_bot.bat`
- PowerShell: `.\run_bot.ps1`

Both launchers:
- ensure `.venv` exists
- install dependencies from `requirements.txt`
- run `healthcheck.py`
- start `bot.py`

## Health check only
- `.\.venv\Scripts\python.exe healthcheck.py`

Checks:
- syntax compile for `bot.py`, `cogs/*.py`, `core/*.py`
- `DISCORD_TOKEN` presence in env or `.env`

## Smoke check only
- `.\.venv\Scripts\python.exe smoke_check.py`

Checks:
- all extensions from `COGS` in `bot.py` load without crashing
- required slash commands exist: `rank`, `leaderboard`, `levelrole`, `setlevel`

## One-command dev checks
- CMD: `dev_check.bat`
- PowerShell: `.\dev_check.ps1`

Runs both `healthcheck.py` and `smoke_check.py`.

## Fast debugging workflow
1. Edit a cog file.
2. In Discord (owner-only): `!reload <cog_name>`
3. If slash commands changed: `!sync <guild_id>`

Examples:
- `!reload xp`
- `!sync 123456789012345678`

## If slash commands do not appear
1. Confirm bot logs show guild sync on startup.
2. Run `!sync <guild_id>`.
3. Refresh Discord client (`Ctrl+R`).

## Common checks
- Syntax: `.\.venv\Scripts\python.exe -m py_compile cogs\modlog.py`
- All bot files: `.\.venv\Scripts\python.exe healthcheck.py`
