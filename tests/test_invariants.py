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


def test_replay_clock():
    from crisis_os.replay import (
        PUBLIC_SCRIPT_PATH, SCRIPT_PATH, belief_for_event, event_count, index_at_time,
        load_script, nearest_belief_keyframe, parse_cdt, phase_category_scan, phase_counts,
        replay_at, script_payload, elapsed_binds, fields_on,
    )

    raw = json.loads(SCRIPT_PATH.read_text(encoding="utf-8"))
    public = json.loads(PUBLIC_SCRIPT_PATH.read_text(encoding="utf-8"))
    assert len(raw["events"]) == 84
    assert [e["id"] for e in raw["events"]] == [e["id"] for e in public["events"]]
    assert {p["id"] for p in raw["phases"]} == {0, 1, 2, 3, 4, 5, 6}

    script = load_script()
    assert event_count(script) == 84
    counts = phase_counts(script)
    assert set(counts) == {0, 1, 2, 3, 4, 5, 6}
    assert sum(counts.values()) == 84
    assert all(counts[p] > 0 for p in range(7))

    prev = None
    ids = set()
    for i, ev in enumerate(script["events"]):
        assert ev["id"] and ev["title"] and isinstance(ev.get("binds"), list)
        assert 0 <= ev["phase"] <= 6
        assert ev["seq"] == i
        dt = parse_cdt(ev["t"])
        assert dt.utcoffset() is not None
        if prev is not None:
            assert dt >= prev
        prev = dt
        ids.add(ev["id"])
    assert len(ids) == 84
    assert [e["id"] for e in script["events"]] == [e["id"] for e in raw["events"]]
    murphy_i = next(i for i, e in enumerate(script["events"]) if e["id"] == "p3-murphy-oil")
    fires_i = next(i for i, e in enumerate(script["events"]) if e["id"] == "p4-fires")
    assert murphy_i < fires_i

    assert fields_on(0)["flood"] is False
    ihnc = script["_id_index"]["p2-ihnc-overtop-west"]
    assert fields_on(ihnc)["flood"] is True
    rescues = script["_id_index"]["p3-rescues-thousands"]
    assert fields_on(rescues)["contamination"] is True
    assert fields_on(rescues)["fire"] is False
    assert fields_on(fires_i)["fire"] is True
    assert "hazards.flood" in elapsed_binds(rescues)

    assert nearest_belief_keyframe("2005-08-23T16:00:00-05:00") == "b7"
    assert nearest_belief_keyframe("2005-08-31T08:00:00-05:00") == "t0"
    assert nearest_belief_keyframe("2005-08-31T09:20:00-05:00") == "reroute"
    assert nearest_belief_keyframe("2005-09-18T12:00:00-05:00") == "reroute"

    landfall = next(e for e in script["events"] if e["id"] == "p2-twin-span")
    assert belief_for_event(landfall) == "b7"
    assert index_at_time("2005-08-23T00:00:00-05:00") == 0

    at = replay_at(event_id="p2-twin-span")
    assert at["build_phase"] == "C"
    assert at["belief_keyframe"] == "b7"
    assert "t0 snapshot unchanged" in at["world_note"]
    assert at["event"]["title"]
    assert at["world_delta"]["entities"]["bridge:B7"]["state"] == "uncertain"

    payload = script_payload()
    assert payload["event_count"] == 84
    assert payload["t_start"] == script["events"][0]["t"]
    assert payload["t_end"] == script["events"][-1]["t"]
    assert "script sequence" in payload["clock_rule"] or "sorted by t" in payload["clock_rule"]
    assert payload["events"][0]["id"] == "p0-td12"
    assert payload["events"][0]["seq"] == 0

    scan0 = phase_category_scan(0, script)
    assert scan0["categories"]["transport"]["status"] == "gap"
    assert scan0["categories"]["cyclone"]["status"] == "gap"
    scan2 = phase_category_scan(2, script)
    assert scan2["categories"]["hazard"]["status"] == "bound"
    assert scan2["categories"]["flood"]["status"] == "bound"
    assert scan2["categories"]["population"]["status"] == "gap"


