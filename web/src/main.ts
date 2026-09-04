import { MapboxOverlay } from "@deck.gl/mapbox";
import { createMap, cameraAltitudeM } from "./map/createMap";
import { buildLayers, type LayerFlags } from "./map/buildLayers";
import { loadAllSnapshots, loadRegistry } from "./state/loadSnapshot";
import type { Entity, KeyframeId, WorldSnapshot } from "./state/types";
import { renderInspector, renderLegend, renderPopCtl, renderPulse, renderTimeline } from "./ui/chrome";

const KEYS: KeyframeId[] = ["t0", "b7", "reroute"];

function webglOk(): boolean {
  try {
    const c = document.createElement("canvas");
    return !!(c.getContext("webgl2") || c.getContext("webgl"));
  } catch {
    return false;
  }
}

async function main(): Promise<void> {
  const fallback = !webglOk();
  if (fallback) document.getElementById("webgl-fail")?.classList.remove("hidden");

  const [snaps, registry] = await Promise.all([loadAllSnapshots(), loadRegistry()]);
  let kf: KeyframeId = "t0";
  let snap: WorldSnapshot = snaps.t0;
  let selected: Entity | null = null;
  let flags: LayerFlags = {
    opRealloc: true, opEvacuate: true,
    popTotal: true,
    cyclone: true, fire: true, landslide: true, fallback2d: fallback,
  };

  const mapEl = document.getElementById("map")!;
  const map = createMap(mapEl, snap);
  document.getElementById("exag-badge")!.textContent =
    "basemap: Esri imagery · modern (Twin Span 2011)";

  const overlay = new MapboxOverlay({ interleaved: true, layers: [] });
  map.addControl(overlay);

  const onClick = (e: Entity | { kind: string; id: string; payload: unknown }) => {
    if ("entity_id" in e) selected = e;
    renderInspector(document.getElementById("inspector")!, snap, selected);
  };

  const redraw = () => {
    const alt = cameraAltitudeM(map);
    overlay.setProps({ layers: buildLayers(snap, registry, flags, alt, onClick) });
    renderPulse(document.getElementById("pulse")!, snap);
    renderInspector(document.getElementById("inspector")!, snap, selected);
    renderLegend(document.getElementById("legend")!, snap, flags);
    const clock = document.getElementById("clock")!;
    clock.textContent = `${snap.valid_at}  ·  recorded ${snap.recorded_at}`;
  };

  const applyKf = (id: KeyframeId) => {
    kf = id;
    snap = snaps[id];
    if (selected) {
      selected = snap.entities.find((e) => e.entity_id === selected!.entity_id) ?? selected;
    }
    renderTimeline(document.getElementById("timeline")!, kf, applyKf, (t) => {
      const i = Math.round(Math.min(2, Math.max(0, t))) as 0 | 1 | 2;
      applyKf(KEYS[i]);
    });
    redraw();
  };

  map.on("load", () => {
    applyKf("t0");
    renderPopCtl(document.getElementById("popctl")!, flags, (f) => { flags = f; redraw(); });
    renderTimeline(document.getElementById("timeline")!, kf, applyKf, (t) => {
      applyKf(KEYS[Math.round(Math.min(2, Math.max(0, t))) as 0 | 1 | 2]);
    });
  });
  map.on("moveend", redraw);
  map.on("zoomend", redraw);
}

main().catch((err) => {
  console.error(err);
  document.getElementById("inspector")!.textContent = String(err);
});
