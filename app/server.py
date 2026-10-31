import logging
import re
import uuid
from hmac import compare_digest
from pathlib import Path
from urllib.parse import urlencode

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse

from app import db, getgabs
from app.config import CORS_ORIGINS, GETGABS_WEBHOOK_TOKEN, UPI_REDIRECT_BASE_URL
from app.upi import build_pay_link

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)
logger = logging.getLogger(__name__)

_WEBAPP_HTML = Path(__file__).parent / "static" / "webapp.html"
_LOGO_PNG = Path(__file__).parent / "static" / "logo.png"
_BRAND_LOGO_JPG = Path(__file__).parent.parent / "data" / "MvjLogo.jpg"
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


@app.get("/brand-logo.jpg")
async def serve_brand_logo():
    return FileResponse(_BRAND_LOGO_JPG)


@app.get("/pay/{txn_id}")
async def pay_redirect(txn_id: str, am: str, tn: str):
    link = build_pay_link(float(am), txn_id, tn)
    return RedirectResponse(link, status_code=302)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/api/menu")
async def api_menu():
    items = await db.get_available_menu_items()
    return [
        {key: item[key] for key in ("id", "name", "price", "category")}
        for item in items
    ]


async def _parse_wa_order(text: str) -> list[dict] | None:
    """Parse order format like '1x Bread Omelet, 2x Chai' or '1 Bread Omelet'"""
    if not text or len(text) < 2:
        return None

    items = []
    pattern = r"(\d+)\s*x?\s*(.+?)(?:,|$)"
    for qty_str, item_name in re.findall(pattern, text, re.IGNORECASE):
        quantity = int(qty_str)
        item_name = item_name.strip()
        if not item_name or not 1 <= quantity <= 20:
            return None
        items.append({"name": item_name, "quantity": quantity})
    return items or None


@app.post("/wa/webhook")
async def wa_webhook(request: Request):
    if not GETGABS_WEBHOOK_TOKEN:
        raise HTTPException(status_code=503, detail="WhatsApp webhook authentication is not configured")
    if not compare_digest(request.query_params.get("token", ""), GETGABS_WEBHOOK_TOKEN):
        raise HTTPException(status_code=403, detail="Invalid webhook token")

    try:
        body = await request.json()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid webhook JSON") from exc
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Invalid webhook payload")
    if body.get("direction") == "outbound":
        return {"ok": True}

    sender = re.sub(r"\D", "", str(body.get("message_from") or ""))
    text = str(body.get("message_text") or "").strip()
    if not sender or not text:
        return {"ok": True}
    if body.get("message_type") not in (None, "text", "button", "interactive"):
        await getgabs.send_text(sender, "Please send your order as text, or type MENU to see today's menu.")
        return {"ok": True}

    action_match = re.fullmatch(r"(paid|cancel)\s+([0-9a-f-]{36})", text, re.IGNORECASE)
    if text.lower() in {"paid", "cancel"}:
        await getgabs.send_text(sender, f"Reply {text.upper()} followed by your full order reference.")
        return {"ok": True}
    if action_match:
        try:
            order_id = str(uuid.UUID(action_match.group(2)))
        except ValueError:
            await getgabs.send_text(sender, "That order reference is invalid. Please check it and try again.")
            return {"ok": True}

        order = await db.get_customer_order(order_id, sender)
        if not order:
            await getgabs.send_text(sender, "That order was not found for your WhatsApp number.")
            return {"ok": True}

        if action_match.group(1).lower() == "cancel":
            cancelled = await db.cancel_order(order_id, sender)
            message = (
                "❌ Your order was cancelled."
                if cancelled
                else "That order can no longer be cancelled."
            )
        elif order["status"] == "cancelled":
            message = "That order was cancelled and can't be marked as paid."
        else:
            token = await db.assign_next_token(order_id)
            message = f"✅ Payment noted. Your canteen token is #{token}. Thank you!"
        await getgabs.send_text(sender, message)
        return {"ok": True}

    if text.lower() in {"hi", "hello", "hey", "menu", "help", "start"}:
        menu_items = await db.get_available_menu_items()
        menu_list = "\n".join(f"• {item['name']} ₹{item['price']}" for item in menu_items[:20])
        message = (
            f"👋 Welcome to LineZero Canteen!\n\n📋 Menu:\n{menu_list}"
            "\n\nOrder format: 1x Bread Omelet, 2x Chai"
        )
        await getgabs.send_text(sender, message)
        return {"ok": True}

    parsed_items = await _parse_wa_order(text)
    if not parsed_items:
        await getgabs.send_text(sender, "I couldn't read that order. Type MENU or use: 1x Bread Omelet, 2x Chai")
        return {"ok": True}

    try:
        menu_items = await db.get_available_menu_items()
        menu_by_name = {item["name"].casefold(): item for item in menu_items}
        order_items = []
        total = 0.0

        for parsed_item in parsed_items:
            menu_item = menu_by_name.get(parsed_item["name"].casefold())
            if not menu_item:
                names = ", ".join(item["name"] for item in menu_items[:5])
                await getgabs.send_text(sender, f"❌ '{parsed_item['name']}' not found. Try: {names}")
                return {"ok": True}

            quantity = parsed_item["quantity"]
            unit_price = float(menu_item["price"])
            total += unit_price * quantity
            order_items.append({
                "menu_item_id": menu_item["id"],
                "item_name": menu_item["name"],
                "unit_price": unit_price,
                "quantity": quantity,
            })

        transaction_id = str(uuid.uuid4())
        profile_name = str(body.get("profile_name") or "WhatsApp customer").strip()[:120]
        order = await db.create_order(
            customer_phone=sender,
            student_name=profile_name or "WhatsApp customer",
            total_amount=total,
            merchant_transaction_id=transaction_id,
            notes=f"WhatsApp order {transaction_id[:8]}",
        )
        await db.create_order_items(order["id"], order_items)

        note = f"LineZero order {transaction_id[:8]}"
        payment_url = f"{UPI_REDIRECT_BASE_URL}/pay/{transaction_id}?" + urlencode(
            {"am": f"{total:.2f}", "tn": note}
        )
        summary = "\n".join(
            f"{item['quantity']}× {item['item_name']} ₹{item['unit_price'] * item['quantity']:.2f}"
            for item in order_items
        )
        await getgabs.send_text(
            sender,
            f"🍽️ Order received!\n\n{summary}\n\nTotal: ₹{total:.2f}"
            f"\n\n💳 Pay here: {payment_url}\nOrder reference: {order['id']}"
            f"\n\nAfter paying, reply PAID {order['id']}. To cancel, reply CANCEL {order['id']}.",
        )
        return {"ok": True}
    except Exception:
        logger.exception("Failed to process GetGabs WhatsApp message")
        raise HTTPException(status_code=502, detail="Could not process WhatsApp message")


@app.post("/api/orders")
async def api_create_order(request: Request):
    try:
        body = await request.json()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid order JSON") from exc
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Invalid order payload")

    student_name = str(body.get("student_name") or "").strip()[:120]
    roll_number = str(body.get("roll_number") or "").strip()[:80]
    if not student_name or not roll_number:
        raise HTTPException(status_code=400, detail="student name and roll number are required")
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
        total_amount=total,
        merchant_transaction_id=merchant_txn_id,
        notes=f"Pickup: {pickup_slot}",
        student_name=student_name,
        roll_number=roll_number,
    )
    await db.create_order_items(order["id"], order_items)

    note = f"LineZero order {merchant_txn_id[:8]}"
    return {
        "order_id": order["id"],
        "total": total,
        "payment_url": build_pay_link(total, merchant_txn_id, note),
    }
