"""
Birthday Cog - Track and announce user birthdays with optional birthday role.
"""
import discord
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime, timezone

from core.helpers import Colors, logger


class Birthday(commands.Cog):
    """Track and announce member birthdays."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.check_birthdays.start()

    def cog_unload(self):
        self.check_birthdays.cancel()

    def _get_config(self, guild_id: int) -> dict:
        """Get birthday config for a guild."""
        gid = str(guild_id)
        if "birthdays" not in self.bot.data:
            self.bot.data["birthdays"] = {}
        if gid not in self.bot.data["birthdays"]:
            self.bot.data["birthdays"][gid] = {"channel": None, "role": None, "users": {}}
        return self.bot.data["birthdays"][gid]

    # ─────────────────────────────────────────────────────────────────────
    #                         BACKGROUND TASK
    # ─────────────────────────────────────────────────────────────────────

    @tasks.loop(hours=1)
    async def check_birthdays(self):
        """Check for birthdays every hour and announce them."""
        now = datetime.now(timezone.utc)
        today = f"{now.month:02d}-{now.day:02d}"

        for guild in self.bot.guilds:
            config = self._get_config(guild.id)
            channel_id = config.get("channel")
            role_id = config.get("role")
            users = config.get("users", {})

            if not channel_id:
                continue

            channel = guild.get_channel(channel_id)
            if not channel:
                continue

            # Check each user
            for user_id, data in users.items():
                birthday = data.get("date", "")
                announced = data.get("announced", "")

                if birthday == today and announced != today:
                    member = guild.get_member(int(user_id))
                    if not member:
                        continue

                    import random
                    # Festive color palette
                    festive_colors = [
                        discord.Color.from_rgb(255, 183, 94),   # Orange
                        discord.Color.from_rgb(255, 99, 132),   # Pink
                        discord.Color.from_rgb(54, 209, 220),   # Blue
                        discord.Color.from_rgb(255, 234, 167),  # Yellow
                        discord.Color.from_rgb(120, 255, 120),  # Green
                        discord.Color.from_rgb(186, 104, 200),  # Purple
                    ]
                    color = random.choice(festive_colors)
                    # Festive backgrounds
                    backgrounds = [
                        "https://i.imgur.com/3GvwNBf.gif",  # Confetti
                        "https://i.imgur.com/1Q9Z1Zm.gif",  # Balloons
                        "https://i.imgur.com/8h3dFQG.png",  # Music note
                        "https://i.imgur.com/2yaf2wb.gif",  # Party
                    ]
                    bg_image = random.choice(backgrounds)
                    # Animated emojis (replace with your server's custom emoji IDs if available)
                    confetti = "<a:confetti:120000000000000000>"
                    balloon = "<a:balloon:120000000000000001>"
                    cake = "<a:cake:120000000000000002>"
                    # Age display if available
                    age_text = ""
                    if data.get("year"):
                        try:
                            birth_year = int(data["year"])
                            now_year = datetime.now(timezone.utc).year
                            age = now_year - birth_year
                            age_text = f"\n🎂 Turning **{age}** today!"
                        except Exception:
                            pass
                    # Birthday wishes from previous years (if stored)
                    wishes = data.get("wishes", [])
                    wishes_text = ""
                    if wishes:
                        wishes_text = "\n\n💌 **Birthday Wishes from Previous Years:**\n" + "\n".join(f"- {w}" for w in wishes[-3:])
                    # Build embed
                    embed = discord.Embed(
                        title=f"{confetti} 🎂 Happy Birthday, {member.display_name}! {balloon}",
                        description=(
                            f"{confetti} **Let's celebrate!** {confetti}\n\n"
                            f"🎉 Today is a special day for {member.mention}!{age_text}\n"
                            f"Send your wishes and make it memorable! 🥳🎁🎈\n\n"
                            f"---\n"
                            f"**Wishing you joy, laughter, and all the cake you can eat!😋** {cake}"
                            f"{wishes_text}"
                        ),
                        color=color
                    )
                    embed.set_thumbnail(url=member.display_avatar.url)
                    embed.set_image(url=bg_image)
                    embed.set_footer(text="🎈 Happy Birthday from everyone! 🎈")
                    # Interactive button for wishes
                    class WishButton(discord.ui.View):
                        def __init__(self, user_id):
                            super().__init__(timeout=3600)
                            self.user_id = user_id
                        @discord.ui.button(label="Send a Birthday Wish! 🎉", style=discord.ButtonStyle.success)
                        async def send_wish(self, interaction: discord.Interaction, button: discord.ui.Button):
                            if interaction.user.id == self.user_id:
                                await interaction.response.send_message("You can't send a wish to yourself, but happy birthday!💖", ephemeral=True)
                                return
                            await interaction.response.send_modal(BirthdayWishModal(self.user_id))
                    class BirthdayWishModal(discord.ui.Modal, title="Send a Birthday Wish!"):
                        wish = discord.ui.TextInput(label="Your wish", style=discord.TextStyle.paragraph, max_length=200)
                        def __init__(self, user_id):
                            super().__init__()
                            self.user_id = user_id
                        async def on_submit(self, interaction: discord.Interaction):
                            # Save the wish to the user's data
                            for uid, d in users.items():
                                if int(uid) == self.user_id:
                                    d.setdefault("wishes", []).append(f"{interaction.user.display_name}: {self.wish.value}")
                                    break
                            self.bot.mark_dirty()
                            await interaction.response.send_message("🎉 Your birthday wish was sent!", ephemeral=True)
                    view = WishButton(member.id)
                    await channel.send(f"@everyone 🎂 It's {member.mention}'s birthday! 🎊", embed=embed, view=view)

                    # Add birthday role if set
                    if role_id:
                        role = guild.get_role(role_id)
                        if role and role not in member.roles:
                            try:
                                await member.add_roles(role, reason="Birthday!")
                            except Exception:
                                pass

                    # Mark as announced
                    users[user_id]["announced"] = today
                    self.bot.mark_dirty()

                # Remove birthday role after the day
                elif announced and announced != today and role_id:
                    member = guild.get_member(int(user_id))
                    if member:
                        role = guild.get_role(role_id)
                        if role and role in member.roles:
                            try:
                                await member.remove_roles(role, reason="Birthday over")
                            except Exception:
                                pass
                    users[user_id]["announced"] = ""
                    self.bot.mark_dirty()

    @check_birthdays.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()

    # ─────────────────────────────────────────────────────────────────────
    #                           COMMANDS
    # ─────────────────────────────────────────────────────────────────────

    bday = app_commands.Group(name="birthday", description="Birthday commands")

    @bday.command(name="set", description="🎂 Set your birthday")
    @app_commands.describe(month="Month (1-12)", day="Day (1-31)")
    async def bday_set(self, interaction: discord.Interaction, month: int, day: int):
        """Set your birthday (month and day only for privacy)."""
        if not interaction.guild:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return

        # Validate
        if month < 1 or month > 12:
            await interaction.response.send_message("❌ Month must be 1-12.", ephemeral=True)
            return
        if day < 1 or day > 31:
            await interaction.response.send_message("❌ Day must be 1-31.", ephemeral=True)
            return

        config = self._get_config(interaction.guild.id)
        uid = str(interaction.user.id)
        if uid not in config["users"]:
            config["users"][uid] = {}
        
        config["users"][uid]["date"] = f"{month:02d}-{day:02d}"
        config["users"][uid]["announced"] = ""
        self.bot.mark_dirty()

        months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        await interaction.response.send_message(
            f"🎂 Birthday set to **{months[month-1]} {day}**!",
            ephemeral=True
        )

    @bday.command(name="view", description="🎂 View someone's birthday")
    @app_commands.describe(user="User to check (leave empty for yourself)")
    async def bday_view(self, interaction: discord.Interaction, user: discord.Member = None):
        """View a user's birthday."""
        if not interaction.guild:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return

        target = user or interaction.user
        config = self._get_config(interaction.guild.id)
        uid = str(target.id)
        
        if uid not in config["users"] or not config["users"][uid].get("date"):
            await interaction.response.send_message(
                f"❌ {target.display_name} hasn't set their birthday.",
                ephemeral=True
            )
            return

        date = config["users"][uid]["date"]
        month, day = int(date[:2]), int(date[3:])
        months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        
        await interaction.response.send_message(
            f"🎂 **{target.display_name}**'s birthday is **{months[month-1]} {day}**!",
            ephemeral=True
        )

    @bday.command(name="upcoming", description="🎂 See upcoming birthdays")
    async def bday_upcoming(self, interaction: discord.Interaction):
        """List upcoming birthdays in the server."""
        if not interaction.guild:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return

        config = self._get_config(interaction.guild.id)
        users = config.get("users", {})
        
        if not users:
            await interaction.response.send_message("❌ No birthdays set yet.", ephemeral=True)
            return

        now = datetime.now(timezone.utc)
        today_num = now.month * 100 + now.day
        
        upcoming = []
        for uid, data in users.items():
            date = data.get("date", "")
            if not date:
                continue
            member = interaction.guild.get_member(int(uid))
            if not member:
                continue
            m, d = int(date[:2]), int(date[3:])
            day_num = m * 100 + d
            # Calculate days until birthday
            if day_num >= today_num:
                diff = day_num - today_num
            else:
                diff = (1231 - today_num) + day_num  # Approximate
            upcoming.append((diff, member.display_name, date))

        upcoming.sort(key=lambda x: x[0])
        upcoming = upcoming[:10]

        months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        lines = []
        for diff, name, date in upcoming:
            m, d = int(date[:2]), int(date[3:])
            if diff == 0:
                lines.append(f"🎂 **{name}** - Today!")
            else:
                lines.append(f"🎂 **{name}** - {months[m-1]} {d}")

        embed = discord.Embed(
            title="🎂 Upcoming Birthdays",
            description="\n".join(lines) if lines else "No birthdays found.",
            color=Colors.INFO
        )
        await interaction.response.send_message(embed=embed)

    @bday.command(name="channel", description="🎂 Set birthday announcement channel")
    @app_commands.describe(channel="Channel for birthday announcements")
    @app_commands.checks.has_permissions(administrator=True)
    async def bday_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Set the channel for birthday announcements."""
        if not interaction.guild:
            return

        config = self._get_config(interaction.guild.id)
        config["channel"] = channel.id
        self.bot.mark_dirty()

        await interaction.response.send_message(
            f"✅ Birthday announcements will be sent to {channel.mention}!",
            ephemeral=True
        )

    @bday.command(name="role", description="🎂 Set birthday role (given on birthday)")
    @app_commands.describe(role="Role to give on birthdays (or leave empty to disable)")
    @app_commands.checks.has_permissions(administrator=True)
    async def bday_role(self, interaction: discord.Interaction, role: discord.Role = None):
        """Set the role to give on birthdays."""
        if not interaction.guild:
            return

        config = self._get_config(interaction.guild.id)
        config["role"] = role.id if role else None
        self.bot.mark_dirty()

        if role:
            await interaction.response.send_message(
                f"✅ Members will get {role.mention} on their birthday!",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "✅ Birthday role disabled.",
                ephemeral=True
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(Birthday(bot))
