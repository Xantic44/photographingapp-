"""
Economy cog - funPoints economy system with gambling.
Optimized and polished version.
"""
import random
import time
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from core.helpers import (
	get_economy_entry,
	save_data,
	mark_dirty,
	format_cooldown,
	DAILY_COOLDOWN,
	WORK_COOLDOWN,
	Colors,
	cute_daily,
	cute_work,
	cute_win,
	cute_loss,
)

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────
DAILY_RANGE = (150, 300)
WORK_RANGE = (40, 120)

# Risk tiers: (min_balance, name, win_bonus, loss_penalty)
RISK_TIERS = [
	(10000, "🔥 High Roller", 1.5, 1.3),
	(5000,  "💰 Big Spender", 1.3, 1.2),
	(2000,  "🎯 Regular", 1.15, 1.1),
	(500,   "🌱 Starter", 1.0, 1.0),
	(0,     "🛡️ Protected", 1.1, 0.8),
]

# Slot symbols: (emoji, name, triple_multiplier)
SLOT_SYMBOLS = [
	("🍒", "Cherry", 2),
	("🍋", "Lemon", 2.5),
	("🍊", "Orange", 3),
	("🍇", "Grapes", 3.5),
	("⭐", "Star", 5),
	("💎", "Diamond", 8),
	("7️⃣", "Lucky 7", 15),
]
SLOT_WEIGHTS = [25, 20, 18, 15, 12, 7, 3]


