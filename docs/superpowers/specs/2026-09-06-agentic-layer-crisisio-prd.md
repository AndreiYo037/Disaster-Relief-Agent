# CrisisIO Agentic Layer Product Requirements Document

**Status:** Draft for implementation review  
**Date:** 2026-09-06  
**Product:** CrisisIO disaster-response coordination platform  
**Scope:** Agentic layer only; UI wiring is a later integration

## 1. Product Summary

CrisisIO turns fragmented disaster information into an auditable, operator-reviewed operational picture. The agentic layer collects evidence from four source channels, creates candidate claims, verifies and evaluates those claims, clusters them into incidents, proposes routes and resource assignments, and produces a concise operational summary.

The system accelerates situational awareness and planning. It does not autonomously deploy people, vehicles, supplies, drones, robots, or other physical resources.

The MVP is a replayable Katrina-style flood scenario using the existing `t0`, `b7`, and `reroute` keyframes. Live provider execution is supported through AWS Bedrock, but the acceptance and demo path runs deterministically from replay fixtures without AWS credentials.

## 2. Goals

1. Create exactly 15 named AI-agent graph nodes in a LangGraph workflow.
2. Keep parallel agent communication typed, append-only, provenance-preserving, and bounded.
3. Convert evidence into verified or unverified incidents and deterministic operational recommendations.
4. Produce Dispatch-suggested routes and priorities compatible with the existing world model.
5. Preserve human accountability for every physical deployment or external actuation.
6. Expose a stable projection that a later UI integration can consume through the existing `/api/state` pattern.
7. Make replay behavior, failures, decisions, and model/tool usage auditable.

## 3. Non-Goals for the MVP

- Wiring the agent graph into the frontend in this PRD.
- Live API/MCP ingestion; only typed adapter interfaces and replay fixtures are required.
- Retrieval-augmented generation or unrestricted database retrieval.
- Autonomous physical dispatch, route activation, or external actuation.
- WebSockets or server-sent events.
- Multiple coordinator approval policies or two-person approval.
- Audience-specific summaries beyond one canonical operational summary.
- Production-scale accuracy, availability, or latency SLOs.
- A broad disaster taxonomy beyond the MVP event enum.

## 4. Users and Primary Workflow

The primary user is a humanitarian operations coordinator reviewing a disaster picture and proposed work. The later UI will show source evidence, verified incidents, unverified incidents, and suggested routes/priorities.

The workflow is:

1. An adapter or replay fixture emits an evidence batch.
2. Source agents normalize the evidence into observations and candidate claims.
3. Source-aligned verification agents apply five deterministic checks.
4. Source-aligned evaluation agents score operational utility and provide harm inputs.
5. Dispatch clusters claims, resolves canonical priority, and proposes routes, assignments, and work items.
6. Orchestrator merges incident state, applies lifecycle/routing rules, and schedules bounded feedback requests.
7. Summariser creates a traceable operational summary.
8. A deterministic projection exposes the result as a compatible `WorldSnapshot`.
9. A coordinator may approve, modify, or reject any physical action proposal. Only an approved physical action can enter `DISPATCHED`.

## 5. Agent Roster

The graph contains exactly these 15 named nodes. The four source, four verification, and four evaluation nodes use shared implementations with lane-specific configuration, prompts, rubrics, and tool allow-lists.

