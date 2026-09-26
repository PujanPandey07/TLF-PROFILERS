import json
from cap import parse_cap
from overlap import (
    overlap_report, load_ward_boundaries, cap_area_to_geometry,
    bin_items_by_ward, buffered_area, flag_items_near_lines,
)
from osm_query import query_disaster_area, get_building_geometries, get_road_geometries

# Both agreed at 100m: how close counts as "at risk" for an amenity near a river,
# and how far past the landslide alert's drawn edge to still check for roads.
RIVER_RISK_BUFFER_M = 100
LANDSLIDE_ROAD_BUFFER_M = 100


def build_report(cap_xml_text, wards_parquet_path, include_detail_layers=False):
    """Top-level entry point: raw CAP XML -> (report dict, wards_gdf). Never raises.

    include_detail_layers=False (default) keeps the report fast: buildings/roads stay
    as shape-wide counts only. Pass True to also fetch full building/road geometry as
    an opt-in, off-by-default Leaflet layer — this issues heavier Overpass queries and
    can time out on dense urban areas or large radii (see README limitations).
    """
    alert = parse_cap(cap_xml_text)
    wards_gdf = load_ward_boundaries(wards_parquet_path)

    report = {
        "identifier": alert["identifier"],
        "sender": alert["sender"],
        "sent": alert["sent"],
        "infos": [],
        "warnings": [
            "Results reflect OpenStreetMap mapping coverage, not verified ground truth.",
            "Population figures use Nepal's 2021 census, joined by ward; some wards may show population as unknown if name resolution failed.",
            "Population-affected figures assume population is spread evenly across a ward's area, scaled by the % of that ward's area the alert shape covers.",
            f"An amenity flagged 'flood_risk' is within {RIVER_RISK_BUFFER_M}m of a mapped river in a straight line — this ignores terrain, elevation and real flood-plain shape.",
            f"Roads listed as potentially affected by a landslide fall within the alert area or {LANDSLIDE_ROAD_BUFFER_M}m of its edge — same straight-line-buffer caveat applies.",
        ],
    }

    for info in alert["infos"]:
        report["infos"].append({
            "event": info["event"],
            "severity": info["severity"],
            "urgency": info["urgency"],
            "certainty": info["certainty"],
            "headline": info["headline"],
            "areas": [process_area(area, wards_gdf, info["event"], include_detail_layers) for area in info["areas"]],
        })

    return report, wards_gdf


def process_area(area, wards_gdf, event_type, include_detail_layers=False):
    """One CAP <area> -> ward impact + infrastructure, or a failure record."""
    if area["kind"] == "unsupported":
        return {"status": "failed", "area_desc": area["area_desc"], "reason": area["reason"]}

    geometry = cap_area_to_geometry(area)
    area_km2 = geometry.area / 1e6

    overlap = overlap_report(area, wards_gdf)
    infrastructure = query_disaster_area(area, area_km2, event_type)

    # Flood-specific: flag amenities within RIVER_RISK_BUFFER_M of a mapped river
    if event_type == "Flood":
        flood = infrastructure.get("flood_context")
        if flood and flood["status"] == "ok":
            river_segments = [seg for river in flood["items"]
                              for seg in river["segments"]]
            for cat in ("schools", "hospitals", "emergency"):
                data = infrastructure.get(cat)
                if data and data["status"] == "ok":
                    flag_items_near_lines(
                        data["items"], river_segments, RIVER_RISK_BUFFER_M)

    # Landslide-specific: roads within the alert area (+ a buffer past its edge),
    # shown as potentially affected — mirrors flood_context's role for rivers.
    if event_type == "Landslide":
        landslide_area = buffered_area(area, LANDSLIDE_ROAD_BUFFER_M)
        if landslide_area is not None:
            infrastructure["landslide_context"] = get_road_geometries(
                landslide_area)
        else:
            infrastructure["landslide_context"] = {
                "status": "failed", "category": "landslide_context",
                "reason": "could not buffer area geometry",
            }

    # Bin point-based amenities (schools/hospitals/emergency) into the ward each one
    # physically falls inside — a local spatial join, no extra Overpass calls — so the
    # report can nest them under their ward instead of showing one flat list.
    for cat in ("schools", "hospitals", "emergency"):
        data = infrastructure.get(cat)
        if data and data["status"] == "ok":
            bin_items_by_ward(data["items"], wards_gdf)

    by_ward, unassigned = _group_amenities_by_ward(infrastructure)

    detail = None
    if include_detail_layers:
        detail = {
            "buildings": get_building_geometries(area),
            "roads": get_road_geometries(area),
        }

    known_pop_wards = [w for w in overlap["wards"] if w["population_known"]]
    total_population_affected = sum(
        w["population_affected"] for w in known_pop_wards)
    wards_with_unknown_population = len(
        overlap["wards"]) - len(known_pop_wards)

    return {
        "status": "ok",
        "area_desc": area["area_desc"],
        "shape": area,  # original circle/polygon dict, kept for map drawing
        "area_km2": round(area_km2, 2),
        "wards": overlap["wards"],
        "amenities_by_ward": by_ward,
        "amenities_unassigned": unassigned,
        "total_population_affected": total_population_affected,
        "wards_with_unknown_population": wards_with_unknown_population,
        "infrastructure": infrastructure,
        "detail": detail,
    }


