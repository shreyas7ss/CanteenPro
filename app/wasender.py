import httpx

from app.config import WASENDER_API_KEY

_API_URL = "https://www.wasenderapi.com/api/send-message"


async def send_text(to: str, text: str) -> None:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            _API_URL,
            headers={"Authorization": f"Bearer {WASENDER_API_KEY}", "Content-Type": "application/json"},
            json={"to": to, "text": text},
        )
        resp.raise_for_status()
