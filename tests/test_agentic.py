from __future__ import annotations

import pytest
from pydantic import ValidationError

from crisis_os import config
from crisis_os.agentic import (
    AGENT_ROSTER,
    CheckStatus,
    Incident,
    StateConflict,
    ToolGateway,
    append_unique,
    build_verification,
    calculate_priority,
    cluster_claims,
    evidence_freshness,
    dispatch_status,
    next_feedback_cycle,
    review_round_allowed,
    replay_projection,
    route_candidate_conflicts,
)
from crisis_os.config import ConfigError, RuntimeConfig, validate_runtime_config
from crisis_os.db import get_db, reset_db
from crisis_os.graph import build_graph, graph_topology, run_replay, run_replay_sequence
from crisis_os.models import AgentRun, EvidenceEnvelope, HumanDecision, Observation, Summary, Verdict, WorkItem


def test_roster_and_topology_have_exactly_fifteen_agents():
    expected = {
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
    }
    assert set(AGENT_ROSTER) == expected
    assert len(AGENT_ROSTER) == 15
    topology = graph_topology()
    assert topology["ingest"] == [
        "SatelliteSourceAgent",
        "TelemetrySourceAgent",
        "FieldReportSourceAgent",
        "CommunityReportSourceAgent",
    ]
    assert topology["join"] == [
        "DispatchResourcePlanningAgent",
        "OrchestratorAgent",
        "SummariserAgent",
    ]
    for lane in ("satellite", "telemetry", "field_report", "community"):
        assert topology["source_to_verification"][lane].endswith("VerificationAgent")
        assert topology["verification_to_evaluation"][lane].endswith("EvaluationAgent")
    compiled_nodes = set(build_graph().get_graph().nodes)
    assert set(AGENT_ROSTER) <= compiled_nodes


def test_append_unique_is_ordered_and_detects_conflicting_ids():
    assert append_unique([{"claim_id": "a", "v": 1}], [{"claim_id": "b", "v": 2}]) == [
        {"claim_id": "a", "v": 1},
        {"claim_id": "b", "v": 2},
    ]
    assert append_unique([{"claim_id": "a", "v": 1}], [{"claim_id": "a", "v": 1}]) == [
        {"claim_id": "a", "v": 1}
    ]
    with pytest.raises(StateConflict):
        append_unique([{"claim_id": "a", "v": 1}], [{"claim_id": "a", "v": 2}])


@pytest.mark.parametrize(
    ("statuses", "verdict", "support"),
    [
        ([CheckStatus.PASS] * 5, "PASS", 1.0),
        ([CheckStatus.PASS] * 3 + [CheckStatus.UNKNOWN] * 2, "UNKNOWN", 0.8),
        ([CheckStatus.PASS, CheckStatus.UNKNOWN, CheckStatus.UNKNOWN, CheckStatus.FAIL, CheckStatus.FAIL], "FAIL", 0.4),
        ([CheckStatus.FAIL] * 5, "FAIL", 0.0),
    ],
)
def test_five_check_verification_has_separate_verdict_and_support(statuses, verdict, support):
    result = build_verification(
        claim_id="claim-1",
        evidence_refs=["e-1"],
        checks=dict(zip(("provenance", "schema", "time_location", "consistency", "corroboration"), statuses)),
    )
    assert result.verdict == verdict
    assert result.support == support
    assert result.pass_count == sum(s == CheckStatus.PASS for s in statuses)


def test_priority_policy_handles_life_risk_and_unverified_queue():
    urgent = calculate_priority(0.8, 0.4, 0.2, 0.8, 0.2, "PASS", False)
    assert urgent.priority >= 90
    assert urgent.route == "URGENT_HUMAN_REVIEW"

    evidence = calculate_priority(0.4, 0.4, 0.4, 0.4, 0.2, "UNKNOWN", False)
    assert evidence.route == "REQUEST_EVIDENCE"
    assert evidence.priority < 90

    candidate = calculate_priority(0.9, 0.9, 0.9, 0.6, 0.9, "PASS", False)
    assert candidate.route == "DISPATCH_CANDIDATE"


def test_contradictory_high_risk_incident_requests_evidence_before_dispatch():
    result = calculate_priority(0.9, 0.2, 0.2, 0.9, 0.8, "PASS", True)
    assert result.route == "REQUEST_EVIDENCE"


