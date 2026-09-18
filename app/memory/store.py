import sqlite3
import json
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime

from app.agent.state import Message

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "threads.db"


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                thread_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                meta TEXT DEFAULT '{}'
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS threads (
                thread_id TEXT PRIMARY KEY,
                prospect_email TEXT,
                booking_status TEXT DEFAULT 'NONE',
                confirmed_slot TEXT,
                proposed_slot TEXT,
                last_quoted_rate REAL,
                walk_away INTEGER DEFAULT 0,
                updated_at TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_thread ON messages(thread_id)")
        conn.commit()


def append_message(thread_id: str, msg: Message) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO messages (thread_id, role, content, timestamp, meta) VALUES (?,?,?,?,?)",
            (thread_id, msg.role, msg.content, msg.timestamp, json.dumps(msg.meta or {})),
        )
        conn.commit()


def load_thread(thread_id: str) -> List[Message]:
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT role, content, timestamp, meta FROM messages WHERE thread_id = ? ORDER BY id ASC",
            (thread_id,),
        ).fetchall()
    return [
        Message(
            role=r[0],
            content=r[1],
            timestamp=r[2],
            meta=json.loads(r[3] or "{}"),
        )
        for r in rows
    ]


def upsert_thread_meta(
    thread_id: str,
    *,
    prospect_email: Optional[str] = None,
    booking_status: Optional[str] = None,
    confirmed_slot: Optional[str] = None,
    proposed_slot: Optional[str] = None,
    last_quoted_rate: Optional[float] = None,
    walk_away: Optional[bool] = None,
) -> None:
    now = datetime.utcnow().isoformat()
    with sqlite3.connect(DB_PATH) as conn:
        # Ensure row exists
        conn.execute(
            "INSERT OR IGNORE INTO threads (thread_id, updated_at) VALUES (?, ?)",
            (thread_id, now),
        )
        updates = ["updated_at = ?"]
        values: list[Any] = [now]

        if prospect_email is not None:
            updates.append("prospect_email = ?")
            values.append(prospect_email)
        if booking_status is not None:
            updates.append("booking_status = ?")
            values.append(booking_status)
        if confirmed_slot is not None:
            updates.append("confirmed_slot = ?")
            values.append(confirmed_slot)
        if proposed_slot is not None:
            updates.append("proposed_slot = ?")
            values.append(proposed_slot)
        if last_quoted_rate is not None:
            updates.append("last_quoted_rate = ?")
            values.append(last_quoted_rate)
        if walk_away is not None:
            updates.append("walk_away = ?")
            values.append(1 if walk_away else 0)

        values.append(thread_id)
        conn.execute(
            f"UPDATE threads SET {', '.join(updates)} WHERE thread_id = ?",
            values,
        )
        conn.commit()


def get_thread_meta(thread_id: str) -> Dict[str, Any]:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT prospect_email, booking_status, confirmed_slot, proposed_slot, "
            "last_quoted_rate, walk_away FROM threads WHERE thread_id = ?",
            (thread_id,),
        ).fetchone()
    if not row:
        return {
            "prospect_email": None,
            "booking_status": "NONE",
            "confirmed_slot": None,
            "proposed_slot": None,
            "last_quoted_rate": None,
            "walk_away": False,
        }
    return {
        "prospect_email": row[0],
        "booking_status": row[1] or "NONE",
        "confirmed_slot": row[2],
        "proposed_slot": row[3],
        "last_quoted_rate": row[4],
        "walk_away": bool(row[5]),
    }