"""Build phase E — Sep federal surge, unwatering, and power.

Carries phase-D rest (HUD ceiling bowls, Dome/CC crisis, Murphy, B7 failed)
and then: fires on at p4-fires, off-map Houston evac (no second city),
MSY military → limited commercial, pump counts, HUD bowls decaying toward
dry, power plants returning. Does not rewrite t0.json.
"""
from __future__ import annotations

import copy
from datetime import datetime
from typing import Any

from .inundation import hud_ceiling_features, inundation_delta
from .landfall import GAP_KEYS
from .population_clock import CLOVER, DOME, MORIAL, _last
from .snapshot import hud_weighted_depth_m, load_parameters, pv

# Remaining share of the 31 Aug HUD ceiling. City-area percents in the script
# (80% → 60% → 40% → 20% still wet) are divided by the 80% landfall language.
REMAIN: tuple[tuple[str, float], ...] = (
    ("p4-cg-4468", 1.00),
    ("p5-portable-pumps", 0.75),
    ("p5-pumps-23", 0.70),
    ("p5-pumps-26", 0.62),
    ("p6-unwater-billions", 0.55),
    ("p6-l9-dry-enough", 0.52),
    ("p6-40pct", 0.50),
    ("p6-80pct-unwatered", 0.25),
    ("p6-october-dry", 0.08),
    ("p6-rebuild", 0.03),
)

# (event_id, entity_id, state, source_key)
FLIPS: tuple[tuple[str, str, str, str], ...] = (
    ("p4-cg-4468", "zone:B", "critical", "design:gap-fill"),
    ("p4-cg-4468", "personnel:ng", "critical", "design:gap-fill"),
    ("p4-media-cc", "shelter:dome", "critical", "design:gap-fill"),
    ("p4-media-cc", "shelter:morial", "critical", "house-select-katrina"),
    ("p4-logistics-confusion", "warehouse:W1", "critical", "design:gap-fill"),
    ("p4-logistics-confusion", "truck:17", "inaccessible", "design:gap-fill"),
    ("p4-logistics-confusion", "food:pod", "critical", "design:gap-fill"),
    ("p4-dome-15000", "shelter:dome", "critical", "design:gap-fill"),
    ("p4-guard-22000", "personnel:ng", "critical", "ng-on-guard-katrina"),
    ("p4-fema-dod-logistics", "warehouse:W1", "damaged", "design:gap-fill"),
    ("p4-fema-dod-logistics", "truck:17", "damaged", "design:gap-fill"),
    ("p4-evac-houston", "shelter:dome", "damaged", "design:gap-fill"),
    ("p4-evac-houston", "shelter:morial", "damaged", "design:gap-fill"),
    ("p4-evac-houston", "airport:msy", "damaged", "design:gap-fill"),
    ("p4-msy-military", "airport:msy", "damaged", "latimes-msy-2005-09-14"),
    ("p4-msy-military", "airport:lakefront", "inaccessible", "design:gap-fill"),
    ("p4-sar-transition", "zone:B", "critical", "design:gap-fill"),
    ("p5-dome-cc-cleared", "shelter:dome", "damaged", "npr-dome-cc-empty-2005-09-04"),
    ("p5-dome-cc-cleared", "shelter:morial", "damaged", "npr-dome-cc-empty-2005-09-04"),
    ("p5-dome-cc-cleared", "zone:C", "damaged", "npr-dome-cc-empty-2005-09-04"),
    ("p5-power-cbd", "infra:power", "damaged", "doe-oe-katrina-sitrep-28"),
    ("p5-power-cbd", "comms:eoc", "operational", "design:gap-fill"),
    ("p5-power-cbd", "hospital:NDH", "critical", "design:gap-fill"),
    ("p5-portable-pumps", "infra:pump6", "damaged", "wiki-nola-reconstruction"),
    ("p5-portable-pumps", "infra:pumpInd", "damaged", "wiki-nola-reconstruction"),
    ("p5-pumps-23", "infra:pump6", "damaged", "wiki-nola-reconstruction"),
    ("p5-pumps-23", "infra:pumpInd", "damaged", "wiki-nola-reconstruction"),
    ("p5-entergy-9of17", "infra:power", "damaged", "doe-oe-katrina-sitrep-28"),
    ("p5-entergy-9of17", "power:ninemile", "operational", "design:gap-fill"),
    ("p5-entergy-9of17", "power:michoud", "inaccessible", "design:gap-fill"),
    ("p5-entergy-9of17", "power:waterford", "damaged", "design:gap-fill"),
    ("p5-ms-75pct", "infra:power", "damaged", "doe-oe-katrina-sitrep-31"),
    ("p5-pumps-26", "infra:pump6", "operational", "wiki-nola-reconstruction"),
    ("p5-pumps-26", "infra:pumpInd", "damaged", "wiki-nola-reconstruction"),
    ("p6-l9-dry-enough", "zone:B", "damaged", "design:gap-fill"),
    ("p6-msy-commercial", "airport:msy", "operational", "latimes-msy-2005-09-14"),
    ("p6-shelter-transition", "shelter:dome", "damaged", "npr-dome-cc-empty-2005-09-04"),
    ("p6-shelter-transition", "shelter:morial", "damaged", "npr-dome-cc-empty-2005-09-04"),
    ("p6-breach-closures", "breach:17th", "damaged", "wiki-nola-reconstruction"),
    ("p6-breach-closures", "breach:london", "damaged", "wiki-nola-reconstruction"),
    ("p6-breach-closures", "breach:london-n", "damaged", "wiki-nola-reconstruction"),
    ("p6-breach-closures", "breach:ihnc", "damaged", "wiki-nola-reconstruction"),
    ("p6-breach-closures", "breach:ihnc-west", "damaged", "wiki-nola-reconstruction"),
    ("p6-hazmat", "fuel:depot", "damaged", "epa-murphy-oil-katrina"),
    ("p6-power-late-sep", "infra:power", "damaged", "doe-oe-katrina-sitrep-28"),
    ("p6-power-late-sep", "power:waterford", "operational", "design:gap-fill"),
    ("p6-october-dry", "zone:B", "damaged", "design:gap-fill"),
    ("p6-october-dry", "infra:pump6", "operational", "wiki-nola-reconstruction"),
    ("p6-october-dry", "infra:pumpInd", "operational", "wiki-nola-reconstruction"),
    ("p6-rebuild", "zone:B", "damaged", "design:gap-fill"),
    ("p6-rebuild", "zone:C", "damaged", "design:gap-fill"),
)


