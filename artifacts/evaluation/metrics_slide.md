# CrisisIO Evaluation: Slide Summary

Tested 25 disaster scenarios against predefined synthetic Katrina-inspired outcomes. The deterministic agentic layer separated confirmed facts from uncertainty, requested evidence when needed, handled duplicates, and enforced human approval before dispatch.

- Decision accuracy: 100.0%
- False dispatches: 0
- Missed urgent incidents: 0
- Schema validation first-pass rate: 92.0%
- Tool-call success rate: 91.3% (21/23 attempted calls)
- Average end-to-end latency: 0.112 ms
- Human approval-gate success: 100.0%

Prototype boundary: local deterministic policy and controlled failure fixtures only; token cost is not a production estimate.
Schema failures are intentional in malformed-input cases so the judges can see the system reject bad records without repair.
