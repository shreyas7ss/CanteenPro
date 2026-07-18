import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl


class InvalidInitData(Exception):
    pass


def validate_init_data(init_data: str, bot_token: str, max_age_seconds: int = 3600) -> dict:
    """Validates Telegram Mini App initData per Telegram's documented algorithm:
    https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app

    secret_key = HMAC_SHA256(key="WebAppData", message=bot_token)
    expected_hash = HMAC_SHA256(key=secret_key, message=data_check_string)
    """
    if not init_data:
        raise InvalidInitData("missing initData")

    parsed = dict(parse_qsl(init_data, strict_parsing=True))
    received_hash = parsed.pop("hash", None)
    if not received_hash:
        raise InvalidInitData("initData missing hash")

    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(parsed.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(expected_hash, received_hash):
        raise InvalidInitData("initData signature mismatch")

    auth_date = int(parsed.get("auth_date", "0"))
    if time.time() - auth_date > max_age_seconds:
        raise InvalidInitData("initData expired")

    user = json.loads(parsed["user"]) if "user" in parsed else None
    if not user or "id" not in user:
        raise InvalidInitData("initData missing user")

    return {"user": user, "auth_date": auth_date}
