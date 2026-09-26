import geopandas as gpd
import pandas as pd
from shapely.geometry import Point, Polygon, LineString

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


def bin_items_by_ward(items, wards_gdf):
    """Assign each {'lat', 'lon', ...} item (e.g. a school/hospital/emergency point from
    osm_query.named_query) to the ward polygon it physically falls inside. Mutates each
    item in place, adding 'ward_osm_id' (None if the item has no coordinates, or falls
    outside every mapped ward — which can happen right at the edge of the dataset).

    This is a pure local spatial join against wards_gdf, already loaded for the same
    report — no extra Overpass calls needed to get per-ward amenity counts.
    """
    valid = [(i, item) for i, item in enumerate(items)
             if item.get("lat") is not None and item.get("lon") is not None]

    if not valid:
        for item in items:
            item["ward_osm_id"] = None
        return items

    idxs = [i for i, _ in valid]
    pts = [Point(item["lon"], item["lat"]) for _, item in valid]
    pts_gdf = gpd.GeoDataFrame(
        {"row": idxs}, geometry=pts, crs=WGS84_CRS).to_crs(UTM_CRS)

    joined = gpd.sjoin(pts_gdf, wards_gdf[["osm_id", "geometry"]],
                       how="left", predicate="within")
    # a point exactly on a shared ward edge could technically match twice — keep one
    joined = joined.drop_duplicates(subset="row")
    ward_by_row = dict(zip(joined["row"], joined["osm_id"]))

    for item in items:
        item["ward_osm_id"] = None
    for i in idxs:
        wid = ward_by_row.get(i)
        items[i]["ward_osm_id"] = wid if pd.notna(wid) else None

    return items


def buffered_area(area, buffer_m):
    """Expand a CAP area (circle or polygon) outward by buffer_m meters, returned as
    a new area-like dict ({'kind': 'polygon', 'points': [(lat, lon), ...]}) that plugs
    straight into osm_query's existing _area_filter / get_road_geometries etc. — no
    changes needed there. Used e.g. to catch roads just outside a landslide alert's
    exact drawn boundary, since real landslide impact rarely stops precisely at the
    alert polygon's edge.
    """
    geometry = cap_area_to_geometry(area)
    if geometry is None:
        return None

    buffered = geometry.buffer(buffer_m)
    if buffered.geom_type != "Polygon":
        # Not expected for a single circle/polygon input, but don't silently hand
        # back a malformed filter if it happens — fall back to a convex hull.
        buffered = buffered.convex_hull

    buffered_wgs84 = gpd.GeoSeries(
        [buffered], crs=UTM_CRS).to_crs(WGS84_CRS).iloc[0]
    points = [(lat, lon) for lon, lat in buffered_wgs84.exterior.coords]
    return {
        "kind": "polygon",
        "points": points,
        "area_desc": area.get("area_desc", "") + f" (+{buffer_m}m buffer)",
    }


def flag_items_near_lines(items, line_segments_latlon, buffer_m):
    """Flag each {'lat', 'lon', ...} item with 'flood_risk': True/False, based on
    whether it falls within buffer_m meters of ANY of the given polylines (each a
    list of (lat, lon) tuples — e.g. river segments from osm_query.flood_context's
    merged 'segments' field). Mutates items in place.

    This is a straight-line proximity heuristic: it ignores terrain, elevation and
    actual flood-plain shape, so treat it as a rough flag to prioritize checking,
    not a validated flood-risk model.
    """
    for item in items:
        item.setdefault("flood_risk", False)

    valid = [(i, item) for i, item in enumerate(items)
             if item.get("lat") is not None and item.get("lon") is not None]
    lines = [LineString([(lon, lat) for lat, lon in seg])
             for seg in line_segments_latlon if len(seg) >= 2]

    if not valid or not lines:
        return items

    lines_gdf = gpd.GeoDataFrame(geometry=lines, crs=WGS84_CRS).to_crs(UTM_CRS)
    risk_zone = lines_gdf.buffer(buffer_m).unary_union

    idxs = [i for i, _ in valid]
    pts = [Point(item["lon"], item["lat"]) for _, item in valid]
    pts_gdf = gpd.GeoDataFrame(
        {"row": idxs}, geometry=pts, crs=WGS84_CRS).to_crs(UTM_CRS)

    for row_id, is_within in zip(pts_gdf["row"], pts_gdf.within(risk_zone)):
        items[row_id]["flood_risk"] = bool(is_within)

    return items