def _group_amenities_by_ward(infrastructure):
    """{'schools': {...items with ward_osm_id...}, ...} -> ({ward_osm_id: {cat: [items]}}, unassigned)."""
    by_ward = {}
    unassigned = {}
    for cat in ("schools", "hospitals", "emergency"):
        data = infrastructure.get(cat)
        if not data or data["status"] != "ok":
            continue
        for item in data.get("items", []):
            wid = item.get("ward_osm_id")
            bucket = by_ward.setdefault(
                wid, {}) if wid is not None else unassigned
            bucket.setdefault(cat, []).append(item)
    return by_ward, unassigned


def _group_wards_hierarchy(wards):
    """Flat ward list -> nested {province: {district: {local_level: [wards]}}}, plus
    order lists so rendering keeps first-seen order instead of an arbitrary dict order."""
    tree = {}
    order_p, order_d, order_l = [], {}, {}
    for w in wards:
        p, d, l = w["province"], w["district"], w["local_level"]
        if p not in tree:
            tree[p] = {}
            order_p.append(p)
        if d not in tree[p]:
            tree[p][d] = {}
            order_d.setdefault(p, []).append(d)
        if l not in tree[p][d]:
            tree[p][d][l] = []
            order_l.setdefault((p, d), []).append(l)
        tree[p][d][l].append(w)
    return tree, order_p, order_d, order_l


# ---------- HTML rendering ----------

CONFIDENCE_COLORS = {"high": "#2e7d32", "low": "#e65100", "unknown": "#757575"}


def _badge(label):
    color = CONFIDENCE_COLORS.get(label, "#757575")
    return f'<span style="background:{color};color:#fff;padding:2px 8px;border-radius:10px;font-size:0.85em;">{label}</span>'


def _render_amenities_for_ward(ward_amenities):
    """Categorized dropdown: one summary line, expanding to a per-category dropdown
    (Schools / Hospitals / Emergency), each expanding to its own item list. Kept out
    of the ward-number cell so the ward table stays readable at a glance."""
    if not ward_amenities:
        return "<span style='color:#999;font-size:0.85em;'>&mdash;</span>"

    total = sum(len(items) for items in ward_amenities.values())
    cats_html = ""
    for cat, items in ward_amenities.items():
        rows = "".join(
            f"<li>{item['name']}"
            + (" <strong style='color:#e65100;'>&#9888; within "
               f"{RIVER_RISK_BUFFER_M}m of a river</strong>" if item.get("flood_risk") else "")
            + "</li>"
            for item in items
        )
        cats_html += f"""
        <details style="margin:2px 0 2px 12px;">
          <summary style="cursor:pointer;">{cat.capitalize()} ({len(items)})</summary>
          <ul style="margin:2px 0 0 0;padding-left:16px;font-size:0.85em;">{rows}</ul>
        </details>"""

    return f"""
    <details>
      <summary style="cursor:pointer;color:#1565c0;">{total} amenit{'y' if total == 1 else 'ies'}</summary>
      {cats_html}
    </details>"""


