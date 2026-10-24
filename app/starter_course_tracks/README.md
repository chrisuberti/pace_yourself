# Starter course track provenance

These CSV files are bundled starter inputs for unauthenticated users. They do
not contain Strava API streams.

## Real-world courses

Route geometry was generated from OpenStreetMap road data and OSM-based bicycle
routing in October 2026. OpenStreetMap data is available under the Open Data
Commons Open Database License (ODbL):
https://www.openstreetmap.org/copyright

The elevation columns are normalized profiles based on the published distance
and climbing totals in the linked public course references. Normalization
removes raster-elevation noise that otherwise creates unrealistic short ramps
and corrupts pacing optimization.

| File | Public segment reference |
|---|---|
| `box_hill_527881.csv` | https://veloviewer.com/segments/527881 |
| `hawk_hill_229781.csv` | https://veloviewer.com/segments/229781 |
| `central_park_full_loop.csv` | https://veloviewer.com/segments/1532085 |
| `prospect_park_loop.csv` | https://veloviewer.com/segments/797660 |

## Virtual courses

Zwift starter courses are generated in `app/starter_courses.py` from published
route distance, climbing, and terrain descriptions. Their map geometry is
schematic and is never displayed on a real-world basemap.
