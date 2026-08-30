import uuid
from pathlib import Path
from urllib.parse import urlencode

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application

from app import db, wasender
from app.config import TELEGRAM_BOT_TOKEN, UPI_REDIRECT_BASE_URL
from app.telegram_auth import InvalidInitData, validate_init_data
from app.upi import build_pay_link, build_qr_png

app = FastAPI()

_bot_app: Application = None

_WEBAPP_HTML = Path(__file__).parent / "static" / "webapp.html"
_LOGO_PNG = Path(__file__).parent / "static" / "logo.png"
_DASHBOARD_HTML = Path(__file__).parent.parent / "dashboard.html"


@app.get("/app")
async def serve_webapp():
    return FileResponse(_WEBAPP_HTML, headers={"Cache-Control": "no-store, must-revalidate"})


@app.get("/dashboard")
async def serve_dashboard():
    return FileResponse(_DASHBOARD_HTML, headers={"Cache-Control": "no-store, must-revalidate"})


@app.get("/logo.png")
async def serve_logo():
    return FileResponse(_LOGO_PNG)


@app.get("/pay/{txn_id}")
async def pay_redirect(txn_id: str, am: str, tn: str):
    link = build_pay_link(float(am), txn_id, tn)
    return RedirectResponse(link, status_code=302)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.on_event("startup")
async def startup_bot():
    global _bot_app
    if _bot_app is None:
        from app.bot import build_application, set_menu_button
        _bot_app = build_application()
        await _bot_app.initialize()
        await set_menu_button(_bot_app)
        await _bot_app.start()


@app.post("/telegram/webhook")
async def telegram_webhook(update: dict):
    global _bot_app
    if _bot_app is None:
        raise HTTPException(status_code=503, detail="Bot not initialized")

    try:
        tg_update = Update.de_json(update, _bot_app.bot)
        await _bot_app.process_update(tg_update)
        return {"ok": True}
    except Exception as e:
        print(f"Error processing Telegram update: {e}")
        return {"ok": True}


async def _parse_wa_order(text: str) -> list[dict] | None:
    """Parse order format like '1x Bread Omelet, 2x Chai' or '1 Bread Omelet'"""
    import re

    if not text or len(text) < 2:
        return None

    items = []
    # Match patterns like "1x Item" or "1 Item" or "1x Item Name"
    pattern = r'(\d+)\s*x?\s*(.+?)(?:,|$)'
    matches = re.findall(pattern, text, re.IGNORECASE)

    if not matches:
        return None

    for qty_str, item_name in matches:
        try:
            qty = int(qty_str)
            item_name = item_name.strip()
            if item_name:
                items.append({"name": item_name, "quantity": qty})
        except ValueError:
            continue

    return items if items else None


@app.post("/wa/webhook")
async def wa_webhook(request: Request):
    body = await request.json()

    messages = body.get("data", {}).get("messages", {})
    key = messages.get("key", {})
    if key.get("fromMe"):
        return {"ok": True}

    sender = key.get("cleanedSenderPn")
    text = messages.get("messageBody") or messages.get("message", {}).get("conversation")
    if not sender or not text:
        return {"ok": True}

    # Try to parse as order
    parsed_items = await _parse_wa_order(text)
    if parsed_items:
        try:
            # Get menu items to match against
            menu_items = await db.get_available_menu_items()
            menu_by_name = {item["name"].lower(): item for item in menu_items}

            order_items = []
            total = 0.0
            matched_items = []

            for parsed_item in parsed_items:
                # Try to find matching menu item (case-insensitive)
                menu_item = menu_by_name.get(parsed_item["name"].lower())
                if menu_item:
                    qty = parsed_item["quantity"]
                    unit_price = float(menu_item["price"])
                    total += unit_price * qty
                    order_items.append({
                        "menu_item_id": menu_item["id"],
                        "item_name": menu_item["name"],
                        "unit_price": unit_price,
                        "quantity": qty,
                    })
                    matched_items.append(f"{qty}× {menu_item['name']} ₹{unit_price * qty:.2f}")
                else:
                    # Item not found
                    await wasender.send_text(f"+{sender}", f"❌ '{parsed_item['name']}' not found. Try: {', '.join([m['name'] for m in menu_items[:5]])}")
                    return {"ok": True}

            if not order_items:
                await wasender.send_text(f"+{sender}", "❌ No valid items found. Please check spelling and try again.")
                return {"ok": True}

            # Create order
            merchant_txn_id = str(uuid.uuid4())
            order = await db.create_order(
                telegram_user_id=int(sender) if sender.isdigit() else 0,
                telegram_username=f"wa_{sender}",
                total_amount=total,
                merchant_transaction_id=merchant_txn_id,
                notes=f"WhatsApp: +{sender}",
            )
            await db.create_order_items(order["id"], order_items)

            # Send payment link
            note = f"LineZero order {merchant_txn_id[:8]}"
            pay_link = build_pay_link(total, merchant_txn_id, note)
            pay_redirect_url = f"{UPI_REDIRECT_BASE_URL}/pay/{merchant_txn_id}?" + urlencode({"am": f"{total:.2f}", "tn": note})

            summary = "\n".join(matched_items)
            msg = f"🍽️ Order Confirmed!\n\n{summary}\n\nTotal: ₹{total:.2f}\n\n💳 Pay here: {pay_redirect_url}"
            await wasender.send_text(f"+{sender}", msg)
            return {"ok": True}
        except Exception as e:
            print(f"Error processing WhatsApp order: {e}")
            await wasender.send_text(f"+{sender}", "❌ Error processing order. Please try again.")
            return {"ok": True}
    else:
        # Send menu if not an order
        menu_items = await db.get_available_menu_items()
        menu_list = "\n".join([f"• {item['name']} ₹{item['price']}" for item in menu_items[:10]])
        msg = f"👋 Welcome to LineZero Canteen!\n\n📋 Menu:\n{menu_list}\n\nOrder format: '1x Bread Omelet, 2x Chai'"
        await wasender.send_text(f"+{sender}", msg)
        return {"ok": True}