def test_life_risk_floor_lifts_priority_to_urgent_review():
    result = calculate_priority(0.70, 0.0, 0.0, 0.70, 0.0, "FAIL", False)
    assert result.priority >= 90
    assert result.route == "URGENT_HUMAN_REVIEW"


def test_agent_run_requires_correlation_ids():
    with pytest.raises(ValidationError):
        AgentRun(
            agent_run_id="agent-run-1",
            agent_name="OrchestratorAgent",
            stage="orchestrator",
            model_provider="local",
            model_id="demo",
            region="us-east-1",
            config_version="v1",
            started_at="2005-08-29T12:00:00-05:00",
            completed_at="2005-08-29T12:00:00-05:00",
            input_valid=True,
            output_valid=True,
            retry_count=0,
        )


def test_claims_inside_tolerances_merge_and_preserve_history():
    claims = [
        {
            "claim_id": "c-1",
            "event_type": "bridge_damage",
            "subject": "bridge:B7",
                "location": {"lon": -89.82486, "lat": 30.18264},
                "observed_at": "2005-08-29T12:00:00-05:00",
                "claim_text": "bridge damage reported",
                "evidence_refs": ["e-field"],
            "source_lane": "field_report",
        },
        {
            "claim_id": "c-2",
            "event_type": "bridge_damage",
            "subject": "bridge:B7",
                "location": {"lon": -89.82500, "lat": 30.18270},
                "observed_at": "2005-08-29T15:00:00-05:00",
                "claim_text": "bridge damage corroborated",
                "evidence_refs": ["e-community"],
            "source_lane": "community",
        },
    ]
    incidents = cluster_claims(claims)
    assert len(incidents) == 1
    assert incidents[0].claim_refs == ["c-1", "c-2"]
    assert incidents[0].evidence_refs == ["e-field", "e-community"]
    assert incidents[0].merge_history[0]["merged_claim_id"] == "c-2"


def test_event_specific_clustering_overrides_default_policy_without_mutating_defaults():
    claims = [
        {
            "claim_id": "c-1",
            "event_type": "bridge_damage",
            "subject": "bridge:B7",
            "location": {"lon": -89.82486, "lat": 30.18264},
            "observed_at": "2005-08-29T12:00:00-05:00",
            "claim_text": "bridge damage reported",
            "evidence_refs": ["e-1"],
            "source_lane": "field_report",
        },
        {
            "claim_id": "c-2",
            "event_type": "bridge_damage",
            "subject": "bridge:B7",
            "location": {"lon": -89.80986, "lat": 30.18264},
            "observed_at": "2005-08-29T19:00:00-05:00",
            "claim_text": "bridge damage corroborated",
            "evidence_refs": ["e-2"],
            "source_lane": "community",
        },
    ]
    assert len(cluster_claims(claims)) == 2
    merged = cluster_claims(
        claims,
        policy={"bridge_damage": {"radius_km": 2.0, "temporal_window_hours": 8.0}},
    )
    assert len(merged) == 1
    assert merged[0].claim_refs == ["c-1", "c-2"]
    assert merged[0].merge_history[0]["merged_claim_id"] == "c-2"


def test_freshness_policy_is_timezone_aware_and_accepts_event_overrides():
    exactly_six_hours_old = evidence_freshness(
        "2005-08-29T06:00:00+00:00",
        "2005-08-29T12:00:00+00:00",
    )
    just_over_six_hours_old = evidence_freshness(
        "2005-08-29T05:59:59+00:00",
        "2005-08-29T12:00:00+00:00",
    )
    widened = evidence_freshness(
        "2005-08-29T04:00:00+00:00",
        "2005-08-29T12:00:00+00:00",
        event_type="bridge_damage",
        policy={"bridge_damage": {"window_hours": 9.0}},
    )
    assert exactly_six_hours_old == 1.0
    assert just_over_six_hours_old == 0.0
    assert widened == 1.0


def test_route_candidate_conflicts_surface_blocked_world_model_routes():
    assert route_candidate_conflicts("route:R14", "b7")
    assert route_candidate_conflicts("route:R22", "b7") == []


