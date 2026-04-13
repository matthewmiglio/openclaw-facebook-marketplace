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
    """)
    conn.commit()


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
