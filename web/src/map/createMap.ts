import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import type { WorldSnapshot } from "../state/types";

export function createMap(container: HTMLElement, snap: WorldSnapshot): maplibregl.Map {
  const [w, s, e, n] = snap.viz.hero_region_bounds;
  const pitch = snap.viz.camera_tilt_degrees;

  const map = new maplibregl.Map({
    container,
    style: {
      version: 8,
      sources: {
        esri: {
          type: "raster",
          tiles: ["https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"],
          tileSize: 256,
          attribution: "Tiles © Esri — Source: Esri, Maxar, Earthstar Geographics. Modern imagery; Twin Span on this map is the 2011 rebuild.",
          maxzoom: 19,
        },
      },
      layers: [{ id: "esri", type: "raster", source: "esri" }],
    } as maplibregl.StyleSpecification,
    center: [-90.05, 29.975],
    zoom: 11.4,
    pitch,
    bearing: -18,
    maxBounds: [w - 0.15, s - 0.1, e + 0.15, n + 0.1],
    attributionControl: true,
  });

  map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "bottom-right");
  return map;
}

export function cameraAltitudeM(map: maplibregl.Map): number {
  const c = map.getCenter();
  const p = map.project(c);
  const earth = map.unproject([p.x, p.y - 1]);
  const dLat = Math.abs(earth.lat - c.lat);
  const metersPerPx = (dLat * 111320) || 1;
  return metersPerPx * 400;
}
