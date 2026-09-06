"""Katrina event-script replay clock (build phases A–C).

The replay clock is the compiled 84-event script, sorted by t. Tick i is
events[i] — never a belief keyframe, never file-order if that disagrees
with time. Phase C attaches a landfall world_delta on 29 Aug; t0 JSON is
not rewritten. Hazard fields follow elapsed script binds.
"""
from __future__ import annotations

import json
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from .catalog import ENTITIES_SPEC
from .cyclone import pose_at as cyclone_pose_at
from .gltf_models import CATEGORIES

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "data" / "katrina" / "sourced" / "katrina_event_script.json"
PUBLIC_SCRIPT_PATH = ROOT / "web" / "public" / "data" / "sourced" / "katrina_event_script.json"

BELIEF_ORDER = ("b7", "t0", "reroute")
REGISTRY_CATEGORIES = (
    "transport", "health", "humanitarian", "utilities", "supply", "hazard",
)
FIELD_LAYERS = ("cyclone", "flood", "fire", "contamination", "population")
HAZARD_PREFIX = "hazards."
CLOCK_RULE = (
    "replay clock = katrina_event_script.json events sorted by t; "
    "one tick per event; map follows that event's t and elapsed binds"
)


def parse_cdt(ts: str) -> datetime:
    return datetime.fromisoformat(ts)


def order_events(events: list[dict]) -> list[dict]:
    """Stable time order — this is the replay clock sequence."""
    ordered = sorted(events, key=lambda e: e["t"])
    out = []
    for i, ev in enumerate(ordered):
        row = dict(ev)
        row["seq"] = i
        out.append(row)
    return out


@lru_cache(maxsize=4)
def _load_script(mtime_ns: int) -> dict:
    data = json.loads(SCRIPT_PATH.read_text(encoding="utf-8"))
    events = order_events(list(data["events"]))
    data = {**data, "events": events}
    kf = data.get("demo_keyframes") or {}
    data["_belief_times"] = {
        name: parse_cdt(kf[name]) for name in BELIEF_ORDER if name in kf
    }
    data["_id_index"] = {e["id"]: i for i, e in enumerate(events)}
    data["_entity_type"] = {e["entity_id"]: e["type"] for e in ENTITIES_SPEC}
    return data


def load_script() -> dict:
    return _load_script(SCRIPT_PATH.stat().st_mtime_ns)


def event_count(script: dict | None = None) -> int:
    return len((script or load_script())["events"])


def phase_counts(script: dict | None = None) -> dict[int, int]:
    script = script or load_script()
    counts: dict[int, int] = {}
    for ev in script["events"]:
        counts[ev["phase"]] = counts.get(ev["phase"], 0) + 1
    return counts


def nearest_belief_keyframe(t: str | datetime, script: dict | None = None) -> str:
    """Pin the world to the nearest of the three logistics snapshots."""
    script = script or load_script()
    dt = parse_cdt(t) if isinstance(t, str) else t
    times: dict[str, datetime] = script["_belief_times"]
    best = BELIEF_ORDER[0]
    best_d: float | None = None
    for name in BELIEF_ORDER:
        d = abs((dt - times[name]).total_seconds())
        if best_d is None or d < best_d:
            best, best_d = name, d
        elif d == best_d and times[name] < times[best]:
            best = name
    return best


def belief_for_event(ev: dict, script: dict | None = None) -> str:
    """Logistics snapshot at this tick. Driven by event time, not file order.

    demo_keyframe tags are hints for the three logistics beats. They do not
    pin a later tick to an earlier snapshot when the clock has moved on.
    """
    return nearest_belief_keyframe(ev["t"], script)


def elapsed_binds(idx: int, script: dict | None = None) -> list[str]:
    """Binds from events[0] through events[idx], first-seen order."""
    script = script or load_script()
    events = script["events"]
    i = max(0, min(int(idx), len(events) - 1))
    seen: list[str] = []
    found: set[str] = set()
    for ev in events[: i + 1]:
        for bind in ev.get("binds") or []:
            if bind not in found:
                found.add(bind)
                seen.append(bind)
    return seen


def fields_on(idx: int, script: dict | None = None) -> dict[str, bool]:
    """Hazard fields the sequence has already introduced (no chrome checkboxes)."""
    elapsed = set(elapsed_binds(idx, script))
    return {
        "cyclone": True,
        "flood": "hazards.flood" in elapsed,
        "fire": "hazards.fire" in elapsed,
        "contamination": "hazards.contamination" in elapsed,
    }


def index_at_time(t: str, script: dict | None = None) -> int:
    """Last event with timestamp <= t, else 0 if t is before the first event."""
    script = script or load_script()
    dt = parse_cdt(t)
    idx = 0
    for i, ev in enumerate(script["events"]):
        if parse_cdt(ev["t"]) <= dt:
            idx = i
        else:
            break
    return idx


def index_for_phase(phase: int, script: dict | None = None) -> int:
    script = script or load_script()
    for i, ev in enumerate(script["events"]):
        if ev["phase"] == phase:
            return i
    return 0