def test_cyclone_pose():
    from crisis_os.cyclone import load_track, pose_at
    from crisis_os.replay import replay_at

    track = load_track()
    assert track[0]["utc"] == "2005-08-23T18:00:00Z"
    assert abs(track[0]["lat"] - 23.1) < 1e-6
    assert abs(track[0]["lon"] + 75.1) < 1e-6
    fl = pose_at("2005-08-25T17:30:00-05:00")
    assert abs(fl["lat"] - 26.0) < 0.05
    assert abs(fl["lon"] + 80.1) < 0.05
    assert fl["camera"] == "gulf"
    peak = pose_at("2005-08-28T13:00:00-05:00")
    assert peak["cat"] == 5
    assert peak["r34_nm"] > 150
    early = pose_at("2005-08-23T16:00:00-05:00")
    assert early["camera"] == "gulf"
    assert early["r34_nm"] == 0
    nola = pose_at("2005-08-31T08:00:00-05:00")
    assert nola["camera"] == "nola"
    westbound = [p["lon"] for p in track if p["utc"] <= "2005-08-28T18:00:00Z"]
    assert westbound[0] > westbound[-1]
    gulf = replay_at(event_id="p0-td12")
    assert gulf["cyclone"]["camera"] == "gulf"
    assert "cyclone pose" in gulf["world_note"]
    early_path = pose_at("2005-08-23T16:00:00-05:00")
    assert len(early_path["ahead"]) <= 8
    assert all(lat < 28 for _lon, lat in early_path["ahead"])
    assert all(lat < 32.5 for _lon, lat in early_path["flown"])
    landfall_path = pose_at("2005-08-29T10:00:00-05:00")
    assert all(lat < 32.5 for _lon, lat in landfall_path["ahead"] + landfall_path["flown"])
    inland = pose_at("2005-08-31T08:00:00-05:00")
    assert all(lat < 32.5 for _lon, lat in inland["ahead"] + inland["flown"])


def test_prelandfall_assets():
    from crisis_os.landfall import prelandfall_delta
    from crisis_os.replay import load_script, replay_at

    script = load_script()
    nagin = replay_at(event_id="p1-nagin-soe")
    assert nagin["event"]["phase"] == 1
    delta = nagin["world_delta"]
    assert delta["prelandfall"] is True
    assert delta["entities"]["bridge:B7"]["state"] == "operational"
    assert delta["entities"]["hospital:charity"]["state"] == "operational"
    assert delta["entities"]["comms:eoc"]["state"] == "operational"
    assert "NOLA assets on" in nagin["world_note"]
    opens = prelandfall_delta(script["_id_index"]["p1-dome-opens"], script)
    assert opens["entities"]["shelter:dome"]["state"] == "operational"
    assert opens["entities"]["shelter:dome"]["attributes"]["occupancy"] == 0
    dome = prelandfall_delta(script["_id_index"]["p1-dome-evening"], script)
    assert dome["entities"]["shelter:dome"]["state"] == "critical"
    assert dome["entities"]["shelter:dome"]["attributes"]["occupancy"] > 0
    gulf = replay_at(event_id="p0-td12")
    assert gulf.get("world_delta") is None
    t0 = json.loads((ROOT / "data" / "katrina" / "snapshots" / "t0.json").read_text(encoding="utf-8"))
    b7 = next(e for e in t0["entities"] if e["entity_id"] == "bridge:B7")
    assert b7["state"] == "uncertain"
    assert b7["verification_status"] == "unverified"


