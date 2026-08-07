# plugins

Plugins (cogs) for a Discord bot, built on top of `discord.py`.

> **This repository does not contain a runnable bot.** It only holds plugin modules that are loaded by a bot application living in a **separate repository**. On its own, the code here has nothing to attach to and will not run.

## Overview

Each plugin is a self-contained Python module (a `discord.py` cog) paired with a `*.settings.json` config file of the same name. The bot repository is responsible for discovering the files in `plugins/`, loading them via each module's `setup()` function, and providing shared/global configuration (most importantly `GUILD_ID`) through environment variables or a `global_settings.json`.

## Repository structure

```
plugins/
├── plugin template/
│   ├── _plugin_template.py            # base cog skeleton to copy for new plugins
│   └── _plugin_template.settings.json # matching example settings file
└── plugins/
    ├── ai_chat.py                     # AI-powered auto-replies in a designated channel
    ├── ai_chat.py.settings.json
    ├── automod.py                     # automatic filtering (spam, banned words, invites)
    ├── automod.py.settings.json
    ├── captcha.py                     # onboarding verification (captcha challenge)
    ├── captcha.py.settings.json
    ├── leveling.py                    # XP / activity leveling system
    ├── leveling.py.settings.json
    ├── moderation.py                  # kick/ban/timeout/warn moderation commands
    ├── moderation.py.settings.json
    ├── reaction_roles.py              # self-service roles via message reactions
    ├── reaction_roles.json            # stored reaction-role embed configurations
    ├── send_message.py                # admin slash commands to send messages/files as the bot
    ├── send_message.py.settings.json
    ├── welcoming.py                   # welcome messages (channel + DM) for new members
    └── welcoming.py.settings.json
```

Files prefixed with `_` (like `_plugin_template.py`) are templates and are not meant to be loaded directly — copy them to a new file without the underscore.

## Plugins

### `ai_chat.py`
Provides AI-powered auto-replies in a single designated channel, using the OpenAI API.

- Listens for `on_message` in `AI_ALLOWED_CHANNEL_ID` and replies with generated responses, with a short per-channel cooldown to avoid spamming.
- Maps the server structure (channels/categories) on load so replies can reference and link to relevant channels.
- Reads the API key exclusively from the `OPENAI_API_KEY` environment variable — never hardcoded or stored in settings.
- Slash commands (`/ai` group): `/ai ban`, `/ai unban`, `/ai list` — manage which channels are excluded from AI responses (Dev-role restricted).

### `automod.py`
Automatically filters messages for spam, banned words/phrases, and Discord invite links.

- Listens for `on_message` and takes action (e.g. deletes the message) when a rule is triggered.
- Banned words/phrases are managed at runtime and persisted per guild.
- Slash commands (`/automod` group): `/automod toggle`, `/automod addword`, `/automod removeword`, `/automod listwords`, `/automod whitelist`, `/automod status`.

### `captcha.py`
Requires new members to pass a captcha challenge before they gain access to the server.

- Listens for `on_member_join` and starts a verification flow in a dedicated channel.
- Supports multiple challenge types: `text`, `math`, `pattern`, `question`, with configurable `difficulty`, `timeout_minutes`, `max_attempts`, and an `image_chance` for image-based challenges.
- Grants a `VERIFIED_ROLE_ID` on success and optionally removes/assigns an `UNVERIFIED_ROLE_ID`.
- Slash commands: `/toggle`, `/verify`, `/refresh`, `/status`, `/config`, `/toggle_type`.

### `leveling.py`
Awards XP for chat activity and tracks member levels/leaderboards.

- Listens for `on_message` and grants XP per message (with a per-user cooldown to prevent farming).
- Announces level-ups to a configurable channel.
- Slash commands (`/level` group): `/level rank`, `/level leaderboard`, `/level setxp`, `/level toggle`, `/level setchannel`.

### `moderation.py`
Core moderation toolkit for staff: warnings, timeouts, kicks, bans, and message purges.

