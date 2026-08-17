import asyncio
from datetime import datetime
import json
import logging
import os
import re
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

# Dedicated IDs
LOG_CHANNEL_ID = 1538815616612565032
TRANSACTION_CHANNEL_ID = 1538818906351730749
TARGET_ROLE_ID = 1538234465992577186


# =========================
# DISCORD
# =========================

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)


# =========================
# STORAGE MANAGEMENT
# =========================

REMINDERS_FILE = "reminders.json"
HISTORY_FILE = "history.json"
TIMEZONE = ZoneInfo("Asia/Tbilisi")


def load_json(filepath):
    if not os.path.exists(filepath):
        return []
    try:
        with open(filepath, "r", encoding="utf-8") as file:
            return json.load(file)
    except Exception as e:
        log.error("Could not load %s: %s", filepath, e)
        return []


def save_json(filepath, data):
    try:
        with open(filepath, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
    except Exception as e:
        log.error("Could not save %s: %s", filepath, e)


reminders = load_json(REMINDERS_FILE)
history = load_json(HISTORY_FILE)


# =========================
# HELPER: SEND LOG TO CHANNEL
# =========================

async def send_system_log(content: str):
    try:
        channel = bot.get_channel(LOG_CHANNEL_ID)
        if channel is None:
            channel = await bot.fetch_channel(LOG_CHANNEL_ID)
        if channel:
            await channel.send(content)
    except Exception as e:
        log.error("Failed to send system log to channel: %s", e)


# =========================
# BOT READY
# =========================

@bot.event
async def on_ready():
    log.info("Logged in as %s (ID: %s)", bot.user, bot.user.id)

    if not hasattr(bot, "reminder_task"):
        bot.reminder_task = asyncio.create_task(reminder_loop())


# =========================
# PING & HELLO
# =========================

@bot.command()
async def ping(ctx):
    await ctx.send(f"pong ({bot.latency * 1000:.0f} ms)")


@bot.command()
async def hello(ctx):
    await ctx.send("Hello! 👋")


# =========================
# AUTOMATIC UNBELIEVABOAT LISTENER (FIXED)
# =========================

@bot.event
async def on_message(message):
    await bot.process_commands(message)

    if message.channel.id != TRANSACTION_CHANNEL_ID:
        return

    if message.author.id == bot.user.id:
        return

    # Check for UnbelievaBoat confirmation message format
    if "has received your" in message.content:
        content = message.content

        # Extract Recipient ID using Regex
        recipient_match = re.search(r"<@!?(\d+)>", content)
        # Extract Amount
        amount_match = re.search(r"has received your.*?\s+([\d,]+(?:\.\d+)?)", content)

        if recipient_match:
            recipient_id = int(recipient_match.group(1))
            amount_str = amount_match.group(1).replace(",", "") if amount_match else "Unknown"
            
            # Try to find sender from message reference or recent messages in channel
            sender_id = None
            if message.reference and message.reference.message_id:
                try:
                    ref_msg = await message.channel.fetch_message(message.reference.message_id)
                    sender_id = ref_msg.author.id
                except Exception:
                    pass
            
            # Fallback: check last 5 messages in the channel to find who used !give
            if not sender_id:
                try:
                    async for hist_msg in message.channel.history(limit=5, before=message):
                        if hist_msg.content.lower().startswith("!give") or "give" in hist_msg.content.lower():
                            sender_id = hist_msg.author.id
                            break
                except Exception:
                    pass

            now_str = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")

            tx_entry = {
                "id": max([tx["id"] for tx in history], default=0) + 1,
                "recipient_id": recipient_id,
                "sender_id": sender_id,
                "amount": amount_str,
                "timestamp": now_str
            }

            history.append(tx_entry)
            save_json(HISTORY_FILE, history)

            # Confirm transaction logging in channel
            sender_mention = f"<@{sender_id}>" if sender_id else "Unknown User"
            await message.channel.send(
                f"📥 **Transaction Saved to History!**\n"
                f"• **Sender:** {sender_mention}\n"
                f"• **Recipient:** <@{recipient_id}>\n"
                f"• **Amount:** `{amount_str}`\n"
                f"• **Date:** `{now_str}`"
            )

            # Send detailed log to Log Channel
            log_msg = (
                "💳 **[LOG] Currency Transfer Detected**\n"
                f"• **Transaction ID:** #{tx_entry['id']}\n"
                f"• **Sender:** {sender_mention}\n"
                f"• **Recipient:** <@{recipient_id}>\n"
                f"• **Amount:** `{amount_str}`\n"
                f"• **Timestamp:** `{now_str}`"
            )
            await send_system_log(log_msg)


# =========================
# HISTORY COMMAND (`!history`) (FIXED)
# =========================

@bot.command()
@commands.has_role(TARGET_ROLE_ID)
async def history(ctx, member: discord.Member = None):
    if not history:
        await ctx.send("📭 **No transactions recorded in history yet.**")
        return

    if member:
        filtered_tx = [
            tx for tx in history 
            if tx.get("recipient_id") == member.id or tx.get("sender_id") == member.id
        ]
        title = f"📜 **Transaction History for {member.display_name}**"
    else:
        filtered_tx = history
        title = "📜 **Global Transaction History (Latest 10)**"

    if not filtered_tx:
        target_name = member.mention if member else "database"
        await ctx.send(f"📭 **No transactions found for {target_name}.**")
        return

    recent_tx = filtered_tx[-10:]
    recent_tx.reverse()

    text = f"{title}\n\n"
    for tx in recent_tx:
        sender = f"<@{tx['sender_id']}>" if tx.get("sender_id") else "Unknown"
        text += (
            f"**#{tx['id']}** | 🕒 `{tx['timestamp']}`\n"
            f"• **Sender:** {sender}\n"
            f"• **Recipient:** <@{tx['recipient_id']}>\n"
            f"• **Amount:** `{tx['amount']}`\n\n"
        )

    await ctx.send(text)


# =========================
# INTERACTIVE CONFIRMATION VIEW
# =========================

class ReminderConfirmView(discord.ui.View):
    def __init__(self, ctx, reminder_data):
        super().__init__(timeout=60)
        self.ctx = ctx
        self.reminder_data = reminder_data
        self.value = None

    @discord.ui.button(label="Confirm & Create", style=discord.ButtonStyle.green, emoji="✅")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("❌ You cannot interact with this confirmation.", ephemeral=True)
            return

        new_id = max([r["id"] for r in reminders], default=0) + 1
        self.reminder_data["id"] = new_id
        reminders.append(self.reminder_data)
        save_json(REMINDERS_FILE, reminders)

        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)

        await interaction.followup.send(f"✅ **Reminder #{new_id} has been successfully created and saved!**")

        author_mention = self.ctx.author.mention
        client_mention = f"<@{self.reminder_data['user_id']}>"
        log_msg = (
            "📌 **[LOG] New Reminder Created**\n"
            f"• **Reminder ID:** #{new_id}\n"
            f"• **Created By (Staff):** {author_mention}\n"
            f"• **Assigned Client:** {client_mention}\n"
            f"• **Schedule Time:** {self.reminder_data['time']}\n"
            f"• **Active Period:** {self.reminder_data['start_date']} to {self.reminder_data['end_date']}\n"
            f"• **Payment Details:** {self.reminder_data['message']}"
        )
        await send_system_log(log_msg)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red, emoji="❌")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("❌ You cannot interact with this confirmation.", ephemeral=True)
            return

        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)
        await interaction.followup.send("❌ **Reminder creation cancelled.**")
        self.stop()

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        try:
            await self.message.edit(view=self)
        except Exception:
            pass


