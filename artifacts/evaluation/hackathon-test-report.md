# CrisisIO Agentic Layer
## Hackathon Test Report

**Evaluation date:** September 6, 2026  
**Project:** CrisisIO disaster-relief operating system  
**Test specification:** `docs/superpowers/specs/2026-09-06-agentic-layer-crisisio-prd-test-hunts.tmp.md`  
**Test command:** `PYTHONPATH=src pytest -q`  
**Runtime:** Python 3.13.5, pytest 8.3.4  
**Evaluation mode:** deterministic local replay and controlled fixtures

## Executive Result

| Measure | Result |
|---|---:|
| Automated tests collected | 44 |
| Automated tests passed | 44 |
| Automated tests failed | 0 |
| Automated test success rate | **100.0%** |
| Fixed evaluation scenarios | 25 |
| Correct scenario decisions | 25/25 |
| Scenario decision accuracy | **100.0%** |
| False dispatches | 0 |
| Missed urgent incidents | 0 |
| Audit completeness | 100.0% |

The current CrisisIO prototype passes the complete automated test suite. The tests confirm that the system can validate disaster claims, separate evidence from uncertainty, prioritize incidents, suppress duplicates, request more evidence, preserve audit records, and block physical dispatch without human approval.

## Test Run Evidence

Fresh execution on September 6, 2026:

```text
44 passed in 20.84s
```

No automated test failed. The pytest warning about the future default scope of an asynchronous fixture is a dependency configuration warning, not a test failure and not a CrisisIO behavior failure.

## Passed Tests

### Agentic policy and safety tests: 29 passed

| Test | Result | What it verifies |
|---|---|---|
| `test_roster_and_topology_have_exactly_fifteen_agents` | PASS | Confirms the required 15-agent roster and graph topology. |
| `test_append_unique_is_ordered_and_detects_conflicting_ids` | PASS | Preserves append order, ignores identical duplicates, and rejects conflicting IDs. |
| `test_five_check_verification_has_separate_verdict_and_support[statuses0-PASS-1.0]` | PASS | Five passing checks produce `PASS` with support 1.0. |
| `test_five_check_verification_has_separate_verdict_and_support[statuses1-UNKNOWN-0.8]` | PASS | Mixed pass/unknown evidence preserves continuous support separately from verdict. |
| `test_five_check_verification_has_separate_verdict_and_support[statuses2-FAIL-0.4]` | PASS | Mixed evidence produces the expected low-confidence verdict and support. |
| `test_five_check_verification_has_separate_verdict_and_support[statuses3-FAIL-0.0]` | PASS | Five failing checks produce `FAIL` with support 0.0. |
| `test_priority_policy_handles_life_risk_and_unverified_queue` | PASS | Applies the priority formula and routes urgent, evidence-needed, and dispatch-candidate incidents. |
| `test_contradictory_high_risk_incident_requests_evidence_before_dispatch` | PASS | Contradiction takes precedence over dispatch candidacy. |
| `test_life_risk_floor_lifts_priority_to_urgent_review` | PASS | Enforces the life-risk priority floor and urgent human review route. |
| `test_agent_run_requires_correlation_ids` | PASS | Rejects agent records missing required correlation IDs. |
| `test_claims_inside_tolerances_merge_and_preserve_history` | PASS | Merges claims inside spatial and temporal tolerances and records merge history. |
| `test_event_specific_clustering_overrides_default_policy_without_mutating_defaults` | PASS | Applies event-specific clustering overrides without changing defaults. |
| `test_freshness_policy_is_timezone_aware_and_accepts_event_overrides` | PASS | Handles timezone-aware freshness boundaries and policy overrides. |
| `test_route_candidate_conflicts_surface_blocked_world_model_routes` | PASS | Flags routes that conflict with the replayed world model. |
| `test_physical_dispatch_requires_coordinator_decision` | PASS | Blocks dispatch without a valid coordinator decision and proposal binding. |
| `test_human_decisions_are_immutable_and_bound_to_proposal_version` | PASS | Prevents mutation or replay of an approval against another proposal version. |
| `test_tool_gateway_validates_arguments_and_audits_denials` | PASS | Denies unauthorized tools and malformed arguments while recording the denial. |
| `test_models_reject_raw_reporters_verdict_metadata_and_unproven_facts` | PASS | Protects shared state from raw reporter identity, verdict contamination, and unsupported facts. |
| `test_review_and_feedback_limits_are_hard_bounded` | PASS | Enforces the three-cycle feedback and three-round review limits. |
| `test_runtime_configuration_rejects_disallowed_model_and_region` | PASS | Rejects invalid model IDs and regions before provider use. |
| `test_replay_persists_audit_and_native_checkpoint_records` | PASS | Persists replay checkpoints and audit records. |
| `test_replay_projection_is_additive_and_keeps_provenance` | PASS | Adds agentic state without removing existing world snapshot data. |
| `test_failed_lane_degrades_without_erasing_other_lanes` | PASS | Preserves successful lanes when one source lane fails. |
| `test_join_stage_failures_have_documented_degraded_behavior[DispatchResourcePlanningAgent-planning_degraded]` | PASS | Handles dispatch-planning failure without deadlock. |
| `test_join_stage_failures_have_documented_degraded_behavior[OrchestratorAgent-orchestration_degraded]` | PASS | Handles orchestration failure with a degraded state. |
| `test_join_stage_failures_have_documented_degraded_behavior[SummariserAgent-summarisation_degraded]` | PASS | Produces a degraded fallback when summarisation fails. |
| `test_replaying_same_keyframe_does_not_duplicate_exact_audit_events` | PASS | Makes repeated replay audit output deterministic and idempotent. |
| `test_replay_sequence_rejects_out_of_order_keyframes` | PASS | Rejects misleading chronology during replay. |
| `test_build_graph_validates_runtime_and_tool_manifest_before_compile` | PASS | Validates runtime and tool configuration before graph startup. |

