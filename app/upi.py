import io
from urllib.parse import quote

import qrcode

from app.config import UPI_PAYEE_NAME, UPI_VPA


def build_pay_link(amount: float, merchant_txn_id: str, note: str) -> str:
    params = {
        "pa": UPI_VPA,
        "pn": UPI_PAYEE_NAME,
        "am": f"{amount:.2f}",
        "tr": merchant_txn_id,
        "tn": note,
        "cu": "INR",
    }
    # Percent-encode spaces as %20 (quote, not quote_plus/urlencode's "+") —
    # some UPI apps' intent parsers treat a literal "+" as a plus sign rather
    # than a space, which silently corrupts the payee name/note.
    query = "&".join(f"{key}={quote(value, safe='')}" for key, value in params.items())
    return "upi://pay?" + query


def build_qr_png(upi_link: str) -> bytes:
    img = qrcode.make(upi_link)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
