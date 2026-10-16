#!/usr/bin/env python3
"""
Migrate sample route CSVs to the database as sample courses.

This script:
1. Reads CSV files from data/sample_routes/
2. Processes them through the Course class (applies smoothing)
3. Stores them in the database with course_type='sample_course'
4. Optionally removes the CSV files after migration
"""

import pandas as pd
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.course import Course
from app.database import CourseDatabase


# Sample course metadata - add descriptive names and info
SAMPLE_COURSE_METADATA = {
    '1504789_processed_course.csv': {
        'name': 'Mt. Evans Hill Climb',
        'description': 'Epic mountain climb with 4,186m of elevation gain',
        'difficulty': 'extreme'
    },
    '1555983_processed_course.csv': {
        'name': 'Flat Training Loop',
        'description': 'Relatively flat course ideal for testing pacing strategies',
        'difficulty': 'easy'
    },
}


def migrate_sample_routes(remove_csvs: bool = False, dry_run: bool = True):
    """
    Migrate sample routes from CSV to database.
    
    Args:
        remove_csvs: If True, delete CSV files after successful migration
        dry_run: If True, only show what would be done without making changes
    """
    db = CourseDatabase()
    sample_routes_dir = project_root / 'data' / 'sample_routes'
    
    if not sample_routes_dir.exists():
        print(f"Sample routes directory not found: {sample_routes_dir}")
        return
    
    csv_files = list(sample_routes_dir.glob('*.csv'))
    print(f"Found {len(csv_files)} CSV files in {sample_routes_dir}")
    
    for csv_file in csv_files:
        filename = csv_file.name
        metadata = SAMPLE_COURSE_METADATA.get(filename, {})
        course_name = metadata.get('name', filename.replace('_processed_course.csv', '').replace('_', ' ').title())
        
        print(f"\n--- Processing: {filename} ---")
        
        # Check if already in database
        existing = db.conn.execute(
            "SELECT course_id, course_name FROM courses WHERE course_name = ? AND course_type = 'sample_course'",
            (course_name,)
        ).fetchone()
        
        if existing:
            print(f"  Already exists in database: {existing['course_name']} (ID: {existing['course_id'][:8]}...)")
            continue
        
        if dry_run:
            print(f"  [DRY RUN] Would process and store as: {course_name}")
            continue
        
        # Load and process through Course class
        try:
            df = pd.read_csv(csv_file)
            print(f"  Loaded {len(df)} GPS points")
            
            course = Course(df)
            print(f"  Processed: gradient range {course.df['gradient'].min():.1f}% to {course.df['gradient'].max():.1f}%")
            
            # Auto-segment the course
            course.auto_segmentation(max_clusters=10)
            print(f"  Segmented into {len(course.course_segments)} segments")
            
            # Prepare course data for database
            course_data = {
                'name': course_name,  # database expects 'name' not 'course_name'
                'course_type': 'sample_course',
                'raw_gps_data': df.to_dict(orient='records'),
                'processed_data': course.df.to_dict(orient='records'),
                'total_distance_km': course.df['cumulative_distance'].iloc[-1] / 1000,
                'total_elevation_gain_m': course.df['height_gain'].sum(),
                'gps_points_count': len(course.df),
            }
            
            # Store in database
            course_id = db.store_course(course_data)
            print(f"  Stored in database with ID: {course_id[:8]}...")
            
            # Store default segmentation
            segmentation_data = {
                'course_id': course_id,
                'segmentation_name': 'Auto (Default)',
                'segmentation_type': 'auto_agglomerative',
                'algorithm_params': {'max_clusters': 10},
                'segment_data': course.course_segments.to_dict(orient='records'),
                'is_default': True,
            }
            seg_id = db.store_segmentation(segmentation_data)
            print(f"  Stored default segmentation with ID: {seg_id[:8]}...")
            
            if remove_csvs:
                os.remove(csv_file)
                print(f"  Removed CSV file: {filename}")
                
        except Exception as e:
            print(f"  ERROR: {e}")
            import traceback
            traceback.print_exc()
    
    # Summary
    print("\n" + "=" * 50)
    sample_courses = db.conn.execute(
        "SELECT course_name, total_distance_km, total_elevation_gain_m FROM courses WHERE course_type = 'sample_course'"
    ).fetchall()
    print(f"Sample courses in database: {len(sample_courses)}")
    for course in sample_courses:
        print(f"  - {course['course_name']}: {course['total_distance_km']:.1f}km, {course['total_elevation_gain_m']:.0f}m")


def list_database_courses():
    """Show all courses in database by type."""
    db = CourseDatabase()
    
    cursor = db.conn.execute("""
        SELECT course_type, COUNT(*) as count, 
               SUM(total_distance_km) as total_km,
               SUM(total_elevation_gain_m) as total_elev
        FROM courses 
        GROUP BY course_type
    """)
    
    print("Courses by type:")
    for row in cursor.fetchall():
        print(f"  {row['course_type']}: {row['count']} courses, {row['total_km']:.1f}km total, {row['total_elev']:.0f}m elevation")


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Migrate sample routes to database')
    parser.add_argument('--execute', action='store_true', help='Actually perform migration (default is dry-run)')
    parser.add_argument('--remove-csvs', action='store_true', help='Remove CSV files after migration')
    parser.add_argument('--list', action='store_true', help='List courses in database')
    
    args = parser.parse_args()
    
    if args.list:
        list_database_courses()
    else:
        migrate_sample_routes(
            remove_csvs=args.remove_csvs,
            dry_run=not args.execute
        )
