"""CrisisIO's 15-agent LangGraph workflow and deterministic replay runner."""
from __future__ import annotations

import hashlib
import json
from typing import Annotated, Any, Callable, Iterable, TypedDict

from pydantic import ValidationError

from .agentic import (
    AGENT_ROSTER,
    LANES,
    LANE_AGENTS,
    MAX_RETRIES,
    ToolGateway,
    append_unique,
    build_verification,
    calculate_priority,
    cluster_claims,
    load_fixtures,
    lane_result_status,
    make_agent_run,
    make_error,
    next_feedback_cycle,
    route_candidate_conflicts,
    replay_projection,
)
from .catalog import ROUTE_PATHS
from . import config
from .models import (
    AgentError,
    AgentRun,
    Claim,
    Evaluation,
    EvidenceEnvelope,
    FeedbackRequest,
    Incident,
    LaneResult,
    LaneStatus,
    Observation,
    Summary,
    VerificationRun,
    Verdict,
    WorkItem,
)


def _reduce(existing: list[Any], incoming: Iterable[Any]) -> list[Any]:
    return append_unique(existing, incoming)


class GraphState(TypedDict, total=False):
    crisis_id: str
    run_id: str
    keyframe_id: str
    trace_id: str
    policy_version: str
    recorded_at: str
    fixture_batch: dict[str, list[dict[str, Any]]]
    failure_plan: dict[str, int] | set[str]
    evidence: Annotated[list[EvidenceEnvelope], _reduce]
    observations: Annotated[list[Observation], _reduce]
    claims: Annotated[list[Claim], _reduce]
    verification_runs: Annotated[list[VerificationRun], _reduce]
    evaluations: Annotated[list[Evaluation], _reduce]
    incidents: Annotated[list[Incident], _reduce]
    work_items: Annotated[list[WorkItem], _reduce]
    summaries: Annotated[list[Summary], _reduce]
    agent_errors: Annotated[list[AgentError], _reduce]
    lane_results: Annotated[list[LaneResult], _reduce]
    feedback_requests: Annotated[list[FeedbackRequest], _reduce]
    agent_runs: Annotated[list[AgentRun], _reduce]
    planning_degraded: bool
    orchestration_degraded: bool
    summarisation_degraded: bool
    incident_candidates: list[Incident]
    projection: dict[str, Any]


def graph_topology() -> dict[str, Any]:
    return {
        "ingest": [LANE_AGENTS[lane][0] for lane in LANES],
        "source_to_verification": {lane: LANE_AGENTS[lane][1] for lane in LANES},
        "verification_to_evaluation": {lane: LANE_AGENTS[lane][2] for lane in LANES},
        "join": ["DispatchResourcePlanningAgent", "OrchestratorAgent", "SummariserAgent"],
        "projection": "WorldSnapshotProjection",
    }


def _validate_startup() -> None:
    config.load_runtime_config()
    try:
        from .agentic import validate_tool_manifest
        validate_tool_manifest()
    except ValueError as exc:
        raise config.ConfigError(str(exc)) from exc


def _correlation(state: GraphState) -> dict[str, str]:
    return {
        "crisis_id": state["crisis_id"],
        "run_id": state["run_id"],
        "keyframe_id": state["keyframe_id"],
        "trace_id": state["trace_id"],
    }


def _planned_failure(state: GraphState, agent_name: str, attempt: int) -> bool:
    plan = state.get("failure_plan", {})
    if isinstance(plan, set):
        return agent_name in plan
    return int(plan.get(agent_name, 0)) >= attempt