def _render_ward_hierarchy(wards, by_ward):
    if not wards:
        return "<p>No wards intersect this alert area.</p>"

    tree, order_p, order_d, order_l = _group_wards_hierarchy(wards)
    html = ""
    for p in order_p:
        html += f"<details open style='margin:6px 0;'><summary style='font-weight:bold;'>{p}</summary>"
        for d in order_d.get(p, []):
            html += f"<details open style='margin:4px 0 4px 14px;'><summary>{d}</summary>"
            for l in order_l.get((p, d), []):
                html += f"<details open style='margin:4px 0 4px 14px;'><summary>{l}</summary>"
                html += "<table border='1' cellpadding='6' style='border-collapse:collapse;width:100%;margin:4px 0;'>"
                html += "<tr><th>Ward</th><th>Coverage</th><th>Population</th><th>Est. Affected</th><th>Amenities</th></tr>"
                for w in tree[p][d][l]:
                    amen_html = _render_amenities_for_ward(
                        by_ward.get(w["ward_osm_id"], {}))
                    html += f"""
                    <tr>
                      <td>{w['ward_no']}</td>
                      <td>{w['coverage_pct']}%</td>
                      <td>{w['population'] if w['population_known'] else 'unknown'}</td>
                      <td>{w['population_affected'] if w['population_known'] else 'unknown'}</td>
                      <td>{amen_html}</td>
                    </tr>"""
                html += "</table></details>"
            html += "</details>"
        html += "</details>"
    return html


def _render_area_wide_infra(infrastructure):
    """Buildings/roads — shape-wide counts, shown separately from the per-ward
    breakdown because they're not reliably attributable to a single ward (see README)."""
    rows = ""
    for cat in ("buildings", "roads"):
        data = infrastructure.get(cat)
        if not data:
            continue
        rows += f"""
        <tr>
          <td>{cat}</td><td>{data.get('count', '-')}</td>
          <td>{_badge(data.get('confidence', 'unknown'))}</td>
          <td>{data['status'] if data['status'] == 'ok' else data.get('reason', '')}</td>
        </tr>"""
    if not rows:
        return ""
    return f"""
    <h4>Area-wide Infrastructure (buildings &amp; roads — shape-wide counts, not split by ward)</h4>
    <table border="1" cellpadding="6" style="border-collapse:collapse;width:100%;">
      <tr><th>Category</th><th>Count</th><th>Confidence</th><th>Notes</th></tr>
      {rows}
    </table>"""


def _render_rivers(infrastructure):
    data = infrastructure.get("flood_context")
    if not data:
        return ""
    if data["status"] != "ok":
        return f"<h4>Rivers</h4><p>{_badge('unknown')} flood context failed — {data.get('reason', '')}</p>"
    if not data["items"]:
        return "<h4>Rivers</h4><p>No named rivers found nearby.</p>"
    rows = "".join(
        f"<li>{r['name']} ({len(r['segments'])} segment(s), drawn on map)</li>" for r in data["items"])
    return f"""
    <h4>Rivers (shown separately — a river spans many wards, unlike a school or hospital)</h4>
    <ul>{rows}</ul>"""


def _render_landslide_roads(infrastructure):
    data = infrastructure.get("landslide_context")
    if not data:
        return ""
    if data["status"] != "ok":
        return (f"<h4>Roads Potentially Affected (Landslide)</h4>"
                f"<p>{_badge('unknown')} query failed — {data.get('reason', '')}</p>")
    if not data["items"]:
        return (f"<h4>Roads Potentially Affected (Landslide)</h4>"
                f"<p>No roads found within the alert area or its {LANDSLIDE_ROAD_BUFFER_M}m buffer.</p>")
    rows = "".join(f"<li>{r['name']}</li>" for r in data["items"])
    return f"""
    <h4>Roads Potentially Affected (alert area + {LANDSLIDE_ROAD_BUFFER_M}m buffer, drawn on map in a different color)</h4>
    <ul>{rows}</ul>"""


