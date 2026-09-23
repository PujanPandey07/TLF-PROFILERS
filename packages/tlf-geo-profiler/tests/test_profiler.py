"""End-to-end tests for profile(lat, lon)."""

import json

import pytest

from tlf_geo_profiler import profile, profile_dict, profile_json


def test_profile_kathmandu_durbar_square():
    p = profile(27.7040, 85.3070)

    # Admin Unit checks
    assert p.admin_unit.district == "Kathmandu"
    assert p.admin_unit.local_level == "Kathmandu"
    assert p.admin_unit.ward == 24
    assert p.admin_unit.local_level_code == "32706"
    assert p.admin_unit.postal_code is not None

    # Demographic checks
    assert p.demographics.population is not None and p.demographics.population > 0
    assert p.demographics.households is not None and p.demographics.households > 0
    assert (
        p.demographics.male_population + p.demographics.female_population
        == p.demographics.population
    )


def test_profile_remote_humla():
    p = profile(29.9707, 81.8203)

    assert p.admin_unit.district == "Humla"
    assert p.admin_unit.local_level == "Simkot"
    assert p.admin_unit.ward == 5
    assert p.admin_unit.local_level_code == "66606"
    assert p.admin_unit.postal_code is not None
    assert p.demographics.population is not None and p.demographics.population > 0


def test_profile_pokhara_lakeside():
    p = profile(28.2096, 83.9560)

    assert p.admin_unit.district == "Kaski"
    assert p.admin_unit.local_level == "Pokhara"
    assert p.admin_unit.ward == 6
    assert p.admin_unit.local_level_code == "44004"
    assert p.admin_unit.postal_code is not None
    assert p.demographics.population is not None and p.demographics.population > 0


def test_profile_outside_nepal_raises():
    with pytest.raises(ValueError):
        profile(0.0, 0.0)


# --- dict / JSON output ------------------------------------------------


def test_profile_to_dict_shape_and_values():
    p = profile(27.7040, 85.3070)
    d = p.to_dict()

    assert set(d.keys()) == {"admin_unit", "demographics"}
    assert d["admin_unit"]["district"] == "Kathmandu"
    assert d["admin_unit"]["ward"] == 24
    assert d["demographics"]["population"] == p.demographics.population


def test_profile_to_dict_is_json_serializable():
    p = profile(27.7040, 85.3070)
    # Should not raise - every field must already be a JSON-safe type.
    json.dumps(p.to_dict())


def test_profile_to_json_round_trips():
    p = profile(27.7040, 85.3070)
    parsed = json.loads(p.to_json())
    assert parsed == p.to_dict()


def test_profile_dict_matches_profile_to_dict():
    assert profile_dict(27.7040, 85.3070) == profile(27.7040, 85.3070).to_dict()


def test_profile_json_matches_profile_to_json():
    assert profile_json(27.7040, 85.3070) == profile(27.7040, 85.3070).to_json()