# tests/test_course_database.py
"""Course database tests (PostgreSQL).

These run only when a database is configured. Set ``PACE_TEST_DATABASE_URL``
(preferred) or ``DATABASE_URL`` to a disposable PostgreSQL database. Each test
cleans up the rows it creates.
"""

import os
import sys
import uuid

import pytest
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

from app.database import CourseDatabase  # noqa: E402

DB_URL = os.getenv("PACE_TEST_DATABASE_URL") or os.getenv("DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DB_URL, reason="Set PACE_TEST_DATABASE_URL or DATABASE_URL to run DB tests."
)


@pytest.fixture()
def db():
    return CourseDatabase(DB_URL)


@pytest.fixture()
def sample_course():
    return {
        "name": "Test Course",
        "strava_segment_id": f"test-{uuid.uuid4()}",
        "created_by": "test_user",
        "raw_gps_data": [
            {"lat": 40.7128, "lon": -74.0060, "ele": 10.0},
            {"lat": 40.7129, "lon": -74.0061, "ele": 12.0},
            {"lat": 40.7130, "lon": -74.0062, "ele": 15.0},
        ],
        "processed_data": {"distances": [0.0, 15.0, 30.0], "gradients": [0.0, 2.5, 3.0]},
        "total_distance_km": 0.030,
        "total_elevation_gain_m": 5,
        "course_type": "test",
    }


def test_store_and_retrieve_course(db, sample_course):
    course_id = db.store_course(sample_course, auto_process=False)
    try:
        retrieved = db.get_course(course_id)
        assert retrieved is not None
        assert retrieved["course_name"] == "Test Course"
        assert db.list_courses("test_user")
    finally:
        db.delete_course(course_id)


def test_segmentation_roundtrip(db, sample_course):
    course_id = db.store_course(sample_course, auto_process=False)
    try:
        seg_id = db.store_segmentation({
            "course_id": course_id,
            "name": "Test Segmentation",
            "type": "manual",
            "algorithm_params": {"segments": 2},
            "segment_data": [{"segment_number": 1}, {"segment_number": 2}],
            "is_default": True,
            "created_by": "test_user",
        })
        assert seg_id
        segs = db.get_course_segmentations(course_id)
        assert len(segs) == 1
        assert len(segs[0]["segment_data"]) == 2
        default = db.get_default_segmentation(course_id)
        assert default is not None and default["segmentation_id"] == seg_id
    finally:
        db.delete_course(course_id)


def test_optimization_is_scoped_by_owner(db, sample_course):
    """A user must not see another user's cached optimization."""
    course_id = db.store_course(sample_course, auto_process=False)
    user_a = str(uuid.uuid4())
    user_b = str(uuid.uuid4())
    try:
        db.cache_optimization_result({
            "course_id": course_id,
            "owner_user_id": user_a,
            "rider_profile": {"cp": 300},
            "optimization_params": {"target_w_utilization": 0.85},
            "results": {"total_time": 300},
            "execution_time_ms": 150,
        })
        # Owner A sees their result; owner B sees nothing for this course.
        assert db.find_cached_optimization(course_id, {}, {}, user_id=user_a) is not None
        assert db.find_cached_optimization(course_id, {}, {}, user_id=user_b) is None
    finally:
        db.delete_course(course_id)


def test_course_dedup_on_strava_segment(db, sample_course):
    """Storing the same Strava segment twice reuses the cached course."""
    first = db.store_course(sample_course, auto_process=False)
    try:
        second = db.store_course(sample_course, auto_process=False)
        assert first == second
    finally:
        db.delete_course(first)