class Economy(commands.Cog):
	"""FunPoints economy and gambling system."""

	def __init__(self, bot: commands.Bot):
		self.bot = bot

	# ─────────────────────────────────────────────────────────────────────────
	# Helper methods
	# ─────────────────────────────────────────────────────────────────────────
	def _get_entry(self, guild_id: int, user_id: int) -> dict:
		"""Get economy entry for a user."""
		return get_economy_entry(self.bot.data["economy"], guild_id, user_id)

	def _get_risk_tier(self, balance: int) -> tuple[str, float, float]:
		"""Get risk tier based on balance. Returns (tier_name, win_bonus, loss_penalty)."""
		for min_bal, name, win_bonus, loss_pen in RISK_TIERS:
			if balance >= min_bal:
				return (name, win_bonus, loss_pen)
		return RISK_TIERS[-1][1:]  # fallback to last tier

	def _embed(self, title: str, color: discord.Color, user: discord.Member | discord.User) -> discord.Embed:
		"""Create a base embed with user avatar."""
		embed = discord.Embed(title=title, color=color)
		embed.set_author(name=user.display_name, icon_url=user.display_avatar.url)
		return embed

	async def _check_bet(self, interaction: discord.Interaction, amount: int) -> Optional[dict]:
		"""Validate bet and return entry if valid, None otherwise."""
		if not interaction.guild:
			await interaction.response.send_message("Use this in a server.", ephemeral=True)
			return None
		if amount <= 0:
			await interaction.response.send_message("❌ Bet must be more than 0.", ephemeral=True)
			return None
		entry = self._get_entry(interaction.guild.id, interaction.user.id)
		if entry["funPoints"] < amount:
			await interaction.response.send_message(f"❌ You only have **{entry['funPoints']:,}** funPoints!", ephemeral=True)
			return None
		return entry

	# ─────────────────────────────────────────────────────────────────────────
	# Core economy commands
	# ─────────────────────────────────────────────────────────────────────────
	@commands.command()
	async def balance(self, ctx: commands.Context, member: discord.Member = None):
		"""Check funPoints balance."""
		member = member or ctx.author
		entry = self._get_entry(ctx.guild.id, member.id)
		tier_name, _, _ = self._get_risk_tier(entry['funPoints'])
		
		embed = discord.Embed(color=Colors.ECONOMY)
		embed.set_author(name=f"{member.display_name}'s Wallet", icon_url=member.display_avatar.url)
		embed.add_field(name="💳 Balance", value=f"**{entry['funPoints']:,}** funPoints", inline=True)
		embed.add_field(name="🏷️ Tier", value=tier_name, inline=True)
		embed.set_footer(text="Use /daily and /work to earn more!")
		await ctx.send(embed=embed)

	@app_commands.command(name="balance", description="💰 Check your funPoints wallet")
	@app_commands.describe(member="User to check (defaults to you)")
	async def balance_slash(self, interaction: discord.Interaction, member: discord.Member = None):
		if not interaction.guild:
			await interaction.response.send_message("Use this in a server.", ephemeral=True)
			return
		member = member or interaction.user
		entry = self._get_entry(interaction.guild.id, member.id)
		tier_name, win_bonus, loss_pen = self._get_risk_tier(entry['funPoints'])
		
		embed = discord.Embed(color=Colors.ECONOMY)
		embed.set_author(name=f"{member.display_name}'s Wallet 💰", icon_url=member.display_avatar.url)
		embed.set_thumbnail(url=member.display_avatar.url)
		
		# Balance display
		embed.add_field(name="💳 Balance", value=f"```{entry['funPoints']:,} funPoints```", inline=True)
		embed.add_field(name="🏷️ Tier", value=tier_name, inline=True)
		
		# Tier info
		if win_bonus > 1.0:
			embed.add_field(name="📈 Bonuses", value=f"Win: **+{int((win_bonus-1)*100)}%** │ Risk: **+{int((loss_pen-1)*100)}%**", inline=False)
		else:
			embed.add_field(name="🛡️ Protection", value="Lower risk for new players!", inline=False)
		
		embed.set_footer(text="💡 Use /daily, /work, and gambling to grow your wallet!")
		await interaction.response.send_message(embed=embed)

	@commands.command()
	async def daily(self, ctx: commands.Context):
		"""Claim daily funPoints."""
		entry = self._get_entry(ctx.guild.id, ctx.author.id)
		now = int(time.time())
		remaining = DAILY_COOLDOWN - (now - entry["last_daily"])
		if remaining > 0:
			await ctx.send(f"⏳ Daily already claimed. Try again in {format_cooldown(remaining)}.")
			return
		amount = random.randint(*DAILY_RANGE)
		entry["funPoints"] += amount
		entry["last_daily"] = now
		mark_dirty()
		await ctx.send(f"🎁 You claimed **{amount}** funPoints! Balance: **{entry['funPoints']:,}**")

	@app_commands.command(name="daily", description="🎁 Claim your daily funPoints reward!")
	async def daily_slash(self, interaction: discord.Interaction):
		if not interaction.guild:
			await interaction.response.send_message("Use this in a server.", ephemeral=True)
			return
		entry = self._get_entry(interaction.guild.id, interaction.user.id)
		now = int(time.time())
		remaining = DAILY_COOLDOWN - (now - entry["last_daily"])
		if remaining > 0:
			embed = discord.Embed(
				title="⏰ Already Claimed!",
				description=f"You've already claimed your daily reward today~\n\nCome back in **{format_cooldown(remaining)}**!",
				color=Colors.WARNING
			)
			embed.set_footer(text="I'll be here waiting! 💕")
			await interaction.response.send_message(embed=embed, ephemeral=True)
			return
		amount = random.randint(*DAILY_RANGE)
		entry["funPoints"] += amount
		entry["last_daily"] = now
		mark_dirty()
		
		embed = discord.Embed(
			title="🎁 Daily Reward!",
			description=cute_daily(),
			color=Colors.SUCCESS
		)
		embed.add_field(name="💰 Earned", value=f"**+{amount:,}** funPoints", inline=True)
		embed.add_field(name="💳 Balance", value=f"**{entry['funPoints']:,}** funPoints", inline=True)
		embed.set_footer(text="Come back tomorrow for more! ✨")
		embed.set_thumbnail(url=interaction.user.display_avatar.url)
		await interaction.response.send_message(embed=embed)

	@commands.command()
	async def work(self, ctx: commands.Context):
		"""Work for funPoints."""
		entry = self._get_entry(ctx.guild.id, ctx.author.id)
		now = int(time.time())
		remaining = WORK_COOLDOWN - (now - entry["last_work"])
		if remaining > 0:
			await ctx.send(f"⏳ You're tired. Work again in {format_cooldown(remaining)}.")
			return
		amount = random.randint(*WORK_RANGE)
		entry["funPoints"] += amount
		entry["last_work"] = now
		mark_dirty()
		await ctx.send(f"🛠️ You earned **{amount}** funPoints. Balance: **{entry['funPoints']:,}**")

	@app_commands.command(name="work", description="💼 Work a shift to earn funPoints!")
	async def work_slash(self, interaction: discord.Interaction):
		if not interaction.guild:
			await interaction.response.send_message("Use this in a server.", ephemeral=True)
			return
		entry = self._get_entry(interaction.guild.id, interaction.user.id)
		now = int(time.time())
		remaining = WORK_COOLDOWN - (now - entry["last_work"])
		if remaining > 0:
			embed = discord.Embed(
				title="😴 Too Tired!",
				description=f"You need a break! Rest up and try again in **{format_cooldown(remaining)}**.",
				color=Colors.WARNING
			)
			embed.set_footer(text="Hard workers need rest too~")
			await interaction.response.send_message(embed=embed, ephemeral=True)
			return
		amount = random.randint(*WORK_RANGE)
		entry["funPoints"] += amount
		entry["last_work"] = now
		mark_dirty()
		
		# Random work scenario
		emoji, job_msg = cute_work()
		
		embed = discord.Embed(
			title=f"{emoji} Work Complete!",
			description=job_msg,
			color=Colors.SUCCESS
		)
		embed.add_field(name="💵 Earned", value=f"**+{amount:,}** funPoints", inline=True)
		embed.add_field(name="💳 Balance", value=f"**{entry['funPoints']:,}** funPoints", inline=True)
		embed.set_footer(text="Work again in 1 hour! 💪")
		embed.set_thumbnail(url=interaction.user.display_avatar.url)
		await interaction.response.send_message(embed=embed)

	@commands.command()
	async def pay(self, ctx: commands.Context, member: discord.Member, amount: int):
		"""Send funPoints to another user."""
		if amount <= 0:
			await ctx.send("Amount must be more than 0.")
			return
		if member.bot or member.id == ctx.author.id:
			await ctx.send("Pick another real user.")
			return
		sender = self._get_entry(ctx.guild.id, ctx.author.id)
		if sender["funPoints"] < amount:
			await ctx.send("You don't have enough funPoints.")
			return
		receiver = self._get_entry(ctx.guild.id, member.id)
		sender["funPoints"] -= amount
		receiver["funPoints"] += amount
		mark_dirty()
		await ctx.send(f"💸 Sent **{amount:,}** funPoints to {member.mention}.")

	@app_commands.command(name="pay", description="💸 Send funPoints to another user")
	@app_commands.describe(member="User to pay", amount="Amount to transfer")
	async def pay_slash(self, interaction: discord.Interaction, member: discord.Member, amount: int):
		if not interaction.guild:
			await interaction.response.send_message("Use this in a server.", ephemeral=True)
			return
		if amount <= 0:
			await interaction.response.send_message("❌ Amount must be more than 0.", ephemeral=True)
			return
		if member.bot or member.id == interaction.user.id:
			await interaction.response.send_message("❌ Pick another real user.", ephemeral=True)
			return
		sender = self._get_entry(interaction.guild.id, interaction.user.id)
		if sender["funPoints"] < amount:
			await interaction.response.send_message("❌ You don't have enough funPoints!", ephemeral=True)
			return
		receiver = self._get_entry(interaction.guild.id, member.id)
		sender["funPoints"] -= amount
		receiver["funPoints"] += amount
		mark_dirty()
		
		embed = discord.Embed(
			title="💸 Payment Sent!",
			color=Colors.SUCCESS
		)
		embed.add_field(name="📤 From", value=interaction.user.mention, inline=True)
		embed.add_field(name="📥 To", value=member.mention, inline=True)
		embed.add_field(name="💰 Amount", value=f"**{amount:,}** funPoints", inline=True)
		embed.add_field(name="💳 Your Balance", value=f"**{sender['funPoints']:,}**", inline=True)
		embed.add_field(name="💳 Their Balance", value=f"**{receiver['funPoints']:,}**", inline=True)
		embed.set_footer(text="Generosity is cool! 🌟")
		await interaction.response.send_message(embed=embed)

	# ─────────────────────────────────────────────────────────────────────────
	# Gambling commands
	# ─────────────────────────────────────────────────────────────────────────
	@app_commands.command(name="coinflip", description="🪙 Flip a coin and bet funPoints!")
	@app_commands.describe(amount="Amount to bet", choice="Heads or Tails")
	@app_commands.choices(choice=[
		app_commands.Choice(name="🦅 Heads", value="heads"),
		app_commands.Choice(name="🐍 Tails", value="tails"),
	])
	async def coinflip(self, interaction: discord.Interaction, amount: int, choice: app_commands.Choice[str]):
		entry = await self._check_bet(interaction, amount)
		if not entry:
			return

		tier_name, win_bonus, loss_pen = self._get_risk_tier(entry["funPoints"])
		result = random.choice(["heads", "tails"])
		coin_emoji = "🦅" if result == "heads" else "🐍"
		won = choice.value == result

		if won:
			winnings = int(amount * win_bonus)
			entry["funPoints"] += winnings
			embed = self._embed("🪙 COINFLIP - WINNER! 🎉", discord.Color.green(), interaction.user)
			embed.description = f"The coin spins through the air...\n\n{coin_emoji} **{result.upper()}!** {coin_emoji}"
			embed.add_field(name="Your Pick", value=f"{'🦅' if choice.value == 'heads' else '🐍'} {choice.value.title()}", inline=True)
			embed.add_field(name="Bet", value=f"🎲 {amount:,}", inline=True)
			embed.add_field(name="Won", value=f"💰 +{winnings:,}", inline=True)
		else:
			loss = int(amount * loss_pen)
			entry["funPoints"] -= loss
			embed = self._embed("🪙 COINFLIP - LOST! 😢", discord.Color.red(), interaction.user)
			embed.description = f"The coin spins through the air...\n\n{coin_emoji} **{result.upper()}!** {coin_emoji}"
			embed.add_field(name="Your Pick", value=f"{'🦅' if choice.value == 'heads' else '🐍'} {choice.value.title()}", inline=True)
			embed.add_field(name="Bet", value=f"🎲 {amount:,}", inline=True)
			embed.add_field(name="Lost", value=f"💸 -{loss:,}", inline=True)

		embed.add_field(name="Balance", value=f"🎯 **{entry['funPoints']:,}** funPoints", inline=False)
		embed.set_footer(text=f"{tier_name} • Higher balance = higher stakes!")
		mark_dirty()
		await interaction.response.send_message(embed=embed)

	@app_commands.command(name="gamble", description="🎲 Roll the dice! Higher balance = bigger rewards & risks")
	@app_commands.describe(amount="Amount to gamble")
	async def gamble(self, interaction: discord.Interaction, amount: int):
		entry = await self._check_bet(interaction, amount)
		if not entry:
			return

		tier_name, win_bonus, loss_pen = self._get_risk_tier(entry["funPoints"])
		roll = random.randint(1, 100)

		# Outcome tiers: (max_roll, multiplier, is_win, outcome_type)
		if roll <= 5:
			mult, won, otype = 3.0 * win_bonus, True, "critical"
		elif roll <= 20:
			mult, won, otype = 2.0 * win_bonus, True, "big"
		elif roll <= 45:
			mult, won, otype = 1.5 * win_bonus, True, "small"
		elif roll <= 70:
			mult, won, otype = 1.0 * loss_pen, False, "near"
		elif roll <= 90:
			mult, won, otype = 1.0 * loss_pen, False, "loss"
		else:
			mult, won, otype = 1.5 * loss_pen, False, "critical_loss"

		if won:
			winnings = int(amount * mult)
			net = winnings - amount
			entry["funPoints"] += net
			colors = {"critical": discord.Color.gold(), "big": discord.Color.green(), "small": discord.Color.blue()}
			titles = {"critical": "🎲 CRITICAL HIT! 💥", "big": "🎲 BIG WIN! 🎉", "small": "🎲 WIN! ✨"}
			descs = {
				"critical": f"```🎲 Rolled: {roll}```\n🌟 **INCREDIBLE LUCK!** 🌟",
				"big": f"```🎲 Rolled: {roll}```\n🎉 **NICE ROLL!** 🎉",
				"small": f"```🎲 Rolled: {roll}```\n✨ A small but satisfying win!",
			}
			embed = self._embed(titles[otype], colors[otype], interaction.user)
			embed.description = descs[otype]
			embed.add_field(name="Bet", value=f"🎲 {amount:,}", inline=True)
			embed.add_field(name="Multi", value=f"✖️ {mult:.1f}x", inline=True)
			embed.add_field(name="Won", value=f"💰 +{net:,}", inline=True)
		else:
			loss = int(amount * mult)
			entry["funPoints"] = max(0, entry["funPoints"] - loss)
			colors = {"critical_loss": discord.Color.dark_red(), "near": discord.Color.orange(), "loss": discord.Color.red()}
			titles = {"critical_loss": "🎲 CRITICAL FAIL! 💀", "near": "🎲 SO CLOSE! 😰", "loss": "🎲 LOST! 😢"}
			descs = {
				"critical_loss": f"```🎲 Rolled: {roll}```\n💀 **DEVASTATING LOSS!** 💀",
				"near": f"```🎲 Rolled: {roll}```\n😰 Just barely missed!",
				"loss": f"```🎲 Rolled: {roll}```\n😢 Better luck next time...",
			}
			embed = self._embed(titles[otype], colors[otype], interaction.user)
			embed.description = descs[otype]
			embed.add_field(name="Bet", value=f"🎲 {amount:,}", inline=True)
			embed.add_field(name="Multi", value=f"✖️ {mult:.1f}x loss", inline=True)
			embed.add_field(name="Lost", value=f"💸 -{loss:,}", inline=True)

		embed.add_field(name="Balance", value=f"🎯 **{entry['funPoints']:,}** funPoints", inline=False)
		embed.set_footer(text=f"{tier_name} • Roll 1-45 to win!")
		mark_dirty()
		await interaction.response.send_message(embed=embed)

	@app_commands.command(name="slots", description="🎰 Spin the slot machine!")
	@app_commands.describe(amount="Amount to bet")
	async def slots(self, interaction: discord.Interaction, amount: int):
		entry = await self._check_bet(interaction, amount)
		if not entry:
			return

		tier_name, win_bonus, loss_pen = self._get_risk_tier(entry["funPoints"])
		symbols = [s[0] for s in SLOT_SYMBOLS]
		reels = random.choices(symbols, weights=SLOT_WEIGHTS, k=3)

		# Check for matches
		multiplier = 0.0
		match_type = "none"
		matched_sym = None

		if reels[0] == reels[1] == reels[2]:
			for emoji, name, mult in SLOT_SYMBOLS:
				if emoji == reels[0]:
					multiplier = mult
					matched_sym = (emoji, name)
					match_type = "jackpot" if emoji == "7️⃣" else "triple"
					break
		elif reels[0] == reels[1] or reels[1] == reels[2] or reels[0] == reels[2]:
			matched = reels[0] if reels[0] == reels[1] else (reels[1] if reels[1] == reels[2] else reels[0])
			for emoji, name, mult in SLOT_SYMBOLS:
				if emoji == matched:
					multiplier = 1.5 + (mult * 0.1)
					matched_sym = (emoji, name)
					match_type = "double"
					break

		# Display
		slot_box = (
			"╭─────────────────────╮\n"
			"│    🎰 **SLOTS** 🎰    │\n"
			"├─────────────────────┤\n"
			f"│  ▸ {reels[0]} ║ {reels[1]} ║ {reels[2]} ◂  │\n"
			"╰─────────────────────╯"
		)

		if multiplier > 0:
			final_mult = multiplier * win_bonus
			winnings = int(amount * final_mult)
			net = winnings - amount
			entry["funPoints"] += net

			if match_type == "jackpot":
				embed = self._embed("✨ JACKPOT!!! ✨", discord.Color.gold(), interaction.user)
				embed.description = f"{slot_box}\n\n╔══════════════════════╗\n║ 🌟 **777 JACKPOT** 🌟 ║\n╚══════════════════════╝"
				embed.add_field(name="🎯 Match", value="7️⃣ 7️⃣ 7️⃣ Triple Sevens!", inline=False)
			elif match_type == "triple":
				embed = self._embed("🎉 TRIPLE MATCH!", discord.Color.green(), interaction.user)
				embed.description = f"{slot_box}\n\n✨ **THREE {matched_sym[1].upper()}S!** ✨"
				embed.add_field(name="🎯 Match", value=f"{matched_sym[0]} {matched_sym[0]} {matched_sym[0]} ─ Triple!", inline=False)
			else:
				embed = self._embed("✨ DOUBLE MATCH!", discord.Color.blue(), interaction.user)
				embed.description = f"{slot_box}\n\n💫 *Two matching symbols!*"
				embed.add_field(name="🎯 Match", value=f"{matched_sym[0]} {matched_sym[0]} ─ Pair!", inline=False)

			embed.add_field(name="🎲 Bet", value=f"{amount:,}", inline=True)
			embed.add_field(name="✖️ Multi", value=f"{final_mult:.1f}x", inline=True)
			embed.add_field(name="💰 Won", value=f"+{net:,}", inline=True)
		else:
			loss = int(amount * loss_pen)
			entry["funPoints"] = max(0, entry["funPoints"] - loss)
			embed = self._embed("😢 No Match", discord.Color.red(), interaction.user)
			embed.description = f"{slot_box}\n\n*No matching symbols...*\n🍀 *Better luck next spin!*"
			embed.add_field(name="🎲 Bet", value=f"{amount:,}", inline=True)
			embed.add_field(name="💸 Lost", value=f"-{loss:,}", inline=True)
			embed.add_field(name="\u200b", value="\u200b", inline=True)

		embed.add_field(name="💳 Balance", value=f"**{entry['funPoints']:,}** funPoints", inline=False)
		embed.set_footer(text=f"{tier_name} ─ 7️⃣×3 = 15x ┃ 💎×3 = 8x ┃ ⭐×3 = 5x")
		mark_dirty()
		await interaction.response.send_message(embed=embed)

	# ─────────────────────────────────────────────────────────────────────────
	# Leaderboard
	# ─────────────────────────────────────────────────────────────────────────
	@app_commands.command(name="funleaderboard", description="🏆 See the richest users!")
	async def funleaderboard(self, interaction: discord.Interaction):
		if not interaction.guild:
			await interaction.response.send_message("Use this in a server.", ephemeral=True)
			return

		guild_id = str(interaction.guild.id)
		economy_data = self.bot.data["economy"].get(guild_id, {})

		if not economy_data:
			await interaction.response.send_message("📊 No economy data yet! Use `/daily` or `/work` to get started.", ephemeral=True)
			return

		# Sort users by points
		user_points = [(int(uid), data.get("funPoints", data.get("coins", 0))) 
					   for uid, data in economy_data.items() if data.get("funPoints", data.get("coins", 0)) > 0]
		user_points.sort(key=lambda x: x[1], reverse=True)

		if not user_points:
			await interaction.response.send_message("📊 No one has any funPoints yet!", ephemeral=True)
			return

		embed = discord.Embed(
			title="🏆 FunPoints Leaderboard 🏆",
			description=f"The wealthiest members of **{interaction.guild.name}**",
			color=discord.Color.gold()
		)

		medals = ["🥇", "🥈", "🥉"]
		lines = []
		for i, (user_id, points) in enumerate(user_points[:10], 1):
			member = interaction.guild.get_member(user_id)
			name = member.display_name if member else f"User {user_id}"
			tier_emoji = self._get_risk_tier(points)[0].split()[0]
			rank = medals[i-1] if i <= 3 else f"**{i}.**"
			lines.append(f"{rank} {name} — {points:,} 🎯 {tier_emoji}")

		embed.add_field(name="Rankings", value="\n".join(lines), inline=False)

		# User's position
		user_rank = next((i for i, (uid, _) in enumerate(user_points, 1) if uid == interaction.user.id), None)
		if user_rank:
			user_pts = user_points[user_rank - 1][1]
			tier_name = self._get_risk_tier(user_pts)[0]
			pos_text = f"**#{user_rank}** with **{user_pts:,}** funPoints\n{tier_name}"
			if user_rank > 10:
				pos_text = f"**#{user_rank}** of {len(user_points)} — {user_pts:,} funPoints\n{tier_name}"
			embed.add_field(name="📍 Your Position", value=pos_text, inline=False)

		total = sum(pts for _, pts in user_points)
		avg = total // len(user_points)
		embed.add_field(name="📊 Stats", value=f"Total: {total:,} │ Avg: {avg:,} │ Players: {len(user_points)}", inline=False)
		embed.set_footer(text="💡 Use /coinflip, /gamble, or /slots to climb!")
		if interaction.guild.icon:
			embed.set_thumbnail(url=interaction.guild.icon.url)

		await interaction.response.send_message(embed=embed)

	# ─────────────────────────────────────────────────────────────────────────
	# Admin commands
	# ─────────────────────────────────────────────────────────────────────────
	@app_commands.command(name="givefunpoints", description="[Admin] Give funPoints")
	@app_commands.checks.has_permissions(administrator=True)
	@app_commands.describe(member="User to give to", amount="Amount")
	async def givefunpoints(self, interaction: discord.Interaction, member: discord.Member, amount: int):
		if not interaction.guild or amount <= 0:
			await interaction.response.send_message("Invalid input.", ephemeral=True)
			return
		entry = self._get_entry(interaction.guild.id, member.id)
		entry["funPoints"] += amount
		mark_dirty()
		await interaction.response.send_message(f"✅ Gave **{amount:,}** to {member.mention}. Balance: **{entry['funPoints']:,}**")

	@app_commands.command(name="removefunpoints", description="[Admin] Remove funPoints")
	@app_commands.checks.has_permissions(administrator=True)
	@app_commands.describe(member="User to remove from", amount="Amount")
	async def removefunpoints(self, interaction: discord.Interaction, member: discord.Member, amount: int):
		if not interaction.guild or amount <= 0:
			await interaction.response.send_message("Invalid input.", ephemeral=True)
			return
		entry = self._get_entry(interaction.guild.id, member.id)
		entry["funPoints"] = max(0, entry["funPoints"] - amount)
		mark_dirty()
		await interaction.response.send_message(f"✅ Removed **{amount:,}** from {member.mention}. Balance: **{entry['funPoints']:,}**")

	@app_commands.command(name="setfunpoints", description="[Admin] Set funPoints balance")
	@app_commands.checks.has_permissions(administrator=True)
	@app_commands.describe(member="User", amount="New balance")
	async def setfunpoints(self, interaction: discord.Interaction, member: discord.Member, amount: int):
		if not interaction.guild or amount < 0:
			await interaction.response.send_message("Invalid input.", ephemeral=True)
			return
		entry = self._get_entry(interaction.guild.id, member.id)
		entry["funPoints"] = amount
		mark_dirty()
		await interaction.response.send_message(f"✅ Set {member.mention}'s balance to **{amount:,}**")

	# ─────────────────────────────────────────────────────────────────────────
	#                        SHOP & INVENTORY
	# ─────────────────────────────────────────────────────────────────────────
	
	def _get_shop(self, guild_id: int) -> dict:
		"""Get shop items for a guild. Structure: {item_id: {name, description, price, role_id, stock}}"""
		gid = str(guild_id)
		if "shop" not in self.bot.data:
			self.bot.data["shop"] = {}
		if gid not in self.bot.data["shop"]:
			self.bot.data["shop"][gid] = {"next_id": 1, "items": {}}
		return self.bot.data["shop"][gid]
	
	def _get_inventory(self, guild_id: int, user_id: int) -> list:
		"""Get user inventory. Returns list of item_ids."""
		entry = self._get_entry(guild_id, user_id)
		if "inventory" not in entry:
			entry["inventory"] = []
		return entry["inventory"]
	
	shop_group = app_commands.Group(name="shop", description="Browse and buy items")
	
	@shop_group.command(name="view", description="🏪 View the server shop")
	async def shop_view(self, interaction: discord.Interaction):
		"""View all items in the shop."""
		if not interaction.guild:
			await interaction.response.send_message("Use this in a server.", ephemeral=True)
			return
		
		shop_data = self._get_shop(interaction.guild.id)
		items = shop_data.get("items", {})
		
		if not items:
			await interaction.response.send_message(
				"🏪 **The shop is empty!**\n"
				"Admins can add items with `/shop add`",
				ephemeral=True
			)
			return
		
		embed = discord.Embed(
			title="🏪 Server Shop",
			description="Use `/shop buy <item>` to purchase!",
			color=Colors.ECONOMY
		)
		
		for item_id, item in items.items():
			stock_text = f" (Stock: {item['stock']})" if item.get("stock", -1) > -1 else ""
			role_text = ""
			if item.get("role_id"):
				role = interaction.guild.get_role(item["role_id"])
				if role:
					role_text = f"\n🎭 Grants: {role.mention}"
			
			embed.add_field(
				name=f"{item['name']} - 🎯 {item['price']:,} funPoints",
				value=f"{item.get('description', 'No description')}{role_text}{stock_text}\nID: `{item_id}`",
				inline=False
			)
		
		entry = self._get_entry(interaction.guild.id, interaction.user.id)
		embed.set_footer(text=f"Your balance: {entry['funPoints']:,} funPoints")
		
		await interaction.response.send_message(embed=embed, allowed_mentions=discord.AllowedMentions.none())
	
	@shop_group.command(name="buy", description="💰 Buy an item from the shop")
	@app_commands.describe(item_id="Item ID to purchase")
	async def shop_buy(self, interaction: discord.Interaction, item_id: str):
		"""Buy an item from the shop."""
		if not interaction.guild:
			await interaction.response.send_message("Use this in a server.", ephemeral=True)
			return
		
		shop_data = self._get_shop(interaction.guild.id)
		items = shop_data.get("items", {})
		
		if item_id not in items:
			await interaction.response.send_message("❌ Item not found.", ephemeral=True)
			return
		
		item = items[item_id]
		entry = self._get_entry(interaction.guild.id, interaction.user.id)
		
		# Check stock
		if item.get("stock", -1) == 0:
			await interaction.response.send_message("❌ This item is out of stock!", ephemeral=True)
			return
		
		# Check balance
		if entry["funPoints"] < item["price"]:
			await interaction.response.send_message(
				f"❌ You need **{item['price']:,}** funPoints but only have **{entry['funPoints']:,}**",
				ephemeral=True
			)
			return
		
		# Process purchase
		entry["funPoints"] -= item["price"]
		
		# Handle role items
		if item.get("role_id"):
			role = interaction.guild.get_role(item["role_id"])
			if role:
				try:
					await interaction.user.add_roles(role, reason="Purchased from shop")
				except discord.Forbidden:
					await interaction.response.send_message("❌ I couldn't give you the role.", ephemeral=True)
					entry["funPoints"] += item["price"]  # Refund
					return
		else:
			# Add to inventory for non-role items
			inventory = self._get_inventory(interaction.guild.id, interaction.user.id)
			inventory.append({"id": item_id, "name": item["name"]})
		
		# Reduce stock if limited
		if item.get("stock", -1) > 0:
			item["stock"] -= 1
		
		mark_dirty()
		
		await interaction.response.send_message(
			f"✅ Purchased **{item['name']}** for **{item['price']:,}** funPoints!\n"
			f"💰 New balance: **{entry['funPoints']:,}**"
		)
	
	@shop_group.command(name="add", description="[Admin] Add item to shop")
	@app_commands.describe(
		name="Item name",
		price="Price in funPoints",
		description="Item description",
		role="Role to grant when purchased (optional)",
		stock="Limited stock (-1 for unlimited)"
	)
	@app_commands.checks.has_permissions(administrator=True)
	async def shop_add(self, interaction: discord.Interaction, name: str, price: int, description: str = "", role: discord.Role = None, stock: int = -1):
		"""Add an item to the shop."""
		if not interaction.guild:
			await interaction.response.send_message("Use this in a server.", ephemeral=True)
			return
		
		if price < 0:
			await interaction.response.send_message("❌ Price must be positive.", ephemeral=True)
			return
		
		if role and role >= interaction.guild.me.top_role:
			await interaction.response.send_message("❌ That role is higher than my top role.", ephemeral=True)
			return
		
		shop_data = self._get_shop(interaction.guild.id)
		item_id = str(shop_data["next_id"])
		shop_data["next_id"] += 1
		
		shop_data["items"][item_id] = {
			"name": name[:50],
			"description": description[:200],
			"price": price,
			"role_id": role.id if role else None,
			"stock": stock
		}
		mark_dirty()
		
		stock_text = f" (Stock: {stock})" if stock > -1 else " (Unlimited)"
		role_text = f"\n🎭 Grants: {role.mention}" if role else ""
		
		await interaction.response.send_message(
			f"✅ Added to shop (ID: `{item_id}`):\n"
			f"**{name}** - 🎯 {price:,} funPoints{stock_text}{role_text}",
			allowed_mentions=discord.AllowedMentions.none()
		)
	
	@shop_group.command(name="remove", description="[Admin] Remove item from shop")
	@app_commands.describe(item_id="Item ID to remove")
	@app_commands.checks.has_permissions(administrator=True)
	async def shop_remove(self, interaction: discord.Interaction, item_id: str):
		"""Remove an item from the shop."""
		if not interaction.guild:
			await interaction.response.send_message("Use this in a server.", ephemeral=True)
			return
		
		shop_data = self._get_shop(interaction.guild.id)
		
		if item_id not in shop_data["items"]:
			await interaction.response.send_message("❌ Item not found.", ephemeral=True)
			return
		
		name = shop_data["items"][item_id]["name"]
		del shop_data["items"][item_id]
		mark_dirty()
		
		await interaction.response.send_message(f"✅ Removed **{name}** from the shop.")
	
	@app_commands.command(name="inventory", description="🎒 View your inventory")
	@app_commands.describe(member="User to check (optional)")
	async def inventory(self, interaction: discord.Interaction, member: discord.Member = None):
		"""View your inventory."""
		if not interaction.guild:
			await interaction.response.send_message("Use this in a server.", ephemeral=True)
			return
		
		member = member or interaction.user
		inventory = self._get_inventory(interaction.guild.id, member.id)
		
		if not inventory:
			if member == interaction.user:
				await interaction.response.send_message("🎒 Your inventory is empty!", ephemeral=True)
			else:
				await interaction.response.send_message(f"🎒 {member.display_name}'s inventory is empty!", ephemeral=True)
			return
		
		# Count items
		item_counts = {}
		for item in inventory:
			name = item.get("name", "Unknown")
			item_counts[name] = item_counts.get(name, 0) + 1
		
		lines = [f"• **{name}** x{count}" for name, count in item_counts.items()]
		
		embed = discord.Embed(
			title=f"🎒 {member.display_name}'s Inventory",
			description="\n".join(lines[:20]),  # Max 20 items displayed
			color=Colors.ECONOMY
		)
		embed.set_footer(text=f"Total items: {len(inventory)}")
		
		await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
	await bot.add_cog(Economy(bot))
