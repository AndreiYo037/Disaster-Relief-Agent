# Population Density Heat Map — Design of Record

**Status:** design of record (andrei, 2026-09-04).

A **live human population density heat map** inside the Crisis World Model /
Situational Awareness 3D interface. Its purpose is to let an operator immediately
understand:

> **Where people are concentrated throughout the affected region, where population
> density is highest, and how that population distribution is changing during the
> crisis.**

This is a **population-density visualization, not an incident map.**

**Related documents.** This expands and supersedes item 3 of
[`3d-diorama.md`](3d-diorama.md), which sketched the density field in one paragraph.
The diorama doc remains authoritative for terrain, hazards, camera and the overall
visual language; this doc is authoritative for everything population.

## 0. The governing principle

Promoted from §33 because everything else is subordinate to it.

> **The population layer is a visualization of the Crisis World Model, not a
> separate source of truth.**

```
POPULATION DATA
      ↓
NORMALIZATION
      ↓
WORLD MODEL
      ↓
POPULATION STATE
      ↓
POPULATION VISUALIZATION
      ↓
3D CRISIS MODEL
```

**Do not store separate conflicting population state inside the frontend.** The
frontend renders what the World Model holds; it never computes a population figure
of its own.

The final experience should make the operator immediately understand
**"where are the people?"** and then **"where are the people who are most exposed,
displaced, isolated, underserved, or likely to need assistance next?"**

## Amendment index

Eight amendments were made during review. Each is marked inline. **P1 is an action
item against a file that already exists.**

| # | Section | Amendment |
| --- | --- | --- |
| **P1** | 28. Legend interaction | ⚠ **Contradiction with existing code.** `parameters.json` currently hard-codes universal density bin edges, which §28 forbids. Bins must be dataset-derived. |
| P2 | 13, 32. Examples | The example figures are **schema shapes, not scenario data**. Canonical values come from `parameters.json` and the seeded entities. |
| P3 | 11–12. Hazard overlay | Exposure is an **elementwise grid join** if the population grid matches `visualization.flood_grid_resolution_m`. Align them. |
| P4 | 17. Forecast population | Requires a **third forecaster** that does not yet exist. Monte Carlo, never LLM, and must carry a `world_snapshot_id`. |
| P5 | 24–25. Storage / performance | PostGIS, COG and vector tiles are the **production** target. The hackathon path is pre-tiled static assets over SQLite. |
| P6 | 5 vs 29. Visual priority | §5 and §29 conflict internally. Resolved by distinguishing **foundational from salient**. |
| P7 | 30. Privacy | The aggregation floor must be an explicit **parameter**, not an implementation detail. |
| P8 | 23. API | Path prefix aligned to the existing world-state API surface. |

---

## 1. Core visualization

Render the overall human population throughout the affected region as a
**continuous spatial heat map**, covering the entire affected region rather than
only individual affected people or incident locations. Use a continuous density
surface rather than thousands of individual markers.

```
LOW POPULATION
░░░░░░░░░░░░░░

MEDIUM
▒▒▒▒▒▒▒▒▒▒▒▒▒▒

HIGH
██████████████

VERY HIGH
███████████████
```

Spatially continuous, so operators immediately identify population concentrations.

## 2. 3D integration

Integrated into the existing 3D Crisis World Model, **not** a separate 2D widget.
The layer follows the terrain and renders as a spatial surface over the affected
region.

The operator can rotate, zoom, tilt, inspect, change altitude, view density
relative to terrain, and toggle the layer on and off.

**Do not obscure buildings, roads, bridges or major infrastructure unnecessarily.**

## 3. Population data

Support density data at different spatial resolutions. Potential inputs: raster
population grids, gridded datasets, census-derived spatial data, WorldPop-style
grids, LandScan-style grids, humanitarian population estimates, internally derived
estimates, dynamically updated displacement estimates.

Normalize these into a common geospatial population representation.

**Do not assume one population dataset is always authoritative.**

Store per dataset: `source`, `dataset version`, `spatial resolution`, `timestamp`,
`estimated population`, `uncertainty`, `geographic coverage`, `provenance`.

## 4. Density calculation

Calculate density appropriately for the underlying spatial unit.