def test_landfall_hour():
    from crisis_os.landfall import FLIPS, landfall_delta
    from crisis_os.replay import load_script, replay_at, script_payload
    from crisis_os.app import snapshot_for

    t0_path = ROOT / "data" / "katrina" / "snapshots" / "t0.json"
    t0 = json.loads(t0_path.read_text(encoding="utf-8"))
    b7t0 = next(e for e in t0["entities"] if e["entity_id"] == "bridge:B7")
    assert b7t0["state"] == "uncertain"
    assert b7t0["verification_status"] == "unverified"
    assert b7t0.get("ground_truth_state") in (None, "uncertain")

    live = snapshot_for("t0")
    live_b7 = next(e for e in live["entities"] if e["entity_id"] == "bridge:B7")
    assert live_b7["state"] == "uncertain"
    assert live_b7["verification_status"] == "unverified"

    src = (ROOT / "data" / "SOURCES.md").read_text(encoding="utf-8")
    script = load_script()
    ids = {e["id"] for e in script["events"]}
    for event_id, _eid, _state, source_key in FLIPS:
        assert event_id in ids, event_id
        assert f"`{source_key}`" in src, source_key

    west = landfall_delta(script["_id_index"]["p2-ihnc-overtop-west"], script)
    assert west["entities"]["breach:ihnc-west"]["state"] == "critical"
    assert west["entities"]["breach:ihnc"]["state"] == "operational"
    assert west["entities"]["bridge:B7"]["state"] == "uncertain"
    assert west["entities"]["bridge:B7"]["ground_truth_state"] == "operational"
    assert west["entities"]["bridge:B7"]["verification_status"] == "unverified"

    twin = landfall_delta(script["_id_index"]["p2-twin-span"], script)
    assert twin["entities"]["bridge:B7"]["state"] == "uncertain"
    assert twin["entities"]["bridge:B7"]["ground_truth_state"] == "inaccessible"
    assert twin["entities"]["bridge:B7"]["verification_status"] == "unverified"
    assert twin["entities"]["route:R14"]["state"] == "inaccessible"

    dome = landfall_delta(script["_id_index"]["p2-dome-power"], script)
    assert dome["entities"]["shelter:dome"]["gap_fill"] is True
    assert dome["entities"]["shelter:dome"]["verification_status"] == "unverified"

    opened = landfall_delta(script["_id_index"]["p2-17th-open"], script)
    for bid in ("breach:ihnc-west", "breach:ihnc", "breach:london", "breach:london-n", "breach:17th"):
        assert opened["entities"][bid]["state"] in ("damaged", "critical", "inaccessible"), bid
    west_wet = sum(f["wet_frac"] for f in west["flood"]["wet_mask"]["features"])
    open_wet = sum(f["wet_frac"] for f in opened["flood"]["wet_mask"]["features"])
    assert open_wet > west_wet
    open_depth = sum(f["depth_m"] for f in opened["flood"]["wet_mask"]["features"])
    later = landfall_delta(script["_id_index"]["p2-catastrophic-flood"], script)
    later_depth = sum(f["depth_m"] for f in later["flood"]["wet_mask"]["features"])
    assert later_depth >= open_depth

    at = replay_at(event_id="p2-twin-span")
    assert at["build_phase"] == "C"
    assert at["world_delta"]["entities"]["bridge:B7"]["state"] == "uncertain"
    assert at["belief_keyframe"] == "b7"

    gulf = replay_at(event_id="p0-td12")
    assert gulf.get("world_delta") is None
    later_clock = replay_at(event_id="p3-murphy-oil")
    assert later_clock["build_phase"] == "D"
    assert later_clock.get("world_delta")
    assert later_clock["world_delta"]["build_phase"] == "D"

    payload = script_payload()
    assert payload["build_phase"] == "E"
    assert payload["events"][script["_id_index"]["p2-17th-open"]].get("world_delta")

    frozen = json.loads(t0_path.read_text(encoding="utf-8"))
    frozen_b7 = next(e for e in frozen["entities"] if e["entity_id"] == "bridge:B7")
    assert frozen_b7["state"] == "uncertain"
    assert frozen_b7["verification_status"] == "unverified"


