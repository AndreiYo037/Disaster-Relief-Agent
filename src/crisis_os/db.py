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
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA foreign_keys=ON")
        _conn.executescript(SCHEMA.read_text(encoding="utf-8"))
        columns = {row[1] for row in _conn.execute("PRAGMA table_info(agent_runs)")}
        if "latency_ms" not in columns:
            _conn.execute("ALTER TABLE agent_runs ADD COLUMN latency_ms INTEGER NOT NULL DEFAULT 0")
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


def insert_audit_if_new(
    actor: str,
    action: str,
    object_type: str,
    object_id: str,
    at: str,
    doc: str,
) -> None:
    conn = get_db()
    conn.execute(
        "INSERT INTO audit(actor,action,object_type,object_id,at,doc) "
        "SELECT ?,?,?,?,?,? WHERE NOT EXISTS ("
        "SELECT 1 FROM audit WHERE actor IS ? AND action IS ? AND object_type IS ? "
        "AND object_id IS ? AND at IS ? AND doc IS ?)",
        (actor, action, object_type, object_id, at, doc,
         actor, action, object_type, object_id, at, doc),
    )


def _insert_audit_rows(conn: sqlite3.Connection, rows: list[tuple]) -> None:
    for row in rows:
        conn.execute(
            "INSERT INTO audit(actor,action,object_type,object_id,at,doc) "
            "SELECT ?,?,?,?,?,? WHERE NOT EXISTS ("
            "SELECT 1 FROM audit WHERE actor IS ? AND action IS ? AND object_type IS ? "
            "AND object_id IS ? AND at IS ? AND doc IS ?)",
            (*row, *row),
        )


def persist_agent_state(state: dict) -> None:
    """Persist validated agent records and one replay checkpoint."""
    conn = get_db()
    tables = {
        "evidence": ("evidence_id", ("source_type", "source_ref", "observed_at", "captured_at",
                                      "artifact_ref", "content_hash")),
        "claims": ("claim_id", ("event_type", "subject", "observed_at", "source_lane")),
        "verification_runs": ("verification_id", ("claim_id", "verdict", "support")),
        "evaluations": ("evaluation_id", ("claim_id", "total_score")),
        "incidents": ("incident_id", ("event_type", "lifecycle_status", "priority", "confidence")),
        "work_items": ("work_item_id", ("incident_id", "kind", "status")),
        "agent_runs": ("agent_run_id", ("agent_name", "stage", "retry_count", "latency_ms", "token_input", "token_output")),
    }
    rows = {
        "evidence": state.get("evidence", []),
        "claims": state.get("claims", []),
        "verification_runs": state.get("verification_runs", []),
        "evaluations": state.get("evaluations", []),
        "incidents": state.get("incidents", []),
        "work_items": state.get("work_items", []),
        "agent_runs": state.get("agent_runs", []),
    }
    with conn:
        for table, (id_key, fields) in tables.items():
            for record in rows[table]:
                data = record.model_dump(mode="json", by_alias=True)
                if table == "claims":
                    conn.execute(
                        "INSERT OR IGNORE INTO claims(claim_id,observation_id,subject,predicate,value,doc) "
                        "VALUES(?,?,?,?,?,?)",
                        (
                            data["claim_id"],
                            data["evidence_refs"][0],
                            data["subject"],
                            data["event_type"],
                            json.dumps({
                                "claim_text": data["claim_text"],
                                "structured_value": data["structured_value"],
                            }, sort_keys=True),
                            json.dumps(data, sort_keys=True),
                        ),
                    )
                    continue
                values = [data.get(field) for field in fields]
                conn.execute(
                    f"INSERT OR IGNORE INTO {table}({id_key},{','.join(fields)},doc) "
                    f"VALUES({','.join('?' for _ in range(len(fields) + 2))})",
                    [data[id_key], *values, json.dumps(data, sort_keys=True)],
                )
        for table, id_key, fields in (
            ("agent_errors", "error_id", ("agent_name", "stage", "error_class", "attempt_number", "final_disposition")),
            ("feedback_requests", "feedback_request_id", ("incident_id", "target_source_lane", "cycle_number", "status")),
        ):
            for record in state.get(table, []):
                data = record.model_dump(mode="json", by_alias=True)
                conn.execute(
                    f"INSERT OR IGNORE INTO {table}({id_key},{','.join(fields)},doc) "
                    f"VALUES({','.join('?' for _ in range(len(fields) + 2))})",
                    [data[id_key], *(data.get(field) for field in fields), json.dumps(data, sort_keys=True)],
                )
        checkpoint = json.dumps(_json_state(state), sort_keys=True).encode("utf-8")
        conn.execute(
            "INSERT OR IGNORE INTO agent_checkpoints(run_id,keyframe_id,state_json,recorded_at) VALUES(?,?,?,?)",
            (
                state["run_id"],
                state["keyframe_id"],
                checkpoint,
                state.get("recorded_at", _now()),
            ),
        )
        audit_rows = [(
            "OrchestratorAgent",
            "checkpoint.write",
            "agent_run",
            state["keyframe_id"],
            state.get("recorded_at", _now()),
            json.dumps({"run_id": state["run_id"], "keyframe_id": state["keyframe_id"], "agent_error_count": len(state.get("agent_errors", []))}),
        )]
        for record in state.get("agent_runs", []):
            audit_rows.append((
                record.agent_name, "agent.completed", "agent_run", record.agent_run_id,
                record.completed_at, record.model_dump_json(),
            ))
        for record in state.get("agent_errors", []):
            audit_rows.append((
                record.agent_name, "agent.error", "agent_error", record.error_id,
                record.timestamp, record.model_dump_json(),
            ))
        for record in state.get("incidents", []):
            for merge in record.merge_history:
                audit_rows.append((
                    "DispatchResourcePlanningAgent", "incident.merge", "incident",
                    record.incident_id, merge.get("at", record.updated_at),
                    json.dumps(merge, sort_keys=True),
                ))
        for record in state.get("summaries", []):
            audit_rows.append((
                "SummariserAgent", "summary.generated", "summary", record.summary_id,
                record.generated_at, record.model_dump_json(),
            ))
        _insert_audit_rows(conn, audit_rows)


def _json_state(state: dict) -> dict:
    def convert(value):
        if hasattr(value, "model_dump"):
            return value.model_dump(mode="json", by_alias=True)
        if isinstance(value, list):
            return [convert(item) for item in value]
        if isinstance(value, set):
            return sorted(value)
        if isinstance(value, dict):
            return {key: convert(item) for key, item in value.items()}
        return value

    return convert(state)


def langgraph_checkpointer():
    """Return LangGraph's native SQLite checkpointer on the shared DB."""
    from langgraph.checkpoint.sqlite import SqliteSaver
    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

    allowed = [
        ("crisis_os.models", name)
        for name in (
            "AgentError", "AgentRun", "CheckStatus", "Claim", "Evaluation",
            "EvidenceEnvelope", "FeedbackRequest", "Incident", "LaneResult",
            "LaneStatus", "Observation", "Summary", "SummaryFact", "VerificationRun",
            "Verdict", "WorkItem",
        )
    ]
    saver = SqliteSaver(get_db(), serde=JsonPlusSerializer(allowed_msgpack_modules=allowed))
    saver.setup()
    return saver
