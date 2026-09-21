"""
Cleans an Overpass GeoJSON export into a bundled GeoParquet file.
Detects the admin level automatically - just point it at a file.

Usage:
    python clean_boundary_level.py path/to/export.geojson
"""

import sys
import json
import geopandas as gpd
from shapely.geometry import shape

LEVEL_NAMES = {
    "4": "provinces",
    "6": "districts",
    "7": "local_levels",
    "9": "wards",
}


def main(input_path):
    with open(input_path, encoding="utf-8") as f:
        data = json.load(f)

    records = []
    detected_level = None

    for feat in data["features"]:
        props = feat["properties"]
        geom = feat.get("geometry")
        if not geom or geom["type"] not in ("Polygon", "MultiPolygon"):
            continue
        if not props.get("@id", "").startswith("relation"):
            continue

        if detected_level is None:
            detected_level = props.get("admin_level")

        g = shape(geom)
        if not g.is_valid:
            g = g.buffer(0)

        records.append({
            "osm_id": props["@id"],
            "name": props.get("name"),
            "name_en": props.get("name:en"),
            "ward": props.get("ward"),
            "geometry": g,
        })

    gdf = gpd.GeoDataFrame(records, crs="EPSG:4326")
    output_name = LEVEL_NAMES.get(detected_level, f"level_{detected_level}")
    out_path = f"{output_name}.parquet"

    gdf.to_parquet(out_path, compression="zstd")
    print(f"Detected admin_level={detected_level} -> {output_name}")
    print(
        f"Kept {len(gdf)} clean polygons out of {len(data['features'])} raw features")
    print(f"Saved to {out_path}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python clean_boundary_level.py path/to/export.geojson")
        sys.exit(1)
    main(sys.argv[1])
