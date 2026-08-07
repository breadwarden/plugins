"""Automatic moderation for the configured Discord guild."""

import asyncio
import collections
import datetime as dt
import json
import re
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

try:
    import moderation
except Exception:
    moderation = None

PLUGIN_DIR = Path(__file__).resolve().parent
SETTINGS_PATH = PLUGIN_DIR / "automod.py.settings.json"

GUILD_ID = None
ADMIN_ROLE_ID = None
DEV_ROLE_ID = None
LOG_CHANNEL_ID = None
BANNED_WORDS = []
ALLOWED_INVITE_GUILD_ID = None
SPAM_MESSAGE_LIMIT = 5
SPAM_INTERVAL_SECONDS = 8
WARN_THRESHOLD_FOR_TIMEOUT = 3
IGNORED_CHANNEL_IDS = []
WHITELISTED_USER_IDS = []
WHITELISTED_CHANNEL_IDS = []
ALLOW_LINKS = False
ENABLED = True

_INVITE_RE = re.compile(r"(?:https?://)?(?:discord\.gg|discord(?:app)?\.com/invite)/([A-Za-z0-9-]+)", re.IGNORECASE)
_URL_RE = re.compile(r"https?://[^\s]+", re.IGNORECASE)
_LEET = str.maketrans({"@": "a", "4": "a", "3": "e", "1": "i", "0": "o", "$": "s", "5": "s", "7": "t"})


def _read_settings():
    try:
        if SETTINGS_PATH.exists():
            return json.loads(SETTINGS_PATH.read_text(encoding="utf-8")) or {}
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Automod: failed to read settings: {exc}")
    return {}


def _write_settings(data):
    SETTINGS_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


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
    global GUILD_ID, ADMIN_ROLE_ID, DEV_ROLE_ID, LOG_CHANNEL_ID
    global BANNED_WORDS, ALLOWED_INVITE_GUILD_ID, SPAM_MESSAGE_LIMIT
    global SPAM_INTERVAL_SECONDS, WARN_THRESHOLD_FOR_TIMEOUT, IGNORED_CHANNEL_IDS
    global WHITELISTED_USER_IDS, WHITELISTED_CHANNEL_IDS, ALLOW_LINKS, ENABLED

    data = _read_settings()
    global_data = load_global_settings() if load_global_settings else {}
    GUILD_ID = _as_int(global_data.get("GUILD_ID") or data.get("GUILD_ID"))
    ADMIN_ROLE_ID = _as_int(data.get("ADMIN_ROLE_ID"))
    DEV_ROLE_ID = _as_int(data.get("DEV_ROLE_ID"))
    LOG_CHANNEL_ID = _as_int(data.get("LOG_CHANNEL_ID"))
    BANNED_WORDS = [str(word).strip() for word in data.get("BANNED_WORDS", []) if str(word).strip()]
    ALLOWED_INVITE_GUILD_ID = _as_int(data.get("ALLOWED_INVITE_GUILD_ID"))
    SPAM_MESSAGE_LIMIT = max(1, _as_int(data.get("SPAM_MESSAGE_LIMIT")) or 5)
    SPAM_INTERVAL_SECONDS = max(1, _as_int(data.get("SPAM_INTERVAL_SECONDS")) or 8)
    WARN_THRESHOLD_FOR_TIMEOUT = max(0, _as_int(data.get("WARN_THRESHOLD_FOR_TIMEOUT")) or 3)
    IGNORED_CHANNEL_IDS = _as_ids(data.get("IGNORED_CHANNEL_IDS", []))
    WHITELISTED_USER_IDS = _as_ids(data.get("WHITELISTED_USER_IDS", []))
    WHITELISTED_CHANNEL_IDS = _as_ids(data.get("WHITELISTED_CHANNEL_IDS", []))
    ALLOW_LINKS = bool(data.get("ALLOW_LINKS", False))
    ENABLED = bool(data.get("ENABLED", True))


