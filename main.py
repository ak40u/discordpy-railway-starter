"""A minimal Discord bot.

Out of the box this needs nothing but a token: the sample commands are slash
commands, which do not require any privileged intent. Prefix commands like
`!ping` read message text, which Discord gates behind the Message Content
intent - set ENABLE_MESSAGE_CONTENT=true and enable the intent in the Developer
Portal (Bot -> Privileged Gateway Intents) if you want them.
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

WANTS_MESSAGE_CONTENT = os.environ.get("ENABLE_MESSAGE_CONTENT", "").lower() in {"1", "true", "yes"}


def build_bot(message_content: bool) -> commands.Bot:
    intents = discord.Intents.default()
    intents.message_content = message_content
    bot = commands.Bot(command_prefix="!", intents=intents)

    @bot.event
    async def on_ready():
        # Slash commands live in the command tree and have to be registered with
        # Discord once per start. A global sync can take up to an hour to appear
        # in every server; the commands themselves work as soon as it lands.
        try:
            synced = await bot.tree.sync()
            log.info("Registered %d slash command(s)", len(synced))
        except discord.HTTPException:
            log.exception("Could not register the slash commands")
        log.info("Logged in as %s (id %s)", bot.user, bot.user.id)
        log.info("Invite it to a server, then type /ping")
        if not message_content:
            log.info(
                "Prefix commands such as !ping are off: they need the Message Content "
                "intent. Set ENABLE_MESSAGE_CONTENT=true and enable the intent in the "
                "Developer Portal to turn them on."
            )

    @bot.tree.command(name="ping", description="Replies with the round-trip latency")
    async def ping_slash(interaction: discord.Interaction):
        await interaction.response.send_message(f"pong ({bot.latency * 1000:.0f} ms)")

    @bot.tree.command(name="hello", description="Replies with a greeting")
    async def hello_slash(interaction: discord.Interaction):
        await interaction.response.send_message("Choo choo! 🚅")

    @bot.command(name="ping")
    async def ping_prefix(ctx: commands.Context):
        """Replies with the round-trip latency."""
        await ctx.send(f"pong ({bot.latency * 1000:.0f} ms)")

    @bot.command(name="hello")
    async def hello_prefix(ctx: commands.Context):
        await ctx.send("Choo choo! 🚅")

    return bot


def run(message_content: bool) -> None:
    build_bot(message_content).run(TOKEN, log_handler=None)


if __name__ == "__main__":
    try:
        try:
            run(WANTS_MESSAGE_CONTENT)
        except discord.PrivilegedIntentsRequired:
            # Asked for Message Content but the portal toggle is off. Coming up
            # without it beats exiting: the slash commands still work, and the
            # log says exactly which switch is missing.
            log.warning(
                "The Message Content intent is not enabled for this application, so "
                "prefix commands stay off. Enable it in the Developer Portal under "
                "Bot -> Privileged Gateway Intents. Starting with slash commands only."
            )
            run(False)
    except discord.LoginFailure:
        log.error(
            "Discord rejected the token. Copy it again from the Developer Portal "
            "and update the DISCORD_TOKEN variable."
        )
        sys.exit(1)