| # | Agent node | Required responsibility |
|---:|---|---|
| 1 | `SatelliteSourceAgent` | Consume satellite fixtures or a future satellite adapter; emit imagery evidence, observations, and candidate flood/damage claims. |
| 2 | `TelemetrySourceAgent` | Consume gauge/sensor fixtures or a future telemetry adapter; emit measurements, observations, and candidate water-level/infrastructure claims. |
| 3 | `FieldReportSourceAgent` | Consume first-responder fixtures or a future field-report adapter; emit operational observations and candidate access/need claims. |
| 4 | `CommunityReportSourceAgent` | Consume public-report fixtures or a future community adapter; pseudonymize reporters and emit candidate stranded-person/need claims. |
| 5 | `SatelliteVerificationAgent` | Apply the five checks with imagery freshness, coverage, persistence, and change-detection policy. |
| 6 | `TelemetryVerificationAgent` | Apply the five checks with measurement validity, timestamp, and persistence policy. |
| 7 | `FieldReportVerificationAgent` | Apply the five checks with reporter proximity, operational specificity, and urgency policy. |
| 8 | `CommunityReportVerificationAgent` | Apply the five checks with independence, geographic coverage, local detail, and duplication policy. |
| 9 | `SatelliteEvaluationAgent` | Score imagery claims for relevance, actionability, freshness, impact, coverage/novelty, and provide `L/D/C/T` inputs. |
| 10 | `TelemetryEvaluationAgent` | Score telemetry claims and provide `L/D/C/T` inputs. |
| 11 | `FieldReportEvaluationAgent` | Score responder claims and provide `L/D/C/T` inputs. |
| 12 | `CommunityReportEvaluationAgent` | Score public claims and provide `L/D/C/T` inputs. |
| 13 | `DispatchResourcePlanningAgent` | Cluster duplicate claims, resolve canonical priority, create candidate routes and resource assignments, identify conflicts, and create work items. |
| 14 | `OrchestratorAgent` | Merge incident state, apply lifecycle and routing rules, issue bounded evidence requests, and maintain state consistency. |
| 15 | `SummariserAgent` | Produce one canonical, provenance-linked operational summary per incident and a projection payload. |

The `WorldSnapshot` projection is a deterministic function after `SummariserAgent`; it is not a sixteenth agent.

## 6. Graph Topology and Execution

The canonical LangGraph `StateGraph` topology is:

```text
ingest
  -> SatelliteSourceAgent       -> SatelliteVerificationAgent       -> SatelliteEvaluationAgent
  -> TelemetrySourceAgent       -> TelemetryVerificationAgent       -> TelemetryEvaluationAgent
  -> FieldReportSourceAgent     -> FieldReportVerificationAgent     -> FieldReportEvaluationAgent
  -> CommunityReportSourceAgent -> CommunityReportVerificationAgent -> CommunityReportEvaluationAgent
  -> DispatchResourcePlanningAgent
  -> OrchestratorAgent
  -> SummariserAgent
  -> WorldSnapshot projection
```

The four lanes run in parallel at each stage. Dispatch runs after the four evaluation results are available. Orchestrator feedback edges may send a targeted evidence request to the relevant source lane, subject to `max_feedback_cycles=3` per incident. A feedback request is a new bounded graph cycle, not an unbounded recursive call.

Replay executes one graph run per keyframe in chronological order: `t0`, `b7`, then `reroute`. Each run consumes the fixture batch for that keyframe, persists a checkpoint, and emits a snapshot projection.

LangGraph is required for typed state, reducers, checkpointing, and human-interrupt support. Checkpoints are stored in the existing SQLite database using LangGraph checkpoint tables.

### 6.1 Reducer implementation contract

Each append-only collection is a reducer-backed field, not a shared mutable dictionary. The implementation should use the equivalent of:

```python
GraphState = TypedDict(
    "GraphState",
    {
        "evidence": Annotated[list[EvidenceEnvelope], append_unique],
        "observations": Annotated[list[Observation], append_unique],
        "claims": Annotated[list[Claim], append_unique],
        "verification_runs": Annotated[list[VerificationRun], append_unique],
        "evaluations": Annotated[list[Evaluation], append_unique],
        "incidents": Annotated[list[Incident], append_unique],
        "work_items": Annotated[list[WorkItem], append_unique],
        "summaries": Annotated[list[Summary], append_unique],
        "agent_errors": Annotated[list[AgentError], append_unique],
        "lane_results": Annotated[list[LaneResult], append_unique],
        "feedback_requests": Annotated[list[FeedbackRequest], append_unique],
    },
)
```

