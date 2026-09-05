"""Guard tests: parameters invariants + demo spine."""
from __future__ import annotations

import json
from pathlib import Path

from crisis_os.layers import check_equity, greedy_allocate, run_demo
from crisis_os.snapshot import load_parameters, pv

ROOT = Path(__file__).resolve().parents[1]


def test_parameter_invariants():
    p = load_parameters()
    sphere = pv(p, "humanitarian_standards", "water_l_per_person_day")
    fb = pv(p, "zones", "zone_B_population") * sphere
    fc = pv(p, "zones", "zone_C_population") * sphere
    stock = pv(p, "supply", "warehouse_W1_staging_l_per_day")
    assert stock >= fb + fc
    assert pv(p, "governance", "human_modify_zone_B_qty_l") >= fb
    tilt = pv(p, "visualization", "camera_tilt_degrees")
    assert 35 <= tilt <= 50
    assert pv(p, "visualization", "vertical_exaggeration") > 1
    assert pv(p, "visualization", "population_grid_resolution_m") == pv(p, "visualization", "flood_grid_resolution_m")
    assert len(pv(p, "visualization", "emissive_materials_allowed")) == 1
    w, s, e, n = pv(p, "visualization", "hero_region_bounds")
    from crisis_os.catalog import ENTITIES_SPEC
    b7 = next(x for x in ENTITIES_SPEC if x["entity_id"] == "bridge:B7")
    msy = next(x for x in ENTITIES_SPEC if x["entity_id"] == "airport:msy")
    assert w <= b7["lon"] <= e and s <= b7["lat"] <= n
    assert w <= msy["lon"] <= e and s <= msy["lat"] <= n
    src = (ROOT / "data" / "SOURCES.md").read_text(encoding="utf-8")
    keys = set()

    def walk(o):
        if isinstance(o, dict):
            if isinstance(o.get("source_key"), str):
                keys.add(o["source_key"])
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(p)
    missing = [k for k in keys if f"`{k}`" not in src]
    assert not missing, missing


def test_registry_covers_types():
    from crisis_os.catalog import ENTITIES_SPEC
    reg = json.loads((ROOT / "data" / "katrina" / "world" / "symbol-registry.json").read_text(encoding="utf-8"))
    types = {e["type"] for e in ENTITIES_SPEC}
    missing = types - set(reg["types"])
    assert not missing, missing
    from crisis_os.gltf_models import CATEGORIES
    for t in types:
        assert reg["types"][t]["category"] == CATEGORIES[t], t
    mesh_glyphs = [
        v["symbol_far"] for v in reg["types"].values()
        if v.get("primitive") == "mesh" and v.get("symbol_far")
    ]
    assert len(mesh_glyphs) == len(set(mesh_glyphs)), mesh_glyphs


def test_distinctive_type_solids():
    from crisis_os.gltf_models import PARTS, SYMBOLS, solids_catalog
    cat = solids_catalog()
    sigs = {}
    for name, parts in PARTS.items():
        sig = tuple((round(p[3], 1), round(p[4], 1), round(p[5], 1), len(parts)) for p in parts)
        assert name in SYMBOLS
        assert name in cat
        assert cat[name]["symbol"] != "•"
        sigs.setdefault(sig, []).append(name)
    collisions = {k: v for k, v in sigs.items() if len(v) > 1}
    assert not collisions, collisions
    glyphs = [SYMBOLS[n] for n in PARTS]
    assert len(glyphs) == len(set(glyphs)), glyphs
    assert SYMBOLS["hospital"] != SYMBOLS["medicine"]
    assert SYMBOLS["hospital"] != SYMBOLS["clinic"]
    assert SYMBOLS["bridge"] != SYMBOLS["bridge.failed"]
    assert cat["hospital"]["parts"] != cat["warehouse"]["parts"]
    assert cat["bridge"]["parts"] != cat["bridge.failed"]["parts"]
    assert len(cat["vehicle"]["parts"]) >= 3


def test_no_synthetic_katrina_entities():
    from crisis_os.catalog import ENTITIES_SPEC
    synth = [e["entity_id"] for e in ENTITIES_SPEC if e.get("synthetic")]
    assert not synth, synth
    ids = {e["entity_id"] for e in ENTITIES_SPEC}
    assert "fire:synth" not in ids and "landslide:synth" not in ids
    assert "bridge:B7" in ids and "hospital:NDH" in ids and "shelter:morial" in ids


