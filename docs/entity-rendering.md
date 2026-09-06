# Entity Rendering & Symbol Registry — Design of Record

**Status:** design of record (andrei, 2026-09-04).

How every entity, resource, hazard, event and geography feature is represented in
the 3D scene. This document is authoritative for **form** — meshes, symbols,
shaders, particles and level of detail.

**Related documents.** [`asset-definitions.md`](asset-definitions.md) is the live
Katrina catalog: 44 instances, registry categories, realloc/evacuate/population
toggles, always-on hazards (flood, fire, contamination, cyclone), and per-sequence
binds. [`3d-diorama.md`](3d-diorama.md) is authoritative for terrain, camera, visual
language and the master render contract.
[`population-density.md`](population-density.md) is authoritative for everything
population. This document adds two amendments to the diorama doc, recorded there as
**A6** (per-type models) and **A7** (the shader-binding rule).

## 0. Governing principles

Three rules, in priority order. Everything below is an application of them.

### 0.1 Type-level semantics — distinct models per *type*, never per instance

Item 2 of the diorama doc requires that *"the shape itself communicate what
something is."* That is a statement about **categories**, not individuals.

A bespoke mesh per instance would defeat it: if every hospital looks different,
"hospital" stops being readable at a glance, and the asset pipeline grows without
bound. So the ~22 entity types get ~22 meshes, and instances differentiate through
**state channels** — colour, translucency, saturation, readouts — never through
geometry.

> **The one sanctioned exception is structural failure.** A severed bridge must
> *look* severed; recolouring it red is not enough when the entire mid-run beat is
> that the crossing is gone. Types whose failure is geometric (`bridge`, `breach`,
> `landslide` runout) carry a second **state mesh variant**. This is an enumerated
> exception, not a general licence.

### 0.2 The shader-binding rule — every effect parameter reads a world-model value

The diorama doc appears to contradict itself here: item 7 calls for *"soft particle
/ flow fields"* while item 16 forbids *"excessive particle effects."* It does not
actually conflict — the distinction is **data-bound versus decorative.**

So: no shader or particle parameter may be a constant chosen for mood. Smoke
advects along a wind vector; water-surface agitation scales with the *rate of change*
of stage; fire emission scales with spread rate; rain density reads a rainfall
figure. **When the numbers stop moving, the effect stops moving.** An effect that
keeps animating while state is static is lying about liveness.

Corollary: exactly one emissive material is permitted in the entire scene — an
active fire core. Everything else is lit, not glowing. Item 16 bans glowing icons
and neon; item 9 requires most of the scene to stay calm.

### 0.3 Registry-driven — no hardcoded type logic

Form is declared as **data**, in a symbol registry (§2). The renderer contains no
`if type == "hospital"` branching.

**An entity type with no registry row does not render.** This is the same discipline
the diorama's render contract imposes on visual channels, applied to form.

## 1. The six category grammars

| Category | Primitive | Distinct per | Geometry changes with state? |
| --- | --- | --- | --- |
| Infrastructure | textured mesh (glTF) | type | only the enumerated failure exceptions |
| Resources | mesh + capacity readout | type, split static/mobile | no |
| Hazards | shader / volume, **not** mesh | hazard type | n/a — hazards *are* their geometry |
| Events | transient symbol, decays | event type | no — events mutate other entities |
| Geography | line + fill, no mesh | admin level | no |
| Populations | draped surface only | `population_class` | no — never a mesh |

### 1.1 Infrastructure — mesh

Physical, sited, persistent. Rendered as a simplified mesh at real coordinates,
extruded or placed on the exaggerated terrain. State drives material, not form,
except for the failure exceptions in §0.1.

### 1.2 Resources — two grammars in one category

Resources split by whether they move, and the two need genuinely different display:

**Static stock** — warehouse, food POD, medicine cache, fuel depot, water point.
A fixed mesh carrying a **capacity readout**: stock against capacity as a fill on
the base of the model. This is also what §12 of the population doc needs for
shelter pressure, and what the current entity attributes lack — occupancy exists,
capacity does not.

**Mobile** — vehicle, personnel unit. A moving mesh constrained to route geometry.
Per the master render contract, a mobile resource **may only travel a solid route**,
never a ghosted (pending-approval) one, and flashes in place when suspended.

### 1.3 Hazards — shader and volume

Hazards are not objects with a model; they are fields with an extent. They render
as volumes and surfaces driven by state, detailed in §3.

Per amendment A5, each hazard needs a world-model binding before it renders at all.

### 1.4 Events — transient symbol that decays into a state change

Events are the category most at risk of becoming permanent map furniture, which
item 9 explicitly guards against. An event symbol **appears, plays briefly, then
decays**, and what persists afterwards is the *state change it caused* plus its row
in the change feed and the provenance thread.

Events also carry the epistemic channel most visibly: an **unverified** event is a
grey ping that leaves the affected entity's colour **unchanged**, and only a
verified event produces the shockwave and writes state.

### 1.5 Geography — line and fill

