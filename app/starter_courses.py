"""Curated real-world and virtual courses available before authentication."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


_TRACK_DIR = Path(__file__).with_name("starter_course_tracks")


@dataclass(frozen=True)
class StarterCourse:
    slug: str
    name: str
    location: str
    description: str
    distance_m: float
    elevation_gain_m: float
    segment_url: str
    research_url: str
    course_type: str
    track_filename: str | None = None
    elevation_profile: tuple[tuple[float, float], ...] = ()
    elevation_source: str = "normalized"

    @property
    def is_virtual(self) -> bool:
        return self.course_type == "virtual"


STARTER_COURSES = (
    StarterCourse(
        slug="box-hill-527881",
        name="Box Hill",
        location="Surrey, UK",
        description=(
            "The classic Zig Zag Road benchmark climb. A focused threshold "
            "effort with steadily changing grade."
        ),
        distance_m=2490.0,
        elevation_gain_m=137.0,
        segment_url="https://veloviewer.com/segments/527881",
        research_url=(
            "https://www.cyclist.co.uk/news/"
            "box-hill-crowned-stravas-most-popular-hill-climb-segment"
        ),
        course_type="real",
        track_filename="box_hill_527881.csv",
    ),
    StarterCourse(
        slug="hawk-hill-229781",
        name="Hawk Hill",
        location="Marin Headlands, California",
        description=(
            "A Bay Area benchmark climb with ramps and short easing sections "
            "that reward controlled W' use."
        ),
        distance_m=2530.0,
        elevation_gain_m=135.0,
        segment_url="https://veloviewer.com/segments/229781",
        research_url="https://epicclimbs.info/segments/229781",
        course_type="real",
        track_filename="hawk_hill_229781.csv",
    ),
    StarterCourse(
        slug="central-park-full-loop",
        name="Central Park Full Loop",
        location="New York, New York",
        description=(
            "The 86th Street-start full park loop, including Harlem Hill, the "
            "west-side rollers, and the southern return."
        ),
        distance_m=9866.14,
        elevation_gain_m=70.0,
        segment_url=(
            "https://veloviewer.com/segment/1532085/"
            "Central+Park+Full+Loop"
        ),
        research_url="https://citibikenyc.com/rides/central-park-full-loop-temp",
        course_type="real",
        track_filename="central_park_full_loop.csv",
        elevation_source="usgs_ned10m",
    ),
    StarterCourse(
        slug="prospect-park-loop",
        name="Prospect Park Loop",
        location="Brooklyn, New York",
        description=(
            "The official counterclockwise Park Drive loop, with the sustained "
            "east-side rise and long west-side recovery."
        ),
        distance_m=5395.0,
        elevation_gain_m=42.0,
        segment_url=(
            "https://www.prospectpark.org/visit-the-park/"
            "places-to-go/park-drive/"
        ),
        research_url="https://citibikenyc.com/rides/prospect-park-loop-temp",
        course_type="real",
        track_filename="prospect_park_loop.csv",
        elevation_source="usgs_ned10m",
    ),
    StarterCourse(
        slug="mt-lemmon-cookie-cabin",
        name="Mt. Lemmon to Cookie Cabin",
        location="Tucson to Summerhaven, Arizona",
        description=(
            "The Catalina Highway climb from the established Mt. Lemmon base "
            "to the Cookie Cabin in Summerhaven."
        ),
        distance_m=39_490.0,
        elevation_gain_m=1692.0,
        segment_url=(
            "https://www.openstreetmap.org/directions?"
            "engine=fossgis_valhalla_bicycle&"
            "route=32.30511%2C-110.74454%3B32.4414515%2C-110.7599221"
        ),
        research_url="https://pjammcycling.com/climb/156.Mt-Lemmon",
        course_type="real",
        track_filename="mt_lemmon_cookie_cabin.csv",
        elevation_source="usgs_ned10m",
    ),
    StarterCourse(
        slug="mercer-island-loop-ccw",
        name="Mercer Island Loop CCW",
        location="Mercer Island, Washington",
        description=(
            "The counterclockwise perimeter loop from Mercer Island Park & "
            "Ride, following North, West, and East Mercer Way."
        ),
        distance_m=21_680.0,
        elevation_gain_m=123.0,
        segment_url="https://ridewithgps.com/routes/28507876",
        research_url=(
            "https://seattlebikeroutes.wordpress.com/2023/03/20/"
            "route-guide-mercer-island-loop/"
        ),
        course_type="real",
        track_filename="mercer_island_ccw.csv",
        elevation_source="usgs_ned10m",
    ),
    StarterCourse(
        slug="alpe-d-huez-official-683473",
        name="Alpe d'Huez Official",
        location="Bourg-d'Oisans, France",
        description=(
            "The complete official ascent through all 21 hairpins to the Tour "
            "de France finish in Alpe d'Huez."
        ),
        distance_m=13_760.0,
        elevation_gain_m=1109.0,
        segment_url="https://veloviewer.com/segment/683473",
        research_url="https://pjammcycling.com/climb/118.Alpe-dHuez",
        course_type="real",
        track_filename="alpe_d_huez_official.csv",
        elevation_source="eu_dem25m",
    ),
)

_COURSES_BY_SLUG = {course.slug: course for course in STARTER_COURSES}


def get_starter_course(slug: str) -> StarterCourse:
    """Return starter-course metadata by stable slug."""
    try:
        return _COURSES_BY_SLUG[slug]
    except KeyError as error:
        raise ValueError(f"Unknown starter course: {slug}") from error


def build_starter_course_frame(slug: str, point_count: int = 1001) -> pd.DataFrame:
    """Load an open GPS track or build a schematic virtual-course frame."""
    starter = get_starter_course(slug)
    if starter.track_filename:
        track_path = _TRACK_DIR / starter.track_filename
        if not track_path.is_file():
            raise FileNotFoundError(f"Starter course track not found: {track_path}")
        return pd.read_csv(track_path, dtype=float)

    if point_count < 3:
        raise ValueError("Virtual starter courses require at least three points.")

    progress = np.linspace(0.0, 1.0, point_count)
    profile_progress, profile_elevation = zip(*starter.elevation_profile)
    elevation = np.interp(progress, profile_progress, profile_elevation)

    angle = progress * 2 * np.pi
    if starter.slug.endswith("figure-8"):
        x = np.sin(angle)
        y = 0.55 * np.sin(2 * angle)
    else:
        radius = 1.0 + 0.12 * np.sin(3 * angle)
        x = radius * np.cos(angle)
        y = 0.7 * radius * np.sin(angle)

    unscaled_distance = np.hypot(np.diff(x), np.diff(y)).sum() * 111_139.0
    scale = starter.distance_m / unscaled_distance
    return pd.DataFrame({
        "lat": y * scale,
        "lon": x * scale,
        "altitude": elevation,
    })
