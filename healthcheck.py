"""
Lightweight project health checks for the Discord bot.

Checks:
- Python syntax compile for bot/core/cogs files
- Presence of DISCORD_TOKEN in environment or .env
"""
from __future__ import annotations

import glob
import os
import py_compile
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def find_python_files() -> list[Path]:
    files: list[Path] = [ROOT / "bot.py"]
    files.extend(Path(p) for p in glob.glob(str(ROOT / "cogs" / "*.py")))
    files.extend(Path(p) for p in glob.glob(str(ROOT / "core" / "*.py")))
    return sorted(files)


def check_syntax(files: list[Path]) -> tuple[int, list[tuple[Path, Exception]]]:
    ok = 0
    bad: list[tuple[Path, Exception]] = []
    for file in files:
        try:
            py_compile.compile(str(file), doraise=True)
            ok += 1
        except Exception as exc:  # noqa: BLE001 - show exact compile errors
            bad.append((file, exc))
    return ok, bad


def parse_env_file_token(env_file: Path) -> str | None:
    if not env_file.exists():
        return None

    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() == "DISCORD_TOKEN":
            return value.strip().strip('"').strip("'")
    return None


def main() -> int:
    print("[healthcheck] Running checks...")
    files = find_python_files()
    ok, bad = check_syntax(files)
    print(f"[healthcheck] Syntax: {ok}/{len(files)} files OK")
    if bad:
        print("[healthcheck] Syntax errors found:")
        for file, err in bad:
            rel = file.relative_to(ROOT)
            print(f"  - {rel}: {err}")

    token = os.getenv("DISCORD_TOKEN") or parse_env_file_token(ROOT / ".env")
    if token:
        print("[healthcheck] DISCORD_TOKEN: found")
    else:
        print("[healthcheck] DISCORD_TOKEN: missing (set it in .env)")

    if bad:
        print("[healthcheck] FAILED")
        return 1

    print("[healthcheck] PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
