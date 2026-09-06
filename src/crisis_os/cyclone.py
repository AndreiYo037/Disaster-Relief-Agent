"""Katrina cyclone pose along HURDAT2 AL122005 (build phase B).

Interpolates eye lon/lat, wind, and 34-kt mean radius. Does not change
catalog entity state. Rain stays 0 unless a rainfall figure is bound elsewhere.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HURDAT_TXT = ROOT / "data" / "katrina" / "sourced" / "hurdat2_al122005.txt"
HURDAT_JSON = ROOT / "data" / "katrina" / "sourced" / "hurdat2_al122005.json"
PUBLIC_JSON = ROOT / "web" / "public" / "data" / "sourced" / "hurdat2_al122005.json"

# 29 Aug 04:30 CDT = first IHNC overtop in the event script — end of cyclone-only window.
CYCLONE_WINDOW_END = datetime.fromisoformat("2005-08-29T04:30:00-05:00")
# Last HURDAT2 fix still in the NOLA landfall story (p2-second-landfall + a short inland stub).
# Do not paint the extra-tropical track to Ohio — that is not the event-script cyclone route.
TRACK_DRAW_END = datetime(2005, 8, 29, 18, 0, tzinfo=timezone.utc)
NM_M = 1852.0
SOURCE_KEY = "hurdat2-al122005"


def sshws_cat(wind_kt: float, status: str) -> int:
    if wind_kt < 64:
        return 0
    if wind_kt < 83:
        return 1
    if wind_kt < 96:
        return 2
    if wind_kt < 113:
        return 3
    if wind_kt < 137:
        return 4
    return 5


def _parse_latlon(token: str) -> float:
    token = token.strip()
    hemi = token[-1]
    mag = float(token[:-1])
    if hemi in ("S", "W"):
        return -mag
    return mag


def _r34_mean(quads: list[int]) -> float | None:
    vals = [q for q in quads if q != -999]
    if not vals:
        return None
    return round(sum(vals) / len(vals), 1)


def parse_hurdat_txt(text: str) -> list[dict]:
    rows = []
    for line in text.splitlines():
        if line.startswith("AL") or not line.strip():
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 8:
            continue
        date, hhmm, record, status = parts[0], parts[1], parts[2], parts[3]
        lat = _parse_latlon(parts[4])
        lon = _parse_latlon(parts[5])
        wind_kt = int(parts[6])
        pres = int(parts[7]) if parts[7] not in ("", "-999") else None
        quads = [int(parts[i]) for i in range(8, 12)] if len(parts) >= 12 else [-999] * 4
        hour = int(hhmm[:2])
        minute = int(hhmm[2:]) if len(hhmm) >= 4 else 0
        utc = datetime(
            int(date[:4]), int(date[4:6]), int(date[6:8]), hour, minute, tzinfo=timezone.utc,
        )
        r34 = _r34_mean(quads)
        rows.append({
            "utc": utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "lat": lat, "lon": lon, "wind_kt": wind_kt,
            "pressure_mb": pres, "status": status,
            "record": record or None,
            "r34_ne_nm": quads[0], "r34_se_nm": quads[1],
            "r34_sw_nm": quads[2], "r34_nw_nm": quads[3],
            "r34_nm": r34, "cat": sshws_cat(wind_kt, status),
        })
    rows.sort(key=lambda r: r["utc"])
    return rows


@lru_cache(maxsize=1)
def load_track() -> list[dict]:
    if HURDAT_TXT.exists():
        return parse_hurdat_txt(HURDAT_TXT.read_text(encoding="utf-8"))
    return json.loads(HURDAT_JSON.read_text(encoding="utf-8"))["track"]


def track_document() -> dict:
    return {
        "storm_id": "AL122005",
        "name": "KATRINA",
        "source_key": SOURCE_KEY,
        "source": "NHC HURDAT2 Atlantic best track (AL122005), 34-kt radii in nautical miles",
        "url": "https://www.nhc.noaa.gov/data/hurdat/hurdat2-1851-2024-040425.txt",
        "retrieved": "2026-09-06",
        "note": (
            "r34_nm is the mean of non-missing 34-kt quadrant radii. "
            "Landfall rows often have -999 radii; interpolation uses neighbouring synoptic fixes. "
            "This is the wind field, not the ~25 nm eye diameter."
        ),
        "track": load_track(),
    }


def _ts(row: dict) -> datetime:
    return datetime.fromisoformat(row["utc"].replace("Z", "+00:00"))


def _lerp(a: float, b: float, u: float) -> float:
    return a + (b - a) * u


def _r34_at(row: dict, fallback: float) -> float:
    v = row.get("r34_nm")
    return fallback if v is None else float(v)


def _is_cyclone_beat(ev: dict) -> bool:
    if "meteorology" in (ev.get("layers") or []):
        return True
    return "hazards.cyclone" in (ev.get("binds") or [])


def _ahead_horizon(dt: datetime) -> datetime:
    """Ghost path runs only to the next script meteorology / cyclone beat."""
    dt_utc = dt.astimezone(timezone.utc)
    try:
        from .replay import load_script
        later = next(
            (
                e for e in load_script()["events"]
                if _is_cyclone_beat(e) and datetime.fromisoformat(e["t"]) > dt
            ),
            None,
        )
    except Exception:
        later = None
    if later is None:
        return TRACK_DRAW_END
    horizon = datetime.fromisoformat(later["t"]).astimezone(timezone.utc)
    return min(horizon, TRACK_DRAW_END)


def pose_at(t) -> dict:
    """Eye / R34 at an aware datetime or ISO string (CDT or UTC)."""
    if isinstance(t, str):
        dt = datetime.fromisoformat(t.replace("Z", "+00:00"))
    else:
        dt = t
    if dt.tzinfo is None:
        raise ValueError("pose_at requires a timezone-aware timestamp")
    dt_utc = dt.astimezone(timezone.utc)
    track = load_track()
    times = [_ts(r) for r in track]
    if dt_utc <= times[0]:
        i0, i1, u = 0, 0, 0.0
    elif dt_utc >= times[-1]:
        i0, i1, u = len(track) - 1, len(track) - 1, 0.0
    else:
        i1 = next(i for i, ts in enumerate(times) if ts >= dt_utc)
        i0 = i1 - 1
        span = (times[i1] - times[i0]).total_seconds()
        u = 0.0 if span <= 0 else (dt_utc - times[i0]).total_seconds() / span
    a, b = track[i0], track[i1]
    r_a = _r34_at(a, 0.0)
    r_b = _r34_at(b, r_a)
    r34 = round(_lerp(r_a, r_b, u), 1)
    wind = round(_lerp(a["wind_kt"], b["wind_kt"], u), 1)
    lon = round(_lerp(a["lon"], b["lon"], u), 4)
    lat = round(_lerp(a["lat"], b["lat"], u), 4)
    cat = sshws_cat(wind, b["status"] if u >= 0.5 else a["status"])
    horizon = _ahead_horizon(dt)
    flown = [
        [p["lon"], p["lat"]] for p in track[: i0 + 1]
        if _ts(p) <= TRACK_DRAW_END
    ]
    if not flown or flown[-1] != [lon, lat]:
        if dt_utc <= TRACK_DRAW_END:
            flown.append([lon, lat])
    ahead = [[lon, lat]] if dt_utc <= TRACK_DRAW_END else []
    for p in track[i1:]:
        ts = _ts(p)
        if ts > horizon:
            break
        ahead.append([p["lon"], p["lat"]])
    if len(ahead) < 2 and i1 < len(track) and _ts(track[i1]) <= TRACK_DRAW_END:
        ahead = [[lon, lat], [track[i1]["lon"], track[i1]["lat"]]]
    window = dt <= CYCLONE_WINDOW_END or dt_utc <= CYCLONE_WINDOW_END.astimezone(timezone.utc)
    return {
        "lon": lon, "lat": lat, "wind_kt": wind, "cat": cat, "r34_nm": r34,
        "r34_m": round(r34 * NM_M),
        "rainfall_mm_h": 0,
        "flown": flown, "ahead": ahead,
        "source_key": SOURCE_KEY,
        "radius_binding": "hurdat2 34-kt quadrant mean",
        "camera": "gulf" if window else "nola",
        "utc": dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def write_json() -> None:
    doc = track_document()
    body = json.dumps(doc, indent=2)
    HURDAT_JSON.write_text(body + "\n", encoding="utf-8")
    PUBLIC_JSON.parent.mkdir(parents=True, exist_ok=True)
    PUBLIC_JSON.write_text(body + "\n", encoding="utf-8")