def _validated_user(init_data: str) -> dict:
    try:
        return validate_init_data(init_data, TELEGRAM_BOT_TOKEN)["user"]
    except InvalidInitData as exc:
        raise HTTPException(status_code=401, detail=str(exc))


@app.post("/api/orders")
async def api_create_order(request: Request):
    body = await request.json()
    telegram_user = _validated_user(body.get("init_data", ""))
    items = body.get("items", [])
    pickup_slot = body.get("pickup_slot") or "Right now"
    if not items:
        raise HTTPException(status_code=400, detail="cart is empty")

    menu_by_id = {item["id"]: item for item in await db.get_available_menu_items()}

    order_items = []
    total = 0.0
    for line in items:
        menu_item = menu_by_id.get(line.get("menu_item_id"))
        quantity = int(line.get("quantity", 0))
        if menu_item is None or quantity <= 0:
            raise HTTPException(status_code=400, detail=f"invalid item {line.get('menu_item_id')}")
        unit_price = float(menu_item["price"])
        total += unit_price * quantity
        order_items.append(
            {
                "menu_item_id": menu_item["id"],
                "item_name": menu_item["name"],
                "unit_price": unit_price,
                "quantity": quantity,
            }
        )

    merchant_txn_id = str(uuid.uuid4())
    order = await db.create_order(
        telegram_user_id=telegram_user["id"],
        telegram_username=telegram_user.get("username"),
        total_amount=total,
        merchant_transaction_id=merchant_txn_id,
        notes=f"Pickup: {pickup_slot}",
    )
    await db.create_order_items(order["id"], order_items)

    await _send_pay_message(
        chat_id=telegram_user["id"],
        order_id=order["id"],
        order_items=order_items,
        total=total,
        merchant_txn_id=merchant_txn_id,
        pickup_slot=pickup_slot,
    )

    return {"order_id": order["id"], "total": total}


async def _send_pay_message(
    *, chat_id: int, order_id: str, order_items: list[dict], total: float, merchant_txn_id: str, pickup_slot: str
) -> None:
    note = f"LineZero order {merchant_txn_id[:8]}"
    pay_link = build_pay_link(total, merchant_txn_id, note)
    qr_png = build_qr_png(pay_link)
    pay_redirect_url = f"{UPI_REDIRECT_BASE_URL}/pay/{merchant_txn_id}?" + urlencode({"am": f"{total:.2f}", "tn": note})

    lines = [f"{item['quantity']} × {item['item_name']} — ₹{item['unit_price'] * item['quantity']:.2f}" for item in order_items]
    caption = (
        "🧾 Order Summary\n"
        + "\n".join(lines)
        + f"\n\nPickup: {pickup_slot}"
        + f"\nTotal: ₹{total:.2f}"
    )

    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("\U0001f4b3 Pay Now", url=pay_redirect_url)],
            [InlineKeyboardButton("✅ I've Paid", callback_data=f"paid:{order_id}")],
            [InlineKeyboardButton("❌ Cancel Order", callback_data=f"cancel:{order_id}")],
        ]
    )

    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    await bot.send_photo(chat_id=chat_id, photo=qr_png, caption=caption, reply_markup=keyboard)
