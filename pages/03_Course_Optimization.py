"""
Course Optimization Page - Enhanced Version

Streamlined optimization workflow that always performs coarse → granular optimization
with clean visualization focused on detailed results.
"""

import streamlit as st
import pandas as pd
import numpy as np
import os
import sys

# Add the app directory to the Python module search path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.course import Course
from app.optimization import CourseOptimizer, create_course_segments_from_course
from app.course_management import CourseManager
from app.database import get_course_db
from app.visualizations_granular import (
    create_granular_optimization_chart,
    display_performance_metrics,
    create_segment_summary_table
)

# Initialize course manager
if 'course_manager' not in st.session_state:
    st.session_state.course_manager = CourseManager()

st.title("🚀 Course Optimization")
st.write("Enhanced optimization with always-on granular simulation for maximum accuracy")

# Course Selection Section
st.header("🏁 Course Selection")

# Check if we have a course from the segmentation page
if 'course' in st.session_state and st.session_state.course:
    current_course = st.session_state.course
    course_name = getattr(st.session_state, 'current_course_name', 'Current Course')
    
    st.success(f"✅ Course loaded: {course_name}")
    
    # Show course metrics
    if hasattr(current_course, 'df') and not current_course.df.empty:
        col1, col2, col3, col4, col5 = st.columns(5)
        
        with col1:
            total_distance = current_course.df['cumulative_distance'].iloc[-1] / 1000
            st.metric("Distance", f"{total_distance:.1f} km")
        
        with col2:
            elevation_gain = current_course.df['height_gain'].sum()
            st.metric("Elevation Gain", f"{elevation_gain:.0f} m")
        
        with col3:
            if hasattr(current_course, 'course_segments'):
                st.metric("Segments", len(current_course.course_segments))
            else:
                st.metric("Segments", "Not segmented")
        
        with col4:
            avg_gradient = current_course.df['gradient'].mean()
            st.metric("Avg Gradient", f"{avg_gradient:.1f}%")
            
        with col5:
            gps_points = len(current_course.df) if hasattr(current_course, 'df') else 0
            st.metric("GPS Points", f"{gps_points:,}")
            
else:
    # No course loaded - show course selection from database
    st.info("No course currently loaded. Please select a course:")
    
    available_courses = st.session_state.course_manager.list_available_courses()
    
    if available_courses:
        # Course selection interface
        def format_course_display(course):
            """Format course for display"""
            name = course['course_name']
            strava_id = course.get('strava_segment_id')
            
            if strava_id:
                if name.startswith('Strava Segment '):
                    display_name = f"Strava Segment - {strava_id}"
                else:
                    display_name = f"{name} - {strava_id}"
            else:
                display_name = name
            
            return display_name
        
        selected_course = st.selectbox(
            "Select a course to optimize:",
            available_courses,
            format_func=format_course_display
        )
        
        if st.button("🔄 Load Selected Course"):
            try:
                course_obj = st.session_state.course_manager.load_course_for_optimization(
                    selected_course['course_id']
                )
                
                if course_obj:
                    st.session_state.course = course_obj
                    st.session_state.current_course_id = selected_course['course_id']
                    st.session_state.current_course_name = selected_course['course_name']
                    st.success(f"✅ Loaded: {selected_course['course_name']}")
                    st.rerun()
                else:
                    st.error("Failed to load course")
            except Exception as e:
                st.error(f"Error loading course: {str(e)}")
    else:
        st.warning("No courses found in database.")
        if st.button("📁 Go to Course Import"):
            st.switch_page("pages/01_Segment_Data_and_Course_Segmentation.py")