def test_sourced_flood_and_population():
    from crisis_os.snapshot import (
        build_snapshot, hud_weighted_depth_m, interpolate_hydrograph, in_open_water, load_parameters,
    )
    from datetime import datetime

    hoods = json.loads((ROOT / "data" / "katrina" / "sourced" / "neighborhoods_census2000.json").read_text(encoding="utf-8"))
    assert len(hoods["neighborhoods"]) >= 70, len(hoods["neighborhoods"])
    assert sum(n["pop"] for n in hoods["neighborhoods"]) == 484674
    assert hoods["orleans_parish_total"] == 484674
    l9 = next(n for n in hoods["neighborhoods"] if n["id"] == "lower-ninth-ward")
    assert l9["pop"] == 14008
    assert l9["flooded"] is True
    fq = next(n for n in hoods["neighborhoods"] if n["id"] == "french-quarter")
    assert fq["flooded"] is False

    stage_m, dstage = interpolate_hydrograph(datetime.fromisoformat("2005-08-29T06:00:00-05:00"))
    assert abs(stage_m - 11.3 * 0.3048) < 1e-6
    assert abs(dstage - 1.0 * 0.3048) < 1e-6

    p = load_parameters()
    assert pv(p, "supply", "warehouse_W1_staging_l_per_day") == 648000
    assert pv(p, "shelters", "superdome_occupancy_landfall") == 11000

    t0 = build_snapshot(p, "t0")
    b7 = build_snapshot(p, "b7")
    assert t0["hazards"]["flood"]["wet_mask"]["vintage"] == "2005-08-31"
    assert t0["hazards"]["flood"]["d_stage_dt"] == 0.0
    assert abs(t0["hazards"]["flood"]["stage_m"] - hud_weighted_depth_m("lower-9th")) < 0.001
    assert b7["hazards"]["flood"]["wet_mask"]["vintage"].startswith("hud-districts")
    assert abs(b7["hazards"]["flood"]["stage_m"] - 11.3 * 0.3048) < 0.001
    assert t0["hazards"]["flood"]["wet_mask"]["flooded_units"] == 103165
    assert t0["population"]["dataset_id"] == "census-2000-sf1"
    assert t0["hazards"]["fire"]["active"] is True
    assert t0["hazards"]["fire"]["synthetic"] is False
    assert len(t0["hazards"]["fire"]["sites"]) >= 3
    assert t0["hazards"]["contamination"]["active"] is True
    assert any(a["id"] == "murphy-oil" and a["ring"] for a in t0["hazards"]["contamination"]["areas"])
    assert t0["hazards"]["landslide"]["active"] is False
    charity = next(e for e in t0["entities"] if e["entity_id"] == "hospital:charity")
    assert charity["state"] == "inaccessible"
    touro = next(e for e in t0["entities"] if e["entity_id"] == "hospital:touro")
    assert touro["state"] == "damaged"
    b7t0 = next(e for e in t0["entities"] if e["entity_id"] == "bridge:B7")
    assert b7t0["state"] == "uncertain"
    b7b = next(e for e in b7["entities"] if e["entity_id"] == "bridge:B7")
    assert b7b["state"] == "inaccessible"
    names = {e["name"] for e in t0["entities"]}
    assert "I-10 Twin Span Bridge" in names
    assert "Ernest N. Morial Convention Center" in names
    b7e = next(e for e in t0["entities"] if e["entity_id"] == "bridge:B7")
    assert abs(b7e["geometry"]["lon"] + 89.82486) < 1e-4
    assert abs(b7e["geometry"]["lat"] - 30.18264) < 1e-4
    assert b7e["attributes"]["span_paths"]
    assert b7e["attributes"]["span_length_m"] > 7000
    geo = t0["geography"]
    assert len(geo["roads"]) > 100
    assert len(geo["buildings"]) > 100
    assert len(geo["canals"]) > 10
    assert "2011" in geo["vintage"]
    dmg = {b.get("damage") for b in geo["buildings"]}
    assert "destroyed" in dmg and "intact" in dmg
    wrecked = [b for b in geo["buildings"] if b.get("damage") == "destroyed"]
    assert len(wrecked) > 20
    assert all((b.get("height_m") or 9) < 6 for b in wrecked[:40])

    hoods2 = json.loads((ROOT / "data" / "katrina" / "sourced" / "neighborhoods_census2000.json").read_text(encoding="utf-8"))
    wet = [n["id"] for n in hoods2["neighborhoods"] if in_open_water(n["lon"], n["lat"])]
    assert wet == [], wet
    lc = next(n for n in hoods2["neighborhoods"] if n["id"] == "lake-catherine")
    assert lc["lat"] < 30.14 and lc["lon"] > -89.78
    we = next(n for n in hoods2["neighborhoods"] if n["id"] == "west-end")
    assert we["lat"] <= 30.022
    ap = next(n for n in hoods2["neighborhoods"] if n["id"] == "algiers-point")
    assert ap["lat"] < 29.954 and ap["lon"] < -90.050
    for c in t0["population"]["cells"]:
        assert not in_open_water(c["lon"], c["lat"]), c["name"]
    draped = [b for b in geo["buildings"] if b.get("density")]
    assert len(draped) > 50, len(draped)
    for b in geo["buildings"]:
        if "cx" in b:
            assert not in_open_water(b["cx"], b["cy"]), b["id"]
    heat = t0["population"].get("heat") or []
    assert len(heat) > 2000, len(heat)
    wet_heat = [h for h in heat if in_open_water(h["lon"], h["lat"])]
    assert wet_heat == [], wet_heat[:5]
    bldg_heat = sum(1 for b in geo["buildings"] if b.get("heat_weight"))
    assert bldg_heat > 500, bldg_heat
    assert t0["hazards"]["flood"]["paths"] == []
    for poly in t0["hazards"]["flood"]["wet_mask"]["coordinates"]:
        for lon, lat in poly[0]:
            assert not (lon < -90.02 and lat > 30.027), (lon, lat)
            assert not (29.952 < lat < 29.958 and -90.052 < lon < -90.045), (lon, lat)
            assert not (lon < -89.85 and lat > 30.062), (lon, lat)
    b7_rings = b7["hazards"]["flood"]["wet_mask"]["coordinates"]
    assert len(b7_rings) == 2
    feats = {f["id"]: f for f in t0["hazards"]["flood"]["wet_mask"]["features"]}
    assert feats["warehouse-cbd"]["depth_m"] < feats["lower-9th"]["depth_m"]
    assert feats["warehouse-cbd"]["wet_frac"] < 0.15
    assert feats["lower-9th"]["wet_frac"] > 0.7
    assert feats["lakeview"]["depth_m"] > feats["garden"]["depth_m"]
    assert len(t0["hazards"]["flood"]["wet_mask"]["features"]) == len(
        t0["hazards"]["flood"]["wet_mask"]["coordinates"]
    )


