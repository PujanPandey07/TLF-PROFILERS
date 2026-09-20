"""Admin unit -> demographic stats.

Intended to reuse tlf-core's existing CBS census vocabulary/FieldResolver
rather than reinventing value normalization here. Not yet wired up.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DemographicProfile:
    population: int | None = None
    households: int | None = None
    # Fuller CBS breakdown (caste/ethnicity, religion, education, etc.)
    # left as an open dict until we decide how much depth Profiler 1
    # actually needs to return by default.
    extra: dict = field(default_factory=dict)


def get_demographics(local_level_code: str) -> DemographicProfile:
    raise NotImplementedError("not yet wired up to tlf-core census data")
