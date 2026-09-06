# Katrina 3D world replay — build phases

**Status:** plan of record. Phases A–E are in the live UI. F (chrome / camera polish) is not done.  
**Date:** 2026-09-06.

This is the staged build for turning the existing New Orleans diorama into an event-driven replay. It is **not** a license to paint the compiled event script as verified fact. Each bind still needs a `source_key` in `data/SOURCES.md` before it may change world-model state.

## Goal — persuasive replay demonstration

A key feature is a **simulation / replay mode** that lets users revisit a historical disaster scenario — Hurricane Katrina as an evacuation and resource-allocation situation — and watch the system process incoming information and recommend responses.

The replay is important because it makes the value proposition visible: judges, investors, or humanitarian stakeholders can see how the platform **identifies hazards**, **tracks population movement**, **routes support**, and **proposes dispatch decisions over time**.

v1 prioritises a **persuasive, understandable replay demonstration** over a fully complex live-disaster backend. The three belief snapshots (`t0` / `b7` / `reroute`) stay the logistics product. Replay is an additional clock on the same map.

## Asset-coverage rule (every sequence)

Build assets that are **reflective of the sequence of events**. Checklist: [`asset-definitions.md`](asset-definitions.md).

For **every** hurricane phase (0–6) and **every** replay tick that paints the world (build phases B+):

1. Search **every asset category** on the live map: `transport`, `health`, `humanitarian`, `utilities`, `supply`, catalog `hazard` (breaches), plus always-on fields **flood**, **fire**, **contamination**, **cyclone**, and the **population heatmap**.
2. Refer to the 44 named entities, operation toggles (realloc / evacuate / access), and couplings in the asset definitions. Do not skip a category because the script JSON omitted a bind.
3. If `data/SOURCES.md` already has the fact, bind it.
4. If there is **no information** for that asset in this sequence: look it up (web / primary literature) and either add a `source_key` to `parameters.json` + `SOURCES.md`, or apply a labeled **`design:gap-fill`**. Gap fills are demo state, never verified parameters. Record the gap in the phase category scan — never leave a category unconsidered.
5. Landslide stays off. No `fire:synth` / `landslide:synth`. Do not invent MOTF polygons or people meshes.

Phase A implements the **clock + category scan** only. It does not yet change meshes. Gap-fills start when a later phase actually paints that category.

## What already exists (do not rebuild)

| Piece | Where | Role |
| --- | --- | --- |
| 44 named entities, type meshes, damage spectrum | `catalog.py`, `symbol-registry.json`, `web/diorama.js` | NOLA world at rest |
| Three belief snapshots | `t0` 31 Aug 08:00 · `b7` 29 Aug 06:00 · `reroute` 31 Aug 09:20 | Logistics beat (Twin Span uncertain → corroborated → R22) |
| NOAA TCR best track | `data/katrina/sourced/nhc_best_track.json` | Storm path + wind/category at 6-hour (and landfall) fixes |
| HUD flood bowls, fires, Murphy Oil | hazard JSON + snapshot hazards | Clock-gated fields (flood / fire / contamination) |
| 84-event script | `data/katrina/sourced/katrina_event_script.json` | Clock *candidates*, not snapshot state |
| Asset catalog (types, toggles, hazards, heatmap, sequence binds) | `docs/asset-definitions.md` + canvas `katrina-asset-definitions` | What is on the map |
| Event chart | canvas `katrina-event-script` | Human index of 84 bullets |

Live camera is Orleans-centric except during the cyclone-only window. `hazards.cyclone.cone_nm` is **0** (no snapshot disk); the live disk is HURDAT2 R34 at the current event. The replay slider **is** the event script (tick = one event).

## Non-negotiables

