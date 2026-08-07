"""Guild-scoped XP and leveling plugin."""

import asyncio
import datetime as dt
import json
import random
from pathlib import Path

import discord
from discord import app_commands

try:
    from bot.global_config import load_global_settings
except Exception:
    try:
        from global_config import load_global_settings
    except Exception:
        load_global_settings = None

PLUGIN_DIR = Path(__file__).resolve().parent
SETTINGS_PATH = PLUGIN_DIR / "leveling.py.settings.json"
DATA_PATH = PLUGIN_DIR / "leveling.json"

GUILD_ID = None
ADMIN_ROLE_ID = None
DEV_ROLE_ID = None
MIN_XP = 10
MAX_XP = 20
XP_COOLDOWN_SECONDS = 60
BASE_XP = 100
LEVELUP_CHANNEL_ID = None
LEVEL_ROLE_REWARDS = {}
IGNORED_CHANNEL_IDS = []
ENABLED = True


def _read_json(path, default):
    try:
        if path.exists():
            value = json.loads(path.read_text(encoding="utf-8"))
            return value if value is not None else default
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Leveling: failed to read {path.name}: {exc}")
    return default


def _write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _as_int(value, default=None):
    try:
        return int(value) if value not in (None, "") else default
    except (TypeError, ValueError):
        return default


def _as_ids(value):
    if not isinstance(value, list):
        return []
    return [number for item in value if (number := _as_int(item)) is not None]


def load_settings():
    global GUILD_ID, ADMIN_ROLE_ID, DEV_ROLE_ID, MIN_XP, MAX_XP
    global XP_COOLDOWN_SECONDS, BASE_XP, LEVELUP_CHANNEL_ID, LEVEL_ROLE_REWARDS
    global IGNORED_CHANNEL_IDS, ENABLED

    data = _read_json(SETTINGS_PATH, {})
    global_data = load_global_settings() if load_global_settings else {}
    GUILD_ID = _as_int(global_data.get("GUILD_ID") or data.get("GUILD_ID"))
    ADMIN_ROLE_ID = _as_int(data.get("ADMIN_ROLE_ID"))
    DEV_ROLE_ID = _as_int(data.get("DEV_ROLE_ID"))
    MIN_XP = max(0, _as_int(data.get("MIN_XP"), 10))
    MAX_XP = max(MIN_XP, _as_int(data.get("MAX_XP"), 20))
    XP_COOLDOWN_SECONDS = max(0, _as_int(data.get("XP_COOLDOWN_SECONDS"), 60))
    BASE_XP = max(1, _as_int(data.get("BASE_XP"), 100))
    LEVELUP_CHANNEL_ID = _as_int(data.get("LEVELUP_CHANNEL_ID"))
    LEVEL_ROLE_REWARDS = {
        str(level): role_id
        for level, role_id in (data.get("LEVEL_ROLE_REWARDS", {}) or {}).items()
        if _as_int(level) is not None and _as_int(role_id) is not None
    }
    IGNORED_CHANNEL_IDS = _as_ids(data.get("IGNORED_CHANNEL_IDS", []))
    ENABLED = bool(data.get("ENABLED", True))


def level_up_xp(level):
    return BASE_XP * level * level


def level_for_xp(xp):
    level = 0
    while level_up_xp(level + 1) <= xp:
        level += 1
    return level


def _guild_data(guild_id):
    data = _read_json(DATA_PATH, {})
    if not isinstance(data, dict):
        data = {}
    guild = data.setdefault(str(guild_id), {})
    return data, guild


def _profile(guild_id, user_id):
    data, guild = _guild_data(guild_id)
    profile = guild.setdefault(str(user_id), {"xp": 0, "level": 0, "last_message_ts": 0})
    profile.setdefault("xp", 0)
    profile.setdefault("level", level_for_xp(int(profile["xp"])))
    profile.setdefault("last_message_ts", 0)
    return data, guild, profile


def _save_profile(guild_id, user_id, profile):
    data, guild = _guild_data(guild_id)
    guild[str(user_id)] = profile
    _write_json(DATA_PATH, data)