def _run_stage(
    state: GraphState,
    agent_name: str,
    stage: str,
    action: Callable[[ToolGateway], Any],
) -> tuple[Any | None, list[AgentRun], list[AgentError], bool]:
    errors: list[AgentError] = []
    runs: list[AgentRun] = []
    attempt_tool_calls: list[dict[str, Any]] = []
    for attempt in range(1, MAX_RETRIES + 2):
        if _planned_failure(state, agent_name, attempt):
            errors.append(make_error(
                agent_name, stage, "planned replay failure",
                attempt=attempt, error_class="TRANSIENT", timestamp=state["recorded_at"],
            ))
            continue
        gateway = ToolGateway(agent_name, state["recorded_at"])
        try:
            value = action(gateway)
            runs.append(make_agent_run(
                agent_name, stage, valid=True, retry_count=attempt - 1,
                tool_calls=gateway.calls, correlation=_correlation(state),
                timestamp=state["recorded_at"],
            ))
            return value, runs, errors, True
        except PermissionError as exc:
            attempt_tool_calls.extend(gateway.calls)
            message = str(exc)
            error_class = "PERMANENT_CONFIG" if any(
                fragment in message for fragment in (
                    "cannot call", "missing arguments", "unknown arguments",
                    "malformed arguments", "no argument schema",
                )
            ) else "PERMANENT_AUTH"
            errors.append(make_error(
                agent_name, stage, str(exc), attempt=attempt,
                error_class=error_class, timestamp=state["recorded_at"],
            ))
            break
        except ValidationError as exc:
            attempt_tool_calls.extend(gateway.calls)
            errors.append(make_error(
                agent_name, stage, str(exc), attempt=attempt,
                error_class="POLICY_REJECTED", timestamp=state["recorded_at"],
            ))
            break
        except (ValueError, TypeError) as exc:
            attempt_tool_calls.extend(gateway.calls)
            errors.append(make_error(
                agent_name, stage, str(exc), attempt=attempt,
                error_class="RECOVERABLE_OUTPUT", timestamp=state["recorded_at"],
            ))
            if attempt >= MAX_RETRIES + 1:
                break
        except Exception as exc:
            attempt_tool_calls.extend(gateway.calls)
            errors.append(make_error(
                agent_name, stage, str(exc), attempt=attempt,
                error_class="TRANSIENT", timestamp=state["recorded_at"],
            ))
    runs.append(make_agent_run(
        agent_name, stage, valid=False, retry_count=MAX_RETRIES,
        tool_calls=attempt_tool_calls,
        correlation=_correlation(state), timestamp=state["recorded_at"],
    ))
    return None, runs, errors, False


def _initial_state(keyframe: str, failures: dict[str, int] | set[str] | None = None) -> GraphState:
    if keyframe not in ("t0", "b7", "reroute"):
        raise ValueError(f"unknown replay keyframe: {keyframe}")
    batch = load_fixtures()[keyframe]
    captured = [row["captured_at"] for lane in LANES for row in batch.get(lane, [])]
    failure_suffix = ""
    if failures:
        failure_suffix = "-fail-" + hashlib.sha256(
            json.dumps(failures, sort_keys=True, default=list).encode("utf-8")
        ).hexdigest()[:8]
    run_id = f"replay-{keyframe}{failure_suffix}"
    return GraphState(
        crisis_id="katrina-nola-2005",
        run_id=run_id,
        keyframe_id=keyframe,
        trace_id=f"trace-katrina-{keyframe}{failure_suffix}",
        policy_version="policy-v1",
        recorded_at=max(captured),
        fixture_batch=batch,
        failure_plan=failures or {},
        evidence=[],
        observations=[],
        claims=[],
        verification_runs=[],
        evaluations=[],
        incidents=[],
        work_items=[],
        summaries=[],
        agent_errors=[],
        lane_results=[],
        feedback_requests=[],
        agent_runs=[],
        planning_degraded=False,
        orchestration_degraded=False,
        summarisation_degraded=False,
    )


def ingest(state: GraphState) -> GraphState:
    if not state.get("fixture_batch"):
        raise ValueError("replay input has no fixture batch")
    return state


