"""Replay-clock population field.

Census 2000 NSA counts are the spatial prior (street fabric = OSM building /
road samples). Remaining share is continuous in event time between sourced
anchors (28 Aug ~100k, early-Sep several thousand, July 2006 city total).
In-between values are design:gap-fill interpolants. Does not rewrite snapshot JSON.

The renderer joins each heat sample to this tick's HUD flood bowl (street-level).
`movement` is the orange-arc geometry for this tick.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from .snapshot import load_neighborhoods, load_parameters, pv

# Remaining share of Census 2000 NSA counts in HUD-flooded vs unflooded
# neighborhoods. Linear in event t between rows. p6-rebuild is replaced at
# runtime with July 2006 / Census 2000 (sourced city total).
FRAC: tuple[tuple[str, float, float, str], ...] = (
    ("p1-parish-evac", 0.97, 1.00, "design:gap-fill"),
    ("p1-nagin-soe", 0.82, 0.95, "design:gap-fill"),
    ("p1-mandatory-nola", 0.50, 0.72, "design:gap-fill"),
    ("p1-contraflow", 0.22, 0.42, "design:gap-fill"),
    ("p1-remain", 0.16, 0.28, "wiki-katrina-nola-effects"),
    ("p2-ihnc-east-monolith", 0.11, 0.27, "design:gap-fill"),
    ("p2-17th-open", 0.07, 0.26, "design:gap-fill"),
    ("p2-catastrophic-flood", 0.045, 0.25, "design:gap-fill"),
    ("p3-80pct", 0.035, 0.24, "design:gap-fill"),
    ("p3-max-inundation", 0.03, 0.22, "design:gap-fill"),
    ("p3-rescues-thousands", 0.022, 0.18, "design:gap-fill"),
    ("p4-evac-houston", 0.010, 0.07, "design:gap-fill"),
    ("p5-dome-cc-cleared", 0.004, 0.010, "rand-tr369-repopulation"),
    ("p6-l9-dry-enough", 0.008, 0.05, "design:gap-fill"),
    ("p6-40pct", 0.012, 0.07, "design:gap-fill"),
    ("p6-october-dry", 0.02, 0.12, "design:gap-fill"),
    ("p6-rebuild", 0.38, 0.70, "census-fff-katrina-2015"),
)

# Occupancy at that event time; linear in t between rows. Holds pin sourced beats.
DOME: tuple[tuple[str, int, str], ...] = (
    ("p1-rta-buses", 2000, "design:gap-fill"),
    ("p1-dome-opens", 4000, "design:gap-fill"),
    ("p1-dome-evening", 11000, "whitehouse-katrina-lessons-ch3"),
    ("p1-remain", 11000, "whitehouse-katrina-lessons-ch3"),
    ("p2-rooftop-start", 15000, "design:gap-fill"),
    ("p2-dome-conditions", 16000, "design:gap-fill"),
    ("p3-80pct", 18000, "design:gap-fill"),
    ("p3-max-inundation", 20000, "nyt-superdome-2005-09-01"),
    ("p3-dome-to-cc", 16000, "design:gap-fill"),
    ("p3-cc-crisis", 16000, "design:gap-fill"),
    ("p4-dome-15000", 5500, "design:gap-fill"),
    ("p4-evac-houston", 1500, "design:gap-fill"),
    ("p5-dome-cc-cleared", 0, "npr-dome-cc-empty-2005-09-04"),
)

MORIAL: tuple[tuple[str, int, str], ...] = (
    ("p3-80pct", 3000, "design:gap-fill"),
    ("p3-bowl-rising", 8000, "design:gap-fill"),
    ("p3-max-inundation", 14000, "design:gap-fill"),
    ("p3-dome-to-cc", 16000, "design:gap-fill"),
    ("p3-cc-crisis", 19000, "house-select-katrina"),
    ("p4-evac-houston", 6000, "design:gap-fill"),
    ("p5-dome-cc-cleared", 0, "npr-dome-cc-empty-2005-09-04"),
)

CLOVER: tuple[tuple[str, int, str], ...] = (
    ("p4-evac-houston", 3500, "design:gap-fill"),
    ("p5-dome-cc-cleared", 0, "npr-dome-cc-empty-2005-09-04"),
)

ROOFTOP_HOODS = (
    "lower-ninth-ward", "lakeview", "gentilly-woods", "filmore",
    "little-woods", "mid-city", "bywater",
)
# Keep rescue arcs readable — three flooded bowls, not every rooftop pin.
ROOFTOP_ARC_HOODS = ("lower-ninth-ward", "lakeview", "gentilly-woods")


def _elapsed(idx: int, script: dict) -> set[str]:
    return {ev["id"] for ev in script["events"][: idx + 1]}


def _last(table: tuple[tuple[str, int, str], ...], elapsed: set[str]) -> tuple[int, str]:
    val, src = 0, "census-2000-sf1"
    for eid, n, key in table:
        if eid in elapsed:
            val, src = n, key
    return val, src


def _dt(ts: str) -> datetime:
    return datetime.fromisoformat(ts)


def _lerp(a: float, b: float, u: float) -> float:
    return a + (b - a) * u


def _event_times(script: dict) -> dict[str, datetime]:
    return {e["id"]: _dt(e["t"]) for e in script["events"]}


def _interp_frac(
    t: datetime, script: dict, table: tuple,
) -> tuple[float, float, str, bool]:
    times = _event_times(script)
    pts: list[tuple[datetime, float, float, str]] = []
    for row in table:
        eid, w, d, src = row[0], row[1], row[2], row[3]
        if eid in times:
            pts.append((times[eid], float(w), float(d), src))
    pts.sort(key=lambda x: x[0])
    if not pts or t < pts[0][0]:
        return 1.0, 1.0, "census-2000-sf1", False
    if t >= pts[-1][0]:
        return pts[-1][1], pts[-1][2], pts[-1][3], False
    for i in range(1, len(pts)):
        t0, w0, d0, s0 = pts[i - 1]
        t1, w1, d1, s1 = pts[i]
        if t <= t1:
            span = (t1 - t0).total_seconds()
            u = 0.0 if span <= 0 else (t - t0).total_seconds() / span
            gap = 0.0 < u < 1.0
            src = s0 if u <= 0 else (s1 if u >= 1 else "design:gap-fill")
            return _lerp(w0, w1, u), _lerp(d0, d1, u), src, gap
    return pts[-1][1], pts[-1][2], pts[-1][3], False


def _interp_occ(
    t: datetime, script: dict, table: tuple[tuple[str, int, str], ...],
) -> tuple[int, str, bool]:
    times = _event_times(script)
    pts = [(times[eid], float(n), src) for eid, n, src in table if eid in times]
    pts.sort(key=lambda x: x[0])
    if not pts or t < pts[0][0]:
        return 0, "census-2000-sf1", False
    if t >= pts[-1][0]:
        return int(round(pts[-1][1])), pts[-1][2], False
    for i in range(1, len(pts)):
        t0, n0, s0 = pts[i - 1]
        t1, n1, s1 = pts[i]
        if t <= t1:
            span = (t1 - t0).total_seconds()
            u = 0.0 if span <= 0 else (t - t0).total_seconds() / span
            gap = 0.0 < u < 1.0
            src = s0 if u <= 0 else (s1 if u >= 1 else "design:gap-fill")
            return int(round(_lerp(n0, n1, u))), src, gap
    return int(round(pts[-1][1])), pts[-1][2], False


def _frac_table(params: dict, census: int) -> tuple:
    july = int(pv(params, "population_clock", "orleans_july_2006"))
    r = (july / census) if census else 0.47
    out = []
    for eid, w, d, src in FRAC:
        if eid == "p6-rebuild":
            out.append((eid, r, r, "census-fff-katrina-2015"))
        else:
            out.append((eid, w, d, src))
    return tuple(out)


def _wet_dry(elapsed: set[str]) -> tuple[float, float]:
    wet, dry = 1.0, 1.0
    for eid, w, d, *_ in FRAC:
        if eid in elapsed:
            wet, dry = w, d
    return wet, dry


def _hood_shares() -> tuple[int, float, float, list[dict]]:
    hoods = load_neighborhoods()
    total = int(hoods["orleans_parish_total"])
    flooded = sum(n["pop"] for n in hoods["neighborhoods"] if n.get("flooded"))
    dry = total - flooded
    return total, flooded / total, dry / total, hoods["neighborhoods"]


def _pin(eid: str) -> dict[str, float]:
    from .catalog import ENTITIES_SPEC
    spec = next(x for x in ENTITIES_SPEC if x["entity_id"] == eid)
    return {"lon": spec["lon"], "lat": spec["lat"]}


def _xy(src: str | list[float] | tuple[float, float]) -> list[float]:
    if isinstance(src, (list, tuple)):
        return [float(src[0]), float(src[1])]
    p = _pin(src)
    return [p["lon"], p["lat"]]


def _mag(n: int) -> float:
    return round(max(0.22, min(1.0, max(0, n) / 180000.0)), 3)


def _arc(
    frm: str | list[float],
    to: str | list[float],
    count: int,
    kind: str,
    src: str,
) -> dict[str, Any]:
    n = max(0, int(count))
    return {
        "from": _xy(frm),
        "to": _xy(to),
        "from_id": frm if isinstance(frm, str) else None,
        "to_id": to if isinstance(to, str) else None,
        "count": n,
        "magnitude": _mag(n if n else 8000),
        "kind": kind,
        "source": src,
    }


def _hood_xy(hoods: list[dict], hid: str) -> list[float] | None:
    for n in hoods:
        if n.get("id") == hid:
            return [n["lon"], n["lat"]]
    return None


def movement_for(
    ev: dict[str, Any],
    elapsed: set[str],
    classes: dict[str, Any],
    hoods: list[dict],
) -> list[dict[str, Any]]:
    """Held orange-arc flows for this tick. Catalog pins only — no Houston coords."""
    if ev.get("phase", 0) == 0 or ev.get("phase", 0) >= 6:
        return []
    if "p5-dome-cc-cleared" in elapsed and ev.get("id") != "p5-dome-cc-cleared":
        return []

    dome = int(classes.get("shelter:dome") or 0)
    cc = int(classes.get("shelter:morial") or 0)
    cl = int(classes.get("camp:cloverleaf") or 0)
    gone = int(classes.get("evacuated") or 0)
    rooftop = int(classes.get("rooftop") or 0)
    moves: list[dict[str, Any]] = []

    if ev.get("phase") == 1 and "p1-parish-evac" in elapsed:
        if gone > 0:
            moves.append(_arc("comms:eoc", "camp:cloverleaf", gone, "outbound",
                              "p1 outbound west via I-10 / Causeway"))
            moves.append(_arc("zone:B", "route:R14", gone, "outbound",
                              "p1 outbound east via I-10 Twin Span"))
        if dome > 0:
            moves.append(_arc("zone:B", "shelter:dome", dome, "to_shelter",
                              "refuge of last resort"))
            moves.append(_arc("comms:eoc", "shelter:dome", dome, "to_shelter",
                              "RTA / downtown to Superdome"))
        return moves

    off_map = (
        "p4-dome-15000" in elapsed
        or "p4-evac-houston" in elapsed
        or ev.get("id") == "p5-dome-cc-cleared"
    )
    xfer = (
        ("p3-dome-uninhabitable" in elapsed or "p3-dome-to-cc" in elapsed)
        and not off_map
    )

    if off_map:
        # MSY is the west catalog pin. Do not draw Houston geography.
        n_dome = max(dome, 15000 if ev.get("id") == "p5-dome-cc-cleared" else dome, 1500)
        n_cc = max(cc, 19000 if ev.get("id") == "p5-dome-cc-cleared" else cc, 1500)
        moves.append(_arc("shelter:dome", "airport:msy", n_dome, "off_map",
                          "shelter evac west via MSY — catalog pin only"))
        moves.append(_arc("shelter:morial", "airport:msy", n_cc, "off_map",
                          "shelter evac west via MSY — catalog pin only"))
        if cl > 0:
            moves.append(_arc("camp:cloverleaf", "airport:msy", cl, "off_map",
                              "cloverleaf staging west"))
        return moves

    if xfer:
        n = max(dome, cc, 4000)
        moves.append(_arc("shelter:dome", "shelter:morial", n, "dome_to_cc",
                          "p3-dome-to-cc"))
        if cc > 0:
            moves.append(_arc("zone:B", "shelter:morial", cc, "to_shelter",
                              "Lower 9 / flooded bowls to Convention Center"))
        return moves

    if dome > 0:
        moves.append(_arc("zone:B", "shelter:dome", dome, "to_shelter",
                          "Lower 9 / flooded bowls to Superdome"))
    if cc > 0:
        moves.append(_arc("zone:B", "shelter:morial", cc, "to_shelter",
                          "Lower 9 / flooded bowls to Convention Center"))
    if rooftop > 0:
        each = max(1, rooftop // max(1, len(ROOFTOP_ARC_HOODS)))
        for hid in ROOFTOP_ARC_HOODS:
            xy = _hood_xy(hoods, hid)
            if xy:
                moves.append(_arc(xy, "shelter:dome", each, "rescue",
                                  f"rooftop / attic — {hid}"))
    return moves


def _hotspot(eid: str, name: str, n: int, src: str) -> dict[str, Any] | None:
    if n <= 0:
        return None
    pin = _pin(eid)
    return {
        "entity_id": eid,
        "name": name,
        "lon": pin["lon"],
        "lat": pin["lat"],
        "people": n,
        "weight": float(n),
        "source_key": src,
    }


def population_delta(idx: int, script: dict | None = None) -> dict[str, Any]:
    if script is None:
        from .replay import load_script
        script = load_script()
    events = script["events"]
    if not events or idx < 0 or idx >= len(events):
        idx = 0
    ev = events[idx]
    params = load_parameters()
    census = int(pv(params, "population_clock", "orleans_census_2000"))
    remain_28 = int(pv(params, "population_clock", "city_remaining_28aug"))
    total, f_share, d_share, hoods = _hood_shares()
    elapsed = _elapsed(idx, script)
    t = _dt(ev["t"])
    wet, dry, frac_src, frac_gap = _interp_frac(t, script, _frac_table(params, census))
    residential = int(round(census * (f_share * wet + d_share * dry)))
    dome_n, dome_src, dome_gap = _interp_occ(t, script, DOME)
    cc_n, cc_src, cc_gap = _interp_occ(t, script, MORIAL)
    cl_n, cl_src, cl_gap = _interp_occ(t, script, CLOVER)
    bowl_empty = float(pv(params, "population_clock", "heatmap_bowl_empty"))

    if "p1-remain" in elapsed and "p2-ihnc-east-monolith" not in elapsed:
        # Hold city remaining to the sourced 28 Aug evening figure.
        residential = max(0, remain_28 - dome_n)
    if "p5-dome-cc-cleared" in elapsed and "p6-l9-dry-enough" not in elapsed:
        residential = int(pv(params, "population_clock", "city_cleared_early_sep"))

    hotspots = []
    for row in (
        _hotspot("shelter:dome", "Louisiana Superdome", dome_n, dome_src),
        _hotspot("shelter:morial", "Ernest N. Morial Convention Center", cc_n, cc_src),
        _hotspot("camp:cloverleaf", "I-10 / Causeway cloverleaf", cl_n, cl_src),
    ):
        if row:
            hotspots.append(row)

    rooftop = 0
    if "p2-rooftop-start" in elapsed and "p4-sar-transition" not in elapsed:
        rooftop = int(round(census * f_share * wet * 0.45))
        pins = [n for n in hoods if n["id"] in ROOFTOP_HOODS]
        if pins and rooftop > 0:
            each = rooftop / len(pins)
            for n in pins:
                hotspots.append({
                    "entity_id": f"rooftop:{n['id']}",
                    "name": f"rooftop / attic — {n['name']}",
                    "lon": n["lon"],
                    "lat": n["lat"],
                    "people": int(round(each)),
                    "weight": each,
                    "source_key": "design:gap-fill",
                })

    city_in = residential + dome_n + cc_n + cl_n
    gap = frac_gap or dome_gap or cc_gap or cl_gap or any(
        h["source_key"] == "design:gap-fill" for h in hotspots
    )
    sources = ["census-2000-sf1"]
    for key in (frac_src, dome_src, cc_src, cl_src):
        if key not in sources:
            sources.append(key)
    for h in hotspots:
        if h["source_key"] not in sources:
            sources.append(h["source_key"])
    classes = {
        "city_in": city_in,
        "residential": residential,
        "shelter:dome": dome_n,
        "shelter:morial": cc_n,
        "camp:cloverleaf": cl_n,
        "rooftop": rooftop,
        "evacuated": max(0, census - city_in),
    }
    movement = movement_for(ev, elapsed, classes, hoods)
    return {
        "event_id": ev["id"],
        "wet_frac": round(wet, 6),
        "dry_frac": round(dry, 6),
        "residential_in": residential,
        "city_in": city_in,
        "census_2000": census,
        "city_frac": round(city_in / census, 4) if census else 0,
        "hotspots": hotspots,
        "classes": classes,
        "movement": movement,
        "street": {
            "bowl_empty": bowl_empty,
            "rule": (
                "heat sample inside this tick's HUD bowl: wet_frac × (1 − bowl_empty × bowl.wet_frac); "
                "else dry_frac. Pre-flood: neighborhood flooded flag."
            ),
        },
        "continuous": True,
        "source_keys": sources,
        "gap_fill": gap,
        "note": (
            f"heatmap · continuous t · {city_in:,} in Orleans of {census:,} Census 2000 · "
            f"flooded NSA ×{wet:.2f} · dry NSA ×{dry:.2f}"
        ),
    }
