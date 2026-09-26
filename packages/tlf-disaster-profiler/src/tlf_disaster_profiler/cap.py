import xml.etree.ElementTree as ET

CAP_NS = {"cap": "urn:oasis:names:tc:emergency:cap:1.2"}


def parse_cap(xml_text):
    """Parse a CAP XML alert into a plain dict.

    Never raises on a shape it doesn't recognize — an unparseable area
    becomes kind="unsupported" with a reason, so the caller can decide
    what to do (skip it, warn about it) rather than the whole alert dying.
    """
    root = ET.fromstring(xml_text)

    alert = {
        "identifier": _text(root, "cap:identifier"),
        "sender": _text(root, "cap:sender"),
        "sent": _text(root, "cap:sent"),
        "infos": [],
    }

    for info_el in root.findall("cap:info", CAP_NS):
        info = {
            "event": _text(info_el, "cap:event"),
            "severity": _text(info_el, "cap:severity"),
            "urgency": _text(info_el, "cap:urgency"),
            "certainty": _text(info_el, "cap:certainty"),
            "headline": _text(info_el, "cap:headline"),
            "areas": [],
        }
        for area_el in info_el.findall("cap:area", CAP_NS):
            info["areas"].append(_parse_area(area_el))
        alert["infos"].append(info)

    return alert


def _parse_area(area_el):
    area_desc = _text(area_el, "cap:areaDesc") or ""

    circle_text = _text(area_el, "cap:circle")
    if circle_text:
        try:
            coords, radius_km = circle_text.strip().split(" ")
            lat, lon = coords.split(",")
            return {
                "kind": "circle",
                "lat": float(lat),
                "lon": float(lon),
                "radius_km": float(radius_km),
                "area_desc": area_desc,
            }
        except (ValueError, IndexError) as e:
            return {"kind": "unsupported", "reason": f"malformed <circle>: {e}", "area_desc": area_desc}

    polygon_text = _text(area_el, "cap:polygon")
    if polygon_text:
        try:
            points = []
            for pair in polygon_text.strip().split(" "):
                lat, lon = pair.split(",")
                points.append((float(lat), float(lon)))
            return {"kind": "polygon", "points": points, "area_desc": area_desc}
        except (ValueError, IndexError) as e:
            return {"kind": "unsupported", "reason": f"malformed <polygon>: {e}", "area_desc": area_desc}

    # no circle or polygon — likely a <geocode> (e.g. a district code), which
    # we can't turn into coordinates without a separate lookup table
    return {"kind": "unsupported", "reason": "no circle/polygon (likely geocode-only)", "area_desc": area_desc}


def _text(parent, tag):
    el = parent.find(tag, CAP_NS)
    return el.text.strip() if el is not None and el.text else None
