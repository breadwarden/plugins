"""
Welcoming Plugin for Discord Bot
Sends welcome messages to new members with basic information
"""

import discord
from discord.ext import commands
import asyncio
import os
import json
from pathlib import Path

import re


def normalize_placeholders(text: str) -> str:
    """Convert [name] placeholders into {name} so .format works, leave existing {} as-is."""
    if not isinstance(text, str):
        return text
    try:
        # convert [name] -> {name}
        out = re.sub(r"\[\s*`?\s*([a-zA-Z0-9_]+)\s*`?\s*\]", r"{\1}", text)
        # convert {`name`} or { `name` } -> {name}
        out = re.sub(r"\{\s*`?\s*([a-zA-Z0-9_]+)\s*`?\s*\}", r"{\1}", out)
        return out
    except Exception:
        return text


# Pull global settings directly as authoritative source when available
try:
    from bot.global_config import load_global_settings
except Exception:
    load_global_settings = None

# Configuration (defaults)
GUILD_ID = 1168883480583745587
WELCOME_CHANNEL_ID = 1168883481410015325  # General channel for welcome messages (optional)
ADMIN_ROLE_ID = 1508759124429639681
DEV_ROLE_ID = 1347589804895768576
# Enable/disable flags (persisted)
WELCOME_ENABLED = True
DM_ENABLED = True
CHANNEL_ENABLED = True
# Message templates (support markdown + placeholders)
CHANNEL_MESSAGE = "👋 Everyone, please welcome {mention} to {guild_name}!"
DM_MESSAGE = "Hi {display_name}, welcome to {guild_name}! Check the rules and say hi in {welcome_channel_mention}"
# Embed templates (JSON-like dict). Keys: title, description, color (int or hex), fields: [{name,value,inline}], thumbnail: {url}, footer: {text,icon_url}
EMBED_TEMPLATE = {
    "title": "🚛 Welcome to Nightwish Trucking!",
    "description": "Hello {mention}! Welcome to our VTC family! 🎉",
    "color": 3447003,
    "fields": [
        {"name": "📋 Getting Started", "value": "• Check out our #rules channel", "inline": False},
        {"name": "🎫 Need Help?", "value": "Use our ticket system for HR / Events", "inline": True},
        {"name": "🚚 Join Our Convoys", "value": "• Check convoy announcements\n• Follow convoy rules", "inline": True}
    ],
    "thumbnail": {"url": "{avatar_url}"},
    "footer": {"text": "Nightwish Trucking • The Greatest Show On Earth"}
}

DM_EMBED_TEMPLATE = {
    "title": "🚛 Welcome to Nightwish Trucking VTC!",
    "description": "Hi {display_name}! Thank you for joining our community! 🎉\n\nHere's everything you need to know to get started:",
    "color": 3066993,
    "fields": [
        {"name": "📋 Server Rules", "value": "• Follow **Discord TOS**\n• Checkout all rules here: {welcome_channel_mention}", "inline": False}
    ],
    "footer": {"text": "Welcome aboard! 🚛 Drive safe and have fun!"}
}

# settings file paths (dashboard writes `<plugin>.py.settings.json`, but plugin-friendly name is `welcoming.settings.json`)
PLUGIN_DIR = Path(__file__).resolve().parent
SETTINGS_PATHS = [
    PLUGIN_DIR / (Path(__file__).name + '.settings.json'),  # welcoming.py.settings.json (dashboard)
    PLUGIN_DIR / 'welcoming.settings.json',  # welcoming.settings.json (friendly)
]

def _choose_settings_path():
    for p in SETTINGS_PATHS:
        if p.exists():
            return p
    # default to dashboard-style path
    return SETTINGS_PATHS[0]


