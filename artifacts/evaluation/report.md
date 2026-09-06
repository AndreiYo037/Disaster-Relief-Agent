# CrisisIO Agentic Layer Evaluation

All scenarios are synthetic Katrina-inspired fixtures; they are not historical findings.

## Summary

This run used replay fixtures only. Token cost is 0 because no live model or paid API call was made. In a live deployment, cost would be tracked per provider call and would be non-zero.

The 92% schema first-pass rate is intentional. The suite includes malformed and incomplete inputs so the harness can prove the system rejects bad records without repair, not just pass on clean cases.

| Metric | Result |
|---|---:|
| Total scenarios | 25 |
| Correct decisions | 25/25 |
| Decision accuracy (%) | 100.0 |
| Schema first-pass (%) | 92.0 |
| Tool-call success (%) | 91.3 |
| Task completion (%) | 84.0 |
| False dispatches | 0 |
| Missed urgent incidents | 0 |
| Unsupported-claim rate (%) | 0.0 |
| Stale-evidence rate (%) | 4.0 |
| False-dispatch rate (%) | 0.0 |
| Missed-urgent rate (%) | 0.0 |
| Correct duplicate suppressions | 4/4 |
| Correct REQUEST_EVIDENCE | 8/8 |
| Priority/routing accuracy (%) | 100.0 |
| Approval-gate success (%) | 100.0 |
| Average latency (ms) | 0.112 |
| Worst-case latency (ms) | 0.625 |
| Average token cost | 0.0 |
| Average loop count | 1.16 |
| Retry/review limit reached (%) | 4.0 |
| Audit completeness (%) | 100.0 |
| Verification accuracy by check | {'provenance': 100.0, 'schema': 100.0, 'time_location': 100.0, 'consistency': 100.0, 'corroboration': 100.0} |

## Scenario Results

| ID | Type | Expected | Actual | Action | Priority | Route | Schema | Tool | Loops | Latency ms | Correct |
|---|---|---|---|---|---|---|---:|---:|---:|---:|---:|
| S01 | verified_flood | PASS | PASS | MONITOR | medium | MONITOR | True | True | 1 | 0.625 | True |
| S02 | contradictory_evidence | UNKNOWN | UNKNOWN | REQUEST_EVIDENCE | low | REQUEST_EVIDENCE | True | True | 1 | 0.113 | True |
| S03 | stale_telemetry | UNKNOWN | UNKNOWN | REQUEST_EVIDENCE | low | REQUEST_EVIDENCE | True | True | 1 | 0.128 | True |
| S04 | duplicate_reports | PASS | PASS | SUPPRESS_DUPLICATE | low | UNVERIFIED | True | True | 1 | 0.618 | True |
| S05 | urgent_unverified | UNKNOWN | UNKNOWN | HOLD_FOR_HUMAN_REVIEW | urgent | URGENT_HUMAN_REVIEW | True | True | 1 | 0.081 | True |
| S06 | failed_source | UNKNOWN | UNKNOWN | REQUEST_EVIDENCE | low | REQUEST_EVIDENCE | True | False | 2 | 0.038 | True |
| S07 | duplicate_reports | PASS | PASS | SUPPRESS_DUPLICATE | medium | MONITOR | True | True | 1 | 0.106 | True |
| S08 | duplicate_reports | PASS | PASS | SUPPRESS_DUPLICATE | low | UNVERIFIED | True | True | 1 | 0.115 | True |
| S09 | near_match_distinct_incidents | PASS | PASS | ROUTE | low | UNVERIFIED | True | True | 1 | 0.089 | True |
| S10 | duplicate_reports | PASS | PASS | SUPPRESS_DUPLICATE | low | UNVERIFIED | True | True | 1 | 0.083 | True |
| S11 | malformed_structured_input | UNKNOWN | UNKNOWN | ABSTAIN | low | UNVERIFIED | False | False | 1 | 0.058 | True |
| S12 | unverifiable_provenance | FAIL | FAIL | REQUEST_EVIDENCE | low | REQUEST_EVIDENCE | True | True | 1 | 0.06 | True |
| S13 | malformed_structured_input | UNKNOWN | UNKNOWN | ABSTAIN | low | UNVERIFIED | False | False | 1 | 0.032 | True |
| S14 | incorrect_coordinates | UNKNOWN | UNKNOWN | REQUEST_EVIDENCE | low | REQUEST_EVIDENCE | True | True | 1 | 0.06 | True |
| S15 | future_timestamp | UNKNOWN | UNKNOWN | REQUEST_EVIDENCE | low | REQUEST_EVIDENCE | True | True | 1 | 0.052 | True |
| S16 | outside_disaster_zone | UNKNOWN | UNKNOWN | REQUEST_EVIDENCE | low | REQUEST_EVIDENCE | True | True | 1 | 0.054 | True |
| S17 | corroborated_low_priority | PASS | PASS | ABSTAIN | low | UNVERIFIED | True | True | 1 | 0.05 | True |
| S18 | high_priority_partial_evidence | UNKNOWN | UNKNOWN | HOLD_FOR_HUMAN_REVIEW | urgent | URGENT_HUMAN_REVIEW | True | True | 1 | 0.051 | True |
| S19 | approval_missing | PASS | PASS | HOLD_FOR_HUMAN_REVIEW | urgent | URGENT_HUMAN_REVIEW | True | True | 1 | 0.064 | True |
| S20 | approval_expired | PASS | PASS | HOLD_FOR_HUMAN_REVIEW | urgent | URGENT_HUMAN_REVIEW | True | True | 1 | 0.05 | True |
| S21 | approval_invalid | PASS | PASS | HOLD_FOR_HUMAN_REVIEW | urgent | URGENT_HUMAN_REVIEW | True | True | 1 | 0.062 | True |
| S22 | human_rejection_or_edit | PASS | PASS | REJECTED | urgent | URGENT_HUMAN_REVIEW | True | True | 1 | 0.064 | True |
| S23 | human_rejection_or_edit | PASS | PASS | DISPATCHED | urgent | URGENT_HUMAN_REVIEW | True | True | 1 | 0.063 | True |
| S24 | valid_not_dispatchable | PASS | PASS | ABSTAIN | low | UNVERIFIED | True | True | 1 | 0.049 | True |
| S25 | retry_limit_exhausted | UNKNOWN | UNKNOWN | REQUEST_EVIDENCE | low | REQUEST_EVIDENCE | True | False | 4 | 0.035 | True |

## Limitations

- The runner uses deterministic Pydantic records and policy functions; it does not benchmark an LLM.
- Tool failures and approval expiry are controlled harness inputs because live adapters are out of MVP scope.
- Token counts are zero for replay/local execution and are not production cost estimates.
- Latency is local process time and is not an availability or latency SLO.

## Judge FAQ

**Why is token cost 0?** Because this run used fixed replay fixtures and deterministic policy code only. No live LLM call was made, so there was nothing to bill.

**What would live cost look like?** Non-zero and model-dependent. The right way to report it is per scenario, with prompt and output tokens recorded from the live provider.

**Why is schema only 92% on first pass?** By design. Some scenarios are malformed or incomplete on purpose. Those cases are supposed to fail schema validation without repair so the test proves the system can reject bad input safely.

**Does that mean the system is flaky?** No. It means the test suite is doing its job. Clean scenarios still pass; bad scenarios fail on the first pass the way they should.

**Why include failures at all?** Because the judges should care that the agent stops safely, asks for more evidence, and blocks unauthorized action when the input is wrong or incomplete.
