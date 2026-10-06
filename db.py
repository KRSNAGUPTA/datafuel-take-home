"""SQLite schema and helpers. No business logic lives here."""
import sqlite3
from contextlib import contextmanager

from config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS stores (
    store_id TEXT PRIMARY KEY,
    city TEXT NOT NULL,
    name TEXT,
    is_active INTEGER NOT NULL,
    is_serviceable INTEGER,
    first_seen_as_of TEXT,
    last_seen_as_of TEXT
);

CREATE TABLE IF NOT EXISTS sweeps (
    as_of TEXT PRIMARY KEY,
    started_at TEXT,
    finished_at TEXT,
    tracked_stores INTEGER,
    complete_stores INTEGER
);

CREATE TABLE IF NOT EXISTS sweep_store_status (
    as_of TEXT NOT NULL,
    store_id TEXT NOT NULL,
    complete INTEGER NOT NULL,
    reason TEXT,
    items_seen INTEGER,
    PRIMARY KEY (as_of, store_id)
);

CREATE TABLE IF NOT EXISTS inventory (
    as_of TEXT NOT NULL,
    store_id TEXT NOT NULL,
    sku_id TEXT NOT NULL,
    name TEXT,
    in_stock INTEGER NOT NULL,
    qty INTEGER,
    price TEXT,
    observed_at TEXT NOT NULL,
    PRIMARY KEY (as_of, store_id, sku_id)
);

CREATE TABLE IF NOT EXISTS sku_names (
    sku_id TEXT PRIMARY KEY,
    name TEXT
);

CREATE INDEX IF NOT EXISTS idx_inv_store_asof ON inventory (store_id, as_of);
CREATE INDEX IF NOT EXISTS idx_inv_sku        ON inventory (sku_id);
"""


def connect(path: str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


@contextmanager
def db(path: str = DB_PATH):
    conn = connect(path)
    try:
        init_db(conn)
        yield conn
    finally:
        conn.close()