`append_unique(existing, incoming)` is pure and deterministic: it preserves existing order, appends unseen record IDs, treats an identical duplicate as a no-op, and raises a typed `StateConflict` when the same ID has different content. Nodes must validate and serialize records before returning them. A `StateConflict` is recorded as an `AgentError` and follows the normal retry/degraded path; reducers never overwrite a record.

Parallel lanes may write only to these collection fields. Immutable run metadata (`crisis_id`, `run_id`, `keyframe_id`, `trace_id`, `policy_version`) is written at graph start. Lifecycle status, per-incident feedback counters, and terminal run status have one writer (`OrchestratorAgent`) and no parallel reducer. Per-lane completion is represented by append-only `LaneResult` records; a join derives readiness from those records rather than racing on a shared boolean. Counters are keyed by incident and incremented only by the Orchestrator, so review and feedback limits cannot be lost through concurrent writes.

## 7. Shared Graph State

`GraphState` is typed and append-only. Every result carries these correlation identifiers:

- `crisis_id`
- `run_id`
- `keyframe_id`
- `trace_id`
- `agent_run_id`

Parallel nodes write through reducers into typed collections. Nodes do not overwrite another lane's result slot and do not pass full raw documents or tool logs downstream.

The state contains these collections and control fields:

```text
evidence[]
observations[]
claims[]
verification_runs[]
evaluations[]
incidents[]
work_items[]
summaries[]
agent_errors[]
lane_results[]
feedback_requests[]
checkpoints / run metadata
loop counters and policy version
```

`LaneResult` is the per-lane join record with `lane_id`, terminal `status` (`SUCCEEDED`, `DEGRADED`, or `FAILED`), output references, error references, and completion timestamp. `FeedbackRequest` is the bounded re-query record with `incident_id`, target source lane, requested evidence type, reason, cycle number, and status. Both are append-only and carry the run correlation identifiers.

All collection entries are immutable after append. Corrections create a new record linked to the prior record.

## 8. Canonical Data Contracts

The implementation must define typed Pydantic models for the following records and serialize those models to JSON for SQLite rows and future HTTP responses.

### 8.1 EvidenceEnvelope

Required fields:

- `evidence_id`
- `source_type` and `source_ref`
- `captured_at` and `observed_at`
- optional point/area geometry
- artifact reference from the storage abstraction
- content hash
- adapter version
- collection metadata
- pseudonymous reporter ID when applicable

Raw artifacts are never copied through every agent. Replay stores them on the local filesystem; deployment uses an S3 adapter. SQLite stores hashes, metadata, and references.

### 8.2 Observation

An observation is a normalized description of what an evidence item reports. It must link to one or more `evidence_id` values and must not contain a verification verdict.

### 8.3 Claim

A claim is a normalized, typed statement with:

- `claim_id`
- versioned `event_type`
- subject/location/time
- claim text or structured value
- evidence references
- source lane
- assumptions and extraction metadata

MVP event types are: `flood_extent_change`, `water_level_rise`, `road_blocked`, `bridge_damage`, `people_stranded`, `resource_shortage`, `facility_unavailable`, and `route_status`. Unknown event types are rejected at validation.

### 8.4 VerificationRun

Each verification run records five checks:

1. Provenance
2. Schema/completeness
3. Time/location validity
4. Internal consistency
5. Corroboration

Each check is `pass`, `unknown`, or `fail`. The record includes pass/unknown/fail counts, a categorical `PASS | UNKNOWN | FAIL` verdict, continuous confidence, failed checks, reason, verifier version, policy version, evidence references, and correlation IDs.

Deterministic verdict rules are:

- 4–5 passing checks: `PASS`
- 2–3 passing checks: `UNKNOWN`
- 0–1 passing checks: `FAIL`

The default freshness window is six hours. Event-specific time and distance tolerances are policy configuration, not prompt instructions.

Categorical verdict and continuous confidence are separate fields. The verdict is derived from the number of checks with `pass`: 4-5 passes yields `PASS`, 2-3 passes yields `UNKNOWN`, and 0-1 passes yields `FAIL`; `unknown` checks do not count as passes. The continuous support value used by prioritisation is:

