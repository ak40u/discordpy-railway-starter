import logging
import os
import sys
import json
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)

log = logging.getLogger("bot")

TOKEN = os.environ.get("DISCORD_TOKEN")

if not TOKEN:
    log.error("DISCORD_TOKEN is not set in Railway Variables.")
    sys.exit(1)

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

REMINDERS_FILE = "reminders.json"
TIMEZONE = ZoneInfo("Asia/Tbilisi")


def load_reminders():
    if not os.path.exists(REMINDERS_FILE):
        return []

    try:
        with open(REMINDERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_reminders(reminders):
    with open(REMINDERS_FILE, "w", encoding="utf-8") as f:
        json.dump(reminders, f, ensure_ascii=False, indent=2)


reminders = load_reminders()


@bot.event
async def on_ready():
    log.info("Logged in as %s (id %s)", bot.user, bot.user.id)

    if not hasattr(bot, "reminder_task"):
        bot.reminder_task = asyncio.create_task(reminder_loop())


@bot.command()
async def ping(ctx):
    await ctx.send(f"pong ({bot.latency * 1000:.0f} ms)")


@bot.command()
async def hello(ctx):
    await ctx.send("Choo choo! 🚅")


@bot.command()
async def remind(ctx, member: discord.Member = None, time: str = None, *message):
    """
    Example:
    !remind @User 20:00 2000-ის გადახდა

    Daily reminder by default.
    """

    if member is None or time is None or not message:
        await ctx.send(
            "❌ გამოყენება:\n"
            "`!remind @კლიენტი 20:00 2000-ის გადახდა`"
        )
        return

    try:
        datetime.strptime(time, "%H:%M")
    except ValueError:
        await ctx.send("❌ დრო უნდა იყოს HH:MM ფორმატში. მაგალითად: `20:00`")
        return

    reminder = {
        "id": max([r["id"] for r in reminders], default=0) + 1,
        "user_id": member.id,
        "channel_id": ctx.channel.id,
        "time": time,
        "message": " ".join(message),
        "daily": True,
        "last_sent": None
    }

    reminders.append(reminder)
    save_reminders(reminders)

    await ctx.send(
        f"✅ Reminder შექმნილია!\n"
        f"👤 კლიენტი: {member.mention}\n"
        f"⏰ დრო: **{time}**\n"
        f"📝 შეტყობინება: **{' '.join(message)}**\n"
        f"🔁 ყოველდღე"
    )


@bot.command()
async def reminders(ctx):
    if not reminders:
        await ctx.send("📭 აქტიური Reminders არ არის.")
        return

    text = "📋 **აქტიური Reminders:**\n\n"

    for r in reminders:
        user = bot.get_user(r["user_id"])
        username = user.mention if user else f"<@{r['user_id']}>"

        text += (
            f"**#{r['id']}** — {username}\n"
            f"⏰ {r['time']} | 📝 {r['message']}\n\n"
        )

    await ctx.send(text)


@bot.command()
async def cancel(ctx, reminder_id: int = None):
    if reminder_id is None:
        await ctx.send("❌ მიუთითე Reminder-ის ID. მაგალითად: `!cancel 1`")
        return

    for reminder in reminders:
        if reminder["id"] == reminder_id:
            reminders.remove(reminder)
            save_reminders(reminders)

            await ctx.send(
                f"🗑️ Reminder **#{reminder_id}** გაუქმებულია."
            )
            return

    await ctx.send("❌ ასეთი Reminder ვერ მოიძებნა.")


async def reminder_loop():
    await bot.wait_until_ready()

    while not bot.is_closed():
        now = datetime.now(TIMEZONE)
        current_time = now.strftime("%H:%M")
        today = now.strftime("%Y-%m-%d")

        changed = False

        for reminder in reminders.copy():

            if reminder["time"] != current_time:
                continue

            if reminder["last_sent"] == today:
                continue

            try:
                user = await bot.fetch_user(reminder["user_id"])

                await user.send(
                    "🔔 **Payment Reminder**\n\n"
                    f"📝 {reminder['message']}\n\n"
                    "გთხოვთ, არ დაგავიწყდეთ დღევანდელი გადახდა."
                )

                reminder["last_sent"] = today
                changed = True

                log.info(
                    "Reminder #%s sent to %s",
                    reminder["id"],
                    user
                )

            except Exception as e:
                log.error(
                    "Could not send reminder #%s: %s",
                    reminder["id"],
                    e
                )

        if changed:
            save_reminders(reminders)

        await asyncio.sleep(30)


if __name__ == "__main__":
    try:
        bot.run(TOKEN, log_handler=None)

    except discord.LoginFailure:
        log.error(
            "Discord rejected the token. "
            "Check DISCORD_TOKEN in Railway Variables."
        )
        sys.exit(1)

    except discord.PrivilegedIntentsRequired:
        log.error(
            "Message Content intent is not enabled. "
            "Enable it in Discord Developer Portal."
        )
        sys.exit(1)@bot.command()
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
