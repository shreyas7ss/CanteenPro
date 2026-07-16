from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from app.upi import build_pay_link

app = FastAPI()


@app.get("/pay/{txn_id}")
async def pay_redirect(txn_id: str, am: str, tn: str):
    link = build_pay_link(float(am), txn_id, tn)
    return RedirectResponse(link, status_code=302)


@app.get("/health")
async def health():
    return {"status": "ok"}
