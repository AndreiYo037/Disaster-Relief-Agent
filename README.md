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

Open http://127.0.0.1:8081/ — scrub t0 → B7 collapse (truck SUSPENDS) → R22 approved.

Frozen snapshots live in `data/katrina/snapshots/`. The renderer never invents state.

Optional Vite toolchain (if you have a working npm registry): `cd web && npm install && npm run dev`.

## Snapshot API (Phase 2)

```bash
$env:PYTHONPATH="src"
python -m crisis_os.app          # http://127.0.0.1:8080/api/state?keyframe=t0
python -m crisis_os.runner       # closed loop; regenerates snapshots
python -m crisis_os.seed
```

`GET /api/state?keyframe=t0|b7|reroute` and `GET /api/state_at?ts=` emit the same
document the Vite app already consumes (proxied from `/api` in dev).

## Layout

```
data/katrina/parameters.json   all numeric inputs (cited or marked unverified)
data/katrina/world/            schema, registry, catalog dumps
data/katrina/snapshots/        t0 / b7 / reroute
web/                           Vite + MapLibre + deck.gl diorama
src/crisis_os/                 catalog, snapshot builder, SQLite, layers, graph
docs/                          3d-diorama, population-density, entity-rendering
```

Set `CRISIS_OS_LLM_PROVIDER=bedrock` later for Claude-on-Bedrock narration. Decisions
stay deterministic either way.
