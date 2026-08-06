"""
Base plugin template.
Copy this file to a new name without the leading underscore, then customize it.
"""

import asyncio
import json
from pathlib import Path

import discord
from discord.ext import commands

try:
    from bot.global_config import load_global_settings
except Exception:
    load_global_settings = None

PLUGIN_DIR = Path(__file__).resolve().parent
PLUGIN_NAME = Path(__file__).stem
SETTINGS_PATH = PLUGIN_DIR / f"{PLUGIN_NAME}.settings.json"

# Keep plugin-specific values here; shared IDs belong in global_settings.json.
GUILD_ID = None
ENABLED = True
MESSAGE = "Hello {mention}!"


def normalize_placeholders(text):
    if not isinstance(text, str):
        return text
    return text.replace("[mention]", "{mention}")


def load_settings():
    global GUILD_ID, ENABLED, MESSAGE
    data = {}
    try:
        if SETTINGS_PATH.exists():
            data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8")) or {}
    except (OSError, json.JSONDecodeError) as exc:
        print(f"{PLUGIN_NAME}: failed to read settings: {exc}")

    global_settings = load_global_settings() if load_global_settings else {}
    guild_id = global_settings.get("GUILD_ID") or data.get("GUILD_ID")
    try:
        GUILD_ID = int(guild_id) if guild_id not in (None, "") else None
    except (TypeError, ValueError):
        GUILD_ID = None

    if "ENABLED" in data:
        ENABLED = bool(data["ENABLED"])
    if "MESSAGE" in data and data["MESSAGE"] is not None:
        MESSAGE = str(data["MESSAGE"])


class BasePluginCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._settings_mtime = None
        load_settings()
        self._watch_task = asyncio.create_task(self._watch_settings())

    async def _watch_settings(self):
        while True:
            try:
                mtime = SETTINGS_PATH.stat().st_mtime if SETTINGS_PATH.exists() else None
                if mtime != self._settings_mtime:
                    load_settings()
                    self._settings_mtime = mtime
                    print(f"{PLUGIN_NAME}: settings reloaded")
                await asyncio.sleep(2)
            except asyncio.CancelledError:
                return
            except Exception as exc:
                print(f"{PLUGIN_NAME}: settings watcher error: {exc}")
                await asyncio.sleep(5)

    @commands.Cog.listener()
    async def on_member_join(self, member):
        if not ENABLED or GUILD_ID is None or member.guild.id != GUILD_ID:
            return

        context = {
            "mention": member.mention,
            "display_name": member.display_name,
            "user_name": member.name,
            "guild_name": member.guild.name,
        }
        content = normalize_placeholders(MESSAGE).format_map(
            _SafeContext(context)
        )
        await member.guild.system_channel.send(content=content)

    @discord.app_commands.command(name="status", description="Show this plugin status")
    async def status(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            f"{PLUGIN_NAME}: enabled={ENABLED}, guild_id={GUILD_ID}",
            ephemeral=True,
        )


class _SafeContext(dict):
    def __missing__(self, key):
        return ""


def setup(bot, global_settings=None):
    load_settings()
    asyncio.create_task(bot.add_cog(BasePluginCog(bot)))
    print(f"{PLUGIN_NAME}: loaded")
