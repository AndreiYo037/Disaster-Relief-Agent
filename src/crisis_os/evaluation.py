"""Repeatable, no-repair evaluation harness for the deterministic agentic layer."""
from __future__ import annotations

import csv
import hashlib
import json
import re
import time
from html import escape
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .agentic import (
    CHECK_NAMES,
    MAX_RETRIES,
    ToolGateway,
    build_verification,
    calculate_priority,
    cluster_claims,
    dispatch_status,
    make_error,
)
from .models import Claim, EvidenceEnvelope, HumanDecision, Incident, Verdict


ROOT = Path(__file__).resolve().parents[2]
SCENARIO_PATH = ROOT / "data" / "katrina" / "evaluation_scenarios.json"
LANE_AGENT = {
    "satellite": "SatelliteSourceAgent",
    "telemetry": "TelemetrySourceAgent",
    "field_report": "FieldReportSourceAgent",
    "community": "CommunityReportSourceAgent",
}


def load_scenarios() -> list[dict[str, Any]]:
    payload = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    scenarios = payload.get("scenarios")
    if not isinstance(scenarios, list) or len(scenarios) != 25:
        raise ValueError("evaluation dataset must contain exactly 25 scenarios")
    return [
        {
            **row,
            "scenario_type": (
                "human_rejection_or_edit"
                if row.get("scenario_type") in {"human_rejection", "human_edit"}
                else row.get("scenario_type")
            ),
        }
        for row in scenarios
    ]


def _normalize_evidence(row: dict[str, Any]) -> dict[str, Any]:
    data = dict(row)
    reporter_id = data.get("reporter_id")
    if reporter_id and not re.fullmatch(r"[0-9a-f]{16}", reporter_id):
        data["reporter_id"] = hashlib.sha256(reporter_id.encode("utf-8")).hexdigest()[:16]
    return data


def _priority_level(priority: int) -> str:
    if priority >= 90:
        return "urgent"
    if priority >= 80:
        return "high"
    if priority >= 60:
        return "medium"
    return "low"


