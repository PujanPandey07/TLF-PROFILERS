"""Tests for osm_query.py. _run_query (the actual HTTP call to Overpass) is
monkeypatched throughout — these tests check our own parsing/merging/categorizing
logic against canned responses, not live Overpass behavior or network reliability."""
from tlf_disaster_profiler import osm_query


def test_area_filter_circle():
    area = {"kind": "circle", "lat": 27.7, "lon": 85.3, "radius_km": 5}
    result = osm_query._area_filter(area)
    assert result == "(around:5000,27.7,85.3)"


def test_area_filter_polygon():
    area = {"kind": "polygon", "points": [(27.0, 85.0), (27.1, 85.1)]}
    result = osm_query._area_filter(area)
    assert result == '(poly:"27.0 85.0 27.1 85.1")'


def test_confidence_label_high_when_above_threshold():
    # buildings threshold is 5/km2; 10 buildings in 1km2 = density 10 >= 5
    assert osm_query.confidence_label(10, 1.0, "buildings") == "high"


def test_confidence_label_low_when_below_threshold():
    assert osm_query.confidence_label(1, 1.0, "buildings") == "low"


def test_confidence_label_unknown_for_zero_area():
    assert osm_query.confidence_label(10, 0, "buildings") == "unknown"


def test_confidence_label_falls_back_to_default_threshold_for_unknown_category():
    # any category not in DENSITY_THRESHOLD_PER_KM2 uses the 0.1 fallback
    assert osm_query.confidence_label(1, 1.0, "some_new_category") == "high"


def test_safe_query_never_raises_on_failure(monkeypatch):
    def boom(ql, timeout=30):
        raise RuntimeError("all Overpass endpoints failed: simulated")
    monkeypatch.setattr(osm_query, "_run_query", boom)

    result = osm_query.safe_query(
        "test_cat", "fake ql", lambda raw: {"count": 1})
    assert result["status"] == "failed"
    assert "simulated" in result["reason"]


def test_flood_context_merges_river_name_variants(monkeypatch):
    """OSM has 'Bagmati River' / 'Bagmati Nadi' / case differences for the same
    river, split across many ways — flood_context should merge them into one entry."""
    fake_response = {
        "elements": [
            {"type": "way", "tags": {"name": "Bagmati River"},
             "geometry": [{"lat": 27.7, "lon": 85.3}, {"lat": 27.71, "lon": 85.31}]},
            {"type": "way", "tags": {"name": "bagmati nadi"},
             "geometry": [{"lat": 27.71, "lon": 85.31}, {"lat": 27.72, "lon": 85.32}]},
            {"type": "way", "tags": {"name": "Manohara River"},
             "geometry": [{"lat": 27.68, "lon": 85.35}, {"lat": 27.69, "lon": 85.36}]},
        ]
    }
    monkeypatch.setattr(osm_query, "_run_query", lambda ql,
                        timeout=30: fake_response)

    area = {"kind": "circle", "lat": 27.7, "lon": 85.3, "radius_km": 5}
    result = osm_query.flood_context(area)

    assert result["status"] == "ok"
    assert result["count"] == 2  # Bagmati (merged) + Manohara
    bagmati = next(r for r in result["items"]
                   if "bagmati" in r["name"].lower())
    assert len(bagmati["segments"]) == 2  # both ways merged under one river


def test_named_amenities_query_buckets_by_tag(monkeypatch):
    """A combined response with mixed amenity/emergency tags should be split into
    the right category buckets, and an untagged/unmatched element should be dropped
    rather than crashing the parse."""
    fake_response = {
        "elements": [
            {"type": "node", "tags": {"amenity": "school", "name": "Test School"},
             "lat": 27.7, "lon": 85.3},
            {"type": "node", "tags": {"amenity": "hospital", "name": "Test Hospital"},
             "lat": 27.71, "lon": 85.31},
            {"type": "node", "tags": {"emergency": "fire_hydrant"},
             "lat": 27.72, "lon": 85.32},
            {"type": "node", "tags": {"shop": "bakery", "name": "Irrelevant Bakery"},
             "lat": 27.73, "lon": 85.33},
        ]
    }
    monkeypatch.setattr(osm_query, "_run_query", lambda ql,
                        timeout=30: fake_response)

    area = {"kind": "circle", "lat": 27.7, "lon": 85.3, "radius_km": 5}
    result = osm_query.named_amenities_query(area)

    assert result["schools"]["status"] == "ok"
    assert result["schools"]["count"] == 1
    assert result["schools"]["items"][0]["name"] == "Test School"

    assert result["hospitals"]["count"] == 1
    assert result["emergency_infra"]["count"] == 1
    # the bakery has no matching category and must not appear anywhere, or crash
    assert result["health_posts"]["count"] == 0


def test_named_amenities_query_all_categories_fail_together_on_error(monkeypatch):
    def boom(ql, timeout=30):
        raise RuntimeError("simulated Overpass outage")
    monkeypatch.setattr(osm_query, "_run_query", boom)

    area = {"kind": "circle", "lat": 27.7, "lon": 85.3, "radius_km": 5}
    result = osm_query.named_amenities_query(area)

    assert set(result.keys()) == set(osm_query.NAMED_AMENITY_CATEGORIES.keys())
    assert all(r["status"] == "failed" for r in result.values())
