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
        elevation_gain_m=133.0,
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
        elevation_gain_m=136.0,
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
            "A rolling loop with Harlem Hill, flats, and descents for repeated "
            "W' depletion and recovery."
        ),
        distance_m=9986.0,
        elevation_gain_m=88.0,
        segment_url="https://veloviewer.com/segments/1532085",
        research_url="https://citibikenyc.com/rides/central-park-full-loop-temp",
        course_type="real",
        track_filename="central_park_full_loop.csv",
    ),
    StarterCourse(
        slug="prospect-park-loop",
        name="Prospect Park Loop",
        location="Brooklyn, New York",
        description=(
            "A compact rolling circuit with a sustained rise and recovery "
            "descent, well suited to quick optimizer experiments."
        ),
        distance_m=5395.0,
        elevation_gain_m=38.0,
        segment_url="https://veloviewer.com/segments/797660",
        research_url="https://www.prospectpark.org/visit-the-park/things-to-do/biking/",
        course_type="real",
        track_filename="prospect_park_loop.csv",
    ),
    StarterCourse(
        slug="zwift-watopia-hilly-route",
        name="Zwift Watopia Hilly Route",
        location="Watopia (virtual)",
        description=(
            "The classic punchy Watopia lap with a KOM, descent, rollers, and "
            "flats for W' depletion and recovery."
        ),
        distance_m=9100.0,
        elevation_gain_m=109.0,
        segment_url="https://veloviewer.com/segments/6150551",
        research_url="https://whatsonzwift.com/world/watopia/route/hilly-route",
        course_type="virtual",
        elevation_profile=(
            (0.0, 10.0),
            (0.12, 10.0),
            (0.22, 62.0),
            (0.32, 14.0),
            (0.48, 30.0),
            (0.58, 18.0),
            (0.70, 48.0),
            (0.78, 22.0),
            (0.90, 33.0),
            (1.0, 10.0),
        ),
    ),
    StarterCourse(
        slug="zwift-watopia-figure-8",
        name="Zwift Watopia Figure 8",
        location="Watopia (virtual)",
        description=(
            "A longer rolling route with the Hilly KOM in both directions, "
            "giving the optimizer multiple hard and recovery phases."
        ),
        distance_m=29_700.0,
        elevation_gain_m=254.0,
        segment_url="https://veloviewer.com/segments/12118421",
        research_url="https://whatsonzwift.com/world/watopia/route/figure-8",
        course_type="virtual",
        elevation_profile=(
            (0.0, 20.0),
            (0.10, 60.0),
            (0.20, 30.0),
            (0.30, 78.0),
            (0.40, 25.0),
            (0.52, 105.0),
            (0.62, 35.0),
            (0.73, 91.0),
            (0.82, 30.0),
            (0.91, 60.0),
            (1.0, 20.0),
        ),
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