```text
check_value(pass)    = 1.0
check_value(unknown) = 0.5
check_value(fail)    = 0.0
V = sum(check_value(each check)) / 5
```

`V` is therefore continuous in `[0, 1]` and never replaces the categorical verdict. For example, three passes and two unknowns produce `verdict=UNKNOWN` and `V=0.8`. This preserves the distinction between “not enough passing checks for verification” and “partially supported for harm ranking.”

### 8.5 Evaluation

Evaluation is a decision-utility pass, not a second truth check. It records five separate 0–2 scores:

- relevance
- actionability
- freshness
- impact
- coverage/novelty

It also records normalized harm inputs:

- `L`: expected loss-of-life risk
- `D`: expected damage severity
- `C`: critical infrastructure/service criticality
- `T`: time criticality

The record includes the total evaluation score, recommended next step, missing information, evidence references, and lane-specific rubric version.

### 8.6 Incident

An incident is the canonical operational object created from one or more related claims. It includes:

- incident and deduplication IDs
- linked claim/evidence references
- event type and location/time window
- lifecycle status
- priority and confidence as separate values
- contradictions
- recommended work items
- timestamps and expiry
- merge history

Claims sharing an event type inside the default 1 km spatial radius and 6 hour temporal window are clustered into one incident. Event-specific overrides may narrow or widen these defaults. Every merge decision is recorded.

### 8.7 WorkItem

Work items represent evidence requests, monitoring items, candidate routes, candidate resource assignments, or physical dispatch proposals. They include owner, status, assumptions, ETA, capacity/conflict data, evidence references, and whether coordinator approval is required.

### 8.8 AgentError

Errors include agent name, stage, input reference, error class, message, attempt number, retry limit, timestamp, and final disposition. A failed lane must not erase successful lanes.

### 8.9 Summary

The canonical summary includes:

- incident ID and generation timestamp
- headline, location, status, priority, and confidence
- known facts with evidence references
- uncertainties
- actions with owner and status
- contradictions
- next update time
- summary version and correlation IDs

Every surfaced factual statement must have evidence references or an explicit uncertainty label.

### 8.10 LaneResult and FeedbackRequest

`LaneResult` records `lane_id`, terminal status (`SUCCEEDED`, `DEGRADED`, or `FAILED`), output references, error references, completion timestamp, and correlation IDs. `FeedbackRequest` records `incident_id`, target source lane, requested evidence type, reason, cycle number, status, and correlation IDs. Both are append-only and are the only records used by the parallel-lane join and bounded feedback edges.

## 9. Deterministic Policy and Safety

Models may extract, normalize, query permitted evidence, or improve wording. Deterministic code owns validation, verification scoring, evaluation aggregation, priority, deduplication, routing, state transitions, and approval gates.

### 9.1 Priority

Verification confidence is the continuous `V` defined above: pass `1`, unknown `0.5`, and fail `0`, averaged across all five checks. The categorical verdict remains a separate pass-count result.

```text
harm_score = 100 * (0.55L + 0.25D + 0.10C + 0.10T)
priority   = round(harm_score * (0.60 + 0.40V))
```

If `L >= 0.70` and `T >= 0.70`, priority is at least 90 and the route is `URGENT_HUMAN_REVIEW`.

Otherwise:

- contradiction or `V < 0.40`: `REQUEST_EVIDENCE`
- priority >= 80 and `V >= 0.80`: `DISPATCH_CANDIDATE`
- priority >= 60: `MONITOR`
- otherwise: `UNVERIFIED`

An unverified incident may be highly prioritized and surfaced, but it cannot become an executable dispatch. All non-`PASS` incidents, including high-priority and high-harm `UNKNOWN`, contradictory, stale, degraded, and `FAIL` incidents, remain in the unverified queue. The queue is sorted by priority descending and retains `URGENT_HUMAN_REVIEW` and `REQUEST_EVIDENCE` items rather than hiding or suppressing them.