def _has_admin_permission(user):
    if not getattr(user, "guild", None):
        return False
    permissions = getattr(user, "guild_permissions", None)
    roles = getattr(user, "roles", [])
    role_ids = {role.id for role in roles}
    return bool(
        getattr(permissions, "administrator", False)
        or (ADMIN_ROLE_ID and ADMIN_ROLE_ID in role_ids)
        or (DEV_ROLE_ID and DEV_ROLE_ID in role_ids)
        or any(role.name.lower() in {"admin", "owner", "developer"} for role in roles)
    )


async def _apply_level_roles(guild, member, level):
    reward_ids = {int(role_id) for role_level, role_id in LEVEL_ROLE_REWARDS.items() if int(role_level) <= level}
    configured_ids = {int(role_id) for role_id in LEVEL_ROLE_REWARDS.values()}
    current_ids = {role.id for role in member.roles}
    add_ids = reward_ids - current_ids
    remove_ids = (configured_ids - reward_ids) & current_ids
    for role_id in add_ids:
        role = guild.get_role(role_id)
        if role:
            try:
                await member.add_roles(role, reason=f"Level {level} reward")
            except discord.HTTPException as exc:
                print(f"Leveling: failed to add reward role {role_id}: {exc}")
    for role_id in remove_ids:
        role = guild.get_role(role_id)
        if role:
            try:
                await member.remove_roles(role, reason=f"Level {level} reward update")
            except discord.HTTPException as exc:
                print(f"Leveling: failed to remove reward role {role_id}: {exc}")


class LevelingListener:
    def __init__(self, bot):
        self.bot = bot
        self._write_lock = asyncio.Lock()

    async def _send_level_up(self, message, member, level, xp):
        channel = message.guild.get_channel(LEVELUP_CHANNEL_ID) if LEVELUP_CHANNEL_ID else message.channel
        if not channel:
            return
        embed = discord.Embed(
            title="Level up!",
            description=f"{member.mention} reached **level {level}**.",
            color=discord.Color.gold(),
        )
        embed.add_field(name="XP", value=str(xp), inline=True)
        embed.add_field(name="Next level", value=str(level_up_xp(level + 1)), inline=True)
        try:
            await channel.send(embed=embed)
        except discord.HTTPException as exc:
            print(f"Leveling: failed to send level-up message: {exc}")

    async def on_message(self, message):
        if getattr(message.author, "bot", False):
            return
        guild = getattr(message, "guild", None)
        if not ENABLED or not guild or not GUILD_ID or guild.id != GUILD_ID:
            return
        if message.channel.id in IGNORED_CHANNEL_IDS:
            return
        if not str(getattr(message, "content", "")).strip():
            return

        now = dt.datetime.now(dt.timezone.utc).timestamp()
        async with self._write_lock:
            data, guild_data, profile = _profile(guild.id, message.author.id)
            if now - float(profile.get("last_message_ts", 0)) < XP_COOLDOWN_SECONDS:
                return
            old_level = int(profile.get("level", level_for_xp(int(profile.get("xp", 0)))))
            profile["xp"] = int(profile.get("xp", 0)) + random.randint(MIN_XP, MAX_XP)
            profile["level"] = level_for_xp(profile["xp"])
            profile["last_message_ts"] = now
            guild_data[str(message.author.id)] = profile
            _write_json(DATA_PATH, data)

        if profile["level"] > old_level:
            await _apply_level_roles(guild, message.author, profile["level"])
            await self._send_level_up(message, message.author, profile["level"], profile["xp"])