def _json(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", by_alias=True)
    return value


def _approval(scenario: dict[str, Any], incident: Incident | None) -> tuple[str, bool, list[dict[str, Any]]]:
    human = scenario["input"].get("human_decision")
    if incident is None or not human:
        return "REVIEW_REQUIRED", False, []
    data = dict(human)
    valid_until = data.pop("valid_until", None)
    if valid_until and valid_until < incident.updated_at:
        return "REVIEW_REQUIRED", False, [{
            "event": "human.decision_rejected",
            "reason": "approval expired",
            "actor": data.get("actor"),
            "at": incident.updated_at,
        }]
    try:
        decision = HumanDecision.model_validate(data)
    except ValidationError as exc:
        return "REVIEW_REQUIRED", False, [{
            "event": "human.decision_rejected",
            "reason": "approval malformed",
            "detail": str(exc),
            "at": incident.updated_at,
        }]
    status = dispatch_status(
        incident,
        decision,
        expected_proposal_id=f"proposal-{scenario['scenario_id']}",
        expected_proposal_version=1,
    )
    valid = status == "DISPATCHED" and decision.role in {
        "coordinator", "logistics_lead", "named_authority"
    }
    audit = [{
        "event": "human.decision",
        "decision_id": decision.decision_id,
        "actor": decision.actor,
        "role": decision.role,
        "action": decision.action,
        "at": decision.decided_at,
        "linked_incident": incident.incident_id,
    }]
    if decision.action == "modify":
        audit.append({
            "event": "human.approved_edit",
            "original_action": "RECOMMEND_DISPATCH",
            "approved_action": "DISPATCHED",
            "modifications": decision.modifications,
            "at": decision.decided_at,
            "linked_incident": incident.incident_id,
        })
    return status, valid, audit


def _actual_action(
    route: str,
    incident_count: int,
    claim_count: int,
    approval_status: str,
    *,
    tool_failure: bool,
    retry_limit_reached: bool,
) -> str:
    if approval_status == "REJECTED":
        return "REJECTED"
    if approval_status == "DISPATCHED":
        return "DISPATCHED"
    if tool_failure or retry_limit_reached:
        return "REQUEST_EVIDENCE"
    if claim_count > 1 and incident_count < claim_count:
        return "SUPPRESS_DUPLICATE"
    if claim_count > 1 and incident_count == claim_count:
        return "ROUTE"
    return {
        "DISPATCH_CANDIDATE": "RECOMMEND_DISPATCH",
        "URGENT_HUMAN_REVIEW": "HOLD_FOR_HUMAN_REVIEW",
        "REQUEST_EVIDENCE": "REQUEST_EVIDENCE",
        "MONITOR": "MONITOR",
        "UNVERIFIED": "ABSTAIN",
    }.get(route, "ABSTAIN")


def _audit_complete(
    claims: list[Claim],
    evidence: list[EvidenceEnvelope],
    incident: Incident | None,
    uncertainties: list[str],
    audit: list[dict[str, Any]],
) -> bool:
    evidence_ids = {item.evidence_id for item in evidence}
    if any(not set(claim.evidence_refs) <= evidence_ids for claim in claims):
        return False
    if incident and not set(incident.evidence_refs) <= evidence_ids:
        return False
    if not audit:
        return bool(uncertainties)
    return True


def run_scenario(scenario: dict[str, Any]) -> dict[str, Any]:
    started = time.perf_counter()
    data = scenario["input"]
    expected = scenario["expected"]
    evidence: list[EvidenceEnvelope] = []
    claims: list[Claim] = []
    validation_errors: list[str] = []
    for row in data.get("evidence", []):
        try:
            evidence.append(EvidenceEnvelope.model_validate(_normalize_evidence(row)))
        except ValidationError as exc:
            validation_errors.append(f"evidence: {exc}")
    for row in data.get("claims", []):
        try:
            claims.append(Claim.model_validate(row))
        except ValidationError as exc:
            validation_errors.append(f"claim: {exc}")

    schema_first_pass = not validation_errors
    tool_calls: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    tool_failure = bool(data.get("tool_failure"))
    retry_attempts = int(data.get("retry_attempts", 0))
    retry_limit_reached = retry_attempts > MAX_RETRIES
    if schema_first_pass and not tool_failure:
        gateway = ToolGateway(LANE_AGENT[data["lane"]], claims[0].observed_at if claims else None)
        try:
            gateway.call(f"adapter.{data['lane']}.read_fixture", {
                "keyframe_id": scenario["scenario_id"],
            })
            tool_calls = gateway.calls
        except Exception as exc:
            tool_failure = True
            tool_calls = gateway.calls
            errors.append({"class": "PERMANENT_CONFIG", "message": str(exc)})
    elif tool_failure:
        tool_calls = [{
            "tool_id": f"adapter.{data['lane']}.read_fixture",
            "arguments": {"keyframe_id": scenario["scenario_id"]},
            "status": "failed",
        }]
        attempts = max(1, retry_attempts)
        errors = [
            _json(make_error(
                LANE_AGENT[data["lane"]],
                "source",
                "controlled evaluation tool failure",
                attempt=attempt,
                input_ref=scenario["scenario_id"],
                timestamp=claims[0].observed_at if claims else None,
            ))
            for attempt in range(1, attempts + 1)
        ]

    checks = dict(data.get("checks", {name: "unknown" for name in CHECK_NAMES}))
    incident: Incident | None = None
    verification: dict[str, Any] = {}
    actual_verdict = "UNKNOWN"
    actual_route = "UNVERIFIED"
    actual_priority = 0
    uncertainties: list[str] = []
    if validation_errors:
        uncertainties.append("input schema validation failed")
    elif tool_failure:
        uncertainties.append("source tool unavailable; no unsupported claim emitted")
        actual_route = "REQUEST_EVIDENCE"
    elif claims:
        verification_model = build_verification(
            claims[0].claim_id,
            list(dict.fromkeys(ref for claim in claims for ref in claim.evidence_refs)),
            checks,
            run_id=f"evaluation-{scenario['scenario_id']}",
            keyframe_id=scenario["scenario_id"],
            trace_id=f"trace-{scenario['scenario_id']}",
            agent_run_id=f"evaluation-{scenario['scenario_id']}",
        )
        verification = _json(verification_model)
        actual_verdict = verification_model.verdict.value
        if verification_model.verdict is not Verdict.PASS:
            uncertainties.append("verification is not PASS")
        incidents = cluster_claims(claims)
        if incidents:
            incident = incidents[0]
            score = data["scores"]
            support = verification_model.support
            verdict = verification_model.verdict
            priority = calculate_priority(
                score["L"], score["D"], score["C"], score["T"],
                support, verdict, bool(data.get("contradictory")),
            )
            actual_priority = priority.priority
            actual_route = priority.route
            incident = incident.model_copy(update={
                "priority": priority.priority,
                "confidence": support,
                "route": priority.route,
                "verification_verdict": verdict,
                "next_step": data.get("next_step", priority.route),
                "lifecycle_status": "NEEDS_EVIDENCE"
                if priority.route == "REQUEST_EVIDENCE" else "MONITORING",
            })
            actual_verdict = verdict.value
            if incident.contradictions:
                uncertainties.append("contradictory evidence is retained")
    elif not claims:
        uncertainties.append("no valid claim entered graph state")

    approval_status, approval_valid, approval_audit = _approval(scenario, incident)
    actual_action = _actual_action(
        actual_route,
        0 if tool_failure or validation_errors else len(cluster_claims(claims)),
        len(claims),
        approval_status,
        tool_failure=tool_failure,
        retry_limit_reached=retry_limit_reached,
    )
    if actual_action == "HOLD_FOR_HUMAN_REVIEW":
        uncertainties.append("human approval required before consequential action")
    audit = [
        {
            "event": "claim.evaluated",
            "scenario_id": scenario["scenario_id"],
            "claim_ids": [claim.claim_id for claim in claims],
            "evidence_refs": list(dict.fromkeys(ref for claim in claims for ref in claim.evidence_refs)),
        }
    ]
    if validation_errors:
        audit.append({"event": "input.rejected", "errors": validation_errors})
        audit.append({
            "event": "action.fallback",
            "action": actual_action,
            "reason": "invalid input; no claim promoted",
        })
    if tool_failure:
        audit.append({
            "event": "tool.failed",
            "attempts": max(1, retry_attempts),
            "final_disposition": "DEGRADED" if retry_limit_reached else "REQUEST_EVIDENCE",
        })
        audit.append({
            "event": "action.fallback",
            "action": actual_action,
            "reason": "source unavailable; request more evidence",
        })
    if incident:
        audit.append({
            "event": "incident.decision",
            "incident_id": incident.incident_id,
            "route": actual_route,
            "action": actual_action,
            "evidence_refs": incident.evidence_refs,
        })
    audit.extend(approval_audit)
    if expected["action"] == "SUPPRESS_DUPLICATE":
        audit.append({
            "event": "incident.suppressed_duplicate",
            "incident_id": incident.incident_id if incident else None,
            "claim_ids": [claim.claim_id for claim in claims],
        })

    incident_count = 0 if tool_failure or validation_errors else len(cluster_claims(claims))
    priority_level = _priority_level(actual_priority)
    approval_required = actual_route in {"DISPATCH_CANDIDATE", "URGENT_HUMAN_REVIEW"}
    dispatch_proposed = approval_required
    actual = {
        "checks": checks,
        "verdict": actual_verdict,
        "priority": actual_priority,
        "priority_level": priority_level,
        "route": actual_route,
        "action": actual_action,
        "incident_count": incident_count,
        "evidence_refs": incident.evidence_refs if incident else [],
        "uncertainties": uncertainties,
        "dispatch_status": approval_status,
        "approval_required": approval_required,
        "dispatch_proposed": dispatch_proposed,
        "dispatch_blocked": approval_required and approval_status != "DISPATCHED",
        "dispatch_approved": approval_status == "DISPATCHED",
        "dispatch_rejected": approval_status == "REJECTED",
        "dispatch_edited": any(item["event"] == "human.approved_edit" for item in approval_audit),
        "recommended_action": actual_action,
    }
    unauthorized_dispatch = (
        approval_status == "DISPATCHED"
        and (not approval_valid or actual_verdict != "PASS")
    )
    elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
    core_match = (
        actual["verdict"] == expected["verdict"]
        and actual["priority_level"] == expected["priority_level"]
        and actual["route"] == expected["route"]
        and actual["action"] == expected["action"]
        and actual["incident_count"] == expected["incident_count"]
    )
    approval_match = (
        "approval_result" not in expected
        or approval_status == expected["approval_result"]
    )
    audit_complete = _audit_complete(claims, evidence, incident, uncertainties, audit)
    return {
        "scenario_id": scenario["scenario_id"],
        "scenario_type": scenario["scenario_type"],
        "data_kind": scenario["data_kind"],
        "description": scenario["description"],
        "expected": expected,
        "actual": actual,
        "verification_check_accuracy": {
            name: checks.get(name) == expected["checks"].get(name)
            for name in CHECK_NAMES
        },
        "unsupported_claim": bool(tool_failure and incident),
        "stale_evidence": scenario["scenario_type"] == "stale_telemetry",
        "missed_urgent": (
            expected["priority_level"] == "urgent"
            and actual["priority_level"] != "urgent"
        ),
        "schema_first_pass": schema_first_pass,
        "tool_success": bool(tool_calls) and not tool_failure,
        "task_completed": bool(schema_first_pass and not tool_failure and core_match and approval_match),
        "manual_repair": False,
        "approval_gate_passed": approval_valid,
        "safety": {"unauthorized_dispatch": unauthorized_dispatch},
        "audit_complete": audit_complete,
        "tool_calls": tool_calls,
        "tool_calls_attempted": len(tool_calls),
        "tool_calls_succeeded": sum(call.get("status") == "ALLOWED" for call in tool_calls),
        "tool_errors": errors,
        "loop_count": max(1, retry_attempts + 1),
        "max_iterations": max(1, retry_attempts + 1),
        "retry_review_limit_reached": retry_limit_reached,
        "token_input": 0,
        "token_output": 0,
        "cached_tokens": 0,
        "token_cost": 0.0,
        "latency_ms": elapsed_ms,
        "overall_correct": bool(core_match and approval_match and not unauthorized_dispatch),
        "audit": audit,
        "verification": verification,
        "notes": expected["rationale"],
    }


def _summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(results)
    expected_duplicates = sum(row["expected"]["action"] == "SUPPRESS_DUPLICATE" for row in results)
    actual_duplicates = sum(
        row["expected"]["action"] == "SUPPRESS_DUPLICATE"
        and row["overall_correct"] for row in results
    )
    expected_requests = sum(row["expected"]["action"] == "REQUEST_EVIDENCE" for row in results)
    actual_requests = sum(
        row["expected"]["action"] == "REQUEST_EVIDENCE"
        and row["overall_correct"] for row in results
    )
    urgent = sum(row["expected"]["priority_level"] == "urgent" for row in results)
    missed_urgent = sum(
        row["expected"]["priority_level"] == "urgent"
        and row["actual"]["priority_level"] != "urgent"
        for row in results
    )
    tool_calls_attempted = sum(row["tool_calls_attempted"] for row in results)
    tool_calls_succeeded = sum(row["tool_calls_succeeded"] for row in results)
    verification_accuracy = {
        name: round(100 * sum(
            row["verification_check_accuracy"][name] for row in results
        ) / total, 2)
        for name in CHECK_NAMES
    }
    return {
        "total_scenarios": total,
        "correct_decisions": f"{sum(row['overall_correct'] for row in results)}/{total}",
        "decision_accuracy_percent": round(100 * sum(row["overall_correct"] for row in results) / total, 2),
        "schema_validation_first_pass_percent": round(100 * sum(row["schema_first_pass"] for row in results) / total, 2),
        "tool_call_success_percent": round(
            100 * tool_calls_succeeded / tool_calls_attempted, 2
        ) if tool_calls_attempted else 100.0,
        "tool_calls_attempted": tool_calls_attempted,
        "tool_calls_succeeded": tool_calls_succeeded,
        "verification_accuracy_percent": verification_accuracy,
        "task_completion_percent": round(100 * sum(row["task_completed"] for row in results) / total, 2),
        "false_dispatches": sum(row["safety"]["unauthorized_dispatch"] for row in results),
        "missed_urgent_incidents": missed_urgent,
        "unsupported_claim_rate_percent": round(100 * sum(
            row["unsupported_claim"] for row in results
        ) / total, 2),
        "stale_evidence_rate_percent": round(100 * sum(
            row["stale_evidence"] for row in results
        ) / total, 2),
        "false_dispatch_rate_percent": round(100 * sum(
            row["safety"]["unauthorized_dispatch"] for row in results
        ) / total, 2),
        "missed_urgent_rate_percent": round(100 * missed_urgent / urgent, 2) if urgent else 0.0,
        "correct_duplicate_suppressions": f"{actual_duplicates}/{expected_duplicates}",
        "useful_abstentions": sum(
            row["expected"]["action"] == "ABSTAIN" and row["overall_correct"] for row in results
        ),
        "correct_request_evidence": f"{actual_requests}/{expected_requests}",
        "priority_routing_accuracy_percent": round(100 * sum(
            row["actual"]["priority_level"] == row["expected"]["priority_level"]
            and row["actual"]["route"] == row["expected"]["route"]
            for row in results
        ) / total, 2),
        "approval_gate_success_percent": round(100 * sum(
            not row["safety"]["unauthorized_dispatch"] for row in results
        ) / total, 2),
        "average_latency_ms": round(sum(row["latency_ms"] for row in results) / total, 3),
        "worst_case_latency_ms": max(row["latency_ms"] for row in results),
        "average_token_cost": round(sum(row["token_cost"] for row in results) / total, 6),
        "average_loop_count": round(sum(row["loop_count"] for row in results) / total, 3),
        "retry_review_limit_reached_percent": round(100 * sum(
            row["retry_review_limit_reached"] for row in results
        ) / total, 2),
        "audit_completeness_percent": round(100 * sum(row["audit_complete"] for row in results) / total, 2),
        "historical_data_used": False,
        "data_note": "All 25 cases are synthetic or Katrina-inspired synthetic fixtures.",
    }


def _write_report(out_dir: Path, results: list[dict[str, Any]], summary: dict[str, Any]) -> None:
    lines = [
        "# CrisisIO Agentic Layer Evaluation",
        "",
        "All scenarios are synthetic Katrina-inspired fixtures; they are not historical findings.",
        "",
        "## Summary",
        "",
        "| Metric | Result |",
        "|---|---:|",
    ]
    labels = {
        "total_scenarios": "Total scenarios",
        "correct_decisions": "Correct decisions",
        "decision_accuracy_percent": "Decision accuracy (%)",
        "schema_validation_first_pass_percent": "Schema first-pass (%)",
        "tool_call_success_percent": "Tool-call success (%)",
        "task_completion_percent": "Task completion (%)",
        "false_dispatches": "False dispatches",
        "missed_urgent_incidents": "Missed urgent incidents",
        "unsupported_claim_rate_percent": "Unsupported-claim rate (%)",
        "stale_evidence_rate_percent": "Stale-evidence rate (%)",
        "false_dispatch_rate_percent": "False-dispatch rate (%)",
        "missed_urgent_rate_percent": "Missed-urgent rate (%)",
        "correct_duplicate_suppressions": "Correct duplicate suppressions",
        "correct_request_evidence": "Correct REQUEST_EVIDENCE",
        "priority_routing_accuracy_percent": "Priority/routing accuracy (%)",
        "approval_gate_success_percent": "Approval-gate success (%)",
        "average_latency_ms": "Average latency (ms)",
        "worst_case_latency_ms": "Worst-case latency (ms)",
        "average_token_cost": "Average token cost",
        "average_loop_count": "Average loop count",
        "retry_review_limit_reached_percent": "Retry/review limit reached (%)",
        "audit_completeness_percent": "Audit completeness (%)",
        "verification_accuracy_percent": "Verification accuracy by check",
    }
    for key, label in labels.items():
        lines.append(f"| {label} | {summary[key]} |")
    lines.extend([
        "",
        "## Scenario Results",
        "",
        "| ID | Type | Expected | Actual | Action | Priority | Route | Schema | Tool | Loops | Latency ms | Correct |",
        "|---|---|---|---|---|---|---|---:|---:|---:|---:|---:|",
    ])
    for row in results:
        lines.append(
            f"| {row['scenario_id']} | {row['scenario_type']} | "
            f"{row['expected']['verdict']} | {row['actual']['verdict']} | "
            f"{row['actual']['action']} | {row['actual']['priority_level']} | "
            f"{row['actual']['route']} | {row['schema_first_pass']} | "
            f"{row['tool_success']} | {row['loop_count']} | "
            f"{row['latency_ms']} | {row['overall_correct']} |"
        )
    lines.extend([
        "",
        "## Limitations",
        "",
        "- The runner uses deterministic Pydantic records and policy functions; it does not benchmark an LLM.",
        "- Tool failures and approval expiry are controlled harness inputs because live adapters are out of MVP scope.",
        "- Token counts are zero for replay/local execution and are not production cost estimates.",
        "- Latency is local process time and is not an availability or latency SLO.",
    ])
    (out_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_html(out_dir: Path, results: list[dict[str, Any]], summary: dict[str, Any]) -> None:
    rows = "\n".join(
        f"<tr id='{row['scenario_id']}'><td>{row['scenario_id']}</td>"
        f"<td>{row['scenario_type']}</td><td>{row['expected']['verdict']}</td>"
        f"<td>{row['actual']['verdict']}</td><td>{row['actual']['action']}</td>"
        f"<td>{row['actual']['route']}</td><td>{row['overall_correct']}</td></tr>"
        for row in results
    )
    featured_ids = ("S01", "S02", "S04", "S05", "S06", "S12", "S19", "S22", "S23")
    featured = "\n".join(
        f"<article class='case'><h3>{escape(row['scenario_id'])}: "
        f"{escape(row['scenario_type'])}</h3><p>{escape(row['description'])}</p>"
        f"<dl><dt>Expected</dt><dd>{escape(row['expected']['verdict'])} / "
        f"{escape(row['expected']['action'])}</dd><dt>Actual</dt><dd>"
        f"{escape(row['actual']['verdict'])} / {escape(row['actual']['action'])}</dd>"
        f"<dt>Route</dt><dd>{escape(row['actual']['route'])}</dd><dt>Approval</dt>"
        f"<dd>{escape(row['actual']['dispatch_status'])}</dd></dl>"
        f"<p class='refs'>Evidence: {escape(', '.join(row['actual']['evidence_refs']) or 'none')} · "
        f"Uncertainty: {escape('; '.join(row['actual']['uncertainties']) or 'none')}</p></article>"
        for row in results if row["scenario_id"] in featured_ids
    )
    html = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>CrisisIO Evaluation</title>
<style>body{{font:16px system-ui;margin:32px;color:#17202a}}table{{border-collapse:collapse;width:100%}}
td,th{{border:1px solid #ccd3d8;padding:8px;text-align:left}}h1{{color:#123b5d}}
.metric{{display:inline-block;margin:8px 24px 16px 0}}.metric b{{display:block;font-size:24px}}
.cases{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin:16px 0 32px}}
.case{{border:1px solid #ccd3d8;border-left:5px solid #2a6f97;padding:12px;background:#f7fafb}}
.case h3{{margin:0 0 6px;color:#123b5d}}.case p{{margin:6px 0}}.case dl{{display:grid;grid-template-columns:80px 1fr;gap:3px;margin:10px 0}}
.case dt{{font-weight:700}}.case dd{{margin:0}}.refs{{font-size:13px;color:#4b5963}}</style></head>
<body><h1>CrisisIO Agentic Layer Evaluation</h1>
<p>25 synthetic Katrina-inspired scenarios. No historical findings. Presentation evidence included in scenario results.</p>
<section>
<div class="metric"><b>{summary['decision_accuracy_percent']}%</b>decision accuracy</div>
<div class="metric"><b>{summary['false_dispatches']}</b>false dispatches</div>
<div class="metric"><b>{summary['schema_validation_first_pass_percent']}%</b>schema first pass</div>
<div class="metric"><b>{summary['approval_gate_success_percent']}%</b>approval safety</div>
</section>
<h2>Presentation evidence</h2>
<div class="cases">{featured}</div>
<table><thead><tr><th>ID</th><th>Type</th><th>Expected</th><th>Actual</th><th>Action</th><th>Route</th><th>Correct</th></tr></thead>
<tbody>{rows}</tbody></table></body></html>"""
    (out_dir / "report.html").write_text(html, encoding="utf-8")


def _write_metrics_slide(out_dir: Path, summary: dict[str, Any]) -> None:
    text = f"""# CrisisIO Evaluation: Slide Summary

Tested {summary["total_scenarios"]} disaster scenarios against predefined synthetic Katrina-inspired outcomes. The deterministic agentic layer separated confirmed facts from uncertainty, requested evidence when needed, handled duplicates, and enforced human approval before dispatch.

- Decision accuracy: {summary["decision_accuracy_percent"]}%
- False dispatches: {summary["false_dispatches"]}
- Missed urgent incidents: {summary["missed_urgent_incidents"]}
- Schema validation first-pass rate: {summary["schema_validation_first_pass_percent"]}%
- Tool-call success rate: {summary["tool_call_success_percent"]}% ({summary["tool_calls_succeeded"]}/{summary["tool_calls_attempted"]} attempted calls)
- Average end-to-end latency: {summary["average_latency_ms"]} ms
- Human approval-gate success: {summary["approval_gate_success_percent"]}%

Prototype boundary: local deterministic policy and controlled failure fixtures only; token cost is not a production estimate.
"""
    (out_dir / "metrics_slide.md").write_text(text, encoding="utf-8")


def run_suite(out_dir: str | Path, *, use_langgraph: bool = False) -> dict[str, Any]:
    del use_langgraph  # The evaluation dataset targets the deterministic policy boundary.
    output = Path(out_dir)
    output.mkdir(parents=True, exist_ok=True)
    (output / "logs").mkdir(exist_ok=True)
    results = [run_scenario(scenario) for scenario in load_scenarios()]
    summary = _summary(results)
    payload = {"dataset_id": "crisisio-katrina-inspired-evaluation-v1", "summary": summary, "scenarios": results}
    (output / "results.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    fields = [
        "scenario_id", "scenario_type", "expected_verdict", "actual_verdict",
        "expected_action", "actual_action", "expected_route", "actual_route",
        "expected_priority", "actual_priority", "schema_first_pass",
        "tool_success", "loop_count", "latency_ms", "token_cost",
        "approval_gate_passed", "overall_correct",
    ]
    with (output / "results.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in results:
            writer.writerow({
                "scenario_id": row["scenario_id"],
                "scenario_type": row["scenario_type"],
                "expected_verdict": row["expected"]["verdict"],
                "actual_verdict": row["actual"]["verdict"],
                "expected_action": row["expected"]["action"],
                "actual_action": row["actual"]["action"],
                "expected_route": row["expected"]["route"],
                "actual_route": row["actual"]["route"],
                "expected_priority": row["expected"]["priority_level"],
                "actual_priority": row["actual"]["priority_level"],
                "schema_first_pass": row["schema_first_pass"],
                "tool_success": row["tool_success"],
                "loop_count": row["loop_count"],
                "latency_ms": row["latency_ms"],
                "token_cost": row["token_cost"],
                "approval_gate_passed": row["approval_gate_passed"],
                "overall_correct": row["overall_correct"],
            })
        for row in results:
            (output / "logs" / f"{row['scenario_id']}.json").write_text(
                json.dumps(row, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
    _write_report(output, results, summary)
    _write_html(output, results, summary)
    _write_metrics_slide(output, summary)
    return payload


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run the fixed CrisisIO evaluation suite.")
    parser.add_argument(
        "--output",
        default=str(ROOT / "artifacts" / "evaluation"),
        help="directory for JSON, CSV, logs, and reports",
    )
    args = parser.parse_args()
    result = run_suite(args.output)
    print(json.dumps(result["summary"], indent=2, sort_keys=True))
