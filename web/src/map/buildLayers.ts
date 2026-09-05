import { ArcLayer, PathLayer, PolygonLayer, ScatterplotLayer, SolidPolygonLayer, TextLayer } from "@deck.gl/layers";
import { HeatmapLayer } from "@deck.gl/aggregation-layers";
import { ScenegraphLayer } from "@deck.gl/mesh-layers";
import { GLTFLoader } from "@loaders.gl/gltf";
import type { Layer } from "@deck.gl/core";
import type { Entity, SymbolRegistry, WorldSnapshot } from "../state/types";
import { SEG_COLOR, STATE_COLOR } from "../state/types";

export interface LayerFlags {
  opRealloc: boolean;
  opEvacuate: boolean;
  popTotal: boolean;
  cyclone: boolean;
  fire: boolean;
  landslide: boolean;
  fallback2d: boolean;
}

const OP_REALLOC = new Set(["warehouse", "vehicle", "food", "fuel", "medicine", "water", "personnel"]);
const OP_EVACUATE = new Set(["shelter", "camp", "zone", "hospital", "clinic", "school"]);

function opOf(ent: Entity): "realloc" | "evacuate" | "access" {
  if (OP_REALLOC.has(ent.type)) return "realloc";
  if (OP_EVACUATE.has(ent.type)) return "evacuate";
  return "access";
}

function opOn(ent: Entity, flags: LayerFlags): boolean {
  const op = opOf(ent);
  if (op === "realloc") return flags.opRealloc;
  if (op === "evacuate") return flags.opEvacuate;
  return flags.opRealloc || flags.opEvacuate;
}

function eventOn(ev: { subject_entity?: string }, snap: WorldSnapshot, flags: LayerFlags): boolean {
  if (!ev.subject_entity) return true;
  const ent = snap.entities.find((e) => e.entity_id === ev.subject_entity);
  return ent ? opOn(ent, flags) : true;
}

function rgb(state: string): [number, number, number] {
  return STATE_COLOR[state] ?? [130, 149, 184];
}

function statePlate(state: string): [number, number, number, number] {
  const c = rgb(state);
  return [
    Math.round(c[0] * 0.42 + 6),
    Math.round(c[1] * 0.34 + 6),
    Math.round(c[2] * 0.34 + 6),
    240,
  ];
}

function densityColor(d: number, edges: number[], alpha: number): [number, number, number, number] {
  const t = d <= edges[0] ? 0 : d <= edges[1] ? 0.33 : d <= edges[2] ? 0.66 : 1;
  const r = Math.round(40 + t * 180);
  const g = Math.round(80 + t * 40);
  const b = Math.round(140 - t * 40);
  return [r, g, b, alpha];
}

function beliefAlpha(e: Entity, snap: WorldSnapshot): number {
  if (e.verification_status === "unverified") return snap.viz.translucency_unverified;
  return snap.viz.translucency_verified;
}

function farSymbol(type: string): string {
  const map: Record<string, string> = {
    hospital: "+", clinic: "+", shelter: "⌂", school: "■", power: "⚡", water: "●",
    pump: "◎", breach: "▲", port: "⚓", airport: "✈", comm: "▲", gauge: "│",
    warehouse: "▣", vehicle: "▸", personnel: "☰", food: "▢", medicine: "✚",
    fuel: "⬤", camp: "△", bridge: " dur", fire: "◇", landslide: "◢",
  };
  return map[type] ?? "•";
}

