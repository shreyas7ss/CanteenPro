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


SUPABASE_URL = _require("SUPABASE_URL").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = _require("SUPABASE_SERVICE_ROLE_KEY")

UPI_VPA = _require("UPI_VPA")
UPI_PAYEE_NAME = _require("UPI_PAYEE_NAME")
UPI_REDIRECT_BASE_URL = _require("UPI_REDIRECT_BASE_URL").rstrip("/")

# Configure this in the hosting provider's secret store, never in source control.
GETGABS_API_KEY = os.environ.get("GETGABS_API_KEY")
GETGABS_WEBHOOK_TOKEN = os.environ.get("GETGABS_WEBHOOK_TOKEN")

PORT = int(os.environ.get("PORT", "8080"))
CORS_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",")
    if origin.strip()
]
