# Design log

Running record of decisions and open questions across all 3 profilers.
Add an entry whenever a real decision gets made in discussion - keeps
context from getting lost between sessions.

## tlf-geo-profiler

- **Monorepo, not 3 separate repos** (2026-09-20): profilers share
  dependencies and Profiler 2 consumes Profiler 1 directly; splitting
  now would mean version-pinning overhead on code that isn't stable yet.
- **Ward boundary source: CONFIRMED - OpenStreetMap Nepal** (2026-09-21).
  Verified via a live Overpass query: 6,738 of Nepal's official 6,743
  wards (99.93%) exist as real admin_level=9 polygon relations with
  ward number + name, including remote areas (Simkot, Humla). Exported
  as GeoJSON, cleaned (14 invalid geometries repaired with buffer(0),
  0 lost), converted to GeoParquet (133MB -> 18.7MB, zstd compression),
  bundled into the package at `data/wards.parquet`.
- **`resolve_ward()` and `resolve_admin_unit()` in `boundaries.py` are
  real and tested** - spatial-index point-in-polygon lookup (geopandas
  `sindex`), verified against Kathmandu, Pokhara, and remote Humla
  coordinates, ~3ms per lookup.
- **Known limitation, not yet solved**: the ward file only carries
  ward name/number - no district or province. Ward names CANNOT be
  string-parsed to get the municipality's district (confirmed: 143
  municipality names, e.g. "Kalika", are reused across different,
  unrelated districts). District/province/municipality need their own
  boundary layer, resolved spatially the same way - candidate: check
  whether OSM's higher admin levels (admin_level 4/6/7) are similarly
  complete, to keep one consistent data source rather than mixing in
  HDX's COD-AB dataset and risking boundary-edge mismatches between
  two different sources at the same coordinate.
- **Postal codes**: not in OSM as polygon data. Nepal Post publishes a
  flat district-level code list - join by district, not by point-in-polygon.
- **Open**: how much demographic depth to return by default (population
  count only vs. full CBS breakdown via tlf-core's existing vocabulary);
  also unconfirmed whether CBS publishes population data down to ward
  level or only to municipality level.

## tlf-disaster-profiler

- Input is a CAP (Common Alerting Protocol) message: area as `polygon`,
  `circle`, or `geocode`, plus `category`/`event`/`urgency`/`severity`/
  `certainty` metadata (all standard CAP fields, filled in by the issuing
  authority - e.g. DHM for hydromet hazards).
- Nepal's DHM ran a national CAP training with WMO (Apr 2025) and has a
  draft national implementation plan - CAP is a real direction, not
  hypothetical, but likely no live production feed yet. Early dev will
  need sample/hand-built CAP test messages.
- Depends on tlf-geo-profiler for the population-count part of the
  exposure profile; adds roads/buildings/facilities from OSM entity layers.

## tlf-db-profiler

- Working hypothesis (unconfirmed with senior): profiles an unfamiliar
  civic dataset's schema against tlf-core's field registry, flagging
  known-vs-unmapped fields.
- tlf-core's registry is currently CBS-census-shaped only - has ~nothing
  to match against BIPAD-style incident/damage data. Plan: (1) seed a
  disaster-domain vocabulary using the existing Youth Innovation Lab
  report's field-mapping tables (DesInventar/BIPAD/Nepal Police), and
  (2) treat "unmapped field" as a useful output on its own, not a failure.
- LLM fallback for fields the registry can't match: registry match first
  (deterministic), LLM only for genuine unknowns, suggestions stored with
  a confidence score and require human confirmation before being accepted
  into the registry - never auto-accepted, to avoid silently corrupting
  civic data mappings.
