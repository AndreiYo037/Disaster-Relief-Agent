import type { Entity, WorldSnapshot } from "../state/types";
import type { LayerFlags } from "../map/buildLayers";
import type { KeyframeId } from "../state/types";

function fmt(n: number, d = 0): string {
  return n.toLocaleString(undefined, { maximumFractionDigits: d });
}

function dash(v: unknown): string {
  if (v === undefined || v === null || v === "") return "—";
  if (typeof v === "number") return fmt(v, v < 10 ? 2 : 0);
  return String(v);
}

export function renderPulse(el: HTMLElement, snap: WorldSnapshot): void {
  const p = snap.pulse;
  const cls = p.band === "CRITICAL" ? "crit" : p.band === "WARNING" ? "warnv" : "";
  el.innerHTML = `
    <h3 class="sec">Crisis pulse</h3>
    <div class="metric ${cls}"><div class="lab">Shortage (zone:B)</div>
      <div class="val">${Math.round(p.shortage_prob * 100)}%</div>
      <div class="lab">${p.band} · ${p.water_hours}h water</div></div>
    <div class="metric"><div class="lab">Affected (class)</div>
      <div class="val">${fmt(p.affected)}</div></div>
    <div class="metric ${p.truck_status === "SUSPENDED" ? "crit" : ""}"><div class="lab">Convoy 17</div>
      <div class="val">${p.truck_status}</div></div>
    <div class="metric ${p.b7_state === "inaccessible" ? "crit" : "warnv"}"><div class="lab">bridge:B7</div>
      <div class="val">${p.b7_state}</div></div>
    <h3 class="sec">Confidence gap</h3>
    <div class="metric"><div class="lab">Data vs recommendation</div>
      <div class="val">${Math.round(p.data_confidence * 100)}% <span class="dash">/</span> ${Math.round(p.recommendation_confidence * 100)}%</div></div>
    <h3 class="sec">Permit</h3>
    <div class="metric"><div class="lab">${snap.permits[0]?.permit_id ?? "—"}</div>
      <div class="val" style="font-size:14px">${snap.permits[0]?.status ?? "—"}</div>
      <div class="lab">${snap.permits[0]?.authorized_route ?? ""} · ${snap.permits[0]?.approved_by ?? ""}</div></div>
  `;
}

export function renderInspector(el: HTMLElement, snap: WorldSnapshot, selected: Entity | null): void {
  if (!selected) {
    el.innerHTML = `<h3 class="sec">Inspector</h3>
      <p class="insp dash">Click an entity. Provenance follows <code>source_event_id</code>.</p>
      <h3 class="sec">Active events</h3>
      ${snap.events.map((ev) => `<div class="insp row"><span>${ev.event_type}</span>
        <span class="tag">${ev.verification_status}</span></div>`).join("")}`;
    return;
  }
  const a = selected.attributes;
  const syn = selected.synthetic ? `<span class="tag syn">synthetic / not Katrina</span>` : "";
  el.innerHTML = `
    <h3 class="sec">${selected.entity_id}</h3>
    <div class="insp"><strong>${selected.name}</strong> ${syn}</div>
    <div class="insp row"><span class="k">type</span><span>${selected.type}</span></div>
    <div class="insp row"><span class="k">state</span><span>${selected.state}</span></div>
    <div class="insp row"><span class="k">verification</span><span>${selected.verification_status}</span></div>
    <div class="insp row"><span class="k">confidence</span><span>${dash(selected.confidence)}</span></div>
    <div class="insp row"><span class="k">population</span><span>${dash(a.population)}</span></div>
    <div class="insp row"><span class="k">stock / cap</span><span>${dash(a.stock)} / ${dash(a.capacity)}</span></div>
    <div class="insp row"><span class="k">occupancy</span><span>${dash(a.occupancy)} / ${dash(a.capacity)}</span></div>
    <div class="insp row"><span class="k">water hours</span><span>${dash(a.water_hours)}</span></div>
    <div class="insp row"><span class="k">stage_m</span><span>${dash(a.stage_m)}</span></div>
    <h3 class="sec">Provenance</h3>
    <div class="prov">source_event_id → <code>${selected.source_event_id ?? "—"}</code><br/>
      valid_from ${selected.valid_from ?? "—"}<br/>recorded_at ${selected.recorded_at ?? snap.recorded_at}</div>
  `;
}