```
raster:   population_density = population_in_cell / cell_area
polygon:  population_density = population / polygon_area
```

**Do not compare raw population counts between differently sized spatial units
without normalization.**

## 5. Heat map visual language

A restrained, professional gradient. The hierarchy communicates
`LOW → MODERATE → HIGH → VERY HIGH`.

**Avoid excessive saturation.** The layer must remain readable alongside terrain,
flood, fire, roads, bridges, infrastructure and logistics, and **must not visually
overpower critical operational information.**

## 6. Legend

A clear legend, in **meaningful units** — `people / km²` — rather than arbitrary
colour values.

```
POPULATION DENSITY
Low       ───────────────
Medium    ───────────────
High      ───────────────
Very High
```

## 7. Affected region mask

The heat map supports an affected-region boundary, and the interface must
distinguish **TOTAL** from **AFFECTED** from **DISPLACED** population.

**Do not interpret total population density as affected population.** The base
heat map is the overall human population. Crisis-specific overlays then show
affected, displaced, vulnerable, currently isolated, and hazard-exposed population.

> This is the single most important correctness rule in the document. Conflating
> total with affected inflates every downstream figure — exposure, shelter
> pressure, resource demand — and those figures feed Planning.

## 8. Multi-layer population view

Sublayers: **Overall Population** (total density), **Affected Population**,
**Displaced Population** (moved from normal location), **Vulnerable Population**
(where appropriately aggregated), **Population Movement** (directional flows).

Default view: **Overall Population Density**, because the purpose of the layer is
to show the human geography of the affected region.

## 9. Dynamic crisis updates

The layer updates as new data arrives.

```
09:00  North District population density
  ↓
11:00  displacement detected
  ↓
13:00  population concentration increases around Shelter Cluster B
  ↓
15:00  shelter area becomes highly concentrated
```

**Do not redraw the entire world when only a small region changes.** Use
incremental updates where practical — which the append-only state log already
supports via a `whats_changed_since(timestamp)` query.

## 10. Displacement overlay

Toggleable `Population Movement`. When enabled, movement flows render over the
density surface.

```
████████████
███████ →→→→
███████ →→→
████████
```

Shows origin, destination, direction, relative flow magnitude, and newly emerging
concentrations.

**Do not display individual people. Use aggregated flows.**

Note the constraint inherited from amendment A3 of the diorama doc: flows may only
be drawn from **observed** movement (shelter occupancy deltas between snapshots),
never from simulated trajectories.

## 11. Hazard + population overlay

The most important analytical interaction: **Population × Hazard.**

```
Population density
        +
Flood extent
        ↓
Population exposed to flood
```

Also support population + fire, landslide, cyclone, conflict, heat, and
infrastructure disruption.

## 12. Population exposure

Calculate `population inside hazard area`, `population near hazard`,
`population isolated`, `population without access`.

```
FLOOD EXPOSURE
Population exposed:       18,400
High-density population:   6,200
Displaced:                 4,100
Shelter capacity:          3,600
```

**These metrics derive from spatial joins and World Model state, never from
manually entered values.**

> ### Amendment P3 — exposure is an elementwise grid join
>
> This is cheaper than it looks, because of amendment A2 in the diorama doc.
>
> Flood extent is already *derived* as a grid: the breach-seeded fill over the DEM
> below the current stage, at `visualization.flood_grid_resolution_m` (30 m). If the
> population raster is resampled to **the same grid and resolution**, then
> population exposure is an elementwise multiply and sum — no geometry library, no
> polygon intersection, no resampling at query time.
>
> `exposed = sum(population_grid * wet_mask)`
>
> Two consequences worth acting on:
>
> 1. **Align the population grid to the flood grid** at seed time. A single shared
>    grid definition makes every population × hazard overlay in §11 the same
>    operation with a different mask.
> 2. **Exposure inherits the DEM's vintage problem.** Because the wet mask is
>    derived from the DEM, a post-Katrina DEM produces a wrong flood mask and
>    therefore a wrong exposure count. Exposure figures must be validated against
>    `fema-motf-flood-extent` and `usgs-hwm-2005`, and divergence recorded.

## 13. Click interaction

Clicking a high-density region opens a context panel.

