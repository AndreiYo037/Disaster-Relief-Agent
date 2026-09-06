"""Typed CrisisIO agent records and deterministic safety policy."""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, TypeVar

from .models import (
    AgentError,
    AgentRun,
    CheckStatus,
    Claim,
    HumanDecision,
    Incident,
    LaneStatus,
    PriorityDecision,
    VerificationRun,
    Verdict,
    utc_now,
)

AGENT_ROSTER = [
    "SatelliteSourceAgent",
    "TelemetrySourceAgent",
    "FieldReportSourceAgent",
    "CommunityReportSourceAgent",
    "SatelliteVerificationAgent",
    "TelemetryVerificationAgent",
    "FieldReportVerificationAgent",
    "CommunityReportVerificationAgent",
    "SatelliteEvaluationAgent",
    "TelemetryEvaluationAgent",
    "FieldReportEvaluationAgent",
    "CommunityReportEvaluationAgent",
    "DispatchResourcePlanningAgent",
    "OrchestratorAgent",
    "SummariserAgent",
]

LANES = ("satellite", "telemetry", "field_report", "community")
LANE_AGENTS = {
    "satellite": ("SatelliteSourceAgent", "SatelliteVerificationAgent", "SatelliteEvaluationAgent"),
    "telemetry": ("TelemetrySourceAgent", "TelemetryVerificationAgent", "TelemetryEvaluationAgent"),
    "field_report": ("FieldReportSourceAgent", "FieldReportVerificationAgent", "FieldReportEvaluationAgent"),
    "community": ("CommunityReportSourceAgent", "CommunityReportVerificationAgent", "CommunityReportEvaluationAgent"),
}

TOOL_ALLOWLIST = {
    "SatelliteSourceAgent": {
        "adapter.satellite.read_fixture", "artifact.put", "evidence.append",
        "observation.append", "claim.append",
    },
    "TelemetrySourceAgent": {
        "adapter.telemetry.read_fixture", "artifact.put", "evidence.append",
        "observation.append", "claim.append",
    },
    "FieldReportSourceAgent": {
        "adapter.field_report.read_fixture", "artifact.put", "evidence.append",
        "observation.append", "claim.append",
    },
    "CommunityReportSourceAgent": {
        "adapter.community.read_fixture", "artifact.put", "evidence.append",
        "observation.append", "claim.append",
    },
    **{
        agent: {
            "evidence.get_by_ids", "claims.get_by_ids",
            "claims.find_corroboration", "verification.append",
        }
        for agent in (
            "SatelliteVerificationAgent",
            "TelemetryVerificationAgent",
            "FieldReportVerificationAgent",
            "CommunityReportVerificationAgent",
        )
    },
    **{
        agent: {"evidence.get_by_ids", "claims.get_by_ids", "policy.get_version", "evaluation.append"}
        for agent in (
            "SatelliteEvaluationAgent",
            "TelemetryEvaluationAgent",
            "FieldReportEvaluationAgent",
            "CommunityReportEvaluationAgent",
        )
    },
    "DispatchResourcePlanningAgent": {
        "world.routes.read", "world.resources.read", "incidents.append", "work_items.append",
    },
    "OrchestratorAgent": {
        "state.read_current", "incidents.append", "feedback_requests.append",
        "checkpoint.read", "checkpoint.write",
    },
    "SummariserAgent": {
        "incidents.read", "evidence.get_by_ids", "work_items.read",
        "summary.append", "projection.write",
    },
}

MAX_RETRIES = 2
MAX_FEEDBACK_CYCLES = 3
MAX_REVIEW_ROUNDS = 3
CHECK_NAMES = ("provenance", "schema", "time_location", "consistency", "corroboration")
DEFAULT_CLUSTER_RADIUS_KM = 1.0
DEFAULT_CLUSTER_WINDOW_HOURS = 6.0
DEFAULT_FRESHNESS_WINDOW_HOURS = 6.0
T = TypeVar("T")


class StateConflict(ValueError):
    """Raised when an append-only record ID is reused with different content."""