# =========================
# CREATE REMINDER
# =========================

@bot.command()
@commands.has_role(TARGET_ROLE_ID)
async def remind(
    ctx, 
    member: discord.Member = None, 
    time: str = None, 
    start_date: str = None, 
    end_date: str = None, 
    *message
):
    if member is None:
        await ctx.send("❌ **Invalid client.** Please mention a real Discord user.")
        return

    if time is None or start_date is None or end_date is None or not message:
        await ctx.send("❌ **Missing arguments.** Example: `!remind @Client 19:00 2026-08-15 2026-09-15 2000 payment`")
        return

    try:
        datetime.strptime(time, "%H:%M")
        datetime.strptime(start_date, "%Y-%m-%d")
        datetime.strptime(end_date, "%Y-%m-%d")
    except ValueError:
        await ctx.send("❌ **Invalid date or time format.** Use HH:MM for time and YYYY-MM-DD for dates.")
        return

    reminder_data = {
        "user_id": member.id,
        "time": time,
        "start_date": start_date,
        "end_date": end_date,
        "message": " ".join(message),
        "last_sent": None,
    }

    preview_text = (
        "🔍 **Reminder Confirmation Preview**\n\n"
        f"👤 **Client to Remind:** {member.mention}\n"
        f"🛡️ **Proposed By (Staff):** {ctx.author.mention}\n"
        f"⏰ **Reminder Time:** **{time}** (Asia/Tbilisi)\n"
        f"📅 **Active Validity Period:** From **{start_date}** to **{end_date}**\n"
        f"💰 **Payment Information:** **{' '.join(message)}**\n\n"
        "Please review and click **Confirm & Create** below."
    )

    view = ReminderConfirmView(ctx, reminder_data)
    msg = await ctx.send(preview_text, view=view)
    view.message = msg


# =========================
# EDIT REMINDER (`!edit`)
# =========================

