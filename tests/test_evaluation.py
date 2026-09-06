from __future__ import annotations

import json
from pathlib import Path

import pytest

from crisis_os.evaluation import load_scenarios, run_scenario, run_suite


ROOT = Path(__file__).resolve().parents[1]


def test_frozen_evaluation_dataset_has_25_complete_cases():
    scenarios = load_scenarios()

    assert len(scenarios) == 25
    assert len({row["scenario_id"] for row in scenarios}) == 25
    required = {
        "scenario_id",
        "scenario_type",
        "data_kind",
        "description",
        "input",
        "expected",
    }
    assert all(required <= row.keys() for row in scenarios)
    scenario_types = {row["scenario_type"] for row in scenarios}
    assert {
        "verified_flood",
        "contradictory_evidence",
        "stale_telemetry",
        "duplicate_reports",
        "urgent_unverified",
        "failed_source",
    } <= scenario_types
    assert {"human_rejection", "human_edit"} <= scenario_types or "human_rejection_or_edit" in scenario_types


def test_scenario_runner_does_not_repair_invalid_input():
    scenario = next(row for row in load_scenarios() if row["scenario_id"] == "S13")

    result = run_scenario(scenario)

    assert result["schema_first_pass"] is False
    assert result["manual_repair"] is False
    assert result["task_completed"] is False
    assert result["actual"]["verdict"] == "UNKNOWN"


def test_suite_writes_machine_readable_results_and_preserves_expected_outcomes(tmp_path):
    result = run_suite(tmp_path, use_langgraph=False)

    assert result["summary"]["total_scenarios"] == 25
    assert len(result["scenarios"]) == 25
    assert (tmp_path / "results.json").exists()
    assert (tmp_path / "results.csv").exists()
    assert (tmp_path / "report.md").exists()
    assert (tmp_path / "metrics_slide.md").exists()
    assert (tmp_path / "report.html").exists()
    html = (tmp_path / "report.html").read_text(encoding="utf-8")
    assert "Presentation evidence" in html
    assert "S23" in html
    assert len(list((tmp_path / "logs").glob("*.json"))) == 25
    persisted = json.loads((tmp_path / "results.json").read_text(encoding="utf-8"))
    assert persisted["summary"] == result["summary"]
    assert set(result["summary"]["verification_accuracy_percent"]) == {
        "provenance", "schema", "time_location", "consistency", "corroboration"
    }
    edited = next(row for row in result["scenarios"] if row["scenario_id"] == "S23")
    assert edited["actual"]["dispatch_proposed"] is True
    assert edited["actual"]["dispatch_approved"] is True
    assert edited["actual"]["dispatch_edited"] is True


def test_approval_gate_blocks_missing_expired_invalid_and_rejected_approvals():
    scenarios = load_scenarios()
    for scenario_id in ("S19", "S20", "S21", "S22"):
        result = run_scenario(next(row for row in scenarios if row["scenario_id"] == scenario_id))
        assert result["actual"]["dispatch_status"] != "DISPATCHED"
        assert result["approval_gate_passed"] is False
        assert result["safety"]["unauthorized_dispatch"] is False


def test_repeat_runs_preserve_decisions_and_audit_records():
    scenario = next(row for row in load_scenarios() if row["scenario_id"] == "S23")

    first = run_scenario(scenario)
    second = run_scenario(scenario)

    assert first["actual"] == second["actual"]
    assert first["audit"] == second["audit"]


@pytest.mark.parametrize("scenario_id", ["S07", "S08", "S09", "S10"])
def test_duplicate_cases_only_suppress_true_incident_duplicates(scenario_id):
    scenario = next(row for row in load_scenarios() if row["scenario_id"] == scenario_id)
    result = run_scenario(scenario)

    assert result["actual"]["action"] == result["expected"]["action"]
    assert result["actual"]["incident_count"] == result["expected"]["incident_count"]
