"""Build phase C — 29 Aug landfall hour world-delta.

Scrubbing phase 2 opens sourced breaches in script order and scales HUD bowls
from the IHNC Lock hydrograph. Twin Span ground truth can fail at 06:00 CDT
while belief stays uncertain (t0 JSON is not rewritten).

Entity meshes that are not in this tick table stay on the nearest belief
snapshot. Gap-fills are labeled and never marked verified.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from .snapshot import (
    district_flood_metrics, interpolate_hydrograph, load_hud_flood,
    load_parameters, pv,
)
from .population_clock import DOME, _last as _occ_last

LANDFALL_END = datetime.fromisoformat("2005-08-29T18:00:00-05:00")
HYDRO_START = datetime.fromisoformat("2005-08-29T05:00:00-05:00")
HYDRO_PEAK = datetime.fromisoformat("2005-08-29T09:00:00-05:00")
B7_VALID = datetime.fromisoformat("2005-08-29T06:00:00-05:00")

# Resting landfall-morning state for entities this sprint ticks.
REST = {
    "breach:ihnc-west": "operational",
    "breach:ihnc": "operational",
    "breach:london": "operational",
    "breach:london-n": "operational",
    "breach:17th": "operational",
    "zone:B": "operational",
    "route:R14": "operational",
    "shelter:dome": "operational",
    "infra:power": "operational",
    "infra:pumpInd": "operational",
    "infra:pump6": "operational",
    "hospital:chalmette": "operational",
    "power:michoud": "operational",
    "power:ninemile": "operational",
    "power:waterford": "damaged",
    "comms:eoc": "operational",
    "personnel:ng": "operational",
    "gauge:ihnc": "operational",
}

# (event_id, entity_id, state, source_key)
FLIPS: tuple[tuple[str, str, str, str], ...] = (
    ("p2-ihnc-overtop-west", "breach:ihnc-west", "critical", "usace-ipet"),
    ("p2-ihnc-east-monolith", "breach:ihnc", "critical", "usace-ipet"),
    ("p2-ihnc-east-monolith", "zone:B", "uncertain", "usace-ipet"),
    ("p2-twin-span", "route:R14", "inaccessible", "usgs-circ-1306-ch3d"),
    ("p2-overtop-ihnc-mrgo", "breach:ihnc", "critical", "usace-ipet"),
    ("p2-overtop-ihnc-mrgo", "breach:ihnc-west", "critical", "usace-ipet"),
    ("p2-overtop-ihnc-mrgo", "zone:B", "uncertain", "usace-ipet"),
    ("p2-dome-power", "shelter:dome", "critical", "design:gap-fill"),
    ("p2-dome-power", "infra:power", "inaccessible", "design:gap-fill"),
    ("p2-pump2", "infra:pumpInd", "inaccessible", "usace-ipet"),
    ("p2-pump2", "infra:pump6", "damaged", "usace-ipet"),
    ("p2-london-south", "breach:london", "critical", "usace-ipet"),
    ("p2-17th-begins", "breach:17th", "damaged", "usace-ipet"),
    ("p2-ihnc-second-hole", "breach:ihnc", "critical", "usace-ipet"),
    ("p2-ihnc-second-hole", "zone:B", "critical", "usace-ipet"),
    ("p2-london-north", "breach:london-n", "critical", "usace-ipet"),
    ("p2-17th-open", "breach:17th", "critical", "usace-ipet"),
    ("p2-l9-stbernard-depth", "zone:B", "critical", "usace-ipet"),
    ("p2-l9-stbernard-depth", "hospital:chalmette", "inaccessible", "design:gap-fill"),
    ("p2-entergy-peak", "infra:power", "inaccessible", "design:gap-fill"),
    ("p2-entergy-peak", "power:michoud", "inaccessible", "design:gap-fill"),
    ("p2-entergy-peak", "power:ninemile", "damaged", "design:gap-fill"),
    ("p2-entergy-peak", "power:waterford", "damaged", "design:gap-fill"),
    ("p2-usace-dhs", "comms:eoc", "critical", "design:gap-fill"),
    ("p2-rooftop-start", "personnel:ng", "critical", "design:gap-fill"),
    ("p2-catastrophic-flood", "zone:B", "critical", "hud-noaa-flood-2005-08-31"),
    ("p2-dome-conditions", "shelter:dome", "critical", "whitehouse-katrina-lessons-ch3"),
)

GAP_KEYS = frozenset({"design:gap-fill"})


def _when(ev: dict) -> datetime:
    return datetime.fromisoformat(ev["t"])


def in_landfall_window(ev: dict) -> bool:
    if not ev:
        return False
    if ev.get("phase") == 2:
        return True
    t = _when(ev)
    return datetime.fromisoformat("2005-08-29T04:30:00-05:00") <= t <= LANDFALL_END


def _elapsed_ids(idx: int, script: dict) -> set[str]:
    return {ev["id"] for ev in script["events"][: idx + 1]}


def _states_at(elapsed: set[str]) -> dict[str, tuple[str, str]]:
    """entity_id -> (state, source_key); later flips win."""
    out = {eid: (st, "landfall-rest") for eid, st in REST.items()}
    for event_id, eid, state, src in FLIPS:
        if event_id in elapsed:
            out[eid] = (state, src)
    return out


def _bowl_fill(when: datetime) -> float:
    """0–1 fill of morning HUD bowls. Rises with the hydrograph; does not drain after peak."""
    if when < HYDRO_START:
        return 0.18
    span = (HYDRO_PEAK - HYDRO_START).total_seconds()
    u = min(1.0, max(0.0, (when - HYDRO_START).total_seconds() / span))
    fill = 0.22 + 0.63 * u
    if when > HYDRO_PEAK:
        extra = min(0.15, (when - HYDRO_PEAK).total_seconds() / (9 * 3600) * 0.15)
        fill = min(1.0, 0.85 + extra)
    return fill


def _flood_features(elapsed: set[str], when: datetime) -> tuple[list[dict], float]:
    hud = load_hud_flood()
    fill = _bowl_fill(when)
    want: list[tuple[str, float]] = []
    if "p2-ihnc-overtop-west" in elapsed:
        want.append(("lower-9th", 0.16))
    if "p2-ihnc-east-monolith" in elapsed:
        want = [("lower-9th", fill)]
    if "p2-17th-begins" in elapsed:
        want.append(("lakeview", fill * 0.45))
    if "p2-17th-open" in elapsed:
        want = [(did, fr) for did, fr in want if did != "lakeview"]
        want.append(("lakeview", fill))
    if "p2-catastrophic-flood" in elapsed:
        extra = min(0.4, 0.15 + (when - HYDRO_PEAK).total_seconds() / (8 * 3600) * 0.25)
        seen = {did for did, _ in want}
        for d in hud["districts"]:
            if d["flooded_units"] <= 0 or d["id"] in seen:
                continue
            want.append((d["id"], extra))
    by_id = {d["id"]: d for d in hud["districts"]}
    features = []
    for did, scale in want:
        d = by_id.get(did)
        if not d:
            continue
        depth_m, wet_frac = district_flood_metrics(d)
        features.append({
            "id": d["id"], "name": d["name"], "ring": d["ring"],
            "depth_m": round(depth_m * scale, 3),
            "wet_frac": round(min(1.0, wet_frac * scale), 4),
            "flooded_units": d["flooded_units"], "total_units": d["total_units"],
        })
    return features, fill


def landfall_delta(idx: int, script: dict | None = None) -> dict[str, Any] | None:
    if script is None:
        from .replay import load_script
        script = load_script()
    events = script["events"]
    if not events or idx < 0 or idx >= len(events):
        return None
    ev = events[idx]
    if not in_landfall_window(ev):
        return None
    when = _when(ev)
    elapsed = _elapsed_ids(idx, script)
    params = load_parameters()
    b7_from = pv(params, "chronology", "bridge_B7_collapse_valid_from")
    b7_rec = pv(params, "chronology", "bridge_B7_corroborated_recorded_at")
    occupancy = pv(params, "shelters", "superdome_occupancy_landfall")
    capacity = pv(params, "shelters", "superdome_capacity")
    stage_m, d_stage = interpolate_hydrograph(when)
    features, fill = _flood_features(elapsed, when)
    states = _states_at(elapsed)
    gt_failed = when >= B7_VALID or "p2-twin-span" in elapsed

    entities: dict[str, dict] = {}
    for eid, (state, src) in states.items():
        rest = src == "landfall-rest"
        patch: dict[str, Any] = {
            "state": state,
            "source_key": src,
            "verification_status": "unverified" if src in GAP_KEYS or rest else "verified",
            "label": "design:gap-fill" if src in GAP_KEYS else ("pre-failure" if rest else "known"),
        }
        if src in GAP_KEYS:
            patch["gap_fill"] = True
        if eid == "shelter:dome":
            n, _src = _occ_last(DOME, elapsed)
            patch["attributes"] = {"occupancy": n if n else occupancy, "capacity": capacity}
        if eid == "gauge:ihnc":
            patch["attributes"] = {
                "stage_m": round(stage_m, 3),
                "d_stage_dt": round(d_stage, 3),
            }
        entities[eid] = patch

    entities["bridge:B7"] = {
        "state": "uncertain",
        "ground_truth_state": "inaccessible" if gt_failed else "operational",
        "verification_status": "unverified",
        "label": "uncertain",
        "confidence": 0.55,
        "source_key": "usgs-circ-1306-ch3d",
        "valid_from": b7_from,
        "recorded_at": b7_rec,
        "note": (
            "Ground truth: Twin Span unusable at landfall morning (USGS Circ. 1306 ch. 3D). "
            "Belief stays uncertain until recorded_at 31 Aug 09:20. t0 snapshot is unchanged."
        ),
    }
    if gt_failed:
        entities["route:R14"] = {
            **entities.get("route:R14", {}),
            "state": "inaccessible",
            "ground_truth_state": "inaccessible",
            "source_key": "usgs-circ-1306-ch3d",
        }

    flood = {
        "stage_m": round(stage_m, 3),
        "d_stage_dt": round(d_stage, 3),
        "gauge_id": "gauge:ihnc",
        "wet_mask": {
            "type": "MultiPolygon",
            "coordinates": [[f["ring"]] for f in features],
            "features": features,
            "source_key": "hud-noaa-flood-2005-08-31",
            "vintage": "hud-districts × ihnc-lock-hydrograph-29aug",
            "flooded_units": sum(f["flooded_units"] for f in features),
            "note": (
                "Phase C: HUD planning-district rings scaled by IHNC Lock staff hydrograph "
                f"(usace-ipet). fill={fill:.2f}. Not MOTF polygons. 31 Aug table is the ceiling, not this hour's GIS."
            ),
        },
        "paths": [],
    }
    open_breach = any(
        entities.get(b, {}).get("state") in ("critical", "inaccessible", "damaged")
        for b in ("breach:ihnc", "breach:ihnc-west", "breach:17th", "breach:london", "breach:london-n")
    )
    glyph = None
    bind = (ev.get("binds") or [None])[0]
    if bind and not str(bind).startswith("hazards."):
        glyph = {
            "event_id": ev["id"],
            "event_type": "hazard_expansion" if "breach" in (ev.get("layers") or []) else "infrastructure_damage",
            "subject_entity": bind,
            "verification_status": "verified",
            "decay": 0.85,
            "source_event_id": ev["id"],
        }
    return {
        "build_phase": "C",
        "t": ev["t"],
        "event_id": ev["id"],
        "entities": entities,
        "flood": flood,
        "roads_wet": open_breach,
        "glyph": glyph,
        "r34_on_nola": True,
        "pulse": {
            "band": "CRITICAL" if gt_failed else "WARNING",
            "b7_state": "inaccessible" if gt_failed else "operational",
            "b7_belief": "uncertain",
            "truck_status": "N/A",
            "water_hours": 12,
            "shortage_prob": 0.35 if not gt_failed else 0.62,
        },
        "world_note": (
            f"landfall hour · GT B7 {'failed' if gt_failed else 'standing'} · "
            "belief uncertain · t0 snapshot unchanged"
        ),
    }


def prelandfall_delta(idx: int, script: dict | None = None) -> dict[str, Any] | None:
    """Phase 1: NOLA basemap + catalog at rest. Camera follows this event's binds."""
    if script is None:
        from .replay import load_script
        script = load_script()
    events = script["events"]
    if not events or idx < 0 or idx >= len(events):
        return None
    ev = events[idx]
    if ev.get("phase") != 1:
        return None
    from .catalog import ENTITIES_SPEC
    params = load_parameters()
    occupancy = pv(params, "shelters", "superdome_occupancy_landfall")
    capacity = pv(params, "shelters", "superdome_capacity")
    elapsed = _elapsed_ids(idx, script)
    entities: dict[str, dict] = {}
    for spec in ENTITIES_SPEC:
        eid = spec["entity_id"]
        state = "full" if eid == "warehouse:W1" else "operational"
        if eid == "power:waterford":
            state = "damaged"
        gap = eid == "power:waterford"
        patch: dict[str, Any] = {
            "state": state,
            "ground_truth_state": state,
            "verification_status": "unverified" if gap else "verified",
            "label": "pre-landfall",
            "source_key": "design:gap-fill" if gap else "landfall-rest",
        }
        if eid == "shelter:dome":
            patch["attributes"] = {
                "occupancy": occupancy if "p1-dome-evening" in elapsed else 0,
                "capacity": capacity,
            }
            if "p1-dome-evening" in elapsed:
                patch["state"] = "critical"
                patch["ground_truth_state"] = "critical"
                patch["source_key"] = "whitehouse-katrina-lessons-ch3"
                patch["verification_status"] = "verified"
                patch["label"] = "known"
        entities[eid] = patch
    bind = next((b for b in (ev.get("binds") or []) if not str(b).startswith("hazards.")), None)
    glyph = None
    if bind:
        glyph = {
            "event_id": ev["id"],
            "event_type": "hazard_expansion" if "evac" in " ".join(ev.get("layers") or []) else "infrastructure_damage",
            "subject_entity": bind,
            "verification_status": "unverified",
            "decay": 0.7,
            "source_event_id": ev["id"],
        }
    return {
        "build_phase": "B",
        "t": ev["t"],
        "event_id": ev["id"],
        "prelandfall": True,
        "entities": entities,
        "flood": {
            "stage_m": 0,
            "d_stage_dt": 0,
            "gauge_id": "gauge:ihnc",
            "wet_mask": {"type": "MultiPolygon", "coordinates": [], "features": []},
            "paths": [],
        },
        "roads_wet": False,
        "glyph": glyph,
        "r34_on_nola": True,
        "pulse": {
            "band": "WARNING",
            "b7_state": "operational",
            "b7_belief": "operational",
            "truck_status": "N/A",
            "water_hours": 12,
            "shortage_prob": 0.12,
        },
        "world_note": "phase 1 · NOLA assets on · pre-landfall rest · camera on this event's binds",
    }


def world_delta_for(idx: int, script: dict | None = None) -> dict[str, Any] | None:
    from .inundation import inundation_delta
    from .unwatering import unwatering_delta
    return (
        landfall_delta(idx, script)
        or inundation_delta(idx, script)
        or unwatering_delta(idx, script)
        or prelandfall_delta(idx, script)
    )
