"""Build WorldSnapshot documents from parameters.json + catalog."""
from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any

from .bridges import load_bridge_spans
from .catalog import (
    BASE_STATES, ENTITIES_SPEC, RELATIONSHIPS, ROUTE_PATHS, ZONE_RINGS,
)
from .gltf_models import CATEGORIES, NONMESH_SYMBOLS, SYMBOLS, write_all as write_gltf_all

FT_M = 0.3048

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "katrina"
WORLD_DIR = DATA / "world"
SNAP_DIR = DATA / "snapshots"
WEB_PUBLIC = ROOT / "web" / "public"


def load_parameters() -> dict:
    return json.loads((DATA / "parameters.json").read_text(encoding="utf-8"))


def pv(params: dict, *path: str) -> Any:
    cur: Any = params
    for p in path:
        cur = cur[p]
    return cur["value"]


def viz_block(params: dict) -> dict:
    v = params["visualization"]
    return {k: v[k]["value"] for k in (
        "vertical_exaggeration", "camera_tilt_degrees", "hero_region_bounds",
        "lod_switch_altitude_m", "max_particle_count", "shader_binding_required",
        "emissive_materials_allowed", "translucency_unverified", "translucency_verified",
        "saturation_historical", "fog_recency_kernel_radius_m",
        "population_grid_resolution_m", "flood_grid_resolution_m",
        "population_min_aggregation_cell_count", "population_density_bin_method",
        "gulf_camera_zoom",
    )}


def interpolate_path(path: list, t: float) -> list[float]:
    if t <= 0:
        return list(path[0])
    if t >= 1:
        return list(path[-1])
    segs = len(path) - 1
    x = t * segs
    i = min(segs - 1, int(x))
    f = x - i
    a, b = path[i], path[i + 1]
    return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f]


def path_heading_deg(path: list, t: float) -> float:
    a = interpolate_path(path, max(0.0, t - 0.03))
    b = interpolate_path(path, min(1.0, t + 0.03))
    dlon = (b[0] - a[0]) * math.cos(math.radians(a[1]))
    dlat = b[1] - a[1]
    return (math.degrees(math.atan2(dlon, dlat)) + 360.0) % 360.0


def segment_route(route_id: str, states: list[str]) -> list[dict]:
    path = ROUTE_PATHS[route_id]
    return [{
        "segment_id": f"{route_id}:s{i}",
        "route_id": route_id,
        "path": [path[i], path[i + 1]],
        "state": states[i] if i < len(states) else states[-1],
    } for i in range(len(path) - 1)]


def load_neighborhoods() -> dict:
    return json.loads((DATA / "sourced" / "neighborhoods_census2000.json").read_text(encoding="utf-8"))


def load_hydrograph() -> dict:
    return json.loads((DATA / "sourced" / "ihnc_lock_hydrograph.json").read_text(encoding="utf-8"))


def load_hud_flood() -> dict:
    return json.loads((DATA / "sourced" / "hud_flood_districts.json").read_text(encoding="utf-8"))


def interpolate_hydrograph(when: datetime) -> tuple[float, float]:
    """Return (stage_m, d_stage_dt m/h) on the 29 Aug IHNC Lock staff series."""
    series = load_hydrograph()["series"]
    times = [datetime.fromisoformat(p["cdt"]) for p in series]
    vals = [float(p["stage_ft"]) for p in series]
    if when <= times[0]:
        dt_h = (times[1] - times[0]).total_seconds() / 3600.0
        d_ft = (vals[1] - vals[0]) / dt_h
        return vals[0] * FT_M, d_ft * FT_M
    if when >= times[-1]:
        dt_h = (times[-1] - times[-2]).total_seconds() / 3600.0
        d_ft = (vals[-1] - vals[-2]) / dt_h
        return vals[-1] * FT_M, d_ft * FT_M
    for i in range(len(times) - 1):
        if times[i] <= when <= times[i + 1]:
            span = (times[i + 1] - times[i]).total_seconds()
            dt_h = span / 3600.0
            f = (when - times[i]).total_seconds() / span
            stage_ft = vals[i] + f * (vals[i + 1] - vals[i])
            d_ft = (vals[i + 1] - vals[i]) / dt_h
            return stage_ft * FT_M, d_ft * FT_M
    return vals[-1] * FT_M, 0.0


def district_flood_metrics(d: dict) -> tuple[float, float]:
    """HUD-weighted mean depth (m) and share of housing units that flooded."""
    n = d["flooded_units"]
    tot = d.get("total_units") or 0
    wet_frac = (n / tot) if tot else 0.0
    if n <= 0:
        return 0.0, 0.0
    mids = load_hud_flood()["bin_midpoints_ft"]
    wft = (d["units_2_4"] * mids[0] + d["units_4_7"] * mids[1] + d["units_gt7"] * mids[2]) / n
    return wft * FT_M, wet_frac


