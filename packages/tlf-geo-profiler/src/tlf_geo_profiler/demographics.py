"""Admin unit -> demographic stats.

Provides census demographic stats (population, households, male/female count)
from the 2021 National Census, resolved by official local_level_code and ward_no.
"""

from dataclasses import dataclass, field
from functools import lru_cache
from importlib import resources

import pandas as pd


@dataclass(frozen=True)
class DemographicProfile:
    population: int | None = None
    households: int | None = None
    male_population: int | None = None
    female_population: int | None = None
    extra: dict = field(default_factory=dict)


@lru_cache(maxsize=1)
def _load_demographics_data():
    """Load and index ward-level and aggregated municipality-level demographics."""
    ward_demographics = {}
    local_demographics = {}

    with resources.as_file(
        resources.files("tlf_geo_profiler").joinpath(
            "data/demographics_ward.csv"
        )
    ) as path:
        df = pd.read_csv(
            path,
            dtype={
                "local_level_code": str,
            },
        )

        for _, row in df.iterrows():
            code = row["local_level_code"]
            if pd.isna(code):
                continue
            code = str(code).strip()
            wn = int(row["Ward No"]) if pd.notna(row["Ward No"]) else None
            hh = int(row["Total Households"]) if pd.notna(row["Total Households"]) else 0
            pop = int(row["Total Population"]) if pd.notna(row["Total Population"]) else 0
            male = int(row["Male Population"]) if pd.notna(row["Male Population"]) else 0
            female = int(row["Female Population"]) if pd.notna(row["Female Population"]) else 0

            if wn is not None:
                ward_demographics[(code, wn)] = DemographicProfile(
                    population=pop,
                    households=hh,
                    male_population=male,
                    female_population=female,
                )

            # Aggregate for local level
            if code not in local_demographics:
                local_demographics[code] = {
                    "population": 0,
                    "households": 0,
                    "male_population": 0,
                    "female_population": 0,
                }
            local_demographics[code]["population"] += pop
            local_demographics[code]["households"] += hh
            local_demographics[code]["male_population"] += male
            local_demographics[code]["female_population"] += female

    local_profiles = {
        code: DemographicProfile(
            population=vals["population"],
            households=vals["households"],
            male_population=vals["male_population"],
            female_population=vals["female_population"],
        )
        for code, vals in local_demographics.items()
    }

    return ward_demographics, local_profiles


def get_demographics(
    local_level_code: str | None, ward_no: int | None = None
) -> DemographicProfile:
    """Return demographics for a local level code, optionally specific to a ward.

    If ward_no is specified and exists, returns ward-level stats.
    Otherwise returns the aggregated municipality-level stats.
    If local_level_code is None or not found, returns an empty DemographicProfile.
    """
    if not local_level_code:
        return DemographicProfile()

    code = str(local_level_code).strip()
    ward_demographics, local_profiles = _load_demographics_data()

    if ward_no is not None and (code, int(ward_no)) in ward_demographics:
        return ward_demographics[(code, int(ward_no))]

    if code in local_profiles:
        return local_profiles[code]

    return DemographicProfile()

