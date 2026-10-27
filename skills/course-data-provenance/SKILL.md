---
name: course-data-provenance
description: Construct or replace public starter courses with independently sourced route geometry, terrain elevation, explicit provenance, and regression tests. Use when adding a real-world demo course or correcting one to match a named public segment.
---

# Public Course Data Provenance

Use this skill for committed starter courses that must work without Strava
authentication. It is separate from authenticated, owner-private Strava imports
described in [strava-data-path](../strava-data-path/SKILL.md).

This procedure enforces the project's data policy; it is not a substitute for
reviewing the source providers' current licenses and terms.

## Core rule

A public segment page may identify the intended course, start, direction,
distance, and expected shape. Do not commit its Strava-derived GPS/elevation
stream, encoded arrays, profile image, token, or authenticated response.

Construct the committed dataset from independently licensed sources:

- **Route geometry:** OpenStreetMap roads/paths, preferably bicycle map-matched.
- **Elevation:** an open terrain DEM such as USGS NED/3DEP.
- **Metadata:** the exact public reference URL and independently derived
  distance/gain shown honestly in the app.

Authenticated Strava segment imports must instead use the current user's
`auth_user_id` and remain owner-private.

## Construction procedure

### 1. Pin the intended course identity

Record:

- Stable slug and display name.
- Exact reference URL and segment ID.
- Start coordinate and direction.
- Whether the course is open or a closed loop.
- Published distance and broad geographic bounds.

Do not assume that two routes with the same display name are interchangeable.
For a loop, start location and direction are part of the identity.

Example: Central Park Full Loop is segment `1532085`, starts near East 86th
Street at approximately `40.7815, -73.9615`, and runs the full park loop. A
route starting near Columbus Circle is not an exact replacement even if it
traces many of the same roads.

### 2. Reconstruct geometry on OpenStreetMap

Use OSM bicycle routing or map matching to obtain the committed coordinates.
The public reference can guide waypoint selection and visual validation, but
the saved coordinate sequence must come from the OSM result.

Preferred output:

```text
lat,lon,altitude
40.781508,-73.961485,31.105568
...
```

For a closed loop:

- Preserve the intended start and direction.
- Ensure the final point closes the loop without adding a long artificial leg.
- Resample by cumulative distance when a stable point density is needed.
- Compute distance geodesically from the saved coordinates; do not force it by
  scaling latitude/longitude.

### 3. Sample open terrain elevation

Sample an appropriate DEM along the OSM geometry. For US courses, prefer USGS
NED/3DEP. OpenTopoData's `ned10m` endpoint is suitable for reproducible API
sampling when its current terms and limits allow it.

Guidelines:

- Sample by route distance rather than input row index.
- Batch requests within the provider's documented limits.
- Interpolate only between DEM samples along the same route.
- Apply modest deterministic smoothing to remove raster stair steps.
- Never scale elevation to force the published climbing total.
- Keep meters internally and document DEM resolution.
- Set starter metadata from `Course(frame)`'s canonical processed distance and
  `height_gain`, not from the raw CSV accumulation, so dropdown and course-card
  metrics agree.

Raw activity elevation often contains GPS/barometric noise and can report more
climbing than a bare-earth DEM. Treat that as a provenance difference, not a
reason to distort the DEM.

### 4. Wire metadata and disclosure

Update:

- `app/starter_courses.py`
- `app/starter_course_tracks/<slug>.csv`
- `app/starter_course_tracks/README.md`
- `pages_vibe/tabs/tab_course.py` when a new source label is needed

Store an explicit `elevation_source` or equivalent provenance value. UI text
must distinguish:

- OSM geometry + open DEM elevation.
- OSM geometry + normalized demonstration elevation.
- Fully schematic virtual geometry/elevation.

Do not label normalized or schematic data as recorded GPS elevation.

### 5. Validate the exact requirement

Add a focused regression in `tests/tests/test_race_lab_workflow.py` or the
nearest course test. Check:

- Exact reference URL/segment ID.
- Expected start coordinate and direction.
- Required columns: `lat`, `lon`, `altitude`.
- No null values and a useful point count.
- Closed-loop continuity when applicable.
- Geometric distance within an explicit tolerance, normally 3%.
- Geographic bounds and plausible elevation min/max.
- Independently derived gain within a documented tolerance.
- `Course(frame)` processes successfully.
- The map uses supported Plotly map traces.

Also inspect the rendered map and elevation chart. A passing distance assertion
does not prove that the route is the intended course.

## Central Park example

The canonical example is
`app/starter_course_tracks/central_park_full_loop.csv`:

- Intended identity: VeloViewer segment `1532085`.
- Geometry: bicycle map-matched OpenStreetMap route.
- Start: East 86th Street, approximately `40.7815, -73.9615`.
- Terrain: USGS NED 10 m sampled through OpenTopoData.
- DEM elevation range: approximately 7-37 m.
- Raw DEM-derived gain: approximately 93 m.
- Canonical processed gain shown by the app: approximately 70 m.

The public activity-derived reference reports more gain because its raw profile
retains elevation noise. The app reports the independently derived DEM profile
and documents the difference.

## Never

- Never use a deployment-global Strava athlete token.
- Never call Strava without the current application user ID.
- Never commit an authenticated athlete's segment stream as a public starter.
- Never scrape and save a third-party encoded route/elevation array when its
  license does not permit redistribution.
- Never copy a profile image into the repository as course data.
- Never claim legal or policy compliance without checking current source terms.
- Never hide synthetic or normalized provenance from the user.
