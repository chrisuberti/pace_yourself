# app/database.py
"""
Course Database Management (PostgreSQL)

Non-Strava terrain and segmentations may be shared. Strava-derived courses,
their segmentations, and optimization results are private to ``owner_user_id``.

Follows the connection conventions in ``app/auth_store.py``: each operation opens
a psycopg connection with dict-row results via ``app/db.py``.
"""

import uuid
from typing import Dict, List, Optional, Any

from app.auth_store import AUTH_SCHEMA_SQL
from app.db import connect, as_jsonb


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS courses (
    course_id TEXT PRIMARY KEY,
    course_name TEXT NOT NULL,
    strava_segment_id TEXT UNIQUE,
    created_by TEXT DEFAULT 'system',
    raw_gps_data JSONB,
    processed_data JSONB,
    total_distance_km DOUBLE PRECISION,
    total_elevation_gain_m INTEGER,
    gps_points_count INTEGER DEFAULT 0,
    course_type TEXT DEFAULT 'unknown',
    owner_user_id UUID REFERENCES users(user_id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Shared, terrain-derived segmentations attached to a shared course.
CREATE TABLE IF NOT EXISTS course_segmentations (
    segmentation_id TEXT PRIMARY KEY,
    course_id TEXT REFERENCES courses(course_id) ON DELETE CASCADE,
    segmentation_name TEXT NOT NULL,
    segmentation_type TEXT,
    algorithm_params JSONB,
    segment_data JSONB,
    is_default BOOLEAN DEFAULT FALSE,
    created_by TEXT DEFAULT 'system',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Private optimization results. owner_user_id references users(user_id); the
-- relationship is enforced in queries (scoping) rather than a DDL foreign key so
-- this store initializes independently of the auth store.
CREATE TABLE IF NOT EXISTS optimization_results (
    optimization_id TEXT PRIMARY KEY,
    course_id TEXT REFERENCES courses(course_id) ON DELETE CASCADE,
    segmentation_id TEXT REFERENCES course_segmentations(segmentation_id) ON DELETE CASCADE,
    owner_user_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    rider_profile JSONB,
    optimization_params JSONB,
    results JSONB,
    execution_time_ms INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE courses ADD COLUMN IF NOT EXISTS owner_user_id UUID;
ALTER TABLE courses DROP CONSTRAINT IF EXISTS courses_strava_segment_id_key;

CREATE INDEX IF NOT EXISTS idx_courses_strava_id ON courses(strava_segment_id);
CREATE INDEX IF NOT EXISTS idx_courses_owner ON courses(owner_user_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_courses_owner_strava_id
    ON courses(owner_user_id, strava_segment_id)
    WHERE owner_user_id IS NOT NULL AND strava_segment_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_segmentations_course ON course_segmentations(course_id);
CREATE INDEX IF NOT EXISTS idx_segmentations_default ON course_segmentations(course_id, is_default);
CREATE INDEX IF NOT EXISTS idx_optimizations_course ON optimization_results(course_id);
CREATE INDEX IF NOT EXISTS idx_optimizations_owner ON optimization_results(owner_user_id, course_id);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'courses_owner_user_id_fkey'
          AND conrelid = 'courses'::regclass
    ) THEN
        ALTER TABLE courses
            ADD CONSTRAINT courses_owner_user_id_fkey
            FOREIGN KEY (owner_user_id) REFERENCES users(user_id)
            ON DELETE CASCADE NOT VALID;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'optimization_results_owner_user_id_fkey'
          AND conrelid = 'optimization_results'::regclass
    ) THEN
        ALTER TABLE optimization_results
            ADD CONSTRAINT optimization_results_owner_user_id_fkey
            FOREIGN KEY (owner_user_id) REFERENCES users(user_id)
            ON DELETE CASCADE NOT VALID;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM optimization_results WHERE owner_user_id IS NULL
    ) THEN
        ALTER TABLE optimization_results
            ALTER COLUMN owner_user_id SET NOT NULL;
    END IF;
END $$;
"""


class CourseDatabase:
    """Database manager for course data storage and retrieval (PostgreSQL)."""

    def __init__(self, database_url: Optional[str] = None):
        """Store the connection URL and ensure the schema exists."""
        self.database_url = database_url
        self.initialize_schema()

    def _connect(self):
        return connect(self.database_url)

    def initialize_schema(self):
        """Create tables and indexes if they do not exist."""
        with self._connect() as connection:
            connection.execute(AUTH_SCHEMA_SQL)
            connection.execute(SCHEMA_SQL)

    def _process_raw_gps_data(self, raw_gps_data: List[Dict]) -> tuple:
        """
        Process raw GPS data using the Course class.

        Returns:
            tuple: (processed_data_list, total_distance_km, total_elevation_gain_m)
        """
        if not raw_gps_data or not isinstance(raw_gps_data, list) or len(raw_gps_data) < 2:
            return [], 0.0, 0

        try:
            import pandas as pd
            from app.course import Course

            df = pd.DataFrame(raw_gps_data)

            if not all(col in df.columns for col in ['lat', 'lon']):
                return [], 0.0, 0

            if 'altitude' not in df.columns and 'ele' in df.columns:
                df['altitude'] = df['ele']
            elif 'altitude' not in df.columns:
                df['altitude'] = 0

            course = Course(df, skip_processing=False)

            processed_df = course.df
            total_distance_km = processed_df['cumulative_distance'].max() / 1000
            total_elevation_gain = processed_df['height_gain'].sum()

            processed_data = processed_df.to_dict('records')

            return processed_data, total_distance_km, total_elevation_gain

        except Exception as e:
            print(f"Error processing GPS data: {e}")
            return [], 0.0, 0

    def store_course(self, course_data: Dict[str, Any], auto_process: bool = True,
                     owner_user_id: Optional[str] = None) -> str:
        """
        Store course data with automatic GPS processing.

        Strava courses require an owner and are deduplicated only within that
        owner's private library. Other course types remain shared.

        Returns:
            course_id: Unique identifier for the stored (or existing) course.
        """
        strava_segment_id = course_data.get('strava_segment_id')
        course_type = course_data.get('course_type', 'unknown')
        is_strava_course = course_type == 'strava_segment'
        if is_strava_course and not owner_user_id:
            raise ValueError('Strava-derived courses require owner_user_id.')
        stored_owner_id = owner_user_id if is_strava_course else None

        if is_strava_course and strava_segment_id is not None:
            existing = self._find_course_id_by_strava_segment(
                strava_segment_id, stored_owner_id)
            if existing:
                return existing

        course_id = str(uuid.uuid4())

        raw_gps_data = course_data.get('raw_gps_data', [])
        gps_points_count = len(raw_gps_data) if isinstance(raw_gps_data, list) else 0

        processed_data = course_data.get('processed_data', [])
        total_distance_km = course_data.get('total_distance_km', 0.0)
        total_elevation_gain_m = course_data.get('total_elevation_gain_m', 0)

        if auto_process and raw_gps_data and not processed_data:
            processed_data, total_distance_km, total_elevation_gain_m = self._process_raw_gps_data(raw_gps_data)
            print(f"Auto-processed course: {len(processed_data)} points, {total_distance_km:.2f}km, {total_elevation_gain_m:.0f}m gain")

        sql = """
        INSERT INTO courses (
            course_id, course_name, strava_segment_id, created_by,
            raw_gps_data, processed_data, total_distance_km,
            total_elevation_gain_m, gps_points_count, course_type, owner_user_id
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT DO NOTHING
        RETURNING course_id
        """

        with self._connect() as connection:
            row = connection.execute(sql, (
                course_id,
                course_data.get('name', 'Unknown Course'),
                strava_segment_id,
                course_data.get('created_by', 'system'),
                as_jsonb(raw_gps_data),
                as_jsonb(processed_data),
                total_distance_km,
                int(total_elevation_gain_m or 0),
                gps_points_count,
                course_type,
                stored_owner_id,
            )).fetchone()

        if row:
            return row['course_id']

        # Concurrent insert of the same strava_segment_id won the race; reuse it.
        if is_strava_course and strava_segment_id is not None:
            existing = self._find_course_id_by_strava_segment(
                strava_segment_id, stored_owner_id)
            if existing:
                return existing
        return course_id

    def _find_course_id_by_strava_segment(
            self, strava_segment_id: str,
            owner_user_id: str) -> Optional[str]:
        with self._connect() as connection:
            row = connection.execute(
                """SELECT course_id FROM courses
                   WHERE strava_segment_id = %s AND owner_user_id = %s""",
                (strava_segment_id, owner_user_id),
            ).fetchone()
        return row['course_id'] if row else None

    def reprocess_course(
            self, course_id: str,
            user_id: Optional[str] = None) -> bool:
        """Reprocess an existing course's raw GPS data."""
        course_data = self.get_course(course_id, user_id=user_id)
        if not course_data:
            print(f"Course {course_id} not found")
            return False

        raw_gps_data = course_data.get('raw_gps_data', [])
        if not raw_gps_data:
            print(f"Course {course_id} has no raw GPS data")
            return False

        processed_data, total_distance_km, total_elevation_gain_m = self._process_raw_gps_data(raw_gps_data)

        if not processed_data:
            print(f"Failed to process GPS data for course {course_id}")
            return False

        sql = """
        UPDATE courses
        SET processed_data = %s, total_distance_km = %s,
            total_elevation_gain_m = %s, updated_at = NOW()
        WHERE course_id = %s
        """
        with self._connect() as connection:
            connection.execute(sql, (
                as_jsonb(processed_data),
                total_distance_km,
                int(total_elevation_gain_m or 0),
                course_id,
            ))
        print(f"Reprocessed course {course_id}: {len(processed_data)} points, {total_distance_km:.2f}km, {total_elevation_gain_m:.0f}m gain")
        return True

    def reprocess_all_courses(self) -> int:
        """Reprocess all courses that have raw GPS data but no processed data."""
        with self._connect() as connection:
            courses = connection.execute(
                "SELECT course_id, course_name, owner_user_id FROM courses"
            ).fetchall()

        count = 0
        for c in courses:
            course_data = self.get_course(
                c['course_id'], user_id=c['owner_user_id'])
            if course_data.get('raw_gps_data') and not course_data.get('processed_data'):
                print(f"Reprocessing: {c['course_name']}")
                if self.reprocess_course(
                        c['course_id'], user_id=c['owner_user_id']):
                    count += 1

        return count

    def get_course(self, course_id: str,
                   user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Retrieve a shared course or the current user's private Strava course."""
        with self._connect() as connection:
            row = connection.execute(
                """SELECT * FROM courses
                   WHERE course_id = %s
                     AND (
                         course_type IS DISTINCT FROM 'strava_segment'
                         OR owner_user_id = %s
                     )""",
                (course_id, user_id),
            ).fetchone()

        if row:
            course_data = dict(row)
            # JSONB columns arrive already parsed.
            course_data['raw_gps_data'] = course_data.get('raw_gps_data') or []
            course_data['processed_data'] = course_data.get('processed_data') or {}
            return course_data

        return None

    def list_courses(self, created_by: Optional[str] = None,
                     user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """List shared courses plus this user's private Strava courses."""
        conditions = [
            "(course_type IS DISTINCT FROM 'strava_segment' OR owner_user_id = %s)"
        ]
        params = [user_id]
        if created_by:
            conditions.append("created_by = %s")
            params.append(created_by)
        sql = (
            "SELECT * FROM courses WHERE " + " AND ".join(conditions)
            + " ORDER BY created_at DESC"
        )
        with self._connect() as connection:
            rows = connection.execute(sql, tuple(params)).fetchall()

        courses = []
        for row in rows:
            course_data = dict(row)
            # Don't return full GPS payloads in the list view (performance).
            course_data['raw_gps_data'] = None
            course_data['processed_data'] = None
            courses.append(course_data)

        return courses

    def store_segmentation(self, segmentation_data: Dict[str, Any],
                           user_id: Optional[str] = None) -> str:
        """Store a course segmentation, reusing an identical existing one."""
        course_id = segmentation_data['course_id']
        if not self.get_course(course_id, user_id=user_id):
            raise PermissionError('Course is unavailable to this user.')
        seg_type = segmentation_data.get('type', 'auto_clustering')
        algorithm_params = segmentation_data.get('algorithm_params', {})

        # Segmentations are shared and terrain-derived; reuse an identical one.
        existing = self._find_matching_segmentation(course_id, seg_type, algorithm_params)
        if existing:
            return existing

        segmentation_id = str(uuid.uuid4())
        sql = """
        INSERT INTO course_segmentations (
            segmentation_id, course_id, segmentation_name,
            segmentation_type, algorithm_params, segment_data,
            is_default, created_by
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """
        with self._connect() as connection:
            connection.execute(sql, (
                segmentation_id,
                course_id,
                segmentation_data.get('name', 'Auto Segmentation'),
                seg_type,
                as_jsonb(algorithm_params),
                as_jsonb(segmentation_data.get('segment_data', [])),
                bool(segmentation_data.get('is_default', False)),
                segmentation_data.get('created_by', 'system'),
            ))
        return segmentation_id

    def _find_matching_segmentation(self, course_id: str, seg_type: str,
                                    algorithm_params: Dict) -> Optional[str]:
        sql = """
        SELECT segmentation_id FROM course_segmentations
        WHERE course_id = %s AND segmentation_type = %s
          AND algorithm_params = %s
        ORDER BY is_default DESC, created_at DESC
        LIMIT 1
        """
        with self._connect() as connection:
            row = connection.execute(
                sql, (course_id, seg_type, as_jsonb(algorithm_params))
            ).fetchone()
        return row['segmentation_id'] if row else None

    def get_course_segmentations(
            self, course_id: str,
            user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all segmentations for a course."""
        sql = """
        SELECT cs.* FROM course_segmentations cs
        JOIN courses c USING (course_id)
        WHERE cs.course_id = %s
          AND (
              c.course_type IS DISTINCT FROM 'strava_segment'
              OR c.owner_user_id = %s
          )
        ORDER BY cs.is_default DESC, cs.created_at DESC
        """
        with self._connect() as connection:
            rows = connection.execute(sql, (course_id, user_id)).fetchall()

        segmentations = []
        for row in rows:
            seg_data = dict(row)
            seg_data['algorithm_params'] = seg_data.get('algorithm_params') or {}
            seg_data['segment_data'] = seg_data.get('segment_data') or []
            segmentations.append(seg_data)

        return segmentations

    def get_default_segmentation(
            self, course_id: str,
            user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Get the default segmentation for a course."""
        sql = """
        SELECT cs.* FROM course_segmentations cs
        JOIN courses c USING (course_id)
        WHERE cs.course_id = %s AND cs.is_default = TRUE
          AND (
              c.course_type IS DISTINCT FROM 'strava_segment'
              OR c.owner_user_id = %s
          )
        LIMIT 1
        """
        with self._connect() as connection:
            row = connection.execute(sql, (course_id, user_id)).fetchone()

        if row:
            seg_data = dict(row)
            seg_data['algorithm_params'] = seg_data.get('algorithm_params') or {}
            seg_data['segment_data'] = seg_data.get('segment_data') or []
            return seg_data

        return None

    def cache_optimization_result(self, optimization_data: Dict[str, Any]) -> str:
        """Persist the latest optimization result per (owner, course) for resume.

        Resume-only: keeps a single most-recent row per owner+course rather than a
        full parameter-keyed cache. Runtime speedups come from in-session
        memoization in the UI layer, not this table.
        """
        optimization_id = str(uuid.uuid4())
        course_id = optimization_data['course_id']
        owner_user_id = (
            optimization_data.get('owner_user_id')
            or optimization_data.get('user_id')
        )
        if not owner_user_id:
            raise ValueError(
                "Authenticated application user ownership is required to "
                "persist optimization results."
            )
        if not self.get_course(course_id, user_id=owner_user_id):
            raise PermissionError('Course is unavailable to this user.')

        with self._connect() as connection:
            # Latest-only: drop any prior result for this owner+course.
            connection.execute(
                "DELETE FROM optimization_results WHERE course_id = %s AND owner_user_id = %s",
                (course_id, owner_user_id),
            )
            connection.execute(
                """
                INSERT INTO optimization_results (
                    optimization_id, course_id, segmentation_id, owner_user_id,
                    rider_profile, optimization_params, results, execution_time_ms
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    optimization_id,
                    course_id,
                    optimization_data.get('segmentation_id'),
                    owner_user_id,
                    as_jsonb(optimization_data.get('rider_profile', {})),
                    as_jsonb(optimization_data.get('optimization_params', {})),
                    as_jsonb(optimization_data.get('results', {})),
                    optimization_data.get('execution_time_ms', 0),
                ),
            )
        return optimization_id

    def find_cached_optimization(self, course_id: str, rider_profile: Dict,
                                 optimization_params: Dict,
                                 user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Return the most recent stored optimization for this owner + course."""
        if not user_id:
            raise ValueError(
                "Authenticated application user ownership is required to "
                "load persisted optimization results."
            )
        sql = """
        SELECT * FROM optimization_results
        WHERE course_id = %s AND owner_user_id = %s
        ORDER BY created_at DESC LIMIT 1
        """
        params = (course_id, user_id)

        with self._connect() as connection:
            row = connection.execute(sql, params).fetchone()

        if row:
            result = dict(row)
            result['rider_profile'] = result.get('rider_profile') or {}
            result['optimization_params'] = result.get('optimization_params') or {}
            result['results'] = result.get('results') or {}
            return result

        return None

    def delete_course(self, course_id: str,
                      user_id: Optional[str] = None) -> bool:
        """Delete a shared course or the current user's private Strava course."""
        with self._connect() as connection:
            result = connection.execute(
                """DELETE FROM courses
                   WHERE course_id = %s
                     AND (
                         course_type IS DISTINCT FROM 'strava_segment'
                         OR owner_user_id = %s
                     )""",
                (course_id, user_id),
            )
        return result.rowcount == 1

    def close(self):
        """No-op: connections are opened per operation."""
        return None


# Singleton instance for app-wide use
_db_instance = None


def get_course_db() -> CourseDatabase:
    """Get singleton database instance."""
    global _db_instance
    if _db_instance is None:
        _db_instance = CourseDatabase()
    return _db_instance
