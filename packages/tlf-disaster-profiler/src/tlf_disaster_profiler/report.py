import json
from cap import parse_cap
from overlap import overlap_report, load_ward_boundaries, cap_area_to_geometry
from osm_query import query_disaster_area


def build_report(cap_xml_text, wards_parquet_path):
    """Top-level entry point: raw CAP XML -> (report dict, wards_gdf). Never raises.
    wards_gdf is returned alongside the report because render_html needs it to redraw ward shapes."""
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
        ],
    }

    for info in alert["infos"]:
        report["infos"].append({
            "event": info["event"],
            "severity": info["severity"],
            "urgency": info["urgency"],
            "certainty": info["certainty"],
            "headline": info["headline"],
            "areas": [process_area(area, wards_gdf, info["event"]) for area in info["areas"]],
        })

    return report, wards_gdf


def process_area(area, wards_gdf, event_type):
    """One CAP <area> -> ward impact + infrastructure, or a failure record."""
    if area["kind"] == "unsupported":
        return {"status": "failed", "area_desc": area["area_desc"], "reason": area["reason"]}

    geometry = cap_area_to_geometry(area)
    area_km2 = geometry.area / 1e6

    overlap = overlap_report(area, wards_gdf)
    infrastructure = query_disaster_area(area, area_km2, event_type)

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
        "total_population_affected": total_population_affected,
        "wards_with_unknown_population": wards_with_unknown_population,
        "infrastructure": infrastructure,
    }


# ---------- HTML rendering ----------

CONFIDENCE_COLORS = {"high": "#2e7d32", "low": "#e65100", "unknown": "#757575"}


def _badge(label):
    color = CONFIDENCE_COLORS.get(label, "#757575")
    return f'<span style="background:{color};color:#fff;padding:2px 8px;border-radius:10px;font-size:0.85em;">{label}</span>'


def _render_map(area, wards_gdf, map_id):
    """Builds a Leaflet map: alert shape in red, wards color-coded by coverage %, infra as markers."""
    shape = area["shape"]

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
    for cat, data in area["infrastructure"].items():
        if data["status"] != "ok" or "items" not in data:
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
                name = json.dumps(item["name"])
                marker_js_parts.append(
                    f'L.circleMarker([{item["lat"]},{item["lon"]}],{{radius:5,color:"#c62828",fillOpacity:0.8}}).bindTooltip({name}).addTo(map);'
                )
    markers_js = "\n".join(marker_js_parts)

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

    ward_rows = "".join(f"""
        <tr>
          <td>{w['ward_no']}</td><td>{w['local_level']}</td><td>{w['district']}</td>
          <td>{w['coverage_pct']}%</td>
          <td>{w['population'] if w['population_known'] else 'unknown'}</td>
          <td>{w['population_affected'] if w['population_known'] else 'unknown'}</td>
        </tr>""" for w in area["wards"])

    infra_rows = "".join(f"""
        <tr>
          <td>{cat}</td><td>{data.get('count', '-')}</td>
          <td>{_badge(data.get('confidence', 'unknown'))}</td>
          <td>{data['status'] if data['status'] == 'ok' else data.get('reason', '')}</td>
        </tr>""" for cat, data in area["infrastructure"].items())

    return f"""
    <div style="border:1px solid #ccc;padding:12px;margin:10px 0;border-radius:6px;">
      <strong>Area:</strong> {area['area_desc']} ({area['area_km2']} km²)<br>
      {map_html}
      <strong>Total population affected (scaled by ward coverage):</strong> {area['total_population_affected']:,}
      {f"<br><em>{area['wards_with_unknown_population']} ward(s) with unknown population</em>" if area['wards_with_unknown_population'] else ""}

      <h4>Affected Wards</h4>
      <table border="1" cellpadding="6" style="border-collapse:collapse;width:100%;">
        <tr><th>Ward</th><th>Local Level</th><th>District</th><th>Coverage</th><th>Population</th><th>Est. Affected</th></tr>
        {ward_rows}
      </table>

      <h4>Infrastructure</h4>
      <table border="1" cellpadding="6" style="border-collapse:collapse;width:100%;">
        <tr><th>Category</th><th>Count</th><th>Confidence</th><th>Notes</th></tr>
        {infra_rows}
      </table>
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
