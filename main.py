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
# AUTOMATIC UNBELIEVABOAT LISTENER
# =========================

@bot.event
async def on_message(message):
    # Process commands first
    await bot.process_commands(message)

    # Listen only in the transaction channel
    if message.channel.id != TRANSACTION_CHANNEL_ID:
        return

    # Don't listen to self
    if message.author.id == bot.user.id:
        return

    # Check for UnbelievaBoat confirmation message format
    # Example: "<@!1203065448065798144> has received your <:unbelievacoin:...> 2"
    if "has received your" in message.content:
        content = message.content

        # Extract Recipient ID using Regex
        recipient_match = re.search(r"<@!?(\d+)>", content)
        # Extract Amount (matches integer or float after currency symbol/text)
        amount_match = re.search(r"has received your.*?\s+([\d,]+(?:\.\d+)?)", content)

        if recipient_match and amount_match:
            recipient_id = int(recipient_match.group(1))
            amount_str = amount_match.group(1).replace(",", "")
            
            # Identify sender (from reference/reply or context)
            sender_id = None
            if message.reference and message.reference.message_id:
                try:
                    ref_msg = await message.channel.fetch_message(message.reference.message_id)
                    sender_id = ref_msg.author.id
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
            await message.channel.send(
                f"📥 **Transaction Saved to History!**\n"
                f"• **Recipient:** <@{recipient_id}>\n"
                f"• **Amount:** `{amount_str}`\n"
                f"• **Date:** `{now_str}`"
            )

            # Send detailed log to Log Channel
            sender_mention = f"<@{sender_id}>" if sender_id else "Unknown User"
            log_msg = (
                "💳 **[LOG] Currency Transfer Detected**\n"
                f"• **Transaction ID:** #{tx_entry['id']}\n"
                f"• **Recipient:** <@{recipient_id}>\n"
                f"• **Sender:** {sender_mention}\n"
                f"• **Amount:** `{amount_str}`\n"
                f"• **Timestamp:** `{now_str}`"
            )
            await send_system_log(log_msg)


# =========================
# HISTORY COMMAND (`!history`)
# =========================

