"""
Globe Selfbot — Message Tracker & Database Manager
Tracks message statistics locally in SQLite for rapid queries:
- Total messages sent per guild & channel
- Direct Messages (DMs)
- Global count across all servers
- Daily / today counts
"""

from __future__ import annotations

import sqlite3
import time
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "stats.db"


class MessageTracker:
    def __init__(self, db_path: Path = DB_PATH) -> None:
        self.db_path = db_path
        self._init_db()
        self._conn: sqlite3.Connection | None = None
        self._buffer: list[tuple[int, int, int, str, float]] = []
        self._last_flush: float = time.monotonic()

    def _get_connection(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.execute("PRAGMA journal_mode=WAL;")
            self._conn.execute("PRAGMA synchronous=NORMAL;")
        return self._conn

    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    author_id INTEGER,
                    guild_id INTEGER,
                    channel_id INTEGER,
                    date TEXT,
                    timestamp REAL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_messages_author_guild ON messages(author_id, guild_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_messages_author_date ON messages(author_id, date)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS snipes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel_id INTEGER,
                    author_id INTEGER,
                    author_name TEXT,
                    content TEXT,
                    attachments TEXT,
                    timestamp REAL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_snipes_ts ON snipes(timestamp DESC)"
            )

    def flush(self) -> None:
        """Flush pending buffered message records to SQLite in a single transaction."""
        if not self._buffer:
            return
        to_write = list(self._buffer)
        self._buffer.clear()
        self._last_flush = time.monotonic()
        try:
            conn = self._get_connection()
            conn.executemany(
                "INSERT INTO messages (author_id, guild_id, channel_id, date, timestamp) VALUES (?, ?, ?, ?, ?)",
                to_write,
            )
            conn.commit()
        except Exception:
            pass

    def record_message(self, author_id: int, guild_id: int | None, channel_id: int) -> None:
        """Buffer message statistics and flush in micro-batches to prevent event-loop stalls."""
        today = datetime.utcnow().strftime("%Y-%m-%d")
        now = time.time()
        self._buffer.append((author_id, guild_id if guild_id else 0, channel_id, today, now))

        # Flush if buffer reaches 8 entries or >3 seconds elapsed since last flush
        if len(self._buffer) >= 8 or (time.monotonic() - self._last_flush) > 3.0:
            self.flush()

    def get_stats(self, author_id: int, guild_id: int | None = None) -> dict[str, int]:
        """
        Return stats:
        - guild_all: all-time messages in this guild
        - guild_today: today's messages in this guild
        - global_all: all-time across all servers and DMs
        - global_today: today across all servers and DMs
        - dms_all: all-time messages sent in DMs
        - dms_today: today's messages in DMs
        """
        self.flush()
        today = datetime.utcnow().strftime("%Y-%m-%d")
        target_guild = guild_id if guild_id else 0

        conn = self._get_connection()
        cur = conn.cursor()

        # Guild counts
        cur.execute(
            "SELECT COUNT(*) FROM messages WHERE author_id = ? AND guild_id = ?",
            (author_id, target_guild),
        )
        guild_all = cur.fetchone()[0]

        cur.execute(
            "SELECT COUNT(*) FROM messages WHERE author_id = ? AND guild_id = ? AND date = ?",
            (author_id, target_guild, today),
        )
        guild_today = cur.fetchone()[0]

        # Global counts
        cur.execute(
            "SELECT COUNT(*) FROM messages WHERE author_id = ?",
            (author_id,),
        )
        global_all = cur.fetchone()[0]

        cur.execute(
            "SELECT COUNT(*) FROM messages WHERE author_id = ? AND date = ?",
            (author_id, today),
        )
        global_today = cur.fetchone()[0]

        # DM counts (guild_id == 0)
        cur.execute(
            "SELECT COUNT(*) FROM messages WHERE author_id = ? AND guild_id = 0",
            (author_id,),
        )
        dms_all = cur.fetchone()[0]

        cur.execute(
            "SELECT COUNT(*) FROM messages WHERE author_id = ? AND guild_id = 0 AND date = ?",
            (author_id, today),
        )
        dms_today = cur.fetchone()[0]

        return {
            "guild_all": guild_all,
            "guild_today": guild_today,
            "global_all": global_all,
            "global_today": global_today,
            "dms_all": dms_all,
            "dms_today": dms_today,
        }

    def record_snipe(
        self,
        channel_id: int,
        author_id: int,
        author_name: str,
        content: str,
        attachments: list[str] | None = None,
    ) -> None:
        """Persist deleted message into SQLite and cap table at 500 newest rows."""
        try:
            conn = self._get_connection()
            att_str = "\n".join(attachments) if attachments else ""
            conn.execute(
                "INSERT INTO snipes (channel_id, author_id, author_name, content, attachments, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                (channel_id, author_id, author_name, content[:1500], att_str, time.time()),
            )
            conn.execute(
                "DELETE FROM snipes WHERE id NOT IN (SELECT id FROM snipes ORDER BY id DESC LIMIT 500)"
            )
            conn.commit()
        except Exception:
            pass

    def search_snipes(self, query: str, limit: int = 8) -> list[dict]:
        """Search persisted deleted messages by keyword or author name."""
        q = f"%{query.strip()}%"
        try:
            conn = self._get_connection()
            cur = conn.cursor()
            cur.execute(
                """
                SELECT channel_id, author_id, author_name, content, attachments, timestamp
                FROM snipes
                WHERE content LIKE ? OR author_name LIKE ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (q, q, limit),
            )
            return [
                {
                    "channel_id": r[0],
                    "author_id": r[1],
                    "author_name": r[2],
                    "content": r[3],
                    "attachments": [u for u in r[4].split("\n") if u] if r[4] else [],
                    "timestamp": r[5],
                }
                for r in cur.fetchall()
            ]
        except Exception:
            return []


tracker = MessageTracker()
