# src/make_map.py
# Step 4 of the blueprint: build an interactive web map with one dot per
# school, coloured by heat risk score. Saves docs/index.html, which GitHub
# Pages can publish as a website.
#
# Before running: run src/score.py, and install folium (python -m pip install folium).
# Run from the project folder:  python src/make_map.py

import html
import sys
from pathlib import Path

import branca.colormap as cm
import folium
import geopandas as gpd

# --- File locations -------------------------------------------------------
PROJECT_DIR = Path(__file__).resolve().parent.parent
SCORES_FILE = PROJECT_DIR / "data" / "scores.geojson"
DOCS_DIR = PROJECT_DIR / "docs"   # GitHub Pages publishes this folder
OUTPUT = DOCS_DIR / "index.html"  # "index.html" is the page a website opens by default

if not SCORES_FILE.exists():
    sys.exit(f"Can't find {SCORES_FILE}. Run src/score.py first.")
DOCS_DIR.mkdir(exist_ok=True)

# --- Load the scores ------------------------------------------------------
all_schools = gpd.read_file(SCORES_FILE)
# Schools with no satellite measurement have no score, so they are left off
# the map. dropna = "drop rows where this column is blank".
df = all_schools.dropna(subset=["heat_risk"])

# The OSM ID columns are called element/id (osmnx 2.x) or element_type/osmid (1.x).
if {"element", "id"} <= set(df.columns):
    type_col, id_col = "element", "id"
elif {"element_type", "osmid"} <= set(df.columns):
    type_col, id_col = "element_type", "osmid"
else:
    type_col = id_col = None  # no IDs found: popups just won't have the OSM link

# --- The base map ---------------------------------------------------------
# Folium writes a Leaflet map (a popular JavaScript map library) for us.
# The background is made of square images ("tiles") that the viewer's browser
# downloads from a tile server while they look at the map.
# We use OpenStreetMap's own tiles: free and no API key needed. (The blueprint
# used CARTO's "cartodbpositron" tiles, but CARTO now requires an API key.)
# Note: OSM's tile server refuses pages opened straight from disk (file:///),
# so preview with:  python -m http.server 8000 --directory docs
# and open http://localhost:8000. On GitHub Pages it works normally.
m = folium.Map(location=[13.75, 100.50], zoom_start=11, tiles="OpenStreetMap")

# A colour scale: 0 = blue (coolest), 50 = pale yellow, 100 = red (hottest).
# cmap(score) returns the colour for any score, e.g. cmap(87) is orange-red.
cmap = cm.LinearColormap(["#2c7bb6", "#ffffbf", "#d7191c"], vmin=0, vmax=100,
                         caption="Heat risk score (0 = coolest, 100 = hottest)")

# --- One dot per school ---------------------------------------------------
for _, r in df.iterrows():
    # School names come from OpenStreetMap, which anyone can edit. A name
    # containing characters like < or & would be read as part of the web
    # page's code. html.escape() turns them into harmless plain text.
    name = html.escape(str(r["name"]))

    popup = (f"<b>{name}</b><br>"
             f"Morning surface temp, hot season (satellite): {r['LST_C']:.1f} &deg;C<br>"
             f"Greenness (NDVI): {r['NDVI']:.2f}<br>"
             f"Heat risk: {r['heat_risk']:.0f}/100")
    if type_col:
        # Each OSM feature has a page like openstreetmap.org/way/123456.
        url = f"https://www.openstreetmap.org/{r[type_col]}/{int(r[id_col])}"
        popup += f'<br><a href="{url}" target="_blank" rel="noopener">View on OpenStreetMap</a>'

    folium.CircleMarker(
        location=[r.geometry.y, r.geometry.x],  # folium wants [latitude, longitude]
        radius=5,
        color=cmap(r["heat_risk"]),
        fill=True,
        fill_opacity=0.8,
        popup=folium.Popup(popup, max_width=300),  # shown on click
        tooltip=name,                               # shown on hover
    ).add_to(m)

cmap.add_to(m)  # the colour legend in the corner

# --- Data credits ---------------------------------------------------------
# The data licences require credit (see "Data sources and licences" in the
# blueprint). This adds a small fixed box in the bottom-left corner.
credits = """
<div style="position: fixed; bottom: 10px; left: 10px; z-index: 1000;
            background: white; padding: 4px 8px; font-size: 11px;
            border-radius: 4px; box-shadow: 0 0 4px rgba(0,0,0,0.3);">
  Schools: &copy; OpenStreetMap contributors (ODbL) &middot;
  Surface temperature: Landsat 8/9, USGS
</div>
"""
m.get_root().html.add_child(folium.Element(credits))

m.save(OUTPUT)

# --- Summary --------------------------------------------------------------
print(len(df), "schools drawn on the map")
print("  left off (no score):", len(all_schools) - len(df))
print(f"  saved to {OUTPUT} ({OUTPUT.stat().st_size / 1_000_000:.1f} MB)")
print("Preview: python -m http.server 8000 --directory docs, then open http://localhost:8000")
