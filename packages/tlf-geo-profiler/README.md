# tlf-geo-profiler

Given a coordinate in Nepal, resolve it to an administrative unit
(Province -> District -> Local Level -> Ward -> postal code)
and attach a demographic profile for that unit. Data is authentic as it is scrapped from CBS official website.

```python
>>> from tlf_geo_profiler import profile
>>> p = profile(27.7040, 85.3070)  # Kathmandu Durbar Square
>>> p.admin_unit.district, p.admin_unit.local_level, p.admin_unit.ward
('Kathmandu', 'Kathmandu', 24)
>>> p.demographics.population
4529
```

## Installation

```bash
pip install tlf-geo-profiler
```

Requires Python >=3.10. Pulls in `shapely`, `geopandas`, `pyarrow`, and
`tlf-geo`. All boundary and lookup data ships inside the package itself, so
there's nothing else to download and no network calls at runtime.

## Quickstart

```python
from tlf_geo_profiler import profile

p = profile(27.7040, 85.3070)

p.admin_unit       # AdminUnit(province="Bagmati", district="Kathmandu", ...)
p.demographics      # DemographicProfile(population=4529, households=1174, ...)
```

`profile(lat, lon)` is the only function most callers need. It returns a
`RegionalProfile`:

```python
@dataclass(frozen=True)
class RegionalProfile:
    admin_unit: AdminUnit
    demographics: DemographicProfile
```

### Coordinate order

Every public function takes **`(lat, lon)`**, i.e. `(27.7040, 85.3070)` for
Kathmandu, matching how coordinates are usually written and how you'd read
them off Google Maps. (Internally the library converts to `(lon, lat)` for
shapely/GeoJSON, but you never have to think about that.)

### Errors

`profile()` and `resolve_admin_unit()` raise `ValueError` if the coordinate
falls outside all four Nepal boundary layers entirely (e.g. the middle of
the ocean, or another country):

```python
>>> profile(0.0, 0.0)
ValueError: (0.0, 0.0) is outside all known Nepal boundaries
>>> profile(28.61, 77.21)  # Delhi
ValueError: (28.61, 77.21) is outside all known Nepal boundaries
```

They do **not** raise for a valid Nepal point that just lacks fine-grained
data (see "Handling remote/protected-area points" under Examples below) -
you get back an `AdminUnit` with some fields set to `None` instead.

## API reference

### `profile(lat: float, lon: float) -> RegionalProfile`

The full pipeline: resolves the admin unit, then looks up demographics for
it. This is what you want in almost all cases.

### Dict / JSON output

`RegionalProfile` has `.to_dict()` and `.to_json()` for when you want
everything as a plain, JSON-serializable structure (an API response, a
file, a message queue payload, etc.) instead of a dataclass:

```python
>>> from tlf_geo_profiler import profile
>>> p = profile(27.7040, 85.3070)
>>> p.to_dict()
{
    "admin_unit": {
        "province": "Bagmati", "province_code": "NP-P3",
        "district": "Kathmandu", "local_level": "Kathmandu",
        "local_level_type": "metropolitan", "local_level_osm_id": "relation/...",
        "local_level_source": "osm", "local_level_code": "32706",
        "ward": 24, "ward_osm_id": "relation/...", "tole": None,
        "postal_code": "3060824",
    },
    "demographics": {
        "population": 4529, "households": 1174,
        "male_population": 2382, "female_population": 2147, "extra": {},
    },
}
>>> p.to_json(indent=2)   # any kwargs are passed through to json.dumps
'{\n  "admin_unit": {\n    "province": "Bagmati",\n    ...\n}'
```

If you don't need the `RegionalProfile` object at all, there are two
one-call convenience wrappers that go straight from coordinate to plain
output:

```python
from tlf_geo_profiler import profile_dict, profile_json

profile_dict(27.7040, 85.3070)             # -> dict, same shape as .to_dict()
profile_json(27.7040, 85.3070, indent=2)   # -> str, same as .to_json(indent=2)
```