def load_settings_from_file():
    global GUILD_ID, WELCOME_CHANNEL_ID, ADMIN_ROLE_ID, DEV_ROLE_ID, CHANNEL_MESSAGE, DM_MESSAGE, EMBED_TEMPLATE, DM_EMBED_TEMPLATE
    global WELCOME_ENABLED, DM_ENABLED, CHANNEL_ENABLED
    path = _choose_settings_path()
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding='utf-8'))
            if 'GUILD_ID' in data:
                GUILD_ID = int(data['GUILD_ID']) if data['GUILD_ID'] not in (None, '') else GUILD_ID
            if 'WELCOME_CHANNEL_ID' in data:
                WELCOME_CHANNEL_ID = int(data['WELCOME_CHANNEL_ID']) if data['WELCOME_CHANNEL_ID'] not in (None, '') else WELCOME_CHANNEL_ID
            if 'ADMIN_ROLE_ID' in data:
                ADMIN_ROLE_ID = int(data['ADMIN_ROLE_ID']) if data['ADMIN_ROLE_ID'] not in (None, '') else ADMIN_ROLE_ID
            if 'DEV_ROLE_ID' in data:
                DEV_ROLE_ID = int(data['DEV_ROLE_ID']) if data['DEV_ROLE_ID'] not in (None, '') else DEV_ROLE_ID
            # persisted enable/disable flags (support both lower and upper keys)
            if 'welcome_enabled' in data:
                try: WELCOME_ENABLED = bool(data.get('welcome_enabled'))
                except Exception: pass
            if 'dm_enabled' in data:
                try: DM_ENABLED = bool(data.get('dm_enabled'))
                except Exception: pass
            if 'channel_enabled' in data:
                try: CHANNEL_ENABLED = bool(data.get('channel_enabled'))
                except Exception: pass
            if 'WELCOME_ENABLED' in data:
                try: WELCOME_ENABLED = bool(data.get('WELCOME_ENABLED'))
                except Exception: pass
            if 'DM_ENABLED' in data:
                try: DM_ENABLED = bool(data.get('DM_ENABLED'))
                except Exception: pass
            if 'CHANNEL_ENABLED' in data:
                try: CHANNEL_ENABLED = bool(data.get('CHANNEL_ENABLED'))
                except Exception: pass
            # optional message templates (can contain markdown and placeholders)
            if 'CHANNEL_MESSAGE' in data:
                CHANNEL_MESSAGE = data.get('CHANNEL_MESSAGE') or CHANNEL_MESSAGE
            if 'DM_MESSAGE' in data:
                DM_MESSAGE = data.get('DM_MESSAGE') or DM_MESSAGE
            # optional embed templates (JSON objects)
            if 'EMBED_TEMPLATE' in data:
                try:
                    EMBED_TEMPLATE = data.get('EMBED_TEMPLATE') or EMBED_TEMPLATE
                except Exception:
                    pass
            if 'DM_EMBED_TEMPLATE' in data:
                try:
                    DM_EMBED_TEMPLATE = data.get('DM_EMBED_TEMPLATE') or DM_EMBED_TEMPLATE
                except Exception:
                    pass
            print(f"Welcoming: loaded settings from {path}")
        else:
            # write defaults to chosen path
            try:
                path.write_text(json.dumps({
                    'GUILD_ID': GUILD_ID,
                    'WELCOME_CHANNEL_ID': WELCOME_CHANNEL_ID,
                    'ADMIN_ROLE_ID': ADMIN_ROLE_ID,
                    'DEV_ROLE_ID': DEV_ROLE_ID,
                }, indent=2), encoding='utf-8')
            except Exception:
                pass
    except Exception as e:
        print(f"Welcoming: failed to load settings: {e}")

    # Pull global settings from dashboard if available and apply as authoritative
    try:
        if load_global_settings:
            g = load_global_settings() or {}
            # priority: global settings override plugin settings
            if 'GUILD_ID' in g and g['GUILD_ID'] not in (None, ''):
                try: GUILD_ID = int(g['GUILD_ID'])
                except Exception: pass
            if 'WELCOME_CHANNEL_ID' in g and g['WELCOME_CHANNEL_ID'] not in (None, ''):
                try: WELCOME_CHANNEL_ID = int(g['WELCOME_CHANNEL_ID'])
                except Exception: pass
            if 'ADMIN_ROLE_ID' in g and g['ADMIN_ROLE_ID'] not in (None, ''):
                try: ADMIN_ROLE_ID = int(g['ADMIN_ROLE_ID'])
                except Exception: pass
            if 'DEV_ROLE_ID' in g and g['DEV_ROLE_ID'] not in (None, ''):
                try: DEV_ROLE_ID = int(g['DEV_ROLE_ID'])
                except Exception: pass
            # flags
            if 'WELCOME_ENABLED' in g: WELCOME_ENABLED = bool(g['WELCOME_ENABLED'])
            if 'DM_ENABLED' in g: DM_ENABLED = bool(g['DM_ENABLED'])
            if 'CHANNEL_ENABLED' in g: CHANNEL_ENABLED = bool(g['CHANNEL_ENABLED'])
            # message templates
            if 'CHANNEL_MESSAGE' in g and g['CHANNEL_MESSAGE'] is not None: CHANNEL_MESSAGE = g['CHANNEL_MESSAGE']
            if 'DM_MESSAGE' in g and g['DM_MESSAGE'] is not None: DM_MESSAGE = g['DM_MESSAGE']
            # embed templates (allow dict or string)
            if 'EMBED_TEMPLATE' in g and g['EMBED_TEMPLATE'] is not None: EMBED_TEMPLATE = g['EMBED_TEMPLATE']
            if 'DM_EMBED_TEMPLATE' in g and g['DM_EMBED_TEMPLATE'] is not None: DM_EMBED_TEMPLATE = g['DM_EMBED_TEMPLATE']
            print("Welcoming: applied global settings from dashboard")
        else:
            # fallback to environment GUILD_ID if present
            env_gid = os.environ.get('GUILD_ID')
            if env_gid and str(env_gid).strip().isdigit():
                GUILD_ID = int(env_gid)
                print(f"Welcoming: using global GUILD_ID from environment: {GUILD_ID}")
    except Exception:
        pass