### 9.2 Incident Lifecycle

```text
OPEN -> MONITORING -> NEEDS_EVIDENCE -> DISPATCHED -> RESOLVED
  \_______________________________________________/       |
                         CLOSED <-------------------------+
```

`CLOSED` may be reached from any non-active or abandoned state. Only a coordinator-approved physical action may enter `DISPATCHED`.

### 9.3 Human Approval

One authenticated coordinator identity is sufficient for the MVP. Local development uses an auth stub; the interface is ready for a production identity provider. The coordinator may approve, modify, or reject a physical deployment or external-actuation proposal. Decisions are immutable and audit-logged.

Recommendations, monitoring items, evidence requests, route candidates, and UI projections may proceed automatically.

### 9.4 Partial Failure and Bounds

Every node invocation is wrapped by one attempt policy that validates the returned typed envelope before it can enter shared state. Each attempt records start/end time, error class, validation result, and token/tool usage.

Error classes and handling are explicit:

- `TRANSIENT` (timeout, connection reset, throttling, provider 5xx): retry with bounded exponential backoff.
- `RECOVERABLE_OUTPUT` (malformed JSON, schema-invalid model output, invalid tool response): retry with a constrained repair instruction; validate the repaired response again.
- `PERMANENT_CONFIG` (invalid model/region, disallowed tool, missing required argument): fail at the boundary; do not retry.
- `PERMANENT_AUTH` (credential or permission failure): do not retry; mark the lane degraded and surface the error.
- `POLICY_REJECTED` (unknown event type, PII violation, provenance violation): do not retry; retain the rejected input reference and emit a typed error result.

`TRANSIENT` and `RECOVERABLE_OUTPUT` errors retry up to `max_retries=2` after the initial attempt. Backoff is capped and configurable; retry timing is recorded. Other lanes continue. After exhaustion, the affected lane emits a schema-valid `LaneResult(status=DEGRADED, error_refs=[...])` rather than silently disappearing:

- source failure: preserve accepted evidence, emit no unsupported claim, and create an evidence request;
- verification failure: retain the claim as `UNKNOWN`/unverified and block promotion to the verified tab;
- evaluation failure: retain the verification record, omit executable planning, and route to `REQUEST_EVIDENCE`;
- Dispatch failure: retain incidents but emit no route or assignment and mark planning degraded;
- Orchestrator failure: do not mutate lifecycle state; checkpoint the error for resume;
- Summariser failure: render a deterministic fallback from validated records and mark the summary degraded.

The graph enforces `max_review_rounds=3`, `max_feedback_cycles=3` per incident, and a LangGraph recursion/step limit sized for the 15-node topology. A join proceeds when every lane has a terminal `SUCCEEDED`, `DEGRADED`, or `FAILED` `LaneResult`; one unavailable lane cannot deadlock the run.

Invalid model IDs, regions, tools, and runtime configuration fail before an agent call.

## 10. Tools, Models, and Runtime Configuration

Every agent has an explicit allow-list. No agent receives a general-purpose database connection, arbitrary SQL, shell/network access, or external-actuation tool. Tool calls pass through a deny-by-default gateway that validates the tool name and JSON arguments against the agent manifest, records denied attempts, and injects only returned typed data into graph state.

| Agent group | Exact MVP tool IDs |
|---|---|
| `SatelliteSourceAgent` | `adapter.satellite.read_fixture`, `artifact.put`, `evidence.append`, `observation.append`, `claim.append` |
| `TelemetrySourceAgent` | `adapter.telemetry.read_fixture`, `artifact.put`, `evidence.append`, `observation.append`, `claim.append` |
| `FieldReportSourceAgent` | `adapter.field_report.read_fixture`, `artifact.put`, `evidence.append`, `observation.append`, `claim.append` |
| `CommunityReportSourceAgent` | `adapter.community.read_fixture`, `artifact.put`, `evidence.append`, `observation.append`, `claim.append` |
| Verification agents | `evidence.get_by_ids`, `claims.get_by_ids`, `claims.find_corroboration`, `verification.append` |
| Evaluation agents | `evidence.get_by_ids`, `claims.get_by_ids`, `policy.get_version`, `evaluation.append` |
| Dispatch | `world.routes.read`, `world.resources.read`, `incidents.append`, `work_items.append` |
| Orchestrator | `state.read_current`, `incidents.append`, `feedback_requests.append`, `checkpoint.read`, `checkpoint.write` |
| Summariser | `incidents.read`, `evidence.get_by_ids`, `work_items.read`, `summary.append`, `projection.write` |

