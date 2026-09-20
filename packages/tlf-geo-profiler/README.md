# tlf-geo-profiler

Given a coordinate in Nepal, resolve it to an administrative unit
(Province -> District -> Local Level -> Ward -> Tole -> postal code)
and attach a demographic profile for that unit.

## Status

Scaffolding only. Open decisions before this does anything real:

- **Boundary data source**: checking OSM Nepal coverage for ward-level
  polygons (province/district/local-level relations look solid; wards
  are patchy outside a few cities). See `docs/decisions.md` in the repo root.
- **Postal codes**: not spatial data in OSM - will need a separate
  Nepal Post district-level lookup table joined in by district.
- **Demographic depth**: population-only vs. full CBS category
  breakdown (reusing `tlf-core`'s existing vocabulary) - not yet decided.

## Layout

- `boundaries.py` - coordinate -> admin unit (point-in-polygon)
- `demographics.py` - admin unit -> demographic stats (meant to reuse tlf-core)
- `profiler.py` - public `profile(lat, lon)` entry point