def _when(ev: dict) -> datetime:
    return datetime.fromisoformat(ev["t"])


def _elapsed_ids(idx: int, script: dict) -> set[str]:
    return {ev["id"] for ev in script["events"][: idx + 1]}


def _last_phase_idx(script: dict, phase: int) -> int:
    last = 0
    for i, ev in enumerate(script["events"]):
        if ev.get("phase") == phase:
            last = i
    return last


def _remain_u(elapsed: set[str]) -> float:
    u = 1.0
    for eid, val in REMAIN:
        if eid in elapsed:
            u = val
    return u


def _scale_features(ceiling: list[dict], remain: float, extra: dict[str, float] | None = None) -> list[dict]:
    extra = extra or {}
    out = []
    for f in ceiling:
        s = extra.get(f["id"], remain)
        out.append({
            **f,
            "depth_m": round(f["depth_m"] * s, 3),
            "wet_frac": round(min(1.0, f["wet_frac"] * s), 4),
        })
    return out


def _apply_flip(entities: dict[str, dict], eid: str, state: str, src: str) -> None:
    prev = entities.get(eid) or {}
    patch: dict[str, Any] = {
        **prev,
        "state": state,
        "ground_truth_state": state if eid != "bridge:B7" else prev.get("ground_truth_state", state),
        "source_key": src,
        "verification_status": "unverified" if src in GAP_KEYS else "verified",
        "label": "design:gap-fill" if src in GAP_KEYS else "known",
    }
    if src in GAP_KEYS:
        patch["gap_fill"] = True
    else:
        patch.pop("gap_fill", None)
    entities[eid] = patch


def _occ_patch(entities: dict[str, dict], eid: str, n: int, src: str, cap: int) -> None:
    row = entities.setdefault(eid, {})
    row["attributes"] = {**(row.get("attributes") or {}), "occupancy": n, "capacity": cap}
    if src in GAP_KEYS:
        row["gap_fill"] = True
        row["verification_status"] = "unverified"
    else:
        row["source_key"] = src
        row.pop("gap_fill", None)
        if n == 0 or src not in GAP_KEYS:
            row["verification_status"] = "verified" if src not in GAP_KEYS else row.get("verification_status")
            row["label"] = "known" if src not in GAP_KEYS else row.get("label", "design:gap-fill")


