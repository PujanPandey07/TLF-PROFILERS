"""Manual smoke test: exercise every public function against known points.

This is not a replacement for `pytest` - it doesn't assert anything, it just
runs each public function and prints the result so you can eyeball it. Good
for a quick "did I break the wiring" check, or for demoing the package.

Run from the package directory:
    python scripts/smoke_test.py
or from the monorepo root, inside the uv workspace:
    uv run --package tlf-geo-profiler python packages/tlf-geo-profiler/scripts/smoke_test.py
"""

import json

from tlf_geo_profiler import profile, profile_dict, profile_json
from tlf_geo_profiler.boundaries import resolve_admin_unit, resolve_ward
from tlf_geo_profiler.demographics import get_demographics

# Known points, same ones covered by tests/test_profiler.py.
SAMPLE_POINTS = {
    "Kathmandu Durbar Square": (27.7040, 85.3070),
    "Simkot, Humla (remote)": (29.9707, 81.8203),
    "Pokhara Lakeside": (28.2096, 83.9560),
}
OUTSIDE_NEPAL = ("Null Island (outside Nepal)", 0.0, 0.0)


def _rule(title: str) -> None:
    print(f"\n{'=' * 60}\n{title}\n{'=' * 60}")


def main() -> None:
    for label, (lat, lon) in SAMPLE_POINTS.items():
        _rule(label)

        print(f"resolve_admin_unit({lat}, {lon}):")
        admin_unit = resolve_admin_unit(lat, lon)
        print(f"  {admin_unit}")

        print(f"\nresolve_ward({lat}, {lon}):")
        print(f"  {resolve_ward(lat, lon)}")

        print(
            f"\nget_demographics({admin_unit.local_level_code!r}, "
            f"ward_no={admin_unit.ward!r}):"
        )
        print(f"  {get_demographics(admin_unit.local_level_code, ward_no=admin_unit.ward)}")

        print(
            f"\nget_demographics({admin_unit.local_level_code!r}) "
            "[no ward - whole local level]:"
        )
        print(f"  {get_demographics(admin_unit.local_level_code)}")

        print(f"\nprofile({lat}, {lon}):")
        p = profile(lat, lon)
        print(f"  {p}")

        print("\np.to_dict():")
        print(f"  {p.to_dict()}")

        print("\np.to_json(indent=2):")
        print(p.to_json(indent=2))

        assert profile_dict(lat, lon) == p.to_dict(), "profile_dict() mismatch!"
        assert profile_json(lat, lon) == p.to_json(), "profile_json() mismatch!"
        print("\nprofile_dict() / profile_json() match .to_dict()/.to_json() - OK")

    label, lat, lon = OUTSIDE_NEPAL
    _rule(label)
    print(f"profile({lat}, {lon}) is expected to raise ValueError:")
    try:
        profile(lat, lon)
        print("  UNEXPECTED: did not raise!")
    except ValueError as exc:
        print(f"  raised ValueError as expected: {exc}")

    _rule("Done")
    print("If every section above printed sensible values and nothing")
    print("raised an unexpected error or AssertionError, the wiring is intact.")


if __name__ == "__main__":
    main()