# load at import
load_settings_from_file()

def has_admin_permissions(user):
    """Check if user has admin role or higher"""
    if not hasattr(user, 'roles'):
        return False
    # gather role ids as strings to robustly compare against settings (which may be int or str)
    try:
        role_ids = {str(getattr(role, 'id', '')) for role in user.roles}
    except Exception:
        role_ids = set()

    admin_id = str(ADMIN_ROLE_ID) if ADMIN_ROLE_ID is not None else ''
    dev_id = str(DEV_ROLE_ID) if DEV_ROLE_ID is not None else ''

    if admin_id and admin_id in role_ids:
        return True
    if dev_id and dev_id in role_ids:
        return True
    # also allow by common role names
    try:
        if any((getattr(role, 'name', '') or '').lower() in ['admin', 'owner', 'developer'] for role in user.roles):
            return True
    except Exception:
        pass

    return False

def create_welcome_embed(member):
    """Create welcome embed for new member using EMBED_TEMPLATE if present"""
    tpl = EMBED_TEMPLATE or {}
    # allow tpl to be a raw JSON string saved by dashboard; try parse
    if isinstance(tpl, str):
        try:
            tpl = json.loads(tpl)
        except Exception:
            # fall back to treat string as description
            tpl = {"description": tpl}
    title = tpl.get('title')
    description = tpl.get('description')
    color = tpl.get('color')
    try:
        if isinstance(color, str) and color.startswith('#'):
            color_val = int(color.lstrip('#'), 16)
        else:
            color_val = int(color) if color is not None else None
    except Exception:
        color_val = None

    embed = discord.Embed(
        title=(title.format(mention=member.mention, display_name=member.display_name,
                             user_name=member.name, guild_name=member.guild.name if member.guild else '' ) if title else None),
        description=(description.format(mention=member.mention, display_name=member.display_name,
                             user_name=member.name, guild_name=member.guild.name if member.guild else '' ) if description else None),
        color=discord.Color(color_val) if color_val is not None else discord.Color.blue()
    )

    # helper to normalize placeholders using module function
    def _norm_placeholders(text):
        try:
            return normalize_placeholders(text)
        except Exception:
            return text

    for f in tpl.get('fields', []):
        try:
            raw_name = f.get('name')
            raw_value = f.get('value')
            if raw_name:
                raw_name = _norm_placeholders(raw_name)
            if raw_value:
                raw_value = _norm_placeholders(raw_value)
            name = raw_name and raw_name.format(mention=member.mention, display_name=member.display_name, user_name=member.name, guild_name=member.guild.name if member.guild else '')
            value = raw_value and raw_value.format(mention=member.mention, display_name=member.display_name, user_name=member.name, guild_name=member.guild.name if member.guild else '')
            inline = bool(f.get('inline'))
            if name and value:
                embed.add_field(name=name, value=value, inline=inline)
        except Exception:
            continue

    # thumbnail
    try:
        thumb = tpl.get('thumbnail', {})
        if thumb and thumb.get('url'):
            turl = thumb.get('url')
            turl = _norm_placeholders(turl)
            url = turl.format(avatar_url=member.display_avatar.url, guild_icon=member.guild.icon.url if member.guild and member.guild.icon else '')
            embed.set_thumbnail(url=url)
    except Exception:
        try:
            embed.set_thumbnail(url=member.display_avatar.url)
        except Exception:
            pass

    # footer
    try:
        footer = tpl.get('footer', {})
        if footer and footer.get('text'):
            icon = footer.get('icon_url') or (member.guild.icon.url if member.guild and member.guild.icon else None)
            ftext = _norm_placeholders(footer.get('text'))
            embed.set_footer(text=ftext.format(guild_name=member.guild.name if member.guild else ''), icon_url=icon)
        else:
            embed.set_footer(text="Nightwish Trucking • The Greatest Show On Earth", icon_url=member.guild.icon.url if member.guild.icon else None)
    except Exception:
        embed.set_footer(text="Nightwish Trucking • The Greatest Show On Earth")

    return embed