```
ZONE B
Population         12,400
Density            8,420 / km²
Affected            8,900
Displaced           4,200
Projected 12h      18,200
Shelter occupancy      92%
Water availability      18h
Hazard exposure       HIGH
[VIEW POPULATION] [VIEW FORECAST] [VIEW RESOURCES]
```

> ### Amendment P2 — these figures are schema shapes, not scenario data
>
> The numbers above (and the "NORTH DISTRICT FLOOD" scenario in §32) illustrate the
> **shape** of the panel. They are not the Katrina scenario and must not be seeded.
>
> Canonical values live in `data/katrina/parameters.json` and the seeded entities.
> For `zone:B` that is a population of **14,008** (2000 Census, Lower Ninth Ward)
> and **8.0** water-hours, not 12,400 and 18h. The density figure must be *computed*
> from census-block geometry, never asserted — §4 exists precisely to prevent an
> unnormalized figure being typed in.
>
> Any panel field that has no backing World Model state should render as `—`, not
> as a plausible placeholder.

## 14. Spatial drill-down

`REGION → DISTRICT → ZONE → SETTLEMENT → LOCAL AREA`, with the heat map adjusting
resolution as the operator zooms. Broad density surface at regional level, more
detail at district level, higher resolution at neighbourhood/facility level where
available.

**Do not expose false precision when high-resolution population data is
unavailable.**

> Architectural note: this is the same principle as the forecaster's
> `insufficient_evidence` output. The population layer must be able to **decline to
> render** at a resolution its data cannot support, rather than interpolating a
> confident-looking surface. Declining is a feature.

## 15. Semantic zoom

Detail increases as the camera approaches the ground:
`population density → district population → settlement population → shelter /
facility population`.

**Avoid thousands of labels.**

## 16. Live vs historical

Integrated with the Crisis World Model timeline, supporting `LIVE` and `REPLAY`.

```
08:00  population distribution
  ↓
12:00  displacement begins
  ↓
16:00  new population concentration
  ↓
20:00  shelter cluster overloaded
```

Dragging the timeline updates the visualization to the historical state, so the
operator can answer **"where were people concentrated at 14:00?"**

This is nearly free: the append-only entity-state log means `get_state_at(T)`
already reconstructs any past population state without a replay engine.

## 17. Forecast population

In Forecast Mode, show projected distributions at `CURRENT / 6H / 12H / 24H`.

```
CURRENT      12,400
12H FORECAST 18,200
24H FORECAST 21,500
```

**Projected population must be visually distinct from observed/current
population. Do not display forecast population as if it were currently observed.**

> ### Amendment P4 — this requires a third forecaster that does not exist
>
> The system currently has two forecasters: resource depletion and route risk.
> Projected population distribution is a **third**, and it is the most demanding of
> the three because its output is spatial rather than scalar.
>
> Three non-negotiables inherited from the forecasting layer:
>
> 1. **Monte Carlo, never the LLM.** The model may narrate the projection; it may
>    never produce the numbers. A hallucinated displacement figure is exactly the
>    failure this product exists to prevent.
> 2. **Every projection carries a `world_snapshot_id`.** A forecast that cannot name
>    the state it assumed cannot be invalidated when that state changes.
> 3. **`insufficient_evidence` is a valid output.** Displacement is the named main
>    uncertainty in the depletion forecaster already; a spatial projection of it will
>    frequently be too uncertain to render, and rendering it anyway is worse than
>    rendering nothing.
>
> Scope-wise this is Tier 3 work. The demo can carry §17 as a designed capability
> with the current-state view working and the forecast toggle disabled.

## 18. Uncertainty

Represent uncertainty explicitly. **Avoid false precision.**

```
Population estimate:  12,400
Range:                11,200–14,100
Confidence:           Moderate
Source:               population_dataset_v4
Last updated:         42m ago
```

This maps onto existing state fields: `EntityState.confidence` and the coarse
`label` (`known | likely | uncertain | conflicted | stale`), rendered through the
belief axis of amendment A4 (translucency).

## 19. Data freshness

Population information has **different** freshness characteristics: census is a
slow-changing baseline, population grids are periodic, shelter registration changes
rapidly, aggregated mobility is near-real-time.

Represent `source timestamp`, `observation timestamp`, `last update`, `freshness`.

