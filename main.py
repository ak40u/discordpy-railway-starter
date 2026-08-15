import logging
import os
import sys
import json
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands


# =========================
# SETTINGS
# =========================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)

log = logging.getLogger("bot")

TOKEN = os.environ.get("DISCORD_TOKEN")

if not TOKEN:
    log.error("DISCORD_TOKEN is not set in Railway Variables.")
    sys.exit(1)


# =========================
# DISCORD BOT
# =========================

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


# =========================
# REMINDERS
# =========================

REMINDERS_FILE = "reminders.json"
TIMEZONE = ZoneInfo("Asia/Tbilisi")


def load_reminders():
    if not os.path.exists(REMINDERS_FILE):
        return []

    try:
        with open(
            REMINDERS_FILE,
            "r",
            encoding="utf-8"
        ) as file:
            return json.load(file)

    except Exception as e:
        log.error(
            "Error loading reminders: %s",
            e
        )
        return []


def save_reminders():
    try:
        with open(
            REMINDERS_FILE,
            "w",
            encoding="utf-8"
        ) as file:
            json.dump(
                reminders,
                file,
                ensure_ascii=False,
                indent=2
            )

    except Exception as e:
        log.error(
            "Error saving reminders: %s",
            e
        )


reminders = load_reminders()


# =========================
# BOT READY
# =========================

@bot.event
async def on_ready():

    log.info(
        "Logged in as %s (%s)",
        bot.user,
        bot.user.id
    )

    if not hasattr(
        bot,
        "reminder_task"
    ):
        bot.reminder_task = asyncio.create_task(
            reminder_loop()
        )


# =========================
# PING
# =========================

@bot.command()
async def ping(ctx):

    await ctx.send(
        f"pong ({bot.latency * 1000:.0f} ms)"
    )


# =========================
# HELLO
# =========================

@bot.command()
async def hello(ctx):

    await ctx.send(
        "Hello! 👋"
    )
    
@bot.command(name="remind")
async def test_remind(ctx, *args):
    await ctx.send("✅ REMIND COMMAND WORKS!")

# =========================
# REMIND
# =========================

@bot.command()
async def remind(
    ctx,
    member: discord.Member = None,
    time: str = None,
    *message
):

    # No user
    if member is None:

        await ctx.send(
            "❌ Please mention the client.\n\n"
            "Example:\n"
            "`!remind @Client 19:00 2000 payment`"
        )

        return

    # No time
    if time is None:

        await ctx.send(
            "❌ Please specify the time.\n\n"
            "Example:\n"
            "`!remind @Client 19:00 2000 payment`"
        )

        return

    # No message
    if not message:

        await ctx.send(
            "❌ Please specify the payment.\n\n"
            "Example:\n"
            "`!remind @Client 19:00 2000 payment`"
        )

        return

    # Check time format
    try:

        datetime.strptime(
            time,
            "%H:%M"
        )

    except ValueError:

        await ctx.send(
            "❌ Invalid time format.\n"
            "Use HH:MM.\n\n"
            "Example: `19:00`"
        )

        return

    # Create reminder
    reminder = {

        "id": max(
            [r["id"] for r in reminders],
            default=0
        ) + 1,

        "user_id": member.id,

        "time": time,

        "message": " ".join(message),

        "last_sent": None
    }

    reminders.append(
        reminder
    )

    save_reminders()

    await ctx.send(

        "✅ **Reminder created!**\n\n"

        f"👤 Client: {member.mention}\n"

        f"⏰ Time: **{time}**\n"

        f"💰 Payment: **{' '.join(message)}**\n"

        "🔁 Repeats every day."
    )


# =========================
# LIST REMINDERS
# =========================

@bot.command()
async def reminders(ctx):

    if not reminders:

        await ctx.send(
            "📭 There are no active reminders."
        )

        return

    text = (
        "📋 **Active Reminders**\n\n"
    )

    for reminder in reminders:

        text += (

            f"**#{reminder['id']}**\n"

            f"👤 <@{reminder['user_id']}>\n"

            f"⏰ **{reminder['time']}**\n"

            f"💰 {reminder['message']}\n\n"
        )

    await ctx.send(
        text
    )


# =========================
# CANCEL REMINDER
# =========================

@bot.command()
async def cancel(
    ctx,
    reminder_id: int = None
):

    if reminder_id is None:

        await ctx.send(
            "❌ Please provide the reminder ID.\n\n"
            "Example:\n"
            "`!cancel 1`"
        )

        return

    for reminder in reminders:

        if reminder["id"] == reminder_id:

            reminders.remove(
                reminder
            )

            save_reminders()

            await ctx.send(

                f"🗑️ Reminder "
                f"**#{reminder_id}** "
                f"has been cancelled."
            )

            return

    await ctx.send(
        "❌ Reminder not found."
    )


# =========================
# REMINDER SYSTEM
# =========================

async def reminder_loop():

    await bot.wait_until_ready()

    log.info(
        "Reminder system started."
    )

    while not bot.is_closed():

        now