def test_physical_dispatch_requires_coordinator_decision():
    incident = Incident(
        incident_id="incident-1",
        deduplication_id="dedupe-1",
        claim_refs=["c-1"],
        evidence_refs=["e-1"],
        event_type="road_blocked",
        lifecycle_status="OPEN",
        priority=91,
        confidence=0.9,
        route="DISPATCH_CANDIDATE",
        verification_verdict=Verdict.PASS,
    )
    assert dispatch_status(incident, None) == "REVIEW_REQUIRED"
    decision = HumanDecision(
        actor="Coordinator Diaz",
        role="coordinator",
        action="approve",
        reason="verified route and need",
        incident_id=incident.incident_id,
        proposal_id="work-physical-incident-1",
        proposal_version=1,
    )
    assert dispatch_status(
        incident, decision, "work-physical-incident-1", 1
    ) == "DISPATCHED"
    assert dispatch_status(
        incident, decision, "work-physical-incident-incident-2", 1
    ) == "REVIEW_REQUIRED"
    assert dispatch_status(
        incident, decision, "work-physical-incident-1", 2
    ) == "REVIEW_REQUIRED"
    assert dispatch_status(
        incident,
        HumanDecision(
            actor="Coordinator Diaz",
            role="coordinator",
            action="approve",
            reason="unbound",
        ),
        "work-physical-incident-1",
        1,
    ) == "REVIEW_REQUIRED"
    assert dispatch_status(incident, HumanDecision(
        actor="x", role="observer", action="approve", reason="ok",
    ), "work-physical-incident-1", 1) == "REVIEW_REQUIRED"


def test_human_decisions_are_immutable_and_bound_to_proposal_version():
    decision = HumanDecision(
        actor="Coordinator Diaz",
        role="coordinator",
        action="approve",
        reason="verified route and need",
        incident_id="incident-1",
        proposal_id="proposal-1",
        proposal_version=1,
    )
    with pytest.raises((TypeError, ValidationError)):
        decision.reason = "changed"
    incident = Incident(
        incident_id="incident-1",
        deduplication_id="dedupe-1",
        claim_refs=["c-1"],
        evidence_refs=["e-1"],
        event_type="road_blocked",
        lifecycle_status="OPEN",
        priority=91,
        confidence=0.9,
        route="DISPATCH_CANDIDATE",
        verification_verdict=Verdict.PASS,
    )
    assert dispatch_status(incident, decision, "proposal-1", 1) == "DISPATCHED"
    assert dispatch_status(incident, decision, "proposal-1", 2) == "REVIEW_REQUIRED"


def test_tool_gateway_validates_arguments_and_audits_denials():
    gateway = ToolGateway("OrchestratorAgent", "2005-08-29T12:00:00-05:00")
    gateway.call("checkpoint.write", {"run_id": "run-1"})
    with pytest.raises(PermissionError):
        gateway.call("checkpoint.write", {"run_id": "run-1", "sql": "DROP TABLE audit"})
    with pytest.raises(PermissionError):
        gateway.call("not-allowlisted", {})
    assert gateway.calls[0]["status"] == "ALLOWED"
    assert [call["status"] for call in gateway.calls[1:]] == ["DENIED", "DENIED"]
    assert all(call["reason"] for call in gateway.calls[1:])


def test_models_reject_raw_reporters_verdict_metadata_and_unproven_facts():
    with pytest.raises(ValidationError):
        EvidenceEnvelope(
            evidence_id="e-1",
            source_type="community",
            source_ref="community://sms/1",
            captured_at="2005-08-29T12:00:00-05:00",
            observed_at="2005-08-29T12:00:00-05:00",
            artifact_ref="replay://e-1",
            content_hash="a" * 64,
            adapter_version="v1",
            reporter_id="raw-reporter",
        )
    with pytest.raises(ValidationError):
        Observation(
            observation_id="o-1",
            evidence_refs=["e-1"],
            description="reported",
            source_lane="community",
            observed_at="2005-08-29T12:00:00-05:00",
            extraction_metadata={"nested": {"verification_verdict": "PASS"}},
        )
    with pytest.raises(ValidationError):
        Summary(
            summary_id="s-1",
            incident_id="i-1",
            generated_at="2005-08-29T12:00:00-05:00",
            headline="fact",
            location=None,
            status="OPEN",
            priority=1,
            confidence=0.5,
            known_facts=[{"fact": "unsupported"}],
            uncertainties=[],
            actions=[],
            contradictions=[],
            next_update_at="2005-08-29T12:00:00-05:00",
            summary_version="v1",
            crisis_id="c-1",
            run_id="r-1",
            keyframe_id="t0",
            trace_id="t-1",
        )
    WorkItem(
        work_item_id="w-1",
        incident_id="i-1",
        kind="physical_dispatch",
        owner="coordinator",
        status="PROPOSED",
    )


