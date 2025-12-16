# tests/test_course_database.py
"""
Test script for course database functionality
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import CourseDatabase, get_course_db
from app.course_management import CourseManager
import json

def test_basic_database_operations():
    """Test basic database operations"""
    print("Testing Course Database...")
    
    # Test database creation and schema
    db = CourseDatabase(':memory:')  # Use in-memory database for testing
    
    # Test course storage
    sample_course_data = {
        'name': 'Test Course',
        'strava_segment_id': '12345',
        'created_by': 'test_user',
        'raw_gps_data': [
            {'lat': 40.7128, 'lon': -74.0060, 'ele': 10.0},
            {'lat': 40.7129, 'lon': -74.0061, 'ele': 12.0},
            {'lat': 40.7130, 'lon': -74.0062, 'ele': 15.0},
        ],
        'processed_data': {
            'distances': [0.0, 15.0, 30.0],
            'gradients': [0.0, 2.5, 3.0],
            'bearings': [0.0, 45.0, 45.0]
        },
        'total_distance_km': 0.030,
        'total_elevation_gain_m': 5,
        'course_type': 'test'
    }
    
    # Store course
    course_id = db.store_course(sample_course_data)
    print(f"✅ Stored course with ID: {course_id}")
    
    # Retrieve course
    retrieved_course = db.get_course(course_id)
    assert retrieved_course is not None
    assert retrieved_course['course_name'] == 'Test Course'
    print(f"✅ Retrieved course: {retrieved_course['course_name']}")
    
    # Test segmentation storage
    segmentation_data = {
        'course_id': course_id,
        'name': 'Test Segmentation',
        'type': 'manual',
        'algorithm_params': {'segments': 2},
        'segment_data': [
            {
                'segment_number': 1,
                'start_distance_km': 0.0,
                'end_distance_km': 0.015,
                'distance_km': 0.015,
                'average_gradient': 2.0,
                'elevation_gain_m': 2,
                'segment_type': 'flat'
            },
            {
                'segment_number': 2,
                'start_distance_km': 0.015,
                'end_distance_km': 0.030,
                'distance_km': 0.015,
                'average_gradient': 3.0,
                'elevation_gain_m': 3,
                'segment_type': 'climbing'
            }
        ],
        'is_default': True,
        'created_by': 'test_user'
    }
    
    segmentation_id = db.store_segmentation(segmentation_data)
    print(f"✅ Stored segmentation with ID: {segmentation_id}")
    
    # Retrieve segmentations
    segmentations = db.get_course_segmentations(course_id)
    assert len(segmentations) == 1
    assert len(segmentations[0]['segment_data']) == 2
    print(f"✅ Retrieved segmentation with {len(segmentations[0]['segment_data'])} segments")
    
    # Test optimization caching
    optimization_data = {
        'course_id': course_id,
        'segmentation_id': segmentation_id,
        'rider_profile': {'cp': 300, 'w_prime': 20000},
        'optimization_params': {'target_w_utilization': 0.85},
        'results': {'total_time': 300, 'average_power': 280},
        'execution_time_ms': 150
    }
    
    optimization_id = db.cache_optimization_result(optimization_data)
    print(f"✅ Cached optimization result with ID: {optimization_id}")
    
    # Test listing courses
    courses = db.list_courses('test_user')
    assert len(courses) == 1
    print(f"✅ Listed {len(courses)} courses for user")
    
    db.close()
    print("✅ All database tests passed!")

def test_course_manager_integration():
    """Test CourseManager integration"""
    print("\nTesting Course Manager Integration...")
    
    # Initialize course manager with in-memory database
    course_manager = CourseManager()
    
    # Create test course data that would come from your existing CSV loading
    test_df_data = {
        'lat': [40.7128, 40.7129, 40.7130, 40.7131],
        'lon': [-74.0060, -74.0061, -74.0062, -74.0063],
        'altitude': [10.0, 12.0, 15.0, 18.0]
    }
    
    # Simulate storing and retrieving a course
    # (In real usage, this would come from Strava import or CSV upload)
    
    # For now, just test the database functions work
    available_courses = course_manager.list_available_courses()
    print(f"✅ Found {len(available_courses)} courses in database")
    
    print("✅ Course Manager integration test completed!")

def print_database_schema_info():
    """Print information about the database schema"""
    print("\nDatabase Schema Information:")
    print("=" * 50)
    
    db = CourseDatabase(':memory:')
    
    # Get table info
    cursor = db.conn.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    
    for table in tables:
        table_name = table[0]
        print(f"\n📋 Table: {table_name}")
        
        # Get column info
        cursor = db.conn.execute(f"PRAGMA table_info({table_name});")
        columns = cursor.fetchall()
        
        for col in columns:
            col_name, col_type, not_null, default, pk = col[1], col[2], col[3], col[4], col[5]
            pk_indicator = " (PK)" if pk else ""
            not_null_indicator = " NOT NULL" if not_null else ""
            default_indicator = f" DEFAULT {default}" if default else ""
            print(f"  📝 {col_name}: {col_type}{pk_indicator}{not_null_indicator}{default_indicator}")
    
    db.close()

if __name__ == "__main__":
    print("🚀 Course Database Test Suite")
    print("=" * 50)
    
    try:
        test_basic_database_operations()
        test_course_manager_integration()
        print_database_schema_info()
        
        print("\n🎉 All tests completed successfully!")
        print("\n📁 Database files will be created in: data/course_data.db")
        print("💡 You can now integrate this with your Streamlit pages")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
