from typing import Optional

import httpx

from app.config import SUPABASE_SERVICE_ROLE_KEY, SUPABASE_URL

_REST_URL = f"{SUPABASE_URL}/rest/v1"
_HEADERS = {
    "apikey": SUPABASE_SERVICE_ROLE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
    "Content-Type": "application/json",
}


async def get_available_menu_items() -> list[dict]:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{_REST_URL}/menu_items",
            headers=_HEADERS,
            params={"is_available": "eq.true", "order": "category,name"},
        )
        resp.raise_for_status()
        return resp.json()


async def create_order(
    *,
    total_amount: float,
    merchant_transaction_id: str,
    student_name: str,
    roll_number: Optional[str] = None,
    customer_phone: Optional[str] = None,
    notes: str | None = None,
) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{_REST_URL}/orders",
            headers={**_HEADERS, "Prefer": "return=representation"},
            json={
                "customer_phone": customer_phone,
                "student_name": student_name,
                "roll_number": roll_number,
                "total_amount": total_amount,
                "merchant_transaction_id": merchant_transaction_id,
                "status": "pending_payment",
                "notes": notes,
            },
        )
        resp.raise_for_status()
        return resp.json()[0]


async def create_order_items(order_id: str, items: list[dict]) -> None:
    rows = [
        {
            "order_id": order_id,
            "menu_item_id": item["menu_item_id"],
            "item_name": item["item_name"],
            "unit_price": item["unit_price"],
            "quantity": item["quantity"],
        }
        for item in items
    ]
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{_REST_URL}/order_items", headers=_HEADERS, json=rows)
        resp.raise_for_status()


async def cancel_order(order_id: str, customer_phone: str) -> bool:
    """Cancels the order only if it's still pending_payment. Returns whether it
    actually cancelled anything (False if the order was already paid/ready/etc)."""
    async with httpx.AsyncClient() as client:
        resp = await client.patch(
            f"{_REST_URL}/orders",
            headers={**_HEADERS, "Prefer": "return=representation"},
            params={
                "id": f"eq.{order_id}",
                "customer_phone": f"eq.{customer_phone}",
                "status": "eq.pending_payment",
            },
            json={"status": "cancelled"},
        )
        resp.raise_for_status()
        return len(resp.json()) > 0


async def get_customer_order(order_id: str, customer_phone: str) -> Optional[dict]:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{_REST_URL}/orders",
            headers=_HEADERS,
            params={
                "id": f"eq.{order_id}",
                "customer_phone": f"eq.{customer_phone}",
                "select": "id,status,token_number",
            },
        )
        resp.raise_for_status()
        orders = resp.json()
        return orders[0] if orders else None


async def assign_next_token(order_id: str) -> int:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{_REST_URL}/rpc/assign_next_token",
            headers=_HEADERS,
            json={"p_order_id": order_id},
        )
        resp.raise_for_status()
        return resp.json()