def _render_map(area, wards_gdf, map_id):
    """Builds a Leaflet map: alert shape in red, wards color-coded by coverage %,
    amenity points as markers, rivers as colored polylines, and — only if
    include_detail_layers=True was used — an opt-in, off-by-default layer control
    for full building/road geometry."""
    shape = area["shape"]
    infrastructure = area["infrastructure"]

    ward_features = []
    ward_ids = {w["ward_osm_id"] for w in area["wards"]}
    coverage_by_id = {w["ward_osm_id"]: w["coverage_pct"]
                      for w in area["wards"]}

    matched = wards_gdf[wards_gdf["osm_id"].isin(ward_ids)].to_crs("EPSG:4326")
    for _, row in matched.iterrows():
        ward_features.append({
            "type": "Feature",
            "geometry": row.geometry.__geo_interface__,
            "properties": {"coverage_pct": coverage_by_id.get(row["osm_id"], 0), "name": row["name"]},
        })
    ward_geojson = {"type": "FeatureCollection", "features": ward_features}

    if shape["kind"] == "circle":
        alert_js = f'L.circle([{shape["lat"]}, {shape["lon"]}], {{radius: {shape["radius_km"]*1000}, color:"red", weight:2, fillOpacity:0.1}}).addTo(map);'
        center = f'[{shape["lat"]}, {shape["lon"]}]'
    else:
        coords_js = json.dumps([[lat, lon] for lat, lon in shape["points"]])
        alert_js = f'L.polygon({coords_js}, {{color:"red", weight:2, fillOpacity:0.1}}).addTo(map);'
        center = json.dumps(list(shape["points"][0]))

    marker_js_parts = []
    for cat in ("schools", "hospitals", "emergency"):
        data = infrastructure.get(cat)
        if not data or data["status"] != "ok" or "items" not in data:
            continue
        dense = len(data["items"]) > 100
        for item in data["items"]:
            if item["lat"] is None or item["lon"] is None:
                continue
            if dense:
                marker_js_parts.append(
                    f'L.circleMarker([{item["lat"]},{item["lon"]}],{{radius:2,color:"#1565c0",fillOpacity:0.6}}).addTo(map);'
                )
            else:
                # Amenities flagged flood_risk (within RIVER_RISK_BUFFER_M of a river)
                # are colored differently from ordinary schools/hospitals/emergency points.
                color = "#ef6c00" if item.get("flood_risk") else "#c62828"
                tooltip = item["name"] + \
                    (f" (within {RIVER_RISK_BUFFER_M}m of a river)" if item.get(
                        "flood_risk") else "")
                name = json.dumps(tooltip)
                marker_js_parts.append(
                    f'L.circleMarker([{item["lat"]},{item["lon"]}],{{radius:5,color:"{color}",fillOpacity:0.8}}).bindTooltip({name}).addTo(map);'
                )
    markers_js = "\n".join(marker_js_parts)

    # Rivers — each named river drawn as its own colored polyline (cycling a small palette)
    river_palette = ["#0277bd", "#00838f",
                     "#6a1b9a", "#ad1457", "#4527a0", "#00695c"]
    river_js_parts = []
    flood = infrastructure.get("flood_context")
    if flood and flood["status"] == "ok":
        for i, river in enumerate(flood["items"]):
            color = river_palette[i % len(river_palette)]
            name = json.dumps(river["name"])
            for seg in river["segments"]:
                coords_js = json.dumps([[lat, lon] for lat, lon in seg])
                river_js_parts.append(
                    f'L.polyline({coords_js}, {{color:{json.dumps(color)}, weight:3}}).bindTooltip({name}).addTo(map);'
                )
    rivers_js = "\n".join(river_js_parts)

    # Landslide-affected roads — always drawn (not gated behind the opt-in detail
    # toggle) since this is a hazard-specific layer like rivers, not raw full detail.
    landslide_js_parts = []
    landslide = infrastructure.get("landslide_context")
    if landslide and landslide["status"] == "ok":
        for r in landslide["items"]:
            coords_js = json.dumps([[lat, lon] for lat, lon in r["coords"]])
            name = json.dumps(r["name"] + " (potentially affected)")
            landslide_js_parts.append(
                f'L.polyline({coords_js}, {{color:"#e65100", weight:4}}).bindTooltip({name}).addTo(map);'
            )
    landslide_js = "\n".join(landslide_js_parts)

    # Optional full building/road geometry — off by default, toggled on via layer control
    detail = area.get("detail")
    detail_layers_js = ""
    layer_control_js = ""
    if detail:
        overlay_entries = []
        if detail.get("buildings", {}).get("status") == "ok":
            polys = []
            for b in detail["buildings"]["items"]:
                coords_js = json.dumps([[lat, lon]
                                       for lat, lon in b["coords"]])
                polys.append(
                    f'L.polygon({coords_js}, {{color:"#8d6e63", weight:1, fillOpacity:0.3}})')
            detail_layers_js += f'var buildingsLayer = L.layerGroup([{",".join(polys)}]);\n'
            overlay_entries.append('"Buildings (detail)": buildingsLayer')
        if detail.get("roads", {}).get("status") == "ok":
            lines = []
            for r in detail["roads"]["items"]:
                coords_js = json.dumps([[lat, lon]
                                       for lat, lon in r["coords"]])
                lines.append(
                    f'L.polyline({coords_js}, {{color:"#546e7a", weight:2}})')
            detail_layers_js += f'var roadsLayer = L.layerGroup([{",".join(lines)}]);\n'
            overlay_entries.append('"Roads (detail)": roadsLayer')
        if overlay_entries:
            layer_control_js = f'L.control.layers(null, {{{",".join(overlay_entries)}}}).addTo(map);'
            # NOTE: overlays start unchecked/off the map on purpose — they are opt-in.

    return f"""
    <div id="{map_id}" style="height:400px;margin:10px 0;border-radius:6px;"></div>
    <script>
      (function() {{
        var map = L.map("{map_id}").setView({center}, 13);
        L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
          attribution: '&copy; OpenStreetMap contributors'
        }}).addTo(map);
        {alert_js}
        L.geoJSON({json.dumps(ward_geojson)}, {{
          style: function(f) {{
            var c = f.properties.coverage_pct;
            var color = c > 66 ? "#b71c1c" : c > 33 ? "#ef6c00" : "#fbc02d";
            return {{color: color, weight: 1, fillOpacity: 0.35}};
          }},
          onEachFeature: function(f, layer) {{
            layer.bindTooltip(f.properties.name + ": " + f.properties.coverage_pct + "% covered");
          }}
        }}).addTo(map);
        {markers_js}
        {rivers_js}
        {landslide_js}
        {detail_layers_js}
        {layer_control_js}
      }})();
    </script>"""