def _json(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", by_alias=True)
    return json.loads(json.dumps(value, sort_keys=True, default=str))


def _record_id(value: Any) -> str:
    data = _json(value)
    for key in (
        "evidence_id", "observation_id", "claim_id", "verification_id",
        "evaluation_id", "work_item_id", "error_id", "summary_id",
        "lane_result_id", "feedback_request_id", "agent_run_id", "incident_id",
    ):
        if data.get(key):
            return str(data[key])
    raise ValueError("append-only records require a stable *_id field")


def append_unique(existing: list[T], incoming: Iterable[T]) -> list[T]:
    """Pure ordered reducer: duplicate content is a no-op; conflicting IDs fail."""
    result = list(existing)
    by_id = {_record_id(item): _json(item) for item in result}
    for item in incoming:
        key = _record_id(item)
        value = _json(item)
        if key in by_id:
            if by_id[key] != value:
                raise StateConflict(f"record {key} already exists with different content")
            continue
        result.append(item)
        by_id[key] = value
    return result


def _parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _haversine_km(a: Mapping[str, float] | None, b: Mapping[str, float] | None) -> float:
    if not a or not b:
        return math.inf
    lat1, lon1, lat2, lon2 = map(math.radians, (a["lat"], a["lon"], b["lat"], b["lon"]))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371.0088 * 2 * math.asin(math.sqrt(h))


def _policy_override(
    policy: Mapping[str, Mapping[str, Any]] | None,
    event_type: str,
    *,
    radius_km: float,
    temporal_window_hours: float,
) -> tuple[float, float]:
    override = dict(policy.get(event_type, {})) if policy else {}
    return (
        float(override.get("radius_km", override.get("distance_km", radius_km))),
        float(override.get("temporal_window_hours", override.get("window_hours", temporal_window_hours))),
    )


def freshness_policy(
    event_type: str | None = None,
    *,
    policy: Mapping[str, Mapping[str, Any]] | None = None,
    window_hours: float = DEFAULT_FRESHNESS_WINDOW_HOURS,
) -> dict[str, float]:
    override = dict(policy.get(event_type, {})) if policy and event_type in policy else {}
    return {
        "window_hours": float(override.get("window_hours", override.get("temporal_window_hours", window_hours))),
        "radius_km": float(override.get("radius_km", override.get("distance_km", DEFAULT_CLUSTER_RADIUS_KM))),
    }


def evidence_freshness(
    observed_at: str,
    compared_at: str | None = None,
    *,
    event_type: str | None = None,
    policy: Mapping[str, Mapping[str, Any]] | None = None,
) -> float:
    window_hours = freshness_policy(event_type, policy=policy)["window_hours"]
    reference = _parse_dt(compared_at) if compared_at else datetime.now(timezone.utc)
    age_hours = abs((reference - _parse_dt(observed_at)).total_seconds()) / 3600
    return 1.0 if age_hours <= window_hours + 1e-9 else 0.0


def route_candidate_conflicts(
    route_id: str,
    keyframe_id: str,
    *,
    incident_subject: str | None = None,
) -> list[str]:
    from .snapshot import build_snapshot, load_parameters

    snapshot = build_snapshot(load_parameters(), keyframe_id)
    route_paths = snapshot.get("route_paths", {})
    route_states = {
        entity["entity_id"]: entity.get("state")
        for entity in snapshot.get("entities", [])
        if entity.get("entity_id", "").startswith("route:")
    }
    conflicts: list[str] = []
    if route_id not in route_paths:
        conflicts.append(f"{route_id} missing from world model")
    state = route_states.get(route_id)
    if state and state != "operational":
        conflicts.append(f"{route_id} is {state}")
    return conflicts


def build_verification(
    claim_id: str,
    evidence_refs: list[str],
    checks: Mapping[str, CheckStatus | str],
    *,
    crisis_id: str = "katrina-nola-2005",
    run_id: str = "run-test",
    keyframe_id: str = "t0",
    trace_id: str = "trace-test",
    agent_run_id: str = "agent-run-test",
) -> VerificationRun:
    if set(checks) != set(CHECK_NAMES):
        raise ValueError(f"verification checks must be exactly {CHECK_NAMES}")
    normalized = {key: CheckStatus(value) for key, value in checks.items()}
    passes = sum(value is CheckStatus.PASS for value in normalized.values())
    unknowns = sum(value is CheckStatus.UNKNOWN for value in normalized.values())
    fails = len(normalized) - passes - unknowns
    verdict = Verdict.PASS if passes >= 4 else Verdict.UNKNOWN if passes >= 2 else Verdict.FAIL
    support = round(sum(
        1.0 if value is CheckStatus.PASS else 0.5 if value is CheckStatus.UNKNOWN else 0.0
        for value in normalized.values()
    ) / len(CHECK_NAMES), 6)
    return VerificationRun(
        verification_id=f"verification-{claim_id}-{agent_run_id}",
        claim_id=claim_id,
        checks=normalized,
        pass_count=passes,
        unknown_count=unknowns,
        fail_count=fails,
        verdict=verdict,
        support=support,
        confidence=support,
        failed_checks=[key for key, value in normalized.items() if value is CheckStatus.FAIL],
        reason=f"{passes} passing, {unknowns} unknown, {fails} failing checks",
        verifier_version="verification-v1",
        policy_version="policy-v1",
        evidence_refs=list(evidence_refs),
        crisis_id=crisis_id,
        run_id=run_id,
        keyframe_id=keyframe_id,
        trace_id=trace_id,
        agent_run_id=agent_run_id,
    )


def calculate_priority(
    loss_of_life_risk: float,
    damage_severity: float,
    service_criticality: float,
    time_criticality: float,
    support: float,
    verdict: Verdict | str,
    contradictory: bool,
) -> PriorityDecision:
    verdict = Verdict(verdict)
    harm_score = 100 * (
        0.55 * loss_of_life_risk
        + 0.25 * damage_severity
        + 0.10 * service_criticality
        + 0.10 * time_criticality
    )
    priority = round(harm_score * (0.60 + 0.40 * support))
    if contradictory:
        route = "REQUEST_EVIDENCE"
    elif loss_of_life_risk >= 0.70 and time_criticality >= 0.70:
        priority = max(priority, 90)
        route = "URGENT_HUMAN_REVIEW"
    elif support < 0.40 or verdict is not Verdict.PASS:
        route = "REQUEST_EVIDENCE"
    elif priority >= 80 and support >= 0.80:
        route = "DISPATCH_CANDIDATE"
    elif priority >= 60:
        route = "MONITOR"
    else:
        route = "UNVERIFIED"
    return PriorityDecision(
        harm_score=round(harm_score, 6),
        priority=priority,
        route=route,
        support=support,
    )


def cluster_claims(
    claims: Iterable[Claim | Mapping[str, Any]],
    *,
    spatial_radius_km: float = 1.0,
    temporal_window_hours: float = 6.0,
    policy: Mapping[str, Mapping[str, Any]] | None = None,
) -> list[Incident]:
    normalized = [claim if isinstance(claim, Claim) else Claim.model_validate(claim) for claim in claims]
    incidents: list[Incident] = []
    for claim in normalized:
        match = None
        claim_radius_km, claim_window_hours = _policy_override(
            policy,
            claim.event_type,
            radius_km=spatial_radius_km,
            temporal_window_hours=temporal_window_hours,
        )
        for incident in incidents:
            if incident.event_type != claim.event_type:
                continue
            if _haversine_km(incident.location, claim.location) > claim_radius_km + 1e-9:
                continue
            if incident.time_window:
                observed = _parse_dt(claim.observed_at)
                start = _parse_dt(incident.time_window["start"])
                end = _parse_dt(incident.time_window["end"])
                delta = min(
                    abs(observed - start).total_seconds(),
                    abs(observed - end).total_seconds(),
                ) / 3600
                if delta > claim_window_hours + 1e-9:
                    continue
            match = incident
            break
        if match is None:
            incidents.append(Incident(
                incident_id=f"incident-{claim.claim_id}",
                deduplication_id=f"dedupe-{claim.event_type}-{claim.subject}",
                claim_refs=[claim.claim_id],
                evidence_refs=list(claim.evidence_refs),
                event_type=claim.event_type,
                subject=claim.subject,
                location=claim.location,
                time_window={"start": claim.observed_at, "end": claim.observed_at},
                created_at=claim.observed_at,
                updated_at=claim.observed_at,
            ))
            continue
        merge = {
            "merged_claim_id": claim.claim_id,
            "prior_incident_id": match.incident_id,
            "reason": "same event type within 1 km and 6 hours",
            "at": claim.observed_at,
        }
        contradictions = list(match.contradictions)
        if claim.structured_value.get("contradicts"):
            contradictions.append(claim.claim_id)
        incidents[incidents.index(match)] = match.model_copy(update={
            "claim_refs": match.claim_refs + [claim.claim_id],
            "evidence_refs": list(dict.fromkeys(match.evidence_refs + claim.evidence_refs)),
            "time_window": {
                "start": min(match.time_window["start"], claim.observed_at),
                "end": max(match.time_window["end"], claim.observed_at),
            },
            "updated_at": claim.observed_at,
            "contradictions": contradictions,
            "merge_history": match.merge_history + [merge],
        })
    return incidents


def dispatch_status(
    incident: Incident,
    decision: HumanDecision | None,
    expected_proposal_id: str | None = None,
    expected_proposal_version: int | None = None,
) -> str:
    if decision is None:
        return "REVIEW_REQUIRED"
    if decision.role not in ("coordinator", "logistics_lead", "named_authority") or not decision.reason:
        return "REVIEW_REQUIRED"
    if (
        not expected_proposal_id
        or not isinstance(expected_proposal_version, int)
        or isinstance(expected_proposal_version, bool)
        or expected_proposal_version <= 0
        or decision.incident_id != incident.incident_id
        or decision.proposal_id != expected_proposal_id
        or decision.proposal_version != expected_proposal_version
    ):
        return "REVIEW_REQUIRED"
    if decision.action == "reject":
        return "REJECTED"
    if (
        incident.verification_verdict is not Verdict.PASS
        or incident.route not in ("DISPATCH_CANDIDATE", "URGENT_HUMAN_REVIEW")
    ):
        return "REVIEW_REQUIRED"
    return "DISPATCHED"


def next_feedback_cycle(current_cycle: int) -> int | None:
    return current_cycle + 1 if 0 <= current_cycle < MAX_FEEDBACK_CYCLES else None


def review_round_allowed(current_round: int) -> bool:
    return 0 <= current_round < MAX_REVIEW_ROUNDS


def fixture_path() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "katrina" / "agent-fixtures.json"


def load_fixtures() -> dict[str, Any]:
    return json.loads(fixture_path().read_text(encoding="utf-8"))


class ToolGateway:
    """Deny-by-default fixture gateway; only typed return values enter graph state."""

    def __init__(self, agent_name: str, timestamp: str | None = None):
        self.agent_name = agent_name
        self.timestamp = timestamp
        self.calls: list[dict[str, Any]] = []

    def call(self, tool_id: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        raw_arguments = dict(arguments) if isinstance(arguments, Mapping) else {"_raw": repr(arguments)}
        if tool_id not in TOOL_ALLOWLIST.get(self.agent_name, set()):
            return self._deny(tool_id, raw_arguments, f"{self.agent_name} cannot call {tool_id}")
        schema = TOOL_ARGUMENT_SCHEMAS.get(tool_id)
        if schema is None:
            return self._deny(tool_id, raw_arguments, f"no argument schema for {tool_id}")
        required, validators = schema
        keys = set(raw_arguments)
        missing = required - keys
        extra = keys - set(validators)
        if missing:
            return self._deny(tool_id, raw_arguments, f"missing arguments: {sorted(missing)}")
        if extra:
            return self._deny(tool_id, raw_arguments, f"unknown arguments: {sorted(extra)}")
        invalid = [
            key for key, validator in validators.items()
            if not validator(raw_arguments[key])
        ]
        if invalid:
            return self._deny(tool_id, raw_arguments, f"malformed arguments: {invalid}")
        self.calls.append({
            "tool_id": tool_id,
            "arguments": raw_arguments,
            "at": self.timestamp or utc_now(),
            "status": "ALLOWED",
        })
        return raw_arguments

    def _deny(self, tool_id: str, arguments: dict[str, Any], reason: str) -> dict[str, Any]:
        self.calls.append({
            "tool_id": tool_id,
            "arguments": arguments,
            "at": self.timestamp or utc_now(),
            "status": "DENIED",
            "reason": reason,
        })
        raise PermissionError(reason)


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _nonnegative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _string_list(value: Any) -> bool:
    return isinstance(value, list) and all(_text(item) for item in value)


TOOL_ARGUMENT_SCHEMAS = {
    **{
        f"adapter.{lane}.read_fixture": ({"keyframe_id"}, {"keyframe_id": _text})
        for lane in LANES
    },
    "artifact.put": (
        {"artifact_ref", "content_hash"},
        {"artifact_ref": _text, "content_hash": _text},
    ),
    "evidence.append": ({"evidence_id"}, {"evidence_id": _text}),
    "observation.append": ({"observation_id"}, {"observation_id": _text}),
    "claim.append": ({"claim_id"}, {"claim_id": _text}),
    "evidence.get_by_ids": ({"count"}, {"count": _nonnegative_int}),
    "claims.get_by_ids": ({"count"}, {"count": _nonnegative_int}),
    "claims.find_corroboration": ({"claim_id"}, {"claim_id": _text}),
    "verification.append": ({"verification_id"}, {"verification_id": _text}),
    "policy.get_version": ({"policy_version"}, {"policy_version": _text}),
    "evaluation.append": ({"evaluation_id"}, {"evaluation_id": _text}),
    "world.routes.read": ({"route_count"}, {"route_count": _nonnegative_int}),
    "world.resources.read": ({"resource_ids"}, {"resource_ids": _string_list}),
    "incidents.append": ({"incident_count"}, {"incident_count": _nonnegative_int}),
    "work_items.append": ({"work_item_count"}, {"work_item_count": _nonnegative_int}),
    "state.read_current": ({"incident_count"}, {"incident_count": _nonnegative_int}),
    "feedback_requests.append": ({"request_count"}, {"request_count": _nonnegative_int}),
    "checkpoint.read": ({"run_id"}, {"run_id": _text}),
    "checkpoint.write": ({"run_id"}, {"run_id": _text}),
    "incidents.read": ({"incident_count"}, {"incident_count": _nonnegative_int}),
    "work_items.read": ({"work_item_count"}, {"work_item_count": _nonnegative_int}),
    "summary.append": ({"summary_count"}, {"summary_count": _nonnegative_int}),
    "projection.write": ({"schema_version"}, {"schema_version": _text}),
}


def validate_tool_manifest() -> None:
    if set(TOOL_ALLOWLIST) != set(AGENT_ROSTER):
        raise ValueError("tool manifest agents must match the 15-agent roster")
    for agent_name, tools in TOOL_ALLOWLIST.items():
        if not tools:
            raise ValueError(f"{agent_name} has no allow-listed tools")
        for tool_id in tools:
            if ".read_live" in tool_id or tool_id not in TOOL_ARGUMENT_SCHEMAS:
                raise ValueError(f"invalid or unscoped tool manifest entry: {tool_id}")


def make_error(
    agent_name: str,
    stage: str,
    message: str,
    *,
    attempt: int,
    input_ref: str | None = None,
    error_class: str = "TRANSIENT",
    timestamp: str | None = None,
    final_disposition: str | None = None,
) -> AgentError:
    if final_disposition is None:
        final_disposition = {
            "TRANSIENT": "RETRYING" if attempt <= MAX_RETRIES else "DEGRADED",
            "RECOVERABLE_OUTPUT": "RETRYING" if attempt <= MAX_RETRIES else "DEGRADED",
            "PERMANENT_CONFIG": "FAILED",
            "PERMANENT_AUTH": "DEGRADED",
            "POLICY_REJECTED": "DEGRADED",
        }.get(error_class, "DEGRADED")
    return AgentError(
        error_id=f"error-{agent_name}-{stage}-{attempt}",
        agent_name=agent_name,
        stage=stage,
        input_ref=input_ref,
        error_class=error_class,
        message=message,
        attempt_number=attempt,
        retry_limit=MAX_RETRIES,
        timestamp=timestamp or utc_now(),
        final_disposition=final_disposition,
    )


def make_agent_run(
    agent_name: str,
    stage: str,
    *,
    valid: bool,
    retry_count: int = 0,
    tool_calls: list[dict[str, Any]] | None = None,
    correlation: Mapping[str, str] | None = None,
    timestamp: str | None = None,
) -> AgentRun:
    from .config import agent_runtime

    correlation = correlation or {}
    runtime = agent_runtime()
    return AgentRun(
        agent_run_id=f"agent-run-{agent_name}-{stage}-{correlation.get('keyframe_id', 'run')}",
        agent_name=agent_name,
        stage=stage,
        model_provider=runtime["provider"],
        model_id=runtime["model_id"],
        region=runtime["region"],
        config_version="agent-runtime-v1",
        started_at=timestamp or utc_now(),
        completed_at=timestamp or utc_now(),
        latency_ms=0,
        input_valid=True,
        output_valid=valid,
        retry_count=retry_count,
        tool_calls=tool_calls or [],
        crisis_id=correlation.get("crisis_id", ""),
        run_id=correlation.get("run_id", ""),
        keyframe_id=correlation.get("keyframe_id", ""),
        trace_id=correlation.get("trace_id", ""),
    )


def lane_result_status(success: bool, errors: Iterable[AgentError]) -> LaneStatus:
    errors = list(errors)
    if success and not errors:
        return LaneStatus.SUCCEEDED
    classes = {error.error_class for error in errors}
    if classes & {"PERMANENT_CONFIG", "POLICY_REJECTED"}:
        return LaneStatus.FAILED
    return LaneStatus.DEGRADED


def replay_projection(result: Any) -> dict[str, Any]:
    """Overlay the additive agentic projection onto the existing WorldSnapshot."""
    state = result.state if hasattr(result, "state") else result
    from .snapshot import build_snapshot, load_parameters

    keyframe = state["keyframe_id"]
    snapshot = build_snapshot(load_parameters(), keyframe)
    incidents = state.get("incidents", [])
    summaries = {s.incident_id: s for s in state.get("summaries", [])}
    verified, unverified = [], []
    for incident in sorted(incidents, key=lambda item: (-item.priority, item.incident_id)):
        summary = summaries.get(incident.incident_id)
        row = {
            "incident_id": incident.incident_id,
            "event_type": incident.event_type,
            "status": incident.lifecycle_status,
            "priority": incident.priority,
            "confidence": incident.confidence,
            "route": incident.route,
            "evidence_refs": incident.evidence_refs,
            "claim_refs": incident.claim_refs,
            "contradictions": incident.contradictions,
            "headline": summary.headline if summary else f"{incident.event_type} at {incident.subject}",
            "uncertainties": summary.uncertainties if summary else ["Summary unavailable"],
        }
        (verified if incident.verification_verdict is Verdict.PASS else unverified).append(row)
    routes = [
        {
            "work_item_id": item.work_item_id,
            "incident_id": item.incident_id,
            "status": item.status,
            "owner": item.owner,
            "route": item.capacity.get("route"),
            "conflicts": item.conflicts,
            "requires_coordinator_approval": item.requires_coordinator_approval,
        }
        for item in state.get("work_items", [])
        if item.kind in ("candidate_route", "physical_dispatch")
    ]
    snapshot["agentic"] = {
        "schema_version": "agentic-v1",
        "source_evidence_summaries": [
            {
                "evidence_id": evidence.evidence_id,
                "source_type": evidence.source_type,
                "observed_at": evidence.observed_at,
                "artifact_ref": evidence.artifact_ref,
            }
            for evidence in state.get("evidence", [])
        ],
        "verified_incidents": verified,
        "unverified_incidents": unverified,
        "dispatch_suggested_routes": routes,
        "dispatch_priorities": [
            {"incident_id": row["incident_id"], "priority": row["priority"], "route": row["route"]}
            for row in verified + unverified
        ],
        "lane_results": [_json(row) for row in state.get("lane_results", [])],
        "feedback_requests": [_json(row) for row in state.get("feedback_requests", [])],
        "planning_degraded": state.get("planning_degraded", False),
        "orchestration_degraded": state.get("orchestration_degraded", False),
        "summarisation_degraded": state.get("summarisation_degraded", False),
        "audit": {
            "run_id": state["run_id"],
            "trace_id": state["trace_id"],
            "agent_error_count": len(state.get("agent_errors", [])),
            "agent_run_count": len(state.get("agent_runs", [])),
            "latency_ms": sum(run.latency_ms for run in state.get("agent_runs", [])),
        },
    }
    return snapshot
