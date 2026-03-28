"""
Events cog - Scheduled events, linked roles, and application emojis.
"""
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Literal

import discord
from discord import app_commands
from discord.ext import commands

from core.helpers import logger, mark_dirty


# ─────────────────────────────────────────────────────────────────────────────
# Event Type Choices
# ─────────────────────────────────────────────────────────────────────────────
EVENT_TYPES = {
    "stream": ("🎥", discord.Color.purple()),
    "meetup": ("🤝", discord.Color.green()),
    "raid": ("⚔️", discord.Color.red()),
    "gvg": ("🏰", discord.Color.orange()),
    "tournament": ("🏆", discord.Color.gold()),
    "other": ("📅", discord.Color.blurple()),
}

# Connection display names for linked roles
CONNECTION_NAMES = {
    "twitch": "🎮 Twitch",
    "youtube": "📺 YouTube",
    "spotify": "🎵 Spotify",
    "steam": "🎮 Steam",
    "twitter": "🐦 Twitter/X",
    "github": "💻 GitHub",
}


class EventModal(discord.ui.Modal, title="Create Server Event"):
    """Modal for creating events with detailed info."""
    
    event_name = discord.ui.TextInput(
        label="Event Name",
        placeholder="Friday Night Raid",
        max_length=100,
        required=True,
    )
    
    description = discord.ui.TextInput(
        label="Description",
        placeholder="Weekly guild raid - bring your best gear!",
        style=discord.TextStyle.paragraph,
        max_length=1000,
        required=True,
    )
    
    location = discord.ui.TextInput(
        label="Location (optional)",
        placeholder="Discord Voice Channel or external link",
        max_length=100,
        required=False,
    )

    def __init__(self, event_type: str, start_time: datetime, duration_hours: int, channel: discord.VoiceChannel | None):
        super().__init__()
        self.event_type = event_type
        self.start_time = start_time
        self.duration_hours = duration_hours
        self.channel = channel

    async def on_submit(self, interaction: discord.Interaction):
        emoji, color = EVENT_TYPES.get(self.event_type, ("📅", discord.Color.blurple()))
        
        try:
            # Calculate end time
            end_time = self.start_time + timedelta(hours=self.duration_hours)
            
            # Create event based on type (voice channel or external)
            if self.channel:
                # Voice channel event
                event = await interaction.guild.create_scheduled_event(
                    name=f"{emoji} {self.event_name.value}",
                    description=self.description.value,
                    start_time=self.start_time,
                    end_time=end_time,
                    channel=self.channel,
                    privacy_level=discord.PrivacyLevel.guild_only,
                )
            else:
                # External event - use location parameter
                location = self.location.value if self.location.value else "Discord Server"
                event = await interaction.guild.create_scheduled_event(
                    name=f"{emoji} {self.event_name.value}",
                    description=self.description.value,
                    start_time=self.start_time,
                    end_time=end_time,
                    location=location,
                    privacy_level=discord.PrivacyLevel.guild_only,
                )

            embed = discord.Embed(
                title="✅ Event Created!",
                description=f"**{event.name}**",
                color=color,
            )
            embed.add_field(name="📅 Start", value=f"<t:{int(self.start_time.timestamp())}:F>", inline=True)
            embed.add_field(name="⏱️ Duration", value=f"{self.duration_hours}h", inline=True)
            embed.add_field(name="📍 Location", value=self.location.value or (self.channel.mention if self.channel else "TBD"), inline=True)
            embed.add_field(name="🔗 Event Link", value=event.url, inline=False)
            
            await interaction.response.send_message(embed=embed)
            logger.info("Created event '%s' in %s", event.name, interaction.guild.name)
            
        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission to create events!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Failed to create event: {e}", ephemeral=True)
            logger.error("Event creation failed: %s", e)