def test_review_and_feedback_limits_are_hard_bounded():
    assert [next_feedback_cycle(i) for i in range(4)] == [1, 2, 3, None]
    assert [review_round_allowed(i) for i in range(4)] == [True, True, True, False]


def test_runtime_configuration_rejects_disallowed_model_and_region():
    config = RuntimeConfig("bedrock", "good", "eu-west-1", 30, 1, ("good",), ("us-east-1",))
    with pytest.raises(ConfigError):
        validate_runtime_config(config)


def test_replay_persists_audit_and_native_checkpoint_records():
    reset_db()
    result = run_replay("b7")
    conn = get_db()
    assert result["agent_runs"]
    assert conn.execute("SELECT COUNT(*) FROM checkpoints").fetchone()[0] > 0
    actions = {row["action"] for row in conn.execute("SELECT action FROM audit")}
    assert {"agent.completed", "incident.merge", "summary.generated", "checkpoint.write"} <= actions


def test_replay_projection_is_additive_and_keeps_provenance():
    for keyframe in ("t0", "b7", "reroute"):
        result = run_replay(keyframe)
        projected = replay_projection(result)
        assert projected["keyframe_id"] == keyframe
        assert projected["schema_version"] == "1.0"
        assert "entities" in projected and "population" in projected
        agentic = projected["agentic"]
        assert agentic["verified_incidents"] or agentic["unverified_incidents"]
        assert {run.agent_name for run in result["agent_runs"]} == set(AGENT_ROSTER)
        for item in agentic["verified_incidents"] + agentic["unverified_incidents"]:
            assert item["evidence_refs"] or item["uncertainties"]


def test_failed_lane_degrades_without_erasing_other_lanes():
    result = run_replay("b7", failures={"TelemetrySourceAgent"})
    statuses = {row.lane_id: row.status for row in result["lane_results"]}
    assert statuses["telemetry"] == "DEGRADED"
    assert statuses["satellite"] == "SUCCEEDED"
    assert statuses["field_report"] == "SUCCEEDED"
    assert statuses["community"] == "SUCCEEDED"
    assert result["agent_errors"]
    assert result["incidents"]


@pytest.mark.parametrize(
    ("agent", "status"),
    [
        ("DispatchResourcePlanningAgent", "planning_degraded"),
        ("OrchestratorAgent", "orchestration_degraded"),
        ("SummariserAgent", "summarisation_degraded"),
    ],
)
def test_join_stage_failures_have_documented_degraded_behavior(agent, status):
    result = run_replay("b7", failures={agent}, use_langgraph=False)
    assert result[status] is True
    assert result["agent_errors"]
    if agent == "DispatchResourcePlanningAgent":
        assert result["incident_candidates"]
        assert not result["work_items"]
    if agent == "OrchestratorAgent":
        assert not result["incidents"]
    if agent == "SummariserAgent":
        assert result["summaries"]
        assert all(summary.degraded for summary in result["summaries"])


def test_replaying_same_keyframe_does_not_duplicate_exact_audit_events():
    reset_db()
    run_replay("b7", use_langgraph=False)
    conn = get_db()
    first = conn.execute("SELECT COUNT(*) FROM audit").fetchone()[0]
    run_replay("b7", use_langgraph=False)
    second = conn.execute("SELECT COUNT(*) FROM audit").fetchone()[0]
    assert second == first


def test_replay_sequence_rejects_out_of_order_keyframes():
    with pytest.raises(ValueError, match="chronological"):
        run_replay_sequence(["b7", "t0"])


def test_build_graph_validates_runtime_and_tool_manifest_before_compile(monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "local")

    def invalid_runtime():
        raise ConfigError("invalid checked-in runtime")

    monkeypatch.setattr(config, "load_runtime_config", invalid_runtime)
    with pytest.raises(ConfigError, match="invalid checked-in runtime"):
        build_graph()

    monkeypatch.setattr(config, "load_runtime_config", lambda: RuntimeConfig(
        "local", "model", "us-east-1", 1, 1, ("model",), ("us-east-1",)
    ))
    from crisis_os import agentic
    monkeypatch.setitem(agentic.TOOL_ALLOWLIST, "OrchestratorAgent", {"missing.tool"})
    with pytest.raises(ConfigError, match="missing.tool"):
        build_graph()
