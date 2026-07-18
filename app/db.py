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
    telegram_user_id: int,
    telegram_username: Optional[str],
    total_amount: float,
    merchant_transaction_id: str,
    notes: Optional[str] = None,
) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{_REST_URL}/orders",
            headers={**_HEADERS, "Prefer": "return=representation"},
            json={
                "telegram_user_id": telegram_user_id,
                "telegram_username": telegram_username,
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


async def cancel_order(order_id: str) -> bool:
    """Cancels the order only if it's still pending_payment. Returns whether it
    actually cancelled anything (False if the order was already paid/ready/etc)."""
    async with httpx.AsyncClient() as client:
        resp = await client.patch(
            f"{_REST_URL}/orders",
            headers={**_HEADERS, "Prefer": "return=representation"},
            params={"id": f"eq.{order_id}", "status": "eq.pending_payment"},
            json={"status": "cancelled"},
        )
        resp.raise_for_status()
        return len(resp.json()) > 0


async def assign_next_token(order_id: str) -> int:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{_REST_URL}/rpc/assign_next_token",
            headers=_HEADERS,
            json={"p_order_id": order_id},
        )
        resp.raise_for_status()
        return resp.json()
