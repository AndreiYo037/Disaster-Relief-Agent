export type KeyframeId = "t0" | "b7" | "reroute";

export interface Entity {
  entity_id: string;
  type: string;
  name: string;
  geometry: { lon: number; lat: number };
  aliases?: string[];
  state: string;
  confidence: number;
  verification_status: string;
  label?: string;
  attributes: Record<string, unknown>;
  source_event_id: string | null;
  valid_from?: string;
  valid_until?: string | null;
  recorded_at?: string;
  synthetic?: boolean;
}

export interface RouteSegment {
  segment_id: string;
  route_id: string;
  path: [number, number][];
  state: "open" | "degraded" | "blocked" | "submerged";
}

export interface WorldSnapshot {
  schema_version: string;
  crisis_id: string;
  keyframe_id: KeyframeId;
  valid_at: string;
  recorded_at: string;
  entities: Entity[];
  route_segments: RouteSegment[];
  relationships: { from_entity: string; to_entity: string; rel_type: string; active: boolean }[];
  population: {
    bin_edges_per_km2: number[];
    bin_method: string;
    cells: { lon: number; lat: number; density: number; affected: number; displaced: number; count: number }[];
    heat?: { lon: number; lat: number; weight: number; density: number }[];
    movement: { from: number[]; to: number[]; magnitude: number; source: string }[];
    classes: Record<string, Record<string, number>>;
    forecast_enabled: boolean;
  };
  hazards: {
    flood: {
      stage_m: number; d_stage_dt: number;
      wet_mask: {
        coordinates: number[][][][];
        features?: { id: string; ring: number[][]; depth_m: number; wet_frac: number }[];
      };
      gauge_id: string;
    };
    cyclone: { track: { lon: number; lat: number; cat: number }[]; cone_nm: number; rainfall_mm_h: number; ghosted: boolean };
    fire: {
      synthetic: boolean; active: boolean; perimeter: number[][]; spread_rate: number;
      wind: { u: number; v: number }; note: string;
      sites?: { id: string; name: string; lon: number; lat: number; radius_m: number }[];
    };
    contamination?: {
      active: boolean;
      areas: { id: string; name: string; kind: string; lon: number; lat: number; ring: number[][] }[];
      note: string;
    };
    landslide: { synthetic: boolean; active: boolean; path: number[][]; note: string };
  };
  plans: { plan_id: string; status: string; via: string; actions: { qty: number; via: string }[]; equity_ok: boolean }[];
  permits: { permit_id: string; status: string; authorized_route: string; approved_by: string }[];
  tasks: { task_id: string; status: string; vehicle: string; progress: number; route: string }[];
  events: { event_id: string; event_type: string; subject_entity: string; verification_status: string; geometry: { lon: number; lat: number }; decay: number; source_event_id: string }[];
  forecasts: { probability: number; band: string; horizon_hours: number }[];
  pulse: {
    affected: number; shortage_prob: number; band: string; water_hours: number;
    truck_status: string; b7_state: string; data_confidence: number; recommendation_confidence: number;
  };
  viz: {
    vertical_exaggeration: number;
    camera_tilt_degrees: number;
    hero_region_bounds: [number, number, number, number];
    lod_switch_altitude_m: number;
    max_particle_count: number;
    translucency_unverified: number;
    translucency_verified: number;
    saturation_historical: number;
  };
  zone_rings: Record<string, number[][]>;
  route_paths: Record<string, number[][]>;
}

export interface SymbolRegistry {
  types: Record<string, {
    category: string;
    primitive?: string;
    asset_near?: string | null;
    asset_failed?: string;
    symbol_far?: string | null;
    grammar?: string;
  }>;
}

export const STATE_COLOR: Record<string, [number, number, number]> = {
  operational: [46, 204, 96],
  full: [46, 204, 96],
  uncertain: [255, 210, 50],
  damaged: [255, 152, 28],
  critical: [255, 84, 48],
  inaccessible: [220, 36, 48],
  destroyed: [220, 36, 48],
  depleted: [220, 36, 48],
};

export const SEG_COLOR: Record<string, [number, number, number, number]> = {
  open: [55, 214, 122, 150],
  degraded: [255, 196, 0, 255],
  blocked: [255, 40, 56, 255],
  submerged: [56, 176, 255, 255],
};
