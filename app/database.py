# app/database.py
"""
Course Database Management
Supports both SQLite (development) and PostgreSQL (production)
"""

import sqlite3
import json
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any
import os
from pathlib import Path

class CourseDatabase:
    """Database manager for course data storage and retrieval"""
    
    def __init__(self, db_path: Optional[str] = None):
        """Initialize database connection"""
        if db_path is None:
            # Default to project data directory
            project_root = Path(__file__).parent.parent
            data_dir = project_root / 'data'
            data_dir.mkdir(exist_ok=True)
            db_path = str(data_dir / 'course_data.db')
        
        self.db_path = str(db_path)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row  # Enable dict-like access
        self._initialize_schema()
    
    def _initialize_schema(self):
        """Create tables if they don't exist"""
        schema_sql = """
        -- Courses table (no segmentation data)
        CREATE TABLE IF NOT EXISTS courses (
            course_id TEXT PRIMARY KEY,
            course_name TEXT NOT NULL,
            strava_segment_id TEXT UNIQUE,
            created_by TEXT DEFAULT 'system',
            raw_gps_data JSON,
            processed_data JSON,
            total_distance_km REAL,
            total_elevation_gain_m INTEGER,
            gps_points_count INTEGER DEFAULT 0,
            course_type TEXT DEFAULT 'unknown',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        -- Course segmentations (user-specific or system-wide)
        CREATE TABLE IF NOT EXISTS course_segmentations (
            segmentation_id TEXT PRIMARY KEY,
            course_id TEXT REFERENCES courses(course_id) ON DELETE CASCADE,
            segmentation_name TEXT NOT NULL,
            segmentation_type TEXT,
            algorithm_params JSON,
            segment_data JSON,
            is_default BOOLEAN DEFAULT FALSE,
            created_by TEXT DEFAULT 'system',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        -- Optimization results cache
        CREATE TABLE IF NOT EXISTS optimization_results (
            optimization_id TEXT PRIMARY KEY,
            course_id TEXT REFERENCES courses(course_id) ON DELETE CASCADE,
            segmentation_id TEXT REFERENCES course_segmentations(segmentation_id) ON DELETE CASCADE,
            rider_profile JSON,
            optimization_params JSON,
            results JSON,
            execution_time_ms INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        -- Indexes for performance
        CREATE INDEX IF NOT EXISTS idx_courses_strava_id ON courses(strava_segment_id);
        CREATE INDEX IF NOT EXISTS idx_segmentations_course ON course_segmentations(course_id);
        CREATE INDEX IF NOT EXISTS idx_segmentations_default ON course_segmentations(course_id, is_default);
        CREATE INDEX IF NOT EXISTS idx_optimizations_course ON optimization_results(course_id);
        """
        
        self.conn.executescript(schema_sql)
        self.conn.commit()
        
        # Add migration for existing databases - add gps_points_count column if it doesn't exist
        try:
            self.conn.execute("ALTER TABLE courses ADD COLUMN gps_points_count INTEGER DEFAULT 0")
            self.conn.commit()
        except sqlite3.OperationalError:
            # Column already exists, ignore
            pass
    
    def _process_raw_gps_data(self, raw_gps_data: List[Dict]) -> tuple:
        """
        Process raw GPS data using the Course class.
        
        Args:
            raw_gps_data: List of dicts with lat, lon, altitude
            
        Returns:
            tuple: (processed_data_list, total_distance_km, total_elevation_gain_m)
        """
        if not raw_gps_data or not isinstance(raw_gps_data, list) or len(raw_gps_data) < 2:
            return [], 0.0, 0
        
        try:
            import pandas as pd
            from app.course import Course
            
            # Create DataFrame from raw GPS data
            df = pd.DataFrame(raw_gps_data)
            
            # Ensure required columns exist
            if not all(col in df.columns for col in ['lat', 'lon']):
                return [], 0.0, 0
            
            # Handle altitude column naming
            if 'altitude' not in df.columns and 'ele' in df.columns:
                df['altitude'] = df['ele']
            elif 'altitude' not in df.columns:
                df['altitude'] = 0  # Default if no altitude data
            
            # Process using Course class
            course = Course(df, skip_processing=False)
            
            # Extract processed data
            processed_df = course.df
            total_distance_km = processed_df['cumulative_distance'].max() / 1000
            total_elevation_gain = processed_df['height_gain'].sum()
            
            # Convert to list of dicts for JSON storage
            processed_data = processed_df.to_dict('records')
            
            return processed_data, total_distance_km, total_elevation_gain
            
        except Exception as e:
            print(f"Error processing GPS data: {e}")
            return [], 0.0, 0
    
    def store_course(self, course_data: Dict[str, Any], auto_process: bool = True) -> str:
        """
        Store course data with automatic GPS processing.
        
        Args:
            course_data: Dictionary containing course information
            auto_process: If True, automatically process raw GPS data (default: True)
            
        Returns:
            course_id: Unique identifier for the stored course
        """
        course_id = str(uuid.uuid4())
        
        # Get raw GPS data
        raw_gps_data = course_data.get('raw_gps_data', [])
        gps_points_count = len(raw_gps_data) if isinstance(raw_gps_data, list) else 0
        
        # Auto-process if requested and raw data exists but processed data doesn't
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
            total_elevation_gain_m, gps_points_count, course_type
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        
        self.conn.execute(sql, (
            course_id,
            course_data.get('name', 'Unknown Course'),
            course_data.get('strava_segment_id'),
            course_data.get('created_by', 'system'),
            json.dumps(raw_gps_data),
            json.dumps(processed_data),
            total_distance_km,
            total_elevation_gain_m,
            gps_points_count,
            course_data.get('course_type', 'unknown')
        ))
        
        self.conn.commit()
        return course_id
    
    def reprocess_course(self, course_id: str) -> bool:
        """
        Reprocess an existing course's raw GPS data.
        Useful for fixing courses that were stored without processing.
        
        Args:
            course_id: The course to reprocess
            
        Returns:
            bool: True if successful, False otherwise
        """
        course_data = self.get_course(course_id)
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
        
        # Update the course
        sql = """
        UPDATE courses 
        SET processed_data = ?, total_distance_km = ?, total_elevation_gain_m = ?, updated_at = CURRENT_TIMESTAMP
        WHERE course_id = ?
        """
        self.conn.execute(sql, (
            json.dumps(processed_data),
            total_distance_km,
            total_elevation_gain_m,
            course_id
        ))
        self.conn.commit()
        print(f"Reprocessed course {course_id}: {len(processed_data)} points, {total_distance_km:.2f}km, {total_elevation_gain_m:.0f}m gain")
        return True
    
    def reprocess_all_courses(self) -> int:
        """
        Reprocess all courses that have raw GPS data but no processed data.
        
        Returns:
            int: Number of courses reprocessed
        """
        courses = self.conn.execute(
            "SELECT course_id, course_name FROM courses"
        ).fetchall()
        
        count = 0
        for c in courses:
            course_data = self.get_course(c['course_id'])
            if course_data.get('raw_gps_data') and not course_data.get('processed_data'):
                print(f"Reprocessing: {c['course_name']}")
                if self.reprocess_course(c['course_id']):
                    count += 1
        
        return count
    
    def get_course(self, course_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve course data by ID"""
        sql = "SELECT * FROM courses WHERE course_id = ?"
        cursor = self.conn.execute(sql, (course_id,))
        row = cursor.fetchone()
        
        if row:
            course_data = dict(row)
            # Parse JSON fields
            course_data['raw_gps_data'] = json.loads(course_data['raw_gps_data'] or '[]')
            course_data['processed_data'] = json.loads(course_data['processed_data'] or '{}')
            return course_data
        
        return None
    
    def list_courses(self, created_by: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all courses, optionally filtered by creator"""
        if created_by:
            sql = "SELECT * FROM courses WHERE created_by = ? ORDER BY created_at DESC"
            cursor = self.conn.execute(sql, (created_by,))
        else:
            sql = "SELECT * FROM courses ORDER BY created_at DESC"
            cursor = self.conn.execute(sql)
        
        courses = []
        for row in cursor.fetchall():
            course_data = dict(row)
            # Don't load full GPS data for list view (performance)
            course_data['raw_gps_data'] = None
            course_data['processed_data'] = None
            courses.append(course_data)
        
        return courses
    
    def store_segmentation(self, segmentation_data: Dict[str, Any]) -> str:
        """Store course segmentation data"""
        segmentation_id = str(uuid.uuid4())
        
        sql = """
        INSERT INTO course_segmentations (
            segmentation_id, course_id, segmentation_name,
            segmentation_type, algorithm_params, segment_data,
            is_default, created_by
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        
        self.conn.execute(sql, (
            segmentation_id,
            segmentation_data['course_id'],
            segmentation_data.get('name', 'Auto Segmentation'),
            segmentation_data.get('type', 'auto_clustering'),
            json.dumps(segmentation_data.get('algorithm_params', {})),
            json.dumps(segmentation_data.get('segment_data', [])),
            segmentation_data.get('is_default', False),
            segmentation_data.get('created_by', 'system')
        ))
        
        self.conn.commit()
        return segmentation_id
    
    def get_course_segmentations(self, course_id: str) -> List[Dict[str, Any]]:
        """Get all segmentations for a course"""
        sql = """
        SELECT * FROM course_segmentations 
        WHERE course_id = ? 
        ORDER BY is_default DESC, created_at DESC
        """
        cursor = self.conn.execute(sql, (course_id,))
        
        segmentations = []
        for row in cursor.fetchall():
            seg_data = dict(row)
            seg_data['algorithm_params'] = json.loads(seg_data['algorithm_params'] or '{}')
            seg_data['segment_data'] = json.loads(seg_data['segment_data'] or '[]')
            segmentations.append(seg_data)
        
        return segmentations
    
    def get_default_segmentation(self, course_id: str) -> Optional[Dict[str, Any]]:
        """Get the default segmentation for a course"""
        sql = """
        SELECT * FROM course_segmentations 
        WHERE course_id = ? AND is_default = TRUE
        LIMIT 1
        """
        cursor = self.conn.execute(sql, (course_id,))
        row = cursor.fetchone()
        
        if row:
            seg_data = dict(row)
            seg_data['algorithm_params'] = json.loads(seg_data['algorithm_params'] or '{}')
            seg_data['segment_data'] = json.loads(seg_data['segment_data'] or '[]')
            return seg_data
        
        return None
    
    def cache_optimization_result(self, optimization_data: Dict[str, Any]) -> str:
        """Cache optimization results for future retrieval"""
        optimization_id = str(uuid.uuid4())
        
        sql = """
        INSERT INTO optimization_results (
            optimization_id, course_id, segmentation_id,
            rider_profile, optimization_params, results,
            execution_time_ms
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        
        self.conn.execute(sql, (
            optimization_id,
            optimization_data['course_id'],
            optimization_data.get('segmentation_id'),
            json.dumps(optimization_data.get('rider_profile', {})),
            json.dumps(optimization_data.get('optimization_params', {})),
            json.dumps(optimization_data.get('results', {})),
            optimization_data.get('execution_time_ms', 0)
        ))
        
        self.conn.commit()
        return optimization_id
    
    def find_cached_optimization(self, course_id: str, rider_profile: Dict, 
                               optimization_params: Dict) -> Optional[Dict[str, Any]]:
        """Find cached optimization results with similar parameters"""
        # Simple cache lookup - could be enhanced with similarity matching
        sql = """
        SELECT * FROM optimization_results 
        WHERE course_id = ? 
        ORDER BY created_at DESC 
        LIMIT 5
        """
        cursor = self.conn.execute(sql, (course_id,))
        
        # For now, return the most recent result
        # TODO: Implement parameter similarity matching
        row = cursor.fetchone()
        if row:
            result = dict(row)
            result['rider_profile'] = json.loads(result['rider_profile'])
            result['optimization_params'] = json.loads(result['optimization_params'])
            result['results'] = json.loads(result['results'])
            return result
        
        return None
    
    def delete_course(self, course_id: str) -> bool:
        """Delete course and all associated data"""
        try:
            # SQLite will handle cascade deletes
            sql = "DELETE FROM courses WHERE course_id = ?"
            self.conn.execute(sql, (course_id,))
            self.conn.commit()
            return True
        except Exception as e:
            print(f"Error deleting course {course_id}: {e}")
            return False
    
    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()

# Singleton instance for app-wide use
_db_instance = None

def get_course_db() -> CourseDatabase:
    """Get singleton database instance"""
    global _db_instance
    if _db_instance is None:
        _db_instance = CourseDatabase()
    return _db_instance