1. **LLM explains; code decides.** Replay ticks are data + functions. No model in `mint_permit` or in state transitions.
2. **Type mesh ≠ instance mesh.** Color is damage. Failure geometry only for `bridge.failed` and `breach.open`.
3. **Belief vs ground truth stays.** Twin Span can be physically gone at 29 Aug 06:00 CDT and still `uncertain` on the `t0` belief snapshot. Replay must expose *valid_at* vs *recorded_at*, not flatten them.
4. **Script ≠ source.** `script:katrina-event-synthesis` is a clock. Parameters stay unverified until cited.
5. **Landslide stays off.** No `fire:synth` / `landslide:synth` entities.
6. **Two operations** (realloc, evacuate). Access is a shared constraint.
7. **Replay is a demonstration clock**, not a live-disaster backend. Persuade with hazards, population, routing, and dispatch over time.
8. Do not copy old `crisis-os` wholesale. Do not edit `3d_then_backend_4705733a.plan.md`.
9. **Replay clock = script sequence.** Tick `i` is `events[i]` sorted by `t`. Play, the range, and phase pills walk that list. The map at that tick uses that event’s `t`, `binds`, and elapsed hazard fields. Belief keyframes do not replace or reorder the clock.

## Target architecture (all later phases use this)

```
katrina_event_script.json  →  ReplayClock (CDT)  →  WorldDelta
                                      ↓
                         SnapshotBuilder.apply(delta)
                                      ↓
                         WorldSnapshot  →  diorama.js
```

- **ReplayClock** — continuous time, pause, jump to event id, optional play rate.
- **WorldDelta** — sparse: cyclone pose, entity state patches, hazard fields. Never a full recatalog.
- **Keyframe snapshots** remain the logistics product (`t0` / `b7` / `reroute`). Replay is an additional mode, not a replacement.
- UI: a **replay** range (script time) plus the existing **belief** stops. Do not merge them into one unlabeled slider.

Radius, rainfall, and flood stage must read world-model numbers (shader-binding rule). When the numbers stop, the effect stops.

---

## Build phase A — Replay clock (no new story)

**Goal.** Time can move; the map does not yet tell a new story.  
**Status.** Shipped — `/api/replay`, `/api/replay/at`, timeline in `web/diorama.js`.

**In**

- Load `katrina_event_script.json` via `/api/replay` (static copy also under `web/public/data/sourced/`).
- Clock: event index across all 84 bullets (CDT `t` from first event to last), **stable-sorted by `t`**. Play / pause / phase jump. Tick i is events[i]. Play is 1.2 s per bullet and does not skip.
- Scrubber lists phase 0–6; current event title in the chrome.
- Snapshot at `t` is still one of the three existing keyframes (**nearest by event `t`**). Belief buttons pin a snapshot without moving the script clock. `demo_keyframe` tags are hints, not a later-tick override.
- Category scan in the inspector: every registry category + flood/fire/contamination/cyclone/population is **bound** or **gap** for the current phase (coverage rule, no paint).

**Out**

- Tests: JSON parses; 84 events; phase counts; ISO timestamps; nearest belief keyframe.
- No camera change, no cyclone motion yet.

**Done when** the timeline can sit on an event without crashing, and the legend names the current script tick plus the belief snapshot still holding entity meshes.

---

## Build phase B — Cyclone only (hurricane phases 0–1)

**Story window.** ~23 Aug 16:00 CDT → ~29 Aug 04:00 CDT (before first IHNC overtop).  
**On the map:** cyclone track, moving eye, radius. Phase 0 hides NOLA. Phase 1 shows NOLA assets at rest; flood / evac arcs stay off.  
**Status.** Shipped — HURDAT2 AL122005 interpolation, gulf camera on phase 0, flown/ahead track, 34-kt disk. Phase 1 enters the NOLA basemap with catalog assets at rest and bind-subject camera.

**In**

1. Interpolate eye lon/lat along TCR track using existing `t_h` (linear in time between fixes).
2. Draw **flown path** (solid) vs **path ahead** (ghost). Include Florida landfall from `landfalls[]` (25 Aug 22:30Z, 26.0°N, 80.1°W).
3. Disk at the eye. `r34_nm` is the mean of HURDAT2 34-kt quadrant radii (`hurdat2-al122005`). Landfall rows with missing radii interpolate from neighbouring synoptic fixes. The ~25 nm eye figure is **not** used as the wind field. `rainfall_mm_h` stays 0 (no rain invented).
4. Camera: phase 0 follows the eye (Bahamas → Florida → Gulf); NOLA layers are off. From **phase 1** the map **enters New Orleans**: imagery + the 44 catalog meshes at **pre-landfall rest** (not the 31 Aug damaged snapshot). The camera eases to this tick's `binds` so the beat's subject is in frame. Meteorology-only ticks with no catalog pin stay on a city overview with the cyclone as overlay. Do not follow the eye during phase 1.
5. Rain particles only if `rainfall_mm_h > 0` (keep the shader-binding rule; do not invent rain).
6. Hide or freeze NOLA operations chrome that implies 31 Aug logistics (or keep it but visually recede). Hazard toggles stay unused; cyclone is the subject.

