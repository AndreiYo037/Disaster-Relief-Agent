# Crisis OS

Hurricane Katrina (New Orleans, 2005) crisis operating system: a 3D World Model
diorama that is a **pure read** of `WorldSnapshot` JSON, plus a deterministic
agentic loop that **writes the same schema**.

LLM involvement decreases toward real-world action. `mint_permit(plan, human_decision)`
has no path around a human.

## 3D World Model (Phase 1)

```bash
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
$env:PYTHONPATH="src"
python -m crisis_os.app
```

Open http://127.0.0.1:8081/ — the footer scrubber is the 84-event Katrina script
(`data/katrina/sourced/katrina_event_script.json`). Frozen belief snapshots stay
in `data/katrina/snapshots/` (`t0` / `b7` / `reroute`). The renderer never invents state.

Optional Vite toolchain (if you have a working npm registry): `cd web && npm install && npm run dev`.

## Snapshot API (Phase 2)

```bash
$env:PYTHONPATH="src"
python -m crisis_os.app          # http://127.0.0.1:8081/api/state?keyframe=t0
python -m crisis_os.runner       # demo spine + agentic overlay (does not rewrite snapshots)
python -m crisis_os.seed
```

`GET /api/replay` and `GET /api/replay/at` drive the diorama clock.
`GET /api/state?keyframe=t0|b7|reroute` returns the frozen snapshot plus an additive
`agentic` projection. `GET /api/state_at?ts=` is the same document keyed by time.

## Layout

```
data/katrina/parameters.json   all numeric inputs (cited or marked unverified)
data/katrina/world/            schema, registry, catalog dumps
data/katrina/snapshots/        t0 / b7 / reroute
web/                           Vite + MapLibre + deck.gl diorama
src/crisis_os/                 catalog, snapshot builder, SQLite, layers, graph
docs/                          asset-definitions, 3d-diorama, population-density, entity-rendering, katrina-replay-build-phases
```

Set `CRISIS_OS_LLM_PROVIDER=bedrock` later for Claude-on-Bedrock narration. Decisions
stay deterministic either way.