- Slash commands (`/mod` group): `/mod warn`, `/mod warnings`, `/mod clearwarnings`, `/mod timeout`, `/mod untimeout`, `/mod kick`, `/mod ban`, `/mod unban`, `/mod purge`, `/mod slowmode`.
- Warning history is recorded per member and can be reviewed or cleared by staff.

### `reaction_roles.py`
Lets members grab or remove roles by reacting to a bot-posted embed message.

- Listens for `on_raw_reaction_add` / `on_raw_reaction_remove`.
- Configurations (which message maps to which emoji → role) are persisted in `reaction_roles.json`, keyed by `channel_id_message_id`.
- Slash commands: `/create`, `/add`, `/remove`, `/list`, `/image`, `/delete`.

### `send_message.py`
Admin/dev utility for having the bot post content on demand.

- Slash commands: `/sendmsg` (send a message to a specific channel) and `/sendfile` (split a long text file into multiple messages).
- Restricted to users with the administrator permission, `ADMIN_ROLE_ID`, `DEV_ROLE_ID`, or a role named `admin`/`owner`/`developer`.

### `welcoming.py`
Sends a welcome message to new members, in the server channel and/or as a DM.

- Listens for `on_member_join`; supports separate templates for channel and DM messages, with optional embeds.
- Placeholders such as `{mention}`, `{display_name}`, `{guild_name}`, `{member_count}` are supported in message templates (both `{name}` and `[name]` syntax are normalized).
- Slash commands: `/toggle`, `/test`, `/reload`, `/status`.

### `plugin template/_plugin_template.py`
Minimal cog skeleton demonstrating the conventions every plugin follows:

- Loads its own `*.settings.json`, falling back to shared values from `global_settings.json` when available (e.g. `GUILD_ID`).
- Watches its settings file for changes every 2 seconds and hot-reloads without a bot restart.
- Exposes a `setup(bot, global_settings=None)` entry point and a basic `/status` command.

## Configuration

Every plugin reads its config from a `*.settings.json` file with the same base name as the `.py` file (e.g. `captcha.py` → `captcha.py.settings.json`). Common fields across plugins:

| Field | Description |
|---|---|
| `GUILD_ID` | Discord server (guild) ID the plugin operates in. Usually inherited from the host bot's environment/global settings rather than set per plugin. |
| `ADMIN_ROLE_ID` / `DEV_ROLE_ID` | Role IDs allowed to use privileged slash commands. |
| `ENABLED` / `*_ENABLED` | Master on/off switch for the plugin's behavior. |
| Plugin-specific keys | e.g. `CAPTCHA_CHANNEL_ID`, `VERIFIED_ROLE_ID`, `WELCOME_CHANNEL_ID`, `CHANNEL_MESSAGE`, `DM_MESSAGE`, `AI_ALLOWED_CHANNEL_ID`, `LOG_CHANNEL_ID`, `BANNED_WORDS` — see each plugin's own settings file for the full list. |

`GUILD_ID` in particular is resolved with the following priority: environment variable set by the host bot → `global_settings.json` → local plugin `settings.json`. This lets a single bot deployment drive all plugins from one shared guild configuration.

Secrets (such as `OPENAI_API_KEY` for `ai_chat.py`) are never stored in a settings file — they are read from environment variables (e.g. a `plugins/.env` loaded by the host bot) only.

## Adding a new plugin

1. Copy `plugin template/_plugin_template.py` into `plugins/` under a new name (no leading underscore).
2. Implement your plugin's logic and create a matching `<name>.py.settings.json` file next to it.
3. Keep IDs that are shared across the whole bot (like `GUILD_ID`) sourced from the global settings, and use the local settings file only for values specific to that plugin.
4. Make sure the module exposes `setup(bot, global_settings=None)` so the host bot's loader can pick it up.
5. If the plugin registers slash commands, expose them through an `app_commands.Group` and rely on the host bot's guild-scoped sync (`bot.tree.sync(guild=discord.Object(id=GUILD_ID))`) so new commands appear on the server immediately after a restart, rather than syncing globally.

## Note

This repository is intentionally scoped to plugins only. The bot process itself — the loader, global configuration, command sync, and startup logic — lives in a separate, related repository.
New repository will be uploaded shortly, and yes you need to use the dashboard for controll its easier
