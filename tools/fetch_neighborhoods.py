"""Fetch Census 2000 neighborhood pops from The Data Center (retrieved 2026-09-04)."""
from __future__ import annotations

import json
import re
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "katrina" / "sourced" / "neighborhoods_census2000.json"

UA = {"User-Agent": "CrisisOS/1.0 (hackathon research; katrina sources)"}

# HUD/NOAA 31 Aug 2005: Algiers, French Quarter, New Aurora/English Turn = 0 flooded units.
DRY_DISTRICTS = {12, 13}
# French Quarter is in district 1 alongside Warehouse/CBD (57 flooded units).
DRY_SLUGS = {"french-quarter"}

# Approximate neighborhood centroids. Missing slugs fall back to the district center.
DISTRICT_CENTER = {
    1: (-90.0680, 29.9540),
    2: (-90.0820, 29.9320),
    3: (-90.1180, 29.9400),
    4: (-90.0850, 29.9700),
    5: (-90.1080, 30.0080),
    6: (-90.0550, 30.0100),
    7: (-90.0420, 29.9720),
    8: (-90.0180, 29.9640),
    9: (-89.9700, 30.0250),
    10: (-89.9150, 30.0480),
    11: (-89.8000, 30.1100),
    12: (-90.0300, 29.9350),
    13: (-89.9700, 29.9000),
}

CENTROIDS = {
    "central-business-district": (-90.0705, 29.9505),
    "french-quarter": (-90.0640, 29.9584),
    "central-city": (-90.0875, 29.9420),
    "east-riverside": (-90.0780, 29.9205),
    "garden-district": (-90.0855, 29.9285),
    "irish-channel": (-90.0755, 29.9230),
    "lower-garden-district": (-90.0710, 29.9330),
    "milan": (-90.0980, 29.9345),
    "st-thomas-development": (-90.0675, 29.9275),
    "touro": (-90.0935, 29.9255),
    "audubon": (-90.1230, 29.9330),
    "black-pearl": (-90.1340, 29.9420),
    "broadmoor": (-90.1030, 29.9470),
    "dixon": (-90.1180, 29.9630),
    "east-carrollton": (-90.1320, 29.9485),
    "marlyville-fontainebleau": (-90.1090, 29.9500),
    "freret": (-90.1070, 29.9370),
    "hollygrove": (-90.1210, 29.9610),
    "leonidas": (-90.1270, 29.9550),
    "uptown": (-90.1130, 29.9260),
    "west-riverside": (-90.1180, 29.9170),
    "bayou-st-john": (-90.0850, 29.9750),
    "b-w-cooper": (-90.0910, 29.9580),
    "fairgrounds": (-90.0780, 29.9830),
    "gert-town": (-90.1050, 29.9610),
    "iberville-development": (-90.0740, 29.9590),
    "mid-city": (-90.0980, 29.9715),
    "st-bernard-area": (-90.0820, 29.9880),
    "seventh-ward": (-90.0550, 29.9755),
    "treme-lafitte": (-90.0740, 29.9670),
    "tulane-gravier": (-90.0820, 29.9590),
    "city-park": (-90.0880, 29.9860),
    "lakeshore-lake-vista": (-90.1020, 30.0160),
    "lakeview": (-90.1120, 30.0060),
    "lakewood": (-90.1190, 30.0120),
    "navarre": (-90.1090, 29.9980),
    "west-end": (-90.1190, 30.0140),
    "dillard": (-90.0650, 29.9980),
    "filmore": (-90.0750, 30.0100),
    "gentilly-terrace": (-90.0555, 30.0020),
    "gentilly-woods": (-90.0480, 30.0100),
    "lake-terrace-lake-oaks": (-90.0650, 30.0160),
    "milneburg": (-90.0580, 30.0140),
    "pontchartrain-park": (-90.0380, 30.0150),
    "st-anthony": (-90.0700, 30.0050),
    "bywater": (-90.0305, 29.9625),
    "desire-dev-neighborhood": (-90.0320, 29.9880),
    "florida-area": (-90.0380, 29.9820),
    "florida-development": (-90.0400, 29.9780),
    "marigny": (-90.0550, 29.9640),
    "st-claude": (-90.0385, 29.9710),
    "st-roch": (-90.0520, 29.9810),
    "holy-cross": (-90.0178, 29.9583),
    "lower-ninth-ward": (-90.0180, 29.9700),
    "little-woods": (-89.9600, 30.0300),
    "pines-village": (-89.9900, 30.0180),
    "plum-orchard": (-89.9800, 30.0120),
    "read-blvd-east": (-89.9500, 30.0380),
    "read-blvd-west": (-89.9700, 30.0220),
    "west-lake-forest": (-89.9850, 30.0280),
    "village-de-lest": (-89.9150, 30.0480),
    "lake-catherine": (-89.7610, 30.1200),
    "viavant-venetian-isles": (-89.8950, 30.0180),
    "algiers-point": (-90.0550, 29.9515),
    "behrman": (-90.0220, 29.9300),
    "fischer-development": (-90.0350, 29.9350),
    "mcdonogh": (-90.0480, 29.9420),
    "old-aurora": (-90.0100, 29.9200),
    "tall-timbers-brechtel": (-90.0050, 29.9100),
    "us-naval-support-area": (-90.0350, 29.9480),
    "whitney": (-90.0300, 29.9380),
    "new-aurora-english-turn": (-89.9700, 29.9020),
}