def create_dm_welcome_embed(member):
    """Create DM welcome embed using DM_EMBED_TEMPLATE if present"""
    tpl = DM_EMBED_TEMPLATE or {}
    if isinstance(tpl, str):
        try:
            tpl = json.loads(tpl)
        except Exception:
            tpl = {"description": tpl}
    title = tpl.get('title')
    description = tpl.get('description')
    color = tpl.get('color')
    try:
        if isinstance(color, str) and color.startswith('#'):
            color_val = int(color.lstrip('#'), 16)
        else:
            color_val = int(color) if color is not None else None
    except Exception:
        color_val = None

    embed = discord.Embed(
        title=(title.format(mention=member.mention, display_name=member.display_name,
                             user_name=member.name, guild_name=member.guild.name if member.guild else '' ) if title else None),
        description=(description.format(mention=member.mention, display_name=member.display_name,
                             user_name=member.name, guild_name=member.guild.name if member.guild else '' ) if description else None),
        color=discord.Color(color_val) if color_val is not None else discord.Color.green()
    )

    def _norm_placeholders(text):
        try:
            return normalize_placeholders(text)
        except Exception:
            return text

    for f in tpl.get('fields', []):
        try:
            raw_name = f.get('name')
            raw_value = f.get('value')
            if raw_name:
                raw_name = _norm_placeholders(raw_name)
            if raw_value:
                raw_value = _norm_placeholders(raw_value)
            name = raw_name and raw_name.format(mention=member.mention, display_name=member.display_name, user_name=member.name, guild_name=member.guild.name if member.guild else '')
            value = raw_value and raw_value.format(mention=member.mention, display_name=member.display_name, user_name=member.name, guild_name=member.guild.name if member.guild else '')
            inline = bool(f.get('inline'))
            if name and value:
                embed.add_field(name=name, value=value, inline=inline)
        except Exception:
            continue

    try:
        footer = tpl.get('footer', {})
        if footer and footer.get('text'):
            embed.set_footer(text=footer.get('text'))
        else:
            embed.set_footer(text="Welcome aboard! 🚛 Drive safe and have fun!")
    except Exception:
        embed.set_footer(text="Welcome aboard! 🚛 Drive safe and have fun!")

    try:
        thumb = tpl.get('thumbnail', {})
        if thumb and thumb.get('url'):
            turl = thumb.get('url')
            turl = _norm_placeholders(turl)
            url = turl.format(avatar_url=member.display_avatar.url, guild_icon=member.guild.icon.url if member.guild and member.guild.icon else '')
            embed.set_thumbnail(url=url)
    except Exception:
        try:
            embed.set_thumbnail(url=member.guild.icon.url if member.guild.icon else None)
        except Exception:
            pass

    return embed

class WelcomingCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # initialize from persisted settings
        self.welcome_enabled = WELCOME_ENABLED
        self.dm_enabled = DM_ENABLED
        self.channel_enabled = CHANNEL_ENABLED
        self._settings_mtime = None
        # ensure settings loaded
        load_settings_from_file()
        try:
            p = _choose_settings_path()
            self._settings_mtime = p.stat().st_mtime
        except Exception:
            self._settings_mtime = None
        # start background task to watch settings file (fast polling for near-immediate reloads)
        self._watch_task = asyncio.create_task(self._watch_settings())
        print("Welcoming plugin initialized")

    async def _watch_settings(self):
        while True:
            try:
                try:
                    p = _choose_settings_path()
                    m = p.stat().st_mtime if p.exists() else None
                except Exception:
                    m = None
                if m and m != self._settings_mtime:
                    print("Welcoming: settings file changed, reloading")
                    load_settings_from_file()
                    # update runtime flags from newly loaded settings
                    try:
                        self.welcome_enabled = WELCOME_ENABLED
                        self.dm_enabled = DM_ENABLED
                        self.channel_enabled = CHANNEL_ENABLED
                        print(f"Welcoming: runtime flags updated: welcome={self.welcome_enabled}, dm={self.dm_enabled}, channel={self.channel_enabled}")
                    except Exception:
                        pass
                    self._settings_mtime = m
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(5)

    @commands.Cog.listener()
    async def on_member_join(self, member):
        """Handle new member joins"""
        # Only handle members joining the configured guild
        if member.guild.id != GUILD_ID:
            return
        
        if not self.welcome_enabled:
            return
        
        print(f"Welcome: New member joined: {member} ({member.id})")
        
        # Build template context for messages
        class _SafeDict(dict):
            def __missing__(self, key):
                return ''

        # Send DM welcome message
        if self.dm_enabled:
            try:
                dm_embed = create_dm_welcome_embed(member)
                # try to resolve welcome channel mention
                try:
                    guild = member.guild
                    welcome_chan = guild.get_channel(WELCOME_CHANNEL_ID) if WELCOME_CHANNEL_ID else None
                    welcome_chan_mention = welcome_chan.mention if welcome_chan else ''
                except Exception:
                    welcome_chan_mention = ''

                ctx = _SafeDict({
                    'mention': member.mention,
                    'display_name': member.display_name,
                    'user_name': member.name,
                    'guild_name': member.guild.name if member.guild else '',
                    'member_count': getattr(member.guild, 'member_count', ''),
                    'welcome_channel_mention': welcome_chan_mention,
                })

                try:
                    dm_template = normalize_placeholders(DM_MESSAGE)
                    dm_text = dm_template.format_map(ctx)
                except Exception:
                    dm_text = ''

                if dm_text:
                    await member.send(content=dm_text, embed=dm_embed)
                else:
                    await member.send(embed=dm_embed)

                print(f"Welcome: Sent DM to {member}")
            except discord.Forbidden:
                print(f"Welcome: Cannot send DM to {member} (DMs disabled)")
            except Exception as e:
                print(f"Welcome: Error sending DM to {member}: {e}")
        
        # Send welcome message to channel
        if self.channel_enabled and WELCOME_CHANNEL_ID:
            try:
                guild = self.bot.get_guild(GUILD_ID)
                welcome_channel = guild.get_channel(WELCOME_CHANNEL_ID)
                
                if welcome_channel:
                    welcome_embed = create_welcome_embed(member)
                    # prepare context and render CHANNEL_MESSAGE
                    try:
                        welcome_chan_mention = welcome_channel.mention
                    except Exception:
                        welcome_chan_mention = ''
                    ctx = _SafeDict({
                        'mention': member.mention,
                        'display_name': member.display_name,
                        'user_name': member.name,
                        'guild_name': member.guild.name if member.guild else '',
                        'member_count': getattr(member.guild, 'member_count', ''),
                        'welcome_channel_mention': welcome_chan_mention,
                    })
                    try:
                        ch_template = normalize_placeholders(CHANNEL_MESSAGE)
                        channel_text = ch_template.format_map(ctx)
                    except Exception:
                        channel_text = f"👋 Everyone, please welcome {member.mention} to {member.guild.name if member.guild else 'the server'}!"

                    # send message supporting markdown in content plus embed
                    await welcome_channel.send(content=channel_text, embed=welcome_embed)
                    print(f"Welcome: Sent channel message for {member}")
                else:
                    print(f"Welcome: Channel {WELCOME_CHANNEL_ID} not found")
            except Exception as e:
                print(f"Welcome: Error sending channel message for {member}: {e}")

