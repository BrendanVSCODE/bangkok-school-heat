# src/schools.py
# Step 1 of the blueprint: download every school in Bangkok from OpenStreetMap
# and save each one as a single point in data/schools.geojson.
#
# Run from the project folder:  python src/schools.py

from pathlib import Path

import osmnx as ox

# --- Where to save the output ---------------------------------------------
# __file__ is the path of this script (src/schools.py). Going up two levels
# gives the project folder, so the output always lands in <project>/data,
# whichever folder you run the script from.
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)  # create data/ if missing; does nothing if it already exists
OUTPUT = DATA_DIR / "schools.geojson"

# --- Download -------------------------------------------------------------
# OpenStreetMap (OSM) labels map features with "tags", which are key=value pairs.
# Every school should carry the tag amenity=school. osmnx looks up the boundary
# of "Bangkok, Thailand", then downloads every feature inside it with that tag.
# The download can take a minute or two.
print("Downloading schools from OpenStreetMap...")
schools = ox.features_from_place("Bangkok, Thailand", tags={"amenity": "school"})

# Some schools are mapped as a single point. Others are drawn as the outline
# (polygon) of the building or campus. We record how many of each before
# turning everything into points.
geom_counts = schools.geometry.geom_type.value_counts()

# --- Turn outlines into centre points -------------------------------------
# A CRS (coordinate reference system) is how coordinates are measured.
# EPSG:4326 means latitude/longitude in degrees. A degree is not a fixed
# distance, so centres calculated in degrees come out slightly wrong.
# EPSG:32647 (UTM zone 47N) measures in metres and covers Bangkok, so we:
#   1. switch to metres, 2. take the centre (centroid), 3. switch back.
schools = schools.to_crs(32647)
schools["geometry"] = schools.geometry.centroid
schools = schools.to_crs(4326)

# --- Keep only the columns we need ----------------------------------------
# OSM features carry hundreds of possible tag columns. We keep the names
# (if those columns exist) plus the location.
keep = [c for c in ["name", "name:en", "name:th"] if c in schools.columns]
# reset_index() turns the OSM ID (e.g. "way 12345") into ordinary columns,
# so every school stays traceable back to OpenStreetMap.
schools = schools[keep + ["geometry"]].reset_index()

# --- Label schools that have no name --------------------------------------
# Some OSM schools have no name tag. We keep them, because a school is still
# a school, but give them a readable label so the map never shows a blank.
# The count is taken first, because once filled there are no blanks left
# to count.
if "name" not in schools.columns:
    schools["name"] = None  # in case no school in the download had a name
no_name = schools["name"].isna().sum()
schools["name"] = schools["name"].fillna("Unnamed school")

# The area is the official Bangkok boundary only. Duplicates are left in
# for now and will be cleaned in a later pass.
schools.to_file(OUTPUT, driver="GeoJSON")

# --- Summary --------------------------------------------------------------
# Only numbers are printed, no Thai names, because the Windows terminal
# can crash when printing Thai characters.
min_lon, min_lat, max_lon, max_lat = schools.total_bounds

print()
print(len(schools), "schools saved to", OUTPUT)
print("  labelled 'Unnamed school':", no_name)
print("  original shapes:", {shape: int(n) for shape, n in geom_counts.items()})
print("  ID columns:", [c for c in schools.columns if c not in keep + ["name", "geometry"]])
print(f"  latitude range:  {min_lat:.3f} to {max_lat:.3f}  (Bangkok is about 13.5 to 14.0)")
print(f"  longitude range: {min_lon:.3f} to {max_lon:.3f}  (Bangkok is about 100.3 to 100.95)")
