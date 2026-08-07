"""Moderation commands and persistent case history."""

import asyncio
import datetime as dt
import json
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
SETTINGS_PATH = PLUGIN_DIR / "moderation.py.settings.json"
DATA_PATH = PLUGIN_DIR / "moderation_data.json"

GUILD_ID = None
ENABLED = True
MOD_ROLE_IDS = []
ADMIN_ROLE_IDS = []
ADMIN_ROLE_ID = None
DEV_ROLE_ID = None
MOD_LOG_CHANNEL_ID = None


def _read_json(path, default):
    try:
        if path.exists():
            value = json.loads(path.read_text(encoding="utf-8"))
            return value if value is not None else default
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Moderation: failed to read {path.name}: {exc}")
    return default


def _write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def _as_int(value):
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _as_ids(value):
    if not isinstance(value, list):
        return []
    return [number for item in value if (number := _as_int(item)) is not None]


def load_settings():
    global GUILD_ID, ENABLED, MOD_ROLE_IDS, ADMIN_ROLE_IDS
    global ADMIN_ROLE_ID, DEV_ROLE_ID, MOD_LOG_CHANNEL_ID
    data = _read_json(SETTINGS_PATH, {})
    globals_data = load_global_settings() if load_global_settings else {}
    GUILD_ID = _as_int(globals_data.get("GUILD_ID") or data.get("GUILD_ID"))
    ENABLED = bool(data.get("ENABLED", True))
    MOD_ROLE_IDS = _as_ids(data.get("MOD_ROLE_IDS", []))
    ADMIN_ROLE_IDS = _as_ids(data.get("ADMIN_ROLE_IDS", []))
    ADMIN_ROLE_ID = _as_int(data.get("ADMIN_ROLE_ID"))
    DEV_ROLE_ID = _as_int(data.get("DEV_ROLE_ID"))
    MOD_LOG_CHANNEL_ID = _as_int(data.get("MOD_LOG_CHANNEL_ID"))


def _ensure_data():
    data = _read_json(DATA_PATH, {"next_case_id": 1, "cases": []})
    data.setdefault("next_case_id", 1)
    data.setdefault("cases", [])
    return data


def _has_mod_access(member):
    if getattr(member.guild_permissions, "administrator", False):
        return True
    role_ids = {role.id for role in getattr(member, "roles", [])}
    configured_ids = set(MOD_ROLE_IDS + ADMIN_ROLE_IDS)
    configured_ids.update(role_id for role_id in (ADMIN_ROLE_ID, DEV_ROLE_ID) if role_id)
    return bool(role_ids.intersection(configured_ids)) or any(
        role.name.lower() in {"admin", "owner", "developer"}
        for role in getattr(member, "roles", [])
    )


def _can_act_on(actor, target):
    if actor.id == target.id:
        return False
    if getattr(target, "guild_permissions", None) and target.guild_permissions.administrator:
        return False
    return actor.top_role > target.top_role


def _reason(reason):
    return (reason or "No reason provided").strip()[:500]


