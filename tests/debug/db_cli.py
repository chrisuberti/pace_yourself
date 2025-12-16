#!/usr/bin/env python3
"""
Quick Database CLI - Simple command line database inspection
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import get_course_db
import argparse

def quick_stats():
    """Show quick database statistics"""
    db = get_course_db()
    
    # Count records
    courses = db.conn.execute("SELECT COUNT(*) FROM courses").fetchone()[0]
    segmentations = db.conn.execute("SELECT COUNT(*) FROM course_segmentations").fetchone()[0]
    optimizations = db.conn.execute("SELECT COUNT(*) FROM optimization_results").fetchone()[0]
    
    print(f"📊 Database Stats:")
    print(f"  Courses: {courses}")
    print(f"  Segmentations: {segmentations}")
    print(f"  Optimizations: {optimizations}")
    
    if courses > 0:
        # Show recent courses
        recent_courses = db.conn.execute("""
            SELECT course_name, total_distance_km, created_at 
            FROM courses 
            ORDER BY created_at DESC 
            LIMIT 3
        """).fetchall()
        
        print(f"\n📋 Recent Courses:")
        for course in recent_courses:
            name, distance, created = course
            print(f"  • {name} ({distance:.1f} km) - {created[:10]}")

def list_courses():
    """List all courses"""
    db = get_course_db()
    
    courses = db.conn.execute("""
        SELECT course_id, course_name, total_distance_km, total_elevation_gain_m, course_type
        FROM courses 
        ORDER BY created_at DESC
    """).fetchall()
    
    print(f"📋 All Courses ({len(courses)} total):")
    print(f"{'ID':10} {'Name':25} {'Distance':>10} {'Elevation':>10} {'Type':12}")
    print("-" * 75)
    
    for course in courses:
        course_id, name, distance, elevation, course_type = course
        short_id = course_id[:8]
        short_name = name[:23] if len(name) > 23 else name
        dist_str = f"{distance:.1f} km" if distance else "N/A"
        elev_str = f"{elevation}m" if elevation else "N/A"
        type_str = course_type[:10] if course_type else "N/A"
        
        print(f"{short_id:10} {short_name:25} {dist_str:>10} {elev_str:>10} {type_str:12}")

def query_db(sql):
    """Run custom SQL query"""
    db = get_course_db()
    
    try:
        cursor = db.conn.execute(sql)
        results = cursor.fetchall()
        
        if results:
            # Show column names
            columns = [desc[0] for desc in cursor.description]
            print(" | ".join(columns))
            print("-" * (len(" | ".join(columns))))
            
            # Show results
            for row in results:
                print(" | ".join(str(val) for val in row))
        else:
            print("No results")
            
    except Exception as e:
        print(f"Error: {e}")

def inspect_course(course_id):
    """Inspect specific course"""
    db = get_course_db()
    
    course = db.conn.execute("""
        SELECT * FROM courses WHERE course_id LIKE ?
    """, (f"{course_id}%",)).fetchone()
    
    if not course:
        print(f"Course not found: {course_id}")
        return
    
    # Show course details
    print(f"📋 Course: {course[1]}")  # course_name
    print(f"  ID: {course[0]}")       # course_id
    print(f"  Distance: {course[6]:.2f} km" if course[6] else "  Distance: N/A")
    print(f"  Elevation: {course[7]}m" if course[7] else "  Elevation: N/A")
    print(f"  Type: {course[8]}")     # course_type
    print(f"  Created: {course[9]}")  # created_at
    
    # Show segmentations
    segmentations = db.conn.execute("""
        SELECT segmentation_name, segmentation_type, is_default
        FROM course_segmentations 
        WHERE course_id = ?
    """, (course[0],)).fetchall()
    
    if segmentations:
        print(f"\n🧩 Segmentations ({len(segmentations)}):")
        for seg in segmentations:
            name, seg_type, is_default = seg
            default_marker = " (DEFAULT)" if is_default else ""
            print(f"  • {name} ({seg_type}){default_marker}")

def main():
    parser = argparse.ArgumentParser(description="Quick database CLI")
    parser.add_argument('command', choices=['stats', 'list', 'inspect', 'query'], 
                       help='Command to run')
    parser.add_argument('--id', help='Course ID for inspect command')
    parser.add_argument('--sql', help='SQL query for query command')
    
    args = parser.parse_args()
    
    if args.command == 'stats':
        quick_stats()
    elif args.command == 'list':
        list_courses()
    elif args.command == 'inspect':
        if not args.id:
            print("Error: --id required for inspect command")
            return
        inspect_course(args.id)
    elif args.command == 'query':
        if not args.sql:
            print("Error: --sql required for query command")
            return
        query_db(args.sql)

if __name__ == "__main__":
    main()