def _source_node(state: GraphState, lane: str) -> GraphState:
    agent_name = LANE_AGENTS[lane][0]
    rows = state["fixture_batch"].get(lane, [])

    def action(gateway: ToolGateway) -> tuple[list[EvidenceEnvelope], list[Observation], list[Claim]]:
        gateway.call(f"adapter.{lane}.read_fixture", {"keyframe_id": state["keyframe_id"]})
        evidence, observations, claims = [], [], []
        for row in rows:
            evidence_id = row["evidence_id"]
            text = row["text"]
            evidence.append(EvidenceEnvelope(
                evidence_id=evidence_id,
                source_type=lane,
                source_ref=row["source_ref"],
                captured_at=row["captured_at"],
                observed_at=row["observed_at"],
                geometry=row.get("location"),
                artifact_ref=f"replay://katrina/{state['keyframe_id']}/{evidence_id}",
                content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
                adapter_version="replay-adapter-v1",
                collection_metadata={"keyframe_id": state["keyframe_id"]},
                reporter_id=(
                    hashlib.sha256(row["reporter"].encode("utf-8")).hexdigest()[:16]
                    if row.get("reporter") else None
                ),
            ))
            observations.append(Observation(
                observation_id=f"observation-{evidence_id}",
                evidence_refs=[evidence_id],
                description=text,
                source_lane=lane,
                observed_at=row["observed_at"],
                extraction_metadata={"adapter_version": "replay-adapter-v1"},
            ))
            claims.append(Claim(
                claim_id=f"claim-{evidence_id}",
                event_type=row["event_type"],
                subject=row["subject"],
                location=row.get("location"),
                observed_at=row["observed_at"],
                claim_text=text,
                structured_value=row.get("value", {}),
                evidence_refs=[evidence_id],
                source_lane=lane,
                extraction_metadata={
                    "checks": row["checks"],
                    "scores": row["scores"],
                    "next_step": row["next_step"],
                },
            ))
        return evidence, observations, claims

    result, runs, errors, ok = _run_stage(state, agent_name, "source", action)
    if not ok:
        return {"agent_runs": runs, "agent_errors": errors}
    evidence, observations, claims = result
    return {
        "evidence": evidence,
        "observations": observations,
        "claims": claims,
        "agent_runs": runs,
        "agent_errors": errors,
    }


def _verification_node(state: GraphState, lane: str) -> GraphState:
    agent_name = LANE_AGENTS[lane][1]
    claims = [claim for claim in state.get("claims", []) if claim.source_lane == lane]

    def action(gateway: ToolGateway) -> list[VerificationRun]:
        gateway.call("evidence.get_by_ids", {"count": len(claims)})
        gateway.call("claims.get_by_ids", {"count": len(claims)})
        return [
            build_verification(
                claim.claim_id, claim.evidence_refs, claim.extraction_metadata["checks"],
                crisis_id=state["crisis_id"], run_id=state["run_id"],
                keyframe_id=state["keyframe_id"], trace_id=state["trace_id"],
                agent_run_id=f"agent-run-{agent_name}-verification-{state['keyframe_id']}",
            )
            for claim in claims
        ]

    result, runs, errors, _ = _run_stage(state, agent_name, "verification", action)
    return {"verification_runs": result or [], "agent_runs": runs, "agent_errors": errors}


