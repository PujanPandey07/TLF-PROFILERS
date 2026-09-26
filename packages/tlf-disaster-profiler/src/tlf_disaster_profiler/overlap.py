import geopandas as gpd
from shapely.geometry import Point, Polygon

from tlf_geo_profiler.boundaries import resolve_admin_unit
from tlf_geo_profiler.demographics import get_demographics

UTM_CRS = "EPSG:32645"
WGS84_CRS = "EPSG:4326"


def load_ward_boundaries(parquet_path):
    """Load the bundled wards.parquet and reproject to UTM for area/coverage math."""
    wards = gpd.read_parquet(parquet_path)
    return wards.to_crs(UTM_CRS)


def cap_area_to_geometry(area):
    if area["kind"] == "circle":
        point_wgs84 = gpd.GeoSeries(
            [Point(area["lon"], area["lat"])], crs=WGS84_CRS)
        point_utm = point_wgs84.to_crs(UTM_CRS).iloc[0]
        return point_utm.buffer(area["radius_km"] * 1000)

    if area["kind"] == "polygon":
        coords = [(lon, lat) for lat, lon in area["points"]]
        poly_wgs84 = gpd.GeoSeries([Polygon(coords)], crs=WGS84_CRS)
        return poly_wgs84.to_crs(UTM_CRS).iloc[0]

    return None


def find_affected_wards(wards_gdf, cap_geometry):
    """Intersect the alert shape against every ward, then resolve each touched
    ward's admin unit + population through tlf-geo-profiler's own corrected
    lookups (rather than trusting wards.parquet's raw, sometimes-wrong 'ward' tag)."""
    candidates = wards_gdf.iloc[wards_gdf.sindex.query(
        cap_geometry, predicate="intersects")]

    results = []
    for _, ward_row in candidates.iterrows():
        overlap = ward_row.geometry.intersection(cap_geometry)
        coverage_pct = (overlap.area / ward_row.geometry.area) * 100

        # representative_point() is guaranteed to fall INSIDE this specific
        # ward's shape (unlike centroid, which can land outside a concave polygon)
        rep_point_utm = ward_row.geometry.representative_point()
        rep_point_wgs84 = gpd.GeoSeries(
            [rep_point_utm], crs=UTM_CRS).to_crs(WGS84_CRS).iloc[0]
        lat, lon = rep_point_wgs84.y, rep_point_wgs84.x

        admin = resolve_admin_unit(lat, lon)
        demo = get_demographics(admin.local_level_code, ward_no=admin.ward)

        population = demo.population  # may genuinely be None — resolver can silently miss
        population_affected = round(
            population * coverage_pct / 100) if population is not None else None

        results.append({
            "ward_osm_id": ward_row["osm_id"],
            "ward_name_osm": ward_row["name"],
            "province": admin.province,
            "district": admin.district,
            "local_level": admin.local_level,
            "ward_no": admin.ward,
            "postal_code": admin.postal_code,
            "coverage_pct": round(coverage_pct, 2),
            "population": population,
            "population_affected": population_affected,
            "population_known": population is not None,
        })
    return results


def overlap_report(area, wards_gdf):
    geometry = cap_area_to_geometry(area)
    if geometry is None:
        return {"status": "failed", "reason": area.get("reason", "unsupported area kind"), "wards": []}

    return {"status": "ok", "wards": find_affected_wards(wards_gdf, geometry)}