The dict is nested (`{"admin_unit": {...}, "demographics": {...}}`) rather
than flattened into one level, so field names never collide between the
two sub-objects. Every field is already a plain `str`, `int`, `dict` or
`None`, so no custom JSON encoder is needed.

### `resolve_admin_unit(lat: float, lon: float) -> AdminUnit`

Just the geographic part, if you don't need demographics. Returns:

```python
@dataclass(frozen=True)
class AdminUnit:
    province: str | None              # e.g. "Bagmati"
    province_code: str | None         # ISO 3166-2, e.g. "NP-P3"
    district: str | None              # e.g. "Kathmandu"
    local_level: str | None           # e.g. "Kathmandu"
    local_level_type: str | None      # metropolitan | sub_metropolitan
                                       # | municipality | rural_municipality
    local_level_osm_id: str | None    # e.g. "relation/1234567"
    local_level_source: str | None    # "osm" | "derived_from_wards"
    local_level_code: str | None      # crosswalked code used to join
                                       # postal codes & demographics
    ward: int | None                  # corrected ward number, e.g. 24
    ward_osm_id: str | None
    tole: str | None                  # currently always None - unimplemented,
                                       # see "Known limitations" below
    postal_code: str | None           # e.g. "3060824"
```

Example, printed in full:

```python
>>> from tlf_geo_profiler.boundaries import resolve_admin_unit
>>> resolve_admin_unit(27.7040, 85.3070)
AdminUnit(
    province='Bagmati',
    province_code='NP-P3',
    district='Kathmandu',
    local_level='Kathmandu',
    local_level_type='metropolitan',
    local_level_osm_id='relation/...',
    local_level_source='osm',
    local_level_code='32706',
    ward=24,
    ward_osm_id='relation/...',
    tole=None,
    postal_code='3060824',
)
```

### `resolve_ward(lat: float, lon: float) -> dict | None`

Lower-level lookup against just the ward layer, for when you only care
whether a point falls in a ward polygon and what OSM calls it. Returns
`None` (not an error) if the point isn't inside any ward polygon.

```python
>>> from tlf_geo_profiler.boundaries import resolve_ward
>>> resolve_ward(27.7040, 85.3070)
{'osm_id': 'relation/...', 'name': 'Kathmandu-24', 'ward': '24', 'ward_no': 24}
```

`ward` is the raw OSM tag (string, occasionally wrong - see below);
`ward_no` is the corrected integer and is what you should use.

### `get_demographics(local_level_code, ward_no=None) -> DemographicProfile`

Usually called for you inside `profile()`, but usable standalone if you
already have a `local_level_code` from somewhere else (e.g. cached from a
previous `resolve_admin_unit()` call, so you can skip the spatial lookup):

```python
@dataclass(frozen=True)
class DemographicProfile:
    population: int | None
    households: int | None
    male_population: int | None
    female_population: int | None
    extra: dict
```

```python
>>> from tlf_geo_profiler.demographics import get_demographics
>>> get_demographics("32706", ward_no=24)          # ward-level
DemographicProfile(population=4529, households=1174, male_population=2382, female_population=2147, extra={})
>>> get_demographics("32706")                       # no ward -> whole municipality
DemographicProfile(population=862400, households=238966, male_population=438256, female_population=424144, extra={})
```

If `ward_no` doesn't have ward-level data, or is omitted, you get the
figures summed across the whole local level. If `local_level_code` is
`None` or unrecognized, you get an empty `DemographicProfile()` (all
fields `None`) rather than an error - always check `population is not None`
before using the numbers.

## More examples

**Building a one-line summary for a point:**

```python
from tlf_geo_profiler import profile

def describe(lat, lon):
    p = profile(lat, lon)
    u = p.admin_unit
    where = " > ".join(filter(None, [u.province, u.district, u.local_level,
                                      f"Ward {u.ward}" if u.ward else None]))
    pop = f", pop. {p.demographics.population:,}" if p.demographics.population else ""
    return f"{where}{pop}"

>>> describe(29.9707, 81.8203)  # Simkot, Humla
'Karnali > Humla > Simkot > Ward 5, pop. 2,145'
```

