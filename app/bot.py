from pathlib import Path

import httpx
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, MenuButtonWebApp, Update, WebAppInfo
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

from app import db
from app.config import TELEGRAM_BOT_TOKEN, UPI_REDIRECT_BASE_URL

# Telegram caches Mini App content by URL, sometimes aggressively, independent of
# HTTP cache headers. Appending the file's mtime busts that cache on every code
# change, since the URL itself changes rather than relying on Telegram to notice
# the content did.
_WEBAPP_VERSION = int((Path(__file__).parent / "static" / "webapp.html").stat().st_mtime)
WEBAPP_URL = f"{UPI_REDIRECT_BASE_URL}/app?v={_WEBAPP_VERSION}"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("\U0001f37d Open Menu", web_app=WebAppInfo(url=WEBAPP_URL))]]
    )
    await update.message.reply_text(
        "Welcome to LineZero! Tap below to browse the menu and order.",
        reply_markup=keyboard,
    )


async def paid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    order_id = query.data.split(":", 1)[1]

    try:
        token = await db.assign_next_token(order_id)
    except httpx.HTTPStatusError:
        await query.answer("This order was cancelled and can't be paid.", show_alert=True)
        return

    await query.answer()
    await query.edit_message_caption(caption=f"Paid ✅ Your token is #{token}", reply_markup=None)
    await query.message.reply_text(f"Paid ✅ Your token is #{token}\nWe'll notify you when it's ready.")


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    order_id = query.data.split(":", 1)[1]

    cancelled = await db.cancel_order(order_id)
    if not cancelled:
        await query.answer("This order was already paid and can't be cancelled.", show_alert=True)
        return

    await query.answer("Order cancelled")
    await query.edit_message_caption(caption="❌ Order cancelled.", reply_markup=None)


async def set_menu_button(application: Application) -> None:
    await application.bot.set_chat_menu_button(
        menu_button=MenuButtonWebApp(text="Order", web_app=WebAppInfo(url=WEBAPP_URL))
    )


def build_application() -> Application:
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(paid, pattern="^paid:"))
    application.add_handler(CallbackQueryHandler(cancel, pattern="^cancel:"))
    return application
