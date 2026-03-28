"""
Scheduler Cog - Schedule messages and announcements for later.
"""
import discord
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime, timezone, timedelta
import uuid

from core.helpers import Colors, logger


class Scheduler(commands.Cog):
    """Schedule messages to be sent at a later time."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.check_scheduled.start()

    def cog_unload(self):
        self.check_scheduled.cancel()

    def _get_scheduled(self, guild_id: int) -> list:
        """Get scheduled messages for a guild."""
        gid = str(guild_id)
        if "scheduled" not in self.bot.data:
            self.bot.data["scheduled"] = {}
        if gid not in self.bot.data["scheduled"]:
            self.bot.data["scheduled"][gid] = []
        return self.bot.data["scheduled"][gid]

    # ─────────────────────────────────────────────────────────────────────
    #                         BACKGROUND TASK
    # ─────────────────────────────────────────────────────────────────────

    @tasks.loop(seconds=30)
    async def check_scheduled(self):
        """Check for scheduled messages every 30 seconds."""
        now = datetime.now(timezone.utc).timestamp()

        for guild in self.bot.guilds:
            scheduled = self._get_scheduled(guild.id)
            to_remove = []

            for msg in scheduled:
                if msg["time"] <= now:
                    channel = guild.get_channel(msg["channel_id"])
                    if channel:
                        try:
                            # Build embed if title provided
                            if msg.get("title"):
                                embed = discord.Embed(
                                    title=msg["title"],
                                    description=msg["content"],
                                    color=Colors.INFO
                                )
                                await channel.send(embed=embed)
                            else:
                                await channel.send(msg["content"])
                            
                            logger.info(f"Sent scheduled message in {guild.name}")
                        except Exception as e:
                            logger.error(f"Failed to send scheduled message: {e}")
                    
                    to_remove.append(msg)

            # Remove sent messages
            for msg in to_remove:
                scheduled.remove(msg)
                self.bot.mark_dirty()

    @check_scheduled.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()

    # ─────────────────────────────────────────────────────────────────────
    #                           COMMANDS
    # ─────────────────────────────────────────────────────────────────────

    sched = app_commands.Group(name="schedule", description="Schedule messages")

    @sched.command(name="message", description="📅 Schedule a message for later")
    @app_commands.describe(
        channel="Channel to send the message in",
        minutes="Minutes from now (0-1440)",
        content="Message content",
        title="Optional embed title (makes it an embed)"
    )
    @app_commands.checks.has_permissions(manage_messages=True)
    async def schedule_msg(
        self, 
        interaction: discord.Interaction, 
        channel: discord.TextChannel,
        minutes: int,
        content: str,
        title: str = None
    ):
        """Schedule a message to be sent later."""
        if not interaction.guild:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return

        if minutes < 1 or minutes > 1440:
            await interaction.response.send_message(
                "❌ Minutes must be between 1 and 1440 (24 hours).",
                ephemeral=True
            )
            return

        send_time = datetime.now(timezone.utc) + timedelta(minutes=minutes)
        
        scheduled = self._get_scheduled(interaction.guild.id)
        scheduled.append({
            "id": str(uuid.uuid4())[:8],
            "channel_id": channel.id,
            "content": content,
            "title": title,
            "time": send_time.timestamp(),
            "author_id": interaction.user.id
        })
        self.bot.mark_dirty()

        time_str = f"<t:{int(send_time.timestamp())}:R>"
        await interaction.response.send_message(
            f"✅ Message scheduled for {channel.mention} {time_str}",
            ephemeral=True
        )

    @sched.command(name="list", description="📅 View scheduled messages")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def schedule_list(self, interaction: discord.Interaction):
        """List all scheduled messages."""
        if not interaction.guild:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return

        scheduled = self._get_scheduled(interaction.guild.id)
        
        if not scheduled:
            await interaction.response.send_message("📅 No scheduled messages.", ephemeral=True)
            return

        lines = []
        for msg in scheduled[:10]:
            channel = interaction.guild.get_channel(msg["channel_id"])
            ch_name = channel.mention if channel else "Unknown"
            time_str = f"<t:{int(msg['time'])}:R>"
            preview = msg["content"][:30] + "..." if len(msg["content"]) > 30 else msg["content"]
            lines.append(f"`{msg['id']}` | {ch_name} | {time_str}\n> {preview}")

        embed = discord.Embed(
            title="📅 Scheduled Messages",
            description="\n\n".join(lines),
            color=Colors.INFO
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @sched.command(name="cancel", description="📅 Cancel a scheduled message")
    @app_commands.describe(message_id="Message ID from /schedule list")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def schedule_cancel(self, interaction: discord.Interaction, message_id: str):
        """Cancel a scheduled message."""
        if not interaction.guild:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return

        scheduled = self._get_scheduled(interaction.guild.id)
        
        for msg in scheduled:
            if msg["id"] == message_id:
                scheduled.remove(msg)
                self.bot.mark_dirty()
                await interaction.response.send_message(
                    f"✅ Cancelled scheduled message `{message_id}`.",
                    ephemeral=True
                )
                return

        await interaction.response.send_message(
            f"❌ No scheduled message with ID `{message_id}`.",
            ephemeral=True
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Scheduler(bot))