@bot.command()
@commands.has_role(TARGET_ROLE_ID)
async def edit(
    ctx, 
    reminder_id: int = None, 
    time: str = None, 
    start_date: str = None, 
    end_date: str = None, 
    *message
):
    if reminder_id is None:
        await ctx.send("❌ Please provide a reminder ID. Example: `!edit 1 20:00 ...`")
        return

    target_reminder = next((r for r in reminders if r["id"] == reminder_id), None)
    if not target_reminder:
        await ctx.send(f"❌ **Reminder #{reminder_id} not found.**")
        return

    new_time = time if time else target_reminder["time"]
    new_start = start_date if start_date else target_reminder["start_date"]
    new_end = end_date if end_date else target_reminder["end_date"]
    new_msg = " ".join(message) if message else target_reminder["message"]

    target_reminder["time"] = new_time
    target_reminder["start_date"] = new_start
    target_reminder["end_date"] = new_end
    target_reminder["message"] = new_msg

    save_json(REMINDERS_FILE, reminders)
    await ctx.send(f"✅ **Reminder #{reminder_id} has been successfully updated!**")

    edit_log_msg = (
        "✏️ **[LOG] Reminder Modified / Edited**\n"
        f"• **Reminder ID:** #{reminder_id}\n"
        f"• **Modified By:** {ctx.author.mention}\n"
        f"• **Target Client:** <@{target_reminder['user_id']}>"
    )
    await send_system_log(edit_log_msg)


# =========================
# SHOW REMINDERS
# =========================

@bot.command(name="reminders")
@commands.has_role(TARGET_ROLE_ID)
async def show_reminders(ctx):
    if not reminders:
        await ctx.send("📭 **There are no active reminders.**")
        return

    text = "📋 **Active Reminders Directory**\n\n"
    for reminder in reminders:
        start = reminder.get("start_date", "N/A")
        end = reminder.get("end_date", "N/A")
        text += (
            f"**#{reminder['id']}**\n"
            f"👤 Client: <@{reminder['user_id']}>\n"
            f"⏰ Time: **{reminder['time']}** | 📅 Period: {start} to {end}\n"
            f"💰 Info: {reminder['message']}\n\n"
        )
    await ctx.send(text)


# =========================
# CANCEL REMINDER
# =========================

@bot.command()
@commands.has_role(TARGET_ROLE_ID)
async def cancel(ctx, reminder_id: int = None):
    if reminder_id is None:
        await ctx.send("❌ Please provide a reminder ID. Example: `!cancel 1`")
        return

    for reminder in reminders:
        if reminder["id"] == reminder_id:
            reminders.remove(reminder)
            save_json(REMINDERS_FILE, reminders)
            await ctx.send(f"🗑️ **Reminder #{reminder_id} has been cancelled and deleted.**")
            return

    await ctx.send("❌ **Reminder not found.**")


# =========================
# ERROR HANDLER FOR ROLES
# =========================

@remind.error
@edit.error
@show_reminders.error
@cancel.error
@history.error
async def role_error(ctx, error):
    if isinstance(error, commands.MissingRole):
        await ctx.send("❌ You do not have the required role to execute this command.")


# =========================
# REMINDER LOOP
# =========================

async def reminder_loop():
    await bot.wait_until_ready()
    log.info("Reminder loop started.")

    while not bot.is_closed():
        now = datetime.now(TIMEZONE)
        current_time = now.strftime("%H:%M")
        today_str = now.strftime("%Y-%m-%d")

        changed = False

        for reminder in reminders.copy():
            end_date = reminder.get("end_date")
            if end_date and today_str > end_date:
                reminders.remove(reminder)
                changed = True

        for reminder in reminders.copy():
            start_date = reminder.get("start_date")
            end_date = reminder.get("end_date")

            if start_date and end_date and not (start_date <= today_str <= end_date):
                continue

            if reminder["time"] != current_time or reminder["last_sent"] == today_str:
                continue

            try:
                user = bot.get_user(reminder["user_id"]) or await bot.fetch_user(reminder["user_id"])
                await user.send(
                    "🔔 **Payment Reminder**\n\n"
                    f"💰 {reminder['message']}\n\n"
                    f"📅 Active Period: {start_date} to {end_date}\n"
                    "Please don't forget today's payment."
                )
                reminder["last_sent"] = today_str
                changed = True
            except Exception as e:
                log.error("Could not send reminder #%s: %s", reminder["id"], e)

        if changed:
            save_json(REMINDERS_FILE, reminders)

        await asyncio.sleep(30)


# =========================
# START
# =========================

if __name__ == "__main__":
    try:
        bot.run(TOKEN, log_handler=None)
    except Exception as e:
        log.error("Fatal error: %s", e)
        sys.exit(1)
        
