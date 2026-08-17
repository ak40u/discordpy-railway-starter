import asyncio
from datetime import datetime
import json
import logging
import os
import re
import sys
from zoneinfo import ZoneInfo
from collections import defaultdict
import time

try:
    import google.generativeai as genai
    import discord
    from discord.ext import commands
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "discord.py", "google-generativeai"])
    import google.generativeai as genai
    import discord
    from discord.ext import commands

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("bot")

TOKEN = os.environ.get("DISCORD_TOKEN")
if not TOKEN:
    log.error("DISCORD_TOKEN is not set in environment variables.")
    sys.exit(1)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    ai_model = genai.GenerativeModel("gemini-1.5-flash")
else:
    ai_model = None

LOG_CHANNEL_ID = 1538815616612565032
TRANSACTION_CHANNEL_ID = 1538818906351730749
OPERATOR_CHANNEL_ID = 1538864392546951218
TARGET_ROLE_ID = 1538234465992577186
SUPPORT_ROLE_ID = 1538234465992577186

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

REMINDERS_FILE = "reminders.json"
HISTORY_FILE = "history.json"
TIMEZONE = ZoneInfo("Asia/Tbilisi")
user_history = defaultdict(list)

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

async def send_system_log(content: str):
    try:
        channel = bot.get_channel(LOG_CHANNEL_ID)
        if channel is None:
            channel = await bot.fetch_channel(LOG_CHANNEL_ID)
        if channel:
            await channel.send(content)
    except Exception as e:
        log.error("Failed to send system log: %s", e)

@bot.event
async def on_ready():
    log.info(f"Logged in as {bot.user} (ID: {bot.user.id})")
    if not hasattr(bot, "reminder_task"):
        bot.reminder_task = asyncio.create_task(reminder_loop())

@bot.event
async def on_message(message):
    await bot.process_commands(message)

    if message.author.id == bot.user.id:
        return

    if message.channel.id == OPERATOR_CHANNEL_ID:
        user_id = message.author.id
        current_time = time.time()

        user_history[user_id].append(current_time)
        user_history[user_id] = [t for t in user_history[user_id] if current_time - t < 30]

        if len(user_history[user_id]) >= 3:
            await message.channel.send(f"<@&{SUPPORT_ROLE_ID}> Please wait, an operator will be with you shortly.")
            user_history[user_id] = []
            return

        async with message.channel.typing():
            try:
                if ai_model:
                    prompt = f"შენ ხარ დამხმარე AI ოპერატორი. მომხმარებელმა მოწერა: {message.content}"
                    response = ai_model.generate_content(prompt)
                    reply = response.text
                    await message.channel.send(reply)
                else:
                    await message.channel.send("AI გასაღები არ არის მითითებული.")
            except Exception as e:
                log.error(f"AI Error: {e}")
                await message.channel.send("Sorry, I am having trouble connecting to the support system right now.")
        return

    if message.channel.id != TRANSACTION_CHANNEL_ID:
        return

    full_text = message.content
    for embed in message.embeds:
        if embed.description:
            full_text += "\n" + embed.description
        if embed.title:
            full_text += "\n" + embed.title

    if "has received your" in full_text:
        recipient_match = re.search(r"<@!?(\d+)>", full_text)
        amount_match = re.search(r"has received your.*?(?:<a?:\w+:\d+>|\W)*([\d,]+(?:\.\d+)?)", full_text)

        if recipient_match:
            recipient_id = int(recipient_match.group(1))
            amount_str = amount_match.group(1).replace(",", "") if amount_match else "Unknown"
            
            sender_id = None
            if message.reference and message.reference.message_id:
                try:
                    ref_msg = await message.channel.fetch_message(message.reference.message_id)
                    sender_id = ref_msg.author.id
                except Exception:
                    pass
            
            if not sender_id:
                try:
                    async for hist_msg in message.channel.history(limit=10, before=message):
                        if hist_msg.content.lower().startswith("!give"):
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

            await message.channel.send(
                f"📥 **Transaction Saved to History!**\n"
                f"• **Recipient:** <@{recipient_id}>\n"
                f"• **Amount:** `{amount_str}`\n"
                f"• **Date:** `{now_str}`"
            )

            sender_mention = f"<@{sender_id}>" if sender_id else "Unknown"
            log_msg = (
                "💳 **[LOG] Currency Transfer Recorded**\n"
                f"• **ID:** #{tx_entry['id']}\n"
                f"• **Sender:** {sender_mention}\n"
                f"• **Recipient:** <@{recipient_id}>\n"
                f"• **Amount:** `{amount_str}`"
            )
            await send_system_log(log_msg)

