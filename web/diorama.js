/* Crisis OS diorama — pure read of WorldSnapshot JSON. CDN deck.gl + MapLibre. */
(() => {
  const KEYS = ["t0", "b7", "reroute"];
  const STATE_COLOR = {
    operational: [46, 204, 96], full: [46, 204, 96],
    uncertain: [255, 210, 50],
    damaged: [255, 152, 28],
    critical: [255, 84, 48],
    inaccessible: [220, 36, 48], depleted: [220, 36, 48],
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
  let flags = {
    opRealloc: true, opEvacuate: true,
    popTotal: true,
    cyclone: true, fire: false, landslide: false, fallback2d: false,
  };
  let map, overlay;

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
    return e.verification_status === "unverified" ? snap.viz.translucency_unverified : snap.viz.translucency_verified;
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
  function rotateXZ(x, z, headingDeg) {
    const theta = (90 - headingDeg) * Math.PI / 180;
    const c = Math.cos(theta), s = Math.sin(theta);
    return [x * c - z * s, x * s + z * c];
  }
  function solidKey(ent) {
    const t = registry.types[ent.type];
    if (!t || t.primitive !== "mesh") return null;
    if (ent.type === "bridge" && ent.state === "inaccessible") return "bridge.failed";
    if (ent.type === "breach" && (ent.state === "critical" || ent.state === "inaccessible")) return "breach.open";
    return solids[ent.type] ? ent.type : null;
  }
  function typeSymbol(ent) {
    const rec = registry.types[ent.type] || {};
    if (ent.type === "bridge" && ent.state === "inaccessible" && rec.symbol_failed) return rec.symbol_failed;
    if (ent.type === "breach" && (ent.state === "critical" || ent.state === "inaccessible") && rec.symbol_open) {
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
    const ent = snap.entities.find((e) => e.entity_id === ev.subject_entity);
    return ent ? opOn(ent) : true;
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
  function mixColor(base, stateRgb, alpha) {
    return [
      Math.round(base[0] * 0.18 + stateRgb[0] * 0.82),
      Math.round(base[1] * 0.18 + stateRgb[1] * 0.82),
      Math.round(base[2] * 0.18 + stateRgb[2] * 0.82),
      alpha,
    ];
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
      const color = mixColor(cat.color, rgb(ent.state), alpha);
      const pierColor = [
        Math.max(0, color[0] - 28),
        Math.max(0, color[1] - 28),
        Math.max(0, color[2] - 28),
        alpha,
      ];
      const width = ent.attributes.span_width_m || 12;
      const deckH = ent.attributes.deck_h_m || 12;
      const spacing = ent.attributes.pier_spacing_m || 70;
      const failed = ent.state === "inaccessible";
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
      const color = mixColor(cat.color, rgb(ent.state), alpha);
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
    const near = !flags.fallback2d && cameraAltitudeM() < snap.viz.lod_switch_altitude_m;
    const entities = snap.entities.filter((e) => registry.types[e.type] && opOn(e));

    if (flags.opEvacuate) {
      layers.push(new ScatterplotLayer({
        id: "pop-displaced", data: snap.population.cells.filter((c) => c.displaced > 0),
        getPosition: (c) => [c.lon, c.lat],
        getRadius: 80,
        getFillColor: [255, 140, 50, 55], radiusUnits: "meters",
      }));
    }
    if (flags.opEvacuate && snap.population.movement.length && ArcLayer) {
      const pulse = 0.5 + 0.5 * Math.sin(performance.now() / 420);
      const glow = Math.round(120 + pulse * 135);
      layers.push(new ArcLayer({
        id: "pop-move-glow", data: snap.population.movement,
        getSourcePosition: (m) => m.from, getTargetPosition: (m) => m.to,
        getSourceColor: [255, 40, 0, Math.round(40 + pulse * 70)],
        getTargetColor: [255, 80, 0, Math.round(50 + pulse * 80)],
        getWidth: (m) => (14 + m.magnitude * 10) * (0.85 + pulse * 0.5),
        getHeight: EVAC_ARC_HEIGHT,
        greatCircle: false,
        widthMinPixels: 10,
      }));
      layers.push(new ArcLayer({
        id: "pop-move", data: snap.population.movement,
        getSourcePosition: (m) => m.from, getTargetPosition: (m) => m.to,
        getSourceColor: [255, 220, 40, glow],
        getTargetColor: [255, 60, 0, glow],
        getWidth: (m) => (5 + m.magnitude * 6) * (0.8 + pulse * 0.55),
        getHeight: EVAC_ARC_HEIGHT,
        greatCircle: false,
        widthMinPixels: 5,
      }));
      const arrows = evacArcArrows(snap.population.movement, flowT);
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

    const flood = snap.hazards.flood;
    const mask = flood.wet_mask || {};
    const floodFeats = (mask.features && mask.features.length)
      ? mask.features
      : (mask.coordinates || []).map((poly) => ({
        ring: poly[0], depth_m: flood.stage_m, wet_frac: 1,
      }));
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
    const geo = snap.geography || { roads: [], canals: [], buildings: [] };
    const BUILD_COLOR = {
      residential: [210, 200, 185, 200], commercial: [190, 185, 175, 220],
      hospital: [240, 240, 245, 230], warehouse: [150, 130, 110, 220],
      school: [180, 170, 150, 220], landmark: [220, 210, 190, 230],
    };
    if (geo.buildings && geo.buildings.length && SolidPolygonLayer) {
      layers.push(new SolidPolygonLayer({
        id: "osm-buildings",
        data: geo.buildings,
        getPolygon: (d) => d.ring,
        extruded: !flags.fallback2d && !flags.popTotal,
        getElevation: (d) => (flags.fallback2d || flags.popTotal) ? 0 : d.height_m,
        getFillColor: (d) => {
          const c = BUILD_COLOR[d.kind] || BUILD_COLOR.residential;
          return flags.popTotal ? [c[0], c[1], c[2], 70] : c;
        },
        getLineColor: [40, 40, 40, 80],
        lineWidthMinPixels: 0.3,
      }));
    }
    if (geo.roads && geo.roads.length) {
      const roadW = (hw) => (hw && hw.startsWith("motorway") ? 7 : hw && hw.startsWith("trunk") ? 5 : 3);
      const openRoads = geo.roads.filter((x) => x.state === "open" || !x.state);
      layers.push(new PathLayer({
        id: "osm-roads", data: openRoads,
        getPath: (x) => x.path,
        getColor: SEG_COLOR.open,
        getWidth: (x) => roadW(x.highway),
        widthMinPixels: 1.2,
        capRounded: true, jointRounded: true,
      }));
    }
    layers.push(new SolidPolygonLayer({
      id: "flood", data: floodPolys, getPolygon: (d) => d.polygon,
      extruded: !flags.fallback2d && !flags.popTotal,
      getElevation: (d) => d.elevation,
      getFillColor: (d) => [30, 90, 180, d.alpha],
    }));
    if (flags.popTotal) {
      const heat = (snap.population.heat && snap.population.heat.length)
        ? snap.population.heat
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
          getFillColor: (p) => densColor(p.density, snap.population.bin_edges_per_km2, 160),
          radiusUnits: "meters",
        }));
      }
    }

    const geoRoads = (snap.geography && snap.geography.roads) || [];
    const submergedRoads = geoRoads.filter((x) => x.state === "submerged");
    const shutRoads = geoRoads.filter((x) => x.state === "degraded" || x.state === "blocked");
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

    const permit = snap.permits[0];
    const plan = snap.plans[0];
    const solidRoute = flags.opRealloc && permit?.status === "active" ? permit.authorized_route : null;
    const ghostRoute = flags.opRealloc && plan && permit?.status !== "active" ? plan.via : null;

    if (flags.opRealloc) {
      layers.push(new PathLayer({
        id: "segments", data: snap.route_segments,
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
      if (ghostRoute && snap.route_paths[ghostRoute] && ghostRoute !== solidRoute) {
        layers.push(new PathLayer({
          id: "ghost-plan", data: [{ path: snap.route_paths[ghostRoute] }],
          getPath: (d) => d.path, getColor: [180, 190, 220, 120], getWidth: 5, widthMinPixels: 2,
        }));
      }
      if (solidRoute && snap.route_paths[solidRoute]) {
        layers.push(new PathLayer({
          id: "solid-permit", data: [{ path: snap.route_paths[solidRoute] }],
          getPath: (d) => d.path, getColor: [55, 214, 122, 240], getWidth: 10, widthMinPixels: 4,
        }));
      }
    }

    if (flags.cyclone) {
      const track = snap.hazards.cyclone.track.map((p) => [p.lon, p.lat]);
      layers.push(new PathLayer({
        id: "cyclone-track", data: [{ path: track }], getPath: (d) => d.path,
        getColor: [176, 107, 255, 140], getWidth: 4, widthMinPixels: 2,
      }));
      const mid = snap.hazards.cyclone.track[Math.floor(snap.hazards.cyclone.track.length / 2)];
      layers.push(new ScatterplotLayer({
        id: "cyclone-cone", data: [mid], getPosition: (p) => [p.lon, p.lat],
        getRadius: snap.hazards.cyclone.cone_nm * 0.012 * 111000,
        getFillColor: [176, 107, 255, 25], getLineColor: [176, 107, 255, 80],
        stroked: true, filled: true, radiusUnits: "meters",
      }));
      const rainN = Math.min(snap.viz.max_particle_count / 4, Math.round(snap.hazards.cyclone.rainfall_mm_h * 80));
      if (snap.hazards.cyclone.rainfall_mm_h > 0) {
        const rain = Array.from({ length: rainN }, (_, i) => ({
          lon: -90.3 + (i % 40) * 0.018, lat: 29.85 + Math.floor(i / 40) * 0.018,
        }));
        layers.push(new ScatterplotLayer({
          id: "rain", data: rain, getPosition: (p) => [p.lon, p.lat],
          getRadius: 40, getFillColor: [140, 180, 255, 40], radiusUnits: "meters",
        }));
      }
    }

    if (flags.fire && snap.hazards.fire.active && snap.hazards.fire.spread_rate > 0) {
      layers.push(new PolygonLayer({
        id: "fire", data: [{ polygon: snap.hazards.fire.perimeter }],
        getPolygon: (d) => d.polygon, getFillColor: [255, 80, 20, 160], getLineColor: [255, 160, 40, 220],
      }));
      const { u, v } = snap.hazards.fire.wind;
      const origin = snap.hazards.fire.perimeter[0];
      const smokeN = Math.min(400, Math.round(snap.hazards.fire.spread_rate * 400));
      const smoke = Array.from({ length: smokeN }, (_, i) => ({
        lon: origin[0] + u * 0.002 * (i / smokeN),
        lat: origin[1] + v * 0.002 * (i / smokeN),
      }));
      layers.push(new ScatterplotLayer({
        id: "smoke", data: smoke, getPosition: (p) => [p.lon, p.lat],
        getRadius: 90, getFillColor: [80, 80, 80, 50], radiusUnits: "meters",
      }));
      const core = snap.hazards.fire.perimeter.reduce((a, p) => [a[0] + p[0], a[1] + p[1]], [0, 0]);
      const n = snap.hazards.fire.perimeter.length;
      layers.push(new ScatterplotLayer({
        id: "fire-core", data: [{ lon: core[0] / n, lat: core[1] / n }],
        getPosition: (p) => [p.lon, p.lat], getRadius: 70,
        getFillColor: [255, 90, 20, 240], radiusUnits: "meters",
      }));
    }
    if (flags.landslide && snap.hazards.landslide.active) {
      layers.push(new PathLayer({
        id: "landslide", data: [{ path: snap.hazards.landslide.path }],
        getPath: (d) => d.path, getColor: [120, 80, 40, 220], getWidth: 14, widthMinPixels: 4,
      }));
    }

    const placed = entities.filter((e) => registry.types[e.type]?.primitive === "mesh");
    const { rows, fills } = entitySolids(placed);
    const pickEnt = (info) => { if (info.object?.entity) onClickEntity(info.object.entity); };
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
      && e.type !== "route" && e.type !== "route_segment");
    layers.push(new TextLayer({
      id: "entity-names",
      data: named,
      getPosition: (e) => [e.geometry.lon, e.geometry.lat],
      getText: (e) => `${typeSymbol(e)}  ${e.name}`,
      getSize: 9,
      getColor: [244, 247, 252, 255],
      billboard: true,
      getPixelOffset: [0, -26],
      fontFamily: "Inter, system-ui, sans-serif",
      fontWeight: 600,
      getTextAnchor: "middle",
      getAlignmentBaseline: "bottom",
      background: true,
      getBackgroundColor: (e) => statePlate(e.state),
      backgroundPadding: [6, 3, 6, 3],
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
        getSize: 8,
        getColor: (e) => STOCK_TYPES.has(e.type) ? [160, 245, 220, 255] : [220, 200, 255, 255],
        billboard: true, getPixelOffset: [0, 14],
        fontFamily: "Inter, system-ui, sans-serif",
        fontWeight: 600,
        ...textPlate((e) => STOCK_TYPES.has(e.type) ? [6, 18, 16, 230] : [28, 16, 48, 230], [5, 2, 5, 2]),
      }));
    }

    const truck = placed.find((e) => e.entity_id === "truck:17");
    if (truck && snap.tasks[0]?.status === "SUSPENDED") {
      layers.push(new ScatterplotLayer({
        id: "truck-suspend", data: [truck],
        getPosition: (e) => [e.geometry.lon, e.geometry.lat], getRadius: 280,
        getFillColor: [255, 89, 100, 35], getLineColor: [255, 89, 100, 220],
        stroked: true, filled: true, radiusUnits: "meters",
      }));
    }

    const events = snap.events.filter(eventOn);
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
      ...textPlate((ev) => ev.verification_status === "unverified"
        ? [28, 30, 38, 230]
        : [48, 12, 18, 230], [6, 3, 6, 3]),
    }));
    return layers;
  }

  function renderPulse() {
    const p = snap.pulse;
    const cls = p.band === "CRITICAL" ? "crit" : p.band === "WARNING" ? "warnv" : "";
    document.getElementById("pulse").innerHTML = `
      <h3 class="sec">Crisis pulse</h3>
      <div class="metric ${cls}"><div class="lab">Shortage (zone:B)</div>
        <div class="val">${Math.round(p.shortage_prob * 100)}%</div>
        <div class="lab">${p.band} · ${p.water_hours}h water</div></div>
      <div class="metric"><div class="lab">Affected (class)</div><div class="val">${fmt(p.affected)}</div></div>
      <div class="metric ${p.truck_status === "SUSPENDED" ? "crit" : ""}"><div class="lab">Convoy 17</div>
        <div class="val">${p.truck_status}</div></div>
      <div class="metric ${p.b7_state === "inaccessible" ? "crit" : "warnv"}"><div class="lab">bridge:B7</div>
        <div class="val">${p.b7_state}</div></div>
      <h3 class="sec">Confidence gap</h3>
      <div class="metric"><div class="lab">Data vs recommendation</div>
        <div class="val">${Math.round(p.data_confidence * 100)}% / ${Math.round(p.recommendation_confidence * 100)}%</div></div>
      <h3 class="sec">Permit</h3>
      <div class="metric"><div class="lab">${snap.permits[0]?.permit_id || "—"}</div>
        <div class="val" style="font-size:14px">${snap.permits[0]?.status || "—"}</div>
        <div class="lab">${snap.permits[0]?.authorized_route || ""} · ${snap.permits[0]?.approved_by || ""}</div></div>`;
  }

  function renderInspector() {
    const el = document.getElementById("inspector");
    if (!selected) {
      el.innerHTML = `<h3 class="sec">Inspector</h3>
        <p class="insp dash">Click an entity. Provenance follows source_event_id.</p>
        <h3 class="sec">Active events</h3>
        ${snap.events.filter(eventOn).map((ev) => `<div class="insp row"><span>${ev.event_type}</span>
          <span class="tag">${ev.verification_status}</span></div>`).join("")}`;
      return;
    }
    const a = selected.attributes || {};
    const syn = selected.synthetic ? `<span class="tag syn">synthetic / not Katrina</span>` : "";
    el.innerHTML = `
      <h3 class="sec">${selected.entity_id}</h3>
      <div class="insp"><strong>${selected.name}</strong> ${syn}</div>
      <div class="insp row"><span class="k">type</span><span>${typeSymbol(selected)} ${selected.type}</span></div>
      <div class="insp row"><span class="k">operation</span><span>${OP_LABEL[opOf(selected)]}</span></div>
      <div class="insp row"><span class="k">category</span><span>${catOf(selected)}</span></div>
      <div class="insp row"><span class="k">state</span><span>${selected.state}</span></div>
      <div class="insp row"><span class="k">verification</span><span>${selected.verification_status}</span></div>
      <div class="insp row"><span class="k">confidence</span><span>${dash(selected.confidence)}</span></div>
      <div class="insp row"><span class="k">population</span><span>${dash(a.population)}</span></div>
      <div class="insp row"><span class="k">stock / cap</span><span>${dash(a.stock)} / ${dash(a.capacity)}</span></div>
      <div class="insp row"><span class="k">occupancy</span><span>${dash(a.occupancy)} / ${dash(a.capacity)}</span></div>
      <div class="insp row"><span class="k">water hours</span><span>${dash(a.water_hours)}</span></div>
      <div class="insp row"><span class="k">stage_m</span><span>${dash(a.stage_m)}</span></div>
      <h3 class="sec">Provenance</h3>
      <div class="prov">source_event_id → <code>${selected.source_event_id || "—"}</code><br/>
        valid_from ${selected.valid_from || "—"}<br/>recorded_at ${selected.recorded_at || snap.recorded_at}</div>`;
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
    const e = snap.population.bin_edges_per_km2;
    document.getElementById("legend").innerHTML = flags.popTotal
      ? `<div>POPULATION DENSITY · people/km² · ${snap.population.bin_method}</div>
         <div>sampled on OSM buildings + land roads (basemap fabric) · low &lt; ${e[0]} · med ${e[0]}–${e[1]} · high ${e[1]}–${e[2]} · very high &gt; ${e[2]}</div>
         <div style="margin-top:4px">evac movement = pulsing orange arcs · slow arrows Lower 9 → Dome / Convention Center</div>
         <div style="margin-top:4px">roads: open green · degraded amber · blocked red · submerged blue</div>
         <div style="margin-top:4px">flood = HUD district depth × flooded-unit share · city stage ${snap.hazards.flood.stage_m} m · Δ ${snap.hazards.flood.d_stage_dt}</div>
         <div style="margin-top:4px;opacity:.8">${(snap.geography && snap.geography.vintage) || ""}</div>`
      : `<div>two operations · realloc (stock) · evacuate (occupancy / displacement)</div>
         <div>access (bridges, roads, breaches) is a shared constraint — drawn with either operation</div>
         <div>roads: open green · degraded amber · blocked red · submerged blue</div>
         <div>evac movement = pulsing orange arcs</div>
         <div>label plate = damage · green undamaged · yellow unknown · orange damaged · red destroyed</div>
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
      <div style="font-size:9px;margin:8px 0 3px;color:#8195b8;letter-spacing:.08em">HAZARDS</div>
      ${row("cyclone", "Cyclone (ghosted)")}
      ${row("fire", "Fire (synthetic)")}
      ${row("landslide", "Landslide (synthetic)")}
      <div style="font-size:9px;margin-top:6px;opacity:.7">Forecast population: disabled</div>`;
    el.querySelectorAll("input").forEach((inp) => {
      inp.addEventListener("change", () => { flags[inp.id] = inp.checked; redraw(); });
    });
  }

  function renderTimeline() {
    const el = document.getElementById("timeline");
    const stops = [
      { id: "t0", label: "t0 belief" },
      { id: "b7", label: "B7 collapse" },
      { id: "reroute", label: "R22 approved" },
    ];
    const idx = KEYS.indexOf(kf);
    el.innerHTML = `
      <div style="font-size:10px;letter-spacing:.08em;color:#5f7191">TIMELINE · discrete state snaps at keyframes</div>
      <input class="range" type="range" min="0" max="2" step="1" value="${idx}" />
      <div class="stops">${stops.map((s) =>
        `<button data-id="${s.id}" class="${s.id === kf ? "active" : ""}">${s.label}</button>`).join("")}</div>`;
    el.querySelectorAll("button").forEach((b) => {
      b.addEventListener("click", () => applyKf(b.getAttribute("data-id")));
    });
    el.querySelector("input").addEventListener("input", (ev) => applyKf(KEYS[Number(ev.target.value)]));
  }

  function redraw() {
    overlay.setProps({ layers: buildLayers() });
    renderPulse();
    renderInspector();
    renderLegend();
    document.getElementById("clock").textContent = `${snap.valid_at}  ·  recorded ${snap.recorded_at}`;
  }

  function applyKf(id) {
    kf = id;
    snap = snaps[id];
    if (selected) selected = snap.entities.find((e) => e.entity_id === selected.entity_id) || selected;
    renderTimeline();
    redraw();
  }

  async function main() {
    flags.fallback2d = !webglOk();
    if (flags.fallback2d) document.getElementById("webgl-fail").classList.remove("hidden");
    const [t0, b7, reroute, reg, typeSolids] = await Promise.all([
      loadSnapshot("t0"), loadSnapshot("b7"), loadSnapshot("reroute"),
      loadJSON("/data/symbol-registry.json"),
      loadJSON("/assets/type-solids.json"),
    ]);
    snaps = { t0, b7, reroute };
    registry = reg;
    solids = typeSolids;
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
            maxzoom: 19,
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
      applyKf("t0");
      setInterval(() => {
        if (!overlay || !snap) return;
        if (!(flags.opEvacuate && snap.population.movement.length)) return;
        flowT = (flowT + 0.008) % 1;
        overlay.setProps({ layers: buildLayers() });
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
