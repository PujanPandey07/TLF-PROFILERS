"""tlf-disaster-profiler: CAP-alert-driven disaster impact reports for Nepal.

Given a CAP XML alert and the bundled ward boundaries, produces a structured
report of affected wards (population/households, scaled by coverage %), plus
hazard-specific and shared infrastructure findings from OpenStreetMap.
"""
from .report import build_report, render_html

__all__ = ["build_report", "render_html"]
