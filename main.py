import asyncio
from datetime import datetime
import json
import logging
import os
import sys
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands

# =========================
# SETTINGS
# =========================

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
)

log = logging.getLogger("bot")

TOKEN = os.environ.get("DISCORD_TOKEN")

if not TOKEN:
    log.error("DISCORD_TOKEN is not set in Railway Variables.")
    sys.exit(1)


# =========================
# DISCORD
# =========================

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)


# =========================
# REMINDER STORAGE
# =========================

REMINDERS_FILE = "reminders.json"
TIMEZONE = ZoneInfo("Asia/Tbilisi")


def load_reminders():
    if not os.path.exists(REMINDERS_FILE):
        return []

    try:
        with open(REMINDERS_FILE, "r", encoding="utf-8") as file:
            return json.load(file)

    except Exception as e:
        log.error("Could not load reminders: %s", e)
        return []


def save_reminders():
    try:
        with open(REMINDERS_FILE, "w", encoding="utf-8") as file:
            json.dump(reminders, file, ensure_ascii=False, indent=2)

    except Exception as e:
        log.error("Could not save reminders: %s", e)


reminders = load_reminders()


# =========================
# BOT READY
# =========================

@bot.event
async def on_ready():
    log.info("Logged in as %s (ID: %s)", bot.user, bot.user.id)

    if not hasattr(bot, "reminder_task"):
        bot.reminder_task = asyncio.create_task(reminder_loop())


# =========================
# PING
# =========================

@bot.command()
async def ping(ctx):
    await ctx.send(f"pong ({bot.latency * 1000:.0f} ms)")


# =========================
# HELLO
# =========================

@bot.command()
async def hello(ctx):
    await ctx.send("Hello! 👋")


# =========================
# CREATE REMINDER (RESTRICTED)
# =========================

@bot.command()
@commands.has_role(1538234465992577186)
async def remind(
    ctx, 
    member: discord.Member = None, 
    time: str = None, 
    start_date: str = None, 
    end_date: str = None, 
    *message
):
    # Check member
    if member is None:
        await ctx.send(
            "❌ **Invalid client.**\n\n"
            "Please mention a real Discord user.\n\n"
            "Example:\n"
            "`!remind @Client 19:00 2026-08-15 2026-09-15 2000 payment`"
        )
        return

    # Check time
    if time is None:
        await ctx.send(
            "❌ **Time is missing.**\n\n"
            "Example:\n"
            "`!remind @Client 19:00 2026-08-15 2026-09-15 2000 payment`"
        )
        return

    # Check start date
    if start_date is None:
        await ctx.send(
            "❌ **Start date is missing.** Use YYYY-MM-DD format.\n\n"
            "Example:\n"
            "`!remind @Client 19:00 2026-08-15 2026-09-15 2000 payment`"
        )
        return

    # Check end date
    if end_date is None:
        await ctx.send(
            "❌ **End date is missing.** Use YYYY-MM-DD format.\n\n"
            "Example:\n"
            "`!remind @Client 19:00 2026-08-15 2026-09-15 2000 payment`"
        )
        return

    # Check message
    if not message:
        await ctx.send(
            "❌ **Payment information is missing.**\n\n"
            "Example:\n"
            "`!remind @Client 19:00 2026-08-15 2026-09-15 2000 payment`"
        )
        return

    # Validate time format (HH:MM)
    try:
        datetime.strptime(time, "%H:%M")
    except ValueError:
        await ctx.send(
            "❌ **Invalid time.** Use HH:MM format (e.g. `19:00`)."
        )
        return

    # Validate start date format (YYYY-MM-DD)
    try:
        datetime.strptime(start_date, "%Y-%m-%d")
    except ValueError:
        await ctx.send(
            "❌ **Invalid start date.** Use YYYY-MM-DD format (e.g. `2026-08-15`)."
        )
        return

    # Validate end date format (YYYY-MM-DD)
    try:
        datetime.strptime(end_date, "%Y-%m-%d")
    except ValueError:
        await ctx.send(
            "❌ **Invalid end date.** Use YYYY-MM-DD format (e.g. `2026-09-15`)."
        )
        return

    # Create reminder object
    reminder = {
        "id": max([r["id"] for r in reminders], default=0) + 1,
        "user_id": member.id,
        "time": time,
        "start_date": start_date,
        "end_date": end_date,
        "message": " ".join(message),
        "last_sent": None,
    }

    reminders.append(reminder)
    save_reminders()

    await ctx.send(
        "✅ **Reminder created!**\n\n"
        f"👤 Client: {member.mention}\n"
        f"⏰ Time: **{time}**\n"
        f"📅 Period: From **{start_date}** to **{end_date}**\n"
        f"💰 Payment: **{' '.join(message)}**\n"
        "🔁 Daily reminder"
    )


