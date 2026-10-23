# miata-bot

Watches a [theparking.eu](https://www.theparking.eu/) search and posts new listings
(photo, price, year, mileage, location, source site, link) to a Telegram chat.

- Sponsored results are skipped.
- Listings outside the allowed countries (EU-27 by default) are skipped, since the
  site has no "EU only" filter.
- Every listing seen is stored in SQLite (`data/listings.db`), so nothing is sent twice.

## How it gets past Cloudflare

The whole site sits behind a Cloudflare managed challenge (Turnstile). Plain
`requests` and TLS-impersonating clients (curl_cffi) both get a 403, so the bot drives
a real Chrome through [nodriver](https://github.com/ultrafunkamsterdam/nodriver):

- Chrome runs **headful** on a virtual display (Xvfb), because headless never passes.
  The bot starts Xvfb itself when `DISPLAY` isn't set.
- When the checkbox shows up, the bot finds it with DOM-only CDP calls and clicks it.
  Running JS in the page (`tab.evaluate`) while the challenge is up gets the click
  rejected, so the bot doesn't do that.
- The Chrome profile is kept in `data/chrome-profile`, so the clearance cookie often
  carries over and later runs skip the challenge.

No paid scraping API is needed as long as this keeps working. If Cloudflare tightens
up, swap `browser.Scraper` for an API like ScrapFly, ZenRows, or ScraperAPI.

## Setup

System dependencies (the devcontainer's `setup.sh` installs these):
Google Chrome and `xvfb`.

```bash
uv sync
cp .env.example .env   # fill in TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID
```

To get the chat ID, send your bot a message (or add it to a group) and open
`https://api.telegram.org/bot<TOKEN>/getUpdates`.

## Running

```bash
uv run miata-bot --once --dry-run   # scrape and print, without sending or storing
uv run miata-bot --once             # one check (for cron / systemd timers)
uv run miata-bot                    # loop forever, checking every INTERVAL_MINUTES
```

On the **first run** the bot records the listings already up without sending them,
so the chat isn't flooded. Use `--notify-existing` to send them anyway.

With cron instead of the built-in loop:

```cron
0 * * * * cd /path/to/miata-bot && uv run miata-bot --once >> data/bot.log 2>&1
```

## Configuration (`.env`)

| Variable | Default | |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | – | required unless `--dry-run` |
| `SEARCH_URL` | NA MX-5, LHD, ≤1997, newest first | paste from the browser; `#!` URLs are fine |
| `ALLOWED_COUNTRIES` | `EU` | `EU`, `*`, or ISO codes such as `es,pt,fr` |
| `MAX_PAGES` | `1` | ~25 listings/page; page 1 covers ~2–3 days for this search |
| `INTERVAL_MINUTES` | `60` | loop mode only |
| `DB_PATH` | `data/listings.db` | |
| `CHROME_PROFILE_DIR` | `data/chrome-profile` | |

## Notes

- Listing photos come from `img.leparking.fr`, which always serves AVIF (whatever the
  file extension says). Telegram can't show AVIF, so the bot converts each photo to JPEG
  before uploading. The site keeps only one photo per listing (about 450×340); the
  full gallery is on the source site behind "View listing".
- Pagination is a JS form POST rather than a URL parameter, so for pages after the first
  the bot clicks the page links.

## Layout

```
src/miata_bot/
  __main__.py  CLI, run loop, dedupe + filtering
  browser.py   nodriver + Cloudflare handling + Xvfb
  parser.py    results HTML -> Listing
  db.py        SQLite seen-store
  telegram.py  Bot API client and message formatting
  config.py    env settings, EU country list
tests/         parser tests against a saved results page
```
