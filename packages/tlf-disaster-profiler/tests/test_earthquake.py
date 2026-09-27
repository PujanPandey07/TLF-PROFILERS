import time
from tlf_disaster_profiler import build_report, render_html

SAMPLE_EARTHQUAKE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<alert xmlns="urn:oasis:names:tc:emergency:cap:1.2">
  <identifier>EQ1567678</identifier>
  <sender>gdacs@jrc.ec.europa.eu</sender>
  <sent>2026-09-23T14:41:02+00:00</sent>
  <info>
    <event>Earthquake</event>
    <urgency>Immediate</urgency>
    <severity>Moderate</severity>
    <certainty>Observed</certainty>
    <headline>Green earthquake alert (Magnitude 5.7M, Depth:10km)</headline>
    <area>
      <areaDesc>10km around epicenter, Kathmandu Valley</areaDesc>
      <circle>27.7040,85.3070 10</circle>
    </area>
  </info>
</alert>
"""

# wards_parquet_path is now auto-resolved from the installed tlf-geo-profiler
# package, so it no longer needs to be passed or hardcoded here.

if __name__ == "__main__":
    print("Starting build_report (earthquake)...", flush=True)
    t0 = time.time()
    # Earthquake gets NO hazard-specific layer (no flood_context, no landslide_context) —
    # just the shared buildings/roads/schools/hospitals/emergency infrastructure report.
    report, wards_gdf = build_report(SAMPLE_EARTHQUAKE_XML)
    print(f"build_report finished in {time.time()-t0:.1f}s", flush=True)

    with open("test_earthquake_output.html", "w", encoding="utf-8") as f:
        f.write(render_html(report, wards_gdf))

    print("Report written to test_earthquake_output.html")