def _evaluation_node(state: GraphState, lane: str) -> GraphState:
    agent_name = LANE_AGENTS[lane][2]
    claims = [claim for claim in state.get("claims", []) if claim.source_lane == lane]
    verifications = {row.claim_id: row for row in state.get("verification_runs", [])}

    def action(gateway: ToolGateway) -> list[Evaluation]:
        gateway.call("evidence.get_by_ids", {"count": len(claims)})
        gateway.call("claims.get_by_ids", {"count": len(claims)})
        gateway.call("policy.get_version", {"policy_version": state["policy_version"]})
        result = []
        for claim in claims:
            if claim.claim_id not in verifications:
                continue
            scores = claim.extraction_metadata["scores"]
            result.append(Evaluation(
                evaluation_id=f"evaluation-{claim.claim_id}",
                claim_id=claim.claim_id,
                **scores,
                total_score=sum(scores[key] for key in (
                    "relevance", "actionability", "freshness", "impact", "coverage_novelty",
                )),
                recommended_next_step=claim.extraction_metadata["next_step"],
                missing_information=(
                    ["independent corroboration"]
                    if verifications[claim.claim_id].verdict is not Verdict.PASS else []
                ),
                evidence_refs=claim.evidence_refs,
                rubric_version=f"{lane}-rubric-v1",
            ))
        return result

    result, runs, errors, ok = _run_stage(state, agent_name, "evaluation", action)
    prior_errors = [
        error for error in state.get("agent_errors", [])
        if error.agent_name in LANE_AGENTS[lane]
    ]
    lane_errors = prior_errors + errors
    refs = [claim.claim_id for claim in claims]
    refs += [row.verification_id for row in state.get("verification_runs", []) if row.claim_id in refs]
    refs += [row.evaluation_id for row in (result or [])]
    return {
        "evaluations": result or [],
        "lane_results": [LaneResult(
            lane_result_id=f"lane-result-{state['run_id']}-{lane}",
            lane_id=lane,
            status=lane_result_status(ok, lane_errors),
            output_refs=refs,
            error_refs=[error.error_id for error in lane_errors],
            completed_at=state["recorded_at"],
            **_correlation(state),
        )],
        "agent_runs": runs,
        "agent_errors": errors,
    }


def _priority_for_incident(
    incident: Incident,
    claims: list[Claim],
    verifications: dict[str, VerificationRun],
    evaluations: dict[str, Evaluation],
) -> Incident:
    related = [claim for claim in claims if claim.claim_id in incident.claim_refs]
    related_evals = [evaluations[claim.claim_id] for claim in related if claim.claim_id in evaluations]
    related_verifications = [
        verifications[claim.claim_id] for claim in related if claim.claim_id in verifications
    ]
    if not related_evals:
        return incident.model_copy(update={
            "route": "REQUEST_EVIDENCE",
            "next_step": "REQUEST_EVIDENCE",
        })
    evaluation = max(related_evals, key=lambda row: (row.total_score, row.claim_id))
    verdict = (
        Verdict.PASS
        if related_verifications and all(row.verdict is Verdict.PASS for row in related_verifications)
        else Verdict.UNKNOWN
    )
    support = min((row.support for row in related_verifications), default=0.0)
    decision = calculate_priority(
        evaluation.loss_of_life_risk, evaluation.damage_severity,
        evaluation.service_criticality, evaluation.time_criticality,
        support, verdict, bool(incident.contradictions),
    )
    return incident.model_copy(update={
        "priority": decision.priority,
        "confidence": support,
        "route": decision.route,
        "verification_verdict": verdict,
        "next_step": evaluation.recommended_next_step,
    })


