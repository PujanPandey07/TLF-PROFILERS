# tlf-geo-profiler

Given a coordinate in Nepal, resolve it to an administrative unit
(Province -> District -> Local Level -> Ward -> Tole -> postal code)
and attach a demographic profile for that unit.

## Status

Boundary resolution works at all four levels: `resolve_admin_unit(lat, lon)`
returns province, district, local level (with type) and ward from bundled
OpenStreetMap Nepal boundaries. Still open:

- **Demographics** are not wired up (`profile()` still raises
  `NotImplementedError`). OSM local levels carry no official CBS/LGD code, so
  joining census data needs a crosswalk table.
- **Postal codes**: not spatial data in OSM - separate Nepal Post
  district-level lookup joined by district.
- **4 local levels (Butwal, Nepalgunj, Duduwa, Sainamaina)** are derived from
  their wards because the OSM export lacked them - see `docs/decisions.md`.
- Points in areas OSM assigns to no ward (e.g. protected areas) resolve to
  province + district only.

Rebuild the boundary layers with `scripts/build_admin_layers.py`.

## Layout

- `boundaries.py` - coordinate -> admin unit (point-in-polygon, 4 layers)
- `scripts/build_admin_layers.py` - Overpass GeoJSON -> bundled GeoParquet
- `demographics.py` - admin unit -> demographic stats (meant to reuse tlf-core)
- `profiler.py` - public `profile(lat, lon)` entry point

## Known limitations of the data (OpenStreetMap)

- **4 local levels are derived, not taken from OSM:** Butwal, Nepalgunj,
  Duduwa and Sainamaina were missing from the level-7 export. Their shapes
  are built by merging their wards and marked
  `local_level_source="derived_from_wards"`, with no local-level type. A
  later query found real OSM outlines for Butwal and Sainamaina, identical
  to the derived shapes. None was found for Nepalgunj or Duduwa.
- **5 wards are missing from OSM:** Nepalgunj-15, Pyuthan-2, Sarumarani-1,
  Nisikhola-7 and Nisikhola-8. A point there resolves to its local level
  with `ward=None`.
- **About 8% of Nepal's land has no ward polygon** (mostly protected
  areas). Such points resolve to province and district only, and
  sometimes local level.
- **13 wards have wrong ward numbers in OSM** (typos, superscript digits,
  duplicates). They are corrected in `data/ward_number_fixes.csv`.
- **No official codes:** OSM local levels carry no CBS/LGD code, and names
  repeat across districts, so census data can't be joined by name alone.
