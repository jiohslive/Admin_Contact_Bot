import os
import json
import asyncio
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)
from telegram.error import Forbidden, BadRequest
from telegram.constants import ChatAction

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

if not BOT_TOKEN or not ADMIN_ID:
    raise RuntimeError("Please set BOT_TOKEN and ADMIN_ID environment variables.")

USERS_FILE = "users.json"
BLOCKED_FILE = "blocked.json"

def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, "r") as f:
        return json.load(f)

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f)

def load_users():
    return set(load_json(USERS_FILE, []))

def save_users(users: set):
    save_json(USERS_FILE, list(users))

def load_blocked():
    return set(load_json(BLOCKED_FILE, []))

def save_blocked(blocked: set):
    save_json(BLOCKED_FILE, list(blocked))

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
    user_id = update.effective_user.id

    users = load_users()
    users.add(user_id)
    save_users(users)

    blocked = load_blocked()
    if user_id in blocked:
        return

    if context.user_data.get("awaiting_msg"):
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
        await asyncio.sleep(1)

        forwarded = await context.bot.forward_message(
            chat_id=ADMIN_ID,
            from_chat_id=update.message.chat_id,
            message_id=update.message.message_id
        )

        context.bot_data.setdefault("msg_map", {})
        context.bot_data["msg_map"][forwarded.message_id] = user_id

        sent_msg = await update.message.reply_text("Message Sent ✅")
        await asyncio.sleep(3)
        try:
            await sent_msg.delete()
        except:
            pass

        context.user_data["awaiting_msg"] = False

async def handle_admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    if not update.message.reply_to_message:
        return

    msg_map = context.bot_data.get("msg_map", {})
    original_msg_id = update.message.reply_to_message.message_id
    user_id = msg_map.get(original_msg_id)

    if not user_id:
        return

    if update.message.text == "/block":
        blocked = load_blocked()
        blocked.add(user_id)
        save_blocked(blocked)
        await update.message.reply_text("🚫 User blocked.")
        return

    if update.message.text == "/unblock":
        blocked = load_blocked()
        blocked.discard(user_id)
        save_blocked(blocked)
        await update.message.reply_text("✅ User unblocked.")
        return

    try:
        await context.bot.copy_message(
            chat_id=user_id,
            from_chat_id=update.message.chat_id,
            message_id=update.message.message_id
        )
    except:
        pass

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📣 Broadcast", callback_data="panel_broadcast")],
        [InlineKeyboardButton("📊 Stats", callback_data="panel_stats")],
    ])

    await update.message.reply_text("🛠 Admin Panel", reply_markup=kb)

async def panel_actions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if update.effective_user.id != ADMIN_ID:
        return

    if query.data == "panel_stats":
        users = load_users()
        blocked = load_blocked()
        await query.message.reply_text(
            f"📊 Bot Stats\n\n"
            f"◇ Total Users: {len(users)}\n"
            f"◇ Blocked Users: {len(blocked)}"
        )

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
    blocked = load_blocked()

    users = users - blocked

    total = len(users)
    success = 0
    blocked_cnt = 0
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
            blocked_cnt += 1
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
        f"◇ Blocked Users: {blocked_cnt}\n"
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
    app.add_handler(CommandHandler("panel", admin_panel))
    app.add_handler(CallbackQueryHandler(panel_actions))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(CommandHandler("broadcast", broadcast_cmd))
    app.add_handler(CommandHandler("confirm", confirm_broadcast))
    app.add_handler(CommandHandler("cancel", cancel_broadcast))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_user_message))
    app.add_handler(MessageHandler(filters.ALL & filters.User(ADMIN_ID), handle_admin_reply))

    app.run_polling()

if __name__ == "__main__":
    main()