class EventListView(discord.ui.View):
    """View for paginating through events."""
    
    def __init__(self, events: list, author_id: int):
        super().__init__(timeout=120)
        self.events = events
        self.author_id = author_id
        self.page = 0
        self.per_page = 5
        self.max_pages = max(1, (len(events) + self.per_page - 1) // self.per_page)
        self.update_buttons()

    def update_buttons(self):
        self.prev_btn.disabled = self.page == 0
        self.next_btn.disabled = self.page >= self.max_pages - 1

    def get_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="📅 Scheduled Events",
            color=discord.Color.blurple(),
        )
        
        start = self.page * self.per_page
        end = start + self.per_page
        page_events = self.events[start:end]
        
        if not page_events:
            embed.description = "No scheduled events."
        else:
            for event in page_events:
                status = "🟢 Active" if event.status == discord.EventStatus.active else "🟡 Scheduled"
                interested = event.user_count or 0
                embed.add_field(
                    name=f"{event.name}",
                    value=(
                        f"{status} • 👥 {interested} interested\n"
                        f"📅 <t:{int(event.start_time.timestamp())}:R>\n"
                        f"[Join Event]({event.url})"
                    ),
                    inline=False,
                )
        
        embed.set_footer(text=f"Page {self.page + 1}/{self.max_pages}")
        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This isn't your menu!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page -= 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page += 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)


