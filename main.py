"""A minimal Discord bot.

Requires the "Message Content" privileged intent, which you enable in the
Discord Developer Portal under Bot -> Privileged Gateway Intents.
"""

import logging
import os
import sys

import discord
from discord.ext import commands

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("bot")

TOKEN = os.environ.get("DISCORD_TOKEN")
if not TOKEN:
    log.error(
        "DISCORD_TOKEN is not set. Add it as a service variable in Railway: "
        "Discord Developer Portal -> your application -> Bot -> Reset Token."
    )
    sys.exit(1)

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    log.info("Logged in as %s (id %s)", bot.user, bot.user.id)
    log.info("Invite it to a server, then send: !ping")


@bot.command()
async def ping(ctx: commands.Context):
    """Replies with the round-trip latency."""
    await ctx.send(f"pong ({bot.latency * 1000:.0f} ms)")


@bot.command()
async def hello(ctx: commands.Context):
    await ctx.send("Choo choo! 🚅")


if __name__ == "__main__":
    try:
        bot.run(TOKEN, log_handler=None)
    except discord.LoginFailure:
        log.error(
            "Discord rejected the token. Copy it again from the Developer Portal "
            "and update the DISCORD_TOKEN variable."
        )
        sys.exit(1)
    except discord.PrivilegedIntentsRequired:
        log.error(
            "The Message Content intent is not enabled for this application. "
            "Enable it in the Developer Portal under Bot -> Privileged Gateway Intents."
        )
        sys.exit(1)