def _new_case(action, target_id, target_name, moderator, reason, extra=None):
    data = _ensure_data()
    case = {
        "id": int(data["next_case_id"]),
        "action": action.upper(),
        "user_id": str(target_id),
        "user_name": str(target_name),
        "moderator_id": str(moderator.id),
        "moderator_name": str(moderator),
        "reason": _reason(reason),
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    if extra:
        case.update(extra)
    data["next_case_id"] = case["id"] + 1
    data["cases"].append(case)
    _write_json(DATA_PATH, data)
    return case


async def _send_log(guild, case):
    if not MOD_LOG_CHANNEL_ID:
        return
    channel = guild.get_channel(MOD_LOG_CHANNEL_ID)
    if not channel:
        return
    embed = discord.Embed(title=f"Case #{case['id']:03d} {case['action']}", color=discord.Color.orange(), timestamp=dt.datetime.fromisoformat(case["timestamp"]))
    embed.add_field(name="Member", value=f"<@{case['user_id']}> (`{case['user_id']}`)", inline=True)
    embed.add_field(name="Moderator", value=f"<@{case['moderator_id']}> (`{case['moderator_id']}`)", inline=True)
    embed.add_field(name="Reason", value=case["reason"], inline=False)
    try:
        await channel.send(embed=embed)
    except discord.HTTPException as exc:
        print(f"Moderation: failed to send log: {exc}")


async def _send_warn_dm(member, guild, case):
    embed = discord.Embed(
        title="You received a warning",
        description=f"You have been warned in **{guild.name}**.",
        color=discord.Color.orange(),
        timestamp=dt.datetime.fromisoformat(case["timestamp"]),
    )
    embed.add_field(name="Reason", value=case["reason"], inline=False)
    embed.add_field(name="Case", value=f"#{case['id']:03d}", inline=True)
    embed.set_footer(text="Please contact the server staff if you believe this was a mistake.")
    try:
        await member.send(embed=embed)
    except discord.HTTPException as exc:
        print(f"Moderation: failed to DM warning to {member}:", exc)


class ModerationGroup(app_commands.Group):
    def __init__(self, bot):
        super().__init__(name="mod", description="Moderation commands")
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
                await asyncio.sleep(2)
            except asyncio.CancelledError:
                return
            except Exception as exc:
                print(f"Moderation: settings watcher error: {exc}")
                await asyncio.sleep(5)

    async def _check(self, interaction):
        if not ENABLED:
            await interaction.response.send_message("Moderation is disabled.", ephemeral=True)
            return False
        if GUILD_ID and interaction.guild_id != GUILD_ID:
            await interaction.response.send_message("This command is not enabled in this server.", ephemeral=True)
            return False
        if not interaction.guild or not _has_mod_access(interaction.user):
            await interaction.response.send_message("You do not have a configured moderator role.", ephemeral=True)
            return False
        return True

    async def _record(self, interaction, action, target, reason, extra=None):
        case = _new_case(action, target.id, target, interaction.user, reason, extra)
        await _send_log(interaction.guild, case)
        return case

    @app_commands.command(name="warn", description="Warn a member and record a case")
    @app_commands.describe(member="Member to warn", reason="Reason for the warning")
    async def warn(self, interaction: discord.Interaction, member: discord.Member, reason: str):
        if not await self._check(interaction): return
        if not _can_act_on(interaction.user, member):
            await interaction.response.send_message("You cannot moderate this member.", ephemeral=True); return
        case = await self._record(interaction, "WARN", member, reason)
        await _send_warn_dm(member, interaction.guild, case)
        await interaction.response.send_message(f"Warned {member.mention}. Case #{case['id']:03d}.", ephemeral=True)

    @app_commands.command(name="warnings", description="Show a member's warning history")
    @app_commands.describe(member="Member whose warnings should be shown")
    async def warnings(self, interaction: discord.Interaction, member: discord.Member):
        if not await self._check(interaction): return
        cases = [case for case in _ensure_data()["cases"] if case["user_id"] == str(member.id) and case["action"] == "WARN"]
        if not cases:
            await interaction.response.send_message(f"{member} has no warnings.", ephemeral=True); return
        text = "\n".join(f"#{case['id']:03d} · {case['reason']} · <t:{int(dt.datetime.fromisoformat(case['timestamp']).timestamp())}:R>" for case in cases[-10:])
        await interaction.response.send_message(f"Warnings for {member.mention}:\n{text}", ephemeral=True)

    @app_commands.command(name="clearwarnings", description="Clear a member's warning history")
    @app_commands.describe(member="Member whose warnings should be cleared")
    async def clearwarnings(self, interaction: discord.Interaction, member: discord.Member):
        if not await self._check(interaction): return
        data = _ensure_data()
        warnings = [case for case in data["cases"] if case["user_id"] == str(member.id) and case["action"] == "WARN"]
        data["cases"] = [case for case in data["cases"] if not (case["user_id"] == str(member.id) and case["action"] == "WARN")]
        _write_json(DATA_PATH, data)
        case = await self._record(interaction, "CLEARWARNINGS", member, "Warnings cleared")
        await interaction.response.send_message(f"Cleared {len(warnings)} warnings for {member.mention}. Case #{case['id']:03d}.", ephemeral=True)

    @app_commands.command(name="timeout", description="Timeout a member")
    @app_commands.describe(member="Member to timeout", minutes="Timeout length in minutes", reason="Reason")
    async def timeout(self, interaction: discord.Interaction, member: discord.Member, minutes: app_commands.Range[int, 1, 40320], reason: str):
        if not await self._check(interaction): return
        if not _can_act_on(interaction.user, member):
            await interaction.response.send_message("You cannot moderate this member.", ephemeral=True); return
        await member.timeout(dt.timedelta(minutes=minutes), reason=_reason(reason))
        case = await self._record(interaction, "TIMEOUT", member, reason, {"duration_minutes": minutes})
        await interaction.response.send_message(f"Timed out {member.mention} for {minutes} minutes. Case #{case['id']:03d}.", ephemeral=True)

    @app_commands.command(name="untimeout", description="Remove a member timeout")
    @app_commands.describe(member="Member to untimeout", reason="Reason")
    async def untimeout(self, interaction: discord.Interaction, member: discord.Member, reason: str = "Timeout removed"):
        if not await self._check(interaction): return
        if not _can_act_on(interaction.user, member):
            await interaction.response.send_message("You cannot moderate this member.", ephemeral=True); return
        await member.timeout(None, reason=_reason(reason))
        case = await self._record(interaction, "UNTIMEOUT", member, reason)
        await interaction.response.send_message(f"Removed timeout from {member.mention}. Case #{case['id']:03d}.", ephemeral=True)

    @app_commands.command(name="kick", description="Kick a member")
    @app_commands.describe(member="Member to kick", reason="Reason")
    async def kick(self, interaction: discord.Interaction, member: discord.Member, reason: str):
        if not await self._check(interaction): return
        if not _can_act_on(interaction.user, member):
            await interaction.response.send_message("You cannot moderate this member.", ephemeral=True); return
        case = await self._record(interaction, "KICK", member, reason)
        await member.kick(reason=_reason(reason))
        await interaction.response.send_message(f"Kicked {member}. Case #{case['id']:03d}.", ephemeral=True)

    @app_commands.command(name="ban", description="Ban a member")
    @app_commands.describe(member="Member to ban", reason="Reason")
    async def ban(self, interaction: discord.Interaction, member: discord.Member, reason: str):
        if not await self._check(interaction): return
        if not _can_act_on(interaction.user, member):
            await interaction.response.send_message("You cannot moderate this member.", ephemeral=True); return
        case = await self._record(interaction, "BAN", member, reason)
        await member.ban(reason=_reason(reason))
        await interaction.response.send_message(f"Banned {member}. Case #{case['id']:03d}.", ephemeral=True)

    @app_commands.command(name="unban", description="Unban a user by ID")
    @app_commands.describe(user_id="Discord user ID", reason="Reason")
    async def unban(self, interaction: discord.Interaction, user_id: str, reason: str):
        if not await self._check(interaction): return
        target_id = _as_int(user_id)
        if target_id is None:
            await interaction.response.send_message("User ID must be numeric.", ephemeral=True); return
        user = await self.bot.fetch_user(target_id)
        await interaction.guild.unban(user, reason=_reason(reason))
        case = await self._record(interaction, "UNBAN", user, reason)
        await interaction.response.send_message(f"Unbanned {user}. Case #{case['id']:03d}.", ephemeral=True)

    @app_commands.command(name="purge", description="Delete recent messages")
    @app_commands.describe(amount="Number of messages to delete", reason="Reason")
    async def purge(self, interaction: discord.Interaction, amount: app_commands.Range[int, 1, 100], reason: str = "Message cleanup"):
        if not await self._check(interaction): return
        if not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message("This command requires a text channel.", ephemeral=True); return
        await interaction.response.defer(ephemeral=True)
        deleted = await interaction.channel.purge(limit=amount)
        case = await self._record(interaction, "PURGE", interaction.user, reason, {"amount": len(deleted), "channel_id": str(interaction.channel.id)})
        await interaction.followup.send(f"Deleted {len(deleted)} messages. Case #{case['id']:03d}.", ephemeral=True)

    @app_commands.command(name="slowmode", description="Set channel slowmode")
    @app_commands.describe(seconds="Slowmode seconds, 0 disables it", reason="Reason")
    async def slowmode(self, interaction: discord.Interaction, seconds: app_commands.Range[int, 0, 21600], reason: str = "Channel slowmode update"):
        if not await self._check(interaction): return
        if not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message("This command requires a text channel.", ephemeral=True); return
        await interaction.channel.edit(slowmode_delay=seconds, reason=_reason(reason))
        case = await self._record(interaction, "SLOWMODE", interaction.user, reason, {"seconds": seconds, "channel_id": str(interaction.channel.id)})
        await interaction.response.send_message(f"Slowmode set to {seconds}s. Case #{case['id']:03d}.", ephemeral=True)


def setup(bot, global_settings=None):
    load_settings()
    group = ModerationGroup(bot)
    guild = discord.Object(id=GUILD_ID) if GUILD_ID else None
    bot.tree.remove_command("mod", guild=guild)
    bot.tree.add_command(group, guild=guild)
    print("Moderation: loaded")
