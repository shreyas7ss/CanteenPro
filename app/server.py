import uuid
from pathlib import Path
from urllib.parse import urlencode

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

from app import db
from app.config import TELEGRAM_BOT_TOKEN, UPI_REDIRECT_BASE_URL
from app.telegram_auth import InvalidInitData, validate_init_data
from app.upi import build_pay_link, build_qr_png

app = FastAPI()

_WEBAPP_HTML = Path(__file__).parent / "static" / "webapp.html"


@app.get("/app")
async def serve_webapp():
    return FileResponse(_WEBAPP_HTML, headers={"Cache-Control": "no-store, must-revalidate"})


@app.get("/pay/{txn_id}")
async def pay_redirect(txn_id: str, am: str, tn: str):
    link = build_pay_link(float(am), txn_id, tn)
    return RedirectResponse(link, status_code=302)


@app.get("/health")
async def health():
    return {"status": "ok"}


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