class Events(commands.Cog):
    """Scheduled events, linked roles, and application emojis."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ─────────────────────────────────────────────────────────────────────────
    # Scheduled Events Commands
    # ─────────────────────────────────────────────────────────────────────────
    events_group = app_commands.Group(name="event", description="Manage server scheduled events")

    @events_group.command(name="create", description="Create a new scheduled event")
    @app_commands.describe(
        event_type="Type of event",
        start_in_hours="Hours from now until event starts",
        duration_hours="How long the event lasts (hours)",
        voice_channel="Optional: Voice channel for the event",
    )
    @app_commands.choices(event_type=[
        app_commands.Choice(name="🎥 Stream", value="stream"),
        app_commands.Choice(name="🤝 Meetup", value="meetup"),
        app_commands.Choice(name="⚔️ Raid", value="raid"),
        app_commands.Choice(name="🏰 Guild vs Guild", value="gvg"),
        app_commands.Choice(name="🏆 Tournament", value="tournament"),
        app_commands.Choice(name="📅 Other", value="other"),
    ])
    @app_commands.checks.has_permissions(manage_events=True)
    async def event_create(
        self,
        interaction: discord.Interaction,
        event_type: str,
        start_in_hours: app_commands.Range[int, 1, 168] = 1,
        duration_hours: app_commands.Range[int, 1, 24] = 2,
        voice_channel: discord.VoiceChannel | None = None,
    ):
        start_time = datetime.now(timezone.utc) + timedelta(hours=start_in_hours)
        modal = EventModal(event_type, start_time, duration_hours, voice_channel)
        await interaction.response.send_modal(modal)

    @events_group.command(name="list", description="List all scheduled events")
    async def event_list(self, interaction: discord.Interaction):
        events = list(interaction.guild.scheduled_events)
        
        if not events:
            embed = discord.Embed(
                title="📅 Scheduled Events",
                description="No scheduled events. Create one with `/event create`!",
                color=discord.Color.blurple(),
            )
            await interaction.response.send_message(embed=embed)
            return

        # Sort by start time
        events.sort(key=lambda e: e.start_time)
        view = EventListView(events, interaction.user.id)
        await interaction.response.send_message(embed=view.get_embed(), view=view)

    @events_group.command(name="cancel", description="Cancel a scheduled event")
    @app_commands.describe(event_name="Name of the event to cancel (partial match)")
    @app_commands.checks.has_permissions(manage_events=True)
    async def event_cancel(self, interaction: discord.Interaction, event_name: str):
        events = list(interaction.guild.scheduled_events)
        matches = [e for e in events if event_name.lower() in e.name.lower()]
        
        if not matches:
            await interaction.response.send_message(f"❌ No event found matching '{event_name}'", ephemeral=True)
            return
        
        if len(matches) > 1:
            names = "\n".join(f"• {e.name}" for e in matches[:5])
            await interaction.response.send_message(f"⚠️ Multiple matches found:\n{names}\n\nBe more specific.", ephemeral=True)
            return

        event = matches[0]
        await event.cancel()
        await interaction.response.send_message(f"✅ Cancelled event: **{event.name}**")

    @events_group.command(name="start", description="Start a scheduled event now")
    @app_commands.describe(event_name="Name of the event to start")
    @app_commands.checks.has_permissions(manage_events=True)
    async def event_start(self, interaction: discord.Interaction, event_name: str):
        events = list(interaction.guild.scheduled_events)
        matches = [e for e in events if event_name.lower() in e.name.lower()]
        
        if not matches:
            await interaction.response.send_message(f"❌ No event found matching '{event_name}'", ephemeral=True)
            return

        event = matches[0]
        try:
            await event.start()
            await interaction.response.send_message(f"🚀 Started event: **{event.name}**\n{event.url}")
        except discord.HTTPException as e:
            await interaction.response.send_message(f"❌ Couldn't start event: {e}", ephemeral=True)

    @events_group.command(name="end", description="End an active event")
    @app_commands.describe(event_name="Name of the event to end")
    @app_commands.checks.has_permissions(manage_events=True)
    async def event_end(self, interaction: discord.Interaction, event_name: str):
        events = list(interaction.guild.scheduled_events)
        matches = [e for e in events if event_name.lower() in e.name.lower()]
        
        if not matches:
            await interaction.response.send_message(f"❌ No event found matching '{event_name}'", ephemeral=True)
            return

        event = matches[0]
        try:
            await event.end()
            await interaction.response.send_message(f"✅ Ended event: **{event.name}**")
        except discord.HTTPException as e:
            await interaction.response.send_message(f"❌ Couldn't end event: {e}", ephemeral=True)

    # ─────────────────────────────────────────────────────────────────────────
    # Linked Roles Commands
    # ─────────────────────────────────────────────────────────────────────────
    roles_group = app_commands.Group(name="linkedrole", description="Manage connection-linked roles")

    @roles_group.command(name="setup", description="Setup linked role requirements (Admin)")
    @app_commands.describe(
        role="Role to grant when requirements are met",
        connection="Required connection type",
    )
    @app_commands.choices(connection=[
        app_commands.Choice(name="🎮 Twitch", value="twitch"),
        app_commands.Choice(name="📺 YouTube", value="youtube"),
        app_commands.Choice(name="🎵 Spotify", value="spotify"),
        app_commands.Choice(name="🎮 Steam", value="steam"),
        app_commands.Choice(name="🐦 Twitter/X", value="twitter"),
        app_commands.Choice(name="💻 GitHub", value="github"),
    ])
    @app_commands.checks.has_permissions(administrator=True)
    async def linkedrole_setup(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
        connection: str,
    ):
        # Store in bot data
        guild_id = str(interaction.guild.id)
        if "linked_roles" not in self.bot.data:
            self.bot.data["linked_roles"] = {}
        
        if guild_id not in self.bot.data["linked_roles"]:
            self.bot.data["linked_roles"][guild_id] = {}
        
        self.bot.data["linked_roles"][guild_id][connection] = role.id
        
        mark_dirty()  # Use mark_dirty instead of save_data for autosave

        embed = discord.Embed(
            title="🔗 Linked Role Setup",
            description=f"Users with **{CONNECTION_NAMES.get(connection, connection)}** connected will get {role.mention}",
            color=discord.Color.green(),
        )
        embed.add_field(
            name="⚠️ Note",
            value="Users need to run `/linkedrole claim` after connecting their account in Discord settings.",
            inline=False,
        )
        await interaction.response.send_message(embed=embed)

    @roles_group.command(name="claim", description="Claim roles based on your connected accounts")
    async def linkedrole_claim(self, interaction: discord.Interaction):
        guild_id = str(interaction.guild.id)
        linked_roles = self.bot.data.get("linked_roles", {}).get(guild_id, {})
        
        if not linked_roles:
            await interaction.response.send_message(
                "❌ No linked roles are configured for this server.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        # Get member's connections (requires member to have connected accounts visible)
        member = interaction.user
        
        # Note: Discord API doesn't allow bots to see user connections directly
        # This requires OAuth2 flow with 'connections' scope
        # For now, we'll show what's available and link to settings
        
        embed = discord.Embed(
            title="🔗 Claim Linked Roles",
            color=discord.Color.blurple(),
        )
        
        available = []
        for conn, role_id in linked_roles.items():
            role = interaction.guild.get_role(role_id)
            if role:
                available.append(f"{CONNECTION_NAMES.get(conn, conn)} → {role.mention}")
        
        if available:
            embed.add_field(
                name="📋 Available Linked Roles",
                value="\n".join(available),
                inline=False,
            )
        
        embed.add_field(
            name="📝 How to Get These Roles",
            value=(
                "1. Go to **User Settings** → **Connections**\n"
                "2. Connect the required account (Twitch, YouTube, etc.)\n"
                "3. Enable **Display on Profile**\n"
                "4. Contact a moderator to verify and grant the role"
            ),
            inline=False,
        )
        
        await interaction.followup.send(embed=embed)

    @roles_group.command(name="verify", description="Verify a user's connection and grant role (Mod)")
    @app_commands.describe(
        member="Member to verify",
        connection="Connection type to verify",
    )
    @app_commands.choices(connection=[
        app_commands.Choice(name="🎮 Twitch", value="twitch"),
        app_commands.Choice(name="📺 YouTube", value="youtube"),
        app_commands.Choice(name="🎵 Spotify", value="spotify"),
        app_commands.Choice(name="🎮 Steam", value="steam"),
        app_commands.Choice(name="🐦 Twitter/X", value="twitter"),
        app_commands.Choice(name="💻 GitHub", value="github"),
    ])
    @app_commands.checks.has_permissions(manage_roles=True)
    async def linkedrole_verify(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        connection: str,
    ):
        guild_id = str(interaction.guild.id)
        linked_roles = self.bot.data.get("linked_roles", {}).get(guild_id, {})
        
        if connection not in linked_roles:
            await interaction.response.send_message(
                f"❌ No linked role configured for {connection}",
                ephemeral=True,
            )
            return
        
        role = interaction.guild.get_role(linked_roles[connection])
        if not role:
            await interaction.response.send_message("❌ Role no longer exists!", ephemeral=True)
            return
        
        if role in member.roles:
            await interaction.response.send_message(f"ℹ️ {member.mention} already has {role.mention}", ephemeral=True)
            return
        
        try:
            await member.add_roles(role, reason=f"Linked role verified by {interaction.user}")
            await interaction.response.send_message(f"✅ Granted {role.mention} to {member.mention}")
        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission to manage that role!", ephemeral=True)

    @roles_group.command(name="list", description="List all linked role configurations")
    async def linkedrole_list(self, interaction: discord.Interaction):
        guild_id = str(interaction.guild.id)
        linked_roles = self.bot.data.get("linked_roles", {}).get(guild_id, {})
        
        if not linked_roles:
            await interaction.response.send_message(
                "No linked roles configured. Use `/linkedrole setup` to add some!",
                ephemeral=True,
            )
            return
        
        embed = discord.Embed(
            title="🔗 Linked Roles Configuration",
            color=discord.Color.blurple(),
        )
        
        for conn, role_id in linked_roles.items():
            role = interaction.guild.get_role(role_id)
            status = role.mention if role else "❌ Role Deleted"
            embed.add_field(
                name=CONNECTION_NAMES.get(conn, conn),
                value=status,
                inline=True,
            )
        
        await interaction.response.send_message(embed=embed)

    # ─────────────────────────────────────────────────────────────────────────
    # Application Emoji Commands  
    # ─────────────────────────────────────────────────────────────────────────
    emoji_group = app_commands.Group(name="appemoji", description="Manage bot application emojis")

    @emoji_group.command(name="list", description="List all application emojis owned by this bot")
    async def appemoji_list(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        try:
            # Fetch application emojis
            emojis = await self.bot.application.emojis()
            
            if not emojis:
                embed = discord.Embed(
                    title="🎨 Application Emojis",
                    description="No application emojis. Add some with `/appemoji add`!",
                    color=discord.Color.blurple(),
                )
                await interaction.followup.send(embed=embed)
                return

            embed = discord.Embed(
                title="🎨 Application Emojis",
                description=f"Bot owns **{len(emojis)}** emojis (work everywhere the bot is)",
                color=discord.Color.blurple(),
            )
            
            emoji_list = []
            for emoji in emojis[:25]:  # Limit display
                emoji_list.append(f"{emoji} `:{emoji.name}:` (ID: {emoji.id})")
            
            embed.add_field(
                name="Emojis",
                value="\n".join(emoji_list) if emoji_list else "None",
                inline=False,
            )
            
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to fetch emojis: {e}")

    @emoji_group.command(name="add", description="Add an application emoji (Bot Owner)")
    @app_commands.describe(
        name="Emoji name (alphanumeric and underscores only)",
        image_url="Direct URL to the image (PNG, JPG, GIF)",
    )
    async def appemoji_add(
        self,
        interaction: discord.Interaction,
        name: str,
        image_url: str,
    ):
        # Check if user is bot owner
        app_info = await self.bot.application_info()
        if interaction.user.id != app_info.owner.id:
            await interaction.response.send_message("❌ Only the bot owner can add application emojis.", ephemeral=True)
            return
        
        await interaction.response.defer()
        
        try:
            import aiohttp
            
            # Download image
            async with aiohttp.ClientSession() as session:
                async with session.get(image_url) as resp:
                    if resp.status != 200:
                        await interaction.followup.send("❌ Failed to download image!")
                        return
                    image_data = await resp.read()
            
            # Create emoji
            emoji = await self.bot.application.create_emoji(name=name, image=image_data)
            
            embed = discord.Embed(
                title="✅ Application Emoji Added!",
                description=f"{emoji} `:{emoji.name}:`",
                color=discord.Color.green(),
            )
            embed.add_field(name="ID", value=str(emoji.id), inline=True)
            embed.add_field(name="Usage", value=f"Works in all servers the bot is in!", inline=True)
            
            await interaction.followup.send(embed=embed)
            logger.info("Created application emoji: %s", emoji.name)
            
        except discord.HTTPException as e:
            await interaction.followup.send(f"❌ Failed to create emoji: {e}")
        except Exception as e:
            await interaction.followup.send(f"❌ Error: {e}")

    @emoji_group.command(name="delete", description="Delete an application emoji (Bot Owner)")
    @app_commands.describe(emoji_id="ID of the emoji to delete")
    async def appemoji_delete(
        self,
        interaction: discord.Interaction,
        emoji_id: str,
    ):
        app_info = await self.bot.application_info()
        if interaction.user.id != app_info.owner.id:
            await interaction.response.send_message("❌ Only the bot owner can delete application emojis.", ephemeral=True)
            return
        
        await interaction.response.defer()
        
        try:
            emojis = await self.bot.application.emojis()
            emoji = discord.utils.get(emojis, id=int(emoji_id))
            
            if not emoji:
                await interaction.followup.send("❌ Emoji not found!")
                return
            
            name = emoji.name
            await emoji.delete()
            
            await interaction.followup.send(f"✅ Deleted application emoji: `:{name}:`")
            logger.info("Deleted application emoji: %s", name)
            
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to delete emoji: {e}")

    @emoji_group.command(name="use", description="Send a message with an application emoji")
    @app_commands.describe(
        emoji_name="Name of the application emoji",
        message="Message to send with the emoji",
    )
    async def appemoji_use(
        self,
        interaction: discord.Interaction,
        emoji_name: str,
        message: str = "",
    ):
        try:
            emojis = await self.bot.application.emojis()
            emoji = discord.utils.get(emojis, name=emoji_name)
            
            if not emoji:
                await interaction.response.send_message(
                    f"❌ No application emoji named `:{emoji_name}:` found.",
                    ephemeral=True,
                )
                return
            
            await interaction.response.send_message(f"{emoji} {message}")
            
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

    # ─────────────────────────────────────────────────────────────────────────
    # Role Management Commands
    # ─────────────────────────────────────────────────────────────────────────
    role_group = app_commands.Group(name="role", description="Manage server roles")

    @role_group.command(name="give", description="Give a role to a user")
    @app_commands.describe(
        member="The member to give the role to",
        role="The role to give",
        reason="Reason for giving the role",
    )
    @app_commands.checks.has_permissions(manage_roles=True)
    async def role_give(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        role: discord.Role,
        reason: str = "No reason provided",
    ):
        # Check role hierarchy
        if role >= interaction.guild.me.top_role:
            await interaction.response.send_message("❌ I can't assign roles higher than or equal to my top role!", ephemeral=True)
            return
        if role >= interaction.user.top_role and interaction.user.id != interaction.guild.owner_id:
            await interaction.response.send_message("❌ You can't assign roles higher than or equal to your top role!", ephemeral=True)
            return
        
        if role in member.roles:
            await interaction.response.send_message(f"ℹ️ {member.mention} already has {role.mention}", ephemeral=True)
            return
        
        try:
            await member.add_roles(role, reason=f"{interaction.user}: {reason}")
            embed = discord.Embed(
                title="✅ Role Added",
                description=f"Gave {role.mention} to {member.mention}",
                color=discord.Color.green(),
            )
            embed.add_field(name="Reason", value=reason, inline=False)
            embed.set_footer(text=f"By {interaction.user.display_name}")
            await interaction.response.send_message(embed=embed)
            logger.info("Role %s given to %s by %s", role.name, member.name, interaction.user.name)
        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission to manage that role!", ephemeral=True)

    @role_group.command(name="remove", description="Remove a role from a user")
    @app_commands.describe(
        member="The member to remove the role from",
        role="The role to remove",
        reason="Reason for removing the role",
    )
    @app_commands.checks.has_permissions(manage_roles=True)
    async def role_remove(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        role: discord.Role,
        reason: str = "No reason provided",
    ):
        if role >= interaction.guild.me.top_role:
            await interaction.response.send_message("❌ I can't manage roles higher than or equal to my top role!", ephemeral=True)
            return
        if role >= interaction.user.top_role and interaction.user.id != interaction.guild.owner_id:
            await interaction.response.send_message("❌ You can't remove roles higher than or equal to your top role!", ephemeral=True)
            return
        
        if role not in member.roles:
            await interaction.response.send_message(f"ℹ️ {member.mention} doesn't have {role.mention}", ephemeral=True)
            return
        
        try:
            await member.remove_roles(role, reason=f"{interaction.user}: {reason}")
            embed = discord.Embed(
                title="✅ Role Removed",
                description=f"Removed {role.mention} from {member.mention}",
                color=discord.Color.orange(),
            )
            embed.add_field(name="Reason", value=reason, inline=False)
            embed.set_footer(text=f"By {interaction.user.display_name}")
            await interaction.response.send_message(embed=embed)
            logger.info("Role %s removed from %s by %s", role.name, member.name, interaction.user.name)
        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission to manage that role!", ephemeral=True)

    @role_group.command(name="info", description="Get information about a role")
    @app_commands.describe(role="The role to get info about")
    async def role_info(self, interaction: discord.Interaction, role: discord.Role):
        embed = discord.Embed(
            title=f"Role Info: {role.name}",
            color=role.color if role.color != discord.Color.default() else discord.Color.blurple(),
        )
        
        # Get members with this role
        member_count = len(role.members)
        
        embed.add_field(name="ID", value=str(role.id), inline=True)
        embed.add_field(name="Color", value=str(role.color), inline=True)
        embed.add_field(name="Position", value=str(role.position), inline=True)
        embed.add_field(name="Members", value=str(member_count), inline=True)
        embed.add_field(name="Mentionable", value="✅" if role.mentionable else "❌", inline=True)
        embed.add_field(name="Hoisted", value="✅" if role.hoist else "❌", inline=True)
        embed.add_field(name="Created", value=f"<t:{int(role.created_at.timestamp())}:R>", inline=True)
        embed.add_field(name="Managed", value="✅ (Bot/Integration)" if role.managed else "❌", inline=True)
        
        # Show key permissions
        key_perms = []
        if role.permissions.administrator:
            key_perms.append("👑 Administrator")
        if role.permissions.manage_guild:
            key_perms.append("🔧 Manage Server")
        if role.permissions.manage_roles:
            key_perms.append("🎭 Manage Roles")
        if role.permissions.manage_channels:
            key_perms.append("📁 Manage Channels")
        if role.permissions.kick_members:
            key_perms.append("👢 Kick Members")
        if role.permissions.ban_members:
            key_perms.append("🔨 Ban Members")
        if role.permissions.manage_messages:
            key_perms.append("💬 Manage Messages")
        if role.permissions.mention_everyone:
            key_perms.append("📢 Mention Everyone")
        
        if key_perms:
            embed.add_field(name="Key Permissions", value="\n".join(key_perms), inline=False)
        
        await interaction.response.send_message(embed=embed)

    @role_group.command(name="members", description="List members with a specific role")
    @app_commands.describe(role="The role to list members for")
    async def role_members(self, interaction: discord.Interaction, role: discord.Role):
        members = role.members
        
        if not members:
            await interaction.response.send_message(f"No members have {role.mention}", ephemeral=True)
            return
        
        # Paginate if many members
        member_list = [m.mention for m in members[:50]]
        remaining = len(members) - 50
        
        embed = discord.Embed(
            title=f"Members with {role.name}",
            description=", ".join(member_list),
            color=role.color if role.color != discord.Color.default() else discord.Color.blurple(),
        )
        embed.set_footer(text=f"Total: {len(members)} members" + (f" (+{remaining} more)" if remaining > 0 else ""))
        
        await interaction.response.send_message(embed=embed)

    @role_group.command(name="all", description="List all server roles")
    async def role_all(self, interaction: discord.Interaction):
        roles = sorted(interaction.guild.roles[1:], key=lambda r: r.position, reverse=True)  # Skip @everyone
        
        if not roles:
            await interaction.response.send_message("No roles in this server.", ephemeral=True)
            return
        
        # Format roles list
        role_lines = []
        for role in roles[:25]:  # Limit to 25
            member_count = len(role.members)
            emoji = "🤖" if role.managed else "🎭"
            role_lines.append(f"{emoji} {role.mention} — {member_count} members")
        
        embed = discord.Embed(
            title=f"📋 Server Roles ({len(roles)} total)",
            description="\n".join(role_lines),
            color=discord.Color.blurple(),
        )
        
        if len(roles) > 25:
            embed.set_footer(text=f"Showing top 25 of {len(roles)} roles")
        
        await interaction.response.send_message(embed=embed)

    @role_group.command(name="create", description="Create a new role")
    @app_commands.describe(
        name="Name for the new role",
        color="Hex color (e.g., #FF5733) or leave empty",
        hoist="Show role members separately in member list",
        mentionable="Allow anyone to mention this role",
    )
    @app_commands.checks.has_permissions(manage_roles=True)
    async def role_create(
        self,
        interaction: discord.Interaction,
        name: str,
        color: str = "",
        hoist: bool = False,
        mentionable: bool = False,
    ):
        # Parse color
        role_color = discord.Color.default()
        if color:
            try:
                color = color.lstrip('#')
                role_color = discord.Color(int(color, 16))
            except ValueError:
                await interaction.response.send_message("❌ Invalid color! Use hex format like #FF5733", ephemeral=True)
                return
        
        try:
            role = await interaction.guild.create_role(
                name=name,
                color=role_color,
                hoist=hoist,
                mentionable=mentionable,
                reason=f"Created by {interaction.user}",
            )
            
            embed = discord.Embed(
                title="✅ Role Created",
                description=f"Created {role.mention}",
                color=role_color if role_color != discord.Color.default() else discord.Color.green(),
            )
            embed.add_field(name="Hoisted", value="✅" if hoist else "❌", inline=True)
            embed.add_field(name="Mentionable", value="✅" if mentionable else "❌", inline=True)
            
            await interaction.response.send_message(embed=embed)
            logger.info("Role %s created by %s", role.name, interaction.user.name)
            
        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission to create roles!", ephemeral=True)

    @role_group.command(name="delete", description="Delete a role")
    @app_commands.describe(role="The role to delete")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def role_delete(self, interaction: discord.Interaction, role: discord.Role):
        if role >= interaction.guild.me.top_role:
            await interaction.response.send_message("❌ I can't delete roles higher than or equal to my top role!", ephemeral=True)
            return
        if role >= interaction.user.top_role and interaction.user.id != interaction.guild.owner_id:
            await interaction.response.send_message("❌ You can't delete roles higher than or equal to your top role!", ephemeral=True)
            return
        if role.managed:
            await interaction.response.send_message("❌ This role is managed by an integration and can't be deleted!", ephemeral=True)
            return
        
        role_name = role.name
        try:
            await role.delete(reason=f"Deleted by {interaction.user}")
            await interaction.response.send_message(f"✅ Deleted role: **{role_name}**")
            logger.info("Role %s deleted by %s", role_name, interaction.user.name)
        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission to delete that role!", ephemeral=True)

    @role_group.command(name="color", description="Change a role's color")
    @app_commands.describe(
        role="The role to modify",
        color="New hex color (e.g., #FF5733)",
    )
    @app_commands.checks.has_permissions(manage_roles=True)
    async def role_color(self, interaction: discord.Interaction, role: discord.Role, color: str):
        if role >= interaction.guild.me.top_role:
            await interaction.response.send_message("❌ I can't modify roles higher than or equal to my top role!", ephemeral=True)
            return
        
        try:
            color = color.lstrip('#')
            new_color = discord.Color(int(color, 16))
        except ValueError:
            await interaction.response.send_message("❌ Invalid color! Use hex format like #FF5733", ephemeral=True)
            return
        
        try:
            await role.edit(color=new_color, reason=f"Color changed by {interaction.user}")
            embed = discord.Embed(
                title="✅ Role Color Updated",
                description=f"Changed {role.mention} color to `#{color}`",
                color=new_color,
            )
            await interaction.response.send_message(embed=embed)
        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission to modify that role!", ephemeral=True)

    @role_group.command(name="massadd", description="Give a role to multiple members at once")
    @app_commands.describe(
        role="The role to give",
        target_role="Give to all members with this role (optional)",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def role_massadd(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
        target_role: discord.Role | None = None,
    ):
        if role >= interaction.guild.me.top_role:
            await interaction.response.send_message("❌ I can't assign roles higher than my top role!", ephemeral=True)
            return
        
        await interaction.response.defer()
        
        # Determine target members
        if target_role:
            targets = [m for m in target_role.members if role not in m.roles]
        else:
            targets = [m for m in interaction.guild.members if role not in m.roles and not m.bot]
        
        if not targets:
            await interaction.followup.send("No members to add the role to!")
            return
        
        success = 0
        failed = 0
        
        for member in targets:
            try:
                await member.add_roles(role, reason=f"Mass add by {interaction.user}")
                success += 1
                await asyncio.sleep(0.5)  # Rate limit protection
            except Exception:
                failed += 1
        
        embed = discord.Embed(
            title="✅ Mass Role Add Complete",
            description=f"Added {role.mention} to members",
            color=discord.Color.green(),
        )
        embed.add_field(name="Success", value=str(success), inline=True)
        embed.add_field(name="Failed", value=str(failed), inline=True)
        
        await interaction.followup.send(embed=embed)
        logger.info("Mass role add: %s to %d members by %s", role.name, success, interaction.user.name)


async def setup(bot: commands.Bot):
    await bot.add_cog(Events(bot))
