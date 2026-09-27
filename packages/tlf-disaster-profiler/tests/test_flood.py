import time
from tlf_disaster_profiler import build_report, render_html

SAMPLE_FLOOD_XML = """<?xml version="1.0" encoding="UTF-8"?>
<alert xmlns="urn:oasis:names:tc:emergency:cap:1.2">
  <identifier>FL0009911</identifier>
  <sender>dhm.gov.np</sender>
  <sent>2026-09-24T06:00:00+00:00</sent>
  <info>
    <event>Flood</event>
    <urgency>Expected</urgency>
    <severity>Severe</severity>
    <certainty>Likely</certainty>
    <headline>Flood warning along Bagmati river basin</headline>
    <area>
      <areaDesc>Bagmati basin, Kathmandu</areaDesc>
      <polygon>27.65,85.30 27.65,85.35 27.72,85.35 27.72,85.30 27.65,85.30</polygon>
    </area>
  </info>
</alert>
"""

# wards_parquet_path is now auto-resolved from the installed tlf-geo-profiler
# package, so it no longer needs to be passed or hardcoded here.

if __name__ == "__main__":
    print("Starting build_report (flood)...", flush=True)
    t0 = time.time()
    # Flood gets flood_context (named rivers, drawn on map) plus flood_risk flags on any
    # school/hospital/emergency point within 100m of a mapped river.
    report, wards_gdf = build_report(SAMPLE_FLOOD_XML)
    print(f"build_report finished in {time.time()-t0:.1f}s", flush=True)

    with open("test_flood_output.html", "w", encoding="utf-8") as f:
        f.write(render_html(report, wards_gdf))

    print("Report written to test_flood_output.html")
