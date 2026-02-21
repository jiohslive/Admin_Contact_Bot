import os
import json
import asyncio
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ChatAction
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)
from telegram.error import Forbidden, BadRequest

# ========= CONFIG =========
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

if not BOT_TOKEN or not ADMIN_ID:
    raise RuntimeError("Please set BOT_TOKEN and ADMIN_ID in env variables")

USERS_FILE = "users.json"

# ========= STORAGE =========
BLOCKED_USERS = set()
ADMIN_REPLY_MAP = {}  # admin_msg_id -> user_id

# ========= USERS DB =========
def load_users():
    if not os.path.exists(USERS_FILE):
        return set()
    with open(USERS_FILE, "r") as f:
        return set(json.load(f))

def save_users(users: set):
    with open(USERS_FILE, "w") as f:
        json.dump(list(users), f)

# ========= AUTO DELETE (ONLY MESSAGE SENT) =========
async def auto_delete(context, chat_id, msg_id, delay=5):
    await asyncio.sleep(delay)
    try:
        await context.bot.delete_message(chat_id, msg_id)
    except:
        pass

# ========= START =========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = load_users()
    users.add(update.effective_user.id)
    save_users(users)

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📩 Message Admin", callback_data="msg_admin")]
    ])
    await update.message.reply_text(
        "Welcome! 👋\n\nTap the button below to message the admin.",
        reply_markup=kb
    )

# ========= BUTTON =========
async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "msg_admin":
        await query.message.reply_text("Type your message below 👇")

# ========= USER MESSAGE =========
async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if user.id in BLOCKED_USERS:
        return

    users = load_users()
    users.add(user.id)
    save_users(users)

    mention = f"<a href='tg://user?id={user.id}'>{user.full_name}</a>"

    # Typing indicator to admin
    await context.bot.send_chat_action(chat_id=ADMIN_ID, action=ChatAction.TYPING)

    sent = await context.bot.copy_message(
        chat_id=ADMIN_ID,
        from_chat_id=update.effective_chat.id,
        message_id=update.message.message_id
    )

    info = await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=(
            "📩 <b>New Message From</b>\n"
            f"👤 User: {mention}\n"
            f"🆔 User ID: <code>{user.id}</code>\n\n"
            "💬 <b>User Message 👇</b>"
        ),
        parse_mode="HTML"
    )

    ADMIN_REPLY_MAP[sent.message_id] = user.id
    ADMIN_REPLY_MAP[info.message_id] = user.id

    status = await update.message.reply_text("✅ Message Sent")
    asyncio.create_task(auto_delete(context, update.effective_chat.id, status.message_id, 5))

# ========= ADMIN REPLY =========
async def admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    if not update.message.reply_to_message:
        return

    replied_id = update.message.reply_to_message.message_id

    if replied_id in ADMIN_REPLY_MAP:
        user_id = ADMIN_REPLY_MAP[replied_id]

        await context.bot.send_chat_action(chat_id=user_id, action=ChatAction.TYPING)

        await context.bot.copy_message(
            chat_id=user_id,
            from_chat_id=update.effective_chat.id,
            message_id=update.message.message_id
        )

# ========= BROADCAST =========
async def broadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to any message with /broadcast")
        return

    context.bot_data["broadcast_msg"] = update.message.reply_to_message
    await update.message.reply_text("Send /confirm to broadcast or /cancel")

async def confirm_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    msg = context.bot_data.get("broadcast_msg")
    if not msg:
        return

    users = load_users()
    for uid in list(users):
        try:
            await context.bot.copy_message(
                chat_id=uid,
                from_chat_id=msg.chat_id,
                message_id=msg.message_id
            )
            await asyncio.sleep(0.05)
        except:
            users.discard(uid)

    save_users(users)
    context.bot_data.pop("broadcast_msg", None)
    await update.message.reply_text("✅ Broadcast done")

async def cancel_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    context.bot_data.pop("broadcast_msg", None)
    await update.message.reply_text("❌ Cancelled")

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

    uid = int(update.message.text)

    if action == "block":
        BLOCKED_USERS.add(uid)
        await update.message.reply_text(f"🚫 Blocked {uid}")
    else:
        BLOCKED_USERS.discard(uid)
        await update.message.reply_text(f"✅ Unblocked {uid}")

    context.user_data.pop("action", None)

# ======= MAIN =======
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(on_button, pattern="^msg_admin$"))
    app.add_handler(CommandHandler("broadcast", broadcast_cmd))
    app.add_handler(CommandHandler("confirm", confirm_broadcast))
    app.add_handler(CommandHandler("cancel", cancel_broadcast))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CallbackQueryHandler(admin_buttons, pattern="^(block|unblock)$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.User(ADMIN_ID), receive_user_id))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND & filters.User(ADMIN_ID), admin_reply))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_user_message))

    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