def _normalise(text):
    return re.sub(r"[^a-z0-9]+", "", text.lower().translate(_LEET))


def _has_permission(user):
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


def _setting_ids(key):
    return [str(value) for value in _read_settings().get(key, [])]


class AutomodGroup(app_commands.Group):
    def __init__(self, bot):
        super().__init__(name="automod", description="Configure automatic moderation")
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
                    print("Automod: settings reloaded")
                await asyncio.sleep(2)
            except asyncio.CancelledError:
                return
            except Exception as exc:
                print(f"Automod: settings watcher error: {exc}")
                await asyncio.sleep(5)

    async def _check(self, interaction):
        if not interaction.guild or (GUILD_ID and interaction.guild_id != GUILD_ID):
            await interaction.response.send_message("This command is not enabled in this server.", ephemeral=True)
            return False
        if not _has_permission(interaction.user):
            await interaction.response.send_message("You do not have permission to configure automod.", ephemeral=True)
            return False
        return True

    @app_commands.command(name="toggle", description="Enable or disable automatic moderation")
    async def toggle(self, interaction: discord.Interaction):
        if not await self._check(interaction):
            return
        data = _read_settings()
        data["ENABLED"] = not ENABLED
        _write_settings(data)
        load_settings()
        await interaction.response.send_message(f"Automod {'enabled' if ENABLED else 'disabled'}.", ephemeral=True)

    @app_commands.command(name="addword", description="Add a banned word or phrase")
    @app_commands.describe(word="Word or phrase to block")
    async def addword(self, interaction: discord.Interaction, word: str):
        if not await self._check(interaction):
            return
        word = word.strip()
        if not word or len(word) > 100:
            await interaction.response.send_message("Word must be between 1 and 100 characters.", ephemeral=True)
            return
        data = _read_settings()
        words = [str(item) for item in data.get("BANNED_WORDS", [])]
        if word.casefold() not in {item.casefold() for item in words}:
            words.append(word)
        data["BANNED_WORDS"] = words
        _write_settings(data)
        load_settings()
        await interaction.response.send_message(f"Added `{word}` to banned words.", ephemeral=True)

    @app_commands.command(name="removeword", description="Remove a banned word or phrase")
    @app_commands.describe(word="Word or phrase to remove")
    async def removeword(self, interaction: discord.Interaction, word: str):
        if not await self._check(interaction):
            return
        data = _read_settings()
        data["BANNED_WORDS"] = [item for item in data.get("BANNED_WORDS", []) if str(item).casefold() != word.strip().casefold()]
        _write_settings(data)
        load_settings()
        await interaction.response.send_message(f"Removed `{word}` from banned words.", ephemeral=True)

    @app_commands.command(name="listwords", description="List banned words and phrases")
    async def listwords(self, interaction: discord.Interaction):
        if not await self._check(interaction):
            return
        words = ", ".join(f"`{word}`" for word in BANNED_WORDS) or "(none)"
        await interaction.response.send_message(f"Banned words: {words}", ephemeral=True)

    @app_commands.command(name="whitelist", description="Add or remove a whitelisted channel or user")
    @app_commands.describe(target="Channel or user ID", target_type="What should be whitelisted", action="Add or remove")
    @app_commands.choices(
        target_type=[app_commands.Choice(name="Channel", value="channel"), app_commands.Choice(name="User", value="user")],
        action=[app_commands.Choice(name="Add", value="add"), app_commands.Choice(name="Remove", value="remove")],
    )
    async def whitelist(self, interaction: discord.Interaction, target: str, target_type: app_commands.Choice[str], action: app_commands.Choice[str]):
        if not await self._check(interaction):
            return
        target_id = _as_int(target)
        if target_id is None:
            await interaction.response.send_message("Target must be a numeric Discord ID.", ephemeral=True)
            return
        key = "WHITELISTED_CHANNEL_IDS" if target_type.value == "channel" else "WHITELISTED_USER_IDS"
        data = _read_settings()
        ids = set(_as_ids(data.get(key, [])))
        if action.value == "add":
            ids.add(target_id)
        else:
            ids.discard(target_id)
        data[key] = [str(value) for value in sorted(ids)]
        _write_settings(data)
        load_settings()
        await interaction.response.send_message(f"{target_type.name} whitelist updated.", ephemeral=True)

    @app_commands.command(name="status", description="Show automatic moderation status")
    async def status(self, interaction: discord.Interaction):
        if not await self._check(interaction):
            return
        await interaction.response.send_message(
            f"Enabled: {ENABLED}\nSpam: {SPAM_MESSAGE_LIMIT} messages/{SPAM_INTERVAL_SECONDS}s\n"
            f"Timeout threshold: {WARN_THRESHOLD_FOR_TIMEOUT}\nBanned words: {len(BANNED_WORDS)}\n"
            f"Ignored channels: {len(IGNORED_CHANNEL_IDS)}",
            ephemeral=True,
        )