**Out of scope for B**

- Parish evacuation orders, contraflow meshes, Florida damage assets, TD12 formation iconography beyond the first track point.
- Densifying the track before 24 Aug 00Z unless TCR Table 1 (or HURDAT) is retrieved for 23 Aug.

**Done when** a scrub from 23→29 Aug shows the storm crossing Florida into the Gulf, growing the disk as category rises, and arriving south of the Mississippi mouth — on sourced track points.

---

## Build phase C — Landfall hour (hurricane phase 2, NOLA camera)

**Story window.** 29 Aug ~04:30–18:00 CDT. Camera stays on NOLA and eases to each tick's binds (IHNC, Twin Span, 17th, Dome, …).

**In (only sourced binds)**

| Clock | World change | Source to require before paint |
| --- | --- | --- |
| ~04:30–05:00 | IHNC west overtop / early wet | IPET / script bind `breach:ihnc-west` — cite IPET before state flip |
| ~05:00 | IHNC east monolith → Lower 9 | `breach:ihnc` critical; `zone:B` |
| ~06:00–06:10 | Buras landfall Cat 3; Twin Span `valid_from` inaccessible **as ground truth** | `noaa-tcr-al122005`, `usgs-circ-1306-ch3d` |
| ~06:20 | Dome power fail | `shelter:dome` + `infra:power` — needs a cited locator |
| ~06:30 | Pumps down; London south; 17th St begins | `infra:pump*`, `breach:london`, `breach:17th` — IPET |
| ~07:30–09:00 | Second IHNC hole; London north; 17th fully open | remaining `breach:*` |
| ~08:12 | NWS Tennessee St warning | event glyph, not a new mesh |
| ~10:00 | Second landfall LA/MS | cyclone eye continues north of the map |
| afternoon | flood bowls deepen toward HUD 31 Aug table | interpolate `wet_frac` / stage toward `hud-noaa-flood-2005-08-31`; do not invent MOTF polygons |

Belief: a **ground-truth** layer can show B7 failed at 06:00 while a **belief** overlay remains unverified until 31 Aug 09:20. Do not delete the logistics beat.

Cyclone: keep the moving disk, now at the edge of / over the NOLA map; radius still data-bound.

**Done when** scrubbing 29 Aug morning opens breaches in script order and flood opacity/height increases, without changing `t0` JSON’s uncertain B7.

**Shipped.** `src/crisis_os/landfall.py` attaches `world_delta` on phase-2 ticks. Ground-truth Twin Span fails at 06:00; belief stays `uncertain` / unverified. HUD bowls scale with the IHNC Lock hydrograph. Pinning the t0 belief snapshot still shows the frozen JSON.

---

## Build phase D — Inundation and shelters (hurricane phase 3)

**Story window.** 30–31 Aug.

**In**

- Drive HUD bowls toward ~80% inundation language **as labeled HUD/USGS-derived**, not as a new GIS fill.
- Dome occupancy: landfall-morning figure → 31 Aug ~20k (already parameterized).
- Convention Center occupancy from 0 (b7) → House 19k at t0 (already parameterized).
- 31 Aug afternoon: Blanco Dome evac **as an event + occupancy transfer**, only if we keep it as scripted UI until a citation is attached.
- Murphy Oil green (30 Aug) already in hazard data — gate on `t >= 2005-08-30` instead of always-on if replay mode is strict.
- Fires: photographs are 2 Sep; current keyframes show them on 31 Aug with a vintage note. Replay should not antedate the photos without labeling.

**Keep** `t0` / `reroute` as the convoy/permit story on 31 Aug morning.

