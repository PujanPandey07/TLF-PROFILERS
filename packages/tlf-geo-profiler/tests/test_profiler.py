"""Placeholder tests - flesh out once boundary data source is picked."""

import pytest

from tlf_geo_profiler import profile


def test_profile_raises_until_data_source_wired_up():
    # Kathmandu Durbar Square, roughly
    with pytest.raises(NotImplementedError):
        profile(27.7040, 85.3070)
