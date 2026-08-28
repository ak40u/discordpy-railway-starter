# Discord bot starter for Railway (discord.py)

A minimal Discord bot that actually builds: current `discord.py`, a pinned Python
runtime, slash commands that need no privileged intent, and clear errors when the
token is wrong.

[![Deploy on Railway](https://railway.com/button.svg)](https://railway.com/templates)

## Why this exists

The widely used discord.py starter on Railway freezes its whole 2022 dependency
tree in `requirements.txt` — `aiohttp==3.8.3`, `frozenlist==1.3.3`, `yarl==1.8.2`
and friends. Those versions have no wheels for Python 3.12+, so pip falls back to
compiling them, and the C sources use CPython internals that no longer exist:

```
frozenlist/_frozenlist.c:8088:45: error: 'PyLongObject' has no member named 'ob_digit'
frozenlist/_frozenlist.c:7723:27: error: too few arguments to function '_PyLong_AsByteArray'
error: command '/usr/bin/gcc' failed with exit code 1
ERROR: Failed building wheel for frozenlist
```

The build fails before the bot ever runs.

Here `requirements.txt` declares only the direct dependency and lets pip resolve
the rest, and `.python-version` fixes the runtime so a builder upgrade cannot move
it underneath you.

## Setup

1. Create an application at the [Discord Developer Portal](https://discord.com/developers/applications).
2. Under **Bot**, reset the token and copy it.
3. Set `DISCORD_TOKEN` in Railway.
4. Under **OAuth2 → URL Generator**, pick scopes `bot` and `applications.commands`,
   grant *Send Messages*, and open the generated URL to invite it.

Type `/ping` in any channel it can see. A global slash command registration can
take up to an hour to reach every server the first time.

## Commands

| Command | Does |
|---------|------|
| `/ping` | Replies with the gateway latency |
| `/hello` | Replies with a greeting |

Add your own in `main.py` with the `@bot.tree.command()` decorator.

### Prefix commands

`!ping` and `!hello` are defined too, but reading message text requires the
**Message Content** privileged intent. To use them, enable it in the Developer
Portal under **Bot → Privileged Gateway Intents** and set
`ENABLE_MESSAGE_CONTENT=true`. If the variable is on while the portal switch is
off, the bot says so in the log and starts with slash commands only instead of
failing the deployment.

## Run locally

```bash
pip install -r requirements.txt
DISCORD_TOKEN=your-token python main.py
```

## Configuration

| Variable | Required | Purpose |
|----------|----------|---------|
| `DISCORD_TOKEN` | yes | Bot token from the Developer Portal |
| `ENABLE_MESSAGE_CONTENT` | no | `true` turns on prefix commands; needs the Message Content intent |

## License

MIT
