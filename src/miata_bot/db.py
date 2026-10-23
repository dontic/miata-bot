"""SQLite store of every listing we've seen, so each one is only notified once."""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .parser import Listing

SCHEMA = """
CREATE TABLE IF NOT EXISTS listings (
    id          TEXT PRIMARY KEY,
    first_seen  TEXT NOT NULL,
    country     TEXT,
    notified    INTEGER NOT NULL DEFAULT 0,  -- 1 = sent to Telegram
    skipped     TEXT,                        -- reason it wasn't sent (e.g. country, seed)
    data        TEXT NOT NULL                -- full Listing as JSON
);
"""


class Store:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.executescript(SCHEMA)

    def is_empty(self) -> bool:
        return self.conn.execute("SELECT 1 FROM listings LIMIT 1").fetchone() is None

    def seen(self, listing_id: str) -> bool:
        return self.conn.execute("SELECT 1 FROM listings WHERE id = ?", (listing_id,)).fetchone() is not None

    def add(self, listing: Listing, *, notified: bool, skipped: str | None = None) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO listings (id, first_seen, country, notified, skipped, data) VALUES (?, ?, ?, ?, ?, ?)",
            (
                listing.id,
                datetime.now(timezone.utc).isoformat(timespec="seconds"),
                listing.country_code,
                int(notified),
                skipped,
                json.dumps(listing.to_dict(), ensure_ascii=False),
            ),
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()
