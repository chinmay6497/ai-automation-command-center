"""SQLite persistence layer (stdlib sqlite3, WAL mode, thread-safe)."""
import json
import sqlite3
import threading
import time
import uuid

from . import config

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,                -- lead | email
    payload TEXT NOT NULL,             -- original submission JSON
    status TEXT NOT NULL,              -- processing | pending_approval | auto_handled | approved | rejected | failed
    classification TEXT,
    score INTEGER,
    priority TEXT,                     -- hot | warm | cold
    summary TEXT,
    draft TEXT,
    risk_level TEXT,
    risk_notes TEXT,
    engine TEXT,                       -- groq | heuristic-fallback
    created_at REAL NOT NULL,
    completed_at REAL,
    duration_ms INTEGER
);
CREATE TABLE IF NOT EXISTS traces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id TEXT NOT NULL,
    agent TEXT NOT NULL,
    title TEXT NOT NULL,
    detail TEXT,
    ts REAL NOT NULL
);
"""


def get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.row_factory = sqlite3.Row
        with _lock:
            _conn.executescript(SCHEMA)
            _conn.commit()
    return _conn


def reset_for_tests(path: str = ":memory:") -> None:
    """Point the module at a fresh database (used by the test suite)."""
    global _conn
    if _conn is not None:
        _conn.close()
    _conn = None
    config.DB_PATH = path


def create_item(kind: str, payload: dict) -> str:
    item_id = uuid.uuid4().hex[:12]
    with _lock:
        get_conn().execute(
            "INSERT INTO items (id, kind, payload, status, created_at) VALUES (?,?,?,?,?)",
            (item_id, kind, json.dumps(payload), "processing", time.time()),
        )
        get_conn().commit()
    return item_id


def update_item(item_id: str, **fields) -> None:
    if not fields:
        return
    cols = ", ".join(f"{k}=?" for k in fields)
    with _lock:
        get_conn().execute(f"UPDATE items SET {cols} WHERE id=?", (*fields.values(), item_id))
        get_conn().commit()


def add_trace(item_id: str, agent: str, title: str, detail: str = "") -> dict:
    ts = time.time()
    with _lock:
        get_conn().execute(
            "INSERT INTO traces (item_id, agent, title, detail, ts) VALUES (?,?,?,?,?)",
            (item_id, agent, title, detail, ts),
        )
        get_conn().commit()
    return {"item_id": item_id, "agent": agent, "title": title, "detail": detail, "ts": ts}


def get_item(item_id: str) -> dict | None:
    row = get_conn().execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
    if not row:
        return None
    item = dict(row)
    item["payload"] = json.loads(item["payload"])
    item["trace"] = [
        dict(t)
        for t in get_conn().execute(
            "SELECT agent, title, detail, ts FROM traces WHERE item_id=? ORDER BY id", (item_id,)
        ).fetchall()
    ]
    return item


def list_items(limit: int = 50) -> list[dict]:
    rows = get_conn().execute(
        "SELECT * FROM items ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        item["payload"] = json.loads(item["payload"])
        out.append(item)
    return out


def metrics() -> dict:
    conn = get_conn()
    total = conn.execute("SELECT COUNT(*) c FROM items").fetchone()["c"]
    hot = conn.execute("SELECT COUNT(*) c FROM items WHERE priority='hot'").fetchone()["c"]
    pending = conn.execute(
        "SELECT COUNT(*) c FROM items WHERE status='pending_approval'"
    ).fetchone()["c"]
    auto = conn.execute("SELECT COUNT(*) c FROM items WHERE status='auto_handled'").fetchone()["c"]
    avg_ms = conn.execute(
        "SELECT AVG(duration_ms) a FROM items WHERE duration_ms IS NOT NULL"
    ).fetchone()["a"]
    by_priority = {
        r["priority"]: r["c"]
        for r in conn.execute(
            "SELECT priority, COUNT(*) c FROM items WHERE priority IS NOT NULL GROUP BY priority"
        ).fetchall()
    }
    return {
        "total_items": total,
        "hot_leads": hot,
        "pending_approvals": pending,
        "auto_handled": auto,
        "avg_processing_ms": round(avg_ms) if avg_ms else None,
        "by_priority": by_priority,
    }
