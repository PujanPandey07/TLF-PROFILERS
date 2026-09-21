"""Build the province / district / local-level boundary layers.

Input: three Overpass GeoJSON exports (admin_level 4, 6, 7).
Output: GeoParquet files written next to wards.parquet in the package data dir.

    python scripts/build_admin_layers.py \
        --provinces export_p.geojson \
        --districts export_d.geojson \
        --local-levels export_l.geojson

What this does beyond format conversion:
  * drops the Point features Overpass adds alongside each relation (label /
    admin_centre nodes) - only polygons are kept
  * repairs invalid geometry (one province polygon is self-intersecting)
  * normalises names into name_en / name_ne (OSM `name` is Devanagari for
    some units and Latin for others; `name:en` is missing on many)
  * maps `name:suffix` to a local-level kind
  * DERIVES polygons for local levels that are absent from the export by
    dissolving their wards (see `derive_missing_local_levels`). These are
    flagged source="derived_from_wards" and should be replaced by the real
    OSM relations once they are exported.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import geopandas as gpd
import pandas as pd
import shapely

DATA_DIR = Path(__file__).resolve(
).parents[1] / "src" / "tlf_geo_profiler" / "data"

_DEVANAGARI = re.compile("[\u0900-\u097f]")

# name:suffix values seen in the export, Latin and Devanagari spellings
_KIND_BY_SUFFIX = {
    "Mahanagarpalika": "metropolitan",
    "महानगरपालिका": "metropolitan",
    "Upamahanagarpalika": "sub_metropolitan",
    "उपमहानगरपालिका": "sub_metropolitan",
    "उप-महानगरपालिका": "sub_metropolitan",
    "Nagarpalika": "municipality",
    "नगरपालिका": "municipality",
    "Gaunpalika": "rural_municipality",
    "गाउँपालिका": "rural_municipality",
}

# Longest first so "Rural Municipality" is stripped before "Municipality"
_EN_TYPE_WORDS = re.compile(
    r"\s+(Rural Municipality|Sub-Metropolitan City|Metropolitan City|Municipality)$"
)
_DISTRICT_FIXES = {"Nawalparasi W": "Nawalparasi West"}


def read_polygons(path: str) -> gpd.GeoDataFrame:
    gdf = gpd.read_file(path)
    gdf = gdf[gdf.geom_type.isin(["Polygon", "MultiPolygon"])].copy()
    gdf["geometry"] = gdf.geometry.map(_fix_geometry)
    return gdf.reset_index(drop=True)


def _fix_geometry(geom):
    if geom.is_valid:
        return geom
    fixed = shapely.make_valid(geom)
    polys = [p for p in shapely.get_parts(fixed) if p.geom_type == "Polygon"]
    assert polys, "make_valid produced no polygons"
    result = polys[0] if len(polys) == 1 else shapely.MultiPolygon(polys)
    # guard against make_valid silently discarding real area
    assert abs(result.area - geom.buffer(0).area) / \
        max(result.area, 1e-12) < 1e-3
    return result


def _col(gdf: gpd.GeoDataFrame, name: str) -> pd.Series:
    return gdf[name] if name in gdf.columns else pd.Series([None] * len(gdf), index=gdf.index)


def _names(gdf: gpd.GeoDataFrame) -> tuple[pd.Series, pd.Series]:
    """(name_en, name_ne): prefer explicit name:en / name:ne, else use `name`
    according to its script."""
    raw = _col(gdf, "name")
    is_deva = raw.map(lambda s: bool(_DEVANAGARI.search(s))
                      if isinstance(s, str) else False)
    en = _col(gdf, "name:en").where(
        _col(gdf, "name:en").notna(), raw.where(~is_deva & raw.notna()))
    ne = _col(gdf, "name:ne").where(
        _col(gdf, "name:ne").notna(), raw.where(is_deva))
    return en, ne


def build_provinces(path: str) -> gpd.GeoDataFrame:
    g = read_polygons(path)
    en, ne = _names(g)
    iso = _col(g, "ISO3166-2")
    return gpd.GeoDataFrame(
        {
            "osm_id": g["@id"],
            "name_en": en,
            "name_ne": ne,
            "iso_code": iso,
            "number": iso.str.extract(r"P(\d)$")[0].astype("Int64"),
            "wikidata": _col(g, "wikidata"),
        },
        geometry=g.geometry,
        crs=g.crs,
    ).sort_values("number", ignore_index=True)


def build_districts(path: str) -> gpd.GeoDataFrame:
    g = read_polygons(path)
    en, ne = _names(g)
    en = (
        en.str.replace(r"\s*\(Nepal\)$", "", regex=True)
        .str.replace(r"\s+District$", "", regex=True)
        .replace(_DISTRICT_FIXES)
    )
    return gpd.GeoDataFrame(
        {
            "osm_id": g["@id"],
            "name_en": en,
            "name_ne": ne,
            "wikidata": _col(g, "wikidata"),
        },
        geometry=g.geometry,
        crs=g.crs,
    ).sort_values("name_en", ignore_index=True)


def _kind(row) -> str | None:
    suffix = row.get("name:suffix")
    if isinstance(suffix, str) and suffix in _KIND_BY_SUFFIX:
        return _KIND_BY_SUFFIX[suffix]
    text = " ".join(str(row.get(k) or "") for k in ("name", "name:en"))
    if "Rural Municipality" in text or "गाउँपालिका" in text:
        return "rural_municipality"
    if "उपमहानगरपालिका" in text or "Sub-Metropolitan" in text:
        return "sub_metropolitan"
    if "महानगरपालिका" in text or "Metropolitan" in text:
        return "metropolitan"
    if "नगरपालिका" in text or "Municipality" in text:
        return "municipality"
    return None


def build_local_levels(path: str) -> gpd.GeoDataFrame:
    g = read_polygons(path)
    en, ne = _names(g)
    kind = g.apply(_kind, axis=1)
    en = en.str.replace(_EN_TYPE_WORDS, "", regex=True)
    return gpd.GeoDataFrame(
        {
            "osm_id": g["@id"],
            "name_en": en,
            "name_ne": ne,
            "kind": kind,
            "wikidata": _col(g, "wikidata"),
            "source": "osm",
        },
        geometry=g.geometry,
        crs=g.crs,
    )


def _ward_prefix(name: str) -> str:
    """'Butwal-09' / 'Nepalgunj.17' / '12, Butwal' -> municipality prefix."""
    name = re.sub(r"^\s*\d+\s*,\s*", "", str(name))
    return re.sub(r"[\d\s\-.,_]+$", "", name).strip()


def derive_missing_local_levels(
    wards: gpd.GeoDataFrame, local_levels: gpd.GeoDataFrame
) -> gpd.GeoDataFrame:
    """Wards whose representative point falls in no local-level polygon belong
    to a local level missing from the export. Group them by ward-name prefix and
    dissolve each group into one polygon.

    Ward-name prefixes are only trusted for this narrow purpose (they contain
    typos elsewhere, e.g. "Saklea", "Illam"); every group is printed so the
    result can be eyeballed.
    """
    pts = wards[["osm_id", "name", "geometry"]].copy()
    pts["geometry"] = wards.geometry.representative_point()
    hit = gpd.sjoin(pts, local_levels[["geometry"]],
                    predicate="within", how="left")
    orphan_ids = set(hit.loc[hit["index_right"].isna(), "osm_id"])
    orphans = wards[wards["osm_id"].isin(orphan_ids)].copy()
    orphans["prefix"] = orphans["name"].map(_ward_prefix)
    orphans = orphans[orphans["prefix"] != ""]

    rows = []
    for prefix, grp in orphans.groupby("prefix"):
        geom = shapely.union_all(grp.geometry.values)
        print(
            f"  derived local level {prefix!r}: {len(grp)} wards, {geom.geom_type}")
        rows.append(
            {
                "osm_id": None,
                "name_en": prefix,
                "name_ne": None,
                "kind": None,
                "wikidata": None,
                "source": "derived_from_wards",
                "geometry": geom,
            }
        )
    return gpd.GeoDataFrame(rows, geometry="geometry", crs=wards.crs)


def _write(gdf: gpd.GeoDataFrame, name: str, out: Path) -> None:
    path = out / f"{name}.parquet"
    gdf.to_parquet(path, compression="zstd", index=False)
    print(
        f"wrote {path.name}: {len(gdf)} rows, {path.stat().st_size / 1e6:.1f} MB")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--provinces", required=True)
    ap.add_argument("--districts", required=True)
    ap.add_argument("--local-levels", required=True)
    ap.add_argument("--wards", default=str(DATA_DIR / "wards.parquet"))
    ap.add_argument("--out", default=str(DATA_DIR))
    args = ap.parse_args()
    out = Path(args.out)

    provinces = build_provinces(args.provinces)
    districts = build_districts(args.districts)
    local_levels = build_local_levels(args.local_levels)
    wards = gpd.read_parquet(args.wards)

    print("deriving missing local levels from wards:")
    derived = derive_missing_local_levels(wards, local_levels)
    local_levels = pd.concat([local_levels, derived], ignore_index=True)
    local_levels = gpd.GeoDataFrame(
        local_levels, geometry="geometry", crs=derived.crs)

    _write(provinces, "provinces", out)
    _write(districts, "districts", out)
    _write(local_levels, "local_levels", out)


if __name__ == "__main__":
    main()