export function buildLayers(
  snap: WorldSnapshot,
  registry: SymbolRegistry,
  flags: LayerFlags,
  altitudeM: number,
  onClick: (e: Entity | { kind: string; id: string; payload: unknown }) => void,
): Layer[] {
  const layers: Layer[] = [];
  const near = !flags.fallback2d && altitudeM < snap.viz.lod_switch_altitude_m;
  const entities = snap.entities.filter((e) => registry.types[e.type] && opOn(e, flags));

  if (flags.popTotal) {
    const heat = snap.population.heat ?? [];
    if (heat.length && !flags.fallback2d) {
      layers.push(new HeatmapLayer({
        id: "pop-total",
        data: heat,
        getPosition: (p: { lon: number; lat: number }) => [p.lon, p.lat],
        getWeight: (p: { weight: number }) => p.weight,
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
      }));
    } else {
      layers.push(new ScatterplotLayer({
        id: "pop-total",
        data: heat,
        getPosition: (p: { lon: number; lat: number }) => [p.lon, p.lat],
        getRadius: 70,
        getFillColor: (p: { density: number }) => densityColor(p.density, snap.population.bin_edges_per_km2, 90),
        radiusUnits: "meters",
        pickable: false,
      }));
    }
  }
  if (flags.opEvacuate) {
    layers.push(new ScatterplotLayer({
      id: "pop-displaced",
      data: snap.population.cells.filter((c) => c.displaced > 0),
      getPosition: (c: { lon: number; lat: number }) => [c.lon, c.lat],
      getRadius: 80,
      getFillColor: [255, 140, 50, 55],
      radiusUnits: "meters",
    }));
  }
  if (flags.opEvacuate && snap.population.movement.length) {
    layers.push(new ArcLayer({
      id: "pop-move",
      data: snap.population.movement,
      getSourcePosition: (m: { from: number[] }) => m.from,
      getTargetPosition: (m: { to: number[] }) => m.to,
      getSourceColor: [255, 168, 72, 120],
      getTargetColor: [255, 96, 28, 220],
      getWidth: (m: { magnitude: number }) => 2.2 + m.magnitude * 5,
      getHeight: 0.58,
      greatCircle: false,
      widthMinPixels: 2,
    }));
  }

  const flood = snap.hazards.flood;
  const mask = flood.wet_mask as {
    coordinates?: number[][][][];
    features?: { ring: number[][]; depth_m: number; wet_frac: number }[];
  };
  const floodFeats = mask.features?.length
    ? mask.features
    : (mask.coordinates || []).map((poly) => ({
      ring: poly[0], depth_m: flood.stage_m, wet_frac: 1,
    }));
  const floodPolys = floodFeats.map((d) => {
    const depth = d.depth_m || 0;
    const frac = d.wet_frac == null ? 1 : d.wet_frac;
    return {
      polygon: d.ring,
      elevation: flags.fallback2d ? 0 : Math.max(0.3, depth * (0.25 + 0.75 * frac) * 2.5),
      alpha: Math.round(28 + frac * 155 + Math.min(25, depth * 10)),
    };
  });
  layers.push(new SolidPolygonLayer({
    id: "flood",
    data: floodPolys,
    getPolygon: (d: { polygon: number[][] }) => d.polygon,
    extruded: !flags.fallback2d,
    getElevation: (d: { elevation: number }) => (flags.fallback2d ? 0 : d.elevation),
    getFillColor: (d: { alpha: number }) => [30, 90, 180, d.alpha],
    wireframe: false,
  }));

  const permit = snap.permits[0];
  const plan = snap.plans[0];
  const solidRoute = flags.opRealloc && permit?.status === "active" ? permit.authorized_route : null;
  const ghostRoute = flags.opRealloc && plan && plan.status !== "approved" ? plan.via : (flags.opRealloc && permit?.status !== "active" ? plan?.via : null);

  if (flags.opRealloc) {
    layers.push(new PathLayer({
      id: "segments",
      data: snap.route_segments,
      getPath: (s: { path: number[][] }) => s.path,
      getColor: (s: { state: string; route_id: string }) => {
        if (s.route_id === ghostRoute && s.route_id !== solidRoute) return [180, 180, 200, 90];
        return SEG_COLOR[s.state] ?? [180, 180, 200, 200];
      },
      getWidth: (s: { state: string }) => {
        if (s.state === "blocked" || s.state === "degraded") return 16;
        if (s.state === "submerged") return 6;
        return 8;
      },
      widthMinPixels: 3,
    }));

    if (ghostRoute && snap.route_paths[ghostRoute] && ghostRoute !== solidRoute) {
      layers.push(new PathLayer({
        id: "ghost-plan",
        data: [{ path: snap.route_paths[ghostRoute] }],
        getPath: (d: { path: number[][] }) => d.path,
        getColor: [180, 190, 220, 120],
        getWidth: 5,
        widthMinPixels: 2,
      }));
    }
  }

  if (flags.cyclone) {
    const track = snap.hazards.cyclone.track.map((p) => [p.lon, p.lat]);
    layers.push(new PathLayer({
      id: "cyclone-track",
      data: [{ path: track }],
      getPath: (d: { path: number[][] }) => d.path,
      getColor: [176, 107, 255, 140],
      getWidth: 4,
      widthMinPixels: 2,
    }));
    const cone = snap.hazards.cyclone.cone_nm * 0.012;
    const mid = snap.hazards.cyclone.track[Math.floor(snap.hazards.cyclone.track.length / 2)];
    layers.push(new ScatterplotLayer({
      id: "cyclone-cone",
      data: [mid],
      getPosition: (p: { lon: number; lat: number }) => [p.lon, p.lat],
      getRadius: cone * 111000,
      getFillColor: [176, 107, 255, 25],
      getLineColor: [176, 107, 255, 80],
      stroked: true,
      filled: true,
      radiusUnits: "meters",
    }));
    const rainN = Math.min(snap.viz.max_particle_count / 4, Math.round(snap.hazards.cyclone.rainfall_mm_h * 80));
    const rain = Array.from({ length: rainN }, (_, i) => ({
      lon: -90.3 + (i % 40) * 0.018,
      lat: 29.85 + Math.floor(i / 40) * 0.018,
    }));
    if (snap.hazards.cyclone.rainfall_mm_h > 0) {
      layers.push(new ScatterplotLayer({
        id: "rain",
        data: rain,
        getPosition: (p: { lon: number; lat: number }) => [p.lon, p.lat],
        getRadius: 40,
        getFillColor: [140, 180, 255, 40],
        radiusUnits: "meters",
      }));
    }
  }

  if (flags.fire && snap.hazards.fire.active) {
    layers.push(new PolygonLayer({
      id: "fire",
      data: [{ polygon: snap.hazards.fire.perimeter }],
      getPolygon: (d: { polygon: number[][] }) => d.polygon,
      getFillColor: [255, 80, 20, 160],
      getLineColor: [255, 160, 40, 220],
      extruded: false,
    }));
    const { u, v } = snap.hazards.fire.wind;
    const smokeN = Math.min(400, Math.round(snap.hazards.fire.spread_rate * 400));
    const origin = snap.hazards.fire.perimeter[0];
    const smoke = Array.from({ length: smokeN }, (_, i) => ({
      lon: origin[0] + u * 0.002 * (i / smokeN),
      lat: origin[1] + v * 0.002 * (i / smokeN),
    }));
    layers.push(new ScatterplotLayer({
      id: "smoke",
      data: smoke,
      getPosition: (p: { lon: number; lat: number }) => [p.lon, p.lat],
      getRadius: 90,
      getFillColor: [80, 80, 80, 50],
      radiusUnits: "meters",
    }));
  }

  if (flags.landslide && snap.hazards.landslide.active) {
    layers.push(new PathLayer({
      id: "landslide",
      data: [{ path: snap.hazards.landslide.path }],
      getPath: (d: { path: number[][] }) => d.path,
      getColor: [120, 80, 40, 220],
      getWidth: 14,
      widthMinPixels: 4,
    }));
  }

  const meshTypes = entities.filter((e) => {
    const t = registry.types[e.type];
    return t?.primitive === "mesh" && t.asset_near;
  });
  const far = entities.filter((e) => e.type !== "route" && e.type !== "route_segment" && e.type !== "zone");

  if (near && !flags.fallback2d) {
    const byAsset = new Map<string, Entity[]>();
    for (const e of meshTypes) {
      const t = registry.types[e.type];
      let asset = t.asset_near as string;
      if (e.type === "bridge" && e.state === "inaccessible" && t.asset_failed) asset = t.asset_failed;
      if (e.type === "breach" && e.state === "critical" && t.asset_failed) asset = t.asset_failed;
      if (!byAsset.has(asset)) byAsset.set(asset, []);
      byAsset.get(asset)!.push(e);
    }
    for (const [asset, rows] of byAsset) {
      layers.push(new ScenegraphLayer({
        id: `mesh-${asset}`,
        data: rows,
        scenegraph: asset,
        loaders: [GLTFLoader],
        getPosition: (e: Entity) => [e.geometry.lon, e.geometry.lat, 4],
        getOrientation: [0, 0, 90],
        sizeScale: 1,
        _lighting: "pbr",
        pickable: true,
        onClick: (info: { object?: Entity }) => { if (info.object) onClick(info.object); },
      }));
    }
  }

  layers.push(new ScatterplotLayer({
    id: "entity-dots",
    data: far,
    getPosition: (e: Entity) => [e.geometry.lon, e.geometry.lat],
    getFillColor: (e: Entity) => {
      const c = rgb(e.state);
      const a = Math.round(beliefAlpha(e, snap) * 255);
      return [c[0], c[1], c[2], a];
    },
    getRadius: (e: Entity) => (e.entity_id === "truck:17" && snap.tasks[0]?.status === "SUSPENDED" ? 220 : 90),
    radiusUnits: "meters",
    pickable: true,
    onClick: (info: { object?: Entity }) => { if (info.object) onClick(info.object); },
    updateTriggers: { getRadius: snap.tasks[0]?.status, getFillColor: snap.keyframe_id },
  }));

  if (!near || flags.fallback2d) {
    layers.push(new TextLayer({
      id: "far-labels",
      data: far.filter((e) => ["bridge", "hospital", "warehouse", "vehicle", "shelter", "gauge"].includes(e.type)),
      getPosition: (e: Entity) => [e.geometry.lon, e.geometry.lat],
      getText: (e: Entity) => farSymbol(e.type),
      getSize: 12,
      getColor: [232, 238, 252, 240],
      billboard: true,
      background: true,
      getBackgroundColor: (e: Entity) => statePlate(e.state),
      backgroundPadding: [8, 4, 8, 4],
      getBorderColor: (e: Entity) => {
        const c = rgb(e.state);
        return [c[0], c[1], c[2], 230];
      },
      getBorderWidth: 1,
    }));
  }

  const truck = entities.find((e) => e.entity_id === "truck:17");
  if (truck && snap.tasks[0]?.status === "SUSPENDED") {
    layers.push(new ScatterplotLayer({
      id: "truck-suspend",
      data: [truck],
      getPosition: (e: Entity) => [e.geometry.lon, e.geometry.lat],
      getRadius: 320,
      getFillColor: [255, 89, 100, 40],
      getLineColor: [255, 89, 100, 220],
      stroked: true,
      filled: true,
      radiusUnits: "meters",
    }));
  }

  const events = snap.events.filter((ev) => eventOn(ev, snap, flags));
  const unverified = events.filter((ev) => ev.verification_status === "unverified");
  layers.push(new ScatterplotLayer({
    id: "unverified-ping",
    data: unverified,
    getPosition: (ev: { geometry: { lon: number; lat: number } }) => [ev.geometry.lon, ev.geometry.lat],
    getRadius: 400,
    getFillColor: [180, 180, 190, 30],
    getLineColor: [200, 200, 210, 180],
    stroked: true,
    filled: true,
    radiusUnits: "meters",
  }));
  const verified = events.filter((ev) => ev.verification_status === "verified" && ev.decay > 0.5);
  layers.push(new ScatterplotLayer({
    id: "verified-shock",
    data: verified,
    getPosition: (ev: { geometry: { lon: number; lat: number } }) => [ev.geometry.lon, ev.geometry.lat],
    getRadius: (ev: { decay: number }) => 200 + ev.decay * 500,
    getFillColor: [255, 89, 100, 20],
    getLineColor: [255, 89, 100, 160],
    stroked: true,
    filled: true,
    radiusUnits: "meters",
  }));
  layers.push(new TextLayer({
    id: "event-glyphs",
    data: events,
    getPosition: (ev: { geometry: { lon: number; lat: number } }) => [ev.geometry.lon, ev.geometry.lat],
    getText: (ev: { event_type: string; verification_status: string }) =>
      ev.verification_status === "unverified" ? "?" : "!",
    getSize: 18,
    getColor: (ev: { verification_status: string }) =>
      ev.verification_status === "unverified" ? [232, 238, 252, 240] : [255, 220, 220, 255],
    background: true,
    getBackgroundColor: (ev: { verification_status: string }) =>
      ev.verification_status === "unverified" ? [28, 30, 38, 230] : [48, 12, 18, 230],
    backgroundPadding: [6, 3, 6, 3],
    getBorderColor: [200, 214, 240, 40],
    getBorderWidth: 1,
  }));

  return layers;
}
