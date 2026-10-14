from __future__ import annotations

from pathlib import Path
import sqlite3

from app.products.storage_parser import parse_storage_gb
from app.products.target_filter import rejection_reason


SCHEMA = """
CREATE TABLE IF NOT EXISTS listings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    source_id TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    price INTEGER,
    currency TEXT NOT NULL,
    seller TEXT,
    location TEXT,
    url TEXT NOT NULL,
    image_url TEXT,
    condition TEXT,
    created_at TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT,
    notified_at TEXT,
    notified_price INTEGER,
    storage_gb INTEGER,
    eligible INTEGER NOT NULL DEFAULT 0,
    observed_at TEXT,
    notification_attempts INTEGER NOT NULL DEFAULT 0,
    notification_error TEXT,
    notification_next_attempt_at TEXT,
    UNIQUE(source, source_id)
);
"""


def connect(database_path: Path) -> sqlite3.Connection:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize(connection: sqlite3.Connection) -> None:
    connection.execute("BEGIN")
    with connection:
        connection.execute(SCHEMA)
        info = list(connection.execute("PRAGMA table_info(listings)"))
        columns = {row[1] for row in info}
        if any(row[1] == "last_seen_at" and row[3] for row in info):
            # Legacy schemas required a post time. Unknown times must remain NULL.
            connection.execute("ALTER TABLE listings RENAME TO listings_legacy")
            connection.execute(SCHEMA)
            names = ", ".join(f'"{row[1]}"' for row in info)
            connection.execute(f"INSERT INTO listings ({names}) SELECT {names} FROM listings_legacy")
            connection.execute("DROP TABLE listings_legacy")
        fields = (
            ("location", "TEXT"), ("notified_at", "TEXT"), ("notified_price", "INTEGER"),
            ("storage_gb", "INTEGER"), ("eligible", "INTEGER NOT NULL DEFAULT 0"),
            ("observed_at", "TEXT"), ("notification_attempts", "INTEGER NOT NULL DEFAULT 0"),
            ("notification_error", "TEXT"), ("notification_next_attempt_at", "TEXT"),
        )
        actual_columns = {row[1] for row in connection.execute("PRAGMA table_info(listings)")}
        for name, declaration in fields:
            if name not in actual_columns:
                connection.execute(f"ALTER TABLE listings ADD COLUMN {name} {declaration}")
        if "notified_price" not in columns:
            connection.execute("UPDATE listings SET notified_price=price WHERE notified_at IS NOT NULL")
        if "observed_at" not in columns:
            connection.execute("UPDATE listings SET observed_at=first_seen_at WHERE observed_at IS NULL")
        if "eligible" not in columns or "storage_gb" not in columns:
            for row in connection.execute("SELECT id, title, description, price, location FROM listings"):
                text = f"{row['title']} {row['description'] or ''}"
                connection.execute(
                    "UPDATE listings SET storage_gb=?, eligible=? WHERE id=?",
                    (parse_storage_gb(text), int(rejection_reason(text, row["price"], row["location"]) is None), row["id"]),
                )
        connection.execute("CREATE INDEX IF NOT EXISTS idx_listings_recent ON listings(last_seen_at DESC, id DESC)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_listings_eligible_recent ON listings(eligible, last_seen_at DESC, id DESC, location)")
        connection.execute("CREATE TABLE IF NOT EXISTS notification_state (id INTEGER PRIMARY KEY CHECK(id=1), next_attempt_at TEXT)")
        connection.execute("INSERT OR IGNORE INTO notification_state(id) VALUES (1)")
        connection.execute('''CREATE TABLE IF NOT EXISTS detail_tasks (
            source_id TEXT PRIMARY KEY, payload TEXT NOT NULL, fingerprint TEXT NOT NULL,
            state TEXT NOT NULL, reason TEXT NOT NULL, attempts INTEGER NOT NULL,
            next_attempt_at TEXT NOT NULL, discovered_at TEXT NOT NULL
        )''')
        connection.execute('CREATE INDEX IF NOT EXISTS idx_detail_tasks_due ON detail_tasks(next_attempt_at)')
