# Katrina asset definitions — live catalog

**Status:** catalog of record for what is on the map today (2026-09-06).  
**Form** (meshes, shaders, LOD) stays in [`entity-rendering.md`](entity-rendering.md).  
**Replay build order** stays in [`katrina-replay-build-phases.md`](katrina-replay-build-phases.md).  
Chart beside chat: `katrina-asset-definitions` canvas.

Closed catalog: **44 named entities**, **one symbolic mesh per type**, color = damage (green undamaged → yellow unknown → orange damaged → red destroyed/inaccessible). A type with no registry row does not render. No unique mesh per hospital.

## Source of truth

| Layer | File |
| --- | --- |
| Instances, coords, `BASE_STATES` | `src/crisis_os/catalog.py` |
| Type grammar (category, primitive, glTF, far symbol, failure variant) | `data/katrina/world/symbol-registry.json` |
| What the live CDN map extrudes | `web/public/assets/type-solids.json` via `web/diorama.js` |
| Chrome toggles | `flags.opRealloc`, `flags.opEvacuate`, `flags.popTotal` in `web/diorama.js` |
| Population field | `snapshot.population` · [`population-density.md`](population-density.md) |
| Event clock | `data/katrina/sourced/katrina_event_script.json` — replay scrubber is this sequence (tick i = events[i] by t) |

glTF under `web/public/assets/gltf/` exists but is **not** loaded on the live CDN path.

Canonical logistics IDs: `bridge:B7`, `route:R14`, `route:R22`, `zone:B`, `zone:C`, `warehouse:W1`, `truck:17`, `hospital:NDH`. Three keyframes only: `t0`, `b7`, `reroute`.

**Couplings you must not split:** `route:R14` ↔ `bridge:B7`; `route:R22` ↔ `bridge:us11`; `zone:C` ↔ `shelter:morial`; pumps / water / hospitals / Dome / EOC / MSY ↔ `infra:power`; IHNC breaches ↔ `zone:B`; 17th / London breaches ↔ `zone:C`.

---

## Registry categories (on the map as assets)

Category is the **shape language**. Operation toggle is a **different axis** (next section). Personnel is humanitarian by category and realloc by toggle; water plant is utilities by category and realloc by toggle.

| Category | Types in use | How they draw |
| --- | --- | --- |
| **transport** | `bridge`, `route`, `road`, `port`, `airport`, `vehicle` | Bridges/port/airport/vehicle = type solids (bridges also OSM span PathLayer). Routes/road = ribbons, not boxes. |
| **health** | `hospital`, `clinic`, `medicine` | Type solids |
| **humanitarian** | `shelter`, `school`, `camp`, `personnel`, `zone` | Mesh solids except `zone` (ring; occupancy at shelter sites) |
| **utilities** | `power`, `water`, `pump`, `comm`, `gauge` | Type solids |
| **supply** | `warehouse`, `food`, `fuel` | Type solids + stock fill |
| **hazard** (catalog) | `breach` only | Type solid; `breach.open` when critical / inaccessible |

**23 types in use** across 44 instances. Live extrusion keys: `bridge`, `hospital`, `clinic`, `shelter`, `school`, `power`, `water`, `pump`, `breach`, `port`, `airport`, `comm`, `gauge`, `warehouse`, `vehicle`, `personnel`, `food`, `medicine`, `fuel`, `camp`. `landslide` has a type solid and is **off**.

Failure geometry only: `bridge.failed` (Twin Span after corroboration), `breach.open`.

---

## Chrome toggles (what actually shows)

Three checkboxes, all **on** by default. There are **no hazard layer checkboxes**.

| Toggle | Flag | Meaning |
| --- | --- | --- |
| Resource reallocation | `opRealloc` | Stock / convoy story |
| Evacuation | `opEvacuate` | Occupancy / displacement story |
| Overall population | `popTotal` | Census density heatmap — not people meshes |

Access is shared: types in neither operation set stay visible if **either** realloc or evacuate is on. Turn **both** operations off and catalog assets drop; hazards and the heatmap do not.

### Resource reallocation — types and instances

`warehouse`, `vehicle`, `food`, `fuel`, `medicine`, `water`, `personnel`

| Type | Instances |
| --- | --- |
| `warehouse` | `warehouse:W1` |
| `vehicle` | `truck:17` |
| `food` | `food:pod` |
| `fuel` | `fuel:depot` |
| `medicine` | `medicine:cache` |
| `water` | `infra:water` |
| `personnel` | `personnel:ng` |

Also only with realloc: `route_segments`, ghost plan vs solid permitted path (`route:R14` / `route:R22`).

### Evacuation — types and instances

`shelter`, `camp`, `zone`, `hospital`, `clinic`, `school`

