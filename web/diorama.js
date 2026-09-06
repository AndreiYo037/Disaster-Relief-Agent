/* Crisis OS diorama — pure read of WorldSnapshot JSON. CDN deck.gl + MapLibre. */
(() => {
  const KEYS = ["t0", "b7", "reroute"];
  const BELIEF = ["b7", "t0", "reroute"];
  const PHASE_SHORT = ["0 Formation", "1 Gulf", "2 Landfall", "3 Inundation", "4 Federal", "5 Unwater", "6 Recovery"];
  const SCAN_CATS = ["transport", "health", "humanitarian", "utilities", "supply", "hazard"];
  const SCAN_FIELDS = ["cyclone", "flood", "fire", "contamination", "population"];
  const REPLAY_STEP_MS = 1200;
  const STATE_COLOR = {
    operational: [46, 204, 96], full: [46, 204, 96],
    uncertain: [255, 210, 50],
    damaged: [255, 152, 28],
    critical: [255, 84, 48],
    inaccessible: [220, 36, 48], destroyed: [220, 36, 48], depleted: [220, 36, 48],
  };
  const SEG_COLOR = {
    open: [55, 214, 122, 150],
    degraded: [255, 196, 0, 255],
    blocked: [255, 40, 56, 255],
    submerged: [56, 176, 255, 255],
  };
  const EVENT_GLYPH = {
    infrastructure_damage: "✕", road_closure: "╪", displacement: "→",
    service_interruption: "⚡", supply_shortage: "▽", facility_closure: "▣",
    security_event: "·", hazard_expansion: "◎",
  };
  const CAT_ORDER = ["transport", "health", "humanitarian", "utilities", "supply", "hazard", "geography"];
  const STOCK_TYPES = new Set(["warehouse", "food", "medicine", "fuel", "water"]);
  const OCCUPANCY_TYPES = new Set(["shelter", "camp"]);
  const OP_REALLOC = new Set(["warehouse", "vehicle", "food", "fuel", "medicine", "water", "personnel"]);
  const OP_EVACUATE = new Set(["shelter", "camp", "zone", "hospital", "clinic", "school"]);
  const BIND_COUPLE = {
    "route:R14": ["bridge:B7"], "bridge:B7": ["route:R14"],
    "route:R22": ["bridge:us11"], "bridge:us11": ["route:R22"],
    "zone:C": ["shelter:morial"], "shelter:morial": ["zone:C"],
    "zone:B": ["breach:ihnc", "breach:ihnc-west"],
    "hazards.contamination": ["fuel:depot"], "fuel:depot": ["hazards.contamination"],
  };
  const OP_LABEL = {
    realloc: "resource reallocation",
    evacuate: "evacuation",
    access: "access — constraint for both operations",
  };
  const MOBILE_TYPES = new Set(["vehicle", "personnel"]);

  const {
    MapboxOverlay, PathLayer, PolygonLayer, ScatterplotLayer, SolidPolygonLayer,
    TextLayer, ArcLayer,
  } = deck;
  const OverlayCtor = MapboxOverlay || deck.MapboxOverlay;

  let snaps = {};
  let registry = { types: {} };
  let solids = {};
  let kf = "t0";
  let snap = null;
  let selected = null;
  let flowT = 0;
  let fireT = 0;
  let flags = {
    opRealloc: true, opEvacuate: true,
    popTotal: true,
    cycloneAoe: true,
    fallback2d: false,
  };
  let map, overlay;
  let script = null;
  let replayIdx = 0;
  let replayPlaying = false;
  let replayTimer = null;
  let hurdat = null;
  let cameraMode = "nola";
  let beliefPinned = false;
  let playTickAt = 0;
  let heatMix = 0;
  let heatJoin = { idx: -1, inund: [] };

  function webglOk() {
    try {
      const c = document.createElement("canvas");
      return !!(c.getContext("webgl2") || c.getContext("webgl"));
    } catch { return false; }
  }

  async function loadJSON(url) {
    const r = await fetch(url);
    if (!r.ok) throw new Error(url);
    return r.json();
  }

  async function loadSnapshot(id) {
    try {
      const live = await fetch(`/api/state?keyframe=${id}`);
      if (live.ok) return live.json();
    } catch { /* frozen */ }
    return loadJSON(`/data/snapshots/${id}.json`);
  }

  function rgb(state) { return STATE_COLOR[state] || [130, 149, 184]; }
  function statePlate(state) {
    const c = rgb(state);
    return [
      Math.round(c[0] * 0.42 + 6),
      Math.round(c[1] * 0.34 + 6),
      Math.round(c[2] * 0.34 + 6),
      240,
    ];
  }
  function stateBorder(state) {
    const c = rgb(state);
    return [c[0], c[1], c[2], 230];
  }
  function densColor(d, edges, a) {
    const t = d <= edges[0] ? 0 : d <= edges[1] ? 0.33 : d <= edges[2] ? 0.66 : 1;
    return [Math.round(40 + t * 180), Math.round(80 + t * 40), Math.round(140 - t * 40), a];
  }
  function beliefAlpha(e) {
    return e.verification_status === "unverified"
      ? (snap.viz.translucency_unverified || 0.35)
      : (snap.viz.translucency_verified || 1);
  }
  function fmt(n) { return Number(n).toLocaleString(); }
  function dash(v) {
    if (v === undefined || v === null || v === "") return "—";
    if (typeof v === "number") return v < 10 ? v.toFixed(2) : fmt(v);
    return String(v);
  }
  function textPlate(bg, pad) {
    return {
      background: true,
      getBackgroundColor: bg,
      backgroundPadding: pad || [8, 4, 8, 4],
      getBorderColor: [200, 214, 240, 40],
      getBorderWidth: 1,
      parameters: { depthTest: false },
    };
  }

  const EVAC_ARC_HEIGHT = 0.65;
  const TILE_SIZE = 512;
  const EARTH_CIRCUMFERENCE = 40.03e6;
  const LABEL_FONT = "Segoe UI Symbol, Apple Symbols, Noto Sans Symbols 2, Inter, system-ui, sans-serif";

  function mToLonLat(lon, lat, x, z) {
    const mLat = 1 / 110570;
    const mLon = 1 / (111320 * Math.max(0.2, Math.cos(lat * Math.PI / 180)));
    return [lon + x * mLon, lat + z * mLat];
  }
  function lngLatToWorld(lng, lat) {
    const sin = Math.sin((lat * Math.PI) / 180);
    const y = 0.5 - 0.25 * Math.log((1 + sin) / (1 - sin)) / Math.PI;
    return [(lng + 180) / 360 * TILE_SIZE, y * TILE_SIZE];
  }
  function arcSample(from, to, t, height) {
    const h = height == null ? EVAC_ARC_HEIGHT : height;
    const lon = from[0] + (to[0] - from[0]) * t;
    const lat = from[1] + (to[1] - from[1]) * t;
    const a = lngLatToWorld(from[0], from[1]);
    const b = lngLatToWorld(to[0], to[1]);
    const dist = Math.hypot(b[0] - a[0], b[1] - a[1]);
    const zCommon = Math.sqrt(Math.max(0, t * (1 - t))) * dist * h;
    const viewLat = (map && map.getCenter) ? map.getCenter().lat : lat;
    const upm = TILE_SIZE / (EARTH_CIRCUMFERENCE * Math.max(0.2, Math.cos(viewLat * Math.PI / 180)));
    return [lon, lat, zCommon / upm];
  }
  function evacArcArrows(moves, t) {
    const arrows = [];
    const halfW = 120;
    for (const m of moves) {
      const n = 8;
      for (let i = 0; i < n; i++) {
        const u = Math.min(0.97, Math.max(0.03, (i / n + t) % 1));
        const tip = arcSample(m.from, m.to, u);
        const back = arcSample(m.from, m.to, u - 0.03);
        const lat = tip[1];
        const dE = (tip[0] - back[0]) * 111320 * Math.cos(lat * Math.PI / 180);
        const dN = (tip[1] - back[1]) * 110570;
        const horiz = Math.hypot(dE, dN) || 1;
        const pe = -dN / horiz, pn = dE / horiz;
        const leftLl = mToLonLat(back[0], back[1], pe * halfW, pn * halfW);
        const rightLl = mToLonLat(back[0], back[1], -pe * halfW, -pn * halfW);
        const z = back[2] || 0;
        arrows.push({
          path: [
            [leftLl[0], leftLl[1], z],
            tip,
            [rightLl[0], rightLl[1], z],
          ],
        });
      }
    }
    return arrows;
  }
  function pointInRing(lon, lat, ring) {
    if (!ring || ring.length < 3) return false;
    let inside = false;
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      const xi = ring[i][0], yi = ring[i][1], xj = ring[j][0], yj = ring[j][1];
      const denom = (yj - yi) || 1e-12;
      if ((yi > lat) !== (yj > lat) && lon < ((xj - xi) * (lat - yi)) / denom + xi) inside = !inside;
    }
    return inside;
  }
  function mixPopulationDelta(a, b, u) {
    if (!a) return b;
    if (!b || u <= 0) return a;
    if (u >= 1) return b;
    const lerp = (x, y) => (x || 0) + ((y || 0) - (x || 0)) * u;
    const ids = new Set([
      ...(a.hotspots || []).map((h) => h.entity_id),
      ...(b.hotspots || []).map((h) => h.entity_id),
    ]);
    const byId = (rows, id) => (rows || []).find((h) => h.entity_id === id);
    const hotspots = [];
    ids.forEach((id) => {
      const p = byId(a.hotspots, id);
      const q = byId(b.hotspots, id);
      const src = q || p;
      if (!src) return;
      const people = Math.round(lerp(p ? p.people : 0, q ? q.people : 0));
      const weight = lerp(p ? p.weight : 0, q ? q.weight : 0);
      if (weight <= 0.04 && people <= 0) return;
      hotspots.push({ ...src, people, weight });
    });
    const ca = a.classes || {};
    const cb = b.classes || {};
    const classes = { ...ca };
    Object.keys({ ...ca, ...cb }).forEach((k) => {
      const x = ca[k], y = cb[k];
      classes[k] = (typeof x === "number" || typeof y === "number")
        ? Math.round(lerp(x || 0, y || 0))
        : (y ?? x);
    });
    return {
      ...a,
      wet_frac: lerp(a.wet_frac, b.wet_frac),
      dry_frac: lerp(a.dry_frac, b.dry_frac),
      residential_in: Math.round(lerp(a.residential_in, b.residential_in)),
      city_in: Math.round(lerp(a.city_in, b.city_in)),
      city_frac: lerp(a.city_frac, b.city_frac),
      hotspots,
      classes,
      gap_fill: true,
    };
  }
  function rotateXZ(x, z, headingDeg) {
    const theta = (90 - headingDeg) * Math.PI / 180;
    const c = Math.cos(theta), s = Math.sin(theta);
    return [x * c - z * s, x * s + z * c];
  }
  function solidKey(ent) {
    const t = registry.types[ent.type];
    const st = meshState(ent);
    if (!t || t.primitive !== "mesh") return null;
    if (ent.type === "bridge" && (st === "inaccessible" || st === "destroyed")) return "bridge.failed";
    if (ent.type === "breach" && (st === "critical" || st === "inaccessible")) return "breach.open";
    return solids[ent.type] ? ent.type : null;
  }
  function typeSymbol(ent) {
    const rec = registry.types[ent.type] || {};
    const st = meshState(ent);
    if (ent.type === "bridge" && (st === "inaccessible" || st === "destroyed") && rec.symbol_failed) return rec.symbol_failed;
    if (ent.type === "breach" && (st === "critical" || st === "inaccessible") && rec.symbol_open) {
      return rec.symbol_open;
    }
    const key = solidKey(ent);
    const g = (key && solids[key]?.symbol) || rec.symbol_far;
    if (!g || g === "line" || g === "outline") return "·";
    return g;
  }
  function catOf(ent) {
    return (registry.types[ent.type] || {}).category || "other";
  }
  function opOf(ent) {
    if (OP_REALLOC.has(ent.type)) return "realloc";
    if (OP_EVACUATE.has(ent.type)) return "evacuate";
    return "access";
  }
  function opOn(ent) {
    const op = opOf(ent);
    if (op === "realloc") return flags.opRealloc;
    if (op === "evacuate") return flags.opEvacuate;
    return flags.opRealloc || flags.opEvacuate;
  }
  function eventOn(ev) {
    if (!ev.subject_entity) return true;
    const world = applyLandfall(snap);
    const ent = world.entities.find((e) => e.entity_id === ev.subject_entity);
    return ent ? opOn(ent) : true;
  }
  function replayEvents() {
    return (script && script.events) || [];
  }
  function replayEvent() {
    return replayEvents()[replayIdx] || null;
  }
  function orderClockEvents(events) {
    return (events || []).slice().sort((a, b) => String(a.t).localeCompare(String(b.t)));
  }
  function elapsedBindSet() {
    const found = new Set();
    replayEvents().slice(0, replayIdx + 1).forEach((ev) => {
      (ev.binds || []).forEach((b) => found.add(b));
    });
    return found;
  }
  function fieldOn(name) {
    const elapsed = elapsedBindSet();
    if (name === "cyclone") return true;
    if (name === "flood") return elapsed.has("hazards.flood");
    if (name === "fire") return elapsed.has("hazards.fire");
    if (name === "contamination") return elapsed.has("hazards.contamination");
    return false;
  }
  function tickBindIds() {
    const ids = new Set();
    const ev = replayEvent();
    const binds = (ev && ev.binds) || [];
    const add = (b) => {
      (BIND_COUPLE[b] || []).forEach((c) => {
        if (!c || String(c).startsWith("hazards.")) return;
        if (ev && ev.phase < 2 && String(c).startsWith("breach:")) return;
        ids.add(c);
      });
      if (!b || b.startsWith("hazards.")) return;
      ids.add(b);
    };
    binds.forEach(add);
    return ids;
  }
  function nearestBelief(iso) {
    const times = (script && script.demo_keyframes) || {};
    const t = Date.parse(iso);
    let best = "b7";
    let bestD = Infinity;
    for (const name of BELIEF) {
      const kfT = Date.parse(times[name]);
      if (!Number.isFinite(kfT)) continue;
      const d = Math.abs(t - kfT);
      if (d < bestD) {
        best = name;
        bestD = d;
      } else if (d === bestD && kfT < Date.parse(times[best])) {
        best = name;
      }
    }
    return best;
  }
  function beliefForEvent(ev) {
    return ev ? nearestBelief(ev.t) : kf;
  }
  function indexAtTime(iso) {
    const t = Date.parse(iso);
    let idx = 0;
    replayEvents().forEach((ev, i) => {
      if (Date.parse(ev.t) <= t) idx = i;
    });
    return idx;
  }
  function indexForPhase(phase) {
    const i = replayEvents().findIndex((ev) => ev.phase === phase);
    return i < 0 ? 0 : i;
  }
  function classifyBind(bind) {
    if (bind.startsWith("hazards.")) return { kind: "field", name: bind.slice("hazards.".length) };
    const ent = snap && snap.entities.find((e) => e.entity_id === bind);
    if (ent) return { kind: "category", name: catOf(ent) };
    return { kind: "unknown", name: bind };
  }
  function scanBinds(binds) {
    const found = {};
    for (const k of SCAN_CATS.concat(SCAN_FIELDS)) found[k] = [];
    for (const bind of binds || []) {
      const { kind, name } = classifyBind(bind);
      if (found[name]) found[name].push(bind);
    }
    return found;
  }
  function phaseBinds(phase) {
    const out = [];
    for (const ev of replayEvents()) {
      if (ev.phase === phase) out.push(...(ev.binds || []));
    }
    return out;
  }
  function scanHtml(scan) {
    const bit = (k) => {
      const n = (scan[k] || []).length;
      return `<span class="${n ? "bound" : "gap"}">${k}${n ? ` ${n}` : " gap"}</span>`;
    };
    return `<div class="scan-row">${SCAN_CATS.concat(SCAN_FIELDS).map(bit).join("")}</div>`;
  }
  function worldNote() {
    const pin = beliefPinned ? " · pinned" : "";
    const n = replayEvents().length;
    const seq = n ? `${replayIdx + 1}/${n}` : "—";
    const land = landfallDelta();
    if (cycloneWindow()) {
      return `replay clock seq ${seq} · cyclone pose · NOLA frozen at ${kf}${pin}`;
    }
    if (land) {
      return `replay clock seq ${seq} · ${land.world_note}${pin}`;
    }
    return `replay clock seq ${seq} · world still at ${kf}${pin}`;
  }
  function cycloneWindow() {
    const ev = replayEvent();
    if (!ev) return false;
    return ev.phase === 0;
  }
  function cameraKindFor(ev) {
    if (!ev) return "nola";
    if (ev.phase === 0) return "gulf";
    return "subject";
  }
  function cameraKind() {
    return cameraKindFor(replayEvent());
  }
  function landfallDelta() {
    if (beliefPinned) return null;
    const ev = replayEvent();
    return (ev && ev.world_delta) || null;
  }
  function eventElapsed(id) {
    return replayEvents().slice(0, replayIdx + 1).some((e) => e.id === id);
  }
  function populationClock() {
    if (beliefPinned) return null;
    const ev = replayEvent();
    const cur = ev && ev.population_delta;
    if (!cur) return null;
    if (!replayPlaying) {
      heatMix = 0;
      return cur;
    }
    const nxt = replayEvents()[replayIdx + 1];
    const u = Math.min(1, Math.max(0, (performance.now() - playTickAt) / REPLAY_STEP_MS));
    heatMix = u;
    if (!nxt || !nxt.population_delta) return cur;
    return mixPopulationDelta(cur, nxt.population_delta, u);
  }
  function applyPopulationClock(world) {
    const clock = populationClock();
    if (!world || !clock || !world.population) return world;
    const cells = world.population.cells || [];
    const floodedAt = (lon, lat) => {
      let best = null;
      let bd = 1e9;
      for (const c of cells) {
        const d = (c.lon - lon) ** 2 + (c.lat - lat) ** 2;
        if (d < bd) {
          bd = d;
          best = c;
        }
      }
      return !!(best && best.flooded);
    };
    const feats = ((world.hazards && world.hazards.flood && world.hazards.flood.wet_mask)
      && world.hazards.flood.wet_mask.features) || [];
    const prior = world.population.heat || [];
    if (heatJoin.idx !== replayIdx || heatJoin.inund.length !== prior.length) {
      heatJoin = {
        idx: replayIdx,
        inund: prior.map((p) => {
          for (let i = 0; i < feats.length; i++) {
            const ring = feats[i].ring;
            if (ring && pointInRing(p.lon, p.lat, ring)) {
              return feats[i].wet_frac == null ? 1 : feats[i].wet_frac;
            }
          }
          return -1;
        }),
      };
    }
    const empty = (clock.street && clock.street.bowl_empty != null) ? clock.street.bowl_empty : 0.75;
    const heat = prior.map((p, i) => {
      const inund = heatJoin.inund[i];
      let scale;
      if (inund >= 0) scale = clock.wet_frac * (1 - empty * inund);
      else if (feats.length) scale = clock.dry_frac;
      else scale = floodedAt(p.lon, p.lat) ? clock.wet_frac : clock.dry_frac;
      return { ...p, weight: p.weight * scale, density: (p.density || 0) * scale };
    }).filter((p) => p.weight > 0.04);
    for (const h of clock.hotspots || []) {
      heat.push({
        lon: h.lon, lat: h.lat, weight: h.weight, density: h.weight,
        hotspot: true, name: h.name,
      });
    }
    const classes = { ...(world.population.classes || {}), ...(clock.classes || {}) };
    const movement = Array.isArray(clock.movement) ? clock.movement : [];
    return {
      ...world,
      population: {
        ...world.population,
        heat,
        classes,
        movement,
        clock,
        note: clock.note || world.population.note,
      },
    };
  }
  function restWorld(base) {
    const domeNight = eventElapsed("p1-dome-evening");
    const entities = base.entities.map((e) => {
      let state = "operational";
      if (e.entity_id === "warehouse:W1") state = "full";
      if (e.entity_id === "power:waterford") state = "damaged";
      if (e.entity_id === "shelter:dome" && domeNight) state = "critical";
      const gap = e.entity_id === "power:waterford";
      const patch = {
        ...e,
        state,
        ground_truth_state: state,
        verification_status: gap ? "unverified" : "verified",
        label: "pre-landfall",
      };
      if (e.entity_id === "shelter:dome") {
        patch.attributes = {
          ...(e.attributes || {}),
          occupancy: domeNight ? (e.attributes && e.attributes.occupancy) || 10000 : 0,
        };
      }
      return patch;
    });
    return {
      ...base,
      entities,
      events: [],
      hazards: {
        ...base.hazards,
        flood: { ...(base.hazards.flood || {}), stage_m: 0, d_stage_dt: 0, wet_mask: { features: [], coordinates: [] }, paths: [] },
      },
      landfall: { prelandfall: true, r34_on_nola: true, pulse: { truck_status: "N/A", b7_state: "operational" } },
      pulse: { ...base.pulse, truck_status: "N/A", b7_state: "operational", b7_belief: "operational" },
    };
  }
  function applyLandfall(base) {
    if (!base) return base;
    if (beliefPinned) return base;
    const delta = landfallDelta();
    const ev = replayEvent();
    let world;
    if (!delta && ev && ev.phase === 1) world = restWorld(base);
    else if (!delta) world = base;
    else {
      const entities = base.entities.map((e) => {
        const patch = (delta.entities || {})[e.entity_id];
        if (!patch) return e;
        return {
          ...e,
          ...patch,
          attributes: { ...(e.attributes || {}), ...(patch.attributes || {}) },
        };
      });
      const flood = delta.flood
        ? { ...(base.hazards.flood || {}), ...delta.flood }
        : base.hazards.flood;
      let events = [];
      if (delta.glyph) {
        const sub = entities.find((e) => e.entity_id === delta.glyph.subject_entity);
        if (sub && sub.geometry) events = [{ ...delta.glyph, geometry: sub.geometry }];
      }
      world = {
        ...base,
        entities,
        events,
        hazards: { ...base.hazards, flood },
        pulse: { ...base.pulse, ...(delta.pulse || {}) },
        landfall: delta,
      };
    }
    return applyPopulationClock(world);
  }
  function meshState(ent) {
    return ent.ground_truth_state || ent.state;
  }
  function stateCaption(ent) {
    const belief = stateWord(ent.state);
    if (ent.ground_truth_state && ent.ground_truth_state !== ent.state) {
      return `${belief} / GT ${stateWord(ent.ground_truth_state)}`;
    }
    return belief;
  }
  function hurdatTrack() {
    return (hurdat && hurdat.track) || [];
  }
  const TRACK_DRAW_END = Date.parse("2005-08-29T18:00:00Z");
  function isCycloneBeat(e) {
    return (e.layers || []).includes("meteorology") || (e.binds || []).includes("hazards.cyclone");
  }
  function aheadHorizon(iso) {
    const t = Date.parse(iso);
    const later = replayEvents().find((e) => isCycloneBeat(e) && Date.parse(e.t) > t);
    const h = later ? Date.parse(later.t) : TRACK_DRAW_END;
    return Math.min(h, TRACK_DRAW_END);
  }
  function poseAt(iso, throughSite) {
    const track = hurdatTrack();
    if (!track.length || !iso) return null;
    const t = Date.parse(iso);
    const times = track.map((p) => Date.parse(p.utc));
    let i0 = 0;
    let i1 = 0;
    let u = 0;
    if (t <= times[0]) {
      i0 = 0;
      i1 = 0;
    } else if (t >= times[times.length - 1]) {
      i0 = times.length - 1;
      i1 = i0;
    } else {
      i1 = times.findIndex((x) => x >= t);
      i0 = i1 - 1;
      const span = times[i1] - times[i0];
      u = span <= 0 ? 0 : (t - times[i0]) / span;
    }
    const a = track[i0];
    const b = track[i1];
    const lerp = (x, y) => x + (y - x) * u;
    const rOf = (p, fb) => (p.r34_nm == null ? fb : p.r34_nm);
    const ra = rOf(a, 0);
    const rb = rOf(b, ra);
    const lon = lerp(a.lon, b.lon);
    const lat = lerp(a.lat, b.lat);
    const horizon = throughSite ? TRACK_DRAW_END : aheadHorizon(iso);
    const flown = track.slice(0, i0 + 1)
      .filter((p) => Date.parse(p.utc) <= TRACK_DRAW_END)
      .map((p) => [p.lon, p.lat]);
    const last = flown[flown.length - 1];
    if (t <= TRACK_DRAW_END && (!last || last[0] !== lon || last[1] !== lat)) flown.push([lon, lat]);
    const ahead = t <= TRACK_DRAW_END ? [[lon, lat]] : [];
    for (const p of track.slice(i1)) {
      const ts = Date.parse(p.utc);
      if (ts > horizon) break;
      ahead.push([p.lon, p.lat]);
    }
    if (ahead.length < 2 && track[i1] && Date.parse(track[i1].utc) <= TRACK_DRAW_END) {
      ahead.length = 0;
      ahead.push([lon, lat], [track[i1].lon, track[i1].lat]);
    }
    return {
      lon, lat, flown, ahead,
      r34_nm: lerp(ra, rb),
      wind_kt: lerp(a.wind_kt, b.wind_kt),
      cat: u >= 0.5 ? b.cat : a.cat,
    };
  }
  function r34Ring(lon, lat, radiusM, n) {
    const ring = [];
    const dLat = radiusM / 110540;
    const dLon = radiusM / (111320 * Math.cos((lat * Math.PI) / 180) || 1);
    for (let i = 0; i <= n; i++) {
      const a = (i / n) * Math.PI * 2;
      ring.push([lon + dLon * Math.sin(a), lat + dLat * Math.cos(a)]);
    }
    return ring;
  }
  function mercatorY(lat) {
    const s = Math.sin(lat * Math.PI / 180);
    const t = Math.max(-0.9999, Math.min(0.9999, s));
    return 0.5 - Math.log((1 + t) / (1 - t)) / (4 * Math.PI);
  }
  function zoomToContain(centerLng, centerLat, points) {
    if (!points.length) return 11.4;
    const el = map.getContainer();
    const w = el.clientWidth || 900;
    const h = el.clientHeight || 600;
    const pad = 0.18;
    const world0 = 512;
    const cy = mercatorY(centerLat);
    let z = 11.4;
    for (const [lng, lat] of points) {
      const dLng = Math.abs(lng - centerLng);
      const dY = Math.abs(mercatorY(lat) - cy);
      if (dLng > 1e-8) {
        z = Math.min(z, Math.log2((w * (0.5 - pad) * 360) / (world0 * dLng)));
      }
      if (dY > 1e-8) {
        z = Math.min(z, Math.log2((h * (0.5 - pad)) / (world0 * dY)));
      }
    }
    z -= 0.4;
    return Math.max(8.0, Math.min(11.4, z));
  }
  function pointsInFrame(points) {
    if (!points.length) return true;
    const el = map.getContainer();
    const w = el.clientWidth || 900;
    const h = el.clientHeight || 600;
    const padX = w * 0.12;
    const padY = h * 0.12;
    return points.every(([lng, lat]) => {
      const p = map.project([lng, lat]);
      return p.x >= padX && p.x <= w - padX && p.y >= padY && p.y <= h - padY;
    });
  }
  function zoomOutToFit(points) {
    if (!points.length) return null;
    const el = map.getContainer();
    const w = el.clientWidth || 900;
    const h = el.clientHeight || 600;
    const padX = w * 0.14;
    const padY = h * 0.14;
    const cx = w / 2;
    const cy = h / 2;
    const maxX = Math.max(8, w / 2 - padX);
    const maxY = Math.max(8, h / 2 - padY);
    let factor = 1;
    for (const [lng, lat] of points) {
      const p = map.project([lng, lat]);
      const dx = Math.abs(p.x - cx);
      const dy = Math.abs(p.y - cy);
      if (dx > maxX) factor = Math.max(factor, dx / maxX);
      if (dy > maxY) factor = Math.max(factor, dy / maxY);
    }
    if (factor <= 1.02) return null;
    return Math.max(8, map.getZoom() - Math.log2(factor));
  }
  function focusBindEntities() {
    if (!snap) return [];
    const world = applyLandfall(snap);
    const ids = tickBindIds();
    if (!ids.size) return [];
    return world.entities.filter((e) => ids.has(e.entity_id) && e.geometry);
  }
  function syncCamera() {
    if (!map) return;
    const ev = replayEvent();
    const pose = ev ? poseAt(ev.t) : null;
    if (cameraKind() === "gulf" && pose) {
      map.setMaxBounds(null);
      map.easeTo({
        center: [pose.lon, pose.lat],
        zoom: (snap.viz && snap.viz.gulf_camera_zoom) || 5.35,
        pitch: 36,
        bearing: -12,
        duration: replayPlaying ? 700 : (cameraMode === "gulf" ? 450 : 850),
      });
      cameraMode = "gulf";
      return;
    }
    map.setMaxBounds(null);
    const home = [-90.05, 29.975];
    const fromGulf = cameraMode === "gulf";
    const targets = focusBindEntities();
    const pts = targets.map((e) => [e.geometry.lon, e.geometry.lat]);
    const playMs = replayPlaying ? 450 : 550;
    if (fromGulf) {
      let z = 11.4;
      if (pts.length) {
        const need = zoomToContain(home[0], home[1], pts);
        if (need < z) z = need;
      }
      map.easeTo({
        center: home,
        zoom: z,
        pitch: (snap.viz && snap.viz.camera_tilt_degrees) || 42,
        bearing: -18,
        duration: playMs,
      });
      cameraMode = "nola";
      return;
    }
    cameraMode = "nola";
    if (!pts.length || pointsInFrame(pts)) return;
    const zoom = zoomOutToFit(pts);
    if (zoom == null || map.getZoom() - zoom < 0.18) return;
    map.easeTo({ zoom, duration: playMs });
  }
  function pushCycloneLayers(layers, nola) {
    const ev = replayEvent();
    const pose = ev ? poseAt(ev.t, nola) : null;
    if (!pose) return;
    const nmM = 1852;
    if (pose.ahead && pose.ahead.length > 1) {
      layers.push(new PathLayer({
        id: "cyclone-ahead",
        data: [{ path: pose.ahead }],
        getPath: (d) => d.path,
        getColor: [176, 107, 255, nola ? 150 : 70],
        getWidth: nola ? 4 : 3,
        widthMinPixels: nola ? 2 : 1.5,
        pickable: false,
      }));
    }
    if (pose.flown && pose.flown.length > 1) {
      layers.push(new PathLayer({
        id: "cyclone-flown",
        data: [{ path: pose.flown }],
        getPath: (d) => d.path,
        getColor: [196, 130, 255, nola ? 210 : 220],
        getWidth: nola ? 6 : 5,
        widthMinPixels: nola ? 3 : 2.5,
        pickable: false,
      }));
    }
    const showR34 = flags.cycloneAoe && pose.r34_nm > 0 && (!nola || (ev && ev.phase <= 2));
    if (showR34) {
      const ring = r34Ring(pose.lon, pose.lat, pose.r34_nm * nmM, 96);
      layers.push(new PolygonLayer({
        id: nola ? "cyclone-r34-fill" : "cyclone-r34-fill-gulf",
        data: [{ polygon: ring }],
        getPolygon: (d) => d.polygon,
        stroked: false,
        filled: true,
        extruded: false,
        getFillColor: [176, 107, 255, nola ? 42 : 38],
        pickable: false,
        parameters: { depthTest: false },
      }));
      layers.push(new PathLayer({
        id: nola ? "cyclone-r34-nola" : "cyclone-r34",
        data: [{ path: ring }],
        getPath: (d) => d.path,
        getColor: [196, 130, 255, nola ? 220 : 200],
        getWidth: nola ? 3 : 2.5,
        widthMinPixels: 2,
        pickable: false,
      }));
    }
    layers.push(new ScatterplotLayer({
      id: "cyclone-eye",
      data: [pose],
      getPosition: (p) => [p.lon, p.lat],
      getRadius: 14000,
      getFillColor: [255, 255, 255, 230],
      getLineColor: [176, 107, 255, 255],
      stroked: true, filled: true, lineWidthMinPixels: 2,
      radiusUnits: "meters", radiusMinPixels: 6, radiusMaxPixels: 18, pickable: false,
    }));
    layers.push(new TextLayer({
      id: "cyclone-label",
      data: [pose],
      getPosition: (p) => [p.lon, p.lat],
      getText: (p) => `Katrina  ·  Cat ${p.cat}  ·  ${Math.round(p.wind_kt)} kt  ·  R34 ${Math.round(p.r34_nm)} nm`,
      getSize: 12,
      getColor: [244, 236, 255, 255],
      billboard: true,
      getPixelOffset: [0, -22],
      fontFamily: LABEL_FONT,
      fontWeight: 600,
      getTextAnchor: "middle",
      ...textPlate(() => [28, 16, 48, 230], [6, 3, 6, 3]),
    }));
  }
  function typeScale(type) {
    if (type === "bridge") return 8;
    if (type === "vehicle") return 18;
    if (type === "airport") return 10;
    if (type === "gauge" || type === "comm") return 12;
    if (type === "hospital" || type === "warehouse") return 11;
    return 8;
  }
  function headingOf(ent) {
    if (ent.attributes?.heading_deg != null) return ent.attributes.heading_deg;
    if (ent.type === "bridge") return 90;
    if (ent.type === "airport") return 80;
    return 90;
  }
  function stateWord(state) {
    if (state === "operational" || state === "full") return "undamaged";
    if (state === "uncertain") return "unknown";
    if (state === "inaccessible" || state === "destroyed") return "destroyed";
    return state || "unknown";
  }
  function entityFill(ent, _cat, alpha) {
    const s = rgb(ent.state);
    return [s[0], s[1], s[2], alpha];
  }
  function stateHaloRadius(ent) {
    if (ent.type === "bridge" || ent.type === "airport") return 620;
    if (ent.type === "hospital" || ent.type === "shelter" || ent.type === "warehouse") return 460;
    return 400;
  }
  const BUILD_COLOR = {
    residential: [210, 200, 185, 200], commercial: [190, 185, 175, 220],
    hospital: [240, 240, 245, 230], warehouse: [150, 130, 110, 220],
    school: [180, 170, 150, 220], landmark: [220, 210, 190, 230],
  };
  function osmBuildingColor(d) {
    const ev = replayEvent();
    if (ev && ev.phase === 1) {
      const c = BUILD_COLOR[d.kind] || BUILD_COLOR.residential;
      return flags.popTotal ? [c[0], c[1], c[2], 70] : c;
    }
    if (d.damage === "destroyed") return flags.popTotal ? [118, 40, 34, 210] : [88, 32, 28, 235];
    if (d.damage === "damaged") return flags.popTotal ? [210, 128, 48, 190] : [186, 108, 42, 225];
    const c = BUILD_COLOR[d.kind] || BUILD_COLOR.residential;
    return flags.popTotal ? [c[0], c[1], c[2], 70] : c;
  }
  function fillRatio(ent) {
    const a = ent.attributes || {};
    if (a.capacity > 0 && a.stock != null) return Math.max(0, Math.min(1, a.stock / a.capacity));
    if (a.capacity > 0 && a.occupancy != null) return Math.max(0, Math.min(1, a.occupancy / a.capacity));
    return null;
  }
  function pathDistM(a, b) {
    const dy = (b[1] - a[1]) * 110570;
    const dx = (b[0] - a[0]) * 111320 * Math.cos(a[1] * Math.PI / 180);
    return Math.hypot(dx, dy);
  }
  function pathHeadingDeg(path) {
    if (!path || path.length < 2) return 90;
    const i = Math.max(1, Math.floor(path.length / 2));
    const a = path[i - 1], b = path[Math.min(path.length - 1, i + 1)];
    const dlon = (b[0] - a[0]) * Math.cos(a[1] * Math.PI / 180);
    const dlat = b[1] - a[1];
    return (Math.atan2(dlon, dlat) * 180 / Math.PI + 360) % 360;
  }
  function offsetLonLat(lon, lat, eastM, northM) {
    return mToLonLat(lon, lat, eastM, northM);
  }
  function perpUnit(path, i) {
    const prev = path[Math.max(0, i - 1)];
    const next = path[Math.min(path.length - 1, i + 1)];
    const dy = (next[1] - prev[1]) * 110570;
    const dx = (next[0] - prev[0]) * 111320 * Math.cos(((prev[1] + next[1]) / 2) * Math.PI / 180);
    const len = Math.hypot(dx, dy) || 1;
    return { east: -dy / len, north: dx / len };
  }
  function ribbonPolygon(path, widthM, z) {
    const half = widthM / 2;
    const left = [];
    const right = [];
    for (let i = 0; i < path.length; i++) {
      const n = perpUnit(path, i);
      const l = offsetLonLat(path[i][0], path[i][1], n.east * half, n.north * half);
      const r = offsetLonLat(path[i][0], path[i][1], -n.east * half, -n.north * half);
      left.push(z == null ? l : [l[0], l[1], z]);
      right.push(z == null ? r : [r[0], r[1], z]);
    }
    const ring = left.concat(right.reverse());
    ring.push(ring[0]);
    return ring;
  }
  function offsetPath(path, eastM, northM) {
    return path.map(([lon, lat]) => offsetLonLat(lon, lat, eastM, northM));
  }
  function samplePath(path, spacingM) {
    if (!path || path.length < 2) return [];
    const pts = [];
    let acc = 0;
    let nextAt = 0;
    for (let i = 0; i < path.length - 1; i++) {
      const a = path[i], b = path[i + 1];
      const seg = pathDistM(a, b);
      while (nextAt <= acc + seg + 1e-6) {
        const f = seg > 0 ? (nextAt - acc) / seg : 0;
        pts.push({
          lon: a[0] + (b[0] - a[0]) * f,
          lat: a[1] + (b[1] - a[1]) * f,
          heading: pathHeadingDeg([a, b]),
        });
        nextAt += spacingM;
        if (pts.length > 400) return pts;
      }
      acc += seg;
    }
    return pts;
  }
  function pierSquare(lon, lat, heading, sx, sz) {
    const corners = [[-sx, -sz], [sx, -sz], [sx, sz], [-sx, sz]];
    return corners.map(([x, z]) => {
      const [rx, rz] = rotateXZ(x, z, heading);
      return mToLonLat(lon, lat, rx, rz);
    });
  }
  function splitFailedPath(path) {
    const n = path.length;
    return {
      west: path.slice(0, Math.max(2, Math.floor(n * 0.44))),
      east: path.slice(Math.min(n - 2, Math.floor(n * 0.58))),
    };
  }
  function bridgeSpanSolids(entities) {
    const slabs = [];
    const piers = [];
    const strokes = [];
    for (const ent of entities) {
      const paths = ent.attributes?.span_paths;
      if (ent.type !== "bridge" || !paths || !paths.length) continue;
      const cat = solids[solidKey(ent)] || solids.bridge;
      const alpha = Math.round(beliefAlpha(ent) * 255);
      const color = entityFill(ent, cat, alpha);
      const pierColor = [
        Math.max(0, color[0] - 28),
        Math.max(0, color[1] - 28),
        Math.max(0, color[2] - 28),
        alpha,
      ];
      const width = ent.attributes.span_width_m || 12;
      const deckH = ent.attributes.deck_h_m || 12;
      const spacing = ent.attributes.pier_spacing_m || 70;
      const failed = meshState(ent) === "inaccessible" || meshState(ent) === "destroyed";
      for (const raw of paths) {
        const segs = [];
        if (failed) {
          const { west, east } = splitFailedPath(raw);
          const n = perpUnit(raw, Math.floor(raw.length / 2));
          segs.push({ path: west, elevation: deckH * 0.92, drop: false });
          segs.push({
            path: offsetPath(east, n.east * 22, n.north * 22 - 8),
            elevation: 2.4,
            drop: true,
          });
        } else {
          segs.push({ path: raw, elevation: deckH, drop: false });
        }
        for (const seg of segs) {
          if (!seg.path || seg.path.length < 2) continue;
          strokes.push({ path: seg.path, width, color, entity: ent });
          slabs.push({
            polygon: ribbonPolygon(seg.path, width, flags.fallback2d ? 0 : seg.elevation),
            entity: ent,
            color,
          });
          if (seg.drop) continue;
          for (const pier of samplePath(seg.path, spacing)) {
            piers.push({
              polygon: pierSquare(pier.lon, pier.lat, pier.heading, 2.2, Math.max(5, width * 0.45)),
              elevation: flags.fallback2d ? 0 : seg.elevation,
              entity: ent,
              color: pierColor,
            });
          }
        }
      }
    }
    return { slabs, piers, strokes };
  }
  function entitySolids(entities) {
    const rows = [];
    const fills = [];
    for (const ent of entities) {
      const key = solidKey(ent);
      const cat = key && solids[key];
      if (!cat) continue;
      if (ent.type === "bridge" && ent.attributes?.span_paths?.length) continue;
      const scale = typeScale(ent.type);
      const heading = headingOf(ent);
      const lon = ent.geometry.lon, lat = ent.geometry.lat;
      const alpha = Math.round(beliefAlpha(ent) * 255);
      const color = entityFill(ent, cat, alpha);
      for (const part of cat.parts) {
        const polygon = part.ring_m.map(([x, z]) => {
          const [rx, rz] = rotateXZ(x * scale, z * scale, heading);
          return mToLonLat(lon, lat, rx, rz);
        });
        rows.push({ polygon, elevation: part.h * (scale * 0.45), entity: ent, color });
      }
      const ratio = fillRatio(ent);
      if (ratio != null && (STOCK_TYPES.has(ent.type) || OCCUPANCY_TYPES.has(ent.type)) && cat.parts[0]) {
        const p = cat.parts[0];
        const inset = 0.55;
        const polygon = p.ring_m.map(([x, z]) => {
          const [rx, rz] = rotateXZ(x * scale * inset, z * scale * inset, heading);
          return mToLonLat(lon, lat, rx, rz);
        });
        fills.push({
          polygon, elevation: p.h * scale * 0.45 * Math.max(0.08, ratio),
          entity: ent,
          color: STOCK_TYPES.has(ent.type) ? [40, 210, 170, 210] : [176, 107, 255, 210],
        });
      }
    }
    return { rows, fills };
  }

  function cameraAltitudeM() {
    const c = map.getCenter();
    const p = map.project(c);
    const earth = map.unproject([p.x, p.y - 1]);
    const dLat = Math.abs(earth.lat - c.lat);
    return (dLat * 111320 || 1) * 400;
  }

  function onClickEntity(e) {
    selected = e;
    renderInspector();
  }

  function buildLayers() {
    const layers = [];
    if (cycloneWindow()) {
      pushCycloneLayers(layers, false);
      return layers;
    }
    const world = applyLandfall(snap);
    const near = !flags.fallback2d && cameraAltitudeM() < world.viz.lod_switch_altitude_m;
    const entities = world.entities.filter((e) => registry.types[e.type] && opOn(e));
    const land = world.landfall;

    if (flags.opEvacuate && fieldOn("flood")) {
      layers.push(new ScatterplotLayer({
        id: "pop-displaced", data: world.population.cells.filter((c) => c.displaced > 0),
        getPosition: (c) => [c.lon, c.lat],
        getRadius: 80,
        getFillColor: [255, 140, 50, 55], radiusUnits: "meters",
      }));
    }
    const evacMoves = flags.opEvacuate ? (world.population.movement || []) : [];
    if (evacMoves.length && ArcLayer) {
      const pulse = 0.5 + 0.5 * Math.sin(performance.now() / 420);
      const glow = Math.round(120 + pulse * 135);
      layers.push(new ArcLayer({
        id: "pop-move-glow", data: evacMoves,
        getSourcePosition: (m) => m.from, getTargetPosition: (m) => m.to,
        getSourceColor: [255, 40, 0, Math.round(40 + pulse * 70)],
        getTargetColor: [255, 80, 0, Math.round(50 + pulse * 80)],
        getWidth: (m) => (14 + m.magnitude * 10) * (0.85 + pulse * 0.5),
        getHeight: EVAC_ARC_HEIGHT,
        greatCircle: false,
        widthMinPixels: 10,
      }));
      layers.push(new ArcLayer({
        id: "pop-move", data: evacMoves,
        getSourcePosition: (m) => m.from, getTargetPosition: (m) => m.to,
        getSourceColor: [255, 220, 40, glow],
        getTargetColor: [255, 60, 0, glow],
        getWidth: (m) => (5 + m.magnitude * 6) * (0.8 + pulse * 0.55),
        getHeight: EVAC_ARC_HEIGHT,
        greatCircle: false,
        widthMinPixels: 5,
      }));
      const arrows = evacArcArrows(evacMoves, flowT);
      layers.push(new PathLayer({
        id: "pop-move-arrows",
        data: arrows,
        getPath: (d) => d.path,
        getColor: [255, 236, 80, 255],
        getWidth: 10,
        widthMinPixels: 3,
        capRounded: false,
        jointRounded: false,
        parameters: { depthTest: false },
        updateTriggers: { getPath: flowT },
      }));
    }

    const flood = world.hazards.flood;
    const mask = flood.wet_mask || {};
    const floodFeats = fieldOn("flood") && (mask.features && mask.features.length)
      ? mask.features
      : fieldOn("flood")
        ? (mask.coordinates || []).map((poly) => ({
          ring: poly[0], depth_m: flood.stage_m, wet_frac: 1,
        }))
        : [];
    const floodPolys = floodFeats.map((d) => {
      const depth = d.depth_m || 0;
      const frac = d.wet_frac == null ? 1 : d.wet_frac;
      const flat = flags.fallback2d || flags.popTotal;
      return {
        polygon: d.ring,
        elevation: flat ? 0 : Math.max(0.3, depth * (0.25 + 0.75 * frac) * 2.5),
        alpha: flags.popTotal
          ? Math.round(18 + frac * 70)
          : Math.round(28 + frac * 155 + Math.min(25, depth * 10)),
      };
    });
    const geo = world.geography || { roads: [], canals: [], buildings: [] };
    if (geo.buildings && geo.buildings.length && SolidPolygonLayer) {
      layers.push(new SolidPolygonLayer({
        id: "osm-buildings",
        data: geo.buildings,
        getPolygon: (d) => d.ring,
        extruded: !flags.fallback2d && !flags.popTotal,
        getElevation: (d) => (flags.fallback2d || flags.popTotal) ? 0 : d.height_m,
        getFillColor: (d) => osmBuildingColor(d),
        getLineColor: (d) => {
          if (replayEvent() && replayEvent().phase === 1) return [40, 40, 40, 80];
          if (d.damage === "destroyed") return [70, 22, 18, 180];
          if (d.damage === "damaged") return [140, 70, 28, 160];
          return [40, 40, 40, 80];
        },
        lineWidthMinPixels: 0.3,
      }));
    }
    if (geo.roads && geo.roads.length) {
      const roadW = (hw) => (hw && hw.startsWith("motorway") ? 7 : hw && hw.startsWith("trunk") ? 5 : 3);
      const roadsIntact = !!(land && land.prelandfall);
      const openRoads = roadsIntact
        ? geo.roads
        : geo.roads.filter((x) => x.state === "open" || !x.state);
      layers.push(new PathLayer({
        id: "osm-roads", data: openRoads,
        getPath: (x) => x.path,
        getColor: SEG_COLOR.open,
        getWidth: (x) => roadW(x.highway),
        widthMinPixels: 1.2,
        capRounded: true, jointRounded: true,
      }));
    }
    if (floodPolys.length) {
      layers.push(new SolidPolygonLayer({
        id: "flood", data: floodPolys, getPolygon: (d) => d.polygon,
        extruded: !flags.fallback2d && !flags.popTotal,
        getElevation: (d) => d.elevation,
        getFillColor: (d) => [30, 90, 180, d.alpha],
      }));
    }
    if (flags.popTotal) {
      const heat = (world.population.heat && world.population.heat.length)
        ? world.population.heat
        : (geo.buildings || []).filter((b) => b.heat_weight > 0).map((b) => ({
            lon: b.cx, lat: b.cy, weight: b.heat_weight, density: b.density,
          }));
      const HeatmapLayer = deck.HeatmapLayer;
      if (HeatmapLayer && !flags.fallback2d && heat.length) {
        layers.push(new HeatmapLayer({
          id: "pop-total",
          data: heat,
          getPosition: (p) => [p.lon, p.lat],
          getWeight: (p) => p.weight,
          radiusPixels: 48,
          intensity: 2.2,
          threshold: 0.03,
          updateTriggers: { getWeight: `${replayIdx}:${heatMix.toFixed(2)}`, data: replayIdx },
          colorRange: [
            [255, 255, 178, 120],
            [254, 217, 118, 170],
            [254, 178, 76, 200],
            [253, 141, 60, 220],
            [240, 59, 32, 235],
            [189, 0, 38, 250],
          ],
          parameters: { depthTest: false, depthMask: false },
        }));
      } else if (heat.length) {
        layers.push(new ScatterplotLayer({
          id: "pop-total", data: heat,
          getPosition: (p) => [p.lon, p.lat],
          getRadius: 180,
          getFillColor: (p) => densColor(p.density, world.population.bin_edges_per_km2, 160),
          radiusUnits: "meters",
        }));
      }
    }

    const geoRoads = (world.geography && world.geography.roads) || [];
    const showSub = fieldOn("flood") && (!land || land.roads_wet);
    const submergedRoads = showSub ? geoRoads.filter((x) => x.state === "submerged") : [];
    const shutRoads = land ? [] : geoRoads.filter((x) => x.state === "degraded" || x.state === "blocked");
    if (submergedRoads.length) {
      const roadW = (hw) => (hw && hw.startsWith("motorway") ? 5 : hw && hw.startsWith("trunk") ? 3.5 : 2);
      layers.push(new PathLayer({
        id: "osm-roads-submerged", data: submergedRoads,
        getPath: (x) => x.path,
        getColor: SEG_COLOR.submerged,
        getWidth: (x) => roadW(x.highway),
        widthMinPixels: 1.4,
        capRounded: true, jointRounded: true,
        parameters: { depthTest: false },
      }));
    }
    if (shutRoads.length) {
      const roadW = (hw) => (hw && hw.startsWith("motorway") ? 12 : hw && hw.startsWith("trunk") ? 9 : 6);
      layers.push(new PathLayer({
        id: "osm-roads-constraint", data: shutRoads,
        getPath: (x) => x.path,
        getColor: (x) => SEG_COLOR[x.state] || [230, 230, 220, 255],
        getWidth: (x) => roadW(x.highway),
        widthMinPixels: 5,
        capRounded: true, jointRounded: true,
        parameters: { depthTest: false },
      }));
    }

    const hideConvoy = !!(land && land.pulse && land.pulse.truck_status === "N/A");
    const permit = world.permits[0];
    const plan = world.plans[0];
    const solidRoute = flags.opRealloc && !hideConvoy && permit?.status === "active" ? permit.authorized_route : null;
    const ghostRoute = flags.opRealloc && !hideConvoy && plan && permit?.status !== "active" ? plan.via : null;

    if (flags.opRealloc && !hideConvoy) {
      layers.push(new PathLayer({
        id: "segments", data: world.route_segments,
        getPath: (x) => x.path,
        getColor: (x) => {
          if (x.route_id === ghostRoute && x.route_id !== solidRoute) return [180, 180, 200, 90];
          return SEG_COLOR[x.state] || [180, 180, 200, 200];
        },
        getWidth: (x) => {
          if (x.state === "blocked" || x.state === "degraded") return 22;
          if (x.state === "submerged") return 8;
          return 14;
        }, widthMinPixels: 4,
      }));
      if (ghostRoute && world.route_paths[ghostRoute] && ghostRoute !== solidRoute) {
        layers.push(new PathLayer({
          id: "ghost-plan", data: [{ path: world.route_paths[ghostRoute] }],
          getPath: (d) => d.path, getColor: [180, 190, 220, 120], getWidth: 5, widthMinPixels: 2,
        }));
      }
      if (solidRoute && world.route_paths[solidRoute]) {
        layers.push(new PathLayer({
          id: "solid-permit", data: [{ path: world.route_paths[solidRoute] }],
          getPath: (d) => d.path, getColor: [55, 214, 122, 240], getWidth: 10, widthMinPixels: 4,
        }));
      }
    }

    pushCycloneLayers(layers, true);

    const contam = fieldOn("contamination")
      ? ((world.hazards.contamination && world.hazards.contamination.areas) || [])
      : [];
    if (contam.length) {
      layers.push(new PolygonLayer({
        id: "contamination",
        data: contam,
        getPolygon: (d) => d.ring,
        stroked: true,
        filled: true,
        extruded: false,
        getFillColor: [28, 210, 68, 140],
        getLineColor: [70, 255, 120, 230],
        lineWidthMinPixels: 2,
        pickable: false,
        parameters: { depthTest: false },
      }));
    }

    const fire = world.hazards.fire || {};
    if (fieldOn("fire") && fire.active && (fire.sites || []).length) {
      const wind = fire.wind || { u: 0.12, v: 0.06 };
      const particles = [];
      for (const s of fire.sites) {
        const r0 = s.radius_m || 70;
        const n = 96;
        for (let i = 0; i < n; i++) {
          const h = Math.sin(i * 12.9898 + (s.lon || 0) * 78.233) * 43758.5453;
          const rnd = h - Math.floor(h);
          const u = (rnd + fireT) % 1;
          const ang = i * 2.399 + fireT * 1.7;
          const spread = r0 * (0.12 + (1 - u) * 0.55);
          const east = Math.cos(ang) * spread + wind.u * u * 180;
          const north = Math.sin(ang) * spread * 0.45 + wind.v * u * 180;
          const ll = mToLonLat(s.lon, s.lat, east, north);
          const smoke = u > 0.42;
          particles.push({
            lon: ll[0], lat: ll[1], z: u * (55 + r0 * 0.9),
            radius: smoke ? 18 + u * 42 : 8 + (1 - u) * 16,
            color: smoke
              ? [48, 44, 40, Math.round(90 - u * 55)]
              : u < 0.18
                ? [255, 252, 160, 240]
                : [255, 90 + Math.round(u * 40), 12, 220],
          });
        }
      }
      const embers = particles.filter((p) => p.color[0] > 80);
      const smoke = particles.filter((p) => p.color[0] <= 80);
      layers.push(new ScatterplotLayer({
        id: "fire-core",
        data: fire.sites,
        getPosition: (s) => [s.lon, s.lat, 4],
        getRadius: (s) => (s.radius_m || 70) * 0.7,
        getFillColor: [255, 58, 8, 210],
        radiusUnits: "meters",
        pickable: false,
        parameters: { depthTest: false },
      }));
      layers.push(new ScatterplotLayer({
        id: "fire-ember",
        data: embers,
        getPosition: (p) => [p.lon, p.lat, p.z],
        getRadius: (p) => p.radius,
        getFillColor: (p) => p.color,
        radiusUnits: "meters",
        pickable: false,
        parameters: { depthTest: false },
        updateTriggers: { getPosition: fireT },
      }));
      layers.push(new ScatterplotLayer({
        id: "fire-smoke",
        data: smoke,
        getPosition: (p) => [p.lon, p.lat, p.z],
        getRadius: (p) => p.radius,
        getFillColor: (p) => p.color,
        radiusUnits: "meters",
        pickable: false,
        parameters: { depthTest: false },
        updateTriggers: { getPosition: fireT },
      }));
    }

    const placed = entities.filter((e) => registry.types[e.type]?.primitive === "mesh");
    const { rows, fills } = entitySolids(placed);
    const pickEnt = (info) => { if (info.object?.entity) onClickEntity(info.object.entity); };
    const stateMarks = entities.filter((e) => e.geometry && e.type !== "route" && e.type !== "route_segment");
    const focusIds = tickBindIds();
    const focusMarks = stateMarks.filter((e) => focusIds.has(e.entity_id));
    layers.push(new ScatterplotLayer({
      id: "entity-state-halo-glow",
      data: stateMarks,
      getPosition: (e) => [e.geometry.lon, e.geometry.lat],
      getRadius: (e) => stateHaloRadius(e) * 1.35,
      radiusUnits: "meters",
      radiusMinPixels: 22,
      radiusMaxPixels: 120,
      getFillColor: (e) => { const c = rgb(e.state); return [c[0], c[1], c[2], 70]; },
      stroked: false,
      filled: true,
      pickable: false,
      parameters: { depthTest: false },
    }));
    layers.push(new ScatterplotLayer({
      id: "entity-state-halo",
      data: stateMarks,
      getPosition: (e) => [e.geometry.lon, e.geometry.lat],
      getRadius: (e) => stateHaloRadius(e),
      radiusUnits: "meters",
      radiusMinPixels: 16,
      radiusMaxPixels: 90,
      getFillColor: (e) => { const c = rgb(e.state); return [c[0], c[1], c[2], 120]; },
      getLineColor: (e) => { const c = rgb(e.state); return [c[0], c[1], c[2], 255]; },
      stroked: true,
      filled: true,
      lineWidthMinPixels: 4,
      lineWidthMaxPixels: 8,
      pickable: false,
      parameters: { depthTest: false },
    }));
    if (focusMarks.length) {
      layers.push(new ScatterplotLayer({
        id: "replay-tick-halo",
        data: focusMarks,
        getPosition: (e) => [e.geometry.lon, e.geometry.lat],
        getRadius: (e) => stateHaloRadius(e) * 1.8,
        radiusUnits: "meters",
        radiusMinPixels: 28,
        radiusMaxPixels: 160,
        getFillColor: [176, 107, 255, 40],
        getLineColor: [244, 236, 255, 255],
        stroked: true,
        filled: true,
        lineWidthMinPixels: 3,
        pickable: false,
        parameters: { depthTest: false },
      }));
    }
    const bridgeGeom = bridgeSpanSolids(placed);
    if (bridgeGeom.strokes.length) {
      layers.push(new PathLayer({
        id: "bridge-spans",
        data: bridgeGeom.strokes,
        getPath: (d) => d.path,
        getColor: (d) => d.color,
        getWidth: (d) => d.width,
        widthUnits: "meters",
        widthMinPixels: 3,
        capRounded: true,
        jointRounded: true,
        pickable: true,
        onClick: pickEnt,
      }));
    }
    if (SolidPolygonLayer && !flags.fallback2d) {
      if (bridgeGeom.piers.length) {
        layers.push(new SolidPolygonLayer({
          id: "bridge-piers",
          data: bridgeGeom.piers,
          getPolygon: (d) => d.polygon,
          extruded: true,
          getElevation: (d) => d.elevation,
          getFillColor: (d) => d.color,
          pickable: true,
          onClick: pickEnt,
        }));
      }
      if (bridgeGeom.slabs.length) {
        layers.push(new SolidPolygonLayer({
          id: "bridge-decks",
          data: bridgeGeom.slabs,
          getPolygon: (d) => d.polygon,
          extruded: false,
          filled: true,
          getFillColor: (d) => d.color,
          pickable: true,
          onClick: pickEnt,
        }));
      }
    }
    function pushFootprints(id, data) {
      if (SolidPolygonLayer) {
        layers.push(new SolidPolygonLayer({
          id, data, getPolygon: (d) => d.polygon,
          extruded: !flags.fallback2d,
          getElevation: (d) => flags.fallback2d ? 0 : d.elevation,
          getFillColor: (d) => d.color, pickable: true, onClick: pickEnt,
        }));
      } else {
        layers.push(new PolygonLayer({
          id, data, getPolygon: (d) => d.polygon,
          getFillColor: (d) => d.color, getLineColor: [12, 16, 28, 200],
          lineWidthMinPixels: 1, pickable: true, onClick: pickEnt,
        }));
      }
    }
    pushFootprints("type-solids", rows);
    if (fills.length) pushFootprints("stock-fill", fills);
    const named = entities.filter((e) => e.geometry && e.name
      && e.type !== "route" && e.type !== "route_segment"
      && focusIds.has(e.entity_id));
    layers.push(new TextLayer({
      id: "entity-names",
      data: named,
      getPosition: (e) => [e.geometry.lon, e.geometry.lat],
      getText: (e) => `${typeSymbol(e)}  ${e.name}  · ${stateCaption(e)}`,
      getSize: (e) => focusIds.has(e.entity_id) ? 13 : 7,
      getColor: [244, 247, 252, 255],
      billboard: true,
      getPixelOffset: [0, -18],
      fontFamily: LABEL_FONT,
      fontWeight: 600,
      getTextAnchor: "middle",
      getAlignmentBaseline: "bottom",
      background: true,
      getBackgroundColor: (e) => statePlate(e.state),
      backgroundPadding: [4, 2, 4, 2],
      getBorderColor: (e) => stateBorder(e.state),
      getBorderWidth: 1,
      parameters: { depthTest: false },
    }));
    const stockLabels = placed.filter((e) => fillRatio(e) != null);
    if (stockLabels.length) {
      layers.push(new TextLayer({
        id: "stock-readout", data: stockLabels,
        getPosition: (e) => [e.geometry.lon, e.geometry.lat],
        getText: (e) => {
          const a = e.attributes;
          const n = a.stock != null ? a.stock : a.occupancy;
          return `${fmt(Math.round(n))} / ${fmt(Math.round(a.capacity))}`;
        },
        getSize: 6,
        getColor: (e) => STOCK_TYPES.has(e.type) ? [160, 245, 220, 255] : [220, 200, 255, 255],
        billboard: true, getPixelOffset: [0, 10],
        fontFamily: LABEL_FONT,
        fontWeight: 600,
        ...textPlate((e) => STOCK_TYPES.has(e.type) ? [6, 18, 16, 230] : [28, 16, 48, 230], [4, 2, 4, 2]),
      }));
    }

    const truck = placed.find((e) => e.entity_id === "truck:17");
    if (truck && world.tasks[0]?.status === "SUSPENDED" && !hideConvoy) {
      layers.push(new ScatterplotLayer({
        id: "truck-suspend", data: [truck],
        getPosition: (e) => [e.geometry.lon, e.geometry.lat], getRadius: 280,
        getFillColor: [255, 89, 100, 35], getLineColor: [255, 89, 100, 220],
        stroked: true, filled: true, radiusUnits: "meters",
      }));
    }

    const events = (world.events || []).filter(eventOn);
    layers.push(new ScatterplotLayer({
      id: "unverified-ping",
      data: events.filter((ev) => ev.verification_status === "unverified"),
      getPosition: (ev) => [ev.geometry.lon, ev.geometry.lat], getRadius: 400,
      getFillColor: [180, 180, 190, 30], getLineColor: [200, 200, 210, 180],
      stroked: true, filled: true, radiusUnits: "meters",
    }));
    layers.push(new ScatterplotLayer({
      id: "verified-shock",
      data: events.filter((ev) => ev.verification_status === "verified" && ev.decay > 0.5),
      getPosition: (ev) => [ev.geometry.lon, ev.geometry.lat],
      getRadius: (ev) => 200 + ev.decay * 500,
      getFillColor: [255, 89, 100, 20], getLineColor: [255, 89, 100, 160],
      stroked: true, filled: true, radiusUnits: "meters",
    }));
    layers.push(new TextLayer({
      id: "event-glyphs", data: events.filter((ev) => ev.decay > 0.05),
      getPosition: (ev) => [ev.geometry.lon, ev.geometry.lat],
      getText: (ev) => ev.verification_status === "unverified"
        ? "?"
        : (EVENT_GLYPH[ev.event_type] || "!"),
      getSize: (ev) => 10 + ev.decay * 6,
      getColor: (ev) => ev.verification_status === "unverified"
        ? [232, 238, 252, 240]
        : [255, 220, 220, 255],
      billboard: true,
      fontFamily: LABEL_FONT,
      ...textPlate((ev) => ev.verification_status === "unverified"
        ? [28, 30, 38, 230]
        : [48, 12, 18, 230], [6, 3, 6, 3]),
    }));
    return layers;
  }

  function renderPulse() {
    if (cycloneWindow()) {
      const pose = replayEvent() ? poseAt(replayEvent().t) : null;
      document.getElementById("pulse").innerHTML = `
        <h3 class="sec">Cyclone window</h3>
        <div class="metric"><div class="lab">Eye</div>
          <div class="val">${pose ? `${pose.lat.toFixed(1)}°N ${Math.abs(pose.lon).toFixed(1)}°W` : "—"}</div></div>
        <div class="metric"><div class="lab">Category / wind</div>
          <div class="val">${pose ? `Cat ${pose.cat}` : "—"}</div>
          <div class="lab">${pose ? `${Math.round(pose.wind_kt)} kt` : ""}</div></div>
        <div class="metric"><div class="lab">34-kt radius</div>
          <div class="val">${pose && pose.r34_nm > 0 ? `${Math.round(pose.r34_nm)} nm` : "none"}</div>
          <div class="lab">HURDAT2 mean of quadrants</div></div>
        <h3 class="sec">Logistics</h3>
        <div class="metric"><div class="lab">NOLA world</div>
          <div class="val" style="font-size:14px">frozen at ${kf}</div>
          <div class="lab">entities not interpolated in phase 0</div></div>`;
      return;
    }
    const world = applyLandfall(snap);
    const ev = replayEvent();
    const p = world.pulse;
    const land = world.landfall;
    const pose = ev ? poseAt(ev.t) : null;
    const ids = [...tickBindIds()];
    const subjects = world.entities.filter((e) => ids.includes(e.entity_id));
    const layers = (ev && ev.layers) || [];
    const subjectHtml = subjects.length
      ? subjects.map((e) => `<div class="metric"><div class="lab">${e.entity_id}</div>
          <div class="val" style="font-size:13px;line-height:1.25">${e.name}</div>
          <div class="lab">${stateCaption(e)}</div></div>`).join("")
      : `<div class="metric"><div class="lab">On the map</div>
          <div class="val" style="font-size:13px;line-height:1.25">${(layers.includes("meteorology") || (ev && (ev.binds || []).includes("hazards.cyclone")))
            ? "NOLA at rest · storm inbound"
            : "NOLA overview"}</div>
          <div class="lab">${(ev && ev.binds && ev.binds.length) ? ev.binds.join(", ") : "this bullet has no catalog pin"}</div></div>`;
    const clock = world.population && world.population.clock;
    const popHtml = clock ? `
      <h3 class="sec">Population this tick</h3>
      <div class="metric"><div class="lab">In Orleans</div>
        <div class="val">${fmt(clock.city_in)}</div>
        <div class="lab">${Math.round((clock.city_frac || 0) * 100)}% of Census 2000 · ${fmt((clock.classes && clock.classes.evacuated) || 0)} gone</div></div>
      <div class="metric"><div class="lab">Dome / CC</div>
        <div class="val">${fmt((clock.classes && clock.classes["shelter:dome"]) || 0)} / ${fmt((clock.classes && clock.classes["shelter:morial"]) || 0)}</div>
        <div class="lab">${clock.gap_fill ? "includes design:gap-fill interpolants" : "sourced occupancy"}</div></div>` : "";
    const eHtml = land && land.build_phase === "E" ? `
      <h3 class="sec">Unwatering</h3>
      <div class="metric"><div class="lab">HUD remaining</div>
        <div class="val">${p.remain != null ? Math.round(p.remain * 100) + "%" : "—"}</div>
        <div class="lab">${p.pumps_on != null ? p.pumps_on + " / " + p.pumps_total + " pumps" : "permanent pumps mostly dead"}${p.off_map ? " · " + p.off_map : ""}</div></div>` : "";
    const logistics = land && land.prelandfall ? "" : `
      <h3 class="sec">Pulse</h3>
      <div class="metric"><div class="lab">Convoy 17</div><div class="val">${p.truck_status}</div></div>
      <div class="metric ${p.b7_state === "inaccessible" ? "crit" : ""}"><div class="lab">bridge:B7 ${land ? "GT" : ""}</div>
        <div class="val">${p.b7_state}</div>
        ${land ? `<div class="lab">belief ${p.b7_belief || "uncertain"} · t0 JSON unchanged</div>` : ""}</div>`;
    document.getElementById("pulse").innerHTML = `
      <h3 class="sec">This event</h3>
      <div class="metric"><div class="lab">${ev ? ev.id : ""} · ${ev ? ev.t_label : ""}</div>
        <div class="val" style="font-size:13px;line-height:1.3">${ev ? ev.title : "—"}</div>
        <div class="lab">${layers.join(" · ") || "—"}</div></div>
      <h3 class="sec">Subject</h3>
      ${subjectHtml}
      ${popHtml}
      ${eHtml}
      ${pose ? `<div class="metric"><div class="lab">Katrina overlay</div>
        <div class="val">Cat ${pose.cat}</div>
        <div class="lab">${Math.round(pose.wind_kt)} kt · R34 ${Math.round(pose.r34_nm)} nm</div></div>` : ""}
      ${logistics}`;
  }

  function renderInspector() {
    const el = document.getElementById("inspector");
    const world = applyLandfall(snap);
    const ev = replayEvent();
    const phaseScan = ev ? scanBinds(phaseBinds(ev.phase)) : {};
    const pose = ev ? poseAt(ev.t) : null;
    const ids = [...tickBindIds()];
    const subjects = ids.map((id) => world.entities.find((e) => e.entity_id === id)).filter(Boolean);
    const poseBlock = pose ? `
      <div class="insp row"><span class="k">eye</span><span>${pose.lat.toFixed(2)}, ${pose.lon.toFixed(2)}</span></div>
      <div class="insp row"><span class="k">wind / R34</span><span>${Math.round(pose.wind_kt)} kt · ${Math.round(pose.r34_nm)} nm</span></div>
      <div class="insp row"><span class="k">cyclone source</span><span>hurdat2-al122005</span></div>
    ` : "";
    const replayBlock = ev ? `
      <h3 class="sec">Replay event</h3>
      <div class="insp"><strong>${ev.title}</strong></div>
      <div class="insp row"><span class="k">clock</span><span>${replayIdx + 1} / ${replayEvents().length} · ${ev.t_label}</span></div>
      <div class="insp row"><span class="k">id</span><span>${ev.id}</span></div>
      <div class="insp row"><span class="k">phase</span><span>${ev.phase} · ${(script.phases.find((p) => p.id === ev.phase) || {}).name || ""}</span></div>
      <div class="insp row"><span class="k">binds</span><span>${(ev.binds && ev.binds.length) ? ev.binds.join(", ") : "—"}</span></div>
      ${ids.length ? `<div class="insp row"><span class="k">on map</span><span>${subjects.map((e) => e.name).join(", ")}</span></div>` : ""}
      <div class="insp row"><span class="k">fields on</span><span>${["flood", "fire", "contamination"].filter(fieldOn).join(", ") || "cyclone only"}</span></div>
      ${poseBlock}
      <div class="insp row"><span class="k">world</span><span>${worldNote()}</span></div>
      <h3 class="sec">Phase category scan</h3>
      <p class="insp dash">Every asset category for this sequence. Gap = look up or design:gap-fill before paint (phase B+).</p>
      ${scanHtml(phaseScan)}
    ` : "";
    if (!selected) {
      el.innerHTML = `${replayBlock}
        <h3 class="sec">Inspector</h3>
        <p class="insp dash">Click an entity. Provenance follows source_event_id.</p>
        <h3 class="sec">Active events</h3>
        ${ (world.events || []).filter(eventOn).map((x) => `<div class="insp row"><span>${x.event_type}</span>
          <span class="tag">${x.verification_status}</span></div>`).join("")}`;
      return;
    }
    const live = world.entities.find((e) => e.entity_id === selected.entity_id) || selected;
    const a = live.attributes || {};
    const syn = live.synthetic ? `<span class="tag syn">synthetic / not Katrina</span>` : "";
    el.innerHTML = `${replayBlock}
      <h3 class="sec">${live.entity_id}</h3>
      <div class="insp"><strong>${live.name}</strong> ${syn}</div>
      <div class="insp row"><span class="k">type</span><span>${typeSymbol(live)} ${live.type}</span></div>
      <div class="insp row"><span class="k">operation</span><span>${OP_LABEL[opOf(live)]}</span></div>
      <div class="insp row"><span class="k">category</span><span>${catOf(live)}</span></div>
      <div class="insp row"><span class="k">state</span><span>${stateCaption(live)}</span></div>
      <div class="insp row"><span class="k">verification</span><span>${live.verification_status}</span></div>
      <div class="insp row"><span class="k">confidence</span><span>${dash(live.confidence)}</span></div>
      <div class="insp row"><span class="k">population</span><span>${dash(a.population)}</span></div>
      <div class="insp row"><span class="k">stock / cap</span><span>${dash(a.stock)} / ${dash(a.capacity)}</span></div>
      <div class="insp row"><span class="k">occupancy</span><span>${dash(a.occupancy)} / ${dash(a.capacity)}</span></div>
      <div class="insp row"><span class="k">water hours</span><span>${dash(a.water_hours)}</span></div>
      <div class="insp row"><span class="k">stage_m</span><span>${dash(a.stage_m)}</span></div>
      <h3 class="sec">Provenance</h3>
      <div class="prov">source_key → <code>${live.source_key || "—"}</code><br/>
        source_event_id → <code>${live.source_event_id || "—"}</code><br/>
        valid_from ${live.valid_from || "—"}<br/>recorded_at ${live.recorded_at || world.recorded_at}</div>`;
  }

  function typeLegendHtml() {
    const seen = {};
    for (const e of snap.entities) {
      if (!opOn(e)) continue;
      const t = registry.types[e.type];
      if (!t || !t.symbol_far || t.symbol_far === "line" || t.symbol_far === "outline") continue;
      const cat = t.category || "other";
      if (!seen[cat]) seen[cat] = {};
      seen[cat][e.type] = t.symbol_far;
    }
    const cats = CAT_ORDER.filter((c) => seen[c]);
    return cats.map((cat) => {
      const bits = Object.entries(seen[cat]).map(([typ, g]) => `${g} ${typ}`).join(" · ");
      return `<div style="margin-top:3px"><span style="color:#c7d3ee">${cat}</span> · ${bits}</div>`;
    }).join("");
  }

  function renderLegend() {
    const world = applyLandfall(snap);
    const bins = world.population.bin_edges_per_km2;
    const ev = replayEvent();
    const note = worldNote();
    const ids = [...tickBindIds()];
    const subjects = ids.map((id) => world.entities.find((ent) => ent.entity_id === id)).filter(Boolean);
    const subjectLine = subjects.length
      ? `camera on ${subjects.map((ent) => ent.name).join(" · ")}`
      : "NOLA basemap + catalog at rest";
    const evLine = ev ? `<div class="event-now">${ev.title}</div><div>${ev.t_label} · ${ev.id}</div>` : "";
    if (cycloneWindow()) {
      const pose = ev ? poseAt(ev.t) : null;
      document.getElementById("legend").innerHTML = `
        ${evLine}
        <div>${note}</div>
        <div>solid purple = flown so far · ghost = next script meteorology beat · disk = HURDAT2 34-kt mean radius</div>
        <div>${pose ? `Cat ${pose.cat} · ${Math.round(pose.wind_kt)} kt · R34 ${Math.round(pose.r34_nm)} nm` : ""}</div>
        <div>NOLA assets enter at phase 1 · this window is the storm over water</div>
        <div style="opacity:.8">source: hurdat2-al122005</div>`;
      return;
    }
    document.getElementById("legend").innerHTML = flags.popTotal
      ? `${evLine}
         <div>${subjectLine}</div>
         <div>${note}</div>
         <div>POPULATION DENSITY · people/km² · ${snap.population.bin_method}</div>
         <div>${(world.population.clock && world.population.clock.note) || "heatmap follows the replay clock"}</div>
         <div>sampled on OSM buildings + land roads (basemap fabric) · low &lt; ${bins[0]} · med ${bins[0]}–${bins[1]} · high ${bins[1]}–${bins[2]} · very high &gt; ${bins[2]}</div>
         <div style="margin-top:4px">evac movement = pulsing orange arcs · this tick's evacuation (outbound, into shelters, off-map via MSY)</div>
         <div style="margin-top:4px">roads: open green · degraded amber · blocked red · submerged blue</div>
         <div style="margin-top:4px">entities: type mesh only · color = damage spectrum · green undamaged → yellow unknown → orange damaged → red destroyed</div>
         <div style="margin-top:4px">hazards follow the replay clock · flood / fire / contamination appear when the sequence introduces them</div>
         <div style="margin-top:4px">flood = HUD district depth × flooded-unit share · city stage ${world.hazards.flood.stage_m} m · Δ ${world.hazards.flood.d_stage_dt}</div>
         <div style="margin-top:4px;opacity:.8">${(world.geography && world.geography.vintage) || ""}</div>`
      : `${evLine}
         <div>${subjectLine}</div>
         <div>${note}</div>
         <div>two operations · realloc (stock) · evacuate (occupancy / displacement)</div>
         <div>access (bridges, roads, breaches) is a shared constraint — drawn with either operation</div>
         <div>roads: open green · degraded amber · blocked red · submerged blue</div>
         <div>hazards follow the replay clock · cyclone pose at this tick · flood / fire / spill when introduced</div>
         <div>evac movement = pulsing orange arcs · this tick's evacuation</div>
         <div>mesh = entity type · color = damage · green undamaged · yellow unknown · orange damaged · red destroyed</div>
         <div>glyph = type · unverified ping is grey</div>
         <div style="margin-top:6px;color:#c7d3ee">ENTITY SYMBOLS</div>
         ${typeLegendHtml()}`;
  }

  function renderPopCtl() {
    const el = document.getElementById("popctl");
    const row = (id, label) => `<label><input type="checkbox" id="${id}" ${flags[id] ? "checked" : ""}/> ${label}</label>`;
    el.innerHTML = `<div style="font-weight:700;color:#c7d3ee;letter-spacing:.08em;font-size:10px">OPERATIONS</div>
      ${row("opRealloc", "Resource reallocation")}
      <div class="hint">water · food · medicine · fuel · vehicles · personnel · warehouses</div>
      ${row("opEvacuate", "Evacuation")}
      <div class="hint">shelters · camp · hospitals · orange arcs = movement</div>
      <div class="hint" style="margin:8px 0 2px 0">Access (B7, roads, breaches, pumps) is a constraint on both — not its own operation.</div>
      <div style="font-weight:700;color:#c7d3ee;margin:10px 0 4px;letter-spacing:.08em;font-size:10px">POPULATION</div>
      ${row("popTotal", "Overall population")}
      <div style="font-size:9px;margin:8px 0 3px;color:#8195b8;letter-spacing:.08em">CYCLONE OVERLAY</div>
      ${row("cycloneAoe", "R34 wind field")}
      <div class="hint">translucent 34-kt radius · off = track and eye only</div>
      <div style="font-size:9px;margin:8px 0 3px;color:#8195b8;letter-spacing:.08em">HAZARDS · replay clock</div>
      <div class="hint">flood / fire / contamination follow the replay clock — no layer checkboxes</div>
      <div style="font-size:9px;margin-top:6px;opacity:.7">Forecast population: disabled</div>`;
    el.querySelectorAll("input").forEach((inp) => {
      inp.addEventListener("change", () => { flags[inp.id] = inp.checked; redraw(); });
    });
  }

  function stopReplay() {
    replayPlaying = false;
    if (replayTimer) {
      clearInterval(replayTimer);
      replayTimer = null;
    }
  }
  function toggleReplay() {
    if (replayPlaying) {
      stopReplay();
      renderTimeline();
      return;
    }
    beliefPinned = false;
    const last = replayEvents().length - 1;
    if (replayIdx >= last) applyReplayIndex(0);
    replayPlaying = true;
    replayTimer = setInterval(() => {
      const end = replayEvents().length - 1;
      if (replayIdx >= end) {
        stopReplay();
        renderTimeline();
        return;
      }
      applyReplayIndex(replayIdx + 1);
    }, REPLAY_STEP_MS);
    renderTimeline();
  }
  function syncEventSubject() {
    if (beliefPinned || !snap) return;
    const ids = [...tickBindIds()];
    if (!ids.length) return;
    const world = applyLandfall(snap);
    const ent = world.entities.find((e) => e.entity_id === ids[0]);
    if (ent) selected = ent;
  }
  function applyReplayIndex(i) {
    const events = replayEvents();
    if (!events.length) return;
    replayIdx = Math.max(0, Math.min(i, events.length - 1));
    playTickAt = performance.now();
    heatJoin = { idx: -1, inund: [] };
    syncEventSubject();
    if (!beliefPinned) {
      const next = beliefForEvent(events[replayIdx]);
      if (next !== kf) {
        applyKf(next, { fromReplay: true });
        return;
      }
    }
    renderTimeline();
    redraw();
    syncCamera();
  }
  function renderTimeline() {
    const el = document.getElementById("timeline");
    const events = replayEvents();
    const ev = replayEvent();
    const stops = [
      { id: "t0", label: "t0 belief" },
      { id: "b7", label: "B7 collapse" },
      { id: "reroute", label: "R22 approved" },
    ];
    const idx = KEYS.indexOf(kf);
    const n = Math.max(events.length - 1, 1);
    const phases = (script && script.phases) || [];
    el.innerHTML = `
      <div class="tl-split">
        <div>
          <div style="font-size:10px;letter-spacing:.08em;color:#b06bff">REPLAY CLOCK · event script · ${events.length} beats · one tick = one bullet</div>
          <div class="replay-title">${ev ? ev.title : "Loading script…"}</div>
          <div class="replay-meta">${ev ? `${ev.t} · ${ev.id} · ${replayIdx + 1} / ${events.length}` : ""} · ${worldNote()}</div>
          <div class="phase-pills">${phases.map((p) =>
            `<button data-phase="${p.id}" class="${ev && ev.phase === p.id ? "active" : ""}">${PHASE_SHORT[p.id] || p.id}</button>`
          ).join("")}</div>
          <div class="tl-controls">
            <button class="tbtn play ${replayPlaying ? "on" : ""}" data-act="play">${replayPlaying ? "Pause" : "Play"}</button>
            <input class="range" data-act="replay" type="range" min="0" max="${n}" step="1" value="${replayIdx}" />
          </div>
        </div>
        <div>
          <div style="font-size:10px;letter-spacing:.08em;color:#5f7191">BELIEF SNAPSHOTS · pin to freeze landfall patches</div>
          <input class="range" data-act="belief" type="range" min="0" max="2" step="1" value="${idx}" />
          <div class="stops">${stops.map((s) =>
            `<button data-id="${s.id}" class="${s.id === kf ? "active" : ""}">${s.label}</button>`).join("")}</div>
        </div>
      </div>`;
    el.querySelectorAll("[data-phase]").forEach((b) => {
      b.addEventListener("click", () => {
        stopReplay();
        beliefPinned = false;
        applyReplayIndex(indexForPhase(Number(b.getAttribute("data-phase"))));
      });
    });
    const playBtn = el.querySelector("[data-act=play]");
    if (playBtn) playBtn.addEventListener("click", toggleReplay);
    const replayRange = el.querySelector("[data-act=replay]");
    if (replayRange) {
      replayRange.addEventListener("input", (e) => {
        stopReplay();
        beliefPinned = false;
        applyReplayIndex(Number(e.target.value));
      });
    }
    el.querySelectorAll("[data-id]").forEach((b) => {
      b.addEventListener("click", () => applyKf(b.getAttribute("data-id")));
    });
    const beliefRange = el.querySelector("[data-act=belief]");
    if (beliefRange) {
      beliefRange.addEventListener("input", (e) => applyKf(KEYS[Number(e.target.value)]));
    }
  }

  function redraw() {
    if (!overlay || !snap || !map) return;
    overlay.setProps({ layers: buildLayers() });
    renderPulse();
    renderInspector();
    renderLegend();
    const ev = replayEvent();
    document.getElementById("clock").textContent = ev
      ? `${ev.t_label}  ·  ${ev.id}`
      : `${snap.valid_at}  ·  recorded ${snap.recorded_at}`;
    const sub = document.querySelector(".crisis-sub");
    if (sub && ev && script) {
      const phase = (script.phases || []).find((p) => p.id === ev.phase);
      const kind = cameraKind();
      sub.textContent = kind === "gulf"
        ? `Replay · cyclone ${phase ? phase.name : ""}`
        : `Replay · ${ev.title}`;
    }
  }

  function applyKf(id, opts) {
    const fromReplay = opts && opts.fromReplay;
    if (!fromReplay) beliefPinned = true;
    kf = id;
    snap = snaps[id];
    if (selected) selected = snap.entities.find((e) => e.entity_id === selected.entity_id) || selected;
    if (fromReplay) syncEventSubject();
    renderTimeline();
    redraw();
    syncCamera();
  }

  async function main() {
    flags.fallback2d = !webglOk();
    if (flags.fallback2d) document.getElementById("webgl-fail").classList.remove("hidden");
    const [t0, b7, reroute, reg, typeSolids, replayScript, hurdatDoc] = await Promise.all([
      loadSnapshot("t0"), loadSnapshot("b7"), loadSnapshot("reroute"),
      loadJSON("/data/symbol-registry.json"),
      loadJSON("/assets/type-solids.json"),
      loadJSON("/api/replay").catch(() => loadJSON("/data/sourced/katrina_event_script.json")),
      loadJSON("/data/sourced/hurdat2_al122005.json").catch(() => ({ track: [] })),
    ]);
    snaps = { t0, b7, reroute };
    registry = reg;
    solids = typeSolids;
    script = replayScript;
    if (script && script.events) script.events = orderClockEvents(script.events);
    hurdat = hurdatDoc;
    if (script.demo_keyframes && script.demo_keyframes.t0) {
      replayIdx = indexAtTime(script.demo_keyframes.t0);
    }
    snap = t0;
    document.getElementById("exag-badge").textContent = "basemap: Esri imagery · modern (Twin Span 2011)";
    const [w, s, e, n] = snap.viz.hero_region_bounds;
    map = new maplibregl.Map({
      container: "map",
      style: {
        version: 8,
        sources: {
          esri: {
            type: "raster",
            tiles: ["https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"],
            tileSize: 256,
            attribution: "Tiles © Esri — Source: Esri, Maxar, Earthstar Geographics. Modern imagery; the Twin Span on this map is the 2011 rebuild.",
            maxzoom: 17,
          },
        },
        layers: [{ id: "esri", type: "raster", source: "esri" }],
      },
      center: [-90.05, 29.975],
      zoom: 11.4, pitch: snap.viz.camera_tilt_degrees, bearing: -18,
      maxBounds: [w - 0.15, s - 0.1, e + 0.15, n + 0.1],
      attributionControl: true,
    });
    map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "bottom-right");
    if (!OverlayCtor) {
      throw new Error("deck.gl MapboxOverlay missing — cannot attach to MapLibre");
    }
    overlay = new OverlayCtor({ interleaved: false, layers: [] });
    map.addControl(overlay);
    map.on("load", () => {
      renderPopCtl();
      applyKf("t0", { fromReplay: true });
      setInterval(() => {
        if (!overlay || !snap) return;
        let tick = false;
        if (replayPlaying) tick = true;
        if (flags.opEvacuate) {
          const moves = ((applyLandfall(snap).population || {}).movement || []);
          if (moves.length) {
            flowT = (flowT + 0.008) % 1;
            tick = true;
          }
        }
        if (fieldOn("fire") && snap.hazards.fire && snap.hazards.fire.active) {
          fireT = (fireT + 0.03) % 1;
          tick = true;
        }
        if (tick) overlay.setProps({ layers: buildLayers() });
      }, 80);
    });
    map.on("moveend", redraw);
    map.on("zoomend", redraw);
  }

  main().catch((err) => {
    console.error(err);
    document.getElementById("inspector").textContent = String(err);
  });
})();
