# Sources

Citation table for every number in `data/katrina/parameters.json` and every piece of
reference geometry consumed by the diorama (`docs/3d-diorama.md`). The contract is
one-directional and enforceable: **every `source_key` in `parameters.json` must
resolve to a row in this file, and every row must carry a real source, a URL, and
a retrieval date before its parameters can be marked `verified`.**

> **Retrieved 2026-09-04.** Rows marked retrieved were opened and the cited
> figure copied. FEMA MOTF shapefiles and USGS NWIS 2005 IHNC series were **not**
> retrieved as files; flood *extent* uses the HUD/NOAA 31 Aug planning-district
> table, and flood *stage* on 29 Aug uses the IHNC Lock staff hydrograph.

## Primary sources

| `source_key` | Source | URL | Retrieved | Status |
| --- | --- | --- | --- | --- |
| `sphere-handbook` | Sphere Handbook 2018 — Water supply standard 2.1, 15 L/person/day | https://interactive.spherestandards.org/ | 2026-09-04 | retrieved |
| `census-2000-sf1` | U.S. Census 2000 SF1 — neighborhood populations via The Data Center (`data/katrina/sourced/neighborhoods_census2000.json`) | https://www.datacenterresearch.org/data-resources/neighborhood-data/ | 2026-09-04 | retrieved |
| `datacenter-nola` | The Data Center — Orleans neighborhood 2000 populations; Orleans Parish total 484,674 | https://www.datacenterresearch.org/ | 2026-09-04 | retrieved |
| `house-select-katrina` | House Select Committee — *A Failure of Initiative*, H. Rpt. 109-377. NG estimate 19,000 at Convention Center (evac. ch., fn. 114). Louisiana water pre-stage 36 trucks × 18,000 L = 648,000 L at Camp Beauregard 28 Aug (preparation ch., fn. 4) | https://biotech.law.lsu.edu/katrina/govdocs/109-377/evac.pdf ; https://govinfo.library.unt.edu/katrina/preparation.pdf | 2026-09-04 | retrieved |
| `whitehouse-katrina-lessons-ch3` | White House *The Federal Response to Hurricane Katrina: Lessons Learned*, ch. 3 — “10,000 - 12,000 people at the Superdome by midnight” (Sunday 28 Aug), fn. 139 | https://georgewbush-whitehouse.archives.gov/reports/katrina-lessons-learned/chapter3.html | 2026-09-04 | retrieved |
| `nyt-superdome-2005-09-01` | NYT, 1 Sep 2005, “Superdome: Haven Quickly Becomes an Ordeal”, dateline 31 Aug — “20,000 or more” | https://www.nytimes.com/2005/09/01/us/nationalspecial/superdome-haven-quicklybecomes-an-ordeal.html | 2026-09-04 | retrieved |
| `convention-center-headcount` | Superseded by `house-select-katrina` | — | 2026-09-04 | superseded |
| `noaa-tcr-al122005` | NOAA NHC TCR AL122005 Table 1 best track; Buras landfall 1110 UTC 29 Aug, 110 kt, 29.3N 89.6W | https://www.nhc.noaa.gov/data/tcr/AL122005_Katrina.pdf | 2026-09-04 | retrieved |
| `usace-ipet` | IPET Vol. V — 17th St / London Ave / IHNC breach timings; IHNC peak ~14.2 ft NAVD88 ~09:00 29 Aug. IHNC Lock staff hydrograph (05:00 10.3 ft → 09:00 14.3 ft → 10:00 12.3 ft) in `data/katrina/sourced/ihnc_lock_hydrograph.json` | https://biotech.law.lsu.edu/katrina/ipet/gpo/Vol%20V%20The%20Performance%20Levees%20and%20Floodwalls%20-%20maintext.pdf | 2026-09-04 | retrieved |
| `usgs-katrina-surge` | USGS NWIS — intended IHNC/NOLA stage series. Station 073802332 (IHNC at Seabrook) **has no 2005 data** (period starts 2017). Substituted: IHNC Lock staff hydrograph under `usace-ipet` | https://waterdata.usgs.gov/nwis | 2026-09-04 | not retrieved (no 2005 series) |
| `usgs-circ-1306-ch3d` | USGS Circ. 1306 ch. 3D — Twin Span rendered unusable; 38 EB + 20 WB spans dislodged | https://pubs.usgs.gov/circ/1306/pdf/c1306_ch3_d.pdf | 2026-09-04 | retrieved |
| `usgs-circ-1306-ch3h` | USGS Circ. 1306 ch. 3H — inundation; Dartmouth Flood Observatory polygons 30 Aug / 2 Sep; city volume ~85e9 gal 30 Aug, ~131e9 gal 2 Sep. DFO GIS URL 404; volume not bound as stage | https://pubs.usgs.gov/circ/1306/pdf/c1306_ch3_h.pdf | 2026-09-04 | retrieved |
| `hud-noaa-flood-2005-08-31` | HUD overlay of NOAA 31 Aug 2005 flood depths on Orleans planning districts. Housing-unit table: Mid-City 23,651 flooded … Algiers / French Quarter / New Aurora-English Turn = 0. `data/katrina/sourced/hud_flood_districts.json` | https://nola.gov/nola/media/Safety-and-Permits/floodplain-management/Extent-Depth-of-Flooding-Katrina.pdf ; https://www.huduser.gov/periodicals/cityscpe/vol9num1/ch9.pdf | 2026-09-04 | retrieved |
| `fema-dr1603` | FEMA — Louisiana Hurricane Katrina disaster declaration (DR-1603-LA) | https://www.fema.gov/disaster/1603 | — | not retrieved |
| `epa-murphy-oil-katrina` | EPA / Wikipedia — Murphy Oil Meraux tank 250-2, ~25,110 barrels mixed crude, ~1,700 homes / ~1 sq mi in Chalmette–Meraux, 30 Aug 2005. Geometry is a class-area sketch, not EPA GIS. `data/katrina/sourced/katrina_contamination.json` | https://archive.epa.gov/katrina/web/html/index-6.html ; https://en.wikipedia.org/wiki/Murphy_Oil_USA_refinery_spill | 2026-09-06 | retrieved |
| `wikipedia-katrina-nola-fires` | Wikipedia *Effects of Hurricane Katrina in New Orleans* — fire at 329 Tchoupitoulas St photographed 2 Sep 2005; Mandeville Street Wharf and 3200 Chartres St also cited. Point sites. `data/katrina/sourced/katrina_fires.json` | https://en.wikipedia.org/wiki/Effects_of_Hurricane_Katrina_in_New_Orleans | 2026-09-06 | retrieved |