def hud_weighted_depth_m(district_id: str) -> float:
    hud = load_hud_flood()
    d = next(x for x in hud["districts"] if x["id"] == district_id)
    depth_m, _ = district_flood_metrics(d)
    return depth_m


def flood_stage(params: dict, keyframe: str) -> tuple[float, float]:
    """b7 = IHNC Lock surge at 06:00 CDT 29 Aug. t0/reroute = 31 Aug standing bowl."""
    if keyframe == "b7":
        when = datetime.fromisoformat(pv(params, "chronology", "bridge_B7_collapse_valid_from"))
        return interpolate_hydrograph(when)
    return hud_weighted_depth_m("lower-9th"), 0.0


def load_contamination() -> dict:
    return load_osm_json("katrina_contamination.json") or {}


def load_fires() -> dict:
    return load_osm_json("katrina_fires.json") or {}


def contamination_hazard(keyframe: str) -> dict:
    raw = load_contamination()
    areas = list(raw.get("areas") or [])
    return {
        "active": bool(areas),
        "areas": areas,
        "source_key": raw.get("source_key"),
        "vintage": raw.get("vintage"),
        "note": raw.get("note") or "",
    }


def fire_hazard(keyframe: str) -> dict:
    raw = load_fires()
    sites = list(raw.get("sites") or [])
    return {
        "synthetic": False,
        "active": bool(sites),
        "sites": sites,
        "perimeter": [],
        "spread_rate": 0.35 if sites else 0.0,
        "wind": {"u": 0.12, "v": 0.06},
        "source_key": raw.get("source_key"),
        "vintage": raw.get("vintage"),
        "note": raw.get("note") or "No Katrina fire binding retrieved — hazard off.",
    }


def entity_ll(eid: str) -> dict:
    spec = next(e for e in ENTITIES_SPEC if e["entity_id"] == eid)
    return {"lon": spec["lon"], "lat": spec["lat"]}


_BRIDGE_SPANS: dict | None = None


def _bridge_span_cache() -> dict:
    global _BRIDGE_SPANS
    if _BRIDGE_SPANS is None:
        _BRIDGE_SPANS = load_bridge_spans()
    return _BRIDGE_SPANS


def load_osm_json(name: str) -> dict:
    p = DATA / "sourced" / name
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def _pip(lon: float, lat: float, ring: list) -> bool:
    inside = False
    for i in range(len(ring) - 1):
        xi, yi = ring[i]
        xj, yj = ring[i + 1]
        denom = (yj - yi) or 1e-12
        if (yi > lat) != (yj > lat) and lon < ((xj - xi) * (lat - yi)) / denom + xi:
            inside = not inside
    return inside


def convoy_segment_states(route_id: str, keyframe: str) -> list[str]:
    path = ROUTE_PATHS[route_id]
    n = len(path) - 1
    if route_id != "route:R14" or keyframe == "t0":
        return ["open"] * n
    out = []
    for a, b in zip(path, path[1:]):
        mid_lon, mid_lat = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        if 30.16 <= mid_lat <= 30.21 and -89.87 <= mid_lon <= -89.78:
            out.append("blocked")
        elif mid_lat < 30.04:
            out.append("submerged")
        else:
            out.append("open")
    return out


def in_open_water(lon: float, lat: float) -> bool:
    """Lake Pontchartrain north of the seawall, Mississippi between FQ and Algiers, City Park lagoons."""
    if lon < -89.88 and lat > 30.0265:
        return True
    if 29.952 < lat < 29.958 and -90.052 < lon < -90.045:
        return True
    if 29.988 < lat < 30.012 and -90.105 < lon < -90.085:
        return True
    return False


def _bldg_xy(b: dict) -> tuple[float, float]:
    if "cx" in b and "cy" in b:
        return float(b["cx"]), float(b["cy"])
    ring = b.get("ring") or []
    pts = ring[:-1] if ring and ring[0] == ring[-1] else ring
    if not pts:
        return 0.0, 0.0
    return sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)


def drape_population(buildings: list[dict], cells: list[dict]) -> list[dict]:
    """Join Census NSA density onto footprints within ~1.3 km. Buildings on water are dropped."""
    max_d2 = 0.012 ** 2
    out = []
    for b in buildings:
        cx, cy = _bldg_xy(b)
        if in_open_water(cx, cy):
            continue
        best, bd = None, 1e9
        for c in cells:
            d = (c["lon"] - cx) ** 2 + (c["lat"] - cy) ** 2
            if d < bd:
                bd, best = d, c
        row = dict(b)
        if best is not None and bd < max_d2:
            row["density"] = best["density"]
            row["pop_name"] = best["name"]
            row["pop_count"] = best["count"]
        else:
            row["density"] = 0.0
            row["pop_name"] = ""
            row["pop_count"] = 0
        out.append(row)
    named = [r["pop_name"] for r in out if r["pop_name"]]
    n_by = {}
    for name in named:
        n_by[name] = n_by.get(name, 0) + 1
    for r in out:
        n = n_by.get(r["pop_name"], 0)
        if n and r["pop_count"]:
            r["heat_weight"] = round(r["pop_count"] / n, 3)
        else:
            r["heat_weight"] = 0.0
    return out


