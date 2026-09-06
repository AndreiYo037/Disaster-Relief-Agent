"""Build phase D — 30–31 Aug inundation and shelters.

Carries phase-C rest (breaches open, B7 ground truth failed / belief uncertain)
and fills HUD planning-district bowls toward the 31 Aug table. Dome and
Convention Center occupancy follow the population clock. Murphy Oil is an
entity patch; the contamination field is already gated by the script bind.
Does not rewrite t0.json. Does not antedate riverfront fires (p4-fires).
"""
from __future__ import annotations

import copy
from datetime import datetime
from typing import Any

from .catalog import ENTITIES_SPEC
from .landfall import GAP_KEYS, landfall_delta
from .population_clock import DOME, MORIAL, _last
from .snapshot import district_flood_metrics, hud_weighted_depth_m, load_hud_flood, load_parameters, pv

T0 = datetime.fromisoformat("2005-08-31T08:00:00-05:00")
B7_RECORDED = datetime.fromisoformat("2005-08-31T09:20:00-05:00")

# Remaining gap from end-of-C bowls to the HUD 31 Aug ceiling.
# 30 Aug is still rising (USGS Circ. 1306 ch. 3H ~85e9 gal that day);
# p3-max-inundation sits on the HUD vintage date.
FILL: tuple[tuple[str, float], ...] = (
    ("p3-80pct", 0.52),
    ("p3-nws-9th-arabi", 0.62),
    ("p3-bowl-rising", 0.82),
    ("p3-max-inundation", 1.0),
)

# (event_id, entity_id, state, source_key)
FLIPS: tuple[tuple[str, str, str, str], ...] = (
    ("p3-80pct", "zone:B", "critical", "hud-noaa-flood-2005-08-31"),
    ("p3-80pct", "shelter:morial", "damaged", "design:gap-fill"),
    ("p3-nws-9th-arabi", "breach:ihnc", "critical", "usace-ipet"),
    ("p3-nws-9th-arabi", "hospital:chalmette", "inaccessible", "design:gap-fill"),
    ("p3-jtf-katrina", "personnel:ng", "critical", "design:gap-fill"),
    ("p3-murphy-oil", "fuel:depot", "critical", "epa-murphy-oil-katrina"),
    ("p3-rescues-thousands", "personnel:ng", "critical", "design:gap-fill"),
    ("p3-guard-ramp", "personnel:ng", "critical", "design:gap-fill"),
    ("p3-dome-uninhabitable", "shelter:dome", "critical", "design:gap-fill"),
    ("p3-dome-to-cc", "shelter:morial", "critical", "design:gap-fill"),
    ("p3-dome-to-cc", "zone:C", "critical", "design:gap-fill"),
    ("p3-cc-crisis", "shelter:morial", "critical", "house-select-katrina"),
    ("p3-cc-crisis", "zone:C", "critical", "house-select-katrina"),
    ("p3-cc-crisis", "food:pod", "critical", "design:gap-fill"),
    ("p3-cc-crisis", "medicine:cache", "critical", "design:gap-fill"),
)

# Snapshot logistics beat after 31 Aug 08:00 — do not override t0/reroute convoy IDs.
LOGISTICS = frozenset({
    "bridge:B7", "route:R14", "route:R22", "bridge:us11", "truck:17", "warehouse:W1",
})


def _when(ev: dict) -> datetime:
    return datetime.fromisoformat(ev["t"])


def _elapsed_ids(idx: int, script: dict) -> set[str]:
    return {ev["id"] for ev in script["events"][: idx + 1]}


def _last_phase2_idx(script: dict) -> int:
    last = 0
    for i, ev in enumerate(script["events"]):
        if ev.get("phase") == 2:
            last = i
    return last


def _fill_u(elapsed: set[str]) -> float:
    u = 0.0
    for eid, val in FILL:
        if eid in elapsed:
            u = val
    return u


def hud_ceiling_features() -> list[dict]:
    """31 Aug HUD planning-district bowls (housing-unit wet_frac / depth). Not MOTF."""
    hud = load_hud_flood()
    features = []
    for d in hud["districts"]:
        if d["flooded_units"] <= 0:
            continue
        depth_m, wet_frac = district_flood_metrics(d)
        features.append({
            "id": d["id"], "name": d["name"], "ring": d["ring"],
            "depth_m": round(depth_m, 3),
            "wet_frac": round(wet_frac, 4),
            "flooded_units": d["flooded_units"], "total_units": d["total_units"],
        })
    return features


def _blend(start: list[dict], ceiling: list[dict], u: float) -> list[dict]:
    by_s = {f["id"]: f for f in start}
    out = []
    for c in ceiling:
        s = by_s.get(c["id"])
        sd = s["depth_m"] if s else 0.0
        sw = s["wet_frac"] if s else 0.0
        out.append({
            **c,
            "depth_m": round(sd + u * (c["depth_m"] - sd), 3),
            "wet_frac": round(min(1.0, sw + u * (c["wet_frac"] - sw)), 4),
        })
    return out


def _rest_patch(eid: str) -> dict[str, Any]:
    state = "full" if eid == "warehouse:W1" else "operational"
    if eid == "power:waterford":
        state = "damaged"
    gap = eid == "power:waterford"
    patch: dict[str, Any] = {
        "state": state,
        "ground_truth_state": state,
        "verification_status": "unverified" if gap else "verified",
        "label": "inundation-rest",
        "source_key": "design:gap-fill" if gap else "landfall-rest",
    }
    if gap:
        patch["gap_fill"] = True
    return patch


