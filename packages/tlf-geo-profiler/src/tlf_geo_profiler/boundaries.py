"""Point-in-polygon resolution: coordinate -> admin unit.

Ward-level resolution is real and tested (source: OpenStreetMap Nepal,
admin_level=9 relations - 6,738 of Nepal's 6,743 official wards, verified
against known coordinates in Kathmandu, Pokhara, and remote Humla).

Province/district/local-level resolution is NOT yet implemented - the ward
data alone does not carry district/province information, and ward names
are not safe to string-parse for this (confirmed: 143 municipality names
are reused across different districts, e.g. "Kalika" appears 3 times in
unrelated parts of the country). This needs its own verified boundary
layer, resolved spatially the same way wards are - see docs/decisions.md.
"""

from dataclasses import dataclass
from functools import lru_cache
from importlib import resources

import geopandas as gpd
from shapely.geometry import Point


@dataclass(frozen=True)
class AdminUnit:
    province: str | None = None
    district: str | None = None
    local_level: str | None = None
    local_level_code: str | None = None
    ward: int | None = None
    ward_osm_id: str | None = None
    tole: str | None = None
    postal_code: str | None = None


@lru_cache(maxsize=1)
def _load_wards() -> gpd.GeoDataFrame:
    """Load the bundled ward boundary data once per process."""
    with resources.as_file(
        resources.files("tlf_geo_profiler").joinpath("data/wards.parquet")
    ) as path:
        return gpd.read_parquet(path)


def resolve_ward(lat: float, lon: float) -> dict | None:
    """Resolve a coordinate to its containing OSM ward relation, if any.

    Uses the GeoDataFrame's spatial index so this stays fast even though
    there are 6,738 candidate polygons.
    """
    gdf = _load_wards()
    pt = Point(lon, lat)  # shapely/geojson order is (lon, lat), not (lat, lon)
    possible_idx = list(gdf.sindex.intersection(pt.bounds))
    if not possible_idx:
        return None
    candidates = gdf.iloc[possible_idx]
    match = candidates[candidates.contains(pt)]
    if match.empty:
        return None
    row = match.iloc[0]
    return {"osm_id": row["osm_id"], "name": row["name"], "ward": row["ward"]}


def resolve_admin_unit(lat: float, lon: float) -> AdminUnit:
    """Resolve a coordinate to its containing admin unit.

    Raises:
        ValueError: if the coordinate is outside all known ward boundaries.
    """
    ward_match = resolve_ward(lat, lon)
    if ward_match is None:
        raise ValueError(f"({lat}, {lon}) is outside all known ward boundaries")

    # District/province/local_level are NOT resolved yet - see module docstring.
    return AdminUnit(
        ward=int(ward_match["ward"]) if ward_match["ward"] is not None else None,
        ward_osm_id=ward_match["osm_id"],
        # local_level left as the raw OSM name for now (e.g. "Kathmandu-24"
        # embeds the municipality name but isn't a clean field yet)
        local_level=ward_match["name"],
    )
