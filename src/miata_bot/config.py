"""Settings loaded from environment variables (and a local .env file)."""

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

from dotenv import load_dotenv

DEFAULT_SEARCH_URL = (
    "https://www.theparking.eu/#!/used-cars/mx5.html"
    "%3Fid_volant%3D1%26slider_millesime%3D1910%7C1997%26tri%3Ddate"
)

# EU-27 member states, as the lowercase ISO-3166 codes theparking uses for flags.
EU_COUNTRIES = frozenset(
    "at be bg hr cy cz dk ee fi fr de gr hu ie it lv lt lu mt nl pl pt ro sk si es se".split()
)


def normalize_search_url(url: str) -> str:
    """Turn the SPA hash URL (`/#!/used-cars/x.html%3F...`) into the server-rendered one.

    The `#!` form only works with the site's JS router; the plain path returns the
    same results as server-side HTML, which is what we parse.
    """
    if "#!" in url:
        base, frag = url.split("#!", 1)
        url = base.rstrip("/") + unquote(frag)
    return url


@dataclass(frozen=True)
class Settings:
    telegram_token: str
    telegram_chat_id: str
    search_url: str
    allowed_countries: frozenset[str]
    max_pages: int
    interval_minutes: int
    db_path: Path
    chrome_profile_dir: Path

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        countries = os.getenv("ALLOWED_COUNTRIES", "EU").strip()
        if countries.upper() == "EU":
            allowed = EU_COUNTRIES
        elif countries in ("", "*"):
            allowed = frozenset()  # empty = no filtering
        else:
            allowed = frozenset(c.strip().lower() for c in countries.split(",") if c.strip())
        return cls(
            telegram_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
            telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", ""),
            search_url=normalize_search_url(os.getenv("SEARCH_URL", DEFAULT_SEARCH_URL)),
            allowed_countries=allowed,
            max_pages=int(os.getenv("MAX_PAGES", "1")),
            interval_minutes=int(os.getenv("INTERVAL_MINUTES", "60")),
            db_path=Path(os.getenv("DB_PATH", "data/listings.db")),
            chrome_profile_dir=Path(os.getenv("CHROME_PROFILE_DIR", "data/chrome-profile")),
        )