def test_population_clock():
    from crisis_os.population_clock import population_delta
    from crisis_os.replay import load_script, replay_at, script_payload
    from crisis_os.snapshot import pv, load_parameters

    script = load_script()
    p = load_parameters()
    census = pv(p, "population_clock", "orleans_census_2000")
    remain = pv(p, "population_clock", "city_remaining_28aug")
    cleared = pv(p, "population_clock", "city_cleared_early_sep")

    p0 = replay_at(event_id="p0-td12")
    assert p0["population_delta"]["city_in"] == census
    assert p0["population_delta"]["wet_frac"] == 1
    assert p0["event"]["population_delta"]["hotspots"] == []
    assert p0["population_delta"]["movement"] == []

    nagin = replay_at(event_id="p1-nagin-soe")
    assert nagin["population_delta"]["city_in"] < census
    assert nagin["population_delta"]["city_in"] > remain
    assert nagin["population_delta"]["continuous"] is True
    nagin_kinds = {m["kind"] for m in nagin["population_delta"]["movement"]}
    assert "outbound" in nagin_kinds
    assert nagin["population_delta"]["movement"]

    prep = replay_at(event_id="p1-eoc-contraflow-prep")
    man = replay_at(event_id="p1-mandatory-nola")
    assert nagin["population_delta"]["wet_frac"] > prep["population_delta"]["wet_frac"] > man["population_delta"]["wet_frac"]

    rta = replay_at(event_id="p1-rta-buses")
    assert any(m["kind"] == "to_shelter" for m in rta["population_delta"]["movement"])
    assert any(m["to_id"] == "shelter:dome" for m in rta["population_delta"]["movement"])

    roof = replay_at(event_id="p2-rooftop-start")
    assert any(m["kind"] == "rescue" for m in roof["population_delta"]["movement"])
    assert any(m["to_id"] == "shelter:dome" for m in roof["population_delta"]["movement"])

    xfer = replay_at(event_id="p3-dome-to-cc")
    assert any(m["kind"] == "dome_to_cc" for m in xfer["population_delta"]["movement"])

    hou = replay_at(event_id="p4-evac-houston")
    assert all(m["to_id"] == "airport:msy" for m in hou["population_delta"]["movement"])
    assert any(m["from_id"] == "shelter:dome" for m in hou["population_delta"]["movement"])
    blob = json.dumps(hou["population_delta"]["movement"]).lower()
    assert "houston" not in blob

    stay = replay_at(event_id="p1-remain")
    assert stay["population_delta"]["city_in"] == remain
    dome = next(h for h in stay["population_delta"]["hotspots"] if h["entity_id"] == "shelter:dome")
    assert dome["people"] == 11000

    cc = replay_at(event_id="p3-cc-crisis")
    assert cc["population_delta"]["classes"]["shelter:morial"] == 19000
    assert cc["population_delta"]["classes"]["shelter:dome"] == 16000
    assert cc["population_delta"]["wet_frac"] < stay["population_delta"]["wet_frac"]

    empty = replay_at(event_id="p5-dome-cc-cleared")
    assert empty["population_delta"]["city_in"] == cleared
    assert empty["population_delta"]["classes"]["shelter:dome"] == 0
    assert empty["population_delta"]["classes"]["shelter:morial"] == 0
    assert any(m["kind"] == "off_map" for m in empty["population_delta"]["movement"])

    rebound = replay_at(event_id="p6-rebuild")
    assert rebound["population_delta"]["city_in"] > empty["population_delta"]["city_in"]
    assert rebound["population_delta"]["movement"] == []
    july = pv(p, "population_clock", "orleans_july_2006")
    assert abs(rebound["population_delta"]["city_in"] - july) < 5

    payload = script_payload()
    assert all("population_delta" in e for e in payload["events"])
    city = [e["population_delta"]["city_in"] for e in payload["events"]]
    assert city[0] == census
    assert min(city) < remain
    t0 = json.loads((ROOT / "data" / "katrina" / "snapshots" / "t0.json").read_text(encoding="utf-8"))
    assert t0["population"]["classes"]["total"]["orleans_parish_2000"] == census


