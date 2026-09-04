/* Crisis OS diorama — pure read of WorldSnapshot JSON. CDN deck.gl + MapLibre. */
(() => {
  const KEYS = ["t0", "b7", "reroute"];
  const STATE_COLOR = {
    operational: [55, 214, 122], full: [55, 214, 122],
    uncertain: [255, 176, 32], damaged: [255, 176, 32],
    critical: [255, 89, 100], inaccessible: [255, 89, 100], depleted: [255, 89, 100],
  };
  const SEG_COLOR = {
    open: [55, 214, 122, 220], degraded: [255, 176, 32, 220],
    blocked: [255, 89, 100, 255], submerged: [40, 90, 180, 180],
  };
  const EVENT_GLYPH = {
    infrastructure_damage: "✕", road_closure: "╪", displacement: "→",
    service_interruption: "⚡", supply_shortage: "▽", facility_closure: "▣",
    security_event: "·", hazard_expansion: "◎",
  };
  const CAT_PLATE = {
    transport: [16, 36, 72, 230],
    health: [72, 22, 32, 230],
    humanitarian: [32, 52, 28, 230],
    utilities: [16, 52, 72, 230],
    hazard: [72, 28, 16, 230],
    supply: [56, 42, 18, 230],
    geography: [28, 32, 48, 230],
    other: [8, 14, 28, 230],
  };
  const CAT_ORDER = ["transport", "health", "humanitarian", "utilities", "supply", "hazard", "geography"];
  const STOCK_TYPES = new Set(["warehouse", "food", "medicine", "fuel", "water"]);
  const OCCUPANCY_TYPES = new Set(["shelter", "camp"]);
  const OP_REALLOC = new Set(["warehouse", "vehicle", "food", "fuel", "medicine", "water", "port"]);
  const OP_EVACUATE = new Set(["shelter", "camp", "zone", "personnel", "hospital", "clinic", "school"]);
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

  function mToLonLat(lon, lat, x, z) {
    const mLat = 1 / 110570;
    const mLon = 1 / (111320 * Math.max(0.2, Math.cos(lat * Math.PI / 180)));
    return [lon + x * mLon, lat + z * mLat];
  }
  function rotateXZ(x, z, headingDeg) {
    const theta = (90 - headingDeg) * Math.PI / 180;
    const c = Math.cos(theta), s = Math.sin(theta);
    return [x * c - z * s, x * s + z * c];
  }
  function pointInRing(lon, lat, ring) {
    let inside = false;
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      const xi = ring[i][0], yi = ring[i][1], xj = ring[j][0], yj = ring[j][1];
      const denom = (yj - yi) || 1e-12;
      if ((yi > lat) !== (yj > lat) && lon < ((xj - xi) * (lat - yi)) / denom + xi) inside = !inside;
    }
    return inside;
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
    if (type === "bridge") return 14;
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
      Math.round(base[0] * 0.5 + stateRgb[0] * 0.5),
      Math.round(base[1] * 0.5 + stateRgb[1] * 0.5),
      Math.round(base[2] * 0.5 + stateRgb[2] * 0.5),
      alpha,
    ];
  }
  function fillRatio(ent) {
    const a = ent.attributes || {};
    if (a.capacity > 0 && a.stock != null) return Math.max(0, Math.min(1, a.stock / a.capacity));
    if (a.capacity > 0 && a.occupancy != null) return Math.max(0, Math.min(1, a.occupancy / a.capacity));
    return null;
  }
  function entitySolids(entities) {
    const rows = [];
    const fills = [];
    for (const ent of entities) {
      const key = solidKey(ent);
      const cat = key && solids[key];
      if (!cat) continue;
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
    const [w, s, e, n] = snap.viz.hero_region_bounds;

    layers.push(new PolygonLayer({
      id: "hero-mask", data: [{ polygon: [[w, s], [e, s], [e, n], [w, n], [w, s]] }],
      getPolygon: (d) => d.polygon, stroked: true, filled: false,
      getLineColor: [124, 156, 255, 90], lineWidthMinPixels: 1,
    }));

    if (flags.opEvacuate) {
      const zonePolys = Object.entries(snap.zone_rings).map(([id, ring]) => {
        const ent = entities.find((x) => x.entity_id === id);
        const cells = snap.population.cells.filter((c) => pointInRing(c.lon, c.lat, ring));
        const dens = cells.length
          ? cells.reduce((s, c) => s + c.density, 0) / cells.length
          : (ent?.attributes?.population || 0) / 2;
        return { id, ring, entity: ent, dens };
      });
      layers.push(new PolygonLayer({
        id: "zones", data: zonePolys, getPolygon: (d) => d.ring, stroked: true, filled: true,
        getFillColor: (d) => densColor(d.dens, snap.population.bin_edges_per_km2, 22),
        getLineColor: [232, 238, 252, 200], lineWidthMinPixels: 2,
        pickable: true,
        onClick: (info) => { if (info.object?.entity) onClickEntity(info.object.entity); },
      }));
    }

    if (flags.opEvacuate) {
      layers.push(new ScatterplotLayer({
        id: "pop-displaced", data: snap.population.cells.filter((c) => c.displaced > 0),
        getPosition: (c) => [c.lon, c.lat],
        getRadius: 80,
        getFillColor: [176, 107, 255, 90], radiusUnits: "meters",
      }));
    }
    if (flags.opEvacuate && snap.population.movement.length && ArcLayer) {
      layers.push(new ArcLayer({
        id: "pop-move", data: snap.population.movement,
        getSourcePosition: (m) => m.from, getTargetPosition: (m) => m.to,
        getSourceColor: [180, 180, 200, 40], getTargetColor: [176, 107, 255, 200],
        getWidth: (m) => 2 + m.magnitude * 6,
      }));
    }

    const flood = snap.hazards.flood;
    const floodPolys = (flood.wet_mask.coordinates || []).map((poly) => ({
      polygon: poly[0],
      elevation: (flags.fallback2d || flags.popTotal) ? 0 : Math.max(1.2, flood.stage_m * 1.4),
    }));
    const floodAlpha = flags.popTotal
      ? Math.min(110, 40 + Math.abs(flood.d_stage_dt) * 180)
      : Math.min(170, 50 + Math.abs(flood.d_stage_dt) * 350);
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
      layers.push(new PathLayer({
        id: "osm-roads", data: geo.roads,
        getPath: (x) => x.path,
        getColor: (x) => SEG_COLOR[x.state] || [230, 230, 220, 180],
        getWidth: (x) => roadW(x.highway),
        widthMinPixels: 1.5,
        capRounded: true, jointRounded: true,
      }));
    }
    layers.push(new SolidPolygonLayer({
      id: "flood", data: floodPolys, getPolygon: (d) => d.polygon,
      extruded: !flags.fallback2d && !flags.popTotal,
      getElevation: (d) => d.elevation,
      getFillColor: [30, 90, 180, floodAlpha],
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
        getWidth: 14, widthMinPixels: 4,
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
      getBackgroundColor: (e) => CAT_PLATE[catOf(e)] || CAT_PLATE.other,
      backgroundPadding: [6, 3, 6, 3],
      getBorderColor: [200, 214, 240, 40],
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
         <div style="margin-top:4px">flood volume = stage ${snap.hazards.flood.stage_m} m · Δ ${snap.hazards.flood.d_stage_dt}</div>
         <div style="margin-top:4px;opacity:.8">${(snap.geography && snap.geography.vintage) || ""}</div>`
      : `<div>two operations · realloc (stock) · evacuate (occupancy / displacement)</div>
         <div>access (bridges, roads, breaches) is a shared constraint — drawn with either operation</div>
         <div>operational green · uncertain amber · inaccessible red</div>
         <div>unverified ping is grey — entity colour unchanged</div>
         <div style="margin-top:6px;color:#c7d3ee">ENTITY SYMBOLS</div>
         ${typeLegendHtml()}`;
  }

  function renderPopCtl() {
    const el = document.getElementById("popctl");
    const row = (id, label) => `<label><input type="checkbox" id="${id}" ${flags[id] ? "checked" : ""}/> ${label}</label>`;
    el.innerHTML = `<div style="font-weight:700;color:#c7d3ee;letter-spacing:.08em;font-size:10px">OPERATIONS</div>
      ${row("opRealloc", "Resource reallocation")}
      <div class="hint">W1 · convoy 17 · PODs · fuel · medicine · water · port</div>
      ${row("opEvacuate", "Evacuation")}
      <div class="hint">shelters · camp · hospitals · zones · displacement</div>
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
    });
    map.on("moveend", redraw);
    map.on("zoomend", redraw);
  }

  main().catch((err) => {
    console.error(err);
    document.getElementById("inspector").textContent = String(err);
  });
})();