class AutomodListener:
    def __init__(self, bot):
        self.bot = bot
        self._recent_messages = collections.defaultdict(collections.deque)
        self._recent_violations = collections.defaultdict(collections.deque)

    def _warning_count(self, user_id):
        if not moderation or not hasattr(moderation, "_ensure_data"):
            return 0
        cases = moderation._ensure_data().get("cases", [])
        return sum(
            1
            for case in cases
            if case.get("user_id") == str(user_id) and case.get("action") in {"WARN", "AUTOMOD"}
        )

    async def _unban_after(self, guild_id, user_id):
        await asyncio.sleep(24 * 60 * 60)
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return
        try:
            await guild.unban(discord.Object(id=user_id), reason="Automod one-day ban expired")
        except (discord.NotFound, discord.Forbidden, discord.HTTPException) as exc:
            print(f"Automod: failed to remove one-day ban for {user_id}: {exc}")

    def _in_scope(self, message):
        guild = getattr(message, "guild", None)
        return bool(ENABLED and guild and GUILD_ID and guild.id == GUILD_ID)

    def _is_whitelisted(self, message):
        return message.channel.id in IGNORED_CHANNEL_IDS or message.channel.id in WHITELISTED_CHANNEL_IDS or message.author.id in WHITELISTED_USER_IDS

    def _spam(self, message):
        now = dt.datetime.now(dt.timezone.utc).timestamp()
        recent = self._recent_messages[message.author.id]
        while recent and now - recent[0] > SPAM_INTERVAL_SECONDS:
            recent.popleft()
        recent.append(now)
        return len(recent) >= SPAM_MESSAGE_LIMIT

    async def _invite_allowed(self, message):
        match = _INVITE_RE.search(message.content)
        if not match:
            return False
        if not ALLOWED_INVITE_GUILD_ID:
            return False
        try:
            invite = await self.bot.fetch_invite(match.group(1), with_counts=False)
            return bool(invite.guild and invite.guild.id == ALLOWED_INVITE_GUILD_ID)
        except (discord.HTTPException, discord.NotFound, discord.Forbidden):
            return False

    async def _violation(self, message):
        content = _normalise(message.content)
        for word in BANNED_WORDS:
            if _normalise(word) and _normalise(word) in content:
                return f"Banned word: {word}"
        if _INVITE_RE.search(message.content):
            if await self._invite_allowed(message):
                return None
            return "Unapproved Discord invite"
        if not ALLOW_LINKS and _URL_RE.search(message.content):
            return "Links are not allowed"
        if self._spam(message):
            return "Spam detected"
        return None

    async def _record_violation(self, message, reason):
        now = dt.datetime.now(dt.timezone.utc).timestamp()
        violations = self._recent_violations[message.author.id]
        while violations and now - violations[0] > SPAM_INTERVAL_SECONDS:
            violations.popleft()
        violations.append(now)

        case = None
        if moderation and hasattr(moderation, "_new_case"):
            moderator = self.bot.user or message.author
            case = moderation._new_case("AUTOMOD", message.author.id, message.author, moderator, reason)
            if hasattr(moderation, "_send_log"):
                await moderation._send_log(message.guild, case)
            if hasattr(moderation, "_send_warn_dm"):
                await moderation._send_warn_dm(message.author, message.guild, case)

        log_channel = message.guild.get_channel(LOG_CHANNEL_ID) if LOG_CHANNEL_ID else None
        if log_channel:
            embed = discord.Embed(title="Automod violation", color=discord.Color.red(), timestamp=dt.datetime.now(dt.timezone.utc))
            embed.add_field(name="Member", value=f"{message.author} (`{message.author.id}`)", inline=True)
            embed.add_field(name="Channel", value=getattr(message.channel, "mention", str(message.channel)), inline=True)
            embed.add_field(name="Reason", value=reason, inline=False)
            if case:
                embed.set_footer(text=f"Case #{case['id']:03d}")
            try:
                await log_channel.send(embed=embed)
            except discord.HTTPException as exc:
                print(f"Automod: failed to send violation log: {exc}")

        warning_count = self._warning_count(message.author.id)
        if warning_count > 30:
            action = "ban"
            escalation = (
                f"{message.author.mention}, you have more than 30 warnings. "
                "You will be banned for 1 day. Further violations may lead to additional moderation action."
            )
        elif warning_count > 15:
            action = "kick"
            escalation = (
                f"{message.author.mention}, you have more than 15 warnings. "
                "You will be kicked. Further violations may lead to a ban."
            )
        elif warning_count > 5:
            action = "timeout"
            escalation = (
                f"{message.author.mention}, you have more than 5 warnings. "
                "You will be timed out for 20 minutes or longer. Further violations may lead to a ban."
            )
        else:
            action = None
            escalation = None

        if action:
            try:
                async with message.channel.typing():
                    await asyncio.sleep(2)
                    await message.channel.send(escalation, delete_after=60)
                moderation_reason = f"Automod escalation at {warning_count} warnings: {reason}"
                if action == "ban":
                    await message.author.ban(reason=moderation_reason)
                    asyncio.create_task(self._unban_after(message.guild.id, message.author.id))
                elif action == "kick":
                    await message.author.kick(reason=moderation_reason)
                else:
                    await message.author.timeout(dt.timedelta(minutes=20), reason=moderation_reason)
                violations.clear()
            except (discord.Forbidden, discord.HTTPException) as exc:
                print(f"Automod: failed to apply {action} to {message.author}: {exc}")

    async def on_message(self, message):
        if getattr(message.author, "bot", False) or not self._in_scope(message) or self._is_whitelisted(message):
            return
        if _has_permission(message.author):
            return
        reason = await self._violation(message)
        if not reason:
            return
        try:
            await message.delete()
        except (discord.Forbidden, discord.NotFound, discord.HTTPException):
            pass
        await self._record_violation(message, reason)
        try:
            warning = await message.channel.send(f"{message.author.mention}, message removed: {reason}.", delete_after=5)
            del warning
        except discord.HTTPException:
            pass


def _register_listener(bot, listener):
    bot.add_listener(listener.on_message, "on_message")


def setup(bot, global_settings=None):
    if getattr(bot, "_automod_plugin_loaded", False):
        return
    load_settings()
    group = AutomodGroup(bot)
    guild = discord.Object(id=GUILD_ID) if GUILD_ID else None
    bot.tree.remove_command("automod", guild=guild)
    bot.tree.add_command(group, guild=guild)
    _register_listener(bot, AutomodListener(bot))
    bot._automod_plugin_loaded = True
    bot._automod_plugin_group = group
    print("Automod: loaded")
