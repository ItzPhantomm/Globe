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
from datetime import datetime, timedelta, timezone
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
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS kv_state (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS bookmarks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tag TEXT,
                    author_name TEXT,
                    content TEXT,
                    jump_url TEXT,
                    attachments TEXT,
                    timestamp REAL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS invite_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    guild_id INTEGER,
                    code TEXT,
                    kind TEXT,
                    date TEXT,
                    timestamp REAL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_invite_logs_user_date ON invite_logs(user_id, date)"
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

    def get_hourly_activity(self, author_id: int, hours: int = 24) -> list[dict[str, object]]:
        """Return hourly message counts for the last N hours from SQLite."""
        self.flush()
        now = time.time()
        cutoff = now - hours * 3600
        buckets = [0] * hours
        try:
            conn = self._get_connection()
            cur = conn.cursor()
            cur.execute(
                "SELECT timestamp FROM messages WHERE author_id = ? AND timestamp >= ?",
                (author_id, cutoff),
            )
            for (ts,) in cur.fetchall():
                idx = int((ts - cutoff) // 3600)
                if 0 <= idx < hours:
                    buckets[idx] += 1
        except Exception:
            pass
        out: list[dict[str, object]] = []
        for i in range(hours):
            slot_ts = cutoff + (i + 1) * 3600
            lbl = datetime.fromtimestamp(slot_ts).strftime("%H:00")
            out.append({"label": lbl, "count": buckets[i]})
        return out

    def record_invite(self, user_id: int, guild_id: int | None, code: str, kind: str = "shared") -> None:
        """Persist a shared or created Discord invite event for analytics."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        now = time.time()
        try:
            conn = self._get_connection()
            conn.execute(
                "INSERT INTO invite_logs (user_id, guild_id, code, kind, date, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, guild_id if guild_id else 0, code[:32], kind[:16], today, now),
            )
            conn.commit()
        except Exception:
            pass

    def get_dm_last_activity(self) -> dict[int, float]:
        """Return {channel_id: latest_timestamp} for DM activity sorting."""
        self.flush()
        out: dict[int, float] = {}
        try:
            conn = self._get_connection()
            cur = conn.cursor()
            cur.execute("SELECT channel_id, MAX(timestamp) FROM messages WHERE guild_id = 0 GROUP BY channel_id")
            for cid, ts in cur.fetchall():
                if cid:
                    out[int(cid)] = float(ts or 0.0)
        except Exception:
            pass
        return out

    @staticmethod
    def _delta_pct(today_val: int, yesterday_val: int) -> float:
        if yesterday_val <= 0:
            return 100.0 if today_val > 0 else 0.0
        return round(((today_val - yesterday_val) / yesterday_val) * 100.0, 1)

    def get_detailed_analytics(self, author_id: int, bot: object | None = None, days: int = 14) -> dict:
        """Compute daily/yesterday/global comparisons, multi-day series, top servers, and top DM contacts."""
        self.flush()
        now_dt = datetime.now(timezone.utc)
        today_str = now_dt.strftime("%Y-%m-%d")
        yest_dt = now_dt - timedelta(days=1)
        yest_str = yest_dt.strftime("%Y-%m-%d")
        today_start = now_dt.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        yest_start = (now_dt.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)).timestamp()

        conn = self._get_connection()
        cur = conn.cursor()

        # Global & today/yesterday messages
        cur.execute("SELECT COUNT(*) FROM messages WHERE author_id = ?", (author_id,))
        msgs_global = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM messages WHERE author_id = ? AND date = ?", (author_id, today_str))
        msgs_today = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM messages WHERE author_id = ? AND date = ?", (author_id, yest_str))
        msgs_yesterday = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM messages WHERE author_id = ? AND guild_id = 0", (author_id,))
        dms_global = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM messages WHERE author_id = ? AND guild_id = 0 AND date = ?", (author_id, today_str))
        dms_today = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM messages WHERE author_id = ? AND guild_id = 0 AND date = ?", (author_id, yest_str))
        dms_yesterday = cur.fetchone()[0]

        # Invites counts
        cur.execute("SELECT COUNT(*) FROM invite_logs WHERE user_id = ?", (author_id,))
        inv_global = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM invite_logs WHERE user_id = ? AND date = ?", (author_id, today_str))
        inv_today = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM invite_logs WHERE user_id = ? AND date = ?", (author_id, yest_str))
        inv_yesterday = cur.fetchone()[0]

        # 24h hourly comparison (today vs yesterday by hour-of-day UTC)
        t_hours = [0] * 24
        y_hours = [0] * 24
        it_hours = [0] * 24
        iy_hours = [0] * 24
        cur.execute("SELECT timestamp FROM messages WHERE author_id = ? AND timestamp >= ?", (author_id, yest_start))
        for (ts,) in cur.fetchall():
            if ts >= today_start:
                idx = min(23, max(0, int((ts - today_start) // 3600)))
                t_hours[idx] += 1
            else:
                idx = min(23, max(0, int((ts - yest_start) // 3600)))
                y_hours[idx] += 1

        cur.execute("SELECT timestamp FROM invite_logs WHERE user_id = ? AND timestamp >= ?", (author_id, yest_start))
        for (ts,) in cur.fetchall():
            if ts >= today_start:
                idx = min(23, max(0, int((ts - today_start) // 3600)))
                it_hours[idx] += 1
            else:
                idx = min(23, max(0, int((ts - yest_start) // 3600)))
                iy_hours[idx] += 1

        hourly_comparison = [
            {
                "label": f"{h:02d}:00",
                "today": t_hours[h],
                "yesterday": y_hours[h],
                "invites_today": it_hours[h],
                "invites_yesterday": iy_hours[h],
            }
            for h in range(24)
        ]

        # 14-day daily series
        day_keys = [(now_dt - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days - 1, -1, -1)]
        msg_by_day: dict[str, int] = {d: 0 for d in day_keys}
        dm_by_day: dict[str, int] = {d: 0 for d in day_keys}
        inv_by_day: dict[str, int] = {d: 0 for d in day_keys}

        cutoff_date = day_keys[0]
        cur.execute(
            "SELECT date, guild_id, COUNT(*) FROM messages WHERE author_id = ? AND date >= ? GROUP BY date, guild_id",
            (author_id, cutoff_date),
        )
        for d_str, gid, cnt in cur.fetchall():
            if d_str in msg_by_day:
                msg_by_day[d_str] += cnt
                if gid == 0:
                    dm_by_day[d_str] += cnt

        cur.execute(
            "SELECT date, COUNT(*) FROM invite_logs WHERE user_id = ? AND date >= ? GROUP BY date",
            (author_id, cutoff_date),
        )
        for d_str, cnt in cur.fetchall():
            if d_str in inv_by_day:
                inv_by_day[d_str] += cnt

        daily_series = [
            {
                "date": d,
                "label": d[5:],
                "messages": msg_by_day[d],
                "dms": dm_by_day[d],
                "invites": inv_by_day[d],
            }
            for d in day_keys
        ]

        # Most active servers (top 8)
        cur.execute(
            """
            SELECT guild_id,
                   COUNT(*) AS total,
                   SUM(CASE WHEN date = ? THEN 1 ELSE 0 END) AS today_cnt
            FROM messages
            WHERE author_id = ? AND guild_id != 0
            GROUP BY guild_id
            ORDER BY total DESC
            LIMIT 8
            """,
            (today_str, author_id),
        )
        server_rows = cur.fetchall()
        server_msg_sum = sum(r[1] for r in server_rows) or 1
        top_servers = []
        for gid, total, today_cnt in server_rows:
            g = bot.get_guild(gid) if bot and hasattr(bot, "get_guild") else None
            top_servers.append({
                "guild_id": str(gid),
                "name": g.name if g else f"Server {gid}",
                "icon": str(g.icon.url) if g and getattr(g, "icon", None) else "",
                "count": total,
                "today_count": int(today_cnt or 0),
                "share_pct": round((total / server_msg_sum) * 100.0, 1),
            })

        # People talked with most (DM channels sorted by combined sent + received messages)
        cur.execute(
            """
            SELECT channel_id,
                   SUM(CASE WHEN author_id = ? THEN 1 ELSE 0 END) AS sent,
                   SUM(CASE WHEN author_id != ? THEN 1 ELSE 0 END) AS received,
                   COUNT(*) AS total,
                   SUM(CASE WHEN date = ? THEN 1 ELSE 0 END) AS today_cnt,
                   MAX(timestamp) AS last_ts
            FROM messages
            WHERE guild_id = 0
            GROUP BY channel_id
            ORDER BY total DESC
            LIMIT 10
            """,
            (author_id, author_id, today_str),
        )
        top_contacts = []
        for cid, sent, received, total, today_cnt, last_ts in cur.fetchall():
            ch = bot.get_channel(cid) if bot and hasattr(bot, "get_channel") else None
            rec = getattr(ch, "recipient", None) if ch else None
            cname = (
                getattr(rec, "global_name", None)
                or getattr(rec, "name", None)
                or (str(rec) if rec else None)
                or getattr(ch, "name", None)
                or f"DM {cid}"
            )
            uname = str(rec) if rec else f"channel:{cid}"
            av = str(rec.display_avatar.url) if rec and getattr(rec, "display_avatar", None) else ""
            top_contacts.append({
                "channel_id": str(cid),
                "user_id": str(rec.id) if rec else "",
                "name": cname,
                "username": uname,
                "avatar": av,
                "sent": int(sent or 0),
                "received": int(received or 0),
                "total": int(total or 0),
                "today_count": int(today_cnt or 0),
                "last_ts": float(last_ts or 0.0),
            })

        # Recent invite events
        cur.execute(
            "SELECT code, guild_id, kind, timestamp FROM invite_logs WHERE user_id = ? ORDER BY id DESC LIMIT 12",
            (author_id,),
        )
        recent_invites = []
        for code, gid, kind, ts in cur.fetchall():
            g = bot.get_guild(gid) if gid and bot and hasattr(bot, "get_guild") else None
            recent_invites.append({
                "code": code,
                "guild_id": str(gid),
                "guild_name": g.name if g else ("Direct Message" if not gid else f"Guild {gid}"),
                "kind": kind,
                "timestamp": ts,
            })

        return {
            "comparison": {
                "messages_today": msgs_today,
                "messages_yesterday": msgs_yesterday,
                "messages_delta_pct": self._delta_pct(msgs_today, msgs_yesterday),
                "messages_global": msgs_global,
                "dms_today": dms_today,
                "dms_yesterday": dms_yesterday,
                "dms_delta_pct": self._delta_pct(dms_today, dms_yesterday),
                "dms_global": dms_global,
                "invites_today": inv_today,
                "invites_yesterday": inv_yesterday,
                "invites_delta_pct": self._delta_pct(inv_today, inv_yesterday),
                "invites_global": inv_global,
            },
            "hourly_comparison": hourly_comparison,
            "daily_series": daily_series,
            "top_servers": top_servers,
            "top_contacts": top_contacts,
            "recent_invites": recent_invites,
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

    def set_state(self, key: str, value: str) -> None:
        """Persist a JSON/string runtime setting into SQLite."""
        try:
            conn = self._get_connection()
            conn.execute(
                "INSERT INTO kv_state (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )
            conn.commit()
        except Exception:
            pass

    def get_state(self, key: str, default: str | None = None) -> str | None:
        """Retrieve a persisted runtime setting from SQLite."""
        try:
            conn = self._get_connection()
            cur = conn.cursor()
            cur.execute("SELECT value FROM kv_state WHERE key = ?", (key,))
            row = cur.fetchone()
            return row[0] if row else default
        except Exception:
            return default

    def add_bookmark(
        self,
        tag: str,
        author_name: str,
        content: str,
        jump_url: str,
        attachments: list[str] | None = None,
    ) -> int:
        """Save a message bookmark and return its row ID."""
        conn = self._get_connection()
        att_str = "\n".join(attachments) if attachments else ""
        cur = conn.execute(
            "INSERT INTO bookmarks (tag, author_name, content, jump_url, attachments, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
            (tag, author_name, content[:1500], jump_url, att_str, time.time()),
        )
        conn.commit()
        return int(cur.lastrowid or 0)

    def list_bookmarks(self, tag: str = "", limit: int = 8) -> list[dict]:
        """List saved bookmarks optionally filtered by tag or content substring."""
        try:
            conn = self._get_connection()
            cur = conn.cursor()
            if tag:
                q = f"%{tag}%"
                cur.execute(
                    "SELECT id, tag, author_name, content, jump_url, timestamp FROM bookmarks WHERE tag LIKE ? OR content LIKE ? ORDER BY id DESC LIMIT ?",
                    (q, q, limit),
                )
            else:
                cur.execute(
                    "SELECT id, tag, author_name, content, jump_url, timestamp FROM bookmarks ORDER BY id DESC LIMIT ?",
                    (limit,),
                )
            return [
                {"id": r[0], "tag": r[1], "author_name": r[2], "content": r[3], "jump_url": r[4], "timestamp": r[5]}
                for r in cur.fetchall()
            ]
        except Exception:
            return []

    def delete_bookmark(self, bookmark_id: int) -> bool:
        """Delete a bookmark by ID. Returns True if a row was removed."""
        try:
            conn = self._get_connection()
            cur = conn.execute("DELETE FROM bookmarks WHERE id = ?", (bookmark_id,))
            conn.commit()
            return cur.rowcount > 0
        except Exception:
            return False


tracker = MessageTracker()
