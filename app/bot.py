import uuid
from urllib.parse import urlencode

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

from app import cart as cart_store
from app import db
from app.config import TELEGRAM_BOT_TOKEN, UPI_REDIRECT_BASE_URL
from app.upi import build_pay_link, build_qr_png


def _rupees(amount: float) -> str:
    return f"₹{amount:.2f}"


async def _menu_keyboard() -> InlineKeyboardMarkup:
    items = await db.get_available_menu_items()
    rows = [
        [InlineKeyboardButton(f"{item['name']} — {_rupees(item['price'])}", callback_data=f"add:{item['id']}")]
        for item in items
    ]
    rows.append([InlineKeyboardButton("\U0001f6d2 View Cart", callback_data="cart")])
    return InlineKeyboardMarkup(rows)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Welcome to LineZero! Add items from the menu, then pay via UPI to get your token.",
        reply_markup=await _menu_keyboard(),
    )


async def show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("Menu:", reply_markup=await _menu_keyboard())


async def add_to_cart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    menu_item_id = query.data.split(":", 1)[1]

    items = await db.get_available_menu_items()
    item = next((i for i in items if i["id"] == menu_item_id), None)
    if item is None:
        await query.answer("That item is no longer available.", show_alert=True)
        return

    cart_store.add_item(update.effective_user.id, item["id"], item["name"], float(item["price"]))
    await query.answer(f"Added {item['name']} to cart")


async def view_cart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    telegram_user_id = update.effective_user.id
    cart = cart_store.get_cart(telegram_user_id)
    if not cart:
        await query.message.reply_text("Your cart is empty. Add something from the menu first.")
        return

    lines = [
        f"{item.quantity} × {item.item_name} — {_rupees(item.unit_price * item.quantity)}"
        for item in cart.values()
    ]
    total = cart_store.cart_total(telegram_user_id)
    text = "\n".join(lines) + f"\n\nTotal: {_rupees(total)}"

    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅ Confirm & Pay", callback_data="checkout")],
            [InlineKeyboardButton("\U0001f5d1 Clear Cart", callback_data="clear")],
            [InlineKeyboardButton("⬅ Back to Menu", callback_data="menu")],
        ]
    )
    await query.message.reply_text(text, reply_markup=keyboard)


async def clear_cart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    cart_store.clear_cart(update.effective_user.id)
    await query.answer("Cart cleared")
    await query.message.reply_text("Cart cleared.")


async def checkout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    telegram_user_id = update.effective_user.id
    cart = cart_store.get_cart(telegram_user_id)
    if not cart:
        await query.answer("Your cart is empty.", show_alert=True)
        return
    await query.answer()

    total = cart_store.cart_total(telegram_user_id)
    merchant_txn_id = str(uuid.uuid4())

    order = await db.create_order(
        telegram_user_id=telegram_user_id,
        telegram_username=update.effective_user.username,
        total_amount=total,
        merchant_transaction_id=merchant_txn_id,
    )
    await db.create_order_items(
        order["id"],
        [
            {
                "menu_item_id": item.menu_item_id,
                "item_name": item.item_name,
                "unit_price": item.unit_price,
                "quantity": item.quantity,
            }
            for item in cart.values()
        ],
    )

    note = f"LineZero order {merchant_txn_id[:8]}"
    pay_link = build_pay_link(total, merchant_txn_id, note)
    qr_png = build_qr_png(pay_link)
    button_url = f"{UPI_REDIRECT_BASE_URL}/pay/{merchant_txn_id}?" + urlencode({"am": f"{total:.2f}", "tn": note})

    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("\U0001f4b3 Pay via UPI", url=button_url)],
            [InlineKeyboardButton("✅ I've Paid", callback_data=f"paid:{order['id']}")],
        ]
    )
    await query.message.reply_photo(
        photo=qr_png,
        caption=(
            f"Total: {_rupees(total)}\n"
            "Tap \"Pay via UPI\", or scan this QR with any UPI app.\n"
            "After paying, tap \"I've Paid\" below."
        ),
        reply_markup=keyboard,
    )

    cart_store.clear_cart(telegram_user_id)


async def paid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    order_id = query.data.split(":", 1)[1]

    token = await db.assign_next_token(order_id)
    await query.message.reply_text(f"Paid ✅ Your token is #{token}\nWe'll notify you when it's ready.")


def build_application() -> Application:
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(show_menu, pattern="^menu$"))
    application.add_handler(CallbackQueryHandler(add_to_cart, pattern="^add:"))
    application.add_handler(CallbackQueryHandler(view_cart, pattern="^cart$"))
    application.add_handler(CallbackQueryHandler(clear_cart, pattern="^clear$"))
    application.add_handler(CallbackQueryHandler(checkout, pattern="^checkout$"))
    application.add_handler(CallbackQueryHandler(paid, pattern="^paid:"))
    return application
