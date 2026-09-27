"""Tests for cap.py. Pure XML parsing, no network calls, no ward data needed —
these should run anywhere, including CI with no Overpass or geodata access."""
from tlf_disaster_profiler import cap


def test_parse_circle_area():
    xml_text = """<?xml version="1.0" encoding="UTF-8"?>
    <alert xmlns="urn:oasis:names:tc:emergency:cap:1.2">
      <identifier>TEST1</identifier>
      <sender>test@example.com</sender>
      <sent>2026-01-01T00:00:00+00:00</sent>
      <info>
        <event>Earthquake</event>
        <severity>Moderate</severity>
        <urgency>Immediate</urgency>
        <certainty>Observed</certainty>
        <headline>Test earthquake</headline>
        <area>
          <areaDesc>Test circle</areaDesc>
          <circle>27.7,85.3 10</circle>
        </area>
      </info>
    </alert>"""
    alert = cap.parse_cap(xml_text)
    assert alert["identifier"] == "TEST1"
    area = alert["infos"][0]["areas"][0]
    assert area["kind"] == "circle"
    assert area["lat"] == 27.7
    assert area["lon"] == 85.3
    assert area["radius_km"] == 10


def test_parse_polygon_area():
    xml_text = """<?xml version="1.0" encoding="UTF-8"?>
    <alert xmlns="urn:oasis:names:tc:emergency:cap:1.2">
      <identifier>TEST2</identifier>
      <sender>test@example.com</sender>
      <sent>2026-01-01T00:00:00+00:00</sent>
      <info>
        <event>Flood</event>
        <severity>Severe</severity>
        <urgency>Expected</urgency>
        <certainty>Likely</certainty>
        <headline>Test flood</headline>
        <area>
          <areaDesc>Test polygon</areaDesc>
          <polygon>27.0,85.0 27.0,85.1 27.1,85.1 27.1,85.0 27.0,85.0</polygon>
        </area>
      </info>
    </alert>"""
    alert = cap.parse_cap(xml_text)
    area = alert["infos"][0]["areas"][0]
    assert area["kind"] == "polygon"
    assert len(area["points"]) == 5
    assert area["points"][0] == (27.0, 85.0)


def test_malformed_circle_is_unsupported_not_a_crash():
    xml_text = """<?xml version="1.0" encoding="UTF-8"?>
    <alert xmlns="urn:oasis:names:tc:emergency:cap:1.2">
      <identifier>TEST3</identifier>
      <sender>test@example.com</sender>
      <sent>2026-01-01T00:00:00+00:00</sent>
      <info>
        <event>Earthquake</event>
        <severity>Moderate</severity>
        <urgency>Immediate</urgency>
        <certainty>Observed</certainty>
        <headline>Test malformed</headline>
        <area>
          <areaDesc>Broken circle</areaDesc>
          <circle>not-a-real-circle</circle>
        </area>
      </info>
    </alert>"""
    alert = cap.parse_cap(xml_text)
    area = alert["infos"][0]["areas"][0]
    assert area["kind"] == "unsupported"
    assert "malformed" in area["reason"]


def test_geocode_only_area_is_unsupported():
    xml_text = """<?xml version="1.0" encoding="UTF-8"?>
    <alert xmlns="urn:oasis:names:tc:emergency:cap:1.2">
      <identifier>TEST4</identifier>
      <sender>test@example.com</sender>
      <sent>2026-01-01T00:00:00+00:00</sent>
      <info>
        <event>Flood</event>
        <severity>Minor</severity>
        <urgency>Future</urgency>
        <certainty>Possible</certainty>
        <headline>Test geocode-only</headline>
        <area>
          <areaDesc>District code only, no shape</areaDesc>
          <geocode>
            <valueName>DistrictCode</valueName>
            <value>27</value>
          </geocode>
        </area>
      </info>
    </alert>"""
    alert = cap.parse_cap(xml_text)
    area = alert["infos"][0]["areas"][0]
    assert area["kind"] == "unsupported"
    assert "geocode" in area["reason"]


def test_multiple_info_blocks_all_parsed():
    """CAP allows several <info> blocks in one alert — must not silently drop any."""
    xml_text = """<?xml version="1.0" encoding="UTF-8"?>
    <alert xmlns="urn:oasis:names:tc:emergency:cap:1.2">
      <identifier>TEST5</identifier>
      <sender>test@example.com</sender>
      <sent>2026-01-01T00:00:00+00:00</sent>
      <info>
        <event>Earthquake</event>
        <severity>Moderate</severity>
        <urgency>Immediate</urgency>
        <certainty>Observed</certainty>
        <headline>First info</headline>
        <area><areaDesc>A</areaDesc><circle>27.0,85.0 5</circle></area>
      </info>
      <info>
        <event>Flood</event>
        <severity>Severe</severity>
        <urgency>Expected</urgency>
        <certainty>Likely</certainty>
        <headline>Second info</headline>
        <area><areaDesc>B</areaDesc><circle>28.0,86.0 5</circle></area>
      </info>
    </alert>"""
    alert = cap.parse_cap(xml_text)
    assert len(alert["infos"]) == 2
    assert alert["infos"][0]["event"] == "Earthquake"
    assert alert["infos"][1]["event"] == "Flood"