### URL confidence

Treat the URLs above as the pages actually opened on 2026-09-04 for retrieved rows.
`waterdata.usgs.gov/nwis` was opened: station 073802332 has no 2005 series.
`fema.gov/disaster/1603` is still a lead, not a citation. FEMA MOTF GIS was not
downloaded; flood extent on stage is the HUD/NOAA 31 Aug district table, labelled
as such.

## Reference geometry sources

Consumed by the diorama (`docs/3d-diorama.md`), not by the layer logic. These are
**static reference data**, never world-model state — the diorama reads geometry from
here and state from `EntityState`.

Every row carries a **vintage**, because geometry has a date and using the wrong one
silently misrepresents 2005. See the geometry-vintage trap below.

| `source_key` | Source | URL | Vintage | Retrieved | Status |
| --- | --- | --- | --- | --- | --- |
| `noaa-digitalcoast-lidar` | NOAA Digital Coast — coastal lidar / DEM for southeast Louisiana; **preferred** terrain source if 2005-era coverage exists | https://coast.noaa.gov/dataviewer/ | **TO DETERMINE** — check for a pre- or immediately-post-Katrina survey | — | not retrieved |
| `usgs-3dep-dem` | USGS 3D Elevation Program — DEM for Orleans and St. Bernard Parish; fallback terrain source | https://apps.nationalmap.gov/downloader/ | modern (post-2005) | — | not retrieved |
| `census-2000-tiger-blocks` | U.S. Census 2000 TIGER/Line — block geometry behind the population density field | https://www.census.gov/geographies/mapping-files/time-series/geo/tiger-line-file.html | **2000 — correct vintage** | — | not retrieved |
| `osm-roads` | OpenStreetMap major highways in the hero region (`data/katrina/sourced/osm_roads.json`) | Overpass API | **current — WRONG vintage for 2005** | 2026-09-04 | retrieved |
| `osm-buildings` | OpenStreetMap building footprints, semantic extrusion by type (`data/katrina/sourced/osm_buildings.json`) | Overpass API | **current — WRONG vintage for 2005** | 2026-09-04 | retrieved |
| `osm-extract-nola` | Combined OSM extract: roads, canals, buildings | https://overpass-api.de/api/interpreter | **current — WRONG vintage for 2005 (Twin Span is the 2011 rebuild)** | 2026-09-04 | retrieved |
| `esri-world-imagery` | Esri World Imagery — geographically accurate orthophoto basemap (no API key). The Twin Span visible is the 2011 rebuild. | https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer | **modern — labelled on screen** | 2026-09-04 | retrieved |
| `aws-terrain-tiles` | AWS Open Data Terrain Tiles (Terrarium) — **not used**; terrain layer was removed from the diorama | https://registry.opendata.aws/terrain-tiles/ | modern | — | not used |
| `usgs-hwm-2005` | USGS / FEMA Hurricane Katrina **high-water marks** — observed flood depths, used to validate the derived breach-fill extent against reality | **URL TO CONFIRM** | 2005 — correct vintage | — | not retrieved |
| `fema-motf-flood-extent` | FEMA Modeling Task Force — Katrina observed flood extent polygons. **Not retrieved as GIS.** Stage substitute: `hud-noaa-flood-2005-08-31` planning-district rings | **URL TO CONFIRM** | 2005 — correct vintage | 2026-09-04 | not retrieved (GIS); HUD table used instead |
| `hud-noaa-flood-2005-08-31` | HUD / NOAA — 31 Aug 2005 flood-depth overlay by Orleans planning district; rings in `data/katrina/sourced/hud_flood_districts.json` | https://nola.gov/nola/media/Safety-and-Permits/floodplain-management/Extent-Depth-of-Flooding-Katrina.pdf | **2005-08-31 — correct vintage** | 2026-09-04 | retrieved |

