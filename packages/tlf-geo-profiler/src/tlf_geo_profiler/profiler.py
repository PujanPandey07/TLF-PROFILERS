"""Public entry point."""

from dataclasses import dataclass

from .boundaries import AdminUnit, resolve_admin_unit
from .demographics import DemographicProfile, get_demographics


@dataclass(frozen=True)
class RegionalProfile:
    admin_unit: AdminUnit
    demographics: DemographicProfile


def profile(lat: float, lon: float) -> RegionalProfile:
    """Given a coordinate, return its admin unit + demographic profile."""
    admin_unit = resolve_admin_unit(lat, lon)
    demographics = get_demographics(admin_unit.local_level_code)
    return RegionalProfile(admin_unit=admin_unit, demographics=demographics)
