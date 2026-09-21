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
