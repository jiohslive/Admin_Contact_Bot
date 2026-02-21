import os
import json
import asyncio
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ChatAction
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)
from telegram.error import Forbidden

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

USERS_FILE = "users.json"
ADMIN_REPLY_MAP = {}
BLOCKED_USERS = set()

def load_users():
    if not os.path.exists(USERS_FILE):
        return set()
    with open(USERS_FILE, "r") as f:
        return set(json.load(f))

def save_users(users):
    with open(USERS_FILE, "w") as f:
        json.dump(list(users), f)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = load_users()
    users.add(update.effective_user.id)
    save_users(users)

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📩 Message Admin", callback_data="msg_admin")]
    ])
    await update.message.reply_text("Welcome! 👋\n\nTap below 👇", reply_markup=kb)

async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.message.reply_text("Type your message 👇")

async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id in BLOCKED_USERS:
        return

    users = load_users()
    users.add(user.id)
    save_users(users)

    mention = f"<a href='tg://user?id={user.id}'>{user.full_name}</a>"

    header = await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=(
            "📩 <b>New Message From</b>\n"
            f"👤 User: {mention}\n"
            f"🆔 User ID: <code>{user.id}</code>\n\n"
            "💬 <b>User Message 👇</b>"
        ),
        parse_mode="HTML"
    )

    msg = await context.bot.copy_message(
        chat_id=ADMIN_ID,
        from_chat_id=update.effective_chat.id,
        message_id=update.message.message_id,
        reply_to_message_id=header.message_id  # 👈 SAME THREAD
    )

    ADMIN_REPLY_MAP[msg.message_id] = user.id

    await update.message.reply_text("✅ Message Sent")

async def admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    if not update.message.reply_to_message:
        return

    replied_id = update.message.reply_to_message.message_id

    if replied_id in ADMIN_REPLY_MAP:
        user_id = ADMIN_REPLY_MAP[replied_id]

        await context.bot.copy_message(
            chat_id=user_id,
            from_chat_id=update.effective_chat.id,
            message_id=update.message.message_id
        )

async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(on_button))

    # ADMIN reply first
    app.add_handler(MessageHandler(filters.ALL & filters.User(ADMIN_ID), admin_reply))

    # USER messages last
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_user_message))

    app.run_polling()

if __name__ == "__main__":
    main()
