"""Tests for overlap.py's pure geometry functions (buffered_area, flag_items_near_lines,
bin_items_by_ward). These use a small synthetic two-ward layout near Kathmandu instead of
the real bundled wards.parquet, and don't touch find_affected_wards/overlap_report (which
need tlf-geo-profiler installed) — so this file has no dependency on that package."""
import geopandas as gpd
from shapely.geometry import box, Polygon, Point as ShapelyPoint

from tlf_disaster_profiler import overlap


def _make_wards_gdf():
    """Two adjacent squares near Kathmandu, reprojected to UTM like load_ward_boundaries does."""
    ward_a = box(85.30, 27.70, 85.31, 27.71)
    ward_b = box(85.31, 27.70, 85.32, 27.71)
    gdf = gpd.GeoDataFrame(
        {"osm_id": [1, 2], "name": ["Ward A", "Ward B"]},
        geometry=[ward_a, ward_b],
        crs=overlap.WGS84_CRS,
    )
    return gdf.to_crs(overlap.UTM_CRS)


def test_bin_items_by_ward_assigns_the_correct_ward():
    wards_gdf = _make_wards_gdf()
    items = [
        {"name": "Point in Ward A", "lat": 27.705, "lon": 85.305},
        {"name": "Point in Ward B", "lat": 27.705, "lon": 85.315},
        {"name": "Point outside both wards", "lat": 27.9, "lon": 85.9},
        {"name": "Missing coordinates", "lat": None, "lon": None},
    ]
    overlap.bin_items_by_ward(items, wards_gdf)

    assert items[0]["ward_osm_id"] == 1
    assert items[1]["ward_osm_id"] == 2
    assert items[2]["ward_osm_id"] is None
    assert items[3]["ward_osm_id"] is None


def test_buffered_area_contains_center_and_excludes_far_point():
    area = {"kind": "circle", "lat": 27.705, "lon": 85.305,
            "radius_km": 1, "area_desc": "test area"}
    buffered = overlap.buffered_area(area, 100)

    assert buffered["kind"] == "polygon"
    assert "100m buffer" in buffered["area_desc"]

    poly = Polygon([(lon, lat) for lat, lon in buffered["points"]])
    assert poly.contains(ShapelyPoint(85.305, 27.705))   # the center is inside
    assert not poly.contains(ShapelyPoint(85.5, 27.9))   # ~25km away is not


def test_flag_items_near_lines_flags_only_points_within_buffer():
    # a short river-like line segment
    river_segment = [(27.70, 85.30), (27.71, 85.30)]
    items = [
        {"name": "Close to the river", "lat": 27.705,
            "lon": 85.3005},   # ~40-50m away
        {"name": "Far from the river", "lat": 27.705, "lon": 85.320},    # ~2km away
        {"name": "Missing coordinates", "lat": None, "lon": None},
    ]
    overlap.flag_items_near_lines(items, [river_segment], buffer_m=100)

    assert items[0]["flood_risk"] is True
    assert items[1]["flood_risk"] is False
    assert items[2]["flood_risk"] is False  # no crash on missing coordinates


def test_flag_items_near_lines_handles_no_lines_gracefully():
    items = [{"name": "Anywhere", "lat": 27.7, "lon": 85.3}]
    overlap.flag_items_near_lines(items, [], buffer_m=100)
    assert items[0]["flood_risk"] is False
