
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
    ├── captcha.py                     # onboarding verification (captcha challenge)
    ├── captcha.py.settings.json
    ├── reaction_roles.py              # self-service roles via message reactions
    ├── reaction_roles.json            # stored reaction-role embed configurations
    ├── send_message.py                # admin slash commands to send messages/files as the bot
    ├── send_message.py.settings.json
    ├── welcoming.py                   # welcome messages (channel + DM) for new members
    └── welcoming.py.settings.json
```

Files prefixed with `_` (like `_plugin_template.py`) are templates and are not meant to be loaded directly — copy them to a new file without the underscore.

## Plugins

### `captcha.py`
Requires new members to pass a captcha challenge before they gain access to the server.

- Listens for `on_member_join` and starts a verification flow in a dedicated channel.
- Supports multiple challenge types: `text`, `math`, `pattern`, `question`, with configurable `difficulty`, `timeout_minutes`, `max_attempts`, and an `image_chance` for image-based challenges.
- Grants a `VERIFIED_ROLE_ID` on success and optionally removes/assigns an `UNVERIFIED_ROLE_ID`.
- Slash commands: `/toggle`, `/verify`, `/refresh`, `/status`, `/config`, `/toggle_type`.

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
| Plugin-specific keys | e.g. `CAPTCHA_CHANNEL_ID`, `VERIFIED_ROLE_ID`, `WELCOME_CHANNEL_ID`, `CHANNEL_MESSAGE`, `DM_MESSAGE` — see each plugin's own settings file for the full list. |

`GUILD_ID` in particular is resolved with the following priority: environment variable set by the host bot → `global_settings.json` → local plugin `settings.json`. This lets a single bot deployment drive all plugins from one shared guild configuration.

## Adding a new plugin

1. Copy `plugin template/_plugin_template.py` into `plugins/` under a new name (no leading underscore).
2. Implement your plugin's logic and create a matching `<name>.py.settings.json` file next to it.
3. Keep IDs that are shared across the whole bot (like `GUILD_ID`) sourced from the global settings, and use the local settings file only for values specific to that plugin.
4. Make sure the module exposes `setup(bot, global_settings=None)` so the host bot's loader can pick it up.

## Note

This repository is intentionally scoped to plugins only. The bot process itself — the loader, global configuration, command sync, and startup logic — lives in a separate, related repository.