Boundaries and containers, never meshes: an outline plus an optional low-opacity
fill, draped on terrain. Region and district outlines give the drill-down hierarchy;
zone rings demarcate the operational units the allocator works over; the operational
area is the hero-region mask; service areas are catchments.

### 1.6 Populations — draped surface only, never a model

**Population gets no 3D model and no person geometry, ever.** Three separate rules
converge on this: amendment P6 and §26 of the population doc require a draped,
unextruded surface specifically so density cannot be mistaken for flood volume;
item 16 bans cartoon people; and §30's privacy floor forbids individual-level
representation outright.

The integration points with entity rendering are therefore indirect, and that is
deliberate:

- **Zone entities take their fill from the density field**, so geography and
  population are the same read rather than two competing surfaces.
- **Shelters and camps are the nodes where the field concentrates** — the mesh is
  the facility, the pressure is the field around it.
- **Movement renders as a flow field** from observed occupancy deltas only, never
  as individual tracks.

## 2. Symbol registry

Held as data. One row per type.

**Row schema:** `type` · `category` · `primitive` · `asset_near` · `symbol_far` ·
`base_form` · `state_channels` · `state_mesh_variants` · `fallback_2d`

### Infrastructure

| `type` | Near-field form | Far symbol | Notes |
| --- | --- | --- | --- |
| `bridge` | deck spanning two banks on pylons | short span bar | **failure variant:** deck section dropped off its pylons |
| `route` | extruded ribbon along polyline | line | parent; state carried by segments |
| `route_segment` | ribbon section | — | the actual state carrier for closure and submersion |
| `road` | extruded ribbon, narrower | line | |
| `hospital` | cruciform block, taller, roof mast | cross | power-dependent; shows capacity |
| `clinic` | small single-storey cruciform | small cross | |
| `shelter` | wide low span-roof structure | roof glyph | capacity readout required |
| `school` | rectilinear block with courtyard | block glyph | often an impromptu shelter |
| `power` | stack and switchyard lattice | bolt | the cascade linchpin |
| `water` | treatment basins and tank | droplet | |
| `pump` | squat housing with outfall channel | impeller | drainage; power-dependent |
| `breach` | levee wall segment with a notch | notch glyph | **failure variant:** notch opens, becomes a flood seed |
| `port` | quay with gantry cranes | crane glyph | |
| `airport` | runway strip with tower | runway glyph | |
| `comm` | lattice mast with dishes | mast glyph | |
| `gauge` | slim staff gauge post at the water's edge | tick glyph | **drives the entire flood** — see §3.1 |

### Resources

| `type` | Near-field form | Far symbol | Grammar |
| --- | --- | --- | --- |
| `warehouse` | large flat industrial shed | shed glyph | static stock |
| `vehicle` | tanker truck | chevron | mobile |
| `personnel` | clustered tents and vehicles | chevron group | mobile |
| `food` | palletised crate stacks | crate glyph | static stock |
| `medicine` | field-hospital tenting with cases | case glyph | static stock |
| `fuel` | cylindrical tank farm | tank glyph | static stock |

### Geography

| `type` | Form | Notes |
| --- | --- | --- |
| `region`, `district` | outline, no fill | drill-down hierarchy |
| `zone` | ring outline + density-derived fill | fill comes from the population field |
| `settlement` | outline at higher zoom only | subject to the false-precision rule |
| `camp` | outline + occupancy node | population node |
| `hazard_area` | outline tracking hazard extent | derived, not authored |
| `operational_area` | hero-region mask | everything outside dims |
| `service_area` | catchment outline, low opacity | hospital / warehouse / POD reach |

### Hazards

| `type` | Primitive | See |
| --- | --- | --- |
| `flood` | extruded water volume | §3.1 |
| `cyclone` | track + swept cone + draped field | §3.2 |
| `fire` | advancing perimeter + advected smoke | §3.3 |
| `landslide` | DEM modification + debris mesh | §3.4 |

Earthquake, drought, heat, conflict and disease are ontology-complete but have no
Katrina binding and no registry rows yet.

## 3. Hazard shader specifications

Each parameter below names the state value it reads. Anything not bound is not
permitted (§0.2).

### 3.1 Flood — the primary hazard

- **Surface height** ← gauge `attributes.stage_m`. The single scalar behind
  everything.
- **Extent** ← breach-seeded connected fill over the DEM below stage, at
  `visualization.flood_grid_resolution_m`. Derived, never authored.
- **Depth opacity** ← stage minus ground elevation, per cell.
- **Surface agitation amplitude** ← *rate of change* of stage. Rising water moves;
  standing water is still. This is the clearest example of the binding rule: the
  demo's flood is dramatic precisely when it is actually rising.
- **Foam line** ← the wet/dry boundary cells.
- **No emissive, no glow.** Water is lit.

### 3.2 Cyclone

- **Track** ← forecast track positions, seeded from the NHC best track. Renders
  **ghosted**, because a track is a forecast and item 14 governs forecast state.
