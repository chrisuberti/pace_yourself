# Starter course track provenance

These CSV files are bundled starter inputs for unauthenticated users. They do
not contain Strava API streams.

## Real-world courses

Route geometry was generated from OpenStreetMap road data and OSM-based bicycle
routing in October 2026. OpenStreetMap data is available under the Open Data
Commons Open Database License (ODbL):
https://www.openstreetmap.org/copyright

| File | Route reference | Elevation source |
|---|---|---|
| `box_hill_527881.csv` | https://veloviewer.com/segments/527881 | Normalized public profile |
| `hawk_hill_229781.csv` | https://veloviewer.com/segments/229781 | Normalized public profile |
| `central_park_full_loop.csv` | https://veloviewer.com/segment/1532085/Central+Park+Full+Loop | USGS NED 10 m |
| `prospect_park_loop.csv` | https://www.prospectpark.org/visit-the-park/places-to-go/park-drive/ | USGS NED 10 m |
| `mt_lemmon_cookie_cabin.csv` | https://pjammcycling.com/climb/156.Mt-Lemmon | USGS NED 10 m |
| `mercer_island_ccw.csv` | https://ridewithgps.com/routes/28507876 | USGS NED 10 m |
| `alpe_d_huez_official.csv` | https://veloviewer.com/segment/683473 | EU-DEM 25 m |

`central_park_full_loop.csv` is the exact 86th Street-start loop represented by
segment 1532085. Its geometry is map-matched to OpenStreetMap's bicycle network,
and its smoothed terrain elevation comes from the USGS NED 10 m dataset through
OpenTopoData. Its DEM-derived gain is approximately 93 m; VeloViewer's raw
activity-derived profile reports more gain because it retains GPS elevation
noise. The app's canonical `Course` smoothing reports approximately 70 m, which
is the value shown in the starter selector and course summary.

`prospect_park_loop.csv` follows the official 3.35-mile, counterclockwise Park
Drive loop. The previous segment reference (`797660`) was unrelated to Prospect
Park and has been removed.

`mt_lemmon_cookie_cabin.csv` is explicitly the OSM bicycle route from the
established Catalina Highway climb start to the mapped Cookie Cabin in
Summerhaven. It is not labeled with one of the common Mt. Lemmon segment IDs
because the verified candidates finish elsewhere.

`alpe_d_huez_official.csv` uses the complete official segment `683473`; the
shorter `652851` reference finishes at Vieil Alpe and is not equivalent.

`mercer_island_ccw.csv` is the 13.5-mile counterclockwise perimeter loop from
Mercer Island Park & Ride. Its Ride with GPS route is used only to establish
the intended identity and direction; committed geometry is OSM map-matched and
elevation is independently sampled from USGS NED. The starter metadata uses the
canonical processed gain rather than the noisier raw DEM accumulation.

Schematic Zwift routes are intentionally excluded from the starter catalog.
