"""SQLite entity-state log. valid_from and recorded_at are independent (bitemporal)."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "crisis_os.db"
SCHEMA = Path(__file__).with_name("schema.sql")

_conn: sqlite3.Connection | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_db() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(DB_PATH)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA foreign_keys=ON")
        _conn.executescript(SCHEMA.read_text(encoding="utf-8"))
        _conn.commit()
    return _conn


def reset_db() -> None:
    global _conn
    if _conn:
        _conn.close()
        _conn = None
    if DB_PATH.exists():
        DB_PATH.unlink()
    get_db()


def upsert_entity(entity_id: str, type: str, name: str,
                  geometry: dict | None = None, attributes: dict | None = None,
                  aliases: list | None = None) -> None:
    conn = get_db()
    conn.execute(
        "INSERT OR REPLACE INTO entities(entity_id,type,name,geometry,attributes,aliases) VALUES(?,?,?,?,?,?)",
        (entity_id, type, name, json.dumps(geometry or {}), json.dumps(attributes or {}),
         json.dumps(aliases or [])),
    )
    conn.commit()


def add_relationship(frm: str, to: str, rel_type: str, active: int = 1) -> None:
    conn = get_db()
    conn.execute(
        "INSERT INTO relationships(from_entity,to_entity,rel_type,active) VALUES(?,?,?,?)",
        (frm, to, rel_type, active),
    )
    conn.commit()


def deactivate_relationship(frm: str, to: str, rel_type: str) -> None:
    get_db().execute(
        "UPDATE relationships SET active=0 WHERE from_entity=? AND to_entity=? AND rel_type=?",
        (frm, to, rel_type),
    )
    get_db().commit()


def append_state(state_id: str, entity_id: str, state: str,
                 attributes: dict | None = None, source_event_id: str | None = None,
                 confidence: float = 1.0, label: str = "known",
                 valid_from: str | None = None, recorded_at: str | None = None) -> None:
    """Close current row, write new. valid_from may precede recorded_at (B7 chronology)."""
    conn = get_db()
    rec = recorded_at or _now()
    vf = valid_from or rec
    conn.execute(
        "UPDATE entity_states SET valid_until=? WHERE entity_id=? AND valid_until IS NULL",
        (rec, entity_id),
    )
    conn.execute(
        "INSERT INTO entity_states(state_id,entity_id,state,attributes,valid_from,valid_until,"
        " source_event_id,confidence,label,recorded_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
        (state_id, entity_id, state, json.dumps(attributes or {}), vf, None,
         source_event_id, confidence, label, rec),
    )
    conn.commit()


def current_state(entity_id: str) -> dict | None:
    row = get_db().execute(
        "SELECT * FROM entity_states WHERE entity_id=? AND valid_until IS NULL ORDER BY recorded_at DESC LIMIT 1",
        (entity_id,),
    ).fetchone()
    if not row:
        return None
    d = dict(row)
    d["attributes"] = json.loads(d["attributes"] or "{}")
    return d