The per-type freshness thresholds already exist in configuration; population
sources need their own entries, because a census baseline going "stale" after an
hour is meaningless while a shelter headcount going stale after an hour is critical.

## 20. Population + infrastructure

Analyse density alongside roads, bridges, hospitals, shelters, water points,
warehouses, power and communications.

```
HIGH POPULATION DENSITY
        +
NO OPEN ROAD
        ↓
ISOLATED POPULATION CLUSTER
```

**The World Model identifies these relationships** — via the existing dependency
propagation, not in the frontend.

## 21. Population + resource access

Identify areas with high population and low water, food, medicine, shelter capacity
or healthcare access.

```
Population:       12,400
Water:                18h
Hospital access:     LOW
Shelter:              92%
Road access:     DEGRADED
```

**This is the important bridge to Planning** — it is the visual form of the input
the allocator consumes.

## 22. Population + equity

Support population-aware equity analysis.

```
Zone C
Population:            9,800
Vulnerable:            3,100
Current allocation:    below minimum floor
```

**Do not automatically interpret density as vulnerability. Population density and
vulnerability are separate dimensions.**

> This agrees with what is already recorded in `parameters.json`:
> `zone_C_vulnerability` is annotated as *"a policy weight, not a measured
> vulnerability index."* The two documents are consistent, and both must stay that
> way — the moment density starts driving vulnerability, the equity floors stop
> being a policy decision and become a derived statistic that no human authorised.

## 23. Population density API

> ### Amendment P8 — prefix aligned
>
> The spec proposed `/world-state/population/*`. Aligned to the existing world-state
> surface as `/api/world-state/population/*` so there is one API root. Semantics
> unchanged.

```
GET /api/world-state/population
GET /api/world-state/population/density
GET /api/world-state/population/affected
GET /api/world-state/population/displaced
GET /api/world-state/population/movement
GET /api/world-state/population/exposure
```

Supporting `bbox`, `time`, `resolution`, `region`, `scenario`:

```
GET /api/world-state/population/density?bbox=...&resolution=...&timestamp=...
```

The `timestamp` parameter is the same mechanism as `get_state_at(T)`; §16's replay
and this API are one feature.

## 24. Data storage

Candidates: PostGIS, raster storage, vector tiles, object storage,
cloud-optimized GeoTIFF, tiled spatial formats.

**For large population rasters, do not load the entire dataset into the browser.**
Use server-side tiling, raster tiles, vector tiles, level-of-detail.

## 25. Rendering performance

Must remain performant over large geographic regions. **Do not render every person,
every population record, or full-resolution global rasters.** Use tiled data, level
of detail, aggregation, GPU rendering, progressive loading, viewport-based fetching.

> ### Amendment P5 — production target versus hackathon path
>
> §24 and §25 describe the production architecture and are correct as such. They
> also conflict with the committed stack, which is a **single SQLite store** with
> PostGIS explicitly marked "introduce later."
>
> **Hackathon path:** the hero region is small (roughly 0.7° × 0.45°) and the grid
> is 30 m, which is a few hundred thousand cells — small enough to pre-tile at seed
> time into static assets served from disk and rendered on the GPU by deck.gl. No
> tile server, no PostGIS, no runtime raster pipeline.
>
> **The architectural trigger for the swap** is a second region or a full-resolution
> national grid. Until one of those exists, tiling infrastructure is scope with no
> demo payoff.

## 26. Colour / semantic separation

The population gradient must remain distinguishable from hazard overlays: hazards
get hazard-specific spatial treatment, forecasts a projected treatment, uncertainty
a softened treatment.

**Do not create a visually ambiguous layer where population density looks like
flood intensity.**

> Concrete rule, since this is the most likely visual failure: the flood already
> occupies *volume* (extruded water surface following terrain) under amendment A2,
> so population should occupy **surface** — a draped, unextruded gradient. Different
> geometry, not merely a different palette. A colour-only distinction will fail the
> moment someone tilts the camera.

## 27. UI layer control

```
POPULATION
☑ Overall population
☐ Affected
☐ Displaced
☐ Vulnerable
☐ Movement
☐ Forecast
```

Default: `Overall population = ON`, everything else off.

## 28. Population legend interaction

Hovering the legend explains the ranges:

