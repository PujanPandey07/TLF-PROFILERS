import time
from collections import Counter

import requests

OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.openstreetmap.ru/api/interpreter",
]

HEADERS = {
    "User-Agent": "tlf-disaster-profiler/0.1 (Pujan Pandey, github.com/PujanPandey07)",
}


def _run_query(query, retries=2, delay_s=5):
    last_error = None
    for attempt in range(retries):
        for endpoint in OVERPASS_ENDPOINTS:
            try:
                response = requests.post(
                    endpoint, data={"data": query}, headers=HEADERS, timeout=120)
                response.raise_for_status()
                return response.json()
            except requests.exceptions.RequestException as e:
                last_error = e
                print(f"  [{endpoint}] attempt {attempt + 1} failed: {e}")
                continue
        if attempt < retries - 1:
            time.sleep(delay_s)
    raise last_error


def _element_latlon(el):
    """Nodes carry lat/lon directly. Ways only get a coordinate when the
    query asks for 'center', which puts it under a 'center' sub-object."""
    if el["type"] == "node":
        return el["lat"], el["lon"]
    center = el.get("center")
    return (center["lat"], center["lon"]) if center else (None, None)


def check_flood_context(lat, lon, radius_m=5000):
    """Rivers, lakes, and flood-control structures near a point.
    Prints results directly — this is a manual verification check,
    not yet the final report-building function."""
    where = f"(around:{radius_m},{lat},{lon})"
    query = f"""
    [out:json][timeout:60];
    (
      way["waterway"~"^(river|stream|canal)$"]{where};
      way["natural"="water"]{where};
      way["waterway"="dam"]{where};
      node["waterway"="dam"]{where};
    );
    out tags center;
    """
    result = _run_query(query)
    print(f"total found: {len(result['elements'])}")
    for el in result["elements"]:
        t = el["tags"]
        kind = t.get("waterway") or t.get("natural")
        name = t.get("name", "unnamed")
        lat_, lon_ = _element_latlon(el)
        print(f"  {kind:12s} {name:30s} ({lat_}, {lon_})")


if __name__ == "__main__":
    # near the Bagmati/Manohara confluence, Kathmandu
    check_flood_context(lat=27.6710, lon=85.4298, radius_m=5000)