def _pump_attrs(elapsed: set[str], params: dict) -> dict[str, Any]:
    total = int(pv(params, "unwatering", "pumps_permanent_total"))
    attrs: dict[str, Any] = {"pumps_total": total, "source_key": "wiki-nola-reconstruction"}
    if "p5-pumps-26" in elapsed:
        on = int(pv(params, "unwatering", "pumps_permanent_on_10sep"))
        port = int(pv(params, "unwatering", "pumps_portable_on_10sep"))
        cfs = int(pv(params, "unwatering", "pumps_permanent_cfs_10sep")) + int(
            pv(params, "unwatering", "pumps_portable_cfs_10sep")
        )
        attrs.update({"pumps_on": on, "portable_on": port, "cfs": cfs})
    elif "p5-pumps-23" in elapsed:
        attrs["pumps_on"] = int(pv(params, "unwatering", "pumps_permanent_on_7sep"))
        attrs["cfs"] = 0
    elif "p5-portable-pumps" in elapsed:
        attrs["pumps_on"] = 0
        attrs["cfs"] = 0
    return attrs


def unwatering_delta(idx: int, script: dict | None = None) -> dict[str, Any] | None:
    if script is None:
        from .replay import load_script
        script = load_script()
    events = script["events"]
    if not events or idx < 0 or idx >= len(events):
        return None
    ev = events[idx]
    if ev.get("phase") not in (4, 5, 6):
        return None

    last_p3 = _last_phase_idx(script, 3)
    base = inundation_delta(last_p3, script)
    if not base:
        return None

    elapsed = _elapsed_ids(idx, script)
    remain = _remain_u(elapsed)
    params = load_parameters()
    dome_cap = pv(params, "shelters", "superdome_capacity")
    cc_cap = pv(params, "shelters", "convention_center_capacity")
    dome_n, dome_src = _last(DOME, elapsed)
    cc_n, cc_src = _last(MORIAL, elapsed)
    cl_n, cl_src = _last(CLOVER, elapsed)

    out = copy.deepcopy(base)
    entities: dict[str, dict] = out["entities"]

    entities["bridge:B7"] = {
        "state": "inaccessible",
        "ground_truth_state": "inaccessible",
        "verification_status": "verified",
        "label": "known",
        "confidence": 0.92,
        "source_key": "usgs-circ-1306-ch3d",
        "note": "Twin Span unusable since landfall morning. Clock shows corroborated failure; t0 JSON is unchanged.",
    }
    entities["route:R14"] = {
        "state": "inaccessible",
        "ground_truth_state": "inaccessible",
        "source_key": "usgs-circ-1306-ch3d",
        "verification_status": "verified",
        "label": "known",
    }
    entities.setdefault("route:R22", {
        "state": "operational",
        "ground_truth_state": "operational",
        "source_key": "landfall-rest",
        "verification_status": "verified",
        "label": "inundation-rest",
    })
    entities.setdefault("bridge:us11", {
        "state": "operational",
        "ground_truth_state": "operational",
        "source_key": "landfall-rest",
        "verification_status": "verified",
        "label": "inundation-rest",
    })
    entities.setdefault("warehouse:W1", {
        "state": "full",
        "ground_truth_state": "full",
        "source_key": "landfall-rest",
        "verification_status": "verified",
        "label": "inundation-rest",
    })
    entities.setdefault("truck:17", {
        "state": "operational",
        "ground_truth_state": "operational",
        "source_key": "landfall-rest",
        "verification_status": "verified",
        "label": "inundation-rest",
    })
    entities["airport:msy"] = {
        "state": "damaged",
        "ground_truth_state": "damaged",
        "source_key": "design:gap-fill",
        "verification_status": "unverified",
        "label": "design:gap-fill",
        "gap_fill": True,
    }
    entities["airport:lakefront"] = {
        "state": "inaccessible",
        "ground_truth_state": "inaccessible",
        "source_key": "design:gap-fill",
        "verification_status": "unverified",
        "label": "design:gap-fill",
        "gap_fill": True,
    }

    for event_id, eid, state, src in FLIPS:
        if event_id in elapsed:
            _apply_flip(entities, eid, state, src)

    _occ_patch(entities, "shelter:dome", dome_n, dome_src, dome_cap)
    _occ_patch(entities, "shelter:morial", cc_n, cc_src, cc_cap)
    if cl_n or "p4-evac-houston" in elapsed:
        _occ_patch(entities, "camp:cloverleaf", cl_n, cl_src, cl_n or 1)
        if cl_n > 0:
            entities["camp:cloverleaf"]["state"] = "critical"
            entities["camp:cloverleaf"]["ground_truth_state"] = "critical"

    pump = _pump_attrs(elapsed, params)
    for pid in ("infra:pump6", "infra:pumpInd"):
        if pid in entities and ("pumps_on" in pump or "p5-portable-pumps" in elapsed):
            entities[pid]["attributes"] = {**(entities[pid].get("attributes") or {}), **pump}

    extra = {}
    if "p6-l9-dry-enough" in elapsed and "p6-40pct" not in elapsed:
        extra["lower-9th"] = min(remain, 0.28)
    features = _scale_features(hud_ceiling_features(), remain, extra)
    hud_stage = hud_weighted_depth_m("lower-9th")
    stage_m = hud_stage * remain

    bind = next((b for b in (ev.get("binds") or []) if not str(b).startswith("hazards.")), None)
    glyph = None
    if bind:
        glyph = {
            "event_id": ev["id"],
            "event_type": "hazard_expansion" if "flood" in (ev.get("layers") or []) else "infrastructure_damage",
            "subject_entity": bind,
            "verification_status": "verified",
            "decay": 0.8,
            "source_event_id": ev["id"],
        }

    pumps_on = pump.get("pumps_on")
    pulse: dict[str, Any] = {
        "band": "CRITICAL" if remain >= 0.45 else "WARNING",
        "b7_state": "inaccessible",
        "b7_belief": "inaccessible",
        "truck_status": "SUSPENDED",
        "water_hours": 18 if remain < 0.3 else 10,
        "shortage_prob": 0.45 if "p5-dome-cc-cleared" in elapsed else 0.78,
        "remain": remain,
    }
    if pumps_on is not None:
        pulse["pumps_on"] = pumps_on
        pulse["pumps_total"] = pump.get("pumps_total")
        pulse["cfs"] = pump.get("cfs")
    if "p4-evac-houston" in elapsed:
        pulse["off_map"] = "Houston / other cities — not a second map"
    if "p4-guard-22000" in elapsed:
        pulse["ng_nola"] = int(pv(params, "unwatering", "ng_nola_2sep"))
        pulse["ng_gulf"] = int(pv(params, "unwatering", "ng_gulf_2sep"))

    out.update({
        "build_phase": "E",
        "t": ev["t"],
        "event_id": ev["id"],
        "entities": entities,
        "flood": {
            "stage_m": round(stage_m, 3),
            "d_stage_dt": 0.0 if remain <= 0.08 else round(-0.08 * (1.0 - remain), 3),
            "gauge_id": "gauge:ihnc",
            "wet_mask": {
                "type": "MultiPolygon",
                "coordinates": [[f["ring"]] for f in features],
                "features": features,
                "source_key": "hud-noaa-flood-2005-08-31",
                "vintage": "hud-districts-2005-08-31 × usace-unwatering",
                "flooded_units": sum(f["flooded_units"] for f in features),
                "remain": remain,
                "note": (
                    f"Phase E: HUD 31 Aug rings scaled by remaining={remain:.2f} "
                    "(city-area unwatering language / 80% landfall). Not MOTF. "
                    "t0 snapshot unchanged."
                ),
            },
            "paths": [],
        },
        "roads_wet": remain > 0.12,
        "glyph": glyph,
        "r34_on_nola": False,
        "pulse": pulse,
        "world_note": (
            f"unwatering · remain {remain:.2f} · Dome {dome_n:,} / CC {cc_n:,}"
            + (f" · pumps {pumps_on}/{pump.get('pumps_total')}" if pumps_on is not None else "")
            + " · t0 snapshot unchanged"
        ),
    })
    return out