```
Population density
0  ↓  5k / km²  ↓  10k / km²  ↓  25k / km²
```

Use **actual dataset-specific ranges. Do not hard-code misleading universal
thresholds.**

> ### ⚠ Amendment P1 — contradiction with a file that already exists
>
> `data/katrina/parameters.json` currently contains:
>
> ```
> "population_density_bin_edges_per_km2": { "value": [1000, 3000, 6000] }
> ```
>
> Those are exactly the hard-coded universal thresholds this section forbids. They
> were written before this spec existed and are wrong as a default.
>
> **Required change.** Bin edges become **derived from the loaded dataset's
> distribution** — quantile breaks, or Jenks natural breaks over the actual cell
> values within the hero region. The fixed array survives only as an explicitly
> labelled fallback for when no dataset is loaded, and the legend must always show
> the *computed* edges with real units.
>
> This matters beyond aesthetics. Fixed bins that don't match the data will either
> flatten New Orleans into one uniform "high" blob or push the entire city into the
> top bin, and in both cases the operator loses exactly the signal — relative
> concentration — that the layer exists to convey.

## 29. Visual priority

The World Model visually prioritizes, in order: **human population**, current
hazards, critical infrastructure, operational resources, logistics, forecasts,
supporting information.

**The human population is the central spatial reference for the humanitarian
mission.**

> ### Amendment P6 — foundational is not the same as salient
>
> §29 puts population first; §5 says the layer must not overpower operational
> information; the diorama's item 9 says most of the environment stays calm and only
> important things become visually active. Read naively, §29 contradicts both.
>
> The resolution is that **priority and salience are different axes.** Population is
> *foundational*: always on by default, drawn beneath everything else, and the
> spatial frame the operator reads every other layer against. It is not *salient*:
> it does not pulse, glow or animate, and it yields contrast to hazards, failures
> and active missions.
>
> Being the base map of the humanitarian mission is a more important role than being
> the brightest thing on screen.

## 30. Safety / privacy

**Never expose unnecessary individual-level location.** Do not render individual
phone locations, individual refugee locations, identifiable patient locations, or
individual movement trajectories. Use aggregated spatial representations.

> ### Amendment P7 — the aggregation floor is a parameter
>
> "Aggregated" without a threshold is unenforceable. A 30 m cell containing three
> people is individual-level data wearing a raster's clothing.
>
> Add `population.min_aggregation_cell_count` as an explicit parameter. Cells below
> it are suppressed or merged upward before the grid ever leaves the server — not
> hidden in the renderer, where a network inspector defeats it.
>
> This connects to the existing `sensitivity` and `reporter_identity` classification
> on `Observation`: privacy is enforced at the boundary the data crosses, in both
> cases.

## 31. Test data

Realistic test data containing dense urban population, medium-density zones, rural
population, flood-affected areas, displaced population, shelter clusters, roads,
hospitals, warehouses and vehicles — demonstrating
`population density → hazard exposure → displacement → shelter pressure → resource
demand`.

## 32. Demo scenario

The spec's illustrative scenario:

```
NORTH DISTRICT FLOOD
Population:          150,000
Affected:             82,000
Displaced:            31,000
Highest-density zone:  Zone B
Flood extent:      increasing
Shelter capacity:         92%
Water:                    18h
```

```
HIGH POPULATION + FLOOD + DISPLACEMENT → HIGH HUMANITARIAN PRESSURE
```

Per amendment P2 this is a shape, not the scenario. The bound equivalent is
Katrina: Orleans and St. Bernard Parish as the region, the Lower Ninth Ward
(`zone:B`) and Convention Center (`zone:C`) as the density peaks, the
breach-seeded flood as the hazard, and the Superdome-to-Convention-Center movement
as the displacement — all with the real figures from `parameters.json` once
verified.

## 33. Technical principle

