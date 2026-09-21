import json

with open("export.geojson", encoding="utf-8") as f:
    data = json.load(f)

for feature in data["features"]:
    if "@relations" in feature["properties"]:
        print(feature["properties"])
        print()
