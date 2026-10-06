from __future__ import annotations

from pathlib import Path
import sqlite3


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
    columns = {row[1] for row in connection.execute("PRAGMA table_info(listings)")}
    connection.executescript(SCHEMA)
    if columns and "location" not in columns:
        connection.execute("ALTER TABLE listings ADD COLUMN location TEXT")
    if columns and "notified_at" not in columns:
        connection.execute("ALTER TABLE listings ADD COLUMN notified_at TEXT")
    connection.commit()
