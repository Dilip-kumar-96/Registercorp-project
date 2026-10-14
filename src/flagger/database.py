"""
database.py — SQLite session state machine.

The database is wiped completely on every bot startup (fresh session).
It tracks the state of each FedEx email encountered this session.

Status flow:
  PENDING → CONFIRMED → FLAGGED  (happy path)
  PENDING → FAILED               (portal says filing failed — ignored rest of session)
  PENDING → GONE                 (email deleted before we could flag it)
  CONFIRMED → ERROR              (flagging failed repeatedly)
"""
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from . import config

_DB_PATH = config.get_app_dir() / "session.db"
_lock = threading.Lock()


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def initialize():
    """Wipe existing session DB and create fresh tables. Called on every bot startup."""
    with _lock:
        db = _conn()
        db.executescript("""
            DROP TABLE IF EXISTS emails;
            DROP TABLE IF EXISTS activity_log;
            DROP TABLE IF EXISTS session_meta;

            CREATE TABLE emails (
                tracking_number  TEXT PRIMARY KEY,
                item_id          TEXT NOT NULL,
                change_key       TEXT NOT NULL,
                bot_status       TEXT NOT NULL DEFAULT 'PENDING',
                portal_status    TEXT,
                first_seen_at    TEXT NOT NULL,
                last_checked_at  TEXT,
                flagged_at       TEXT,
                error_message    TEXT
            );

            CREATE TABLE activity_log (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                ts           TEXT NOT NULL,
                level        TEXT NOT NULL,
                event        TEXT NOT NULL,
                tracking     TEXT,
                detail       TEXT
            );

            CREATE TABLE session_meta (
                key   TEXT PRIMARY KEY,
                value TEXT
            );
        """)
        db.commit()
        db.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Email CRUD ────────────────────────────────────────────────────────────────

def add_email(tracking_number: str, item_id: str, change_key: str):
    """Add a newly discovered email as PENDING. Silently ignored if already exists."""
    with _lock:
        db = _conn()
        db.execute(
            """INSERT OR IGNORE INTO emails
               (tracking_number, item_id, change_key, bot_status, first_seen_at)
               VALUES (?, ?, ?, 'PENDING', ?)""",
            (tracking_number, item_id, change_key, _now())
        )
        db.commit()
        db.close()


def get_status(tracking_number: str) -> str | None:
    """Return the current bot_status for a tracking number, or None if not in DB."""
    with _lock:
        db = _conn()
        row = db.execute(
            "SELECT bot_status FROM emails WHERE tracking_number = ?",
            (tracking_number,)
        ).fetchone()
        db.close()
        return row["bot_status"] if row else None


def update_status(tracking_number: str, new_status: str, **kwargs):
    """Update bot_status and any additional fields for an email."""
    with _lock:
        db = _conn()
        fields = {"bot_status": new_status, "last_checked_at": _now()}
        if new_status == "FLAGGED":
            fields["flagged_at"] = _now()
        fields.update(kwargs)

        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [tracking_number]
        db.execute(
            f"UPDATE emails SET {set_clause} WHERE tracking_number = ?",
            values
        )
        db.commit()
        db.close()


def update_change_key(tracking_number: str, new_change_key: str):
    """Update the ChangeKey for an email (required after UpdateItem response)."""
    with _lock:
        db = _conn()
        db.execute(
            "UPDATE emails SET change_key = ? WHERE tracking_number = ?",
            (new_change_key, tracking_number)
        )
        db.commit()
        db.close()


def get_pending() -> list[dict]:
    """Return all emails with bot_status = PENDING."""
    with _lock:
        db = _conn()
        rows = db.execute(
            "SELECT * FROM emails WHERE bot_status = 'PENDING'"
        ).fetchall()
        db.close()
        return [dict(r) for r in rows]


def get_confirmed() -> list[dict]:
    """Return all emails with bot_status = CONFIRMED (ready to be flagged)."""
    with _lock:
        db = _conn()
        rows = db.execute(
            "SELECT * FROM emails WHERE bot_status = 'CONFIRMED'"
        ).fetchall()
        db.close()
        return [dict(r) for r in rows]


def get_all(limit: int = 100) -> list[dict]:
    """Return all emails ordered by most recently seen first."""
    with _lock:
        db = _conn()
        rows = db.execute(
            "SELECT * FROM emails ORDER BY first_seen_at DESC LIMIT ?",
            (limit,)
        ).fetchall()
        db.close()
        return [dict(r) for r in rows]


def get_counts() -> dict:
    """Return count of emails per status."""
    with _lock:
        db = _conn()
        counts = {}
        for status in ("PENDING", "CONFIRMED", "FAILED", "FLAGGED", "GONE", "ERROR"):
            row = db.execute(
                "SELECT COUNT(*) AS cnt FROM emails WHERE bot_status = ?",
                (status,)
            ).fetchone()
            counts[status.lower()] = row["cnt"]
        db.close()
        return counts


# ── Activity log ──────────────────────────────────────────────────────────────

def log_activity(level: str, event: str, tracking: str = None, detail: str = None):
    """Append a row to the activity log (shown on dashboard)."""
    try:
        with _lock:
            db = _conn()
            db.execute(
                "INSERT INTO activity_log (ts, level, event, tracking, detail) VALUES (?,?,?,?,?)",
                (datetime.now().strftime("%H:%M:%S"), level, event, tracking, detail)
            )
            db.commit()
            db.close()
    except Exception:
        pass


def get_activity(limit: int = 50) -> list[dict]:
    """Return the most recent activity entries for the dashboard."""
    with _lock:
        db = _conn()
        rows = db.execute(
            "SELECT * FROM activity_log ORDER BY id DESC LIMIT ?",
            (limit,)
        ).fetchall()
        db.close()
        return [dict(r) for r in rows]


# ── Session metadata ──────────────────────────────────────────────────────────

def set_meta(key: str, value: str):
    with _lock:
        db = _conn()
        db.execute(
            "INSERT OR REPLACE INTO session_meta (key, value) VALUES (?, ?)",
            (key, str(value))
        )
        db.commit()
        db.close()


def get_meta(key: str, default: str = None) -> str | None:
    with _lock:
        db = _conn()
        row = db.execute(
            "SELECT value FROM session_meta WHERE key = ?", (key,)
        ).fetchone()
        db.close()
        return row["value"] if row else default
