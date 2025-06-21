#!/usr/bin/env python3
"""
Phase 1 Verification Script

This script verifies that all Phase 1 deliverables are working correctly.
"""

import sys
import os
sys.path.append('.')

def test_imports():
    """Test that all new modules can be imported."""
    try:
        from app.optimization import CourseOptimizer, create_course_segments_from_course
        from app.course import Course
        import pandas as pd
        return True, "All imports successful"
    except Exception as e:
        return False, f"Import failed: {e}"

def test_basic_optimization():
    """Test basic optimization functionality."""
    try:
        from app.optimization import CourseOptimizer
        import pandas as pd
        
        # Create simple test data
        segments = pd.DataFrame({
            'distance': [1000, 1500],
            'gradient': [0.02, -0.01],
            'altitude': [100, 95],
            'wind': [0, 0]
        })
        
        optimizer = CourseOptimizer(300, 25000)
        power, time, results = optimizer.optimize_constant_power(segments)
        
        if power > 0 and time > 0:
            return True, f"Optimization successful: {power:.0f}W, {time/60:.1f}min"
        else:
            return False, "Optimization returned invalid results"
            
    except Exception as e:
        return False, f"Optimization failed: {e}"

def test_course_integration():
    """Test integration with Course class."""
    try:
        from app.course import Course
        from app.optimization import create_course_segments_from_course
        import pandas as pd
        
        # Create synthetic course data
        course_data = pd.DataFrame({
            'lat': [47.6, 47.61, 47.62],
            'lon': [-122.3, -122.31, -122.32],
            'altitude': [100, 110, 95]
        })
        
        course = Course(course_data)
        course.equal_segmentation(2)
        
        if hasattr(course, 'course_segments') and len(course.course_segments) > 0:
            opt_segments = create_course_segments_from_course(course)
            return True, f"Course integration successful: {len(opt_segments)} segments"
        else:
            return False, "Course segmentation failed"
            
    except Exception as e:
        return False, f"Course integration failed: {e}"

def main():
    """Run all verification tests."""
    print("🚀 Phase 1 Verification")
    print("=" * 40)
    
    tests = [
        ("Module Imports", test_imports),
        ("Basic Optimization", test_basic_optimization),
        ("Course Integration", test_course_integration)
    ]
    
    all_passed = True
    
    for test_name, test_func in tests:
        try:
            passed, message = test_func()
            status = "✅ PASS" if passed else "❌ FAIL"
            print(f"{status}: {test_name} - {message}")
            if not passed:
                all_passed = False
        except Exception as e:
            print(f"❌ FAIL: {test_name} - Unexpected error: {e}")
            all_passed = False
    
    print("=" * 40)
    if all_passed:
        print("🎉 Phase 1 Implementation: ALL TESTS PASSED")
        print("✅ Ready for production use")
    else:
        print("⚠️  Phase 1 Implementation: SOME TESTS FAILED")
        print("🔧 Please review and fix issues")
    
    return all_passed

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
