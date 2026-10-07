# src/satellite.py
# Step 2 of the blueprint: for every school, measure how hot the ground is
# (land surface temperature) and how green the area is (NDVI), using Landsat
# satellite images from Google Earth Engine. Saves data/satellite.csv.
#
# Before running: run src/schools.py, and log in once with `earthengine authenticate`.
# Run from the project folder:  python src/satellite.py
#
# IMPORTANT: if you ever rerun schools.py, rerun this script too. The two files
# are matched by row number, and a fresh OpenStreetMap download can change
# which school sits in which row.

import sys
from pathlib import Path

import ee
import geopandas as gpd
import pandas as pd

# --- Settings (blueprint defaults, chosen by you) -------------------------
PROJECT_ID = "bangkok-school-heat"  # your Google Cloud project name (not a secret)
FIRST_YEAR, LAST_YEAR = 2022, 2026  # five hot seasons
FIRST_MONTH, LAST_MONTH = 3, 5      # March to May, Bangkok's hot season
RADIUS_M = 150                      # size of the circle measured around each school, in metres
CHUNK_SIZE = 500                    # schools sent to Earth Engine per request; lower to 200 if it times out

# --- File locations (same idea as schools.py) -----------------------------
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SCHOOLS_FILE = DATA_DIR / "schools.geojson"
OUTPUT = DATA_DIR / "satellite.csv"

if not SCHOOLS_FILE.exists():
    sys.exit(f"Can't find {SCHOOLS_FILE}. Run src/schools.py first.")

# --- Connect to Earth Engine ----------------------------------------------
# Earth Engine runs on Google's computers, not yours. This line connects to it
# using the login saved by `earthengine authenticate`. Our code mostly
# *describes* the calculation; Google only does the work when we ask for
# results with .getInfo().
ee.Initialize(project=PROJECT_ID)

gdf = gpd.read_file(SCHOOLS_FILE)

# A rectangle around all the schools, written as [west, south, east, north].
# We only want satellite images that cover this area.
area = ee.Geometry.Rectangle([float(v) for v in gdf.total_bounds])


# --- Remove clouds --------------------------------------------------------
# Every Landsat image comes with a quality band called QA_PIXEL. Each pixel's
# value is a number whose binary digits ("bits") act as yes/no flags.
# Bit 3 = cloud, bit 4 = cloud shadow.
# (1 << 3) means binary 1000, which is "only bit 3". bitwiseAnd checks whether
# that flag is switched on. We keep pixels where both flags are off (eq(0)).
def mask_clouds(img):
    qa = img.select("QA_PIXEL")
    clear = qa.bitwiseAnd(1 << 3).eq(0).And(qa.bitwiseAnd(1 << 4).eq(0))
    return img.updateMask(clear)  # masked pixels are ignored in all later maths


# --- Turn raw numbers into temperature and greenness ----------------------
# Landsat stores measurements as whole numbers to save space. The USGS
# publishes "scaling factors" to turn them back into real units:
#   ST_B10 (thermal band) x 0.00341802 + 149.0  = temperature in kelvin
#   then subtract 273.15 to get degrees Celsius.
#   SR_B4 (red) and SR_B5 (near-infrared) x 0.0000275 - 0.2 = reflectance (0 to 1).
#
# NDVI = (near-infrared - red) / (near-infrared + red)
# Healthy plants reflect lots of near-infrared light and absorb red light, so
# vegetation gives high NDVI (around 0.3 to 0.8). Concrete and roofs are
# around 0 to 0.2. Water is below 0.
def add_bands(img):
    lst = (img.select("ST_B10").multiply(0.00341802).add(149.0)
              .subtract(273.15).rename("LST_C"))
    sr = img.select(["SR_B4", "SR_B5"]).multiply(0.0000275).add(-0.2)
    ndvi = sr.normalizedDifference(["SR_B5", "SR_B4"]).rename("NDVI")
    return img.addBands([lst, ndvi])


# --- Collect the images ---------------------------------------------------
# Landsat 8 and Landsat 9 are two satellites taking the same kind of picture.
# Merging them gives roughly one picture of Bangkok every 8 days.
collection = (ee.ImageCollection("LANDSAT/LC08/C02/T1_L2")
              .merge(ee.ImageCollection("LANDSAT/LC09/C02/T1_L2"))
              .filterBounds(area)
              .filter(ee.Filter.calendarRange(FIRST_MONTH, LAST_MONTH, "month"))
              .filter(ee.Filter.calendarRange(FIRST_YEAR, LAST_YEAR, "year"))
              .map(mask_clouds)
              .map(add_bands))

n_images = collection.size().getInfo()
print(f"Using {n_images} Landsat images (hot seasons {FIRST_YEAR}-{LAST_YEAR})")

# The median takes, for each pixel, the middle value across all images.
# One unusually hot day, or a cloud edge the mask missed, can't drag the
# median around the way it would drag an average.
composite = collection.select(["LST_C", "NDVI"]).median()

# --- Measure each school, a chunk at a time -------------------------------
# For each school we draw a circle of RADIUS_M metres and average all the 30 m
# pixels inside it. Earth Engine limits how much one request can do, so
# schools are sent in chunks. "row" records which row of schools.geojson each
# result belongs to, so Step 3 can match them back up.
rows = []
n_chunks = (len(gdf) + CHUNK_SIZE - 1) // CHUNK_SIZE  # divide, rounding up
for chunk_no, start in enumerate(range(0, len(gdf), CHUNK_SIZE), start=1):
    print(f"Chunk {chunk_no} of {n_chunks}...")
    chunk = gdf.iloc[start:start + CHUNK_SIZE]
    fc = ee.FeatureCollection([
        ee.Feature(ee.Geometry.Point([g.x, g.y]).buffer(RADIUS_M), {"row": int(i)})
        for i, g in zip(chunk.index, chunk.geometry)
    ])
    result = composite.reduceRegions(collection=fc, reducer=ee.Reducer.mean(), scale=30).getInfo()
    rows += [f["properties"] for f in result["features"]]

# columns=... fixes the column order, and gives a blank (NaN) for any school
# whose circle had no clear pixels at all.
df = pd.DataFrame(rows, columns=["row", "LST_C", "NDVI"]).sort_values("row")
df.to_csv(OUTPUT, index=False)

# --- Summary --------------------------------------------------------------
print()
print(len(df), "schools measured, saved to", OUTPUT)
print("  blank (no clear pixels):", int(df["LST_C"].isna().sum()))
print(f"  surface temp (C): min {df['LST_C'].min():.1f}, "
      f"median {df['LST_C'].median():.1f}, max {df['LST_C'].max():.1f}  (expect 30s to 40s)")
print(f"  NDVI:             min {df['NDVI'].min():.2f}, "
      f"median {df['NDVI'].median():.2f}, max {df['NDVI'].max():.2f}  (expect about -0.1 to 0.6)")