def classify_bind(bind: str, script: dict | None = None) -> tuple[str, str]:
    """Return (kind, name) where kind is category | field | unknown."""
    script = script or load_script()
    if bind.startswith(HAZARD_PREFIX):
        field = bind[len(HAZARD_PREFIX):]
        if field == "landslide":
            return ("field", "landslide")
        return ("field", field)
    typ = script["_entity_type"].get(bind)
    if typ:
        return ("category", CATEGORIES.get(typ, "other"))
    return ("unknown", bind)


def scan_binds(binds: list[str], script: dict | None = None) -> dict[str, list[str]]:
    script = script or load_script()
    found: dict[str, list[str]] = {k: [] for k in (*REGISTRY_CATEGORIES, *FIELD_LAYERS)}
    found["unknown"] = []
    for bind in binds:
        kind, name = classify_bind(bind, script)
        if kind == "category" and name in found:
            found[name].append(bind)
        elif kind == "field" and name in found:
            found[name].append(bind)
        else:
            found["unknown"].append(bind)
    return found


def phase_category_scan(phase: int, script: dict | None = None) -> dict[str, Any]:
    """Every asset category for a story phase: bound ids or gap."""
    script = script or load_script()
    binds: list[str] = []
    for ev in script["events"]:
        if ev["phase"] == phase:
            binds.extend(ev.get("binds") or [])
    grouped = scan_binds(binds, script)
    rows = {}
    for cat in REGISTRY_CATEGORIES:
        ids = grouped[cat]
        rows[cat] = {"status": "bound" if ids else "gap", "binds": ids}
    for field in FIELD_LAYERS:
        ids = grouped[field]
        rows[field] = {"status": "bound" if ids else "gap", "binds": ids}
    if grouped["unknown"]:
        rows["unknown"] = {"status": "unmapped", "binds": grouped["unknown"]}
    return {
        "phase": phase,
        "rule": "search every asset category; gap = look up or design:gap-fill before paint",
        "categories": rows,
    }


EVENT_KEYS = ("id", "seq", "phase", "t", "t_label", "title", "layers", "binds", "demo_keyframe")


def _event_view(ev: dict) -> dict:
    return {k: ev[k] for k in EVENT_KEYS if k in ev}


def replay_at(
    t: str | None = None,
    event_id: str | None = None,
    index: int | None = None,
    script: dict | None = None,
) -> dict:
    script = script or load_script()
    events = script["events"]
    if event_id is not None:
        idx = script["_id_index"].get(event_id, 0)
    elif index is not None:
        idx = max(0, min(int(index), len(events) - 1))
    elif t:
        idx = index_at_time(t, script)
    else:
        idx = index_at_time(script["demo_keyframes"]["t0"], script)
    ev = events[idx]
    belief = belief_for_event(ev, script)
    phase_meta = next((p for p in script["phases"] if p["id"] == ev["phase"]), None)
    pose = cyclone_pose_at(ev["t"])
    on = fields_on(idx, script)
    from .landfall import world_delta_for
    from .population_clock import population_delta
    delta = world_delta_for(idx, script)
    pop = population_delta(idx, script)
    if ev.get("phase") == 0:
        build = "B"
        note = f"replay clock (script seq {idx + 1}/{len(events)}) · cyclone pose · NOLA frozen at {belief}"
    elif delta:
        build = delta.get("build_phase") or "C"
        note = delta.get("world_note") or (
            f"replay clock (script seq {idx + 1}/{len(events)}) · world still at {belief}"
        )
    else:
        build = "A"
        note = f"replay clock (script seq {idx + 1}/{len(events)}) · world still at {belief}"
    out = {
        "build_phase": build,
        "clock_rule": CLOCK_RULE,
        "t": ev["t"],
        "event_index": idx,
        "event_count": len(events),
        "event": _event_view(ev),
        "phase": phase_meta,
        "belief_keyframe": belief,
        "belief_rule": "nearest of t0|b7|reroute by event t; phases C–E patch landfall/inundation/unwatering entities without rewriting t0",
        "world_note": note,
        "elapsed_binds": elapsed_binds(idx, script),
        "fields_on": on,
        "cyclone": pose,
        "event_scan": scan_binds(ev.get("binds") or [], script),
        "phase_scan": phase_category_scan(ev["phase"], script),
        "population_delta": pop,
    }
    out["event"]["population_delta"] = pop
    if delta:
        out["world_delta"] = delta
        out["event"]["world_delta"] = delta
    return out


def script_payload() -> dict:
    script = load_script()
    from .landfall import world_delta_for
    from .population_clock import population_delta
    events = []
    for i, e in enumerate(script["events"]):
        row = _event_view(e)
        delta = world_delta_for(i, script)
        if delta:
            row["world_delta"] = delta
        row["population_delta"] = population_delta(i, script)
        events.append(row)
    return {
        "dataset_id": script["dataset_id"],
        "source_key": script["source_key"],
        "timezone": script["timezone"],
        "status": script["status"],
        "build_phase": "E",
        "clock_rule": CLOCK_RULE,
        "world_note": "replay clock = 84-event script · C landfall · D inundation · E unwatering/power · t0 B7 belief unchanged",
        "demo_keyframes": script["demo_keyframes"],
        "phases": script["phases"],
        "t_start": events[0]["t"],
        "t_end": events[-1]["t"],
        "event_count": len(events),
        "phase_counts": phase_counts(script),
        "events": events,
    }
