"""Snap Census neighborhood pins onto land using OSM building centroids.

Does not change population counts — only lon/lat. Lake / river pins are rejected.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCED = ROOT / "data" / "katrina" / "sourced"

# Land-safe pins for NSAs whose geometric center is water, marsh, or park lagoon.
LAND_PINS = {
    "lake-catherine": (-89.761, 30.120),          # Chef Menteur houses, not the lake
    "viavant-venetian-isles": (-89.895, 30.018),  # Chef Menteur land, not the lake
    "west-end": (-90.119, 30.014),                 # streets south of the harbor
    "lakeshore-lake-vista": (-90.102, 30.016),     # inland of Lakeshore Dr
    "lake-terrace-lake-oaks": (-90.065, 30.016),
    "city-park": (-90.088, 29.986),                # south edge (residential), not lagoons
    "algiers-point": (-90.0550, 29.9515),          # west bank, not mid-river
    "pontchartrain-park": (-90.038, 30.015),
    "milneburg": (-90.058, 30.014),
    "village-de-lest": (-89.912, 30.042),
}


def ring_centroid(ring: list) -> tuple[float, float]:
    pts = ring[:-1] if ring and ring[0] == ring[-1] else ring
    return sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)


def in_open_water(lon: float, lat: float) -> bool:
    if lon < -89.88 and lat > 30.0265:
        return True
    if 29.952 < lat < 29.958 and -90.052 < lon < -90.045:
        return True
    if 29.988 < lat < 30.012 and -90.105 < lon < -90.085:
        return True  # City Park lagoons
    return False


def main() -> None:
    hoods = json.loads((SOURCED / "neighborhoods_census2000.json").read_text(encoding="utf-8"))
    bldgs = json.loads((SOURCED / "osm_buildings.json").read_text(encoding="utf-8")).get("buildings", [])
    sites = []
    for b in bldgs:
        if "cx" in b:
            sites.append((b["cx"], b["cy"]))
        else:
            sites.append(ring_centroid(b["ring"]))

    moved = 0
    for n in hoods["neighborhoods"]:
        lon, lat = n["lon"], n["lat"]
        if n["id"] in LAND_PINS:
            lon, lat = LAND_PINS[n["id"]]
        if sites:
            best, bd = sites[0], 1e9
            for sx, sy in sites:
                d = (sx - lon) ** 2 + (sy - lat) ** 2
                if d < bd:
                    bd, best = d, (sx, sy)
            # Snap to a building only if it is in the same neighborhood (~1.6 km)
            if bd < 0.015 ** 2:
                lon, lat = best
        if in_open_water(lon, lat) and n["id"] in LAND_PINS:
            lon, lat = LAND_PINS[n["id"]]
        if in_open_water(lon, lat):
            lat = min(lat, 30.024)
            if 29.952 < lat < 29.958 and -90.052 < lon < -90.045:
                lon, lat = -90.0550, 29.9515
        if (lon, lat) != (n["lon"], n["lat"]):
            moved += 1
        n["lon"], n["lat"] = round(lon, 5), round(lat, 5)
        n["on_land"] = not in_open_water(n["lon"], n["lat"])

    hoods["note"] = (
        hoods.get("note", "")
        + " Centroids snapped onto OSM building footprints / land-safe pins so the density field does not paint Lake Pontchartrain or the Mississippi."
    )
    (SOURCED / "neighborhoods_census2000.json").write_text(
        json.dumps(hoods, indent=2), encoding="utf-8"
    )
    wet = [n["id"] for n in hoods["neighborhoods"] if not n["on_land"]]
    print("moved", moved, "still_water", wet, flush=True)


if __name__ == "__main__":
    main()