def _render_area(area, wards_gdf, map_id):
    if area["status"] == "failed":
        return f"""
        <div style="border:1px solid #e57373;padding:12px;margin:10px 0;border-radius:6px;">
          <strong>Area:</strong> {area['area_desc']}<br>
          <strong>Status:</strong> {_badge('unknown')} failed to process — {area['reason']}
        </div>"""

    map_html = _render_map(area, wards_gdf, map_id)
    ward_hierarchy_html = _render_ward_hierarchy(
        area["wards"], area["amenities_by_ward"])

    unassigned_html = ""
    if area["amenities_unassigned"]:
        amen_html = _render_amenities_for_ward(area["amenities_unassigned"])
        unassigned_html = f"""
        <p style="font-size:0.85em;color:#888;">
          Some amenities fell outside every mapped ward boundary (an edge-of-dataset effect):
          {amen_html}
        </p>"""

    return f"""
    <div style="border:1px solid #ccc;padding:12px;margin:10px 0;border-radius:6px;">
      <strong>Area:</strong> {area['area_desc']} ({area['area_km2']} km²)<br>
      {map_html}
      <strong>Total population affected (scaled by ward coverage):</strong> {area['total_population_affected']:,}
      {f"<br><em>{area['wards_with_unknown_population']} ward(s) with unknown population</em>" if area['wards_with_unknown_population'] else ""}

      <h4>Affected Wards (Province &rarr; District &rarr; Local Level &rarr; Ward)</h4>
      {ward_hierarchy_html}
      {unassigned_html}

      {_render_area_wide_infra(area["infrastructure"])}
      {_render_rivers(area["infrastructure"])}
      {_render_landslide_roads(area["infrastructure"])}
    </div>"""


def render_html(report, wards_gdf):
    """(report dict, wards_gdf) -> a single self-contained HTML string."""
    infos_html = ""
    for info in report["infos"]:
        areas_html = ""
        for i, a in enumerate(info["areas"]):
            areas_html += _render_area(a, wards_gdf,
                                       map_id=f"map-{info['event']}-{i}")
        infos_html += f"""
        <h2>{info['event']} — {info['headline']}</h2>
        <p><strong>Severity:</strong> {info['severity']} | <strong>Urgency:</strong> {info['urgency']} | <strong>Certainty:</strong> {info['certainty']}</p>
        {areas_html}"""

    warnings_html = "".join(f"<li>{w}</li>" for w in report["warnings"])

    return f"""<!DOCTYPE html>
<html><head>
  <meta charset="utf-8">
  <title>Disaster Report — {report['identifier']}</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
</head>
<body style="font-family:sans-serif;max-width:900px;margin:40px auto;">
  <h1>Disaster Report</h1>
  <p><strong>Alert ID:</strong> {report['identifier']} | <strong>Sender:</strong> {report['sender']} | <strong>Sent:</strong> {report['sent']}</p>
  {infos_html}
  <h3>Warnings</h3>
  <ul>{warnings_html}</ul>
</body></html>"""