**Done when** 30–31 Aug scrub shows rising water, Dome/CC occupancy, and the existing R14/R22 beat still works at 08:00 / 09:20.

**Shipped.** `src/crisis_os/inundation.py` attaches `world_delta` on phase-3 ticks. HUD bowls interpolate from end-of-C hydrograph fill to the 31 Aug planning-district table (not MOTF). Dome occupancy reaches the sourced 20k at `p3-max-inundation`; Convention Center reaches House 19k at `p3-cc-crisis`. Murphy Oil is `fuel:depot` + `hazards.contamination`. Fires stay off until `p4-fires`. After 31 Aug 08:00 the overlay drops logistics IDs so pinning t0/reroute still shows the convoy beat. `t0.json` B7 stays `uncertain` / unverified.

---

## Build phase E — Federal / unwatering (hurricane phases 4–6)

**Defer until A–D are shippable.** These ticks are in the JSON but mostly **unbound** to sourced parameters (Guard headcounts, Title 10, pump cfs, % unwatered, MSY commercial reopen).

**When opened, do in this order**

1. Retrieve numbers into `parameters.json` (Entergy restoration fractions, USACE pump cfs, MSY 13 Sep, DHS Dome/CC clear ~4 Sep).
2. Then: MSY state, pump counts, flood `wet_frac` decay, power plants returning from inaccessible → damaged → operational.
3. Do not build Houston Astrodome geography. Off-map evac is an arc or a chrome count, not a second city.

**Done when** Sep 4–18 is a sourced unwatering/power story on the same NOLA map, or we explicitly cut the replay end at 31 Aug.

**Shipped.** `src/crisis_os/unwatering.py` attaches `world_delta` on hurricane phases 4–6. HUD bowls decay from the 31 Aug ceiling (60% city on 6 Sep, 40% on 15 Sep, >80% unwatered on 18 Sep). Pump counts and cfs are parameters (USACE via Wikipedia, unverified). Entergy 9/17 units and 11% of ENO customers on are DOE sitrep #28. MSY goes military/relief → limited commercial on 13 Sep (LA Times). Dome/CC occupancy hits 0 at `p5-dome-cc-cleared` (NPR). Houston is a chrome count, not a second city. Fires appear at `p4-fires`. `t0.json` B7 stays `uncertain` / unverified.

---

## Build phase F — Product polish (parallel, after B)

- Replay vs belief chrome (two clocks, one map).
- Event inspector: script title + `binds` + source_key or “unverified script.”
- Tests: cyclone interpolation monotonic; B7 ground-truth vs t0 belief; no synthetic fire/landslide entities; `cone_nm` / radius never a magic constant in the renderer.
- Camera presets: `gulf` (phase B), `nola` (C–E).
- Hard-refresh / `Cache-Control: no-store` unchanged.

---

## Suggested ship order

| Sprint | Build phase | Visible result |
| --- | --- | --- |
| 1 | A | Shipped: scrubber on the 84 events; world still the three snapshots |
| 2 | B | Shipped: storm flies Bahamas → Florida → Gulf with a growing 34-kt disk |
| 3 | C | Shipped: 29 Aug morning breaches + flood + B7 ground truth |
| 4 | D | Shipped: 30–31 Aug water / Dome / CC; logistics keyframes intact |
| 5 | F | Chrome, tests, camera presets |
| 6 | E | Shipped: Sep unwatering / power / MSY on the same NOLA map |

## Explicitly not in v1

- Unique meshes per hospital or a Florida asset catalog
- FEMA MOTF shapefiles, USGS 2005 IHNC NWIS (absent), 2005 DEM terrain
- People meshes, contraflow lane geometry, Title 10 unit icons
- Using the event script as a verified hydrograph

## Pointers

- Script: `data/katrina/sourced/katrina_event_script.json`
- Track: `data/katrina/sourced/nhc_best_track.json`
- Citations: `data/SOURCES.md`
- Live draw: `web/diorama.js`
- Catalog / layers / sequence entities: `docs/asset-definitions.md`
- This file is the build-phase plan; hurricane phase numbers (0–6) are the *story* bins inside the script, not sprint names (those are A–F above).