POP_ROW = re.compile(
    r"<td[^>]*>\s*Population\s*</td>(.*?)</tr>",
    re.I | re.S,
)
NUM = re.compile(r">\s*([0-9,]+)\s*<")
SKIP_SLUGS = {"feed", "marigny-2", "florida-development"}
# florida-development's 2000 page (1,604) + florida-area overshoots Orleans Parish 484,674 by exactly 1,604.


def get(url: str) -> str | None:
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.read().decode("utf-8", "replace")
    except Exception:
        return None


def discover() -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for i in range(1, 14):
        html = get(f"https://www.datacenterresearch.org/data-resources/neighborhood-data/district-{i}/")
        time.sleep(0.12)
        if not html:
            continue
        seen: set[str] = set()
        for slug in re.findall(rf"/neighborhood-data/district-{i}/([a-z0-9-]+)/", html):
            if slug in SKIP_SLUGS or slug in seen:
                continue
            seen.add(slug)
            found.append((i, slug))
    return found


def parse_pop(html: str) -> int | None:
    m = POP_ROW.search(html)
    if not m:
        return None
    nums = NUM.findall(m.group(1))
    if not nums:
        return None
    return int(nums[0].replace(",", ""))


def title_from_slug(slug: str) -> str:
    return slug.replace("-", " ").title().replace("B W ", "B.W. ").replace("De Lest", "de l'Est")


def main() -> None:
    rows = []
    missing = []
    for district, slug in discover():
        url = f"https://www.datacenterresearch.org/data-resources/neighborhood-data/district-{district}/{slug}/"
        html = get(url)
        time.sleep(0.12)
        pop = parse_pop(html) if html else None
        if pop is None:
            missing.append(f"district-{district}/{slug}")
            print("MISS", district, slug, flush=True)
            continue
        lon, lat = CENTROIDS.get(slug, DISTRICT_CENTER[district])
        flooded = district not in DRY_DISTRICTS and slug not in DRY_SLUGS
        rows.append({
            "id": slug,
            "name": title_from_slug(slug),
            "pop": pop,
            "lon": lon,
            "lat": lat,
            "flooded": flooded,
            "district": f"district-{district}",
            "url": url,
        })
        print("OK", slug, pop, flush=True)

    out = {
        "dataset_id": "census-2000-sf1",
        "compiler": "datacenter-nola",
        "retrieved": "2026-09-04",
        "vintage": "2000",
        "unit": "persons",
        "orleans_parish_total": 484674,
        "note": (
            "Census 2000 SF1 via The Data Center neighborhood statistical areas. "
            "Centroids are approximate neighborhood centers, not block centroids. "
            "flooded flag from HUD/NOAA 31 Aug 2005 planning-district housing-unit flood table "
            "(nola.gov Extent-Depth-of-Flooding-Katrina.pdf / HUD Cityscape 9:1): "
            "Algiers, French Quarter, and New Aurora/English Turn reported 0 flooded units."
        ),
        "missing_slugs": missing,
        "neighborhoods": rows,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print("wrote", OUT, "n=", len(rows), "missing", len(missing), "sum", sum(r["pop"] for r in rows), flush=True)


if __name__ == "__main__":
    main()
