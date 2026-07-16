import os
import sys

from dotenv import load_dotenv

load_dotenv()


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        print(f"Missing required environment variable: {name}", file=sys.stderr)
        sys.exit(1)
    return value


TELEGRAM_BOT_TOKEN = _require("TELEGRAM_BOT_TOKEN")

SUPABASE_URL = _require("SUPABASE_URL").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = _require("SUPABASE_SERVICE_ROLE_KEY")

UPI_VPA = _require("UPI_VPA")
UPI_PAYEE_NAME = _require("UPI_PAYEE_NAME")
UPI_REDIRECT_BASE_URL = _require("UPI_REDIRECT_BASE_URL").rstrip("/")

PORT = int(os.environ.get("PORT", "8080"))
