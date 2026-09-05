"""Snap catalog bridges onto OSM ways so 3D decks follow the basemap.

The live imagery is current; Twin Span ways are the 2011 rebuild. Length,
orientation, and position come from those ways — not schematic boxes.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from .catalog import ENTITIES_SPEC

ROOT = Path(__file__).resolve().parents[2]
OSM_ROADS = ROOT / "data" / "katrina" / "sourced" / "osm_roads.json"

# One spec per catalog bridge. Ways are matched by name, then stitched into
# carriageway centerlines. clip_m keeps the Causeway from covering the lake.
BRIDGE_SPECS: dict[str, dict[str, Any]] = {
    "bridge:B7": {
        "name_contains": ["Frank Davis"],
        "highway": ("motorway",),
        "width_m": 16.0,
        "deck_h_m": 12.0,
        "pier_spacing_m": 80.0,
        "clip_m": None,
    },
    "bridge:us11": {
        "name_contains": ["Maestri"],
        "highway": ("primary",),
        "width_m": 11.0,
        "deck_h_m": 9.0,
        "pier_spacing_m": 55.0,
        "clip_m": None,
    },
    "bridge:ccc": {
        "name_contains": ["Crescent City Connection"],
        "highway": ("motorway",),
        "width_m": 16.0,
        "deck_h_m": 42.0,
        "pier_spacing_m": 90.0,
        "clip_m": None,
    },
    "bridge:danziger": {
        "name_contains": ["Chef Menteur"],
        "highway": ("primary",),
        "width_m": 12.0,
        "deck_h_m": 11.0,
        "pier_spacing_m": 40.0,
        "clip_m": None,
    },
    "bridge:causeway": {
        "name_contains": ["Lake Pontchartrain Causeway"],
        "highway": ("trunk",),
        "width_m": 9.0,
        "deck_h_m": 8.0,
        "pier_spacing_m": 70.0,
        "clip_m": 4500.0,
    },
}

JOIN_M = 140.0
DUP_MEAN_M = 12.0
DENSIFY_M = 28.0


def dist_m(a: list, b: list) -> float:
    dy = (b[1] - a[1]) * 110570.0
    dx = (b[0] - a[0]) * 111320.0 * math.cos(a[1] * math.pi / 180.0)
    return math.hypot(dx, dy)


def path_length_m(path: list) -> float:
    return sum(dist_m(path[i], path[i + 1]) for i in range(len(path) - 1))


def heading_deg(path: list) -> float:
    if len(path) < 2:
        return 90.0
    mid = max(1, len(path) // 2)
    a, b = path[max(0, mid - 1)], path[min(len(path) - 1, mid + 1)]
    dlon = (b[0] - a[0]) * math.cos(math.radians(a[1]))
    dlat = b[1] - a[1]
    return (math.degrees(math.atan2(dlon, dlat)) + 360.0) % 360.0


def _nearest_dist(path: list, pin: tuple[float, float]) -> float:
    return min(dist_m(list(pin), pt) for pt in path)


def _cum_m(path: list) -> list[float]:
    out = [0.0]
    for i in range(len(path) - 1):
        out.append(out[-1] + dist_m(path[i], path[i + 1]))
    return out


def densify_path(path: list, spacing_m: float = DENSIFY_M) -> list:
    if len(path) < 2:
        return [list(p) for p in path]
    out = [list(path[0])]
    for i in range(len(path) - 1):
        a, b = path[i], path[i + 1]
        d = dist_m(a, b)
        n = max(1, int(round(d / spacing_m)))
        for k in range(1, n + 1):
            f = k / n
            out.append([a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f])
    return out


def clip_near_pin(path: list, pin: tuple[float, float], max_m: float) -> list:
    if max_m is None or len(path) < 2:
        return path
    cum = _cum_m(path)
    nearest = min(range(len(path)), key=lambda i: dist_m(list(pin), path[i]))
    origin = cum[nearest]
    kept = [path[i] for i, c in enumerate(cum) if abs(c - origin) <= max_m]
    return kept if len(kept) >= 2 else path


def _ref(road: dict) -> str:
    return f"{road.get('ref') or ''} {road.get('name') or ''}"


def _matches(road: dict, spec: dict, pin: tuple[float, float]) -> bool:
    if not road.get("bridge"):
        return False
    hw = spec.get("highway")
    if hw and road.get("highway") not in hw:
        return False
    ref = _ref(road)
    if not any(token in ref for token in spec["name_contains"]):
        return False
    path = road.get("path") or []
    if len(path) < 2:
        return False
    return _nearest_dist(path, pin) < 8000.0


def _hdg(a: list, b: list) -> float:
    dlon = (b[0] - a[0]) * math.cos(math.radians(a[1]))
    dlat = b[1] - a[1]
    return (math.degrees(math.atan2(dlon, dlat)) + 360.0) % 360.0


def _turn_ok(in_a: list, in_b: list, out_a: list, out_b: list, max_deg: float = 55.0) -> bool:
    """Refuse U-turns so dual carriageways stay two decks, not one out-and-back."""
    if dist_m(in_a, in_b) < 2 or dist_m(out_a, out_b) < 2:
        return True
    delta = abs((_hdg(in_a, in_b) - _hdg(out_a, out_b) + 180.0) % 360.0 - 180.0)
    return delta <= max_deg


def _stitch(paths: list[list]) -> list[list]:
    unused = [list(map(list, p)) for p in paths if len(p) >= 2]
    unused.sort(key=path_length_m, reverse=True)
    chains: list[list] = []
    while unused:
        chain = unused.pop(0)
        changed = True
        while changed:
            changed = False
            for i, p in enumerate(unused):
                joined = None
                if dist_m(chain[-1], p[0]) < JOIN_M and _turn_ok(chain[-2], chain[-1], p[0], p[1]):
                    joined = chain + p[1:]
                elif dist_m(chain[-1], p[-1]) < JOIN_M and _turn_ok(chain[-2], chain[-1], p[-1], p[-2]):
                    joined = chain + list(reversed(p))[1:]
                elif dist_m(chain[0], p[-1]) < JOIN_M and _turn_ok(p[-2], p[-1], chain[0], chain[1]):
                    joined = p[:-1] + chain
                elif dist_m(chain[0], p[0]) < JOIN_M and _turn_ok(p[1], p[0], chain[0], chain[1]):
                    joined = list(reversed(p))[:-1] + chain
                if joined is None:
                    continue
                chain = joined
                unused.pop(i)
                changed = True
                break
        chains.append(chain)
    chains.sort(key=path_length_m, reverse=True)
    if not chains:
        return []
    top = path_length_m(chains[0])
    return [c for c in chains if path_length_m(c) >= 0.35 * top]



def _mean_pt(path: list) -> list[float]:
    n = len(path)
    return [sum(p[0] for p in path) / n, sum(p[1] for p in path) / n]


def _drop_duplicates(chains: list[list]) -> list[list]:
    """Keep the longest chain in each ~12 m cluster (same carriageway, two OSM names)."""
    kept: list[list] = []
    for chain in chains:
        pt = _mean_pt(chain)
        if any(dist_m(pt, _mean_pt(k)) < DUP_MEAN_M for k in kept):
            continue
        kept.append(chain)
    return kept[:2]


def _round_path(path: list) -> list[list[float]]:
    return [[round(p[0], 6), round(p[1], 6)] for p in path]


def load_osm_roads() -> list[dict]:
    if not OSM_ROADS.exists():
        return []
    return json.loads(OSM_ROADS.read_text(encoding="utf-8")).get("roads") or []


def load_bridge_spans(roads: list[dict] | None = None) -> dict[str, dict]:
    roads = roads if roads is not None else load_osm_roads()
    pins = {e["entity_id"]: (e["lon"], e["lat"]) for e in ENTITIES_SPEC if e["type"] == "bridge"}
    out: dict[str, dict] = {}
    for eid, spec in BRIDGE_SPECS.items():
        pin = pins[eid]
        matched = [r["path"] for r in roads if _matches(r, spec, pin)]
        chains = _drop_duplicates(_stitch(matched))
        paths = []
        for chain in chains:
            clipped = clip_near_pin(chain, pin, spec["clip_m"])
            dense = densify_path(clipped)
            if path_length_m(dense) < 80:
                continue
            paths.append(_round_path(dense))
        if not paths:
            continue
        out[eid] = {
            "span_paths": paths,
            "span_width_m": spec["width_m"],
            "deck_h_m": spec["deck_h_m"],
            "pier_spacing_m": spec["pier_spacing_m"],
            "heading_deg": round(heading_deg(paths[0]), 1),
            "span_length_m": round(max(path_length_m(p) for p in paths), 1),
        }
    return out