| Type | Instances |
| --- | --- |
| `shelter` | `shelter:dome`, `shelter:morial` |
| `camp` | `camp:cloverleaf` |
| `zone` | `zone:B`, `zone:C` |
| `hospital` | `hospital:NDH`, `charity`, `university`, `touro`, `methodist`, `chalmette` |
| `clinic` | `clinic:9th` |
| `school` | `school:mcd` |

Also only with evacuate: displaced-cell dots (after flood is on) and pulsing orange evac arcs. Arcs follow `population_delta.movement` for this replay tick (outbound, into shelters, rescue, Dome→CC, off-map via MSY). They are **not** the density heatmap and must not wait for flood or a landfall patch.

### Access — constraint for both

Shown if realloc **or** evacuate is on:

`bridge`, `route`, `road`, `port`, `airport`, `power`, `pump`, `breach`, `comm`, `gauge`

Instances: `bridge:B7`, `bridge:us11`, `bridge:ccc`, `bridge:danziger`, `bridge:causeway`, `route:R14`, `route:R22`, `road:i10`, `infra:port`, `airport:msy`, `airport:lakefront`, `infra:power`, `power:michoud`, `power:waterford`, `power:ninemile`, `infra:pump6`, `infra:pumpInd`, five `breach:*`, `comms:eoc`, `gauge:ihnc`.

---

## Hazards — no checkboxes; replay clock gates them

Already built. Bound to world-model values. Do not add `fire:synth` / `landslide:synth`. Chrome has no hazard toggles — the **replay clock** turns fields on when the script sequence binds them.

| Hazard | Primitive | Bound to | On-map |
| --- | --- | --- | --- |
| **Flood** | HUD planning-district bowls | district depth × flooded-unit share; city `stage_m` | after first `hazards.flood` tick; OSM roads blue when submerged |
| **Fire** | particles | three riverfront sites (Tchoupitoulas, Mandeville Wharf, Chartres) | after `hazards.fire` (`p4-fires`, 2 Sep) |
| **Contamination** | polygon fill | Murphy Oil Meraux spill | after `hazards.contamination` (`p3-murphy-oil`) · catalog pin `fuel:depot` |
| **Cyclone** | HURDAT2 pose at event `t` | `hurdat2-al122005` 34-kt mean radius | every tick; phase 0 follows the eye (NOLA hidden); phase 1+ NOLA assets + camera on this tick's binds; cyclone stays an overlay |
| **Landslide** | registered mesh | none | **off** |

With **Overall population** on, flood bowls and OSM buildings flatten so the heatmap can sit on the map.

---

## Population heatmap (already built)

`popTotal` draws `snap.population.heat` as a deck.gl HeatmapLayer (yellow → red). Remaining share is **continuous in event time** between sourced anchors (Census 2000 prior, 28 Aug remaining, early-Sep emptying, July 2006 city total). Each building/road sample joins this tick's HUD flood bowl (street-level): inside a bowl it scales by `wet_frac × (1 − bowl_empty × bowl.wet_frac)`; outside by `dry_frac`. Play eases between consecutive `population_delta`s. Never people meshes. Forecast population is disabled.

| Toggle | Effect |
| --- | --- |
| On | density surface; buildings and flood flatten |
| Off | 3D bowls and extruded footprints return; density surface hides |

Evac dots/arcs ride on `opEvacuate`, not on this toggle. See [`population-density.md`](population-density.md) for the design of record; live chrome is the three checkboxes above, not the six-item POPULATION panel in that doc’s §27.

---

## City fabric (not entities)

OSM buildings (HUD `wet_frac` tints damaged/destroyed), OSM roads (green open · amber degraded · red blocked · blue submerged), OSM canals (reference), Esri World Imagery (modern; Twin Span visible is the 2011 rebuild).

---

## All 44 named entities

t0 = `BASE_STATES`. Color on the map follows this spectrum.

### Transport (12)

| ID | Type | Name | t0 | Toggle |
| --- | --- | --- | --- | --- |
| `bridge:B7` | bridge | I-10 Twin Span Bridge | uncertain | access |
| `bridge:us11` | bridge | Maestri Bridge (US-11) | operational | access |
| `bridge:ccc` | bridge | Crescent City Connection (US-90) | operational | access |
| `bridge:danziger` | bridge | Danziger Bridge | operational | access |
| `bridge:causeway` | bridge | Lake Pontchartrain Causeway (south) | operational | access |
| `route:R14` | route | I-10 East (to Slidell) | operational | access |
| `route:R22` | route | US-11 Lake Pontchartrain (alt) | operational | access |
| `road:i10` | road | I-10 at Claiborne Avenue overpass | damaged | access |
| `truck:17` | vehicle | Relief water convoy 17 | operational | realloc |
| `infra:port` | port | Port of New Orleans (Julia St) | damaged | access |
| `airport:msy` | airport | Louis Armstrong New Orleans Intl | inaccessible | access |
| `airport:lakefront` | airport | New Orleans Lakefront Airport | inaccessible | access |