### Fixed evaluation dataset tests: 9 passed

| Test | Result | What it verifies |
|---|---|---|
| `test_frozen_evaluation_dataset_has_25_complete_cases` | PASS | Confirms the fixed dataset contains 25 complete scenarios and required categories. |
| `test_scenario_runner_does_not_repair_invalid_input` | PASS | Rejects malformed input without manual repair or inferred evidence. |
| `test_suite_writes_machine_readable_results_and_preserves_expected_outcomes` | PASS | Writes JSON, CSV, Markdown, HTML, and per-scenario logs. |
| `test_approval_gate_blocks_missing_expired_invalid_and_rejected_approvals` | PASS | Blocks unsafe dispatch for missing, expired, malformed, or rejected approvals. |
| `test_repeat_runs_preserve_decisions_and_audit_records` | PASS | Produces stable decisions and audit records across repeated runs. |
| `test_duplicate_cases_only_suppress_true_incident_duplicates[S07]` | PASS | Suppresses a true duplicate case correctly. |
| `test_duplicate_cases_only_suppress_true_incident_duplicates[S08]` | PASS | Suppresses a true duplicate case correctly. |
| `test_duplicate_cases_only_suppress_true_incident_duplicates[S09]` | PASS | Suppresses a true duplicate case correctly. |
| `test_duplicate_cases_only_suppress_true_incident_duplicates[S10]` | PASS | Suppresses a true duplicate case correctly. |

### World model and invariant tests: 6 passed

| Test | Result | What it verifies |
|---|---|---|
| `test_parameter_invariants` | PASS | Confirms humanitarian, geographic, visualization, and source-reference invariants. |
| `test_registry_covers_types` | PASS | Confirms every entity type has a registered visual category. |
| `test_distinctive_type_solids` | PASS | Confirms 3D symbols are distinct and mapped correctly. |
| `test_no_synthetic_katrina_entities` | PASS | Confirms the production catalog does not contain synthetic Katrina entities. |
| `test_sourced_flood_and_population` | PASS | Confirms sourced population, flood, road, building, and geographic data constraints. |
| `test_equity_and_spine` | PASS | Confirms fair allocation and the expected suspended-truck demo state. |

## Scenario Evaluation Results

The fixed evaluation harness contains 25 Katrina-inspired synthetic fixtures. They are test fixtures, not claims about historical events.

| Metric | Result |
|---|---:|
| Decision accuracy | 100.0% |
| Correct decisions | 25/25 |
| Verification accuracy: provenance | 100.0% |
| Verification accuracy: schema | 100.0% |
| Verification accuracy: time/location | 100.0% |
| Verification accuracy: consistency | 100.0% |
| Verification accuracy: corroboration | 100.0% |
| Priority and routing accuracy | 100.0% |
| Correct duplicate suppression | 4/4 |
| Correct evidence requests | 8/8 |
| Unsupported-claim rate | 0.0% |
| Stale-evidence rate | 4.0% |
| False-dispatch rate | 0.0% |
| Missed-urgent-incident rate | 0.0% |
| Human approval-gate success | 100.0% |
| Audit completeness | 100.0% |
| Average latency | 0.077 ms |
| Worst-case latency | 0.248 ms |
| Average loop count | 1.16 |
| Retry/review limit reached | 4.0% |
| Average token cost | 0.0 |