def _dispatch_node(state: GraphState) -> GraphState:
    claims = state.get("claims", [])
    incidents = cluster_claims(claims)
    verifications = {row.claim_id: row for row in state.get("verification_runs", [])}
    evaluations = {row.claim_id: row for row in state.get("evaluations", [])}
    incidents = [
        _priority_for_incident(incident, claims, verifications, evaluations)
        for incident in incidents
    ]
    def action(gateway: ToolGateway) -> list[WorkItem]:
        gateway.call("world.routes.read", {"route_count": len(ROUTE_PATHS)})
        gateway.call("world.resources.read", {"resource_ids": ["truck:17", "warehouse:W1"]})
        work_items: list[WorkItem] = []
        for incident in incidents:
            if incident.route in ("DISPATCH_CANDIDATE", "URGENT_HUMAN_REVIEW"):
                route = "route:R22" if incident.subject in ("bridge:B7", "route:R22") else "route:R14"
                conflicts = route_candidate_conflicts(route, state["keyframe_id"])
                work_items.extend((
                    WorkItem(
                        work_item_id=f"work-route-{incident.incident_id}",
                        incident_id=incident.incident_id,
                        kind="candidate_route",
                        owner="dispatch",
                        status="CONFLICTED" if conflicts else "SUGGESTED",
                        assumptions=["route remains open until coordinator review"],
                        capacity={"route": route, "path_points": len(ROUTE_PATHS[route])},
                        conflicts=conflicts,
                        evidence_refs=incident.evidence_refs,
                    ),
                    WorkItem(
                        work_item_id=f"work-physical-{incident.incident_id}",
                        incident_id=incident.incident_id,
                        kind="physical_dispatch",
                        owner="coordinator",
                        status="PROPOSED",
                        assumptions=["no physical action without authenticated coordinator decision"],
                        capacity={"route": route, "resource": "truck:17"},
                        conflicts=conflicts,
                        evidence_refs=incident.evidence_refs,
                        requires_coordinator_approval=True,
                    ),
                ))
            elif incident.route == "REQUEST_EVIDENCE":
                work_items.append(WorkItem(
                    work_item_id=f"work-evidence-{incident.incident_id}",
                    incident_id=incident.incident_id,
                    kind="evidence_request",
                    owner="orchestrator",
                    status="OPEN",
                    assumptions=["retain incident in unverified queue"],
                    evidence_refs=incident.evidence_refs,
                ))
            else:
                work_items.append(WorkItem(
                    work_item_id=f"work-monitor-{incident.incident_id}",
                    incident_id=incident.incident_id,
                    kind="monitoring",
                    owner="orchestrator",
                    status="OPEN",
                    evidence_refs=incident.evidence_refs,
                ))
        return work_items

    work_items, runs, errors, ok = _run_stage(
        state, "DispatchResourcePlanningAgent", "dispatch", action
    )
    return {
        "incident_candidates": incidents,
        "work_items": work_items or [],
        "planning_degraded": not ok,
        "agent_runs": runs,
        "agent_errors": errors,
    }


def _orchestrator_node(state: GraphState) -> GraphState:
    def action(gateway: ToolGateway) -> tuple[list[Incident], list[FeedbackRequest], list[WorkItem]]:
        incidents, feedback, work_items = [], [], []
        for candidate in state.get("incident_candidates", []):
            lifecycle = "NEEDS_EVIDENCE" if candidate.route == "REQUEST_EVIDENCE" else "MONITORING"
            incident = candidate.model_copy(update={
                "lifecycle_status": lifecycle,
                "updated_at": state["recorded_at"],
            })
            incidents.append(incident)
            if incident.route == "REQUEST_EVIDENCE":
                cycle = next_feedback_cycle(0)
                lane = next(
                    (claim.source_lane for claim in state.get("claims", []) if claim.claim_id in incident.claim_refs),
                    "field_report",
                )
                if cycle is not None:
                    feedback.append(FeedbackRequest(
                        feedback_request_id=f"feedback-{state['run_id']}-{incident.incident_id}",
                        incident_id=incident.incident_id,
                        target_source_lane=lane,
                        requested_evidence_type="independent corroboration",
                        reason="claim is not sufficiently supported for promotion",
                        cycle_number=cycle,
                        status="OPEN",
                        **_correlation(state),
                    ))
        for lane_result in state.get("lane_results", []):
            if lane_result.status is LaneStatus.DEGRADED:
                work_items.append(WorkItem(
                    work_item_id=f"work-lane-evidence-{state['run_id']}-{lane_result.lane_id}",
                    incident_id=f"run:{state['run_id']}",
                    kind="evidence_request",
                    owner=lane_result.lane_id,
                    status="OPEN",
                    assumptions=["lane failure preserved; no unsupported claim was emitted"],
                ))
        gateway.call("state.read_current", {"incident_count": len(incidents)})
        gateway.call("checkpoint.write", {"run_id": state["run_id"]})
        return incidents, feedback, work_items

    result, runs, errors, ok = _run_stage(
        state, "OrchestratorAgent", "orchestrator", action
    )
    incidents, feedback, work_items = result or ([], [], [])
    return {
        "incidents": incidents,
        "feedback_requests": feedback,
        "work_items": work_items,
        "orchestration_degraded": not ok,
        "agent_runs": runs,
        "agent_errors": errors,
    }