# Optimization section - only show if we have a course
if 'course' in st.session_state and st.session_state.course:
    course = st.session_state.course
    
    # Ensure course is segmented
    if not hasattr(course, 'course_segments') or course.course_segments.empty:
        st.warning("⚠️ Course needs to be segmented first")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔧 Quick Auto-Segmentation"):
                course.auto_segmentation(max_clusters=8)
                st.success("✅ Applied auto-clustering")
                st.rerun()
        with col2:
            if st.button("📁 Go to Segmentation Page"):
                st.switch_page("pages/01_Segment_Data_and_Course_Segmentation.py")
    
    else:
        # Convert course segments to optimization format
        try:
            optimization_segments = create_course_segments_from_course(course)
            
            # Course overview metrics
            st.header("📊 Course Overview")
            col1, col2, col3, col4 = st.columns(4)
            
            total_distance = optimization_segments['distance'].sum() / 1000
            avg_gradient = optimization_segments['gradient'].mean() * 100
            max_gradient = optimization_segments['gradient'].max() * 100
            num_segments = len(optimization_segments)
            
            with col1:
                st.metric("Distance", f"{total_distance:.1f} km")
            with col2:
                st.metric("Segments", f"{num_segments}")
            with col3:
                st.metric("Avg Gradient", f"{avg_gradient:.1f}%")
            with col4:
                st.metric("Max Gradient", f"{max_gradient:.1f}%")

            # Optimization Settings
            st.header("⚙️ Optimization Settings")
            
            col1, col2 = st.columns(2)
            
            with col1:
                # Rider Profile
                st.subheader("🏋️ Rider Profile")
                critical_power = st.number_input(
                    "Critical Power (W)",
                    min_value=150,
                    max_value=500,
                    value=300,
                    step=10,
                    help="Your sustainable power output for ~1 hour"
                )
                
                w_prime = st.number_input(
                    "W' (Anaerobic Capacity)",
                    min_value=10000,
                    max_value=50000,
                    value=25000,
                    step=1000,
                    format="%d",
                    help="Your anaerobic energy reserve in Joules"
                )
                
            with col2:
                # Optimization Parameters
                st.subheader("🎯 Optimization Parameters")
                
                optimization_type = st.selectbox(
                    "Optimization Strategy",
                    ["Constant Power", "Variable Pacing"],
                    help="Constant Power: Single power target | Variable Pacing: Terrain-adaptive strategy"
                )
                
                target_w_util = st.slider(
                    "Target W' Utilization (%)",
                    min_value=50,
                    max_value=95,
                    value=85,
                    step=5,
                    help="How much anaerobic capacity to target (higher = more aggressive)"
                ) / 100

            # Initialize optimizer
            optimizer = CourseOptimizer(critical_power=critical_power, w_prime=w_prime)
            
            st.info("ℹ️ **Enhanced Mode Always Active**: Uses segment order preservation and high-resolution simulation (5000+ points)")

            # Optimization execution
            if optimization_type == "Constant Power":
                st.subheader("🔄 Constant Power Optimization")
                
                if st.button("🚀 Optimize Constant Power", type="primary"):
                    with st.spinner("Running two-stage optimization..."):
                        try:
                            # Always enable enhanced segmentation
                            if hasattr(course, 'enable_enhanced_segmentation'):
                                course.enable_enhanced_segmentation()
                            
                            # Stage 1: Coarse segment optimization (for strategy)
                            with st.spinner("🎯 Stage 1: Determining optimal power strategy..."):
                                optimal_power, coarse_time, segment_results = optimizer.optimize_constant_power(
                                    optimization_segments, 
                                    target_w_utilization=target_w_util
                                )
                                st.success(f"✅ Strategy determined: {optimal_power:.0f}W constant power")
                            
                            # Stage 2: High-resolution granular simulation (for results)
                            with st.spinner("🔬 Stage 2: Running high-resolution simulation..."):
                                granular_results, granular_time, granular_analysis = optimizer.simulate_course_detailed(
                                    course, optimization_segments, optimal_power, target_resolution=5000
                                )
                                st.success(f"✅ Detailed simulation complete: {len(granular_results):,} points analyzed")
                            
                            # Store results in session state
                            st.session_state['optimization_results'] = {
                                'type': 'constant_power',
                                'optimal_power': optimal_power,
                                'coarse_time': coarse_time,
                                'granular_time': granular_time,
                                'segment_results': segment_results,
                                'granular_results': granular_results,
                                'granular_analysis': granular_analysis,
                                'target_w_util': target_w_util,
                                'optimization_segments': optimization_segments
                            }
                            
                            st.success(f"🎉 Optimization complete! Total time: {granular_time/60:.1f} minutes")
                            
                        except Exception as e:
                            st.error(f"❌ Optimization failed: {str(e)}")
                            import traceback
                            st.error(f"Details: {traceback.format_exc()}")

            elif optimization_type == "Variable Pacing":
                st.subheader("🎯 Variable Pacing Optimization")
                
                # Additional variable pacing parameters
                aggressive_factor = st.slider(
                    "Climb Aggressiveness",
                    min_value=1.0,
                    max_value=2.0,
                    value=1.3,
                    step=0.1,
                    help="Power multiplier for climbs (1.0=CP, 2.0=very aggressive)"
                )
                
                if st.button("🚀 Optimize Variable Pacing", type="primary"):
                    with st.spinner("Running variable pacing optimization..."):
                        try:
                            # Always enable enhanced segmentation
                            if hasattr(course, 'enable_enhanced_segmentation'):
                                course.enable_enhanced_segmentation()
                            
                            # Stage 1: Variable pacing optimization (coarse)
                            with st.spinner("🎯 Stage 1: Optimizing terrain-adaptive strategy..."):
                                var_results_df, var_time, var_analysis = optimizer.optimize_variable_pacing(
                                    optimization_segments,
                                    target_w_utilization=target_w_util,
                                    aggressive_factor=aggressive_factor
                                )
                                st.success(f"✅ Variable strategy optimized: {var_time/60:.1f} min")
                            
                            # Stage 2: High-resolution simulation with variable power
                            with st.spinner("🔬 Stage 2: Running high-resolution variable simulation..."):
                                # Extract power array from variable results
                                power_array = var_results_df['target_power'].values
                                
                                granular_results, granular_time, granular_analysis = optimizer.simulate_course_detailed(
                                    course, optimization_segments, power_array, target_resolution=5000
                                )
                                st.success(f"✅ Detailed simulation complete: {len(granular_results):,} points analyzed")
                            
                            # Store results in session state
                            st.session_state['optimization_results'] = {
                                'type': 'variable_pacing',
                                'var_results_df': var_results_df,
                                'var_analysis': var_analysis,
                                'coarse_time': var_time,
                                'granular_time': granular_time,
                                'granular_results': granular_results,
                                'granular_analysis': granular_analysis,
                                'target_w_util': target_w_util,
                                'aggressive_factor': aggressive_factor,
                                'optimization_segments': optimization_segments
                            }
                            
                            st.success(f"🎉 Variable pacing complete! Total time: {granular_time/60:.1f} minutes")
                            
                        except Exception as e:
                            st.error(f"❌ Variable pacing failed: {str(e)}")
                            import traceback
                            st.error(f"Details: {traceback.format_exc()}")

            # Display Results Section
            if 'optimization_results' in st.session_state:
                results = st.session_state['optimization_results']
                
                st.header("📊 Optimization Results")
                
                # Performance metrics summary
                display_performance_metrics(results['granular_analysis'])
                
                # Main granular visualization
                st.subheader("📈 Course Analysis")
                
                course_info = {
                    'name': getattr(st.session_state, 'current_course_name', 'Course'),
                    'distance_km': total_distance,
                    'segments': num_segments
                }
                
                try:
                    chart = create_granular_optimization_chart(
                        results['granular_results'],
                        results['optimization_segments'],
                        course_info,
                        results['type']
                    )
                    st.plotly_chart(chart, width='stretch')
                except Exception as e:
                    st.error(f"Chart creation failed: {str(e)}")
                    # Fallback to data table
                    st.write("Showing raw data instead:")
                    sample_data = results['granular_results'].sample(min(100, len(results['granular_results'])))
                    st.dataframe(sample_data)
                
                # Segment summary table
                with st.expander("📋 Segment-by-Segment Analysis"):
                    segment_table = create_segment_summary_table(
                        results['optimization_segments'],
                        results['granular_analysis']
                    )
                    st.dataframe(segment_table, width='stretch')
                
                # Detailed granular data
                with st.expander("🔬 Detailed Point-by-Point Data"):
                    st.write(f"Full simulation used {len(results['granular_results']):,} points")
                    
                    # Sample for display
                    sample_size = min(200, len(results['granular_results']))
                    sample_df = results['granular_results'].sample(sample_size).sort_index()
                    
                    display_columns = [
                        'cumulative_distance', 'gradient', 'power', 'speed_kmh', 
                        'acceleration', 'time', 'w_remaining'
                    ]
                    available_columns = [col for col in display_columns if col in sample_df.columns]
                    
                    st.dataframe(sample_df[available_columns], width='stretch')
                    
                    # Download option
                    csv_data = results['granular_results'].to_csv(index=False)
                    st.download_button(
                        label="📥 Download Full Results (CSV)",
                        data=csv_data,
                        file_name=f"optimization_results_{results['type']}.csv",
                        mime="text/csv"
                    )

        except Exception as e:
            st.error(f"❌ Error preparing optimization: {str(e)}")
            st.info("Please ensure your course is properly segmented.")

else:
    st.info("👆 Please load a course from the selection above or go to the segmentation page.")

# Footer
st.write("---")
st.caption("Enhanced Course Optimization with high-resolution simulation and acceleration modeling")
