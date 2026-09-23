"""Public entry point."""

import json
from dataclasses import asdict, dataclass

from .boundaries import AdminUnit, resolve_admin_unit
from .demographics import DemographicProfile, get_demographics


@dataclass(frozen=True)
class RegionalProfile:
    admin_unit: AdminUnit
    demographics: DemographicProfile

    def to_dict(self) -> dict:
        """Return this profile as a plain, JSON-serializable dict.

        Nested: {"admin_unit": {...all AdminUnit fields...},
                 "demographics": {...all DemographicProfile fields...}}.
        Every field is already a str, int, dict or None, so this needs no
        custom encoder.
        """
        return asdict(self)

    def to_json(self, **kwargs) -> str:
        """Return this profile as a JSON string.

        Extra keyword arguments are passed through to `json.dumps` (e.g.
        `indent=2`, `ensure_ascii=False`).
        """
        return json.dumps(self.to_dict(), **kwargs)


def profile(lat: float, lon: float) -> RegionalProfile:
    """Given a coordinate, return its admin unit + demographic profile."""
    admin_unit = resolve_admin_unit(lat, lon)
    demographics = get_demographics(
        admin_unit.local_level_code, ward_no=admin_unit.ward
    )
    return RegionalProfile(admin_unit=admin_unit, demographics=demographics)


def profile_dict(lat: float, lon: float) -> dict:
    """Convenience: `profile(lat, lon)`, already flattened via `.to_dict()`."""
    return profile(lat, lon).to_dict()


def profile_json(lat: float, lon: float, **kwargs) -> str:
    """Convenience: `profile(lat, lon)`, already serialized via `.to_json()`."""
    return profile(lat, lon).to_json(**kwargs)