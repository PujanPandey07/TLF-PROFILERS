"""Point-in-polygon resolution: coordinate -> admin unit.

Four independent boundary layers, all from OpenStreetMap Nepal, each resolved
spatially with the same method:

    provinces     admin_level=4   7 polygons
    districts     admin_level=6   77 polygons
    local_levels  admin_level=7   753 polygons (749 from OSM + 4 derived, see below)
    wards         admin_level=9   6,738 polygons (of 6,743 official wards)

Names are NEVER used to link levels: 143 local-level names are reused across
unrelated districts (e.g. "Kalika"), so every lookup is by geometry.

Coverage differs by layer, on purpose of the data, not by bug: ward polygons
cover roughly 92% of Nepal's land area and local-level polygons roughly 96%;
province and district polygons cover all of it. The gap is consistent with
protected areas (Dolpa, Chitwan, Bardiya, Parsa, ...) that OSM does not assign
to any ward. A coordinate there resolves to province + district only.

Four local levels (Butwal, Nepalgunj, Duduwa, Sainamaina) are absent from the
OSM export; their polygons are dissolved from their wards and flagged
local_level_source="derived_from_wards". See scripts/build_admin_layers.py.
"""

from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
import re

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

_LAYERS = ("provinces", "districts", "local_levels", "wards")


@dataclass(frozen=True)
class AdminUnit:
    province: str | None = None
    province_code: str | None = None  # ISO 3166-2, e.g. "NP-P3"
    district: str | None = None
    local_level: str | None = None
    # metropolitan | sub_metropolitan | municipality | rural_municipality
    local_level_type: str | None = None
    local_level_osm_id: str | None = None
    local_level_source: str | None = None  # "osm" | "derived_from_wards"
    # reserved for an official CBS/LGD code; OSM carries none
    local_level_code: str | None = None
    ward: int | None = None
    ward_osm_id: str | None = None
    tole: str | None = None
    postal_code: str | None = None


def _with_ward_numbers(wards: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Add an integer `ward_no` column.

    The raw OSM `ward` tag is right for 6,725 of 6,738 wards. The other 13 are
    OSM tagging errors (superscript digits, typos like 1433, or a number that
    duplicates a sibling ward). Those are corrected from
    data/ward_number_fixes.csv, each with the reason. Anything still not a
    plain integer falls back to the number at the end of the ward name.
    """
    wards = wards.copy()
    tag = wards["ward"].astype("string")
    ward_no = pd.to_numeric(
        tag.where(tag.str.fullmatch(r"\d+")), errors="coerce")

    with resources.as_file(
        resources.files("tlf_geo_profiler").joinpath(
            "data/ward_number_fixes.csv")
    ) as path:
        fixes = pd.read_csv(path).set_index("osm_id")["ward_no"]
    ward_no = ward_no.where(~wards["osm_id"].isin(
        fixes.index), wards["osm_id"].map(fixes))

    def from_name(name: str):
        m = re.search(r"(\d+)\s*$", str(name)
                      ) or re.match(r"^\s*(\d+)\s*,", str(name))
        return int(m.group(1)) if m else pd.NA

    missing = ward_no.isna()
    ward_no[missing] = wards.loc[missing, "name"].map(from_name)
    wards["ward_no"] = ward_no.astype("Int64")
    return wards


@lru_cache(maxsize=None)
def _load(layer: str) -> gpd.GeoDataFrame:
    """Load a bundled boundary layer once per process."""
    if layer not in _LAYERS:
        raise ValueError(f"unknown layer {layer!r}")
    with resources.as_file(
        resources.files("tlf_geo_profiler").joinpath(f"data/{layer}.parquet")
    ) as path:
        gdf = gpd.read_parquet(path)
    return _with_ward_numbers(gdf) if layer == "wards" else gdf


def _lookup(layer: str, lat: float, lon: float):
    """Row of `layer` containing the coordinate, or None.

    Uses the spatial index, so it stays fast for the 6,738-polygon ward layer.
    A coordinate exactly on a shared edge matches both neighbours; the
    lowest-index polygon wins so the result is deterministic.
    """
    gdf = _load(layer)
    pt = Point(lon, lat)  # shapely/geojson order is (lon, lat), not (lat, lon)
    hits = sorted(gdf.sindex.query(pt, predicate="intersects"))
    if not hits:
        return None
    return gdf.iloc[hits[0]]


def _clean(value):
    """Turn pandas NA/NaN into None so dataclass fields stay plain."""
    try:
        return None if value != value else value
    except Exception:
        return value


def resolve_ward(lat: float, lon: float) -> dict | None:
    """Resolve a coordinate to its containing OSM ward relation, if any."""
    row = _lookup("wards", lat, lon)
    if row is None:
        return None
    return {
        "osm_id": row["osm_id"],
        "name": row["name"],
        "ward": row["ward"],  # raw OSM tag, kept for compatibility
        "ward_no": int(row["ward_no"]),  # corrected integer, use this
    }


def resolve_admin_unit(lat: float, lon: float) -> AdminUnit:
    """Resolve a coordinate to its containing admin unit, as deep as the data goes.

    Province and district are resolved for every point in Nepal. Local level
    and ward are filled only where a polygon exists (see module docstring);
    otherwise those fields are None.

    Raises:
        ValueError: if the coordinate falls in no boundary layer at all.
    """
    province = _lookup("provinces", lat, lon)
    district = _lookup("districts", lat, lon)
    local = _lookup("local_levels", lat, lon)
    ward = _lookup("wards", lat, lon)

    if all(x is None for x in (province, district, local, ward)):
        raise ValueError(
            f"({lat}, {lon}) is outside all known Nepal boundaries")

    ward_no = int(ward["ward_no"]) if ward is not None else None

    return AdminUnit(
        province=_clean(province["name_en"]) if province is not None else None,
        province_code=_clean(province["iso_code"]
                             ) if province is not None else None,
        district=_clean(district["name_en"]) if district is not None else None,
        local_level=_clean(local["name_en"]) if local is not None else None,
        local_level_type=_clean(local["kind"]) if local is not None else None,
        local_level_osm_id=_clean(
            local["osm_id"]) if local is not None else None,
        local_level_source=_clean(
            local["source"]) if local is not None else None,
        ward=ward_no,
        ward_osm_id=ward["osm_id"] if ward is not None else None,
    )
