import asyncio
import json
import os
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ChatAction
from telegram.error import Forbidden, BadRequest
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

# ========= CONFIG =========
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

if not BOT_TOKEN or not ADMIN_ID:
    raise RuntimeError("Please set BOT_TOKEN and ADMIN_ID in env variables")

# ========= USER DB =========
def load_users():
    if not os.path.exists(USERS_FILE):
        return set()
    with open(USERS_FILE, "r") as f:
        return set(json.load(f))

def save_users(users):
    with open(USERS_FILE, "w") as f:
        json.dump(list(users), f)

# ========= START =========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = load_users()
    users.add(update.effective_user.id)
    save_users(users)

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📩 Message Admin", callback_data="msg_admin")]
    ])

    await update.message.reply_text(
        "Welcome! 👋\n\nTap button to message admin.",
        reply_markup=kb
    )

# ========= USER → ADMIN =========
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("Type your message below 👇")

async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid in BLOCKED_USERS:
        return

    users = load_users()
    users.add(uid)
    save_users(users)

    await context.bot.send_chat_action(chat_id=ADMIN_ID, action=ChatAction.TYPING)

    text = update.message.text

    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=f"📩 New Message From\n"
             f"👤 User: @{update.effective_user.username}\n"
             f"🆔 User ID: {uid}\n\n"
             f"💬 {text}"
    )

    sent = await update.message.reply_text("✅ Message sent To Admin")
    await asyncio.sleep(3)
    try:
        await sent.delete()
    except:
        pass

# ========= ADMIN → USER REPLY =========
async def admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    if not update.message.reply_to_message:
        return

    reply_msg = update.message.reply_to_message.text or ""
    uid = None

    for line in reply_msg.splitlines():
        if "User ID:" in line:
            try:
                uid = int(line.split("User ID:")[1].strip())
            except:
                pass

    if not uid:
        await update.message.reply_text("❌ User ID not found.")
        return

    try:
        await context.bot.send_message(chat_id=uid, text=update.message.text)
        sent = await update.message.reply_text("✅ Reply sent")
        await asyncio.sleep(3)
        try:
            await sent.delete()
        except:
            pass
    except:
        await update.message.reply_text("❌ Failed to send reply.")

# ========= BROADCAST =========
async def broadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to any message with /broadcast")
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
            await context.bot.copy_message(uid, msg.chat_id, msg.message_id)
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
        f"✅ Broadcast completed\n\n"
        f"Total Users: {total}\n"
        f"Successful: {success}\n"
        f"Blocked: {blocked}\n"
        f"Deleted: {deleted}\n"
        f"Failed: {failed}"
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
        await update.message.reply_text(f"🚫 Blocked {uid}")
    else:
        BLOCKED_USERS.discard(uid)
        await update.message.reply_text(f"✅ Unblocked {uid}")

    context.user_data.pop("action", None)

# ========= MAIN =========
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button, pattern="msg_admin"))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.User(ADMIN_ID), handle_user_message))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.User(ADMIN_ID), admin_reply))

    app.add_handler(CommandHandler("broadcast", broadcast_cmd))
    app.add_handler(CommandHandler("confirm", confirm_broadcast))
    app.add_handler(CommandHandler("cancel", cancel_broadcast))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CallbackQueryHandler(admin_buttons, pattern="block|unblock"))
    app.add_handler(MessageHandler(filters.TEXT & filters.User(ADMIN_ID), receive_user_id))

    print("Bot running...")
    app.run_polling()

if __name__ == "__main__":
    main()