def _summariser_node(state: GraphState) -> GraphState:
    items_by_incident: dict[str, list[WorkItem]] = {}
    for item in state.get("work_items", []):
        items_by_incident.setdefault(item.incident_id, []).append(item)
    def build_summaries(degraded: bool) -> list[Summary]:
        summaries = []
        for incident in state.get("incidents", []):
            uncertain = []
            if incident.verification_verdict is not Verdict.PASS:
                uncertain.append("verification is not PASS")
            if incident.contradictions:
                uncertain.append("contradictory evidence is retained")
            summaries.append(Summary(
                summary_id=f"summary-{incident.incident_id}",
                incident_id=incident.incident_id,
                generated_at=state["recorded_at"],
                headline=f"{incident.event_type} reported at {incident.subject}",
                location=incident.location,
                status=incident.lifecycle_status,
                priority=incident.priority,
                confidence=incident.confidence,
                known_facts=[{
                    "fact": f"{incident.event_type} at {incident.subject}",
                    "evidence_refs": incident.evidence_refs,
                }],
                uncertainties=uncertain,
                actions=[
                    {"work_item_id": item.work_item_id, "owner": item.owner, "status": item.status}
                    for item in items_by_incident.get(incident.incident_id, [])
                ],
                contradictions=incident.contradictions,
                next_update_at=state["recorded_at"],
                summary_version="summary-v1",
                degraded=degraded,
                **_correlation(state),
            ))
        return summaries

    def action(gateway: ToolGateway) -> list[Summary]:
        gateway.call("incidents.read", {"incident_count": len(state.get("incidents", []))})
        gateway.call("work_items.read", {"work_item_count": len(state.get("work_items", []))})
        summaries = build_summaries(False)
        gateway.call("summary.append", {"summary_count": len(summaries)})
        return summaries

    result, runs, errors, ok = _run_stage(
        state, "SummariserAgent", "summariser", action
    )
    summaries = result if ok else build_summaries(True)
    return {
        "summaries": summaries,
        "summarisation_degraded": not ok,
        "agent_runs": runs,
        "agent_errors": errors,
    }


def _projection_node(state: GraphState) -> GraphState:
    return {"projection": replay_projection(state)}


def _node_for(agent_name: str) -> Callable[[GraphState], GraphState]:
    if agent_name.endswith("SourceAgent"):
        lane = next(lane for lane in LANES if LANE_AGENTS[lane][0] == agent_name)
        return lambda state: _source_node(state, lane)
    if agent_name.endswith("VerificationAgent"):
        lane = next(lane for lane in LANES if LANE_AGENTS[lane][1] == agent_name)
        return lambda state: _verification_node(state, lane)
    if agent_name.endswith("EvaluationAgent"):
        lane = next(lane for lane in LANES if LANE_AGENTS[lane][2] == agent_name)
        return lambda state: _evaluation_node(state, lane)
    return {
        "DispatchResourcePlanningAgent": _dispatch_node,
        "OrchestratorAgent": _orchestrator_node,
        "SummariserAgent": _summariser_node,
    }[agent_name]


