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
from app.db import connect  # noqa: E402
from app.rider import initialize_rider_database  # noqa: E402

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
        with connect(DB_URL) as connection:
            for user_id, athlete_id, name in (
                (user_a, 900000001, "Owner A"),
                (user_b, 900000002, "Owner B"),
            ):
                connection.execute(
                    """INSERT INTO users (
                           user_id, strava_athlete_id, display_name
                       ) VALUES (%s, %s, %s)""",
                    (user_id, athlete_id, name),
                )
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
        with connect(DB_URL) as connection:
            connection.execute(
                "DELETE FROM users WHERE user_id = ANY(%s)",
                ([user_a, user_b],),
            )


def test_ownerless_optimization_persistence_is_rejected(db, sample_course):
    course_id = db.store_course(sample_course, auto_process=False)
    try:
        with pytest.raises(ValueError, match="ownership is required"):
            db.cache_optimization_result({
                "course_id": course_id,
                "results": {"total_time": 300},
            })
        with pytest.raises(ValueError, match="ownership is required"):
            db.find_cached_optimization(course_id, {}, {})
    finally:
        db.delete_course(course_id)


def test_private_owner_columns_are_not_nullable(db):
    initialize_rider_database()
    with connect(DB_URL) as connection:
        rows = connection.execute(
            """SELECT table_name, is_nullable
               FROM information_schema.columns
               WHERE table_schema = current_schema()
                 AND column_name = 'owner_user_id'
                 AND table_name IN ('rider_info', 'optimization_results')"""
        ).fetchall()

    assert {row['table_name']: row['is_nullable'] for row in rows} == {
        'optimization_results': 'NO',
        'rider_info': 'NO',
    }


def test_course_dedup_on_strava_segment(db, sample_course):
    """Strava segments dedupe per owner and remain private between owners."""
    user_a = str(uuid.uuid4())
    user_b = str(uuid.uuid4())
    sample_course["course_type"] = "strava_segment"
    try:
        with connect(DB_URL) as connection:
            connection.execute(
                """INSERT INTO users (
                       user_id, strava_athlete_id, display_name
                   ) VALUES (%s, %s, %s), (%s, %s, %s)""",
                (user_a, 910000001, "Course Owner A",
                 user_b, 910000002, "Course Owner B"),
            )
        first = db.store_course(
            sample_course, auto_process=False, owner_user_id=user_a)
        duplicate = db.store_course(
            sample_course, auto_process=False, owner_user_id=user_a)
        second_owner = db.store_course(
            sample_course, auto_process=False, owner_user_id=user_b)

        assert first == duplicate
        assert first != second_owner
        assert db.get_course(first, user_id=user_a) is not None
        assert db.get_course(first, user_id=user_b) is None
        assert db.get_course(first) is None
        assert first in {
            course["course_id"] for course in db.list_courses(user_id=user_a)
        }
        assert first not in {
            course["course_id"] for course in db.list_courses(user_id=user_b)
        }
    finally:
        with connect(DB_URL) as connection:
            connection.execute(
                "DELETE FROM users WHERE user_id = ANY(%s)",
                ([user_a, user_b],),
            )


def test_strava_course_requires_owner(db, sample_course):
    sample_course["course_type"] = "strava_segment"
    with pytest.raises(ValueError, match="require owner_user_id"):
        db.store_course(sample_course, auto_process=False)


def test_legacy_ownerless_strava_course_is_hidden(db, sample_course):
    sample_course["course_type"] = "test"
    course_id = db.store_course(sample_course, auto_process=False)
    try:
        with connect(DB_URL) as connection:
            connection.execute(
                """UPDATE courses SET course_type = 'strava_segment',
                   owner_user_id = NULL WHERE course_id = %s""",
                (course_id,),
            )
        assert db.get_course(course_id) is None
        assert course_id not in {
            course["course_id"] for course in db.list_courses()
        }
    finally:
        with connect(DB_URL) as connection:
            connection.execute(
                "DELETE FROM courses WHERE course_id = %s", (course_id,))
