import os
import json
import asyncio
import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ChatAction
from telegram.error import Forbidden, BadRequest
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

# ====== LOGGING ======
logging.basicConfig(level=logging.INFO)

# ====== ENV CONFIG ======
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

# ====== FILES ======
USERS_FILE = "users.json"

# ====== GLOBAL ======
BLOCKED_USERS = set()

# ====== USERS SAVE/LOAD ======
def load_users():
    if not os.path.exists(USERS_FILE):
        return set()
    with open(USERS_FILE, "r") as f:
        return set(json.load(f))

def save_users(users):
    with open(USERS_FILE, "w") as f:
        json.dump(list(users), f)

# ====== START ======
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = load_users()
    users.add(update.effective_user.id)
    save_users(users)

    await update.message.reply_text("🤖 Bot started! Send me any message.")

# ====== USER MESSAGE ======
async def user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if user.id in BLOCKED_USERS:
        return

    await context.bot.send_chat_action(chat_id=ADMIN_ID, action=ChatAction.TYPING)

    text = update.message.text if update.message.text else "📎 Media received"

    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=(
            "📩 New Message From\n"
            f"👤 User: {user.first_name}\n"
            f"🆔 User ID: {user.id}\n\n"
            f"💬 {text}"
        )
    )

    await update.message.reply_text("✅ Message sent to admin")

# ====== ADMIN REPLY ======
async def admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    if not update.message.reply_to_message:
        return

    text = update.message.text

    lines = update.message.reply_to_message.text.split("\n")
    uid_line = [x for x in lines if "User ID:" in x]

    if not uid_line:
        return

    uid = int(uid_line[0].split(":")[1].strip())

    await context.bot.send_chat_action(chat_id=uid, action=ChatAction.TYPING)
    await context.bot.send_message(chat_id=uid, text=text)

# ========= BROADCAST =========
async def broadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to any message with /broadcast to open panel.")
        return

    context.bot_data["broadcast_msg"] = update.message.reply_to_message
    await update.message.reply_text(
        "📣 Broadcast panel opened\n\nSend /confirm to start\nSend /cancel to abort"
    )

async def confirm_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    msg = context.bot_data.get("broadcast_msg")
    if not msg:
        await update.message.reply_text("No broadcast message found.")
        return

    users = load_users()
    total = len(users)
    success = blocked = deleted = failed = 0

    status = await update.message.reply_text("📡 Broadcasting started...")

    for uid in list(users):
        try:
            await context.bot.copy_message(
                chat_id=uid,
                from_chat_id=msg.chat_id,
                message_id=msg.message_id
            )
            success += 1
            await asyncio.sleep(0.05)
        except Forbidden:
            blocked += 1
            users.discard(uid)
        except BadRequest as e:
            if "deactivated" in str(e).lower():
                deleted += 1
                users.discard(uid)
            else:
                failed += 1
        except:
            failed += 1

    save_users(users)

    await status.edit_text(
        "✅ Broadcast completed\n\n"
        f"◇ Total Users: {total}\n"
        f"◇ Successful: {success}\n"
        f"◇ Blocked Users: {blocked}\n"
        f"◇ Deleted Accounts: {deleted}\n"
        f"◇ Unsuccessful: {failed}"
    )

    context.bot_data.pop("broadcast_msg", None)

async def cancel_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    context.bot_data.pop("broadcast_msg", None)
    await update.message.reply_text("❌ Broadcast cancelled.")

# ========= ADMIN PANEL =========
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚫 Block User", callback_data="block")],
        [InlineKeyboardButton("✅ Unblock User", callback_data="unblock")]
    ])
    await update.message.reply_text("Admin Panel:", reply_markup=kb)

async def admin_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["action"] = query.data
    await query.message.reply_text("Send User ID:")

async def receive_user_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    action = context.user_data.get("action")
    if not action:
        return

    try:
        uid = int(update.message.text)
    except:
        await update.message.reply_text("Invalid ID")
        return

    if action == "block":
        BLOCKED_USERS.add(uid)
        await update.message.reply_text(f"🚫 User {uid} blocked.")
    elif action == "unblock":
        BLOCKED_USERS.discard(uid)
        await update.message.reply_text(f"✅ User {uid} unblocked.")

    context.user_data.pop("action", None)

# ====== MAIN ======
async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("broadcast", broadcast_cmd))
    app.add_handler(CommandHandler("confirm", confirm_broadcast))
    app.add_handler(CommandHandler("cancel", cancel_broadcast))
    app.add_handler(CommandHandler("admin", admin_panel))

    app.add_handler(CallbackQueryHandler(admin_buttons))
    app.add_handler(MessageHandler(filters.TEXT & filters.REPLY & filters.User(user_id=ADMIN_ID), admin_reply))
    app.add_handler(MessageHandler(filters.TEXT & filters.User(user_id=ADMIN_ID), receive_user_id))
    app.add_handler(MessageHandler(filters.ALL & ~filters.User(user_id=ADMIN_ID), user_message))

    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
