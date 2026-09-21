"""Real tests against the bundled ward data - no mocking, actual polygons."""

import pytest

from tlf_geo_profiler.boundaries import resolve_admin_unit, resolve_ward


def test_kathmandu_durbar_square():
    result = resolve_ward(27.7040, 85.3070)
    assert result["name"] == "Kathmandu-24"
    assert result["ward"] == "24"


def test_simkot_humla_remote_area():
    """Confirms coverage isn't just urban - Humla is one of Nepal's most
    remote districts."""
    result = resolve_ward(29.9707, 81.8203)
    assert result["name"] == "Simkot-05"


def test_pokhara_lakeside():
    result = resolve_ward(28.2096, 83.9560)
    assert result["name"] == "Pokhara-06"


def test_point_outside_nepal_raises():
    with pytest.raises(ValueError):
        resolve_admin_unit(0.0, 0.0)  # middle of the ocean


def test_resolve_admin_unit_returns_ward_number():
    unit = resolve_admin_unit(27.7040, 85.3070)
    assert unit.ward == 24


# --- province / district / local level ------------------------------------


def test_full_hierarchy_kathmandu():
    unit = resolve_admin_unit(27.7040, 85.3070)
    assert unit.province_code == "NP-P3"
    assert unit.district == "Kathmandu"
    assert unit.local_level == "Kathmandu"
    assert unit.local_level_type == "metropolitan"
    assert unit.local_level_source == "osm"
    assert unit.ward == 24


def test_remote_humla_full_hierarchy():
    unit = resolve_admin_unit(29.9707, 81.8203)
    assert unit.province_code == "NP-P6"
    assert unit.district == "Humla"
    assert unit.local_level == "Simkot"
    assert unit.ward == 5


def test_derived_local_level_is_flagged():
    """Butwal is absent from the OSM level-7 export; its polygon is dissolved
    from its wards and must say so."""
    unit = resolve_admin_unit(27.7006, 83.4483)
    assert unit.district == "Rupandehi"
    assert unit.local_level == "Butwal"
    assert unit.local_level_source == "derived_from_wards"


def test_point_outside_wards_still_resolves_district():
    """Inside Chitwan district but in no ward or local-level polygon: report
    province + district and leave the finer levels None rather than raising."""
    unit = resolve_admin_unit(27.5300, 84.3500)
    assert unit.district == "Chitwan"
    assert unit.province_code == "NP-P3"
    assert unit.ward is None
    assert unit.local_level is None


def test_point_in_india_raises():
    with pytest.raises(ValueError):
        resolve_admin_unit(28.61, 77.21)  # Delhi


# --- data invariants (guard against a bad rebuild of the parquet files) ----


def _layer(name):
    from tlf_geo_profiler.boundaries import _load

    return _load(name)


def test_layer_counts():
    assert len(_layer("provinces")) == 7
    assert len(_layer("districts")) == 77
    assert len(_layer("local_levels")) == 753  # 749 from OSM + 4 derived


def test_no_null_names_and_no_invalid_geometry():
    for name in ("provinces", "districts", "local_levels"):
        gdf = _layer(name)
        assert gdf["name_en"].notna().all(), name
        assert gdf.is_valid.all(), name


def test_every_ward_lands_in_a_local_level_district_and_province():
    """Nesting check: no ward may sit outside the coarser layers. This is what
    would break if wards and higher levels came from different sources."""
    import geopandas as gpd

    wards = _layer("wards")
    pts = gpd.GeoDataFrame(
        {"osm_id": wards["osm_id"]}, geometry=wards.representative_point(), crs=wards.crs
    )
    for name in ("local_levels", "districts", "provinces"):
        joined = gpd.sjoin(pts, _layer(
            name)[["geometry"]], predicate="within", how="left")
        joined = joined.drop_duplicates("osm_id")
        assert joined["index_right"].notna().all(), f"wards outside {name}"


# --- ward-number corrections ------------------------------------------------


def _point_in_ward(osm_id):
    wards = _layer("wards")
    p = wards[wards["osm_id"] ==
              osm_id].geometry.iloc[0].representative_point()
    return p.y, p.x


@pytest.mark.parametrize(
    "osm_id, expected",
    [
        ("relation/16127854", 15),  # Hetauda-15, ward tag was superscript '⁵'
        ("relation/6667491", 1),  # Yangwarak-01, ward tag was superscript '¹'
        ("relation/6079233", 1),  # Bungdikali-01, ward tag was 1433
        ("relation/7594658", 10),  # Bode Parsain-10, ward tag was 19
    ],
)
def test_mistagged_wards_resolve_without_crashing(osm_id, expected):
    unit = resolve_admin_unit(*_point_in_ward(osm_id))
    assert unit.ward == expected


def test_ward_numbers_unique_within_each_local_level():
    """Catches a bad ward tag that duplicates a sibling's number."""
    import geopandas as gpd

    wards = _layer("wards")
    pts = gpd.GeoDataFrame(
        {"osm_id": wards["osm_id"], "ward_no": wards["ward_no"]},
        geometry=wards.representative_point(),
        crs=wards.crs,
    )
    lls = _layer("local_levels").reset_index().rename(columns={"index": "ll"})
    joined = gpd.sjoin(pts, lls[["ll", "geometry"]],
                       predicate="within", how="inner")
    joined = joined.drop_duplicates("osm_id")
    dupes = joined[joined.duplicated(["ll", "ward_no"], keep=False)]
    assert dupes.empty, dupes[["osm_id", "ward_no"]].to_string()
    assert wards["ward_no"].notna().all()
