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

    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
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

    def record_message(self, author_id: int, guild_id: int | None, channel_id: int) -> None:
        today = datetime.utcnow().strftime("%Y-%m-%d")
        now = time.time()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO messages (author_id, guild_id, channel_id, date, timestamp) VALUES (?, ?, ?, ?, ?)",
                (author_id, guild_id if guild_id else 0, channel_id, today, now),
            )

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
        today = datetime.utcnow().strftime("%Y-%m-%d")
        target_guild = guild_id if guild_id else 0

        with sqlite3.connect(self.db_path) as conn:
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


tracker = MessageTracker()
