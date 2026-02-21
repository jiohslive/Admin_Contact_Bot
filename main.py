import os
import asyncio
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

# ========= CONFIG (Variables Only) =========
BOT_TOKEN = os.getenv("BOT_TOKEN")  # set in env
ADMIN_ID = int(os.getenv("ADMIN_ID"))  # set in env

# ========= STORAGE =========
USER_STATES = {}   # user_id: waiting
BLOCKED_USERS = set()
ADMIN_REPLY_MAP = {}  # admin_msg_id : user_id


# ========= HELPERS =========
async def auto_delete(context, chat_id, msg_id, delay=5):
    await asyncio.sleep(delay)
    try:
        await context.bot.delete_message(chat_id, msg_id)
    except:
        pass


# ========= START =========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📩 Message Admin", callback_data="msg_admin")]
    ])
    msg = await update.message.reply_text(
        "Welcome! 👋\nTap the button below to message the admin.",
        reply_markup=keyboard
    )
    asyncio.create_task(auto_delete(context, update.effective_chat.id, msg.message_id))


# ========= USER CLICKS BUTTON =========
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "msg_admin":
        USER_STATES[query.from_user.id] = True
        msg = await query.message.reply_text("Type your message below 👇")
        asyncio.create_task(auto_delete(context, query.message.chat_id, msg.message_id))


# ========= USER MESSAGE =========
async def user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text

    if user.id in BLOCKED_USERS:
        return

    # Direct forward without forcing button click
    sent = await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=f"📩 New Message\n\n👤 User: {user.full_name}\n🆔 ID: {user.id}\n\n💬 {text}"
    )

    ADMIN_REPLY_MAP[sent.message_id] = user.id

    status = await update.message.reply_text("✅ Message sent")
    asyncio.create_task(auto_delete(context, update.effective_chat.id, status.message_id))


# ========= ADMIN REPLY =========
async def admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    if not update.message.reply_to_message:
        return

    replied_id = update.message.reply_to_message.message_id

    if replied_id in ADMIN_REPLY_MAP:
        user_id = ADMIN_REPLY_MAP[replied_id]

        await context.bot.send_message(
            chat_id=user_id,
            text=f"💬 Admin Reply:\n\n{update.message.text}"
        )


# ========= ADMIN PANEL =========
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚫 Block User", callback_data="block")],
        [InlineKeyboardButton("✅ Unblock User", callback_data="unblock")]
    ])

    await update.message.reply_text("Admin Panel:", reply_markup=keyboard)


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

    uid = int(update.message.text)

    if action == "block":
        BLOCKED_USERS.add(uid)
        await update.message.reply_text(f"🚫 User {uid} blocked.")
    elif action == "unblock":
        BLOCKED_USERS.discard(uid)
        await update.message.reply_text(f"✅ User {uid} unblocked.")

    context.user_data["action"] = None


# ========= MAIN =========
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CallbackQueryHandler(button_handler, pattern="msg_admin"))
    app.add_handler(CallbackQueryHandler(admin_buttons))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.User(ADMIN_ID), user_message))
    app.add_handler(MessageHandler(filters.TEXT & filters.User(ADMIN_ID), admin_reply))
    app.add_handler(MessageHandler(filters.TEXT & filters.User(ADMIN_ID), receive_user_id))

    print("Bot Running...")
    app.run_polling()


if __name__ == "__main__":
    main()
