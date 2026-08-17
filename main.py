import asyncio
from datetime import datetime
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
    log.error("DISCORD_TOKEN is not set.")
    sys.exit(1)

# IDs
LOG_CHANNEL_ID = 1538815616612565032
TRANSACTION_CHANNEL_ID = 1538818906351730749
TARGET_ROLE_ID = 1538234465992577186

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# In-memory storage
history = []
reminders = []
TIMEZONE = ZoneInfo("Asia/Tbilisi")

# =========================
# BOT READY
# =========================

@bot.event
async def on_ready():
    log.info("Logged in as %s", bot.user)
    if not hasattr(bot, "reminder_task"):
        bot.reminder_task = asyncio.create_task(reminder_loop())

# =========================
# UNBELIEVABOAT LISTENER (FIXED FOR EMBEDS)
# =========================

@bot.event
async def on_message(message):
    await bot.process_commands(message)

    if message.channel.id != TRANSACTION_CHANNEL_ID or message.author.id == bot.user.id:
        return

    # შევკრიბოთ მესიჯის და ემბედის ტექსტი
    full_text = message.content
    for embed in message.embeds:
        full_text += f"\n{embed.description or ''}\n{embed.title or ''}"

    if "has received your" in full_text:
        recipient_match = re.search(r"<@!?(\d+)>", full_text)
        amount_match = re.search(r"has received your.*?(?:<a?:\w+:\d+>|\W)*([\d,]+(?:\.\d+)?)", full_text)

        if recipient_match:
            recipient_id = int(recipient_match.group(1))
            amount_str = amount_match.group(1).replace(",", "") if amount_match else "Unknown"
            
            # სენდერის პოვნა
            sender_id = None
            if message.reference and message.reference.message_id:
                try:
                    ref_msg = await message.channel.fetch_message(message.reference.message_id)
                    sender_id = ref_msg.author.id
                except: pass
            
            if not sender_id:
                async for hist_msg in message.channel.history(limit=5, before=message):
                    if hist_msg.content.lower().startswith("!give"):
                        sender_id = hist_msg.author.id
                        break

            tx_entry = {
                "id": len(history) + 1,
                "recipient_id": recipient_id,
                "sender_id": sender_id,
                "amount": amount_str,
                "timestamp": datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
            }

            history.append(tx_entry)
            log.info(f"Transaction Recorded: {tx_entry}")

            await message.channel.send(
                f"📥 **Transaction Saved!**\n"
                f"• **Recipient:** <@{recipient_id}>\n"
                f"• **Amount:** `{amount_str}`"
            )

# =========================
# COMMANDS
# =========================

@bot.command()
@commands.has_role(TARGET_ROLE_ID)
async def history(ctx, member: discord.Member = None):
    if not history:
        return await ctx.send("📭 **No transactions recorded yet.**")

    filtered = [tx for tx in history if not member or tx['recipient_id'] == member.id or tx['sender_id'] == member.id]
    
    if not filtered:
        return await ctx.send(f"📭 **No transactions for {member.display_name if member else 'anyone'}.**")

    text = "📜 **Transaction History**\n\n"
    for tx in filtered[-10:]:
        text += f"**#{tx['id']}** | {tx['timestamp']} | Amount: `{tx['amount']}` | To: <@{tx['recipient_id']}>\n"
    
    await ctx.send(text)

@bot.command()
@commands.has_role(TARGET_ROLE_ID)
async def debug_history(ctx):
    await ctx.send(f"🛠️ Total records in memory: `{len(history)}`")

# =========================
# REMINDERS (Simplified)
# =========================

async def reminder_loop():
    while not bot.is_closed():
        await asyncio.sleep(60)

# START BOT
if __name__ == "__main__":
    bot.run(TOKEN)
    
