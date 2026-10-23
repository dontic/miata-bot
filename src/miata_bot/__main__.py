"""Entry point: `uv run miata-bot [--once] [--dry-run] [--notify-existing]`."""

import argparse
import asyncio
import logging

from .browser import Scraper, VirtualDisplay
from .config import Settings
from .db import Store
from .parser import Listing, parse_listings
from .telegram import TelegramClient

log = logging.getLogger("miata_bot")


async def scrape(settings: Settings) -> list[Listing]:
    """Return listings from the first `max_pages` result pages, newest first."""
    listings: list[Listing] = []
    async with Scraper(settings.chrome_profile_dir) as scraper:
        html = await scraper.open(settings.search_url)
        for page in range(1, settings.max_pages + 1):
            if page > 1:
                html = await scraper.goto_page(page)
                if html is None:
                    break
            found = parse_listings(html)
            log.info("Page %d: %d listings", page, len(found))
            if not found:
                break
            listings.extend(found)
    return listings


async def run_once(settings: Settings, *, dry_run: bool, notify_existing: bool) -> None:
    store = Store(settings.db_path)
    # On the very first run, record what's already listed instead of flooding the chat.
    seeding = store.is_empty() and not notify_existing
    telegram = None if dry_run else TelegramClient(settings.telegram_token, settings.telegram_chat_id)
    try:
        listings = await scrape(settings)
        unique = {item.id: item for item in listings}.values()
        new = [item for item in unique if not store.seen(item.id)]
        log.info("%d listings scraped, %d new", len(listings), len(new))

        # Oldest first, so the chat reads chronologically.
        for item in reversed(new):
            allowed = not settings.allowed_countries or item.country_code in settings.allowed_countries
            if dry_run:
                status = "SEND" if allowed else f"skip ({item.country_code})"
                print(f"[{status}] {item.title} | {item.price} | {item.year} | {item.country} | {item.url}")
                continue
            if not allowed:
                store.add(item, notified=False, skipped=f"country:{item.country_code}")
                continue
            if seeding:
                store.add(item, notified=False, skipped="seed")
                continue
            await telegram.send_listing(item)
            store.add(item, notified=True)
            await asyncio.sleep(1)  # stay well under Telegram's per-chat limits

        if seeding and not dry_run:
            log.info("First run: stored %d existing listings without notifying", len(new))
    finally:
        store.close()
        if telegram:
            await telegram.close()


async def run(args: argparse.Namespace) -> None:
    settings = Settings.from_env()
    with VirtualDisplay():
        while True:
            try:
                await run_once(settings, dry_run=args.dry_run, notify_existing=args.notify_existing)
            except Exception:
                log.exception("Run failed")
                if args.once:
                    raise
            if args.once:
                return
            log.info("Sleeping %d minutes", settings.interval_minutes)
            await asyncio.sleep(settings.interval_minutes * 60)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="run a single check and exit (for cron)")
    parser.add_argument("--dry-run", action="store_true", help="print new listings instead of sending/storing them")
    parser.add_argument(
        "--notify-existing", action="store_true", help="on first run, notify current listings instead of seeding"
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # nodriver is very chatty at DEBUG
    logging.getLogger("nodriver").setLevel(logging.WARNING)
    logging.getLogger("uc").setLevel(logging.WARNING)
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