**Handling remote/protected-area points that only resolve partially:**

```python
p = profile(27.5300, 84.3500)  # inside Chitwan, but no ward polygon here
p.admin_unit.district      # 'Chitwan'
p.admin_unit.ward          # None
p.admin_unit.local_level   # None
p.demographics.population  # None - no local_level_code to join demographics on
```

**Batch-processing a list of coordinates, tolerating out-of-Nepal points:**

```python
from tlf_geo_profiler import profile

points = [(27.7040, 85.3070), (28.2096, 83.9560), (0.0, 0.0)]
results = []
for lat, lon in points:
    try:
        results.append(profile(lat, lon))
    except ValueError:
        results.append(None)  # outside Nepal
```

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
  repeat across districts, so census data can't be joined by name alone;
  `local_level_code` comes from `tlf_geo.GeoResolver` matching name +
  district, and can occasionally fail to resolve (see below).
- **`AdminUnit.tole` is unused** - the field exists but nothing in
  `boundaries.py` ever populates it. Either wire it up or drop the field
  before relying on it.
- **Silent resolver misses:** if `tlf_geo.GeoResolver.resolve()` can't
  match a local level's name, `local_level_code` (and therefore postal
  code and demographics) silently come back `None` rather than raising -
  there's no way from the return value alone to tell "no data for this
  area" apart from "the name matcher failed."

## Status

`profile(lat, lon)` is fully wired end to end: boundary resolution (all four
levels), postal code, and census demographics all run and are covered by
`tests/test_profiler.py`.

## License

[Apache License 2.0](LICENSE).

## Development

This section is for people modifying the package itself, not for people
using it. This package lives inside the
[`TLF-PROFILERS`](https://github.com/PujanPandey07/TLF-PROFILERS) monorepo,
at `packages/tlf-geo-profiler`:

```bash
git clone https://github.com/PujanPandey07/TLF-PROFILERS.git
cd TLF-PROFILERS/packages/tlf-geo-profiler
```

### Project layout

- `boundaries.py` - coordinate -> admin unit (point-in-polygon, 4 layers) and
  postal code lookup (ward- and local-level granularity, joined by
  `local_level_code` + ward number, not by district)
- `scripts/build_admin_layer.py` - Overpass GeoJSON -> bundled GeoParquet.
  Rebuild the boundary layers with this if the source OSM data changes.
- `scripts/inspect_data.py` - dump the bundled parquet/csv files to the
  console (and optionally to `data_preview/*.csv`) for manual inspection
- `demographics.py` - admin unit -> demographic stats from the 2021 census
  (`data/demographics_ward.csv`), joined by `local_level_code` and ward
- `profiler.py` - public `profile(lat, lon)` entry point

### Running the tests

If you're working on this package standalone:

```bash
pip install -e ".[dev]"
pytest -v
```

If you're working inside the `TLF-PROFILERS` monorepo (uv workspace), run
from the workspace root instead, so the shared `uv.lock` is used:

```bash
uv sync
uv run --package tlf-geo-profiler pytest packages/tlf-geo-profiler/tests -v
```

or equivalently, from inside `packages/tlf-geo-profiler/`: `uv run pytest -v`.

`tests/test_boundaries.py` checks the raw boundary-resolution layer
(including data invariants like layer counts and geometry validity);
`tests/test_profiler.py` checks the full `profile()` pipeline end to end
against known coordinates, including the `.to_dict()`/`.to_json()` output.

### Smoke-testing with sample data

`scripts/smoke_test.py` exercises every public function
(`profile`, `resolve_admin_unit`, `resolve_ward`, `get_demographics`,
`profile_dict`, `profile_json`) against a handful of known coordinates and
prints the results, for a quick manual sanity check beyond what pytest
asserts:

```bash
uv run --package tlf-geo-profiler python packages/tlf-geo-profiler/scripts/smoke_test.py
# or, standalone: python scripts/smoke_test.py
```