def test_bridge_spans_follow_osm():
    from crisis_os.bridges import dist_m, load_bridge_spans, path_length_m
    from crisis_os.catalog import ENTITIES_SPEC

    spans = load_bridge_spans()
    pins = {e["entity_id"]: (e["lon"], e["lat"]) for e in ENTITIES_SPEC if e["type"] == "bridge"}
    assert set(spans) == set(pins)
    for eid, rec in spans.items():
        assert rec["span_paths"], eid
        pin = pins[eid]
        nearest = min(dist_m(list(pin), pt) for path in rec["span_paths"] for pt in path)
        assert nearest < 700, (eid, nearest)
        assert rec["span_length_m"] > 400, (eid, rec["span_length_m"])
        for path in rec["span_paths"]:
            assert path_length_m(path) > 300, (eid, path_length_m(path))
    assert spans["bridge:B7"]["span_length_m"] > 7000
    assert len(spans["bridge:B7"]["span_paths"]) == 2
    assert spans["bridge:us11"]["span_length_m"] > 4000
    assert spans["bridge:danziger"]["span_length_m"] > 800
    ccc = spans["bridge:ccc"]["span_paths"][0]
    assert abs(ccc[0][0] - ccc[-1][0]) > abs(ccc[0][1] - ccc[-1][1])
    # Causeway is clipped to the south landing, not the full lake crossing.
    assert 2500 < spans["bridge:causeway"]["span_length_m"] < 6000
    assert len(spans["bridge:causeway"]["span_paths"]) == 2


def test_equity_and_spine():
    p = load_parameters()
    sphere = pv(p, "humanitarian_standards", "water_l_per_person_day")
    floors = {
        "zone:B": pv(p, "zones", "zone_B_population") * sphere,
        "zone:C": pv(p, "zones", "zone_C_population") * sphere,
    }
    stock = pv(p, "supply", "warehouse_W1_staging_l_per_day")
    ok, _ = check_equity({"zone:B": stock, "zone:C": 0}, floors)
    assert not ok
    fair = greedy_allocate(stock, floors)
    ok, _ = check_equity(fair, floors)
    assert ok
    result = run_demo()
    assert result["truck"][1] == "SUSPENDED"


if __name__ == "__main__":
    test_parameter_invariants()
    test_registry_covers_types()
    test_distinctive_type_solids()
    test_no_synthetic_katrina_entities()
    test_sourced_flood_and_population()
    test_bridge_spans_follow_osm()
    test_equity_and_spine()
    print("ok")