The stage time series that drives the water surface comes from the existing
`usgs-katrina-surge` row under [Primary sources](#primary-sources); it now has two
consumers, the sensor-threshold path in Perception and the diorama's water height.

### Vintage legend

- **correct vintage** — the data dates from 2005 or earlier and can depict the
  scenario directly.
- **modern** — usable only where the underlying feature is unlikely to have changed
  (broad terrain relief, coastline). Must be labelled where it appears.
- **WRONG vintage** — the feature demonstrably changed after 2005. Requires an
  explicit, documented substitution, not silent use.

## Non-source keys

These two keys exist so that **every** parameter has a resolvable `source_key` and
none can hide as an unattributed literal. They are declarations that a number is a
choice rather than a measurement.

| `source_key` | Meaning |
| --- | --- |
| `design:tuned-for-demo` | A calibration decision made so the demo behaves as designed. Not a claim about the world. If it appears on screen it must be labelled as a modelling assumption. |
| `design:derived` | Computed from other parameters. Must never be hand-edited; change its inputs instead. |

## Verification protocol

To move a parameter from `unverified` to `verified`:

1. Retrieve the source and record the URL actually used plus today's date in the
   table above.
2. Record the precise locator — table number, page, gauge ID, census tract set, or
   IPET volume and section — in the parameter's `note`. "It's in the IPET report"
   is not a citation.
3. Replace the value with the sourced figure. If it differs from the current value,
   re-check the `derivations.invariants` list in `parameters.json`, because several
   demo beats depend on specific inequalities holding.
4. Flip `status` to `verified`.

## Known conflicts to resolve during verification

**The Sphere rate halves or doubles every equity floor.** If the current edition's
standard is 7.5 L/person/day rather than 15, the summed floors drop from 495,120 L
to 247,560 L and the staging volume, convoy size, and scripted MODIFY all need
recomputing.

**The Twin Span's destruction predates the relief window.** `usace-ipet` and
`noaa-tcr-al122005` should confirm the collapse occurred during landfall on 29 Aug,
roughly two days before demo t0. This is not a problem to fix but the fact the
bitemporal design depends on, so the sourced timestamp must go into
`chronology.bridge_B7_collapse_valid_from` exactly as found.

**Real resupply delay breaks the forecast band.** Sourcing the actual convoy delay
(on the order of 72 hours) will contradict `resupply_eta_mu_hours: 12.0`. The
resolution is to keep the sourced figure visible as the event-scale reality while
scoping the forecast claim to `horizon_hours`, not to quietly keep the tuned number.

**Neighborhood boundaries are not census geographies.** The Lower Ninth Ward figure
depends on which tracts are aggregated. Record the tract list, or `datacenter-nola`
and `census-2000-sf1` will disagree and neither will be reproducible.

**The geometry-vintage trap.** Current OpenStreetMap data includes the I-10 Twin
Span that was **rebuilt in 2011**, along with post-Katrina levee and floodwall
works. Rendering 2005 with today's road network is exactly the sourcing error this
project exists to catch — and it is worse in the diorama than in a table, because a
3D scene reads as observation rather than as a claim.

Two rules follow. Any feature drawn from a modern source must be labelled as such in
the scene's provenance panel, not just in this file. And `bridge:B7` in particular
must use 2005 geometry or an explicitly annotated substitution, since the entire
mid-run beat depends on that structure being severed — depicting the rebuilt span
would contradict the event the demo is about.

**The DEM is probably post-Katrina.** `usgs-3dep-dem` reflects topography surveyed
after the storm, after scour, subsidence and levee reconstruction. Since flood extent
is *derived* from the DEM under amendment A2, a post-2005 surface will produce a
flood footprint that differs from what actually happened. This is why
`noaa-digitalcoast-lidar` is listed first and why `fema-motf-flood-extent` and
`usgs-hwm-2005` matter: the derived fill needs validating against observed extent and
depths, and any divergence recorded rather than tuned away.
