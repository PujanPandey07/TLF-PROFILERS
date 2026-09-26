# test_report.py
import time
from report import build_report, render_html

SAMPLE_CIRCLE_XML = """<?xml version="1.0" encoding="UTF-8"?>
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

WARDS_PARQUET_PATH = r"C:\Users\Dell\Downloads\tlf-profilers\tlf-profilers\packages\tlf-geo-profiler\src\tlf_geo_profiler\data\wards.parquet"

print("Starting build_report...", flush=True)
t0 = time.time()
report, wards_gdf = build_report(SAMPLE_CIRCLE_XML, WARDS_PARQUET_PATH)
print(f"build_report finished in {time.time()-t0:.1f}s", flush=True)

with open("test_report_output.html", "w", encoding="utf-8") as f:
    f.write(render_html(report, wards_gdf))

print("Report written to test_report_output.html")
