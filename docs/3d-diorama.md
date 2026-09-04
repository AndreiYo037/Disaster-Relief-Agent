# 3D Diorama — Visual Design of Record

**Status:** design of record (andrei, 2026-09-04). Supersedes the PRD §5
"3D live situational-awareness view" note, which this expands.

The diorama is the World Model's visual representation: a living miniature model of
the affected region, somewhere between a premium architectural model, Google Earth,
and a real-time emergency simulation. It must feel like **one coherent physical
world, not a pile of UI overlays.**

## 0. The governing principle

> **Don't design the 3D scene first and then put crisis information on it. Design
> the World Model first, then let the 3D scene become its visual representation.**

This is the load-bearing rule and every other item is subordinate to it. Concretely
it means the diorama is a **pure read** of `EntityState` / `WorldSnapshot` and is
never a second source of truth. If a visual channel has no entry in the
[render contract](#render-contract), it does not get rendered — because there is
nothing in the world model authorising it to appear.

The Crisis OS isn't showing geography. It's showing **knowledge about geography.**

## Amendment index

Seven amendments were made to the original spec during review. Each is marked inline
where it applies. A6 and A7 arrived later, from the entity-rendering pass; their
full treatment is in [`entity-rendering.md`](entity-rendering.md).

| # | Item | Amendment |
| --- | --- | --- |
| A1 | 1. Terrain | New Orleans has no mountains. The terrain that dominates is the **bowl**, with a declared vertical exaggeration factor. |
| A2 | 4. Hazards | Flood extent is **derived** from a stage scalar plus a breach-seeded fill, not authored as a polygon. |
| A3 | 7. Population movement | Restricted to **real shelter-occupancy deltas**. No simulated flows. |
| A4 | 14. Visual states | The five states are **two independent axes**, not five exclusive values. |
| A5 | 4. Hazards | All four hazard variants stay. Each needs its own **world-model binding** before it may render; cyclone binds directly to the Katrina scenario. |
| A6 | 2. Buildings | Distinct 3D models **per type, never per instance**. State drives material, not form — except for enumerated structural-failure variants. |
| A7 | 7 vs 16. Effects | Particles and shaders are permitted when **every parameter is bound to a world-model value**, forbidden when decorative. |

---

## 1. Terrain should dominate

The base is a 3D terrain model: valleys, rivers, coastline, urban and rural areas.

Not hyper-realistic like a video game. A slightly simplified digital-twin /
simulation aesthetic makes operational information easier to read.

> Think **physical model + satellite geography + game-engine lighting**, rather
> than photorealism.

> ### Amendment A1 — the bowl, not mountains
>
> The original sketches placed mountains at the top of the frame. New Orleans has
> essentially no relief; the city is flat and largely **below sea level**. That is
> not a problem to work around — it is the entire reason the city flooded and could
> not drain, so the terrain still dominates, just inverted.
>
> Two consequences:
>
> 1. **Vertical exaggeration is mandatory.** A few metres of relief will not read as
>    topography at 1:1. Expect 20× or more.
> 2. **The exaggeration factor must be declared on screen and stored as a
>    parameter** (`visualization.vertical_exaggeration` in
>    `data/katrina/parameters.json`, `source_key: design:tuned-for-demo`). An
>    undeclared exaggeration is the model lying about elevation, which is precisely
>    the class of failure this product exists to prevent.

## 2. Buildings should be simplified

Don't render every building with architectural detail. Instead let the **shape
itself communicate what something is** — semantic 3D:

- residential areas → dense clusters
- commercial → slightly taller blocks
- hospitals → recognisable landmarks
- warehouses → large industrial forms
- shelters → distinct structures
- critical infrastructure → clearly identifiable

Implementation: extrude a real footprint by a **type-derived** height. Footprint
geometry is static reference data; the type comes from `Entity.type`.

> ### Amendment A6 — distinct models per type, never per instance
>
> Named entities get their own **3D model or symbol**, drawn from a registry keyed on
> `Entity.type`. Roughly 22 types means roughly 22 meshes.
>
> Per *instance* is rejected. If every hospital has a bespoke mesh, "hospital" stops
> being readable at a glance — which is the whole point of this section — and the
> asset count becomes the entity count. Instances differentiate through **state
> channels**: colour, translucency, saturation, capacity readouts. Never geometry.
>
> **One enumerated exception: structural failure.** A severed bridge must look
> severed, because recolouring it is not enough when the mid-run beat is that the
> crossing is gone. `bridge`, `breach` and landslide run-out carry a second state
> mesh variant. This is a closed list, not a general licence.
>
> Full registry, category grammars and asset budget in
> [`entity-rendering.md`](entity-rendering.md).

## 3. Population should look like a density field

> **Expanded and superseded by [`population-density.md`](population-density.md).**
> That document is authoritative for everything population — sublayers, hazard
> exposure, provenance, drill-down, privacy and the API. This section remains as the
> visual summary and the binding to the rest of the diorama.

Do **not** put thousands of little people into the model. The terrain carries a
population-density field:

```
LOW       ░░░░░░
MEDIUM    ▒▒▒▒▒▒
HIGH      ██████
VERY HIGH ████████
```

Density conforms to geography and urban structure, so a dense city looks visually
dense while rural areas stay sparse. The operator immediately understands
**where the people are.**

This requires **gridded** population, not the single scalar per zone the world
model currently holds. `zone:B.population = 14008` is one number at one coordinate;
a field needs census-block geometry.

This is also where the equity thesis becomes *spatial*: "the efficient plan starves
the vulnerable zone" is legible on a density field in a way it never is in a table.

## 4. Hazards should physically interact with the world

Don't place a blue polygon over the terrain. The water **occupies the low-lying
terrain**:

```
mountain
       \
        \____
             ~~~~~~~~~
             FLOOD
~~~~~~~~~~~~~~
```

Buildings sit inside and around the affected area. Road segments disappear under
the flood. Bridges become particularly obvious.

> ### Amendment A2 — flood extent is derived, not authored
>
> This is the strongest idea in the spec and it is worth stating more strongly than
> the original does.
>
> Given a real DEM and a **water-surface elevation** held in the world model, flood
> extent stops being an authored GeoJSON polygon and becomes a *computed* result:
> the wet cells are those whose ground elevation sits below the current stage.
>
> The whole flood visual is therefore driven by **a single scalar** — and that
> scalar is exactly what the USGS gauge supplies to the sensor-threshold path in
> Perception. The chain from sensor reading to rendered water becomes physically
> causal rather than decorative.
>
> **Do not simply threshold the entire DEM.** That floods disconnected inland
> depressions that never actually filled. Instead **flood-fill outward from the
> breach entities** (`breach:ihnc`, `breach:17th`, `breach:london`), seeded only
> where the breach state is critical. Water then enters at the levee failures and
> spreads through the bowl, which makes the breaches the visible *cause* of the
> inundation instead of coincidental red dots.
>
> Cost: a connected-component fill over a grid. Payoff: the most convincing single
> thing that can be put on screen.

### 4a. Wildfire

```
      ╭──── fire perimeter ────╮
     ╱    ▓▓▓ burned ▓▓▓       ╲
    │   ▓▓▓▓ terrain ▓▓▓▓       │
     ╲     ~ smoke ~          ╱
      ╰────────────────────────╯
```

- **fire perimeter** — an advancing boundary, not a static polygon
- **smoke** — drifting, and it degrades observation quality downwind
- **burned terrain** — a persistent change to the terrain itself
- **affected structures** — buildings inside the perimeter change state

### 4b. Landslide

```
   slope failure
        ╲
         ╲▓▓▓
          ▓▓▓▓▓ debris path
            ▓▓▓▓▓
   ──────────✕▓▓▓──────  road blocked
```

- **slope failure** — a change to the terrain surface at the source
- **debris path** — a downslope run-out corridor
- **blocked road** — the route segments the debris path intersects

Note that landslide is the hazard most tightly coupled to the terrain model: it is
the only one whose visual requires *modifying* the DEM rather than layering over it.

### 4c. Cyclone

```
        projected track
       ·  ·  ·  ●─────╮
                      ╰──▶  ╭─────────────╮
                            │  wind/rain  │
                            │  footprint  │
                            ╰─────────────╯
```

- **projected track** — with the uncertainty cone, which is a forecast and must
  render as ghosted per item 14
- **affected region** — the area under warning
- **wind/rain footprint** — intensity as a field, not a boundary

> ### Amendment A5 — every hazard variant needs a world-model binding
>
> All four hazard treatments stay in the spec. The amendment is about **what must
> exist before each one may render**, not about cutting scope.
>
> The governing principle applies to hazards exactly as it applies to everything
> else: a hazard renders because state authorises it, never because the renderer
> knows how to draw it. So each variant needs a hazard entity carrying geometry and
> an `EntityState`, and a row in the [render contract](#render-contract) naming the
> field that drives it. Until those exist, the variant is specified but not
> renderable.
>
> **The cyclone treatment is not a generalisation for this scenario — it is core to
> it.** Katrina *is* a tropical cyclone, and `noaa-tcr-al122005` (the NHC best
> track) is already a committed source supplying track position, intensity and
> timing. The projected track and wind footprint are therefore first-class demo
> content, and the uncertainty cone is a genuinely good showcase for the forecast
> rendering state in item 14.
>
> **Wildfire and landslide are the multi-hazard proof.** They demonstrate that the
> diorama renders *hazards* rather than being hardwired to floods, which is a real
> architectural claim worth making. They need seeded hazard entities of their own,
> so they follow the Katrina content rather than competing with it.
>
> One useful cross-hazard note: wildfire smoke and cyclone rainfall both degrade
> observation quality in a region. That is the same mechanism as the data fog in
> item 15, so they should drive the fog rather than getting bespoke treatments.

## 5. Infrastructure should feel physical

A bridge actually bridges two pieces of terrain. A road actually connects
locations. A warehouse exists at a real location. A hospital is physically situated
within the city.

This is what lets the operator **see relationships, not just objects**:

```
bridge:B7 collapses
  → the bridge itself changes appearance
  → route:R14 becomes unavailable
  → dependent routes are highlighted
  → logistics missions relying on it become affected
```

Note the dependency requirement this creates: to show a road *disappearing under
water*, routes need **segment-level** geometry. A single `route:R14` entity at one
coordinate cannot express partial inundation.

## 6. Vehicles should be tiny but alive

Small 3D models — trucks, ambulances, boats, aircraft, responder vehicles — moving
along **actual** routes:

```
WAREHOUSE
    ●
    │
    │ 🚚
    │   →
    │      →
    ✕──────── B7
             \
              ZONE B
```

Clicking a vehicle opens its operational state. The movement is what gives the
diorama a sense of life.

## 7. Population movement should be subtle

No giant arrows across the map. Soft particle / flow fields, where the **density of
movement indicates magnitude**:

```
██████████
████████  → → →
████████  → → → →   SHELTER CLUSTER
████████      → →
```

> ### Amendment A3 — flows must come from occupancy deltas only
>
> Displacement flow fields need origin–destination pairs that the system does not
> produce. Forecasting yields a displacement **rate** (a scalar), not flows.
>
> Animating anything beyond observed movement would mean rendering invented data —
> the exact failure the product exists to prevent, and worse here than in a table
> because motion is so persuasive.
>
> **Permitted source:** deltas in shelter `EntityState.attributes.occupancy`
> between snapshots, drawn as flow from the zone that lost people to the shelter
> that gained them. Nothing else. If occupancy isn't changing, nothing moves.

## 8. Roads should communicate state

The road network is part of the visual language:

```
OPEN           ───────
DEGRADED       - - - - -
BLOCKED        ───── ✕ ─────
PLANNED ROUTE  ═══════
INVALIDATED    ══════ ✕ ════
```

## 9. Glow only where it matters

Most of the environment stays calm and neutral. Then important things become
visually active: a bridge failure highlights, a critical hospital highlights, an
emerging population cluster highlights, an active logistics mission animates, a new
hazard spatially expands.

The point is a strong **signal-to-noise hierarchy**. Everything glowing is
equivalent to nothing glowing.

## 10. Everything can change

The diorama is alive. Watching a crisis unfold:

```
10:00  flood small · bridge open · population normal · truck moving
11:00  flood expands → bridge inaccessible → route:R14 blocked
11:10  truck stops → delivery delayed
11:15  world model updates → shortage risk increases
11:20  alternative route appears
```

**The diorama itself tells the story of the crisis.** This is the demo.

## 11. A very subtle atmosphere layer

Environmental effects that communicate the crisis — clouds, rain, smoke, fog,
water, changing daylight — kept restrained. Gradually increasing rain during a
flood makes the environment feel alive.

**Visual effects must never compromise operational visibility.** Deferred: this
layer has no world-model binding and is therefore last in the build order.

## 12. Camera angle

Not a top-down GIS view. A slightly elevated oblique view, **35–50°**, so terrain
depth, buildings, roads, water, infrastructure and vehicles are all legible — a
miniature architectural model viewed from above. Then allow orbit, zoom, tilt and
focus.

Stored as `visualization.camera_tilt_degrees`.

## 13. A "hero region"

Don't render the entire country at maximum detail. The **affected region** is
visually rich; everything outside the crisis boundary becomes simpler, darker,
lower detail, contextual. That alone tells the operator: *this is the operational
area.*

Stored as `visualization.hero_region_bounds`.

## 14. Different visual states

The diorama shows knowledge about geography, so objects must express their
epistemic standing, not just their position.

> ### Amendment A4 — two axes, not five states
>
> The original five states — current, unverified, confirmed, forecast, historical —
> are **not mutually exclusive**. Epistemic status and temporal status vary
> independently: an entity can be simultaneously historical *and* unverified, or
> current *and* unverified.
>
> Encode as **two orthogonal visual channels**:
>
> | Axis | Channel | Driven by |
> | --- | --- | --- |
> | How much we believe it | **translucency** (provisional → solid) | `verification_status`, `EntityState.confidence` |
> | When it applies | **saturation** (faded → full) | `valid_until`, forecast vs. current |
>
> This is nearly free, because both channels read fields the world model has to
> carry anyway.

## 15. Data fog

A subtle uncertainty field, so the environment communicates *"we don't know
everything equally well"*:

```
CONFIDENT    ████████
LESS CERTAIN ▓▓▓▓▓▓▓
UNKNOWN      ░░░░░░░
```

Cheap and conceptually strong: it is a kernel density of observation **recency**,
computed from `EntityState.recorded_at` against the per-type freshness thresholds
the world model already defines. The fog is literally *"where have we not looked
lately."*

## 16. Don't make it look like a game

**Avoid:** Fortnite-style graphics, cartoon people, giant glowing icons, sci-fi
holograms, excessive particle effects, cyberpunk neon, floating 3D text everywhere.

**Instead:** serious, spatial, elegant, operational.

> ### Amendment A7 — the shader-binding rule
>
> This section and item 7 look contradictory: item 7 asks for *"soft particle / flow
> fields"* while this one forbids *"excessive particle effects."* They are not in
> conflict. The real distinction is **data-bound versus decorative.**
>
> Hazards may use detailed shaders and particle systems, on one condition: **every
> parameter reads a world-model value.** Smoke advects along a wind vector rather
> than a noise field; water-surface agitation scales with the *rate of change* of
> stage; fire emission scales with spread rate; rain density reads a rainfall figure.
>
> **When the numbers stop moving, the effect stops moving.** An effect still
> animating over static state is lying about liveness, which is a worse failure than
> looking plain.
>
> Corollary, to keep this section's ban on glowing icons and neon intact: exactly
> **one** emissive material is permitted anywhere in the scene — an active fire core.
> Everything else is lit, not glowing.
>
> Specifications per hazard in [`entity-rendering.md`](entity-rendering.md).

The goal is *"this is a real computational model of the physical world"* — not
*"this is a futuristic dashboard."*

## 17. The ideal final composition

```
                  LIVE CRISIS MODEL
      ┌───────────────────────┐
      │        █████          │
      │      ████████         │
      │  ~~~~~ FLOOD ~~~~     │
      │ ~~~~~~~~~~~~~~~~      │
      │  ─────R14─────✕ B7    │
      │       🚚 →             │
      │   ███████████         │
      │   POPULATION DENSITY  │
      │           🏥          │
      │       → → →           │
      │     DISPLACEMENT      │
      └───────────────────────┘
```

with the actual 3D terrain underneath all of it. Surrounding UI stays minimal:

- **Left** — crisis pulse
- **Centre** — the 3D world
- **Right** — selected object / context
- **Bottom** — timeline

---

## Render contract

**The rule: a visual channel may only exist if this table names the world-model
field that drives it.** Anything not listed here has no authority to appear on
screen. This is what keeps the diorama a read of the world model rather than a
second source of truth.

| Visual channel | Driven by | Notes |
| --- | --- | --- |
| Terrain base | DEM (static reference data) | Not world-model state. Exaggerated per `visualization.vertical_exaggeration`. |
| Water surface height | gauge `EntityState.attributes.stage_m` | The single scalar behind the whole flood. |
| Wet extent | breach-seeded fill over DEM below stage | Seeds are `breach:*` entities in a critical state. Derived, never authored. |
| Cyclone track + uncertainty cone | `Forecast` track positions, seeded from the `noaa-tcr-al122005` best track | Ghosted per item 14 — a track is a forecast, never observed state. |
| Cyclone wind / rain footprint | hazard `EntityState.attributes` intensity field | Intensity as a field, not a boundary. |
| Wildfire perimeter | fire hazard entity `geometry` + `EntityState.state` | Advancing boundary. Requires a seeded fire entity; not renderable until one exists. |
| Wildfire burn scar | persistent terrain-surface change | Outlives the perimeter, so it is state rather than an effect. |
| Landslide debris path | slide hazard entity `geometry`, applied as a DEM modification | The only hazard that alters the terrain surface rather than layering over it. |
| Smoke / heavy rain observation loss | drives the item 15 data fog | Not a bespoke layer. Degraded observation is degraded observation, whatever caused it. |
| Hazard-blocked route segment | intersected segment `EntityState.state` | Same channel as flood-submerged segments, for every hazard type. |
| Building form | footprint (static) × `Entity.type` | Semantic 3D; height from type, not measurement. |
| Population density | census-block geometry × block population, on the shared 30 m grid | Gridded, not per-zone scalars. Full contract in [`population-density.md`](population-density.md#render-contract-additions). |
| Zone fill colour | `Forecast.probability` (shortage) | |
| Zone extrusion height | `EntityState.attributes.water_hours` | |
| Zone pulse | equity-floor violation from `Plan.equity_notes` | |
| Route segment style | per-segment `EntityState.state` | Requires segmented route geometry. |
| Dependency arcs | `relationships.active` | Snap when deactivated. |
| Entity translucency | `verification_status`, `EntityState.confidence` | Axis 1 of amendment A4. |
| Entity saturation | `valid_until`, forecast vs. current | Axis 2 of amendment A4. |
| Data fog | `EntityState.recorded_at` vs. per-type freshness TTL | Kernel density of recency. |
| Unverified ping | `CandidateEvent` | Grey pulse; **entity colour must not change**. Restraint made visible. |
| Verified flip | `VerifiedEvent` emission | Shockwave at the moment belief changes. |
| Route ghost → solid | `Plan.status` pending → `Permit.status` active | The governance gate, in space. Vehicles travel solid routes only. |
| Vehicle position | `ExecutionTask.status` + route progress | |
| Vehicle SUSPENDED flash | `ExecutionTask.status == SUSPENDED` | The climax beat. |
| Displacement flow | shelter `attributes.occupancy` deltas | Amendment A3. Observed movement only. |
| Provenance thread | `source_event_id` → verified event → claims → observations | On click. Proves state isn't hallucinated. |
| Hero region dimming | `visualization.hero_region_bounds` | |
| Time scrubber | `get_state_at(T)` | Replay data already exists; append-only log. |
| Atmosphere | *(nothing)* | No world-model binding. Cosmetic, therefore last. |

## Build triage

The full spec is a much larger visual scope than a hackathon supports. Ranked by
impact per hour.

**Tier 1 — build these.** The DEM bowl with declared exaggeration; the
breach-seeded flood fill driven by the stage scalar; segmented route polylines with
per-segment state; the two-channel epistemic/temporal encoding; the unverified
ping that deliberately does *not* change entity colour; the ghost → solid permit
transition; the provenance thread on click.

**Tier 2 — if time holds.** The cyclone projected track, uncertainty cone and wind
footprint, which are cheap because the NHC best track is already a committed source
and which give the forecast rendering state something real to express; semantic
building extrusion; population density from census blocks; vehicles animating along
real polylines; hero-region dimming; the 3-stop time scrubber.

**Tier 3 — the multi-hazard proof.** Wildfire (perimeter, smoke, burn scar) and
landslide (slope failure, debris path, blocked road). These follow the Katrina
content rather than competing with it, because each needs its own seeded hazard
entities before it can render at all. Their value is architectural: they demonstrate
the diorama renders *hazards* generally rather than being hardwired to floods.
Landslide is the more expensive of the two, since it is the only hazard that
modifies the DEM.

**Deferred.** The atmosphere layer; data fog as a true interpolated surface;
displacement particles.

Nothing is cut. The scope discipline lives in the ordering and in amendment A5's
rule that a hazard needs a world-model binding before it renders — not in dropping
capability from the spec.

**Fallback.** The 2D dashboard remains the WebGL-failure path, and playback is
driven by the deterministic runner so the scene is rehearsable frame-for-frame.

## Data this requires

New reference geometry, none of which the world model currently holds. Each needs a
`source_key` row in `data/SOURCES.md` **with a geometry-vintage field**:

- **Terrain DEM** — NOAA Digital Coast lidar preferred, chosen for *vintage* rather
  than resolution; USGS 3DEP as the fallback, which is post-2005 and will therefore
  skew the derived flood extent under amendment A2.
- **Census 2000 TIGER/Line blocks** — the geometry behind the density field.
- **Road centrelines** — segmented, for per-segment state.
- **Building footprints** — for semantic extrusion.
- **Water-surface elevation series** — the stage scalar over time.
- **Terrain / basemap tiles** — the rendering substrate.
- **NHC best track** — track positions, intensity and timing for the cyclone
  treatment. Already committed as `noaa-tcr-al122005`, so the cyclone variant needs
  no new source; only the seeded track entities.

Wildfire and landslide have **no external source** for this scenario, since neither
occurred. They require seeded hazard entities, which must be labelled as synthetic
wherever they appear — a demonstration of the renderer, not a claim about Katrina.

> ### The geometry-vintage trap
>
> Current OSM data includes the Twin Span that was **rebuilt in 2011**, plus
> post-Katrina levee works. Rendering 2005 with today's road network is exactly the
> sourcing error this project exists to catch. Every geometry source must carry the
> vintage of the data, and where modern geometry is used to depict 2005 that
> substitution must be stated explicitly rather than passed off silently.