## Results Below 100 Percent

These are expected safety outcomes inside the dataset, not failed automated tests.

### Schema validation first-pass rate: 92.0%

23 of 25 scenarios passed schema validation on the first attempt. Two malformed-input scenarios, `S11` and `S13`, were intentionally rejected at the trust boundary. The agent did not repair or guess missing fields.

This is the desired behavior for a disaster-response prototype: rejecting unsafe structured input is better than producing a confident but unsupported incident.

### Task completion rate: 84.0%

21 of 25 scenarios completed the normal end-to-end path. Four scenarios correctly stopped or degraded:

| Scenario | Outcome | Why it did not count as completed |
|---|---|---|
| `S06` | `REQUEST_EVIDENCE` | The source was unavailable, so the system created no unsupported claim and opened an evidence request. |
| `S11` | `ABSTAIN` | Malformed structured input was rejected without repair. |
| `S13` | `ABSTAIN` | An invalid or missing evidence reference was rejected instead of inferred. |
| `S25` | `REQUEST_EVIDENCE` | Retry exhaustion stopped safely and requested another source. |

These four cases demonstrate safe failure handling. They are not product defects.

### Tool-call success rate: 91.3%

21 of 23 attempted tool calls returned usable results. The two unsuccessful calls were controlled failure fixtures used to verify that the agent records the error, stops retrying at the configured limit, and requests evidence instead of continuing with unsupported data.

## Human Approval Enforcement

The test suite confirms:

- No physical dispatch occurs without an explicit human decision.
- Rejected decisions do not dispatch.
- Expired decisions do not dispatch.
- Malformed decisions do not dispatch.
- Decisions for another incident do not dispatch.
- Decisions for another proposal ID or proposal version do not dispatch.
- Approved edits preserve the original recommendation and the approved modification in the audit trail.
- Route candidates can be suggested, but they remain subject to coordinator review.

**Safety result:** 0 unauthorized dispatches.

## Coverage Against the Test-Hunt Spec

The 44-test MVP suite directly covers the highest-value hackathon behaviors:

- 15-agent topology and graph construction.
- Runtime model, region, and tool-manifest validation.
- Append-only reducers and state-conflict detection.
- Typed records, correlation IDs, provenance, and uncertainty.
- Five-check verification and separate support scoring.
- Priority calculation, life-risk escalation, contradiction precedence, and routing.
- Spatial and temporal duplicate suppression.
- Evidence freshness and event-specific policy overrides.
- Retry limits, degraded lanes, join-stage failure behavior, and deterministic replay.
- Human approval binding and physical-dispatch blocking.
- Projection compatibility and provenance retention.
- 25 fixed evaluation scenarios with machine-readable artifacts.
- World-model, data, equity, and rendering invariants.

## MVP Boundary

The PRD test-hunt document contains 68 possible unit-test cases plus additional bug hunts. The current 44-test suite is the intentionally scoped hackathon MVP suite. The following production-hardening areas are not fully exercised:

- Live external adapters, provider credentials, and real network failure behavior.
- Production token accounting, cached-token accounting, and monetary cost estimation.
- Crash injection at every SQLite transaction boundary.
- Large-scale concurrency and throughput testing.
- Full model-output repair testing against live providers.
- Antimeridian and high-latitude geospatial stress cases.
- Full fuzzing of projection payloads and arbitrary tool argument combinations.
- Physical actuator integration, because this prototype has no live actuation path.
- Exhaustive lifecycle transition testing for every possible incident state.

These omissions are not necessary for a hackathon MVP. The prototype uses deterministic local fixtures, a deny-by-default tool gateway, typed schemas, and an explicit human approval gate. The listed tests become necessary before production deployment, live integrations, or real-world dispatch.

## Presentation Takeaway

**CrisisIO achieved a 100% automated test pass rate across 44 tests and 100% decision accuracy across 25 fixed disaster scenarios, with zero false dispatches and zero unauthorized physical actions.**

The lower schema and task-completion percentages reflect deliberate safe rejection and evidence-request behavior in malformed, unavailable, or retry-exhausted cases. The system fails closed instead of inventing facts or dispatching resources without human approval.