Live adapter IDs (`adapter.*.read_live`) are reserved for the later live-ingestion phase and are not enabled by the MVP manifests. `projection.write` writes only the validated versioned projection; it cannot call a frontend or mutate UI state directly. No listed tool may activate a route, send a vehicle, release supplies, operate a drone/robot, or otherwise actuate the physical world.

The runtime interface is provider-neutral, but the MVP live provider is AWS Bedrock. The checked-in non-secret configuration is [`config/agent-runtime.toml`](../../../config/agent-runtime.toml):

- model ID: `openai.gpt-oss-120b-1:0`
- region: `us-east-1`
- provider/model/region allow-list validation is mandatory; startup must fail clearly if the configured model is not available in the configured Bedrock region
- timeout and token budget are explicit configuration values

Replay fixtures do not require AWS credentials. Bedrock calls are covered by contract mocks in tests.

RAG is deferred. Agents use only the current typed graph state and scoped policy inputs.

Source reliability is versioned metadata with neutral initial priors. Updates require auditable, human-reviewed outcomes and reliability is never the sole verification basis.

PII is minimized and redacted before entering shared state. Raw artifacts use access controls, encryption, retention limits, and pseudonymous reporter IDs.

## 11. Dispatch and Resource Planning

`DispatchResourcePlanningAgent` owns the deterministic operational planning pass:

1. Cluster duplicate claims into incidents.
2. Resolve canonical priority while preserving confidence separately.
3. Match incident needs to world-model resources using capacity, location, capability, ETA, and competing incidents.
4. Read existing `route_paths` and route states to produce candidate routes.
5. Record shortages, conflicts, assumptions, evidence references, and candidate assignments.
6. Create work items for monitoring, evidence requests, or coordinator review.

The agent does not call a live routing service, activate a route, or deploy a resource. The primary later UI surface exposes suggested routes and priorities; detailed assignments remain in the operational records and audit view.

## 12. Summarisation and Projection

`SummariserAgent` produces one canonical operational summary per incident. It does not verify evidence, reprioritize incidents, change lifecycle state, or dispatch resources.

The structured summary is validated first. A deterministic template renders the summary. Bedrock may improve wording only after validation and may not change facts, status, priority, routes, owners, uncertainty labels, or evidence references.

The deterministic projection preserves all existing `WorldSnapshot` fields and adds only the minimum agent-facing fields required for later UI integration:

- source evidence summaries
- verified incident summaries
- unverified incident summaries
- Dispatch-suggested routes
- Dispatch priorities

Verified-tab membership is determined by Orchestrator status: only `PASS` incidents appear in the verified tab. `UNKNOWN`, `FAIL`, contradictory, stale, and degraded incidents appear in the unverified tab, including high-priority and high-harm incidents. The unverified tab is an operational queue, not a discard/archive view: it is sorted by priority descending, displays urgency and next step, and retains `URGENT_HUMAN_REVIEW` and `REQUEST_EVIDENCE` items. Intermediate verification and evaluation details remain persisted and available to audit endpoints but are not required in the primary dashboard.

The existing read-only HTTP pattern remains the compatibility target: versioned projections are available through `/api/state?keyframe=...` for replay and polling during live runs. The frontend never reads the database directly.

## 13. Persistence and Database Requirements

Preserve existing entity, relationship, entity-state, plan, permit, episode, and audit tables. Add normalized tables for:

