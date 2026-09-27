# tlf-disaster-profiler

CAP-alert-driven disaster impact reports for Nepal: affected wards, population
and household estimates, and hazard-specific infrastructure impact, built on
[tlf-geo-profiler](../tlf-geo-profiler).

## Usage

### Generate a full HTML report

```python
from tlf_disaster_profiler import build_report, render_html

with open("alert.xml", encoding="utf-8") as f:
    cap_xml_text = f.read()

report, wards_gdf = build_report(cap_xml_text)
html = render_html(report, wards_gdf)

with open("disaster_report.html", "w", encoding="utf-8") as f:
    f.write(html)
```

Ward boundary data is found automatically from the installed `tlf-geo-profiler`
package — you don't need to locate or pass `wards.parquet` yourself. To override
it (e.g. testing against a different boundary file), pass it explicitly:

```python
report, wards_gdf = build_report(cap_xml_text, wards_parquet_path="/custom/path/wards.parquet")
```

### Include full building/road detail layers (opt-in, heavier)

```python
report, wards_gdf = build_report(cap_xml_text, include_detail_layers=True)
```

Off by default — see the Overpass reliability notes below before turning this on
for a dense urban alert.

### Read the report dict directly, without generating HTML

`build_report()` returns plain dicts/lists, so you can use the data without ever
touching `render_html()`:

```python
for info in report["infos"]:
    print(info["event"], "-", info["headline"])
    for area in info["areas"]:
        if area["status"] != "ok":
            continue
        print(f"  {area['area_desc']}: "
              f"{area['total_population_affected']:,} people, "
              f"{area['total_households_affected']:,} households affected")
        for ward in area["wards"]:
            print(f"    Ward {ward['ward_no']} ({ward['local_level']}, "
                  f"{ward['district']}): {ward['coverage_pct']}% covered")
```

### Standalone functions — inspect one area without a full report

Useful in a notebook, or while debugging a new CAP source, without paying for a
whole report:

```python
from tlf_disaster_profiler.cap import parse_cap
from tlf_disaster_profiler.osm_query import (
    named_amenities_query, get_building_geometries, get_road_geometries,
)

alert = parse_cap(cap_xml_text)
area = alert["infos"][0]["areas"][0]  # a parsed circle/polygon area dict

amenities = named_amenities_query(area)  # schools, hospitals, pharmacies, etc. — one request
for category, result in amenities.items():
    if result["status"] == "ok" and result["count"]:
        print(category, result["count"])

buildings = get_building_geometries(area)   # full footprints — can time out, see below
roads = get_road_geometries(area)           # full polylines — same caveat
```

### Running the tests

```bash
uv sync
pytest tests/
```

These cover CAP parsing, `osm_query`'s parsing/merging/bucketing logic (Overpass
itself is mocked, so no network calls), and `overlap.py`'s geometry helpers
(against a small synthetic ward layout, not the real Nepal dataset) — see the
Overpass and boundary-data caveats below for what these tests intentionally don't
cover: live mirror behavior, real ward topology, and real population figures.

## Amenity coverage

Earlier versions only queried schools and hospitals (plus a generic `emergency=*`
category). The report now covers, per ward, in one combined Overpass request:
schools, hospitals, health posts/clinics, pharmacies, police, fire stations,
shelters, religious sites (often used as informal gathering/relief points in
Nepal), marketplaces, drinking-water sources, and general `emergency=*`
infrastructure. Buildings and roads remain shape-wide counts only (see below for
why). This list reflects what's realistically useful for disaster response, not
every amenity tag OSM supports — more can be added the same way if needed.

This piece is being published as its own package; a separate layer that uses an
LLM to add plain-language, Nepal-aware explanations on top of this structured
output is a planned follow-up, not part of this package.

## Known Limitations

This package produces a best-effort disaster impact report from a CAP alert. It is
built to degrade gracefully (nothing should crash the whole report), but "graceful"
is not the same as "accurate everywhere." Read this before treating any number here
as ground truth.

## Boundary & admin data

- Ward boundaries come from OpenStreetMap, not an official Nepal government source.
  A live Overpass check found 6,738 of 6,743 official wards (99.93%) mapped as
  `admin_level=9` relations — the remaining ~5 wards will simply not appear in any
  report, with no fallback.
- `nepalboundariespy` (the existing PyPI package for this) was tested and found
  unusable — its README documents a ward-level API and column names that don't
  exist in the data it actually ships. This project bundles its own cleaned OSM
  export instead, built and verified once, not fetched live.
- OSM boundary topology can have small gaps or slivers between adjacent wards. A
  point near a shared edge can occasionally resolve to the wrong ward, or to no
  ward at all — this is why amenities that fail to bin into any ward are shown as
  "unassigned" rather than silently dropped or silently misassigned.

## Population figures

- Population per ward comes from Nepal's 2021 census, joined by ward through
  tlf-geo-profiler's own admin-unit resolver — some wards may show population as
  `unknown` if that name resolution fails.
- **Population-affected is a uniform-density estimate**: `population × coverage_pct`.
  It assumes people are spread evenly across a ward's area, which is essentially
  never true (a ward's population is rarely uniform — settlements cluster, and the
  actual overlap area matters far more than raw ward area). Treat this number as a
  rough order of magnitude, not a precise headcount.

## OSM data coverage & the confidence label

