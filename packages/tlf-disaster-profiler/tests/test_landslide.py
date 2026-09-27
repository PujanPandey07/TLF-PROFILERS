import time
from tlf_disaster_profiler import build_report, render_html

SAMPLE_LANDSLIDE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<alert xmlns="urn:oasis:names:tc:emergency:cap:1.2">
  <identifier>LS0004521</identifier>
  <sender>dhm.gov.np</sender>
  <sent>2026-09-25T09:15:00+00:00</sent>
  <info>
    <event>Landslide</event>
    <urgency>Expected</urgency>
    <severity>Severe</severity>
    <certainty>Likely</certainty>
    <headline>Landslide warning, Sindhupalchok district (Sunkoshi corridor)</headline>
    <area>
      <areaDesc>3km around Jure area, Sindhupalchok</areaDesc>
      <circle>27.9520,85.6810 3</circle>
    </area>
  </info>
</alert>
"""

# wards_parquet_path is now auto-resolved from the installed tlf-geo-profiler
# package, so it no longer needs to be passed or hardcoded here.

if __name__ == "__main__":
    print("Starting build_report (landslide)...", flush=True)
    t0 = time.time()
    # Landslide gets landslide_context: roads within the alert area + a 100m buffer,
    # drawn on the map in a distinct color and listed as "potentially affected".
    report, wards_gdf = build_report(SAMPLE_LANDSLIDE_XML)
    print(f"build_report finished in {time.time()-t0:.1f}s", flush=True)

    with open("test_landslide_output.html", "w", encoding="utf-8") as f:
        f.write(render_html(report, wards_gdf))

    print("Report written to test_landslide_output.html")