def test_inundation_shelters():
    from crisis_os.inundation import FLIPS, hud_ceiling_features, inundation_delta
    from crisis_os.landfall import landfall_delta
    from crisis_os.replay import load_script, replay_at, script_payload
    from crisis_os.snapshot import district_flood_metrics, load_hud_flood

    t0_path = ROOT / "data" / "katrina" / "snapshots" / "t0.json"
    frozen = json.loads(t0_path.read_text(encoding="utf-8"))
    frozen_b7 = next(e for e in frozen["entities"] if e["entity_id"] == "bridge:B7")
    assert frozen_b7["state"] == "uncertain"
    assert frozen_b7["verification_status"] == "unverified"

    src = (ROOT / "data" / "SOURCES.md").read_text(encoding="utf-8")
    script = load_script()
    ids = {e["id"] for e in script["events"]}
    for event_id, _eid, _state, source_key in FLIPS:
        assert event_id in ids, event_id
        assert f"`{source_key}`" in src, source_key

    last_p2 = max(i for i, e in enumerate(script["events"]) if e["phase"] == 2)
    c_end = landfall_delta(last_p2, script)
    c_wet = sum(f["wet_frac"] for f in c_end["flood"]["wet_mask"]["features"])
    c_depth = sum(f["depth_m"] for f in c_end["flood"]["wet_mask"]["features"])

    eighty = inundation_delta(script["_id_index"]["p3-80pct"], script)
    assert eighty["build_phase"] == "D"
    assert eighty["entities"]["bridge:B7"]["state"] == "uncertain"
    assert eighty["entities"]["bridge:B7"]["ground_truth_state"] == "inaccessible"
    assert eighty["entities"]["bridge:B7"]["verification_status"] == "unverified"
    assert eighty["pulse"]["truck_status"] == "N/A"
    eighty_wet = sum(f["wet_frac"] for f in eighty["flood"]["wet_mask"]["features"])
    assert eighty_wet > c_wet
    assert "MOTF" in eighty["flood"]["wet_mask"]["note"]
    assert "hud-noaa-flood-2005-08-31" in eighty["flood"]["wet_mask"]["source_key"]

    at80 = replay_at(event_id="p3-80pct")
    assert at80["build_phase"] == "D"
    assert at80["world_delta"]["entities"]["bridge:B7"]["state"] == "uncertain"
    assert at80["fields_on"]["fire"] is False

    ceiling = {f["id"]: f for f in hud_ceiling_features()}
    peak = inundation_delta(script["_id_index"]["p3-max-inundation"], script)
    peak_depth = sum(f["depth_m"] for f in peak["flood"]["wet_mask"]["features"])
    assert peak_depth >= sum(f["depth_m"] for f in eighty["flood"]["wet_mask"]["features"])
    assert peak_depth >= c_depth
    for f in peak["flood"]["wet_mask"]["features"]:
        want = ceiling[f["id"]]
        assert abs(f["wet_frac"] - want["wet_frac"]) < 1e-6, f["id"]
        assert abs(f["depth_m"] - want["depth_m"]) < 1e-6, f["id"]
    hud = load_hud_flood()
    for d in hud["districts"]:
        if d["flooded_units"] <= 0:
            continue
        depth_m, wet_frac = district_flood_metrics(d)
        got = next(x for x in peak["flood"]["wet_mask"]["features"] if x["id"] == d["id"])
        assert abs(got["wet_frac"] - round(wet_frac, 4)) < 1e-6
        assert abs(got["depth_m"] - round(depth_m, 3)) < 1e-6

    cc = replay_at(event_id="p3-cc-crisis")
    assert cc["build_phase"] == "D"
    assert cc["population_delta"]["classes"]["shelter:morial"] == 19000
    assert cc["population_delta"]["classes"]["shelter:dome"] == 16000
    assert cc["world_delta"]["entities"]["shelter:morial"]["attributes"]["occupancy"] == 19000
    assert cc["world_delta"]["entities"]["shelter:dome"]["attributes"]["occupancy"] == 16000
    assert cc["world_delta"]["entities"]["shelter:morial"]["state"] == "critical"
    assert cc["fields_on"]["fire"] is False

    murphy = replay_at(event_id="p3-murphy-oil")
    assert murphy["fields_on"]["contamination"] is True
    assert murphy["fields_on"]["fire"] is False
    assert murphy["world_delta"]["entities"]["fuel:depot"]["state"] == "critical"
    assert murphy["world_delta"]["pulse"]["truck_status"] == "N/A"

    fires = replay_at(event_id="p4-fires")
    assert fires["fields_on"]["fire"] is True
    assert fires["build_phase"] == "E"
    assert fires.get("world_delta")

    td = replay_at(event_id="p3-td")
    assert td["build_phase"] == "D"
    assert "bridge:B7" not in td["world_delta"]["entities"]
    assert td["world_delta"]["pulse"].get("truck_status") != "N/A"
    assert td["belief_keyframe"] == "reroute"

    payload = script_payload()
    assert payload["build_phase"] == "E"
    assert payload["events"][script["_id_index"]["p3-max-inundation"]].get("world_delta")
    frozen2 = json.loads(t0_path.read_text(encoding="utf-8"))
    frozen2_b7 = next(e for e in frozen2["entities"] if e["entity_id"] == "bridge:B7")
    assert frozen2_b7["state"] == "uncertain"
    assert frozen2_b7["verification_status"] == "unverified"