def build_heat_field(buildings: list[dict], roads: list[dict], cells: list[dict]) -> list[dict]:
    """Heatmap samples sit on basemap land fabric: building centroids and non-bridge roads."""
    heat = []
    for b in buildings:
        w = b.get("heat_weight") or 0
        if w <= 0:
            continue
        lon, lat = _bldg_xy(b)
        if in_open_water(lon, lat) or (lat > 30.05 and lon < -89.80):
            continue
        heat.append({
            "lon": round(lon, 5), "lat": round(lat, 5),
            "weight": w, "density": b.get("density") or 0,
        })
    for road in roads:
        if road.get("bridge"):
            continue
        path = road.get("path") or []
        if len(path) < 2:
            continue
        step = max(1, len(path) // 3)
        for p in path[::step]:
            lon, lat = p[0], p[1]
            if in_open_water(lon, lat) or (lat > 30.05 and lon < -89.80):
                continue
            best, bd = None, 1e9
            for c in cells:
                d = (c["lon"] - lon) ** 2 + (c["lat"] - lat) ** 2
                if d < bd:
                    bd, best = d, c
            if best is None or bd >= 0.012 ** 2:
                continue
            heat.append({
                "lon": round(lon, 5), "lat": round(lat, 5),
                "weight": round(best["count"] / 40.0, 3),
                "density": best["density"],
            })
    return heat


def mark_orphan_cells(cells: list[dict], buildings: list[dict]) -> None:
    """Cells with no nearby footprint keep a small land pin; others are represented by buildings."""
    max_d2 = 0.012 ** 2
    sites = [_bldg_xy(b) for b in buildings]
    for c in cells:
        if not sites:
            c["orphan"] = True
            continue
        bd = min((sx - c["lon"]) ** 2 + (sy - c["lat"]) ** 2 for sx, sy in sites)
        c["orphan"] = bd >= max_d2


def mark_building_flood_damage(buildings: list[dict], keyframe: str) -> None:
    """HUD wet_frac / depth → intact | damaged | destroyed. Height follows damage."""
    hud = load_hud_flood()
    districts = []
    for d in hud["districts"]:
        if keyframe == "b7" and not d.get("early_29aug"):
            continue
        if d.get("flooded_units", 0) <= 0:
            continue
        depth_m, wet_frac = district_flood_metrics(d)
        districts.append({
            "id": d["id"], "ring": d["ring"],
            "depth_m": depth_m, "wet_frac": wet_frac,
        })
    for b in buildings:
        cx, cy = _bldg_xy(b)
        hit = next((d for d in districts if _pip(cx, cy, d["ring"])), None)
        h0 = float(b.get("height_m") or 8)
        if hit is None:
            b["damage"] = "intact"
            b["wet_frac"] = 0.0
            b["depth_m"] = 0.0
            continue
        b["wet_frac"] = round(hit["wet_frac"], 3)
        b["depth_m"] = round(hit["depth_m"], 3)
        b["flood_district"] = hit["id"]
        if hit["wet_frac"] >= 0.55 or hit["depth_m"] >= 1.8:
            b["damage"] = "destroyed"
            b["height_m"] = round(max(1.2, h0 * 0.18), 2)
        elif hit["wet_frac"] >= 0.12:
            b["damage"] = "damaged"
            b["height_m"] = round(max(2.4, h0 * 0.55), 2)
        else:
            b["damage"] = "intact"


def geography_bundle(keyframe: str, cells: list | None = None) -> dict:
    roads_raw = load_osm_json("osm_roads.json")
    canals_raw = load_osm_json("osm_canals.json")
    bldgs_raw = load_osm_json("osm_buildings.json")
    hud = load_hud_flood()
    if keyframe == "b7":
        flood_rings = [d["ring"] for d in hud["districts"] if d.get("early_29aug")]
    elif keyframe == "t0":
        flood_rings = [d["ring"] for d in hud["districts"] if d["flooded_units"] > 0]
    else:
        flood_rings = [d["ring"] for d in hud["districts"] if d["flooded_units"] > 0]
    b7_down = keyframe != "t0"
    roads = []
    for road in roads_raw.get("roads", []):
        path = road["path"]
        ref = f"{road.get('ref') or ''} {road.get('name') or ''}"
        state = "open"
        on_twin = any(30.16 <= p[1] <= 30.21 and -89.87 <= p[0] <= -89.78 for p in path)
        if b7_down and on_twin and ("I 10" in ref or "I-10" in ref or "Twin" in ref):
            state = "blocked"
        elif not road.get("bridge"):
            hits = sum(1 for p in path if any(_pip(p[0], p[1], ring) for ring in flood_rings))
            if hits >= max(1, len(path) // 4):
                state = "submerged"
        roads.append({**road, "state": state})
    buildings = bldgs_raw.get("buildings", [])
    if cells is not None:
        buildings = drape_population(buildings, cells)
    else:
        buildings = [b for b in buildings if not in_open_water(*_bldg_xy(b))]
    mark_building_flood_damage(buildings, keyframe)
    return {
        "vintage": roads_raw.get("vintage") or "current OSM — Twin Span is the 2011 rebuild",
        "source_key": "osm-extract-nola",
        "roads": roads,
        "canals": canals_raw.get("canals", []),
        "buildings": buildings,
    }


def load_best_track() -> list[dict]:
    raw = json.loads((DATA / "sourced" / "nhc_best_track.json").read_text(encoding="utf-8"))
    out = []
    landfall = "2005-08-29T11:10:00Z"
    t0 = datetime.fromisoformat(landfall.replace("Z", "+00:00"))
    for p in raw["track"]:
        t = datetime.fromisoformat(p["utc"].replace("Z", "+00:00"))
        dt_h = (t - t0).total_seconds() / 3600.0
        out.append({
            "lon": p["lon"], "lat": p["lat"], "t_h": round(dt_h, 1),
            "cat": p["cat"], "wind_km": round(p["wind_kt"] * 1.852, 1),
        })
    return out


def quantile_edges(values: list[float]) -> list[float]:
    xs = sorted(v for v in values if v > 0)
    if len(xs) < 4:
        return [1000.0, 3000.0, 6000.0]

    def q(p: float) -> float:
        i = min(len(xs) - 1, max(0, int(p * (len(xs) - 1))))
        return round(xs[i], 1)

    return [q(0.25), q(0.50), q(0.75)]


def build_population(params: dict, keyframe: str) -> dict:
    """Density from retrieved Census 2000 neighborhood counts. Movement from shelter occupancy deltas."""
    hoods = load_neighborhoods()
    min_count = pv(params, "visualization", "population_min_aggregation_cell_count")
    res_m = pv(params, "visualization", "population_grid_resolution_m")
    # Neighborhood land area is not in SF1 as retrieved; use Data Center page areas where
    # known (Holy Cross 1.8 km²) and a 4 km² default so density is comparable across cells.
    default_km2 = 4.0
    area_km2 = {"holy-cross": 1.8, "french-quarter": 1.7, "algiers-point": 1.0,
                "lower-ninth-ward": 5.5, "little-woods": 18.0, "lakeview": 4.2}
    dome_t0 = pv(params, "shelters", "superdome_occupancy_31aug")
    dome_landfall = pv(params, "shelters", "superdome_occupancy_landfall")
    cc_t0 = pv(params, "zones", "zone_C_population")
    post_storm = keyframe != "b7"
    cells, totals = [], []
    flooded_pop = 0
    for n in hoods["neighborhoods"]:
        km2 = area_km2.get(n["id"], default_km2)
        dens = n["pop"] / km2
        if n["pop"] < min_count:
            continue
        # Affected = HUD-flooded neighborhoods after the breaches (31 Aug table).
        aff = dens if (post_storm and n["flooded"]) else (dens * 0.05)
        # Displaced overlay is shelter-bound, not a second residential raster.
        disp = 0.0
        if post_storm and n["id"] == "lower-ninth-ward":
            disp = cc_t0 / km2
        if n["flooded"]:
            flooded_pop += n["pop"]
        if in_open_water(n["lon"], n["lat"]):
            continue
        cells.append({
            "lon": n["lon"], "lat": n["lat"], "name": n["name"],
            "count": n["pop"], "density": round(dens, 1),
            "affected": round(aff, 1), "displaced": round(disp, 1),
            "flooded": n["flooded"],
            "orphan": False,
        })
        totals.append(dens)
    pop_b = pv(params, "zones", "zone_B_population")
    pop_c = cc_t0
    movement = []
    if post_storm:
        # House Rpt 109-377: people went to the Convention Center after Mon/Tue breaches;
        # search-and-rescue also dropped people at the Dome. Magnitude = occupancy gained.
        movement = [
            {"from": [entity_ll("zone:B")["lon"], entity_ll("zone:B")["lat"]],
             "to": [entity_ll("shelter:morial")["lon"], entity_ll("shelter:morial")["lat"]],
             "magnitude": 1.0, "count": cc_t0,
             "source": "house-select-katrina fn.114 NG 19,000 at Convention Center"},
            {"from": [entity_ll("zone:B")["lon"], entity_ll("zone:B")["lat"]],
             "to": [entity_ll("shelter:dome")["lon"], entity_ll("shelter:dome")["lat"]],
             "magnitude": max(0.0, (dome_t0 - dome_landfall) / max(dome_t0, 1)),
             "count": max(0, dome_t0 - dome_landfall),
             "source": "shelter occupancy delta Dome landfall → 31 Aug"},
        ]
    return {
        "dataset_id": hoods["dataset_id"], "version": "1.0",
        "source": hoods["compiler"], "retrieved": hoods["retrieved"],
        "spatial_resolution_m": res_m,
        "bin_method": pv(params, "visualization", "population_density_bin_method"),
        "bin_edges_per_km2": quantile_edges(totals),
        "min_aggregation_cell_count": min_count,
        "classes": {
            "total": {"zone:B": pop_b, "zone:C": pop_c,
                      "orleans_parish_2000": hoods["orleans_parish_total"]},
            "affected": {"flooded_neighborhoods_retrieved": flooded_pop if post_storm else 0,
                         "zone:B": pop_b if post_storm else 0},
            "displaced": {
                "shelter:morial": 0 if keyframe == "b7" else cc_t0,
                "shelter:dome": dome_landfall if keyframe == "b7" else dome_t0,
            },
        },
        "cells": cells, "movement": movement, "forecast_enabled": False, "heat": [],
        "note": (
            "Residential density is Census 2000 NSA counts. The heatmap is sampled from OSM "
            "building footprints and land roads on the basemap — not neighborhood centroids, "
            "so it does not paint Lake Pontchartrain or the Mississippi. "
            "Displaced counts are shelter headcounts."
        ),
    }


def wet_mask(keyframe: str) -> dict:
    hud = load_hud_flood()
    if keyframe == "b7":
        districts = [d for d in hud["districts"] if d.get("early_29aug")]
        vintage = "hud-districts + ipet-breach-morning-29aug"
        note = (
            "Rings follow east-bank land bowls on the basemap (lake seawall, 17th St, IHNC, "
            "river levee). LOW subset is Lower 9th + Lakeview at ~06:00 CDT 29 Aug. "
            "Extrusion is each district's HUD-weighted depth, not a 06:00 observed water polygon."
        )
    else:
        districts = [d for d in hud["districts"] if d["flooded_units"] > 0]
        vintage = hud["vintage"]
        note = (
            "HUD overlay of NOAA 31 Aug 2005 flood depths on Orleans planning districts. "
            "Algiers, French Quarter, and New Aurora/English Turn omitted (0 flooded units). "
            "Each ring's height is that district's HUD-weighted mean depth; opacity is flooded-unit share. "
            "Not MOTF shapefiles and not open water."
        )
    features = []
    for d in districts:
        depth_m, wet_frac = district_flood_metrics(d)
        features.append({
            "id": d["id"], "name": d["name"], "ring": d["ring"],
            "depth_m": round(depth_m, 3), "wet_frac": round(wet_frac, 4),
            "flooded_units": d["flooded_units"], "total_units": d["total_units"],
        })
    return {
        "type": "MultiPolygon",
        "coordinates": [[d["ring"]] for d in districts],
        "features": features,
        "source_key": hud["source_key"],
        "vintage": vintage,
        "flooded_units": sum(d["flooded_units"] for d in districts),
        "note": note,
    }


def _entity_record(spec: dict, state: str, params: dict, vstatus: str, source: str | None,
                   extra: dict | None = None) -> dict:
    attrs: dict[str, Any] = {}
    eid = spec["entity_id"]
    sphere = pv(params, "humanitarian_standards", "water_l_per_person_day")
    if eid == "zone:B":
        attrs = {
            "population": pv(params, "zones", "zone_B_population"),
            "vulnerability": pv(params, "zones", "zone_B_vulnerability"),
            "water_hours": pv(params, "forecast_depletion", "water_hours_remaining"),
            "ring": ZONE_RINGS["zone:B"],
            "alpha_min": pv(params, "zones", "zone_B_population") * sphere,
        }
    elif eid == "zone:C":
        attrs = {
            "population": pv(params, "zones", "zone_C_population"),
            "vulnerability": pv(params, "zones", "zone_C_vulnerability"),
            "water_hours": 6.0, "ring": ZONE_RINGS["zone:C"],
            "alpha_min": pv(params, "zones", "zone_C_population") * sphere,
        }
    elif eid == "warehouse:W1":
        stock = pv(params, "supply", "warehouse_W1_staging_l_per_day")
        attrs = {
            "stock": stock, "capacity": stock,
            "origin": "Camp Beauregard, LA (House Rpt 109-377 preparation fn. 4)",
            "map_pin": "Slidell I-10 forward node",
        }
    elif eid == "truck:17":
        attrs = {
            "capacity": pv(params, "supply", "convoy_17_tanker_count") * pv(params, "supply", "tanker_capacity_l"),
            "tanker_count": pv(params, "supply", "convoy_17_tanker_count"),
        }
    elif eid == "shelter:dome":
        attrs = {
            "occupancy": pv(params, "shelters", "superdome_occupancy_31aug"),
            "capacity": pv(params, "shelters", "superdome_capacity"),
        }
    elif eid == "shelter:morial":
        attrs = {
            "occupancy": pv(params, "zones", "zone_C_population"),
            "capacity": pv(params, "shelters", "convention_center_capacity"),
        }
    elif eid == "gauge:ihnc":
        attrs = {"stage_m": 0.0, "d_stage_dt": 0.0}
    if extra:
        attrs.update(extra)
    if spec.get("type") == "bridge":
        span = _bridge_span_cache().get(eid)
        if span:
            attrs.update(span)
        elif spec.get("heading_deg") is not None:
            attrs["heading_deg"] = spec["heading_deg"]
    elif spec.get("heading_deg") is not None:
        attrs["heading_deg"] = spec["heading_deg"]
    return {
        "entity_id": eid, "type": spec["type"], "name": spec["name"],
        "geometry": {"lon": spec["lon"], "lat": spec["lat"]},
        "aliases": spec.get("aliases", []), "state": state,
        "confidence": 0.55 if vstatus == "unverified" else (0.7 if state == "uncertain" else 0.92),
        "verification_status": vstatus,
        "label": "uncertain" if state == "uncertain" else "known",
        "attributes": attrs, "source_event_id": source,
        "valid_from": pv(params, "chronology", "demo_t0"),
        "valid_until": None, "synthetic": bool(spec.get("synthetic", False)),
    }


def build_snapshot(params: dict, keyframe: str) -> dict:
    states = dict(BASE_STATES)
    t0 = pv(params, "chronology", "demo_t0")
    b7_from = pv(params, "chronology", "bridge_B7_collapse_valid_from")
    b7_rec = pv(params, "chronology", "bridge_B7_corroborated_recorded_at")
    qty = pv(params, "governance", "human_modify_zone_B_qty_l")

    if keyframe == "t0":
        valid_at, recorded_at = t0, t0
        b7_vs, src_b7 = "unverified", None
        progress, tstatus, via = 0.22, "IN_PROGRESS", "route:R14"
        r14s = convoy_segment_states("route:R14", keyframe)
        stage, dstage = flood_stage(params, keyframe)
        permit, pvia, pstatus = "active", "route:R14", "approved"
        shortage, band = 0.78, "WARNING"
        events = [{
            "event_id": "ev-unverified-b7", "event_type": "infrastructure_damage",
            "subject_entity": "bridge:B7", "verification_status": "unverified",
            "geometry": entity_ll("bridge:B7"), "decay": 0.4,
            "source_event_id": "obs-field-1",
        }]
    elif keyframe == "b7":
        valid_at, recorded_at = b7_from, b7_rec
        states.update({"bridge:B7": "inaccessible", "route:R14": "inaccessible", "truck:17": "critical"})
        b7_vs, src_b7 = "verified", "ve-b7-1"
        progress, tstatus, via = 0.55, "SUSPENDED", "route:R14"
        r14s = convoy_segment_states("route:R14", keyframe)
        stage, dstage = flood_stage(params, keyframe)
        permit, pvia, pstatus = "revoked", "route:R14", "invalidated"
        shortage, band = 0.91, "CRITICAL"
        events = [
            {"event_id": "ev-verified-b7", "event_type": "infrastructure_damage",
             "subject_entity": "bridge:B7", "verification_status": "verified",
             "geometry": entity_ll("bridge:B7"), "decay": 1.0, "source_event_id": "ve-b7-1"},
            {"event_id": "ev-road-closure", "event_type": "road_closure",
             "subject_entity": "route:R14", "verification_status": "verified",
             "geometry": entity_ll("bridge:B7"), "decay": 0.8, "source_event_id": "ve-b7-1"},
            {"event_id": "ev-hazard-exp", "event_type": "hazard_expansion",
             "subject_entity": "gauge:ihnc", "verification_status": "verified",
             "geometry": entity_ll("gauge:ihnc"), "decay": 0.6, "source_event_id": "ve-flood-1"},
        ]
    else:
        valid_at, recorded_at = b7_rec, b7_rec
        states.update({"bridge:B7": "inaccessible", "route:R14": "inaccessible", "truck:17": "operational"})
        b7_vs, src_b7 = "verified", "ve-b7-1"
        progress, tstatus, via = 0.40, "IN_PROGRESS", "route:R22"
        r14s = convoy_segment_states("route:R14", keyframe)
        stage, dstage = flood_stage(params, keyframe)
        permit, pvia, pstatus = "active", "route:R22", "approved"
        shortage, band = 0.88, "CRITICAL"
        events = [{"event_id": "ev-verified-b7", "event_type": "infrastructure_damage",
                   "subject_entity": "bridge:B7", "verification_status": "verified",
                   "geometry": entity_ll("bridge:B7"), "decay": 0.2, "source_event_id": "ve-b7-1"}]

    entities = []
    for spec in ENTITIES_SPEC:
        spec = dict(spec)
        extra: dict[str, Any] = {}
        if spec["entity_id"] == "gauge:ihnc":
            extra = {"stage_m": round(stage, 3), "d_stage_dt": round(dstage, 3)}
        if spec["entity_id"] == "warehouse:W1" and keyframe == "reroute":
            extra = {
                "stock": pv(params, "supply", "warehouse_W1_staging_l_per_day") - qty,
                "origin": "Camp Beauregard, LA (House Rpt 109-377 preparation fn. 4)",
                "map_pin": "Slidell I-10 forward node",
            }
        if spec["entity_id"] == "truck:17":
            pos = interpolate_path(ROUTE_PATHS[via], progress)
            spec["lon"], spec["lat"] = pos[0], pos[1]
            extra = {
                "capacity": pv(params, "supply", "convoy_17_tanker_count") * pv(params, "supply", "tanker_capacity_l"),
                "stock": qty if keyframe == "reroute" else 0,
                "progress": progress, "route": via, "position": pos,
                "heading_deg": path_heading_deg(ROUTE_PATHS[via], progress),
            }
        if spec["entity_id"] == "shelter:dome":
            extra = {
                "occupancy": pv(params, "shelters", "superdome_occupancy_landfall") if keyframe == "b7"
                else pv(params, "shelters", "superdome_occupancy_31aug"),
                "capacity": pv(params, "shelters", "superdome_capacity"),
            }
        if spec["entity_id"] == "shelter:morial":
            extra = {
                "occupancy": 0 if keyframe == "b7" else pv(params, "zones", "zone_C_population"),
                "capacity": pv(params, "shelters", "convention_center_capacity"),
            }
        vs = b7_vs if spec["entity_id"] == "bridge:B7" else "verified"
        src = src_b7 if spec["entity_id"] == "bridge:B7" else ("seed" if vs == "verified" else None)
        rec = _entity_record(spec, states.get(spec["entity_id"], "operational"), params, vs, src, extra or None)
        if spec["entity_id"] == "bridge:B7":
            rec["valid_from"] = b7_from
            rec["recorded_at"] = recorded_at
        entities.append(rec)

    rels = []
    for a, b, t in RELATIONSHIPS:
        active = not (keyframe != "t0" and t == "reachable_from" and a == "route:R14")
        rels.append({"from_entity": a, "to_entity": b, "rel_type": t, "active": active})

    plan_id = "plan-1048" if keyframe != "reroute" else "plan-1052"
    pop = build_population(params, keyframe)
    geo = geography_bundle(keyframe, pop["cells"])
    mark_orphan_cells(pop["cells"], geo["buildings"])
    pop["heat"] = build_heat_field(geo["buildings"], geo["roads"], pop["cells"])
    r22s = ["open"] * (len(ROUTE_PATHS["route:R22"]) - 1)
    return {
        "schema_version": "1.0", "crisis_id": "katrina-nola-2005", "keyframe_id": keyframe,
        "valid_at": valid_at, "recorded_at": recorded_at,
        "entities": entities,
        "route_segments": segment_route("route:R14", r14s) + segment_route("route:R22", r22s),
        "relationships": rels, "population": pop,
        "hazards": {
            "flood": {"stage_m": round(stage, 3), "d_stage_dt": round(dstage, 3),
                      "wet_mask": wet_mask(keyframe), "gauge_id": "gauge:ihnc",
                      "paths": []},
            "cyclone": {"track": load_best_track(), "cone_nm": 0,
                        "rainfall_mm_h": 0,
                        "ghosted": True, "source": "noaa-tcr-al122005"},
            "fire": fire_hazard(keyframe),
            "contamination": contamination_hazard(keyframe),
            "landslide": {"synthetic": False, "active": False, "path": [],
                          "note": "No Katrina landslide binding — hazard off."},
        },
        "plans": [{
            "plan_id": plan_id, "objective": "Protect Zone B against water shortage",
            "status": pstatus, "via": pvia,
            "depends_on": ["bridge:B7", "route:R14"] if pvia == "route:R14" else ["route:R22"],
            "actions": [{"type": "deliver_water", "qty": qty, "to": "zone:B", "via": pvia, "vehicle": "truck:17"}],
            "equity_ok": True, "world_snapshot_id": keyframe,
        }],
        "permits": [{
            "permit_id": "permit-1" if keyframe != "reroute" else "permit-2",
            "plan_id": plan_id, "status": permit, "authorized_actions": ["deliver_water"],
            "conditions": [f"{pvia}.active == true"], "approved_by": "Coordinator Diaz",
            "authorized_route": pvia,
        }],
        "tasks": [{"task_id": "task-dispatch", "plan_id": plan_id, "type": "dispatch",
                   "status": tstatus, "vehicle": "truck:17", "progress": progress, "route": via}],
        "events": events,
        "forecasts": [{"forecast_id": "fc-dep", "forecast_type": "resource_depletion",
                       "subject_entity": "zone:B", "probability": shortage, "band": band,
                       "horizon_hours": pv(params, "forecast_depletion", "horizon_hours"),
                       "world_snapshot_id": keyframe}],
        "pulse": {
            "affected": pop["classes"]["affected"].get("flooded_neighborhoods_retrieved", 0),
            "shortage_prob": shortage, "band": band,
            "water_hours": pv(params, "forecast_depletion", "water_hours_remaining") if keyframe == "t0" else 5.0,
            "truck_status": tstatus, "b7_state": states["bridge:B7"],
            "data_confidence": 0.52 if keyframe == "t0" else 0.71,
            "recommendation_confidence": 0.91,
        },
        "viz": viz_block(params), "zone_rings": ZONE_RINGS, "route_paths": ROUTE_PATHS,
        "geography": geo,
    }


def write_world_files() -> list[Path]:
    params = load_parameters()
    WORLD_DIR.mkdir(parents=True, exist_ok=True)
    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    (WORLD_DIR / "entities.json").write_text(json.dumps({
        "entities": ENTITIES_SPEC, "zone_rings": ZONE_RINGS, "route_paths": ROUTE_PATHS,
    }, indent=2), encoding="utf-8")
    (WORLD_DIR / "relationships.json").write_text(json.dumps(
        [{"from": a, "to": b, "rel": t} for a, b, t in RELATIONSHIPS], indent=2), encoding="utf-8")
    (WORLD_DIR / "timeline.json").write_text(json.dumps({"keyframes": [
        {"id": "t0", "label": "t0 — belief, B7 uncertain", "file": "t0.json"},
        {"id": "b7", "label": "B7 corroborated — truck SUSPENDED", "file": "b7.json"},
        {"id": "reroute", "label": "R22 approved — convoy moving", "file": "reroute.json"},
    ]}, indent=2), encoding="utf-8")
    written = []
    for kf in ("t0", "b7", "reroute"):
        p = SNAP_DIR / f"{kf}.json"
        p.write_text(json.dumps(build_snapshot(params, kf)), encoding="utf-8")
        written.append(p)
    gltf_dir = WEB_PUBLIC / "assets" / "gltf"
    solids_path = WEB_PUBLIC / "assets" / "type-solids.json"
    write_gltf_all(gltf_dir, solids_path)
    (WORLD_DIR / "type-solids.json").write_text(solids_path.read_text(encoding="utf-8"), encoding="utf-8")
    reg_path = WORLD_DIR / "symbol-registry.json"
    if reg_path.exists():
        reg = json.loads(reg_path.read_text(encoding="utf-8"))
        for name, glyph in SYMBOLS.items():
            if "." in name:
                base, variant = name.split(".", 1)
                if base in reg.get("types", {}):
                    reg["types"][base][f"symbol_{variant}"] = glyph
            elif name in reg.get("types", {}):
                reg["types"][name]["symbol_far"] = glyph
        for name, glyph in NONMESH_SYMBOLS.items():
            if name in reg.get("types", {}):
                reg["types"][name]["symbol_far"] = glyph
        for name, cat in CATEGORIES.items():
            if name in reg.get("types", {}):
                reg["types"][name]["category"] = cat
        reg_path.write_text(json.dumps(reg, indent=2), encoding="utf-8")
    pub = WEB_PUBLIC / "data"
    pub.mkdir(parents=True, exist_ok=True)
    for src in [DATA / "parameters.json", WORLD_DIR / "symbol-registry.json",
                WORLD_DIR / "timeline.json", WORLD_DIR / "snapshot.schema.json"]:
        if src.exists():
            (pub / src.name).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    sourced_pub = pub / "sourced"
    sourced_pub.mkdir(exist_ok=True)
    sourced = DATA / "sourced"
    if sourced.exists():
        for p in sourced.glob("*.json"):
            (sourced_pub / p.name).write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
    snap_pub = pub / "snapshots"
    snap_pub.mkdir(exist_ok=True)
    for p in written:
        (snap_pub / p.name).write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
    return written
