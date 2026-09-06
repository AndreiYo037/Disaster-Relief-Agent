from __future__ import annotations
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class HumanDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    decision_id: str = Field(default_factory=lambda: f"decision-{uuid4().hex}")
    decision_version: int = Field(default=1, gt=0)
    actor: str
    role: str
    action: Literal["approve", "modify", "reject"]
    reason: str
    modifications: dict = Field(default_factory=dict)
    incident_id: str | None = None
    proposal_id: str | None = None
    proposal_version: int | None = Field(default=None, gt=0)
    supersedes_decision_id: str | None = None
    decided_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class Permit(BaseModel):
    permit_id: str
    plan_id: str
    status: str
    authorized_actions: list[str]
    approved_by: str
    authorized_route: str


class CheckStatus(StrEnum):
    PASS = "pass"
    UNKNOWN = "unknown"
    FAIL = "fail"


class Verdict(StrEnum):
    PASS = "PASS"
    UNKNOWN = "UNKNOWN"
    FAIL = "FAIL"


class LaneStatus(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"


EventType = Literal[
    "flood_extent_change",
    "water_level_rise",
    "road_blocked",
    "bridge_damage",
    "people_stranded",
    "resource_shortage",
    "facility_unavailable",
    "route_status",
]
SourceLane = Literal["satellite", "telemetry", "field_report", "community"]


class Record(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class EvidenceEnvelope(Record):
    evidence_id: str
    source_type: SourceLane
    source_ref: str
    captured_at: str
    observed_at: str
    geometry: dict[str, Any] | None = None
    artifact_ref: str
    content_hash: str
    adapter_version: str
    collection_metadata: dict[str, Any] = Field(default_factory=dict)
    reporter_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{16}$")


class Observation(Record):
    observation_id: str
    evidence_refs: list[str] = Field(min_length=1)
    description: str
    source_lane: SourceLane
    observed_at: str
    extraction_metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("extraction_metadata")
    @classmethod
    def reject_verdict_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        def walk(item: Any) -> bool:
            if isinstance(item, dict):
                if any(key in item for key in ("verdict", "verification_verdict")):
                    return True
                return any(walk(child) for child in item.values())
            if isinstance(item, list):
                return any(walk(child) for child in item)
            return False

        if walk(value):
            raise ValueError("observation metadata cannot contain verdict fields")
        return value


class Claim(Record):
    claim_id: str
    version: int = 1
    event_type: EventType
    subject: str
    location: dict[str, float] | None = None
    observed_at: str
    claim_text: str
    structured_value: dict[str, Any] = Field(default_factory=dict)
    evidence_refs: list[str] = Field(min_length=1)
    source_lane: SourceLane
    assumptions: list[str] = Field(default_factory=list)
    extraction_metadata: dict[str, Any] = Field(default_factory=dict)


class VerificationRun(Record):
    verification_id: str
    claim_id: str
    checks: dict[str, CheckStatus]
    pass_count: int
    unknown_count: int
    fail_count: int
    verdict: Verdict
    support: float
    confidence: float
    failed_checks: list[str] = Field(default_factory=list)
    reason: str
    verifier_version: str
    policy_version: str
    evidence_refs: list[str]
    crisis_id: str
    run_id: str
    keyframe_id: str
    trace_id: str
    agent_run_id: str


class Evaluation(Record):
    evaluation_id: str
    claim_id: str
    relevance: int = Field(ge=0, le=2)
    actionability: int = Field(ge=0, le=2)
    freshness: int = Field(ge=0, le=2)
    impact: int = Field(ge=0, le=2)
    coverage_novelty: int = Field(ge=0, le=2)
    loss_of_life_risk: float = Field(alias="L", ge=0, le=1)
    damage_severity: float = Field(alias="D", ge=0, le=1)
    service_criticality: float = Field(alias="C", ge=0, le=1)
    time_criticality: float = Field(alias="T", ge=0, le=1)
    total_score: int
    recommended_next_step: str
    missing_information: list[str] = Field(default_factory=list)
    evidence_refs: list[str]
    rubric_version: str

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)


class Incident(Record):
    incident_id: str
    deduplication_id: str
    claim_refs: list[str]
    evidence_refs: list[str]
    event_type: EventType
    subject: str | None = None
    location: dict[str, float] | None = None
    time_window: dict[str, str] = Field(default_factory=dict)
    lifecycle_status: str = "OPEN"
    priority: int = 0
    confidence: float = 0.0
    route: str = "UNVERIFIED"
    verification_verdict: Verdict = Verdict.UNKNOWN
    next_step: str = "REQUEST_EVIDENCE"
    contradictions: list[str] = Field(default_factory=list)
    work_item_refs: list[str] = Field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    expires_at: str | None = None
    merge_history: list[dict[str, Any]] = Field(default_factory=list)


class WorkItem(Record):
    work_item_id: str
    incident_id: str
    kind: Literal["evidence_request", "monitoring", "candidate_route", "candidate_assignment", "physical_dispatch"]
    owner: str
    status: str
    assumptions: list[str] = Field(default_factory=list)
    eta: str | None = None
    capacity: dict[str, Any] = Field(default_factory=dict)
    conflicts: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    requires_coordinator_approval: bool = False
    proposal_version: int = Field(default=1, gt=0)


class AgentError(Record):
    error_id: str
    agent_name: str
    stage: str
    input_ref: str | None = None
    error_class: Literal[
        "TRANSIENT",
        "RECOVERABLE_OUTPUT",
        "PERMANENT_CONFIG",
        "PERMANENT_AUTH",
        "POLICY_REJECTED",
    ]
    message: str
    attempt_number: int
    retry_limit: int
    timestamp: str
    final_disposition: str


class SummaryFact(Record):
    fact: str
    evidence_refs: list[str] = Field(default_factory=list)
    uncertainty: str | None = None

    @model_validator(mode="after")
    def require_provenance_or_uncertainty(self) -> SummaryFact:
        if not self.evidence_refs and not (self.uncertainty and self.uncertainty.strip()):
            raise ValueError("summary facts require evidence_refs or uncertainty")
        return self


class Summary(Record):
    summary_id: str
    incident_id: str
    generated_at: str
    headline: str
    location: dict[str, float] | None
    status: str
    priority: int
    confidence: float
    known_facts: list[SummaryFact]
    uncertainties: list[str]
    actions: list[dict[str, Any]]
    contradictions: list[str]
    next_update_at: str
    summary_version: str
    crisis_id: str
    run_id: str
    keyframe_id: str
    trace_id: str
    degraded: bool = False


class LaneResult(Record):
    lane_result_id: str
    lane_id: SourceLane
    status: LaneStatus
    output_refs: list[str] = Field(default_factory=list)
    error_refs: list[str] = Field(default_factory=list)
    completed_at: str
    crisis_id: str
    run_id: str
    keyframe_id: str
    trace_id: str


class FeedbackRequest(Record):
    feedback_request_id: str
    incident_id: str
    target_source_lane: SourceLane
    requested_evidence_type: str
    reason: str
    cycle_number: int
    status: str
    crisis_id: str
    run_id: str
    keyframe_id: str
    trace_id: str


class AgentRun(Record):
    agent_run_id: str
    agent_name: str
    stage: str
    model_provider: str
    model_id: str
    region: str
    config_version: str
    started_at: str
    completed_at: str
    latency_ms: int = 0
    input_valid: bool
    output_valid: bool
    retry_count: int
    token_input: int = 0
    token_output: int = 0
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    crisis_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    keyframe_id: str = Field(min_length=1)
    trace_id: str = Field(min_length=1)


class PriorityDecision(Record):
    harm_score: float
    priority: int
    route: str
    support: float


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
