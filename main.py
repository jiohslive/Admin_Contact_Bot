import os
import asyncio
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

users_db = set()
blocked_users = set()

# ================= START =================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    users_db.add(user.id)

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📩 Message Admin", callback_data="msg_admin")]
    ])

    await update.message.reply_text(
        "Welcome! 👋\n\nTap the button below to send a message to the admin.",
        reply_markup=keyboard
    )

# ================= CALLBACK =================

async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "msg_admin":
        await query.message.reply_text(
            "Type your message below. I will forward it to the admin 👇"
        )

    elif query.data == "admin_panel":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🚫 Block User", callback_data="block_user")],
            [InlineKeyboardButton("✅ Unblock User", callback_data="unblock_user")],
        ])
        await query.message.reply_text("Admin Panel:", reply_markup=keyboard)

# ================= USER MESSAGE =================

async def user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if user.id in blocked_users:
        return

    users_db.add(user.id)

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    caption = update.message.caption if update.message.caption else ""

    text_info = (
        f"📩 New Message\n\n"
        f"👤 User: {user.full_name}\n"
        f"🆔 ID: {user.id}\n"
    )

    if update.message.text:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=text_info + f"\n💬 Message:\n{update.message.text}"
        )
    else:
        await context.bot.copy_message(
            chat_id=ADMIN_ID,
            from_chat_id=update.effective_chat.id,
            message_id=update.message.message_id,
            caption=text_info + f"\n💬 Message:\n{caption}" if caption else text_info
        )

    confirm = await update.message.reply_text("Message Sent ✅")

    await asyncio.sleep(2)
    try:
        await confirm.delete()
    except:
        pass

# ================= ADMIN REPLY =================

async def admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_ID:
        return

    if not update.message.reply_to_message:
        return

    text = update.message.reply_to_message.text or update.message.reply_to_message.caption
    if not text or "ID:" not in text:
        return

    try:
        user_id = int(text.split("ID:")[1].split("\n")[0].strip())
    except:
        return

    await context.bot.copy_message(
        chat_id=user_id,
        from_chat_id=ADMIN_ID,
        message_id=update.message.message_id
    )

# ================= BROADCAST =================

async def broadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_ID:
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to a message with /broadcast")
        return

    success = 0
    blocked = 0
    failed = 0

    for uid in users_db:
        if uid == ADMIN_ID:
            continue

        try:
            await context.bot.copy_message(
                chat_id=uid,
                from_chat_id=ADMIN_ID,
                message_id=update.message.reply_to_message.message_id
            )
            success += 1
        except:
            failed += 1

    report = (
        "Broadcast completed ✅\n\n"
        f"◇ Total Users: {len(users_db)}\n"
        f"◇ Successful: {success}\n"
        f"◇ Blocked Users: {len(blocked_users)}\n"
        f"◇ Deleted Accounts: 0\n"
        f"◇ Unsuccessful: {failed}"
    )

    await update.message.reply_text(report)

# ================= ADMIN PANEL =================

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_ID:
        return

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚫 Block User", callback_data="block_user")],
        [InlineKeyboardButton("✅ Unblock User", callback_data="unblock_user")],
    ])
    await update.message.reply_text("Admin Panel:", reply_markup=keyboard)

# ================= MAIN =================

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("broadcast", broadcast_cmd))
    app.add_handler(CommandHandler("admin", admin_panel))

    app.add_handler(CallbackQueryHandler(callbacks))

    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, user_message))
    app.add_handler(MessageHandler(filters.ALL & filters.Chat(ADMIN_ID), admin_reply))

    print("Bot Started...")
    app.run_polling()

if __name__ == "__main__":
    main()
