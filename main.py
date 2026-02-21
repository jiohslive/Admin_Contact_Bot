import os
import json
import asyncio
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)
from telegram.error import Forbidden, BadRequest

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

if not BOT_TOKEN or not ADMIN_ID:
    raise RuntimeError("Please set BOT_TOKEN and ADMIN_ID environment variables.")

USERS_FILE = "users.json"

def load_users():
    if not os.path.exists(USERS_FILE):
        return set()
    with open(USERS_FILE, "r") as f:
        return set(json.load(f))

def save_users(users: set):
    with open(USERS_FILE, "w") as f:
        json.dump(list(users), f)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = load_users()
    users.add(update.effective_user.id)
    save_users(users)

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📩 Message Admin", callback_data="msg_admin")]
    ])
    await update.message.reply_text(
        "Welcome! 👋\n\nTap the button below to send a message to the admin.",
        reply_markup=kb
    )

async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "msg_admin":
        context.user_data["awaiting_msg"] = True
        await query.message.reply_text("Type your message below. I will forward it to the admin 👇")

async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = load_users()
    users.add(update.effective_user.id)
    save_users(users)

    if context.user_data.get("awaiting_msg"):
        user = update.effective_user

        await context.bot.forward_message(
            chat_id=ADMIN_ID,
            from_chat_id=update.message.chat_id,
            message_id=update.message.message_id
        )

        sent_msg = await update.message.reply_text("Message Sent ✅")
        await asyncio.sleep(10)
        try:
            await sent_msg.delete()
        except:
            pass

        context.user_data["awaiting_msg"] = False

async def broadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    if not update.message.reply_to_message:
        await update.message.reply_text(
            "Reply to any message with /broadcast to open the broadcast panel."
        )
        return

    context.bot_data["broadcast_msg"] = update.message.reply_to_message
    await update.message.reply_text(
        "📣 Broadcast panel opened.\n\nSend /confirm to start broadcasting or /cancel to abort."
    )

async def confirm_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    msg = context.bot_data.get("broadcast_msg")
    if not msg:
        await update.message.reply_text("No broadcast message found. Reply to a message with /broadcast first.")
        return

    users = load_users()

    total = len(users)
    success = 0
    blocked = 0
    deleted = 0
    failed = 0

    status_msg = await update.message.reply_text("📡 Broadcasting started...")

    for uid in users.copy():
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
            if "user is deactivated" in str(e).lower():
                deleted += 1
                users.discard(uid)
            else:
                failed += 1

        except Exception:
            failed += 1

    save_users(users)

    await status_msg.edit_text(
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

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(CommandHandler("broadcast", broadcast_cmd))
    app.add_handler(CommandHandler("confirm", confirm_broadcast))
    app.add_handler(CommandHandler("cancel", cancel_broadcast))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_user_message))

    app.run_polling()

if __name__ == "__main__":
    main()