def _apply_flip(entities: dict[str, dict], eid: str, state: str, src: str) -> None:
    prev = entities.get(eid) or {}
    patch: dict[str, Any] = {
        **prev,
        "state": state,
        "ground_truth_state": prev.get("ground_truth_state", state),
        "source_key": src,
        "verification_status": "unverified" if src in GAP_KEYS else "verified",
        "label": "design:gap-fill" if src in GAP_KEYS else "known",
    }
    if src in GAP_KEYS:
        patch["gap_fill"] = True
    else:
        patch.pop("gap_fill", None)
    entities[eid] = patch


def inundation_delta(idx: int, script: dict | None = None) -> dict[str, Any] | None:
    if script is None:
        from .replay import load_script
        script = load_script()
    events = script["events"]
    if not events or idx < 0 or idx >= len(events):
        return None
    ev = events[idx]
    if ev.get("phase") != 3:
        return None

    last_p2 = _last_phase2_idx(script)
    base = landfall_delta(last_p2, script)
    if not base:
        return None

    when = _when(ev)
    elapsed = _elapsed_ids(idx, script)
    u = _fill_u(elapsed)
    params = load_parameters()
    dome_cap = pv(params, "shelters", "superdome_capacity")
    cc_cap = pv(params, "shelters", "convention_center_capacity")
    dome_n, dome_src = _last(DOME, elapsed)
    cc_n, cc_src = _last(MORIAL, elapsed)

    out = copy.deepcopy(base)
    entities: dict[str, dict] = out["entities"]
    for spec in ENTITIES_SPEC:
        eid = spec["entity_id"]
        if eid not in entities:
            entities[eid] = _rest_patch(eid)
    if "fuel:depot" in entities and "p3-murphy-oil" not in elapsed:
        entities["fuel:depot"] = _rest_patch("fuel:depot")

    for event_id, eid, state, src in FLIPS:
        if event_id in elapsed:
            _apply_flip(entities, eid, state, src)

    if "shelter:dome" in entities:
        entities["shelter:dome"]["attributes"] = {
            **(entities["shelter:dome"].get("attributes") or {}),
            "occupancy": dome_n,
            "capacity": dome_cap,
        }
        if dome_src in GAP_KEYS:
            entities["shelter:dome"]["gap_fill"] = True
            entities["shelter:dome"]["verification_status"] = "unverified"
        elif dome_n:
            entities["shelter:dome"]["source_key"] = dome_src
    if "shelter:morial" in entities:
        entities["shelter:morial"]["attributes"] = {
            **(entities["shelter:morial"].get("attributes") or {}),
            "occupancy": cc_n,
            "capacity": cc_cap,
        }
        if cc_src in GAP_KEYS:
            entities["shelter:morial"]["gap_fill"] = True
            entities["shelter:morial"]["verification_status"] = "unverified"
        elif cc_n:
            entities["shelter:morial"]["source_key"] = cc_src
            entities["shelter:morial"].pop("gap_fill", None)
            entities["shelter:morial"]["verification_status"] = "verified"
            entities["shelter:morial"]["label"] = "known"

    if when >= T0:
        for eid in LOGISTICS:
            entities.pop(eid, None)

    start_feats = (base.get("flood") or {}).get("wet_mask", {}).get("features") or []
    features = _blend(start_feats, hud_ceiling_features(), u)
    start_stage = float((base.get("flood") or {}).get("stage_m") or 0)
    hud_stage = hud_weighted_depth_m("lower-9th")
    stage_m = start_stage + u * (hud_stage - start_stage)

    bind = next((b for b in (ev.get("binds") or []) if not str(b).startswith("hazards.")), None)
    glyph = None
    if bind:
        glyph = {
            "event_id": ev["id"],
            "event_type": "hazard_expansion" if "flood" in (ev.get("layers") or []) else "infrastructure_damage",
            "subject_entity": bind,
            "verification_status": "verified",
            "decay": 0.85,
            "source_event_id": ev["id"],
        }

    pulse = {
        "band": "CRITICAL",
        "b7_state": "inaccessible",
        "b7_belief": "uncertain" if when < B7_RECORDED else "inaccessible",
        "water_hours": 8 if "p3-cc-crisis" in elapsed else 10,
        "shortage_prob": 0.85 if "p3-cc-crisis" in elapsed else 0.72,
    }
    if when < T0:
        pulse["truck_status"] = "N/A"

    out.update({
        "build_phase": "D",
        "t": ev["t"],
        "event_id": ev["id"],
        "entities": entities,
        "flood": {
            "stage_m": round(stage_m, 3),
            "d_stage_dt": 0.0 if u >= 1.0 else round(0.10 * (1.0 - u), 3),
            "gauge_id": "gauge:ihnc",
            "wet_mask": {
                "type": "MultiPolygon",
                "coordinates": [[f["ring"]] for f in features],
                "features": features,
                "source_key": "hud-noaa-flood-2005-08-31",
                "vintage": "hud-districts-2005-08-31",
                "flooded_units": sum(f["flooded_units"] for f in features),
                "note": (
                    "Phase D: HUD 31 Aug planning-district rings, interpolated from end-of-C "
                    f"IHNC-scaled bowls (fill={u:.2f}). Not MOTF polygons. USGS Circ. 1306 ch. 3H "
                    "city-volume figures are the rising-water language, not this GIS."
                ),
            },
            "paths": [],
        },
        "roads_wet": True,
        "glyph": glyph,
        "r34_on_nola": "p3-td" not in elapsed,
        "pulse": pulse,
        "world_note": (
            f"inundation · HUD fill {u:.2f} · Dome {dome_n:,} / CC {cc_n:,} · "
            "t0 snapshot unchanged"
        ),
    })
    return out
