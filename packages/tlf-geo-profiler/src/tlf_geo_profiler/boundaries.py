"""Point-in-polygon resolution: coordinate -> admin unit.

Responsible ONLY for turning (lat, lon) into an admin-unit reference
(province / district / local level / ward). Does not know about
demographics - see demographics.py for that.

Boundary source is not yet decided (OSM coverage is being checked for
ward-level completeness). This module should stay source-agnostic:
whatever loader is used, it must return AdminUnit objects.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class AdminUnit:
    province: str | None = None
    district: str | None = None
    local_level: str | None = None
    local_level_code: str | None = None
    ward: int | None = None
    tole: str | None = None
    postal_code: str | None = None


def resolve_admin_unit(lat: float, lon: float) -> AdminUnit:
    """Resolve a coordinate to its containing admin unit.

    Raises:
        ValueError: if the coordinate is outside all known boundaries.
    """
    raise NotImplementedError(
        "boundary data source not yet wired up - see docs/decisions.md"
    )