@bot.command()
@commands.has_role(TARGET_ROLE_ID)
async def history(ctx, member: discord.Member = None):
    if not history:
        await ctx.send("📭 **No transactions recorded in history yet.**")
        return

    # Filter by user if specified
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
        await ctx.send(f"📭 **No transactions found for {member.mention}.**")
        return

    # Take latest 10 transactions
    recent_tx = filtered_tx[-10:]
    recent_tx.reverse()

    text = f"{title}\n\n"
    for tx in recent_tx:
        sender = f"<@{tx['sender_id']}>" if tx.get("sender_id") else "Unknown"
        text += (
            f"**#{tx['id']}** | 🕒 `{tx['timestamp']}`\n"
            f"• **Recipient:** <@{tx['recipient_id']}>\n"
            f"• **Sender:** {sender}\n"
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
        await ctx.send(
            "❌ **Invalid client.**\n\n"
            "Please mention a real Discord user.\n\n"
            "Example:\n"
            "`!remind @Client 19:00 2026-08-15 2026-09-15 2000 payment`"
        )
        return

    if time is None:
        await ctx.send("❌ **Time is missing.** Use HH:MM format.")
        return

    if start_date is None:
        await ctx.send("❌ **Start date is missing.** Use YYYY-MM-DD format.")
        return

    if end_date is None:
        await ctx.send("❌ **End date is missing.** Use YYYY-MM-DD format.")
        return

    if not message:
        await ctx.send("❌ **Payment information is missing.**")
        return

    try:
        datetime.strptime(time, "%H:%M")
    except ValueError:
        await ctx.send("❌ **Invalid time format.** Use HH:MM (e.g. `19:00`).")
        return

    try:
        datetime.strptime(start_date, "%Y-%m-%d")
    except ValueError:
        await ctx.send("❌ **Invalid start date format.** Use YYYY-MM-DD.")
        return

    try:
        datetime.strptime(end_date, "%Y-%m-%d")
    except ValueError:
        await ctx.send("❌ **Invalid end date format.** Use YYYY-MM-DD.")
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
        f"👤 **Client to Remind:** {member.mention} (ID: `{member.id}`)\n"
        f"🛡️ **Proposed By (Staff):** {ctx.author.mention}\n"
        f"⏰ **Reminder Time:** **{time}** (Asia/Tbilisi)\n"
        f"📅 **Active Validity Period:** From **{start_date}** to **{end_date}**\n"
        f"💰 **Payment Information:** **{' '.join(message)}**\n\n"
        "Please review the details above carefully and click **Confirm & Create** below to activate this agreement."
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
        await ctx.send(
            "❌ **Please provide a reminder ID.**\n\n"
            "Example:\n"
            "`!edit 1 20:00 2026-08-15 2026-09-15 2500 updated payment`"
        )
        return

    target_reminder = None
    for r in reminders:
        if r["id"] == reminder_id:
            target_reminder = r
            break

    if not target_reminder:
        await ctx.send(f"❌ **Reminder #{reminder_id} not found.**")
        return

    new_time = time if time else target_reminder["time"]
    new_start = start_date if start_date else target_reminder["start_date"]
    new_end = end_date if end_date else target_reminder["end_date"]
    new_msg = " ".join(message) if message else target_reminder["message"]

    if time:
        try:
            datetime.strptime(time, "%H:%M")
        except ValueError:
            await ctx.send("❌ **Invalid time format.** Use HH:MM.")
            return

    if start_date:
        try:
            datetime.strptime(start_date, "%Y-%m-%d")
        except ValueError:
            await ctx.send("❌ **Invalid start date format.** Use YYYY-MM-DD.")
            return

    if end_date:
        try:
            datetime.strptime(end_date, "%Y-%m-%d")
        except ValueError:
            await ctx.send("❌ **Invalid end date format.** Use YYYY-MM-DD.")
            return

    old_time = target_reminder["time"]
    old_start = target_reminder["start_date"]
    old_end = target_reminder["end_date"]
    old_msg = target_reminder["message"]

    target_reminder["time"] = new_time
    target_reminder["start_date"] = new_start
    target_reminder["end_date"] = new_end
    target_reminder["message"] = new_msg

    save_json(REMINDERS_FILE, reminders)

    await ctx.send(f"✅ **Reminder #{reminder_id} has been successfully updated!**")

    edit_log_msg = (
        "✏️ **[LOG] Reminder Modified / Edited**\n"
        f"• **Reminder ID:** #{reminder_id}\n"
        f"• **Modified By (Staff):** {ctx.author.mention}\n"
        f"• **Target Client:** <@{target_reminder['user_id']}>\n\n"
        "🔄 **Changes Applied:**\n"
        f"• **Time:** `{old_time}` ➔ `{new_time}`\n"
        f"• **Period:** `{old_start} to {old_end}` ➔ `{new_start} to {new_end}`\n"
        f"• **Payment Details:** \n  Old: *{old_msg}*\n  New: *{new_msg}*"
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

            cancel_log_msg = (
                "🗑️ **[LOG] Reminder Deleted / Cancelled**\n"
                f"• **Reminder ID:** #{reminder_id}\n"
                f"• **Action Performed By:** {ctx.author.mention}\n"
                f"• **Associated Client:** <@{reminder['user_id']}>\n"
                f"• **Details was:** {reminder['message']}"
            )
            await send_system_log(cancel_log_msg)
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
# REMINDER LOOP (WITH AUTO-CLEANUP & LOGGING)
# =========================

async def reminder_loop():
    await bot.wait_until_ready()

    log.info("Advanced reminder loop with Auto-Cleanup started.")

    while not bot.is_closed():
        now = datetime.now(TIMEZONE)
        current_time = now.strftime("%H:%M")
        today_str = now.strftime("%Y-%m-%d")

        changed = False
        expired_reminders = []

        # 1. Auto-Cleanup expired reminders
        for reminder in reminders.copy():
            end_date = reminder.get("end_date")
            if end_date and today_str > end_date:
                expired_reminders.append(reminder)
                reminders.remove(reminder)
                changed = True

        for exp in expired_reminders:
            cleanup_log_msg = (
                "🧹 **[LOG] Auto-Cleanup Performed (Expired Contract)**\n"
                f"• **Reminder ID:** #{exp['id']}\n"
                f"• **Target Client:** <@{exp['user_id']}>\n"
                f"• **End Date Was:** {exp['end_date']} (Today is {today_str})\n"
                "• **Status:** Automatically removed from active storage."
            )
            await send_system_log(cleanup_log_msg)
            log.info("Auto-cleaned expired reminder #%s", exp["id"])

        # 2. Process active daily reminders
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

                delivery_log_msg = (
                    "📨 **[LOG] Reminder Successfully Sent**\n"
                    f"• **Reminder ID:** #{reminder['id']}\n"
                    f"• **Recipient Client:** <@{reminder['user_id']}>\n"
                    f"• **Scheduled Time:** {reminder['time']}\n"
                    f"• **Payment Content:** {reminder['message']}"
                )
                await send_system_log(delivery_log_msg)

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

    except discord.LoginFailure:
        log.error("Discord rejected the bot token.")
        sys.exit(1)

    except discord.PrivilegedIntentsRequired:
        log.error("Message Content Intent is not enabled.")
        sys.exit(1)
            
