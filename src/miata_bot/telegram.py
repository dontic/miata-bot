"""Send listings to a Telegram chat via the Bot API."""

import asyncio
import io
import logging
from html import escape

import httpx
from PIL import Image

from .parser import Listing

log = logging.getLogger(__name__)

API = "https://api.telegram.org/bot{token}/{method}"


def format_caption(listing: Listing) -> str:
    """HTML caption (Telegram limits photo captions to 1024 chars)."""
    flag = _flag_emoji(listing.country_code)
    lines = [
        f"<b>{escape(listing.title)}</b>",
        f"💶 <b>{escape(listing.price or 'POA')}</b>",
        f"📅 {escape(listing.year or '?')}   🛣 {escape(listing.mileage or '? km')}",
        f"⚙️ {escape(' · '.join(filter(None, [listing.fuel, listing.gearbox])) or '?')}",
        f"{flag} {escape(listing.country)} {escape(listing.postcode)}".rstrip(),
        f"🏷 {escape(listing.seller or '?')} on {escape(listing.source or '?')} · listed {escape(listing.published)}",
    ]
    if listing.description:
        lines.append(f"<i>{escape(listing.description[:300])}</i>")
    lines.append(f'<a href="{escape(listing.url, quote=True)}">View listing</a>')
    return "\n".join(lines)[:1024]


def _flag_emoji(code: str) -> str:
    if len(code) != 2 or not code.isalpha():
        return "📍"
    return "".join(chr(0x1F1E6 + ord(c) - ord("a")) for c in code.lower())


class TelegramClient:
    def __init__(self, token: str, chat_id: str) -> None:
        if not token or not chat_id:
            raise ValueError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set")
        self.token = token
        self.chat_id = chat_id
        self.http = httpx.AsyncClient(timeout=30)

    async def close(self) -> None:
        await self.http.aclose()

    async def send_listing(self, listing: Listing) -> None:
        caption = format_caption(listing)
        photo = await self._fetch_photo(listing.image_url) if listing.image_url else None
        if photo:
            await self._call(
                "sendPhoto",
                data={"chat_id": self.chat_id, "caption": caption, "parse_mode": "HTML"},
                files={"photo": ("photo.jpg", photo, "image/jpeg")},
            )
        else:
            await self._call(
                "sendMessage",
                data={"chat_id": self.chat_id, "text": caption, "parse_mode": "HTML"},
            )

    async def send_text(self, text: str) -> None:
        await self._call("sendMessage", data={"chat_id": self.chat_id, "text": text})

    async def _fetch_photo(self, url: str) -> bytes | None:
        """Download the thumbnail and re-encode as JPEG.

        img.leparking.fr always serves AVIF (whatever the extension or Accept header),
        which Telegram can't display, so we can't just pass the URL to Telegram.
        """
        try:
            resp = await self.http.get(url)
            resp.raise_for_status()
            img = Image.open(io.BytesIO(resp.content)).convert("RGB")
            out = io.BytesIO()
            img.save(out, "JPEG", quality=90)
            return out.getvalue()
        except Exception as e:  # a missing photo shouldn't block the notification
            log.warning("Could not fetch photo %s: %s", url, e)
            return None

    async def _call(self, method: str, **kwargs) -> dict:
        url = API.format(token=self.token, method=method)
        for _ in range(5):
            resp = await self.http.post(url, **kwargs)
            body = resp.json()
            if body.get("ok"):
                return body["result"]
            retry_after = body.get("parameters", {}).get("retry_after")
            if resp.status_code == 429 and retry_after:
                log.info("Telegram rate limit, sleeping %ss", retry_after)
                await asyncio.sleep(retry_after + 1)
                continue
            raise RuntimeError(f"Telegram {method} failed: {body.get('description')}")
        raise RuntimeError(f"Telegram {method} kept rate-limiting")