- **Uncertainty cone** ← the forecast's spread, as a translucent swept hull.
- **Wind footprint** ← intensity as a draped scalar field, not a boundary.
- **Rain particles** ← vertical streaks, density bound to a rainfall figure.

### 3.3 Fire

- **Perimeter** ← fire entity geometry, advancing.
- **Emissive core** ← the *only* sanctioned emissive material in the scene, and only
  while the fire is active.
- **Smoke** ← particles advected along the wind vector, not a noise field.
- **Burn scar** ← a persistent terrain material change; it outlives the perimeter,
  so it is state rather than an effect.
- **Smoke degrades observation quality downwind**, feeding the data fog rather than
  getting its own treatment.

### 3.4 Landslide

- **Slope failure** ← a DEM modification at the source. The only hazard that alters
  the terrain surface rather than layering over it, and therefore the most expensive.
- **Debris path** ← run-out corridor mesh.
- **Dust** ← particles decaying with time since the event.
- **Blocked segments** ← the route segments the debris path intersects, using the
  same channel as flood submersion.

## 4. Event symbols

Eight event types. Each has a symbol, the entity class it mutates, and a decay. All
of them render grey and non-mutating while unverified.

| Event | Symbol | Mutates | Persists as |
| --- | --- | --- | --- |
| `infrastructure_damage` | fracture mark on the entity | bridge / road / facility state | new entity state + failure mesh variant |
| `road_closure` | barrier chevrons across the segment | `route_segment` state | segment restyled per item 8 |
| `displacement` | flow seed at origin, pulse at destination | population fields, shelter occupancy | updated density + occupancy |
| `service_interruption` | snapped link on the dependency arc | power / water / hospital state | deactivated relationship |
| `supply_shortage` | draining fill on the resource readout | warehouse / zone demand | reduced stock |
| `facility_closure` | shutter glyph over the facility | hospital / shelter / airport state | state change |
| `security_event` | muted marker, deliberately understated | optional | feed entry |
| `hazard_expansion` | expanding rim on the hazard boundary | flood stage / fire perimeter | new hazard extent |

## 5. Level of detail

Distinct per-type meshes collide with §15 semantic zoom and item 25 performance, so
**every mesh type needs an LOD pair**: a near-field mesh and a far-field billboard
symbol, switching at `visualization.lod_switch_altitude_m`.

The ladder, from the population doc's §15 and the diorama's §14:

```
regional altitude   → far symbols, density surface, region outlines
district altitude   → near meshes appear, zone rings, district density
zone altitude       → full meshes, segments, capacity readouts
facility altitude   → shelter and facility population, individual readouts
```

Per §14 of the population doc, the scene must **decline to add detail** it has no
data for rather than interpolating a confident-looking surface.

## 6. Asset budget

- **22 mesh types × 2 LODs ≈ 44 assets**, plus 3 failure variants.
- **4 hazards: 0 meshes** (shaders and volumes), except the landslide debris mesh.
- **7 geography types: 0 meshes** (lines and fills).
- **8 event symbols**: 2D sprites, not meshes.

Format: glTF for meshes, rendered through a scenegraph/mesh layer; sprites for
symbols. Assets are static reference data and belong beside the other reference
geometry, never in the world model.

This budget is the real cost of the per-type decision, and the reason per-instance
models were rejected: per-instance would multiply 44 by the entity count.

## 7. 2D fallback degradation

The 2D dashboard remains the WebGL-failure path, so each grammar needs a defined
collapse:

| Grammar | 2D fallback |
| --- | --- |
| Infrastructure mesh | typed icon at the same coordinate |
| Resource mesh + readout | icon plus a numeric stock/capacity field |
| Hazard shader | flat polygon at the derived extent |
| Event symbol | change-feed row only |
| Geography line + fill | the same outline, unshaded |
| Population surface | choropleth by zone |

Nothing in the fallback is a different *fact* — only a simpler rendering of the same
state.

## 8. Build triage

**Tier 1.** The registry mechanism itself; far symbols for all types (cheap, and
they alone make the scene legible); near meshes for the seven canonical entity types
plus `breach`, `power` and `gauge`; the bridge failure variant; the flood shader with
stage, extent and depth bound; the event grammar for `infrastructure_damage` and
`road_closure`; zone rings and the operational-area mask.

**Tier 2.** Remaining near meshes; capacity readouts; the LOD switch; cyclone track
and cone; the remaining event symbols; service-area catchments.

**Tier 3.** Landslide shaders, including the DEM modification; the full
semantic-zoom ladder; rain particles bound to a rainfall figure.

Live Katrina already ships flood HUD bowls, fire particles, Murphy Oil
contamination fill, and the cyclone track (see [`asset-definitions.md`](asset-definitions.md)).
Landslide stays **off**. Do not treat fire/contamination as unbuilt.

**Constraint that overrides all three tiers:** a far symbol with correct state
colour beats a beautiful mesh with wrong state. Form is subordinate to the render
contract.
