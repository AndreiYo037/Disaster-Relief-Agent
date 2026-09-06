# CrisisIO Agentic Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the offline Katrina replay agentic layer with exactly 15 named LangGraph agents, typed append-only state, deterministic safety policy, persistence, auditability, and additive `WorldSnapshot` projections.

**Architecture:** Pydantic models define immutable record contracts. A small deterministic runtime runs four source/verification/evaluation lanes in parallel, then Dispatch, Orchestrator, and Summariser. LangGraph is the execution path with SQLite checkpoints; a sequential fallback keeps local tests runnable when the optional runtime package is unavailable.

**Tech Stack:** Python 3.11+, Pydantic 2, LangGraph, SQLite, `tomllib`, JSON replay fixtures, pytest.

**Spec:** `docs/superpowers/specs/2026-09-06-agentic-layer-crisisio-prd.md`

## Global Constraints

- Exactly 15 named agent nodes from the PRD roster.
- Parallel collections are reducer-backed, append-only, provenance-preserving, and conflict-detecting.
- Deterministic code owns validation, verification, scoring, priority, deduplication, routing, lifecycle, and approval gates.
- Replay uses `t0`, `b7`, and `reroute` without AWS credentials.
- Non-`PASS` incidents remain visible in the unverified queue and cannot be executable dispatch.
- Physical actions enter `DISPATCHED` only after an immutable coordinator decision.
- No frontend wiring, live adapters, RAG, streaming, or autonomous actuation.

### Task 1: Typed contracts and deterministic policy

**Files:**
- Modify: `src/crisis_os/models.py`
- Create: `src/crisis_os/agentic.py`
- Test: `tests/test_agentic.py`

- [ ] Write tests for model validation, reducer conflicts, five-check verdicts, priority thresholds, deduplication, and approval gating.
- [ ] Run the focused tests and verify they fail because the new contracts do not exist.
- [ ] Add the Pydantic records, reducer, deterministic verification/evaluation/priority/deduplication helpers, tool allow-list, retry envelope, and approval transition.
- [ ] Run the focused tests and verify they pass.

### Task 2: Fixture adapters and 15-node graph

**Files:**
- Modify: `src/crisis_os/graph.py`
- Create: `data/katrina/agent-fixtures.json`
- Test: `tests/test_agentic.py`

- [ ] Add four replay fixture lanes for all three keyframes.
- [ ] Build the canonical `ingest -> source -> verification -> evaluation -> dispatch -> orchestrator -> summariser` topology with all 15 named agent nodes.
- [ ] Execute the four lanes through typed records and append-only reducers; keep failures local to a lane.
- [ ] Run tests proving roster, topology, replay output, partial failure, and bounded feedback/review loops.

### Task 3: Persistence, runtime validation, and projection

**Files:**
- Modify: `src/crisis_os/schema.sql`
- Modify: `src/crisis_os/db.py`
- Modify: `src/crisis_os/config.py`
- Modify: `src/crisis_os/runner.py`
- Test: `tests/test_agentic.py`

- [ ] Add normalized agent tables and audit/metric persistence while preserving existing world-model tables.
- [ ] Add Bedrock configuration validation and a contract-mock model boundary.
- [ ] Persist replay records/checkpoints where the LangGraph SQLite saver is available.
- [ ] Add additive agentic fields to replay projections and make the runner execute the three keyframes.
- [ ] Run the full Python suite and the web build.

## Verification

- `PYTHONPATH=src pytest -q`
- `PYTHONPATH=src python -m crisis_os.runner`
- `cd web && npm run build`
- Assert the graph roster contains exactly the 15 PRD agent names and every node has an incoming/outgoing link in the canonical path.