# =========================
# SHOW REMINDERS (RESTRICTED)
# =========================

@bot.command(name="reminders")
@commands.has_role(1538234465992577186)
async def show_reminders(ctx):
    if not reminders:
        await ctx.send("📭 **There are no active reminders.**")
        return

    text = "📋 **Active Reminders**\n\n"

    for reminder in reminders:
        start = reminder.get("start_date", "N/A")
        end = reminder.get("end_date", "N/A")
        text += (
            f"**#{reminder['id']}**\n"
            f"👤 <@{reminder['user_id']}>\n"
            f"⏰ **{reminder['time']}** | 📅 {start} to {end}\n"
            f"💰 {reminder['message']}\n\n"
        )

    await ctx.send(text)


# =========================
# CANCEL REMINDER (RESTRICTED)
# =========================

@bot.command()
@commands.has_role(1538234465992577186)
async def cancel(ctx, reminder_id: int = None):
    if reminder_id is None:
        await ctx.send(
            "❌ Please provide a reminder ID.\n\n"
            "Example:\n"
            "`!cancel 1`"
        )
        return

    for reminder in reminders:
        if reminder["id"] == reminder_id:
            reminders.remove(reminder)
            save_reminders()
            await ctx.send(
                f"🗑️ **Reminder #{reminder_id} has been cancelled.**"
            )
            return

    await ctx.send("❌ **Reminder not found.**")


# =========================
# ERROR HANDLER FOR MISSING ROLE
# =========================

@remind.error
@show_reminders.error
@cancel.error
async def role_error(ctx, error):
    if isinstance(error, commands.MissingRole):
        await ctx.send("❌ You do not have the required role to use this command.")


# =========================
# REMINDER LOOP
# =========================

async def reminder_loop():
    await bot.wait_until_ready()

    log.info("Reminder system started.")

    while not bot.is_closed():
        now = datetime.now(TIMEZONE)
        current_time = now.strftime("%H:%M")
        today_str = now.strftime("%Y-%m-%d")

        changed = False

        for reminder in reminders.copy():
            start_date = reminder.get("start_date")
            end_date = reminder.get("end_date")

            if start_date and end_date:
                if not (start_date <= today_str <= end_date):
                    continue

            if reminder["time"] != current_time:
                continue

            if reminder["last_sent"] == today_str:
                continue

            try:
                user = bot.get_user(reminder["user_id"])
                if user is None:
                    user = await bot.fetch_user(reminder["user_id"])

                await user.send(
                    "🔔 **Payment Reminder**\n\n"
                    f"💰 {reminder['message']}\n\n"
                    f"📅 Active Period: {start_date} to {end_date}\n"
                    "Please don't forget today's payment."
                )

                reminder["last_sent"] = today_str
                changed = True

                log.info("Reminder #%s sent to %s", reminder["id"], user)

            except Exception as e:
                log.error("Could not send reminder #%s: %s", reminder["id"], e)

        if changed:
            save_reminders()

        await asyncio.sleep(30)


# =========================
# START
# =========================

if __name__ == "__main__":
    try:
        bot.run(TOKEN, log_handler=None)

    except discord.LoginFailure:
        log.error("Discord rejected the bot token.")
        sys.exit(1)

    except discord.PrivilegedIntentsRequired:
        log.error("Message Content Intent is not enabled.")
        sys.exit(1)
        