### Health (8)

| ID | Type | Name | t0 | Toggle |
| --- | --- | --- | --- | --- |
| `hospital:NDH` | hospital | Memorial Medical Center (Baptist) | operational | evacuate |
| `hospital:charity` | hospital | Charity Hospital | inaccessible | evacuate |
| `hospital:university` | hospital | University Hospital (MCLNO) | inaccessible | evacuate |
| `hospital:touro` | hospital | Touro Infirmary | damaged | evacuate |
| `hospital:methodist` | hospital | Pendleton Memorial Methodist | inaccessible | evacuate |
| `hospital:chalmette` | hospital | Chalmette Medical Center | inaccessible | evacuate |
| `clinic:9th` | clinic | St. Claude Ave clinic (9th Ward) | inaccessible | evacuate |
| `medicine:cache` | medicine | MSY airport DMAT field hospital | inaccessible | realloc |

### Humanitarian (7)

| ID | Type | Name | t0 | Toggle |
| --- | --- | --- | --- | --- |
| `zone:B` | zone | Lower Ninth Ward | uncertain | evacuate |
| `zone:C` | zone | Ernest N. Morial Convention Center | uncertain | evacuate |
| `shelter:dome` | shelter | Louisiana Superdome | critical | evacuate |
| `shelter:morial` | shelter | Ernest N. Morial Convention Center | critical | evacuate |
| `camp:cloverleaf` | camp | I-10 / Causeway cloverleaf | critical | evacuate |
| `school:mcd` | school | McDonogh 35 Senior High | critical | evacuate |
| `personnel:ng` | personnel | Jackson Barracks — Louisiana NG HQ | critical | realloc |

### Utilities (9)

| ID | Type | Name | t0 | Toggle |
| --- | --- | --- | --- | --- |
| `infra:power` | power | A.B. Paterson / Market St plant | inaccessible | access |
| `power:michoud` | power | Entergy Michoud Generating Station | inaccessible | access |
| `power:waterford` | power | Waterford 3 Nuclear Station | damaged | access |
| `power:ninemile` | power | Entergy Nine Mile Point | damaged | access |
| `infra:water` | water | Carrollton Water Purification Plant | critical | realloc |
| `infra:pump6` | pump | S&WB Drainage Pump Station No. 6 | damaged | access |
| `infra:pumpInd` | pump | S&WB Drainage Pump Station No. 5 | inaccessible | access |
| `comms:eoc` | comm | City command post — Hyatt Regency | critical | access |
| `gauge:ihnc` | gauge | IHNC Lock staff gauge | operational | access |

### Supply (3)

| ID | Type | Name | t0 | Toggle |
| --- | --- | --- | --- | --- |
| `warehouse:W1` | warehouse | Slidell I-10 staging | full | realloc |
| `food:pod` | food | Alario Center POD | inaccessible | realloc |
| `fuel:depot` | fuel | Murphy Oil refinery (Meraux) | inaccessible | realloc |

### Hazard catalog (5 breaches)

| ID | Name | t0 | Toggle |
| --- | --- | --- | --- |
| `breach:17th` | 17th Street Canal (Bellaire Dr) | critical | access |
| `breach:london` | London Avenue Canal south (Mirabeau) | critical | access |
| `breach:london-n` | London Avenue Canal north (Warrington) | critical | access |
| `breach:ihnc` | IHNC east-bank (Lower Ninth) | critical | access |
| `breach:ihnc-west` | IHNC west-bank (France Rd) | critical | access |

---

## Sequence awareness (hurricane phases 0–6)

**Replay clock = this sequence.** The footer range is `events[]` sorted by `t`. Scrubbing, Play, and phase pills walk those 84 ticks. Do not invent a parallel timeline.

At tick `i`: cyclone pose is `ev.t`; catalog `binds` on that event are highlighted (plus couplings); the camera frames those binds; hazard fields are on if any event `0..i` bound them. Phase 1 patches all 44 entities to **pre-landfall rest**. Phase C patches 29 Aug landfall entities. Script binds are **hints** for that interpolation, not verified parameters — bind a bullet only when `data/SOURCES.md` has the same fact.

Sprint B phase 0 is cyclone-only. Sprint B phase 1 is NOLA basemap + catalog at rest; camera on the current event's binds. The population heatmap scales every tick (`population_delta`).

Hazards and the heatmap have **no chrome checkboxes**. On NOLA sequences they follow the replay clock (flood after the first `hazards.flood` bind, Murphy Oil after `hazards.contamination`, riverfront fire after `hazards.fire`). Catalog ticks are listed here.

### Phase 0 — Formation and first U.S. landfall (23–25 Aug)

