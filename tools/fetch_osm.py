"""Fetch OSM roads, canals, and building footprints for the Katrina hero region.

Vintage is current OSM (post-2011 Twin Span). Labelled as such in the JSON.
"""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "katrina" / "sourced"

UA = {"User-Agent": "CrisisOS/1.0 (hackathon research; katrina geography)", "Accept": "application/json"}
OVERPASS_MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]


def overpass(query: str) -> dict:
    data = query.encode("utf-8")
    last_err: Exception | None = None
    for url in OVERPASS_MIRRORS:
        try:
            req = urllib.request.Request(url, data=data, headers=UA, method="POST")
            with urllib.request.urlopen(req, timeout=180) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001 — try next mirror
            last_err = exc
            print("overpass fail", url, exc, flush=True)
    raise last_err or RuntimeError("overpass failed")

# Hero region plus a bit of the West Bank / Slidell
BBOX = (29.88, -90.29, 30.32, -89.62)  # s, w, n, e

# Building fabric boxes: land only — do not extend into Lake Pontchartrain or the river.
BUILDING_BOXES = [
    (29.948, -90.038, 29.988, -89.985),  # Lower 9 / Holy Cross / Bywater east
    (29.934, -90.090, 29.965, -90.050),  # CBD / CC / Dome / FQ (south of river)
    (29.990, -90.128, 30.0255, -90.085),  # Lakeview (south of seawall)
    (29.990, -90.085, 30.0255, -90.020),  # Gentilly
    (29.940, -90.110, 29.975, -90.070),  # Central City / Touro / Memorial
    (29.905, -90.060, 29.952, -89.995),  # Algiers west bank
    (29.995, -90.015, 30.050, -89.890),  # New Orleans East
    (29.918, -90.145, 29.968, -90.095),  # Uptown / Carrollton
    (30.090, -89.775, 30.145, -89.720),  # Lake Catherine land strip
    (29.995, -89.920, 30.035, -89.860),  # Venetian Isles / Chef Menteur
]
PER_BOX = 400


def way_line(el: dict) -> list[list[float]] | None:
    geom = el.get("geometry") or []
    if len(geom) < 2:
        return None
    line = [[round(p["lon"], 5), round(p["lat"], 5)] for p in geom]
    if line[0] == line[-1] and len(line) > 2:
        return line
    return line


def way_ring(el: dict) -> list[list[float]] | None:
    line = way_line(el)
    if not line or len(line) < 4:
        return None
    if line[0] != line[-1]:
        line = line + [line[0]]
    if len(line) > 24:
        step = max(1, len(line) // 20)
        core = line[:-1:step]
        line = core + [line[0]]
    return line


def ring_area(ring: list[list[float]]) -> float:
    a = 0.0
    for i in range(len(ring) - 1):
        a += ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1]
    return abs(a) * 0.5


def classify_building(tags: dict) -> str:
    amenity = (tags.get("amenity") or "").lower()
    b = (tags.get("building") or "").lower()
    if amenity == "hospital" or b == "hospital":
        return "hospital"
    if amenity in ("school", "college", "university") or b == "school":
        return "school"
    if b in ("warehouse", "industrial") or amenity == "warehouse":
        return "warehouse"
    if amenity in ("place_of_worship", "theatre", "stadium"):
        return "landmark"
    if b in ("commercial", "retail", "office", "hotel") or amenity in ("townhall", "bank"):
        return "commercial"
    if b in ("apartments", "residential", "house", "detached", "terrace", "semidetached_house", "yes"):
        return "residential"
    return "residential"


HEIGHTS = {
    "residential": 9, "commercial": 18, "hospital": 28, "warehouse": 16,
    "school": 14, "landmark": 22,
}