def build_graph(checkpointer: Any = None) -> Any:
    """Compile the required LangGraph topology, or return None if absent."""
    _validate_startup()
    try:
        from langgraph.graph import END, START, StateGraph
    except ImportError:
        return None

    builder = StateGraph(GraphState)
    builder.add_node("ingest", ingest)
    builder.add_node("source_join", lambda state: {})
    builder.add_node("verification_join", lambda state: {})
    builder.add_node("evaluation_join", lambda state: {})
    for agent_name in AGENT_ROSTER:
        builder.add_node(agent_name, _node_for(agent_name))
    builder.add_node("WorldSnapshotProjection", _projection_node)
    builder.add_edge(START, "ingest")
    source_agents = []
    verification_agents = []
    evaluation_agents = []
    for lane in LANES:
        source, verification, evaluation = LANE_AGENTS[lane]
        source_agents.append(source)
        verification_agents.append(verification)
        evaluation_agents.append(evaluation)
        builder.add_edge("ingest", source)
    builder.add_edge(source_agents, "source_join")
    for verification in verification_agents:
        builder.add_edge("source_join", verification)
    builder.add_edge(verification_agents, "verification_join")
    for evaluation in evaluation_agents:
        builder.add_edge("verification_join", evaluation)
    builder.add_edge(evaluation_agents, "evaluation_join")
    builder.add_edge("evaluation_join", "DispatchResourcePlanningAgent")
    builder.add_edge("DispatchResourcePlanningAgent", "OrchestratorAgent")
    builder.add_edge("OrchestratorAgent", "SummariserAgent")
    builder.add_edge("SummariserAgent", "WorldSnapshotProjection")
    builder.add_edge("WorldSnapshotProjection", END)
    return builder.compile(checkpointer=checkpointer)


def _merge_state(state: GraphState, update: GraphState) -> GraphState:
    merged = dict(state)
    list_fields = (
        "evidence", "observations", "claims", "verification_runs", "evaluations",
        "incidents", "work_items", "summaries", "agent_errors", "lane_results",
        "feedback_requests", "agent_runs",
    )
    for field in list_fields:
        if field in update:
            merged[field] = append_unique(merged.get(field, []), update[field])
    for key, value in update.items():
        if key not in list_fields:
            merged[key] = value
    return GraphState(**merged)


def _run_sequential(state: GraphState) -> GraphState:
    state = _merge_state(state, ingest(state))
    for lane in LANES:
        state = _merge_state(state, _source_node(state, lane))
    for lane in LANES:
        state = _merge_state(state, _verification_node(state, lane))
    for lane in LANES:
        state = _merge_state(state, _evaluation_node(state, lane))
    for node in (_dispatch_node, _orchestrator_node, _summariser_node, _projection_node):
        state = _merge_state(state, node(state))
    return state


def run_replay(
    keyframe: str,
    *,
    failures: dict[str, int] | set[str] | None = None,
    use_langgraph: bool = True,
) -> GraphState:
    state = _initial_state(keyframe, failures)
    checkpointer = None
    if use_langgraph:
        _validate_startup()
        try:
            from .db import langgraph_checkpointer
            checkpointer = langgraph_checkpointer()
        except ImportError:
            pass
    graph = build_graph(checkpointer) if use_langgraph else None
    if graph is None:
        result = _run_sequential(state)
    else:
        result = GraphState(**graph.invoke(
            state,
            config={"recursion_limit": 40, "configurable": {"thread_id": state["run_id"]}},
        ))
    from .db import persist_agent_state
    persist_agent_state(result)
    return result


def run_replay_sequence(
    keyframes: Iterable[str],
    *,
    failures: dict[str, int] | set[str] | None = None,
    use_langgraph: bool = True,
) -> dict[str, dict[str, Any]]:
    order = {"t0": 0, "b7": 1, "reroute": 2}
    sequence = list(keyframes)
    if sequence != sorted(sequence, key=order.__getitem__):
        raise ValueError("keyframes must be in chronological order")
    return {
        keyframe: replay_projection(
            run_replay(keyframe, failures=failures, use_langgraph=use_langgraph)
        )
        for keyframe in sequence
    }


def run_all_replay() -> dict[str, dict[str, Any]]:
    return run_replay_sequence(("t0", "b7", "reroute"))
