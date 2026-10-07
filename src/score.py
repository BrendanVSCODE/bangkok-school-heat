# src/score.py
# Step 3 of the blueprint: combine surface temperature and greenness into a
# single heat risk score from 0 (coolest) to 100 (hottest) for every school.
# Saves data/scores.geojson (for the map) and data/scores.csv (for reading).
#
# Before running: run src/schools.py, then src/satellite.py.
# Run from the project folder:  python src/score.py

import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd

# --- Settings (blueprint defaults, chosen by you) -------------------------
# How much each part counts. The two weights add up to 1, so you only set
# W_HOT and the greenery weight is whatever is left over.
# This is a judgement call, not science: record your reason in the README.
W_HOT = 0.7          # weight for hot surroundings
W_GREEN = 1 - W_HOT  # weight for lack of greenery (0.3)
# Other weightings to compare against, to see if the ranking is stable.
ALTERNATIVE_W_HOT = [0.6, 0.8]
TOP_N = 20

# --- File locations -------------------------------------------------------
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SCHOOLS_FILE = DATA_DIR / "schools.geojson"
SATELLITE_FILE = DATA_DIR / "satellite.csv"

for f, script in [(SCHOOLS_FILE, "schools.py"), (SATELLITE_FILE, "satellite.py")]:
    if not f.exists():
        sys.exit(f"Can't find {f}. Run src/{script} first.")

# --- Load and join --------------------------------------------------------
gdf = gpd.read_file(SCHOOLS_FILE)                      # rows numbered 0, 1, 2...
sat = pd.read_csv(SATELLITE_FILE).set_index("row")     # use "row" as the row label

# Safety check: satellite.csv must have exactly one result for each school.
# If schools.py was rerun after satellite.py, the row numbers no longer refer
# to the same schools, and joining would give schools the wrong values.
if sorted(sat.index) != list(gdf.index):
    sys.exit("schools.geojson and satellite.csv don't match row for row. "
             "Rerun src/satellite.py, then this script.")

# join() lines rows up by their row label, adding the LST_C and NDVI columns.
df = gdf.join(sat)


# --- The score ------------------------------------------------------------
# A percentile says where a school ranks among all schools, from 0 to 1.
# lst_pct = 0.9 means the school is hotter than (or equal to) 90% of schools.
# Using percentiles puts temperature (in C) and NDVI (no units) on the same
# 0-to-1 scale, so they can be added together.
#
# High greenness lowers risk, so we use (1 - green_pct): "lack of greenery".
# Schools with no measurement (blank in satellite.csv) get a blank score.
def heat_score(data, w_hot):
    lst_pct = data["LST_C"].rank(pct=True)
    green_pct = data["NDVI"].rank(pct=True)
    return (w_hot * lst_pct + (1 - w_hot) * (1 - green_pct)) * 100


df["lst_pct"] = df["LST_C"].rank(pct=True)
df["green_pct"] = df["NDVI"].rank(pct=True)
df["heat_risk"] = heat_score(df, W_HOT)

# --- Save -----------------------------------------------------------------
df.to_file(DATA_DIR / "scores.geojson", driver="GeoJSON")
# utf-8-sig adds a small marker at the start of the file that tells Excel the
# text is UTF-8, so Thai names display properly instead of as garbled symbols.
(df.drop(columns="geometry")
   .sort_values("heat_risk", ascending=False)        # hottest first; blanks go last
   .to_csv(DATA_DIR / "scores.csv", index=False, encoding="utf-8-sig"))

# --- Summary --------------------------------------------------------------
print(df["heat_risk"].notna().sum(), "schools scored, saved to", DATA_DIR / "scores.csv")
print("  no score (no satellite measurement):", int(df["heat_risk"].isna().sum()))

# The OSM ID columns are called element/id (osmnx 2.x) or element_type/osmid (1.x).
id_cols = [c for c in ["element", "id", "element_type", "osmid"] if c in df.columns]
top = df.nlargest(TOP_N, "heat_risk")
print()
print(f"Top {TOP_N} by heat risk ({W_HOT:.0%} heat / {W_GREEN:.0%} lack of greenery):")
print(top[["name"] + id_cols + ["LST_C", "NDVI", "heat_risk"]]
      .round({"LST_C": 1, "NDVI": 2, "heat_risk": 0})
      .to_string(index=False))

# --- Sensitivity check ----------------------------------------------------
# Rescore with different weights and count how many of today's top schools
# are still in the top list. A high count means the ranking doesn't depend
# much on the exact weights, which you can say in the README.
print()
print(f"Weight sensitivity (how many of the top {TOP_N} stay in the top {TOP_N}):")
top_rows = set(top.index)
for w in ALTERNATIVE_W_HOT:
    alt_top = set(heat_score(df, w).nlargest(TOP_N).index)
    print(f"  {w:.0%}/{1 - w:.0%}: {len(top_rows & alt_top)} of {TOP_N}")