def setup(bot, global_settings=None):
    # If dashboard passed global settings, merge into plugin settings file
    try:
        if global_settings and isinstance(global_settings, dict):
            path = _choose_settings_path()
            data = {}
            if path.exists():
                try:
                    data = json.loads(path.read_text(encoding='utf-8')) or {}
                except Exception:
                    data = {}
            for k in ('GUILD_ID', 'WELCOME_CHANNEL_ID', 'ADMIN_ROLE_ID', 'DEV_ROLE_ID', 'CHANNEL_MESSAGE', 'DM_MESSAGE', 'EMBED_TEMPLATE', 'DM_EMBED_TEMPLATE', 'welcome_enabled', 'dm_enabled', 'channel_enabled', 'WELCOME_ENABLED', 'DM_ENABLED', 'CHANNEL_ENABLED'):
                if k in global_settings and global_settings[k] is not None:
                    data[k] = global_settings[k]
            try:
                path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
                print(f"Welcoming: merged global settings into {path}")
            except Exception:
                pass
    except Exception:
        pass

    # Add Welcoming Cog
    asyncio.create_task(bot.add_cog(WelcomingCog(bot)))
    
    # Create Welcome management command group
    class WelcomeGroup(discord.app_commands.Group):
        def __init__(self):
            super().__init__(name="welcome", description="Welcome system management commands")

        @discord.app_commands.command(name="toggle", description="Toggle welcome system on/off")
        @discord.app_commands.describe(
            system="Which system to toggle (all/dm/channel)",
            enabled="Enable or disable the system"
        )
        async def toggle_welcome(self, interaction: discord.Interaction, 
                                system: str = "all",
                                enabled: bool = True):
            """Toggle welcome system"""
            if not has_admin_permissions(interaction.user):
                await interaction.response.send_message(f"❌ You need admin permissions to use this command. {interaction.user}, needed role {ADMIN_ROLE_ID}", ephemeral=True)
                return
            
            # Get the welcoming cog
            welcoming_cog = bot.get_cog('WelcomingCog')
            if not welcoming_cog:
                await interaction.response.send_message("❌ Welcoming system not found.", ephemeral=True)
                return
            
            system = system.lower()
            if system == "all":
                welcoming_cog.welcome_enabled = enabled
                welcoming_cog.dm_enabled = enabled
                welcoming_cog.channel_enabled = enabled
                status = "enabled" if enabled else "disabled"
                await interaction.response.send_message(f"✅ Welcome system {status} (all features).", ephemeral=True)
            elif system == "dm":
                welcoming_cog.dm_enabled = enabled
                status = "enabled" if enabled else "disabled"
                await interaction.response.send_message(f"✅ Welcome DM messages {status}.", ephemeral=True)
            elif system == "channel":
                welcoming_cog.channel_enabled = enabled
                status = "enabled" if enabled else "disabled"
                await interaction.response.send_message(f"✅ Welcome channel messages {status}.", ephemeral=True)
            else:
                await interaction.response.send_message("❌ Invalid system. Use: all, dm, or channel", ephemeral=True)

        @discord.app_commands.command(name="test", description="Test welcome message on yourself")
        async def test_welcome(self, interaction: discord.Interaction):
            """Test welcome message"""
            if not has_admin_permissions(interaction.user):
                await interaction.response.send_message(f"❌ You need admin permissions to use this command. {interaction.user}, needed role {ADMIN_ROLE_ID}", ephemeral=True)
                return
            
            try:
                # Test DM
                dm_embed = create_dm_welcome_embed(interaction.user)
                await interaction.user.send(embed=dm_embed)
                
                # Test channel embed
                welcome_embed = create_welcome_embed(interaction.user)
                await interaction.response.send_message("✅ Test welcome message sent! Check your DMs and see the channel preview below:", embed=welcome_embed, ephemeral=True)
                
            except discord.Forbidden:
                await interaction.response.send_message("❌ Cannot send DM - please enable DMs from server members.", ephemeral=True)
            except Exception as e:
                await interaction.response.send_message(f"❌ Error sending test message: {str(e)}", ephemeral=True)

        @discord.app_commands.command(name="reload", description="Reload welcome plugin settings from disk")
        async def reload_settings(self, interaction: discord.Interaction):
            """Force reload plugin settings from the .settings.json file and apply immediately"""
            if not has_admin_permissions(interaction.user):
                await interaction.response.send_message(f"❌ You need admin permissions to use this command. {interaction.user}, needed role {ADMIN_ROLE_ID}", ephemeral=True)
                return
            try:
                load_settings_from_file()
                welcoming_cog = bot.get_cog('WelcomingCog')
                if welcoming_cog:
                    welcoming_cog.welcome_enabled = WELCOME_ENABLED
                    welcoming_cog.dm_enabled = DM_ENABLED
                    welcoming_cog.channel_enabled = CHANNEL_ENABLED
                await interaction.response.send_message(f"✅ Welcome settings reloaded. welcome={WELCOME_ENABLED}, dm={DM_ENABLED}, channel={CHANNEL_ENABLED}", ephemeral=True)
            except Exception as e:
                await interaction.response.send_message(f"❌ Failed to reload settings: {e}", ephemeral=True)

        @discord.app_commands.command(name="status", description="Show welcome system status")
        async def welcome_status(self, interaction: discord.Interaction):
            """Show welcome system status"""
            if not has_admin_permissions(interaction.user):
                await interaction.response.send_message(f"❌ You need admin permissions to use this command. {interaction.user}, needed role {ADMIN_ROLE_ID}", ephemeral=True)
                return
            
            # Get the welcoming cog
            welcoming_cog = bot.get_cog('WelcomingCog')
            if not welcoming_cog:
                await interaction.response.send_message("❌ Welcoming system not found.", ephemeral=True)
                return
            
            embed = discord.Embed(
                title="🚛 Welcome System Status",
                color=discord.Color.blue()
            )
            
            overall_status = "🟢 Enabled" if welcoming_cog.welcome_enabled else "🔴 Disabled"
            dm_status = "🟢 Enabled" if welcoming_cog.dm_enabled else "🔴 Disabled"
            channel_status = "🟢 Enabled" if welcoming_cog.channel_enabled else "🔴 Disabled"
            
            embed.add_field(name="Overall System", value=overall_status, inline=True)
            embed.add_field(name="DM Messages", value=dm_status, inline=True)
            embed.add_field(name="Channel Messages", value=channel_status, inline=True)
            
            guild = interaction.guild
            welcome_channel = guild.get_channel(WELCOME_CHANNEL_ID) if WELCOME_CHANNEL_ID else None
            channel_info = welcome_channel.mention if welcome_channel else "Not configured"
            embed.add_field(name="Welcome Channel", value=channel_info, inline=False)
            
            embed.set_footer(text="Use /welcome toggle to change settings")
            
            await interaction.response.send_message(embed=embed, ephemeral=True)

    # Add the command group to the bot
    bot.tree.add_command(WelcomeGroup())
    
    print("Welcoming plugin loaded successfully")