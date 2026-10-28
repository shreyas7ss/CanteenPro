import httpx

from app.config import GETGABS_API_KEY

_API_URL = "https://app.getgabs.com/sendservicemessages/sendmessages"


async def send_text(to: str, text: str) -> None:
    if not GETGABS_API_KEY:
        raise RuntimeError("GETGABS_API_KEY is not configured")

    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            _API_URL,
            headers={"Content-Type": "application/json"},
            json={
                "to": to,
                "text": {"body": text, "preview_url": True},
                "type": "text",
                "recipient_type": "individual",
                "messaging_product": "whatsapp",
                "api_key": GETGABS_API_KEY,
            },
        )
        response.raise_for_status()