export function renderLegend(el: HTMLElement, snap: WorldSnapshot, flags: LayerFlags): void {
  const e = snap.population.bin_edges_per_km2;
  el.innerHTML = flags.popTotal
    ? `<div>POPULATION DENSITY · people/km² · ${snap.population.bin_method}</div>
       <div>low &lt; ${e[0]} · med ${e[0]}–${e[1]} · high ${e[1]}–${e[2]} · very high &gt; ${e[2]}</div>
       <div style="margin-top:4px">flood volume = stage ${snap.hazards.flood.stage_m} m · Δ ${snap.hazards.flood.d_stage_dt}</div>`
    : `<div>two operations · realloc (stock) · evacuate (occupancy / displacement)</div>
       <div>access (bridges, roads, breaches) is a shared constraint — drawn with either operation</div>
       <div>operational green · uncertain amber · inaccessible red</div>
       <div>unverified ping is grey — entity colour unchanged</div>`;
}

export function renderPopCtl(el: HTMLElement, flags: LayerFlags, onChange: (f: LayerFlags) => void): void {
  el.innerHTML = `<div style="font-weight:700;color:#c7d3ee;letter-spacing:.08em;font-size:10px">OPERATIONS</div>
    ${chk("opRealloc", "Resource reallocation", flags)}
    <div class="hint">W1 · convoy 17 · PODs · fuel · medicine · water · port</div>
    ${chk("opEvacuate", "Evacuation", flags)}
    <div class="hint">shelters · camp · hospitals · zones · displacement</div>
    <div class="hint" style="margin:8px 0 2px 0">Access (B7, roads, breaches, pumps) is a constraint on both — not its own operation.</div>
    <div style="font-weight:700;color:#c7d3ee;margin:10px 0 4px;letter-spacing:.08em;font-size:10px">POPULATION</div>
    ${chk("popTotal", "Overall population", flags)}
    <div style="font-size:9px;margin:8px 0 3px;color:#8195b8;letter-spacing:.08em">HAZARDS</div>
    ${chk("cyclone", "Cyclone (ghosted)", flags)}
    ${chk("fire", "Fire (synthetic)", flags)}
    ${chk("landslide", "Landslide (synthetic)", flags)}
    <div style="font-size:9px;margin-top:6px;opacity:.7">Forecast population: disabled</div>`;
  el.querySelectorAll("input").forEach((inp) => {
    inp.addEventListener("change", () => {
      const next = { ...flags };
      next[inp.id as keyof LayerFlags] = (inp as HTMLInputElement).checked;
      onChange(next);
    });
  });
}

function chk(id: string, label: string, flags: LayerFlags): string {
  const on = flags[id as keyof LayerFlags] ? "checked" : "";
  return `<label><input type="checkbox" id="${id}" ${on}/> ${label}</label>`;
}

export function renderTimeline(
  el: HTMLElement,
  current: KeyframeId,
  onPick: (id: KeyframeId) => void,
  onScrub: (t: number) => void,
): void {
  const stops: { id: KeyframeId; label: string }[] = [
    { id: "t0", label: "t0 belief" },
    { id: "b7", label: "B7 collapse" },
    { id: "reroute", label: "R22 approved" },
  ];
  const idx = stops.findIndex((s) => s.id === current);
  el.innerHTML = `
    <div style="font-size:10px;letter-spacing:.08em;color:#5f7191">TIMELINE · discrete state snaps at keyframes</div>
    <input class="range" type="range" min="0" max="2" step="0.01" value="${idx}" />
    <div class="stops">${stops.map((s) =>
      `<button data-id="${s.id}" class="${s.id === current ? "active" : ""}">${s.label}</button>`).join("")}</div>`;
  el.querySelectorAll("button").forEach((b) => {
    b.addEventListener("click", () => onPick(b.getAttribute("data-id") as KeyframeId));
  });
  el.querySelector("input")?.addEventListener("input", (ev) => {
    onScrub(Number((ev.target as HTMLInputElement).value));
  });
}
