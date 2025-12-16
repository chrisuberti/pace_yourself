# app/course_management.py
"""
Course Management Integration
Connects database storage with existing course processing
"""

import json
import math
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Any
from .database import get_course_db
from .course import Course

# Optional import for polyline decoding
try:
    import polyline as polyline_lib
    POLYLINE_AVAILABLE = True
except ImportError:
    POLYLINE_AVAILABLE = False
    print("Warning: polyline library not available. Install with: pip install polyline")

class CourseManager:
    """High-level interface for course management"""
    
    def __init__(self):
        self.db = get_course_db()
    
    def import_strava_segment(self, strava_segment_id: str, 
                            segment_data: Dict[str, Any]) -> str:
        """
        Import a Strava segment and store as a course
        
        Args:
            strava_segment_id: Strava segment identifier
            segment_data: Raw segment data from Strava API
            
        Returns:
            course_id: Database ID for the stored course
        """
        # Convert Strava data to course format
        course_data = self._convert_strava_to_course(strava_segment_id, segment_data)
        
        # Store in database
        course_id = self.db.store_course(course_data)
        
        # Create default segmentation
        self._create_default_segmentation(course_id, course_data)
        
        return course_id
    
    def load_course_for_optimization(self, course_id: str) -> Optional[Course]:
        """
        Load course from database and convert to Course object for optimization
        
        Args:
            course_id: Database course identifier
            
        Returns:
            Course object ready for optimization, or None if not found
        """
        course_data = self.db.get_course(course_id)
        if not course_data:
            return None

        # Convert database format back to Course object
        return self._convert_db_to_course(course_data)
    
    def get_course_with_segmentation(self, course_id: str, 
                                   segmentation_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Get course data with segmentation information
        
        Args:
            course_id: Course identifier
            segmentation_id: Specific segmentation, or None for default
            
        Returns:
            Combined course and segmentation data
        """
        course_data = self.db.get_course(course_id)
        if not course_data:
            return None
        
        if segmentation_id:
            segmentations = self.db.get_course_segmentations(course_id)
            segmentation = next((s for s in segmentations if s['segmentation_id'] == segmentation_id), None)
        else:
            segmentation = self.db.get_default_segmentation(course_id)
        
        return {
            'course': course_data,
            'segmentation': segmentation,
            'segments': segmentation['segment_data'] if segmentation else []
        }
    
    def list_available_courses(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all available courses for selection"""
        return self.db.list_courses(created_by=user_id)
    
    def _convert_strava_to_course(self, strava_segment_id: str, 
                                segment_data: Dict[str, Any]) -> Dict[str, Any]:
        """Convert Strava segment data to course database format"""
        # Extract GPS points from Strava polyline
        gps_points = self._decode_polyline(segment_data.get('map', {}).get('polyline', ''))
        
        # Calculate basic course metrics
        total_distance = segment_data.get('distance', 0) / 1000  # Convert to km
        elevation_gain = segment_data.get('total_elevation_gain', 0)
        
        # Process GPS data (gradients, smoothing, etc.)
        processed_data = self._process_gps_data(gps_points)
        
        return {
            'name': segment_data.get('name', f'Strava Segment {strava_segment_id}'),
            'strava_segment_id': strava_segment_id,
            'created_by': 'strava_import',
            'raw_gps_data': gps_points,
            'processed_data': processed_data,
            'total_distance_km': total_distance,
            'total_elevation_gain_m': elevation_gain,
            'course_type': self._determine_course_type(segment_data)
        }
    
    def _convert_db_to_course(self, course_data: Dict[str, Any]) -> Course:
        """Convert database course data to Course object"""
        # Create DataFrame from GPS data in the format Course expects
        gps_data = course_data['raw_gps_data']
        
        df = pd.DataFrame({
            'lat': [p['lat'] for p in gps_data],
            'lon': [p['lon'] for p in gps_data], 
            'altitude': [p['ele'] for p in gps_data]
        })
        
        # Create Course object - it will process the data automatically
        course = Course(df)
        
        # Ensure the course is fully processed
        required_columns = ['cumulative_distance', 'gradient', 'distance', 'bearing', 'height_gain']
        missing_columns = [col for col in required_columns if col not in course.df.columns]
        
        if missing_columns:
            # Force reprocessing
            try:
                course.process_segment()
                if 'bearing' not in course.df.columns:
                    course.calculate_bearing()
            except Exception as e:
                print(f"Warning: Error processing course data: {e}")
        
        return course
    
    def _create_default_segmentation(self, course_id: str, course_data: Dict[str, Any]):
        """Create default auto-clustering segmentation for a course"""
        # Convert to Course object for segmentation
        course = self._convert_db_to_course({'raw_gps_data': course_data['raw_gps_data'],
                                           'processed_data': course_data['processed_data']})
        
        # Use existing clustering algorithm
        try:
            from .optimization import create_course_segments_from_course
            segments_df = create_course_segments_from_course(course)
            
            # Convert DataFrame to database format
            segment_data = []
            total_segments = len(segments_df)
            for i in range(total_segments):
                row = segments_df.iloc[i]
                segment_data.append({
                    'segment_number': i + 1,
                    'start_distance_km': i * (course_data['total_distance_km'] / total_segments),
                    'end_distance_km': (i + 1) * (course_data['total_distance_km'] / total_segments),
                    'distance_km': row['distance'] / 1000,  # Convert back to km
                    'average_gradient': row['gradient'] * 100,  # Convert to percentage
                    'elevation_gain_m': max(0, row['gradient'] * row['distance']),  # Estimate
                    'segment_type': 'climbing' if row['gradient'] > 0.02 else 'flat' if row['gradient'] > -0.02 else 'descent',
                    'start_idx': 0,  # Would need more complex calculation
                    'end_idx': 0
                })
            
            # Store segmentation
            segmentation_data = {
                'course_id': course_id,
                'name': 'Auto Clustering',
                'type': 'auto_clustering',
                'algorithm_params': {
                    'gradient_weight': 1.0,
                    'bearing_weight': 1.0,
                    'smoothing_window': 5
                },
                'segment_data': segment_data,
                'is_default': True,
                'created_by': 'system'
            }
            
            self.db.store_segmentation(segmentation_data)
            
        except Exception as e:
            print(f"Warning: Could not create default segmentation: {e}")
            # Create simple single-segment fallback
            fallback_segmentation = {
                'course_id': course_id,
                'name': 'Single Segment',
                'type': 'single_segment',
                'algorithm_params': {},
                'segment_data': [{
                    'segment_number': 1,
                    'start_distance_km': 0.0,
                    'end_distance_km': course_data['total_distance_km'],
                    'distance_km': course_data['total_distance_km'],
                    'average_gradient': 0.0,
                    'elevation_gain_m': course_data['total_elevation_gain_m'],
                    'segment_type': 'mixed'
                }],
                'is_default': True,
                'created_by': 'system'
            }
            self.db.store_segmentation(fallback_segmentation)
    
    def _decode_polyline(self, polyline_str: str) -> List[Dict[str, float]]:
        """Decode Strava polyline to GPS points"""
        if not POLYLINE_AVAILABLE:
            print("Warning: polyline library not available. Install with: pip install polyline")
            return []
        
        try:
            coords = polyline_lib.decode(polyline_str)
            return [{'lat': lat, 'lon': lon, 'ele': 0.0} for lat, lon in coords]
        except Exception as e:
            print(f"Error decoding polyline: {e}")
            return []
    
    def _process_gps_data(self, gps_points: List[Dict[str, float]]) -> Dict[str, Any]:
        """Process GPS data to calculate distances, gradients, bearings"""
        if not gps_points:
            return {}
        
        # Basic distance calculation
        distances = [0.0]
        gradients = [0.0]
        bearings = [0.0]
        
        for i in range(1, len(gps_points)):
            # Simplified distance calculation
            # In production, use proper geospatial distance functions
            lat_diff = gps_points[i]['lat'] - gps_points[i-1]['lat']
            lon_diff = gps_points[i]['lon'] - gps_points[i-1]['lon']
            distance = ((lat_diff**2 + lon_diff**2)**0.5) * 111.32  # Rough km conversion
            distances.append(distances[-1] + distance)
            
            # Basic gradient calculation
            ele_diff = gps_points[i]['ele'] - gps_points[i-1]['ele']
            gradient = (ele_diff / (distance * 1000)) * 100 if distance > 0 else 0
            gradients.append(gradient)
            
            # Basic bearing calculation
            bearing = math.atan2(lon_diff, lat_diff) * 180 / math.pi
            bearings.append(bearing)
        
        return {
            'distances': distances,
            'gradients': gradients,
            'bearings': bearings,
            'total_points': len(gps_points)
        }
    
    def _determine_course_type(self, segment_data: Dict[str, Any]) -> str:
        """Determine course type from Strava segment data"""
        # Simple heuristics based on segment characteristics
        distance_km = segment_data.get('distance', 0) / 1000
        elevation_gain = segment_data.get('total_elevation_gain', 0)
        
        if distance_km < 5 and elevation_gain < 50:
            return 'time_trial'
        elif elevation_gain > distance_km * 50:  # Significant climbing
            return 'hill_climb'
        elif distance_km > 50:
            return 'road_race'
        else:
            return 'training'


# Usage example for integration with existing Streamlit pages
def integrate_with_streamlit():
    """Example of how to integrate with existing Streamlit interface"""
    import streamlit as st
    
    # Initialize course manager
    course_manager = CourseManager()
    
    # Add to course selection page
    st.subheader("Stored Courses")
    available_courses = course_manager.list_available_courses()
    
    if available_courses:
        course_options = {f"{c['course_name']} ({c['total_distance_km']:.1f} km)": c['course_id'] 
                         for c in available_courses}
        
        selected_course_name = st.selectbox("Select Course", list(course_options.keys()))
        selected_course_id = course_options[selected_course_name]
        
        # Load course for optimization
        course_obj = course_manager.load_course_for_optimization(selected_course_id)
        if course_obj:
            # Now can use with existing optimization functions
            st.session_state['current_course'] = course_obj
            st.session_state['current_course_id'] = selected_course_id
    
    # Add import functionality
    st.subheader("Import New Course")
    strava_segment_id = st.text_input("Strava Segment ID")
    if st.button("Import from Strava") and strava_segment_id:
        # This would integrate with your existing Strava API calls
        # segment_data = fetch_strava_segment(strava_segment_id)
        # course_id = course_manager.import_strava_segment(strava_segment_id, segment_data)
        st.success(f"Course imported successfully!")