**Reflect:** `hazards.cyclone` (eye, flown/ahead track, radius). Script binds are empty.  
**Do not tick:** all 44 NOLA entities, flood, fire, contamination.

### Phase 1 — Gulf intensification (26–28 Aug)

**On the map:** NOLA imagery + 44 catalog meshes at pre-landfall rest. Camera eases to this tick's binds (EOC, Dome, pumps, hospitals, …). Cyclone is an inbound overlay (low-alpha R34). Flood / fire / contamination off. No 31 Aug evac arcs or convoy.  
**Implied if those binds ever paint:** `bridge:B7` (with R14), `bridge:us11` (with R22), `shelter:morial` (with zone:C).

### Phase 2 — Landfall, surge, initial failures (29 Aug)

**On the map (sprint C):** breaches open in script order; HUD bowls rise with the IHNC Lock hydrograph; Twin Span **ground-truth** mesh fails at ~06:00 while **belief** stays yellow/`uncertain` (t0 JSON is not rewritten). Gap-fills (`shelter:dome` power, Entergy plants, Chalmette, EOC, Guard) are never marked verified.

First sequence where catalog **state must change** (sourced binds only):

`breach:ihnc-west`, `breach:ihnc`, `breach:london`, `breach:london-n`, `breach:17th`, `zone:B`, `gauge:ihnc`, `bridge:B7`, `route:R14`, `shelter:dome`, `infra:power`, `infra:pumpInd`, `infra:pump6`, `hospital:chalmette`, `power:michoud`, `power:ninemile`, `power:waterford`, `personnel:ng`, `comms:eoc`, `hazards.flood`, `hazards.cyclone`.

B7 ground truth can be failed at ~06:00 while `t0` belief stays `uncertain` until 31 Aug 09:20.

**Keep on the NOLA map (may not tick yet):** remaining hospitals, `clinic:9th`, `infra:water`, other bridges, `road:i10`, `camp:cloverleaf`, `school:mcd`, airports, `infra:port`, `warehouse:W1`, `truck:17`, `food:pod`, `medicine:cache`, `fuel:depot`, `shelter:morial`, `zone:C`. Power-dependent sites follow `infra:power`.

### Phase 3 — Inundation and shelters (30–31 Aug)

`hazards.flood`, `zone:B`, `breach:ihnc`, `hospital:chalmette`, `personnel:ng`, `hazards.cyclone` (fade), `shelter:dome`, `shelter:morial`, `zone:C`, `food:pod`, `medicine:cache`, `hazards.contamination`, `fuel:depot`.

Build phase D patches HUD bowls toward the 31 Aug table, Dome/CC occupancy, and Murphy green. `t0.json` is unchanged. Fires stay off until phase 4.

31 Aug logistics beat: the eight canonical IDs plus `bridge:us11` with R22. Do not antedate `hazards.fire` (photos are 2 Sep) without a vintage label.

### Phase 4 — Federal surge (1–3 Sep)

`zone:B`, `shelter:dome`, `shelter:morial`, `warehouse:W1`, `truck:17`, `food:pod`, `personnel:ng`, `airport:msy`, `airport:lakefront`, `hazards.fire`. Houston is chrome, not a second city.

Build phase E starts here: riverfront fires on, Dome/CC still occupied then emptying, MSY military/relief only, Twin Span known failed. `t0.json` unchanged.

### Phase 5 — Unwatering and power start (4–10 Sep)

`infra:power`, `comms:eoc`, `hospital:NDH`, `power:waterford`, `power:michoud`, `power:ninemile`, `infra:pump6`, `infra:pumpInd`, `hazards.flood`, `shelter:dome`, `shelter:morial`.

Phase E: Dome/CC empty (NPR 4 Sep). HUD bowls decay. 23 then 26 permanent pumps. Entergy 9 of 17 units; Waterford still offline; ~11% of Entergy New Orleans customers on.

### Phase 6 — Recession and early recovery (11 Sep–Oct)

`hazards.flood`, `zone:B`, `zone:C`, `airport:msy`, `shelter:dome`, `shelter:morial`, `infra:power`, `power:waterford`, `breach:17th`, `breach:london`, `breach:london-n`, `breach:ihnc`, `breach:ihnc-west`, `hazards.contamination`, `fuel:depot`.

Phase E: 40% inundation (15 Sep), >80% unwatered (18 Sep), MSY limited commercial (13 Sep), emergency breach closures, October mostly dry. No Houston geography.

### On the map every NOLA sequence, never bound in the script

These ten still exist in the 44 and already have `BASE_STATES`. They must not vanish:

`bridge:ccc`, `bridge:danziger`, `bridge:causeway`, `camp:cloverleaf`, `school:mcd`, `hospital:methodist`, `clinic:9th`, `infra:water`, `infra:port`, and `bridge:us11` (must move with `route:R22` even though the JSON never names it).