class LevelingGroup(app_commands.Group):
    def __init__(self, bot):
        super().__init__(name="level", description="View and configure XP levels")
        self.bot = bot
        load_settings()
        self._settings_mtime = None
        self._watch_task = asyncio.create_task(self._watch_settings())

    def unload(self):
        self._watch_task.cancel()

    async def _watch_settings(self):
        while True:
            try:
                mtime = SETTINGS_PATH.stat().st_mtime if SETTINGS_PATH.exists() else None
                if mtime != self._settings_mtime:
                    load_settings()
                    self._settings_mtime = mtime
                    print("Leveling: settings reloaded")
                await asyncio.sleep(2)
            except asyncio.CancelledError:
                return
            except Exception as exc:
                print(f"Leveling: settings watcher error: {exc}")
                await asyncio.sleep(5)

    async def _check_guild(self, interaction):
        if not interaction.guild or (GUILD_ID and interaction.guild_id != GUILD_ID):
            await interaction.response.send_message("This command is not enabled in this server.", ephemeral=True)
            return False
        return True

    async def _check_admin(self, interaction):
        if not await self._check_guild(interaction):
            return False
        if not _has_admin_permission(interaction.user):
            await interaction.response.send_message("You do not have permission to manage leveling.", ephemeral=True)
            return False
        return True

    @app_commands.command(name="rank", description="Show your or another member's rank")
    @app_commands.describe(member="Member whose rank should be shown")
    async def rank(self, interaction: discord.Interaction, member: discord.Member = None):
        if not await self._check_guild(interaction):
            return
        member = member or interaction.user
        _, _, profile = _profile(interaction.guild.id, member.id)
        embed = discord.Embed(title=f"{member.display_name}'s rank", color=discord.Color.blurple())
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Level", value=str(profile["level"]), inline=True)
        embed.add_field(name="XP", value=str(profile["xp"]), inline=True)
        embed.add_field(name="Next level", value=str(level_up_xp(profile["level"] + 1)), inline=True)
        embed.set_footer(text=f"User ID: {member.id}")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="leaderboard", description="Show the top 10 members by XP")
    async def leaderboard(self, interaction: discord.Interaction):
        if not await self._check_guild(interaction):
            return
        _, guild_data = _guild_data(interaction.guild.id)
        entries = sorted(guild_data.items(), key=lambda item: int(item[1].get("xp", 0)), reverse=True)[:10]
        lines = []
        for index, (user_id, profile) in enumerate(entries, 1):
            member = interaction.guild.get_member(int(user_id))
            name = member.display_name if member else f"User {user_id}"
            lines.append(f"**{index}.** {name} - Level {profile.get('level', 0)} ({profile.get('xp', 0)} XP)")
        embed = discord.Embed(title="Level leaderboard", description="\n".join(lines) or "No XP recorded yet.", color=discord.Color.gold())
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="setxp", description="Set a member's XP")
    @app_commands.describe(member="Member whose XP should be changed", xp="New XP amount")
    async def setxp(self, interaction: discord.Interaction, member: discord.Member, xp: app_commands.Range[int, 0, 1000000000]):
        if not await self._check_admin(interaction):
            return
        data, guild_data, profile = _profile(interaction.guild.id, member.id)
        profile["xp"] = xp
        profile["level"] = level_for_xp(xp)
        guild_data[str(member.id)] = profile
        _write_json(DATA_PATH, data)
        await _apply_level_roles(interaction.guild, member, profile["level"])
        await interaction.response.send_message(f"Set {member.mention} to level {profile['level']} ({xp} XP).", ephemeral=True)

    @app_commands.command(name="toggle", description="Enable or disable XP earning")
    async def toggle(self, interaction: discord.Interaction):
        if not await self._check_admin(interaction):
            return
        data = _read_json(SETTINGS_PATH, {})
        data["ENABLED"] = not ENABLED
        _write_json(SETTINGS_PATH, data)
        load_settings()
        await interaction.response.send_message(f"Leveling {'enabled' if ENABLED else 'disabled'}.", ephemeral=True)

    @app_commands.command(name="setchannel", description="Set the level-up announcement channel")
    @app_commands.describe(channel="Channel for level-up messages; choose the current channel to override")
    async def setchannel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if not await self._check_admin(interaction):
            return
        data = _read_json(SETTINGS_PATH, {})
        data["LEVELUP_CHANNEL_ID"] = str(channel.id)
        _write_json(SETTINGS_PATH, data)
        load_settings()
        await interaction.response.send_message(f"Level-up channel set to {channel.mention}.", ephemeral=True)


def setup(bot, global_settings=None):
    if getattr(bot, "_leveling_plugin_loaded", False):
        return
    load_settings()
    group = LevelingGroup(bot)
    guild = discord.Object(id=GUILD_ID) if GUILD_ID else None
    bot.tree.remove_command("level", guild=guild)
    bot.tree.add_command(group, guild=guild)
    listener = LevelingListener(bot)
    bot.add_listener(listener.on_message, "on_message")
    bot._leveling_plugin_loaded = True
    bot._leveling_plugin_group = group
    print("Leveling: loaded")