def test_unwatering():
    from crisis_os.inundation import hud_ceiling_features, inundation_delta
    from crisis_os.replay import load_script, replay_at, script_payload
    from crisis_os.snapshot import pv, load_parameters
    from crisis_os.unwatering import FLIPS, unwatering_delta

    t0_path = ROOT / "data" / "katrina" / "snapshots" / "t0.json"
    frozen = json.loads(t0_path.read_text(encoding="utf-8"))
    frozen_b7 = next(e for e in frozen["entities"] if e["entity_id"] == "bridge:B7")
    assert frozen_b7["state"] == "uncertain"
    assert frozen_b7["verification_status"] == "unverified"

    src = (ROOT / "data" / "SOURCES.md").read_text(encoding="utf-8")
    script = load_script()
    ids = {e["id"] for e in script["events"]}
    for event_id, _eid, _state, source_key in FLIPS:
        assert event_id in ids, event_id
        assert f"`{source_key}`" in src, source_key

    last_p3 = max(i for i, e in enumerate(script["events"]) if e["phase"] == 3)
    d_end = inundation_delta(last_p3, script)
    d_wet = sum(f["wet_frac"] for f in d_end["flood"]["wet_mask"]["features"])

    fires = replay_at(event_id="p4-fires")
    assert fires["build_phase"] == "E"
    assert fires["fields_on"]["fire"] is True
    assert fires["fields_on"]["contamination"] is True
    fire_wet = sum(f["wet_frac"] for f in fires["world_delta"]["flood"]["wet_mask"]["features"])
    assert abs(fire_wet - d_wet) < 0.05
    assert "astrodome" not in json.dumps(fires["world_delta"]).lower()
    assert "houston" not in (fires["world_delta"].get("entities") or {})

    pumps = replay_at(event_id="p5-portable-pumps")
    pump_wet = sum(f["wet_frac"] for f in pumps["world_delta"]["flood"]["wet_mask"]["features"])
    assert pump_wet < fire_wet
    assert pumps["world_delta"]["entities"]["infra:pump6"]["state"] == "damaged"
    assert pumps["world_delta"]["pulse"]["remain"] == 0.75

    n23 = replay_at(event_id="p5-pumps-23")
    p = load_parameters()
    assert n23["world_delta"]["entities"]["infra:pump6"]["attributes"]["pumps_on"] == pv(p, "unwatering", "pumps_permanent_on_7sep")
    assert n23["world_delta"]["pulse"]["pumps_on"] == 23

    n26 = replay_at(event_id="p5-pumps-26")
    assert n26["world_delta"]["pulse"]["pumps_on"] == pv(p, "unwatering", "pumps_permanent_on_10sep")
    assert n26["world_delta"]["entities"]["infra:pump6"]["state"] == "operational"
    assert n26["world_delta"]["pulse"]["cfs"] == (
        pv(p, "unwatering", "pumps_permanent_cfs_10sep") + pv(p, "unwatering", "pumps_portable_cfs_10sep")
    )

    entergy = replay_at(event_id="p5-entergy-9of17")
    assert entergy["world_delta"]["entities"]["power:waterford"]["state"] != "operational"
    assert entergy["world_delta"]["entities"]["power:michoud"]["state"] == "inaccessible"
    assert entergy["world_delta"]["entities"]["infra:power"]["state"] == "damaged"

    forty = replay_at(event_id="p6-40pct")
    ceiling = hud_ceiling_features()
    by_id = {f["id"]: f for f in forty["world_delta"]["flood"]["wet_mask"]["features"]}
    for f in ceiling:
        got = by_id[f["id"]]
        assert abs(got["wet_frac"] - round(f["wet_frac"] * 0.50, 4)) < 1e-6, f["id"]
    forty_wet = sum(x["wet_frac"] for x in by_id.values())
    assert forty_wet < pump_wet

    dryish = replay_at(event_id="p6-80pct-unwatered")
    dry_wet = sum(f["wet_frac"] for f in dryish["world_delta"]["flood"]["wet_mask"]["features"])
    assert dry_wet < forty_wet
    assert dryish["world_delta"]["pulse"]["remain"] == 0.25

    octo = replay_at(event_id="p6-october-dry")
    assert octo["world_delta"]["pulse"]["remain"] < 0.12
    assert octo["world_delta"]["roads_wet"] is False

    cleared = replay_at(event_id="p5-dome-cc-cleared")
    assert cleared["population_delta"]["classes"]["shelter:dome"] == 0
    assert cleared["population_delta"]["classes"]["shelter:morial"] == 0
    assert cleared["world_delta"]["entities"]["shelter:dome"]["attributes"]["occupancy"] == 0
    assert cleared["world_delta"]["entities"]["shelter:morial"]["attributes"]["occupancy"] == 0

    msy = replay_at(event_id="p6-msy-commercial")
    assert msy["world_delta"]["entities"]["airport:msy"]["state"] == "operational"
    mil = replay_at(event_id="p4-msy-military")
    assert mil["world_delta"]["entities"]["airport:msy"]["state"] == "damaged"

    houston = replay_at(event_id="p4-evac-houston")
    assert "Houston" in houston["world_delta"]["pulse"]["off_map"]
    assert all("houston" not in eid and "astrodome" not in eid for eid in houston["world_delta"]["entities"])

    b7 = replay_at(event_id="p6-rebuild")
    assert b7["world_delta"]["entities"]["bridge:B7"]["state"] == "inaccessible"
    assert b7["world_delta"]["entities"]["bridge:B7"]["verification_status"] == "verified"

    payload = script_payload()
    assert payload["build_phase"] == "E"
    assert payload["events"][script["_id_index"]["p6-october-dry"]].get("world_delta")
    frozen2 = json.loads(t0_path.read_text(encoding="utf-8"))
    frozen2_b7 = next(e for e in frozen2["entities"] if e["entity_id"] == "bridge:B7")
    assert frozen2_b7["state"] == "uncertain"
    assert frozen2_b7["verification_status"] == "unverified"
    assert unwatering_delta(script["_id_index"]["p3-cc-crisis"], script) is None


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
    test_replay_clock()
    test_cyclone_pose()
    test_prelandfall_assets()
    test_landfall_hour()
    test_population_clock()
    test_inundation_shelters()
    test_unwatering()
    test_equity_and_spine()
    print("ok")
