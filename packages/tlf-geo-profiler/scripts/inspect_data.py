"""Look inside the bundled boundary files (parquet can't be opened in an editor).

    uv run --package tlf-geo-profiler python packages/tlf-geo-profiler/scripts/inspect_data.py
    uv run --package tlf-geo-profiler python packages/tlf-geo-profiler/scripts/inspect_data.py --csv

Prints, for each file: how many rows, what each column holds, and a few sample rows.
With --csv it also writes one CSV per file (everything except the shape itself)
into data_preview/, which you can open in VS Code or Excel.
"""

import argparse
from pathlib import Path

import geopandas as gpd
import pandas as pd

DATA_DIR = Path(__file__).resolve(
).parents[1] / "src" / "tlf_geo_profiler" / "data"
FILES = ["provinces", "districts", "local_levels", "wards"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", action="store_true",
                    help="also write data_preview/*.csv")
    args = ap.parse_args()

    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", 20)
    pd.set_option("display.max_colwidth", 30)

    for name in FILES:
        gdf = gpd.read_parquet(DATA_DIR / f"{name}.parquet")
        table = gdf.drop(columns="geometry")
        print("=" * 70)
        print(f"{name}.parquet  -  {len(gdf)} rows")
        print("shape types:", gdf.geom_type.value_counts().to_dict())
        print("columns:")
        for col in table.columns:
            filled = int(table[col].notna().sum())
            print(
                f"  {col:12s} {str(table[col].dtype):10s} filled in {filled} of {len(gdf)} rows")
        print("first 5 rows:")
        print(table.head(5).to_string())
        if args.csv:
            out = Path("data_preview")
            out.mkdir(exist_ok=True)
            table.to_csv(out / f"{name}.csv",
                         index=False, encoding="utf-8-sig")
            print(f"-> wrote data_preview/{name}.csv")


if __name__ == "__main__":
    main()
