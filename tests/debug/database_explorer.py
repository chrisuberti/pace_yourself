#!/usr/bin/env python3
"""
Interactive Database Explorer
Run this script to explore and interact with your course database
"""

import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from app.database import get_course_db
from app.course_management import CourseManager
import json
import pandas as pd

class DatabaseExplorer:
    """Interactive database exploration tool"""
    
    def __init__(self):
        self.db = get_course_db()
        self.course_manager = CourseManager()
        
    def show_menu(self):
        """Display interactive menu"""
        print("\n" + "="*60)
        print("🔍 COURSE DATABASE EXPLORER")
        print("="*60)
        print("1. 📊 Show database overview")
        print("2. 📋 List all courses") 
        print("3. 🔍 Inspect specific course")
        print("4. 🧩 Show course segmentations")
        print("5. ⚡ View optimization results")
        print("6. 🔧 Run custom SQL query")
        print("7. 🗑️  Delete course")
        print("8. 📈 Database statistics")
        print("9. 🧪 Add sample data")
        print("0. 🚪 Exit")
        print("="*60)
        
    def show_overview(self):
        """Show database overview"""
        print("\n📊 DATABASE OVERVIEW")
        print("-" * 40)
        
        # Count records in each table
        tables = ['courses', 'course_segmentations', 'optimization_results']
        
        for table in tables:
            count = self.db.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            print(f"{table:25} {count:>10} records")
        
        # Show database file size
        if os.path.exists(self.db.db_path):
            size_bytes = os.path.getsize(self.db.db_path)
            size_mb = size_bytes / (1024 * 1024)
            print(f"{'Database file size':25} {size_mb:>8.2f} MB")
    
    def list_courses(self):
        """List all courses with details"""
        print("\n📋 ALL COURSES")
        print("-" * 80)
        
        courses = self.course_manager.list_available_courses()
        
        if not courses:
            print("No courses found in database.")
            return
            
        print(f"{'ID':36} {'Name':20} {'Distance':>10} {'Elevation':>10} {'Type':12} {'Created':12}")
        print("-" * 80)
        
        for course in courses:
            course_id = course['course_id'][:8] + "..."
            name = course['course_name'][:18]
            distance = f"{course['total_distance_km']:.1f} km" if course['total_distance_km'] else "N/A"
            elevation = f"{course['total_elevation_gain_m']}m" if course['total_elevation_gain_m'] else "N/A"
            course_type = course['course_type'][:10]
            created = course['created_at'][:10] if course['created_at'] else "N/A"
            
            print(f"{course_id:36} {name:20} {distance:>10} {elevation:>10} {course_type:12} {created:12}")
    
    def inspect_course(self):
        """Inspect a specific course in detail"""
        course_id = input("\n🔍 Enter course ID (or first few characters): ").strip()
        
        # Find course by partial ID match
        courses = self.course_manager.list_available_courses()
        matching_courses = [c for c in courses if c['course_id'].startswith(course_id)]
        
        if len(matching_courses) == 0:
            print("❌ No courses found matching that ID")
            return
        elif len(matching_courses) > 1:
            print("🔍 Multiple courses found:")
            for i, course in enumerate(matching_courses):
                print(f"  {i+1}. {course['course_name']} ({course['course_id'][:8]}...)")
            
            choice = input("Select course number: ").strip()
            try:
                selected_course = matching_courses[int(choice) - 1]
            except (ValueError, IndexError):
                print("❌ Invalid selection")
                return
        else:
            selected_course = matching_courses[0]
        
        # Get full course data
        full_course_id = selected_course['course_id']
        course_data = self.db.get_course(full_course_id)
        
        if not course_data:
            print("❌ Course not found")
            return
            
        print(f"\n📋 COURSE DETAILS: {course_data['course_name']}")
        print("-" * 60)
        print(f"Course ID: {full_course_id}")
        print(f"Name: {course_data['course_name']}")
        print(f"Strava ID: {course_data.get('strava_segment_id', 'N/A')}")
        print(f"Distance: {course_data['total_distance_km']:.2f} km")
        print(f"Elevation Gain: {course_data['total_elevation_gain_m']} m")
        print(f"Course Type: {course_data['course_type']}")
        print(f"Created By: {course_data['created_by']}")
        print(f"Created At: {course_data['created_at']}")
        
        # Show GPS data summary
        gps_data = course_data.get('raw_gps_data', [])
        print(f"\nGPS Data: {len(gps_data)} points")
        if gps_data:
            first_point = gps_data[0]
            last_point = gps_data[-1]
            print(f"Start: {first_point['lat']:.6f}, {first_point['lon']:.6f}")
            print(f"End: {last_point['lat']:.6f}, {last_point['lon']:.6f}")
        
        # Show processed data summary
        processed_data = course_data.get('processed_data', {})
        if processed_data:
            print(f"\nProcessed Data Available:")
            for key, value in processed_data.items():
                if isinstance(value, list):
                    print(f"  {key}: {len(value)} values")
                else:
                    print(f"  {key}: {value}")
    
    def show_segmentations(self):
        """Show course segmentations"""
        course_id = input("\n🧩 Enter course ID for segmentations: ").strip()
        
        # Find course by partial ID
        courses = self.course_manager.list_available_courses()
        matching_courses = [c for c in courses if c['course_id'].startswith(course_id)]
        
        if len(matching_courses) != 1:
            print("❌ Please provide a more specific course ID")
            return
            
        full_course_id = matching_courses[0]['course_id']
        segmentations = self.db.get_course_segmentations(full_course_id)
        
        if not segmentations:
            print("No segmentations found for this course")
            return
            
        print(f"\n🧩 SEGMENTATIONS FOR: {matching_courses[0]['course_name']}")
        print("-" * 60)
        
        for seg in segmentations:
            print(f"\nSegmentation: {seg['segmentation_name']}")
            print(f"  ID: {seg['segmentation_id']}")
            print(f"  Type: {seg['segmentation_type']}")
            print(f"  Segments: {len(seg['segment_data'])}")
            print(f"  Default: {'Yes' if seg['is_default'] else 'No'}")
            print(f"  Created: {seg['created_at']}")
            
            # Show segment details
            segments = seg['segment_data']
            if segments:
                print(f"  Segment Details:")
                print(f"    {'#':>3} {'Distance':>10} {'Gradient':>10} {'Type':12}")
                for segment in segments[:5]:  # Show first 5 segments
                    seg_num = segment.get('segment_number', '?')
                    distance = f"{segment.get('distance_km', 0):.2f} km"
                    gradient = f"{segment.get('average_gradient', 0):.1f}%"
                    seg_type = segment.get('segment_type', 'unknown')[:10]
                    print(f"    {seg_num:>3} {distance:>10} {gradient:>10} {seg_type:12}")
                
                if len(segments) > 5:
                    print(f"    ... and {len(segments) - 5} more segments")
    
    def run_custom_query(self):
        """Run custom SQL query"""
        print("\n🔧 CUSTOM SQL QUERY")
        print("Enter your SQL query (press Enter twice to execute):")
        print("Example: SELECT * FROM courses LIMIT 5;")
        print("-" * 40)
        
        query_lines = []
        while True:
            line = input()
            if line.strip() == "" and query_lines:
                break
            query_lines.append(line)
        
        query = "\n".join(query_lines).strip()
        
        if not query:
            print("No query entered")
            return
            
        try:
            cursor = self.db.conn.execute(query)
            
            if query.upper().startswith('SELECT'):
                # For SELECT queries, show results
                results = cursor.fetchall()
                
                if results:
                    # Show column names
                    columns = [description[0] for description in cursor.description]
                    print(f"\n📊 Query Results ({len(results)} rows):")
                    print("-" * 60)
                    print(" | ".join(f"{col:15}" for col in columns))
                    print("-" * 60)
                    
                    # Show first 10 rows
                    for row in results[:10]:
                        formatted_row = []
                        for value in row:
                            if isinstance(value, str) and len(value) > 15:
                                formatted_row.append(value[:12] + "...")
                            else:
                                formatted_row.append(str(value)[:15])
                        print(" | ".join(f"{val:15}" for val in formatted_row))
                    
                    if len(results) > 10:
                        print(f"... and {len(results) - 10} more rows")
                else:
                    print("No results returned")
            else:
                # For non-SELECT queries
                self.db.conn.commit()
                print(f"✅ Query executed successfully")
                
        except Exception as e:
            print(f"❌ Error executing query: {e}")
    
    def add_sample_data(self):
        """Add sample course data for testing"""
        print("\n🧪 ADDING SAMPLE DATA")
        print("-" * 30)
        
        # Sample course data
        sample_courses = [
            {
                'name': 'Test Hill Climb',
                'created_by': 'sample_data',
                'raw_gps_data': [
                    {'lat': 40.7128, 'lon': -74.0060, 'ele': 100.0},
                    {'lat': 40.7138, 'lon': -74.0070, 'ele': 150.0},
                    {'lat': 40.7148, 'lon': -74.0080, 'ele': 200.0},
                    {'lat': 40.7158, 'lon': -74.0090, 'ele': 250.0},
                ],
                'total_distance_km': 2.5,
                'total_elevation_gain_m': 150,
                'course_type': 'hill_climb'
            },
            {
                'name': 'Flat Time Trial',
                'created_by': 'sample_data',
                'raw_gps_data': [
                    {'lat': 40.8000, 'lon': -74.1000, 'ele': 50.0},
                    {'lat': 40.8010, 'lon': -74.1010, 'ele': 52.0},
                    {'lat': 40.8020, 'lon': -74.1020, 'ele': 48.0},
                    {'lat': 40.8030, 'lon': -74.1030, 'ele': 51.0},
                ],
                'total_distance_km': 10.0,
                'total_elevation_gain_m': 20,
                'course_type': 'time_trial'
            }
        ]
        
        for course_data in sample_courses:
            course_id = self.db.store_course(course_data)
            print(f"✅ Added: {course_data['name']} (ID: {course_id[:8]}...)")
        
        print("Sample data added successfully!")
    
    def delete_course(self):
        """Delete a course from database"""
        print("\n🗑️ DELETE COURSE")
        print("⚠️  This will permanently delete the course and all associated data!")
        
        course_id = input("Enter course ID to delete: ").strip()
        
        # Find course
        courses = self.course_manager.list_available_courses()
        matching_courses = [c for c in courses if c['course_id'].startswith(course_id)]
        
        if len(matching_courses) != 1:
            print("❌ Course not found or ID ambiguous")
            return
            
        course = matching_courses[0]
        print(f"\nCourse to delete: {course['course_name']}")
        
        confirm = input("Type 'DELETE' to confirm: ").strip()
        if confirm == 'DELETE':
            success = self.db.delete_course(course['course_id'])
            if success:
                print("✅ Course deleted successfully")
            else:
                print("❌ Error deleting course")
        else:
            print("❌ Deletion cancelled")
    
    def show_statistics(self):
        """Show database statistics"""
        print("\n📈 DATABASE STATISTICS")
        print("-" * 40)
        
        # Course statistics
        courses = self.course_manager.list_available_courses()
        if courses:
            distances = [c['total_distance_km'] for c in courses if c['total_distance_km']]
            elevations = [c['total_elevation_gain_m'] for c in courses if c['total_elevation_gain_m']]
            
            print(f"Total Courses: {len(courses)}")
            if distances:
                print(f"Average Distance: {sum(distances)/len(distances):.2f} km")
                print(f"Total Distance: {sum(distances):.2f} km")
            if elevations:
                print(f"Average Elevation: {sum(elevations)/len(elevations):.0f} m")
                print(f"Total Elevation: {sum(elevations):.0f} m")
        
        # Segmentation statistics
        total_segmentations = self.db.conn.execute("SELECT COUNT(*) FROM course_segmentations").fetchone()[0]
        print(f"Total Segmentations: {total_segmentations}")
        
        # Optimization statistics
        total_optimizations = self.db.conn.execute("SELECT COUNT(*) FROM optimization_results").fetchone()[0]
        print(f"Cached Optimizations: {total_optimizations}")
        
        if total_optimizations > 0:
            avg_time = self.db.conn.execute("SELECT AVG(execution_time_ms) FROM optimization_results").fetchone()[0]
            print(f"Average Optimization Time: {avg_time:.0f} ms")
    
    def run(self):
        """Main interactive loop"""
        print("🚀 Starting Course Database Explorer...")
        
        while True:
            try:
                self.show_menu()
                choice = input("\nSelect option (0-9): ").strip()
                
                if choice == '0':
                    print("👋 Goodbye!")
                    break
                elif choice == '1':
                    self.show_overview()
                elif choice == '2':
                    self.list_courses()
                elif choice == '3':
                    self.inspect_course()
                elif choice == '4':
                    self.show_segmentations()
                elif choice == '5':
                    print("⚡ Optimization results viewer - Coming soon!")
                elif choice == '6':
                    self.run_custom_query()
                elif choice == '7':
                    self.delete_course()
                elif choice == '8':
                    self.show_statistics()
                elif choice == '9':
                    self.add_sample_data()
                else:
                    print("❌ Invalid choice. Please select 0-9.")
                    
            except KeyboardInterrupt:
                print("\n\n👋 Goodbye!")
                break
            except Exception as e:
                print(f"❌ Error: {e}")
                input("Press Enter to continue...")

if __name__ == "__main__":
    explorer = DatabaseExplorer()
    explorer.run()