- `evidence`
- `claims`
- `verification_runs`
- `evaluations`
- `incidents`
- `work_items`
- `agent_runs`

Add LangGraph checkpoint tables in the same SQLite database. Use immutable IDs and foreign-key-compatible references where practical. The audit record must capture agent decisions, merge decisions, retry/failure events, coordinator decisions, and summary versions.

## 14. Testing and Acceptance

The MVP must include an offline fixture suite for the Katrina replay. Tests should be small, deterministic, and runnable without cloud credentials.

Required checks:

1. All agent outputs validate against the typed models.
2. Five-check verification produces the expected `PASS`, `UNKNOWN`, and `FAIL` classifications.
3. Priority formula, life-risk override, and routing thresholds are reproducible.
4. Claims inside deduplication tolerances merge into one incident; merge history and evidence references remain intact.
5. Contradictory evidence remains visible and routes correctly.
6. A failed source/tool retries twice, records errors, and does not stop unaffected lanes.
7. Review and feedback loops stop at their hard limits.
8. Physical actions cannot enter `DISPATCHED` without coordinator approval.
9. Approve, modify, and reject decisions are immutable and audit-logged.
10. `t0`, `b7`, and `reroute` replay runs produce deterministic projections compatible with existing snapshot consumers.
11. Verified/unverified membership follows the Orchestrator verdict rules.
12. Suggested routes and priorities use existing world-model route data.
13. Every surfaced fact has provenance or an explicit uncertainty label.
14. Bedrock model calls pass through contract mocks and reject invalid configuration.

Acceptance targets:

- at least 95% of fixture node outputs schema-valid on the first attempt (without retry) for healthy scenarios;
- 100% schema-valid agent result envelopes after the configured retry budget (`max_retries=2`), with exhausted failures represented as typed `DEGRADED`/`FAILED` results rather than invalid JSON;
- 0 autonomous physical dispatches.
- 100% provenance coverage for surfaced factual statements.
- deterministic priority/routing results for identical inputs.
- graceful completion under partial failure.
- recorded latency, token, tool-call, completion, and loop-iteration metrics.

The MVP does not set production accuracy or availability targets. A later harness may run labeled scenarios through the real pipeline and report correct decisions, false dispatches, missed urgent claims, useful abstentions, latency, and cost.

## 15. Observability and Audit

Every agent run records model/provider, model ID, region, prompt/config version, tool calls, token counts, latency, input/output validation result, retry count, and correlation IDs. Metrics must distinguish:

- schema-valid output rate
- tool-call success rate
- graph completion rate
- token usage/cost
- latency by agent and run
- loop iterations
- verification verdict distribution
- routing distribution
- human approval outcomes

No raw PII or unrestricted raw tool logs are copied into shared state or primary UI output.

## 16. Deferred Extensions

The following are intentionally compatible with this PRD but not required for the MVP:

- live satellite, telemetry, responder, and community adapters behind the existing typed interfaces
- S3-backed artifact storage in deployment
- scoped RAG views for evidence history, source reliability, policies, and labeled scenarios
- streaming projection transport
- audience-specific summaries
- multi-coordinator approval policies
- additional disaster types and event enums
- a larger labeled evaluation harness and production SLOs

## 17. Decision Record

The following decisions resolve the draft’s open requirements:

- 15 nodes are fixed as four source, four verification, four evaluation, Dispatch/resource planning, Orchestrator, and Summariser.
- LangGraph `StateGraph` is the required runtime.
- Shared state is typed, append-only, and reducer-backed.
- Source agents emit candidate claims; they never verify them.
- Verification and evaluation remain source-aligned, with shared-pool corroboration.
- Deterministic logic owns all safety-critical scoring and routing.
- Bedrock is the MVP live provider, fixed to `openai.gpt-oss-120b-1:0` in `us-east-1`.
- Replay fixtures are the credential-free acceptance path.
- Unverified high-harm incidents remain visible but never executable.
- One coordinator identity handles approval, modification, and rejection.
- The UI integration is projection-based and preserves `/api/state` compatibility.