def fetch_roads_canals() -> tuple[list[dict], list[dict]]:
    s, w, n, e = BBOX
    q = f"""
[out:json][timeout:120];
(
  way["highway"~"^(motorway|motorway_link|trunk|trunk_link|primary|primary_link|secondary)$"]({s},{w},{n},{e});
  way["waterway"~"^(canal|river)$"](29.90,-90.16,30.05,-89.86);
);
out geom;
"""
    raw = overpass(q)
    roads, canals = [], []
    for el in raw.get("elements", []):
        if el.get("type") != "way":
            continue
        tags = el.get("tags") or {}
        line = way_line(el)
        if not line:
            continue
        if tags.get("highway"):
            roads.append({
                "id": f"osm-way-{el['id']}",
                "highway": tags.get("highway"),
                "name": tags.get("name") or tags.get("ref") or "",
                "ref": tags.get("ref") or "",
                "bridge": tags.get("bridge") == "yes",
                "path": line,
            })
        elif tags.get("waterway"):
            canals.append({
                "id": f"osm-way-{el['id']}",
                "waterway": tags.get("waterway"),
                "name": tags.get("name") or "",
                "path": line,
            })
    return roads, canals


def ring_centroid(ring: list[list[float]]) -> tuple[float, float]:
    pts = ring[:-1] if ring[0] == ring[-1] else ring
    return sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)


def in_open_water(lon: float, lat: float) -> bool:
    """Lake Pontchartrain north of the seawall, and the Mississippi between FQ and Algiers."""
    if lon < -89.88 and lat > 30.0265:
        return True
    if 29.952 < lat < 29.958 and -90.052 < lon < -90.045:
        return True
    return False


def fetch_buildings() -> list[dict]:
    seen: set[int] = set()
    kept: list[dict] = []
    for s, w, n, e in BUILDING_BOXES:
        q = f"""
[out:json][timeout:90];
way["building"]({s},{w},{n},{e});
out geom;
"""
        raw = overpass(q)
        box_rows = []
        for el in raw.get("elements", []):
            if el.get("type") != "way" or el["id"] in seen:
                continue
            tags = el.get("tags") or {}
            if not tags.get("building"):
                continue
            ring = way_ring(el)
            if not ring:
                continue
            clon, clat = ring_centroid(ring)
            if in_open_water(clon, clat):
                continue
            area = ring_area(ring)
            if area < 1e-10:
                continue
            seen.add(el["id"])
            kind = classify_building(tags)
            box_rows.append({
                "id": f"bldg-{el['id']}",
                "kind": kind,
                "name": tags.get("name") or "",
                "height_m": HEIGHTS[kind],
                "ring": ring,
                "cx": round(clon, 5),
                "cy": round(clat, 5),
                "area": area,
            })
        box_rows.sort(key=lambda r: r["area"], reverse=True)
        kept.extend(box_rows[:PER_BOX])
        print("  box", s, w, "n=", min(len(box_rows), PER_BOX), flush=True)
    for r in kept:
        r.pop("area", None)
    return kept


def main() -> None:
    import sys
    buildings_only = "--buildings" in sys.argv
    OUT.mkdir(parents=True, exist_ok=True)
    meta = {
        "compiler": "openstreetmap",
        "retrieved": "2026-09-04",
        "vintage": "current — WRONG for 2005 (Twin Span is the 2011 rebuild)",
        "source_key": "osm-extract-nola",
        "attribution": "© OpenStreetMap contributors",
    }
    if not buildings_only:
        print("overpass roads+canals…", flush=True)
        roads, canals = fetch_roads_canals()
        print("roads", len(roads), "canals", len(canals), flush=True)
        (OUT / "osm_roads.json").write_text(json.dumps({**meta, "roads": roads}, separators=(",", ":")), encoding="utf-8")
        (OUT / "osm_canals.json").write_text(json.dumps({**meta, "canals": canals}, separators=(",", ":")), encoding="utf-8")
    print("overpass buildings…", flush=True)
    buildings = fetch_buildings()
    print("buildings", len(buildings), flush=True)
    (OUT / "osm_buildings.json").write_text(json.dumps({**meta, "buildings": buildings}, separators=(",", ":")), encoding="utf-8")
    print("wrote", OUT, flush=True)


if __name__ == "__main__":
    main()
