import requests

OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.openstreetmap.ru/api/interpreter",
]

HEADERS = {
    "User-Agent": "tlf-disaster-profiler/0.1 (contact: your-email-or-repo-url)"}

DENSITY_THRESHOLD_PER_KM2 = {
    "buildings": 5,
    "amenities": 1,
    "roads": 0.5,
    "schools": 1,
    "hospitals": 0.2,
    "emergency": 0.3,
}


def _area_filter(area):
    """Build the Overpass QL location filter from a parsed cap.py area dict."""
    if area["kind"] == "circle":
        radius_m = area["radius_km"] * 1000
        return f'(around:{radius_m},{area["lat"]},{area["lon"]})'

    if area["kind"] == "polygon":
        coord_str = " ".join(f"{lat} {lon}" for lat, lon in area["points"])
        return f'(poly:"{coord_str}")'

    raise ValueError(f"unsupported area kind: {area['kind']}")


def _run_query(ql, timeout=30):
    """POST a query to Overpass, falling back through mirrors on failure. Raises only if all fail."""
    last_error = None
    for endpoint in OVERPASS_ENDPOINTS:
        try:
            resp = requests.post(
                endpoint, data={"data": ql}, headers=HEADERS, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            last_error = e
            continue
    raise RuntimeError(f"all Overpass endpoints failed: {last_error}")


def safe_query(category_key, ql, parse_fn):
    """Never raises — turns any failure into a structured 'failed' result."""
    try:
        raw = _run_query(ql)
        return {"status": "ok", "category": category_key, **parse_fn(raw)}
    except Exception as e:
        return {"status": "failed", "category": category_key, "reason": str(e)}


def count_query(area, category_key, osm_filter):
    """category_key is the friendly label (e.g. 'buildings'); osm_filter is the OSM tag filter."""
    loc = _area_filter(area)
    ql = f'[out:json][timeout:25];(way{osm_filter}{loc};node{osm_filter}{loc};);out count;'

    def parse(raw):
        return {"count": int(raw["elements"][0]["tags"]["total"])}

    return safe_query(category_key, ql, parse)


def named_query(area, category_key, osm_filter):
    """category_key is the friendly label (e.g. 'schools'); osm_filter is the OSM tag filter."""
    loc = _area_filter(area)
    ql = f'[out:json][timeout:25];(node{osm_filter}{loc};way{osm_filter}{loc};);out center;'

    def parse(raw):
        items = []
        for el in raw["elements"]:
            lat = el.get("lat") or el.get("center", {}).get("lat")
            lon = el.get("lon") or el.get("center", {}).get("lon")
            name = el.get("tags", {}).get("name", "unnamed")
            items.append({"name": name, "lat": lat, "lon": lon})
        return {"items": items, "count": len(items)}

    return safe_query(category_key, ql, parse)


def flood_context(area):
    """Nearby rivers/lakes/dams, deduped by name (OSM has River/Nadi/case variants)."""
    result = named_query(area, "flood_context", '["waterway"="river"]')
    if result["status"] != "ok":
        return result

    seen = set()
    deduped = []
    for item in result["items"]:
        key = item["name"].lower().replace(
            " river", "").replace(" nadi", "").strip()
        if key not in seen:
            seen.add(key)
            deduped.append(item)

    result["items"] = deduped
    result["count"] = len(deduped)
    return result


def confidence_label(count, area_km2, category_key):
    """high/low/unknown, based on density vs a plausibility threshold — not a real count check."""
    if area_km2 <= 0:
        return "unknown"
    density = count / area_km2
    threshold = DENSITY_THRESHOLD_PER_KM2.get(category_key, 0.1)
    return "high" if density >= threshold else "low"


def query_disaster_area(area, area_km2, event_type):
    """Top-level: run every relevant category query, attach confidence, never crash."""
    categories = {
        "buildings": count_query(area, "buildings", '["building"]'),
        "roads": count_query(area, "roads", '["highway"]'),
        "schools": named_query(area, "schools", '["amenity"="school"]'),
        "hospitals": named_query(area, "hospitals", '["amenity"="hospital"]'),
        "emergency": named_query(area, "emergency", '["emergency"]'),
    }

    if event_type == "Flood":
        categories["flood_context"] = flood_context(area)

    for key, result in categories.items():
        if result["status"] == "ok":
            result["confidence"] = confidence_label(
                result["count"], area_km2, key)
        else:
            result["confidence"] = "unknown"

    return categories