- Every infrastructure/amenity count depends entirely on how well volunteers have
  mapped that specific area in OpenStreetMap. Rural or remote areas can be sparsely
  mapped — a "low" or zero count there may mean "poorly mapped," not "actually
  empty." The `confidence` label is a density-vs-threshold heuristic, not a
  ground-truth check, and it cannot tell the difference between those two cases.
- A `"status": "failed"` entry (query error, timeout) is deliberately kept distinct
  from a real zero count — but both can still under-report what's actually there.

## Overpass reliability

- The package depends on public Overpass API mirrors (overpass-api.de and others),
  which are shared community infrastructure with no SLA. They can rate-limit,
  block requests (HTTP 406) that don't send a proper User-Agent, or simply be slow
  or down. Multiple mirrors with retry/fallback are used, but if all of them are
  degraded at once, entire categories will come back as `"failed"`.
- **Named amenities are fetched in one combined request per area** (schools,
  hospitals, health posts, pharmacies, police, fire stations, shelters, religious
  sites, marketplaces, water sources, and `emergency=*` together) rather than one
  request per category — fewer round trips, less load on shared mirrors. The
  trade-off: if that one combined request fails, every one of those categories
  fails together (all show `"status": "failed"` with the same reason), whereas
  previously an unrelated category could still succeed independently.
- **Counts-only by default for buildings/roads.** Full-detail geometry queries for
  dense urban areas (or large-radius alerts) were found to time out during testing.
  The default report avoids this by requesting counts only. The optional detail
  layers (`include_detail_layers=True`, or the standalone `get_building_geometries`/
  `get_road_geometries` functions) carry the same timeout risk — they are opt-in
  for exactly this reason, and can still fail or return partial data on a big or
  dense alert area.
- There is no caching layer. Re-running the same or an overlapping area re-queries
  Overpass from scratch every time, which is both slower and puts more load on
  shared public infrastructure than necessary.
- No authentication or query-rate governance is implemented — sending many reports
  back-to-back risks temporary blocking by an Overpass mirror.

## River / flood-context data

- River names in OSM aren't standardized — the same river can appear under several
  spellings, or with/without "River"/"Nadi" suffixes. Deduping is a simple
  heuristic (lowercase, strip common suffixes) and can still either merge two
  different rivers with similar names, or fail to merge two spellings of the same
  one.
- Lakes and dams are not currently implemented in `flood_context` — only named
  rivers are queried and drawn.
- Many minor roads (tracks, footpaths, unclassified rural roads) have no `name`
  tag in OSM at all — common in hilly/rural areas. `get_road_geometries()` and
  `get_building_geometries()` fall back to labeling these by type (e.g. "Unnamed
  track", "Unnamed residential") instead of a bare "unnamed", so at least the
  road/building type is visible for triage — but the actual name, where OSM
  simply never recorded one, can't be recovered.

## Hazard-specific scope

- **Flood** gets a hazard-specific layer: nearby named rivers, drawn on the map, plus
  every amenity (school, hospital, health post, pharmacy, police, fire station,
  shelter, religious site, marketplace, water source, or emergency infrastructure)
  within 100m of one of those rivers is flagged `flood_risk` and shown in a
  different color, both on the map and in the ward table.
  This 100m check is a **straight-line proximity heuristic** — it does not account for
  terrain, elevation, or the real shape of a flood plain. A point 100m from a river on
  a hillside above it is not actually at flood risk; the flag doesn't know that.
- **Landslide** gets its own hazard-specific layer too: roads within the alert area,
  extended 100m past its drawn edge, shown as "potentially affected" in a distinct
  color on the map. Same straight-line-buffer caveat as above — real landslide runout
  is governed by slope and material, not a flat 100m ring, so this is a rough
  first-pass flag for which roads to check, not a validated impact assessment.
  Earthquake alerts still get **no** hazard-specific layer — OSM has no usable fault
  line, soil type, or slope data, and building-material tags are too sparse to support
  a meaningful vulnerability layer for earthquakes specifically.
- The landslide road buffer reuses the same heavier `out geom` road query as the
  opt-in detail layers, so it carries the same timeout risk on a large or oddly
  shaped alert area — see the Overpass section above.

## CAP source & parsing

- Nepal's own DHM CAP system is not live yet (still in draft/SOP stage). This
  package currently targets GDACS (gdacs.org) as its live feed for real earthquake
  and flood alerts, plus locally saved sample files for testing (GDACS alert files
  expire, so live testing against old alerts isn't possible).
- A CAP `<area>` with no `<circle>` or `<polygon>` — i.e. geocode-only, referencing
  a district or region code — is marked `"unsupported"` and skipped. There is no
  lookup table yet to resolve those codes into coordinates.

## Performance & environment

- Report generation makes live network calls (Overpass, OpenStreetMap tile
  servers) at build time — there is no offline mode.
- Turning on the detail layers for a dense urban alert can mean rendering tens of
  thousands of building polygons in the browser, which will noticeably slow down
  both page load and map interaction.
- A real `pytest` suite now covers CAP parsing, `osm_query`'s parsing/merging/
  bucketing logic, and `overlap.py`'s geometry helpers (see Usage above) — but it
  deliberately mocks Overpass and uses a synthetic ward layout rather than real
  Nepal data, so it verifies our own logic, not live Overpass behavior, real ward
  topology, or real population figures. There's no integration test against the
  actual bundled `wards.parquet` or a live Overpass mirror yet.
