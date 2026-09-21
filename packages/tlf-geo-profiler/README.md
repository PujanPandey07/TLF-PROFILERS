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