Promoted to [§0](#0-the-governing-principle).

---

## Population state — data contract

What the World Model must hold for any of the above to render. Per §3, no single
dataset is authoritative, so provenance is per-dataset rather than global.

| Field | Purpose |
| --- | --- |
| `dataset_id`, `version` | Which population product this came from |
| `source`, `provenance` | §3 provenance chain |
| `spatial_resolution_m` | Drives §14 drill-down and the §4 normalization |
| `grid_definition` | Shared with the flood grid per amendment P3 |
| `timestamp`, `observed_at`, `recorded_at` | §19 freshness, and the bitemporal split |
| `estimated_population` | The raw count, before normalization |
| `population_density` | Computed per §4, never stored as input |
| `uncertainty_range`, `confidence` | §18 |
| `geographic_coverage` | Where this dataset is valid at all |
| `population_class` | `total` / `affected` / `displaced` / `vulnerable`, per §7 |

## Render contract additions

Extends the contract in [`3d-diorama.md`](3d-diorama.md#render-contract). Same rule:
a channel with no world-model driver does not render.

| Visual channel | Driven by | Notes |
| --- | --- | --- |
| Overall density surface | population grid, `population_class = total` | Draped surface, not extruded — amendment P6 and §26. |
| Density colour bins | dataset-derived quantile/Jenks breaks | Amendment P1. Never fixed universal edges. |
| Affected population | `population_class = affected` | Distinct sublayer, never inferred from total (§7). |
| Displaced population | `population_class = displaced` | |
| Vulnerable population | `population_class = vulnerable` | Policy classification, not derived from density (§22). |
| Movement flows | shelter `occupancy` deltas between snapshots | Diorama amendment A3. Observed only. |
| Hazard exposure | `sum(population_grid * hazard_mask)` | Amendment P3. Elementwise on the shared grid. |
| Isolated cluster | high density ∧ no active route | Via dependency propagation (§20). |
| Forecast distribution | displacement forecaster + `world_snapshot_id` | Amendment P4. Ghosted; disabled until the forecaster exists. |
| Density uncertainty | `confidence`, `uncertainty_range` | Softened treatment per §26. |
| Suppressed cells | `min_aggregation_cell_count` | Amendment P7. Suppressed server-side. |
| Declined resolution | dataset `spatial_resolution_m` vs. zoom | §14. Renders as "insufficient resolution", not interpolation. |

## Build triage

**Tier 1.** The overall density surface from census blocks on the shared 30 m grid;
dataset-derived bins with a real `people/km²` legend; click-to-inspect on
`zone:B` / `zone:C` with `—` for unbacked fields; the layer toggle; and the
population × flood exposure join, which is nearly free once the grids align and is
the single most analytically convincing element.

**Tier 2.** Affected and displaced sublayers; timeline replay of the density surface
(cheap — `get_state_at(T)` already exists); uncertainty rendering; freshness
indicators; the isolated-cluster relationship from §20.

**Tier 3.** Forecast population distribution and its new forecaster (amendment P4);
semantic zoom and full drill-down; movement flow rendering.

**Production.** Tiling infrastructure, PostGIS, COG, vector tiles, viewport fetching
(amendment P5); vulnerable-population sublayer, which needs a governed
classification rather than a rendering decision.

## Definition of done

The 16 criteria from §34, kept verbatim, with hackathon reachability marked.

| # | Criterion | Hackathon |
| --- | --- | --- |
| 1 | Affected region displays a continuous population-density heat map | ✅ |
| 2 | Heat map rendered within the 3D terrain | ✅ |
| 3 | Density normalized spatially | ✅ |
| 4 | Affected, displaced and total population distinguishable | ◐ total + affected |
| 5 | Population data has source/provenance metadata | ✅ |
| 6 | Population estimates have timestamps/freshness | ✅ |
| 7 | Map updates as World Model state changes | ✅ |
| 8 | Historical population state can be replayed | ✅ |
| 9 | Forecast population visualized separately | ✗ Tier 3 |
| 10 | Population combinable spatially with hazards | ✅ |
| 11 | Population combinable with infrastructure/access | ◐ |
| 12 | High-density areas selectable and inspectable | ✅ |
| 13 | Large datasets remain performant | ✅ within the hero region |
| 14 | No unnecessary individual-level data exposed | ✅ |
| 15 | Frontend reads population state from the World Model | ✅ |
| 16 | Density visually distinguished from hazard intensity | ✅ surface vs. volume |

Criterion 9 is the only outright gap, and amendment P4 explains why: it needs a
forecaster the system does not have. Criteria 4 and 11 are partial rather than
missing.