@bot.command()
@commands.has_role(TARGET_ROLE_ID)
async def history(ctx, member: discord.Member = None):
    global history
    history = load_json(HISTORY_FILE)

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
        sender_id = tx.get('sender_id')
        sender = f"<@{sender_id}>" if sender_id else "Unknown"
        text += (
            f"**#{tx['id']}** | 🕒 `{tx['timestamp']}`\n"
            f"• **Sender:** {sender}\n"
            f"• **Recipient:** <@{tx['recipient_id']}>\n"
            f"• **Amount:** `{tx['amount']}`\n\n"
        )

    await ctx.send(text)

@bot.command()
@commands.has_role(TARGET_ROLE_ID)
async def debug_history(ctx):
    global history
    history = load_json(HISTORY_FILE)
    total_count = len(history)
    file_exists = os.path.exists(HISTORY_FILE)
    await ctx.send(
        f"🛠️ **History Debug Info:**\n"
        f"• File exists: `{file_exists}`\n"
        f"• Total records: `{total_count}`\n"
        f"• File path: `{os.path.abspath(HISTORY_FILE)}`"
    )

class ReminderConfirmView(discord.ui.View):
    def __init__(self, ctx, reminder_data):
        super().__init__(timeout=60)
        self.ctx = ctx
        self.reminder_data = reminder_data

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

@bot.command()
@commands.has_role(TARGET_ROLE_ID)
async def remind(ctx, member: discord.Member = None, time_str: str = None, start_date: str = None, end_date: str = None, *message):
    if member is None:
        return await ctx.send("❌ **Invalid client.** Please mention a real Discord user.")

    if time_str is None or start_date is None or end_date is None or not message:
        return await ctx.send("❌ **Missing arguments.** Example: `!remind @Client 19:00 2026-08-15 2026-09-15 2000 payment`")

    reminder_data = {
        "user_id": member.id,
        "time": time_str,
        "start_date": start_date,
        "end_date": end_date,
        "message": " ".join(message),
        "last_sent": None,
    }

    view = ReminderConfirmView(ctx, reminder_data)
    msg = await ctx.send("🔍 **Reminder Confirmation Preview**", view=view)
    view.message = msg

@bot.command()
@commands.has_role(TARGET_ROLE_ID)
async def cancel(ctx, reminder_id: int = None):
    if reminder_id is None:
        return await ctx.send("❌ Please provide a reminder ID. Example: `!cancel 1`")

    for r in reminders:
        if r["id"] == reminder_id:
            reminders.remove(r)
            save_json(REMINDERS_FILE, reminders)
            return await ctx.send(f"🗑️ **Reminder #{reminder_id} has been cancelled and deleted.**")

    await ctx.send("❌ **Reminder not found.**")

@bot.command()
async def ping(ctx):
    await ctx.send(text=f"Pong! Latency: {round(bot.latency * 1000)}ms")

async def reminder_loop():
    await bot.wait_until_ready()
    log.info("Reminder loop started.")

    while not bot.is_closed():
        now = datetime.now(TIMEZONE)
        current_time = now.strftime("%H:%M")
        today_str = now.strftime("%Y-%m-%d")
        changed = False

        for r in reminders.copy():
            if r.get("end_date") and today_str > r["end_date"]:
                reminders.remove(r)
                changed = True

        for r in reminders.copy():
            if r.get("start_date") and r.get("end_date") and not (r["start_date"] <= today_str <= r["end_date"]):
                continue

            if r["time"] != current_time or r["last_sent"] == today_str:
                continue

            try:
                user = bot.get_user(r["user_id"]) or await bot.fetch_user(r["user_id"])
                await user.send(f"🔔 **Payment Reminder:** {r['message']}")
                r["last_sent"] = today_str
                changed = True
            except Exception as e:
                log.error("Could not send reminder #%s: %s", r["id"], e)

        if changed:
            save_json(REMINDERS_FILE, reminders)

        await asyncio.sleep(30)

if __name__ == "__main__":
    bot.run(TOKEN)
