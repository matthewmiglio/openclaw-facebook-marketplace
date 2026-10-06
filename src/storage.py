"""SQLite persistence layer for listings, messages, and agent sessions.

All data is stored in ``data/listings.db`` relative to the project root.
Tables are created automatically on first access via :func:`get_db`.
"""

import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "listings.db")


def get_db():
    """Open (or create) the SQLite database and return a connection with WAL mode enabled."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    _ensure_tables(conn)
    return conn


def _ensure_tables(conn):
    """Create the listings, messages, and sessions tables if they don't already exist."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS listings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            listing_url TEXT UNIQUE,
            title TEXT,
            price REAL,
            seller TEXT,
            location TEXT,
            condition TEXT,
            description TEXT,
            timestamp_found TEXT DEFAULT (datetime('now')),
            score REAL,
            score_reasoning TEXT,
            status TEXT DEFAULT 'found'
        );

        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            listing_id INTEGER REFERENCES listings(id),
            message_text TEXT,
            sent_at TEXT DEFAULT (datetime('now')),
            reply_text TEXT,
            reply_at TEXT
        );

        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prompt TEXT,
            parsed_intent TEXT,
            started_at TEXT DEFAULT (datetime('now')),
            summary TEXT
        );

        -- Marketplace chats copied from Messenger by `cli.py sync-messages`
        CREATE TABLE IF NOT EXISTS conversations (
            thread_id TEXT PRIMARY KEY,
            title TEXT,
            listing_url TEXT,
            last_synced TEXT
        );

        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            thread_id TEXT REFERENCES conversations(thread_id),
            sent_time TEXT,  -- as Messenger shows it ("4:01 PM", "Mon 4:01 PM", "Oct 3, 2026, 4:01 PM")
            sender TEXT,
            text TEXT,
            first_seen TEXT DEFAULT (datetime('now')),
            UNIQUE(thread_id, sent_time, sender, text)
        );
    """)
    conn.commit()


def save_conversation(conn, thread_id: str, title: str, listing_url: str, messages: list[dict]) -> int:
    """Upsert a chat and add any messages not stored yet. Returns how many messages were new."""
    conn.execute("""
        INSERT INTO conversations (thread_id, title, listing_url, last_synced) VALUES (?, ?, ?, datetime('now'))
        ON CONFLICT(thread_id) DO UPDATE SET title=excluded.title,
            listing_url=COALESCE(excluded.listing_url, listing_url), last_synced=excluded.last_synced
    """, (thread_id, title, listing_url))
    before = conn.total_changes
    conn.executemany("INSERT OR IGNORE INTO chat_messages (thread_id, sent_time, sender, text) VALUES (?, ?, ?, ?)",
                     [(thread_id, m["time"], m["sender"], m["text"]) for m in messages])
    new = conn.total_changes - before
    conn.commit()
    return new


def find_listing(conn, name: str):
    """Find listings or chats whose title contains `name` (case-insensitive). Returns [{title, url, source}]."""
    like = f"%{name}%"
    rows = conn.execute("""
        SELECT title, listing_url AS url, 'chat' AS source FROM conversations WHERE title LIKE ? AND listing_url IS NOT NULL
        UNION
        SELECT title, listing_url, 'search' FROM listings WHERE title LIKE ?
    """, (like, like)).fetchall()
    return [dict(r) for r in rows]


def save_listing(conn, listing: dict) -> int:
    """Insert or update a listing row. Returns the row ID."""
    cur = conn.execute("""
        INSERT INTO listings (listing_url, title, price, seller, location, condition, description, score, score_reasoning, status)
        VALUES (:listing_url, :title, :price, :seller, :location, :condition, :description, :score, :score_reasoning, :status)
        ON CONFLICT(listing_url) DO UPDATE SET
            price=excluded.price,
            score=excluded.score,
            score_reasoning=excluded.score_reasoning,
            status=excluded.status
    """, listing)
    conn.commit()
    return cur.lastrowid


def save_message(conn, listing_id: int, message_text: str):
    """Record a message that was sent to a listing's seller."""
    conn.execute("""
        INSERT INTO messages (listing_id, message_text)
        VALUES (?, ?)
    """, (listing_id, message_text))
    conn.commit()


def save_session(conn, prompt: str, parsed_intent: str, summary: str):
    """Log an agent run (original prompt, parsed intent JSON, and outcome summary)."""
    conn.execute("""
        INSERT INTO sessions (prompt, parsed_intent, summary)
        VALUES (?, ?, ?)
    """, (prompt, parsed_intent, summary))
    conn.commit()


def get_listings_by_status(conn, status: str):
    """Return all listing rows matching the given status (e.g. 'found', 'messaged', 'skipped')."""
    return conn.execute("SELECT * FROM listings WHERE status = ?", (status,)).fetchall()
