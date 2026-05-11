"""Telegram Bot API: sendPhoto with multipart upload.

Single function, single POST. We deliberately don't use python-telegram-bot
(heavyweight async runtime). httpx is enough.
"""
import httpx

API_URL = "https://api.telegram.org/bot{token}/sendPhoto"


def send_photo(token: str, chat_id: str, image: bytes, caption: str) -> None:
    """POST sendPhoto. Raises on non-2xx (caller decides how to handle).

    `chat_id` may be a numeric string like '-1001234567890' for private channels
    or a username like '@my_channel' for public ones.
    """
    response = httpx.post(
        API_URL.format(token=token),
        data={
            "chat_id": chat_id,
            "caption": caption,
            "parse_mode": "HTML",
        },
        files={"photo": ("forecast.jpg", image, "image/jpeg")},
        timeout=30.0,
    )
    if response.is_error:
        # Telegram's 4xx bodies carry a JSON "description" field that explains
        # why (e.g. "caption is too long", "can't parse entities at offset N").
        # raise_for_status() hides this; surface it so cron logs are diagnosable.
        raise RuntimeError(
            f"Telegram sendPhoto failed: {response.status_code} {response.text}"
        )
