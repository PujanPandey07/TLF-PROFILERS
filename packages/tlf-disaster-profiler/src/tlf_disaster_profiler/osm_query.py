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
    "roads": 0.5,
    "schools": 1,
    "hospitals": 0.2,
    "health_posts": 0.3,
    "pharmacies": 0.5,
    "police": 0.1,
    "fire_stations": 0.05,
    "shelters": 0.1,
    "religious_sites": 1,
    "marketplaces": 0.3,
    "water_sources": 0.5,
    "emergency_infra": 0.3,
}

# Every named, point-based amenity category queried as one combined Overpass
# request (see named_amenities_query). (tag_key, tag_value) — tag_value=None
# means "key present, any value" (used for emergency=*).
NAMED_AMENITY_CATEGORIES = {
    "schools": ("amenity", "school"),
    "hospitals": ("amenity", "hospital"),
    "health_posts": ("amenity", "clinic"),
    "pharmacies": ("amenity", "pharmacy"),
    "police": ("amenity", "police"),
    "fire_stations": ("amenity", "fire_station"),
    "shelters": ("amenity", "shelter"),
    "religious_sites": ("amenity", "place_of_worship"),
    "marketplaces": ("amenity", "marketplace"),
    "water_sources": ("amenity", "drinking_water"),
    "emergency_infra": ("emergency", None),
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


def safe_query(category_key, ql, parse_fn, timeout=30):
    """Never raises — turns any failure into a structured 'failed' result.
    timeout is the HTTP request timeout in seconds; it must be >= the
    [timeout:N] value baked into the Overpass QL itself, or we'll abort the
    request client-side before Overpass even gets a chance to respond."""
    try:
        raw = _run_query(ql, timeout=timeout)
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


def river_geometries(area):
    """Named rivers as full polylines (out geom) rather than a single centroid point,
    so the report can draw the actual river course on the map instead of a dot."""
    loc = _area_filter(area)
    ql = f'[out:json][timeout:25];(way["waterway"="river"]{loc};);out geom;'

    def parse(raw):
        rivers = []
        for el in raw["elements"]:
            if el.get("type") != "way" or "geometry" not in el:
                continue
            name = el.get("tags", {}).get("name", "unnamed")
            coords = [(pt["lat"], pt["lon"]) for pt in el["geometry"]]
            rivers.append({"name": name, "coords": coords})
        return {"items": rivers, "count": len(rivers)}

    return safe_query("river_geometries", ql, parse)


def flood_context(area):
    """Nearby rivers, deduped by name (OSM has River/Nadi/case variants). A single
    named river is usually split across many OSM ways, so segments belonging to the
    same name are grouped under one entry: {"name": ..., "segments": [[(lat,lon),...],...]}."""
    result = river_geometries(area)
    if result["status"] != "ok":
        return result

    merged = {}
    order = []
    for item in result["items"]:
        key = item["name"].lower().replace(
            " river", "").replace(" nadi", "").strip()
        if key not in merged:
            merged[key] = {"name": item["name"], "segments": []}
            order.append(key)
        merged[key]["segments"].append(item["coords"])

    result["items"] = [merged[k] for k in order]
    result["count"] = len(result["items"])
    return result


def named_amenities_query(area):
    """Every category in NAMED_AMENITY_CATEGORIES, fetched in ONE Overpass round
    trip instead of one request per category — faster, and puts far less load on
    the shared public mirrors than the old one-request-per-amenity approach.
    Returns {category: {"status", "items", "count"}}, same shape as if each
    category had been fetched with the old named_query() individually, so nothing
    downstream (binning, rendering) needs to know the difference.
    """
    loc = _area_filter(area)
    clauses = []
    for key, value in NAMED_AMENITY_CATEGORIES.values():
        tag_filter = f'["{key}"="{value}"]' if value is not None else f'["{key}"]'
        clauses.append(f'node{tag_filter}{loc};')
        clauses.append(f'way{tag_filter}{loc};')
    ql = f'[out:json][timeout:25];({"".join(clauses)});out center tags;'

    def matches(tags, key, value):
        return (key in tags) if value is None else (tags.get(key) == value)

    def parse(raw):
        buckets = {cat: [] for cat in NAMED_AMENITY_CATEGORIES}
        for el in raw.get("elements", []):
            tags = el.get("tags", {})
            for cat, (key, value) in NAMED_AMENITY_CATEGORIES.items():
                if matches(tags, key, value):
                    lat = el.get("lat") or el.get("center", {}).get("lat")
                    lon = el.get("lon") or el.get("center", {}).get("lon")
                    buckets[cat].append(
                        {"name": tags.get("name", "unnamed"), "lat": lat, "lon": lon})
                    break  # first matching category wins if an element has several tags
        return buckets

    combined = safe_query("named_amenities", ql, lambda raw: {
                          "buckets": parse(raw)})
    if combined["status"] != "ok":
        # One combined failure becomes a per-category "failed" entry, so downstream
        # code that expects one result dict per category doesn't need to change.
        return {cat: {"status": "failed", "category": cat, "reason": combined["reason"]}
                for cat in NAMED_AMENITY_CATEGORIES}

    return {
        cat: {"status": "ok", "category": cat,
              "items": items, "count": len(items)}
        for cat, items in combined["buckets"].items()
    }


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
        **named_amenities_query(area),
    }

    if event_type == "Flood":
        categories["flood_context"] = flood_context(area)

    for key, result in categories.items():
        if result["status"] == "ok":
            result["confidence"] = confidence_label(
                result.get("count", 0), area_km2, key)
        else:
            result["confidence"] = "unknown"

    return categories


# ---------- Standalone detail functions ----------
# Heavier "out geom" queries, kept OUT of the default report path (query_disaster_area)
# because full-detail dumps for buildings/roads can time out on dense urban areas or
# large radii — the same limitation already found during design (see README). These are
# meant to be called directly by a user who wants to drill into one specific area, or by
# report.py's optional include_detail_layers=True path (opt-in, off by default).

def _way_geometries(area, category_key, osm_filter, timeout=45):
    loc = _area_filter(area)
    ql = f'[out:json][timeout:{timeout}];(way{osm_filter}{loc};);out geom;'

    def parse(raw):
        items = []
        for el in raw["elements"]:
            if el.get("type") != "way" or "geometry" not in el:
                continue
            name = el.get("tags", {}).get("name", "unnamed")
            coords = [(pt["lat"], pt["lon"]) for pt in el["geometry"]]
            items.append(
                {"name": name, "coords": coords, "osm_id": el.get("id")})
        return {"items": items, "count": len(items)}

    # +10s margin so the HTTP client outlives the Overpass-side timeout above
    return safe_query(category_key, ql, parse, timeout=timeout + 10)


def get_building_geometries(area):
    """Standalone: full building footprints for one alert area, independent of build_report().
    Can time out on dense urban areas or large radii — try a smaller radius/polygon if it fails."""
    return _way_geometries(area, "building_geometries", '["building"]')


def get_road_geometries(area):
    """Standalone: full road polylines for one alert area, independent of build_report().
    Same timeout caveat as get_building_geometries."""
    return _way_geometries(area, "road_geometries", '["highway"]')
