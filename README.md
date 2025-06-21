# 🚴‍♂️ Pace Yourself - Cycling Performance Optimization

A comprehensive cycling performance analysis and course optimization tool that integrates Strava data, physics-based modeling, and advanced pacing strategies.

## 🆕 **Phase 1 Complete: Optimization Engine**

### New Features
- **Course Optimization Engine**: Physics-based power modeling and race simulation
- **W' Energy Dynamics**: Advanced anaerobic capacity tracking and recovery modeling  
- **Optimal Pacing Strategies**: Find the optimal constant power for any course
- **Performance Metrics**: TSS, IF, power-to-weight, and critical segment analysis
- **Interactive Streamlit Interface**: Real-time optimization with comprehensive visualizations

### Core Capabilities
- **Strava Integration**: Fetch and analyze course data from Strava segments
- **Course Segmentation**: Multiple algorithms (equal distance, auto-clustering, manual)
- **Physics Modeling**: Air resistance, rolling resistance, gradient, and wind effects
- **Rider Profiling**: Critical power, W', and aerodynamic modeling
- **Route Visualization**: Interactive maps and elevation profiles

## 🚀 **Getting Started**

### Prerequisites
- Python 3.8+
- Strava API credentials (optional, for live data)

### Installation

1. Clone the repository
   ```bash
   git clone https://github.com/your-username/pace-yourself.git
   cd pace-yourself
   ```

2. Install dependencies
   ```bash
   pip install -r requirements.txt
   ```

3. Set up environment variables (optional)
   ```bash
   # Create .env file with:
   ROUTE_PATH=data/sample_routes
   STRAVA_CLIENT_ID=your_client_id
   STRAVA_CLIENT_SECRET=your_client_secret
   ```

4. Run the application
   ```bash
   streamlit run main.py
   ```

## 📊 **Usage Examples**

### Quick Optimization
```python
from app.optimization import CourseOptimizer
from app.course import Course
import pandas as pd

# Load course data
course_data = pd.read_csv('data/sample_routes/example_route.csv')
course = Course(course_data)
course.equal_segmentation(8)

# Create optimizer
optimizer = CourseOptimizer(critical_power=300, w_prime=25000)

# Find optimal power strategy
optimal_power, time, results = optimizer.optimize_constant_power(
    create_course_segments_from_course(course)
)

print(f"Optimal power: {optimal_power:.0f}W")
print(f"Race time: {time/60:.1f} minutes")
```

### Comprehensive Analysis
```python
# Full performance analysis
analysis = optimizer.analyze_pacing_strategy(course_segments)

print(f"TSS: {analysis['performance_metrics']['tss_estimate']:.0f}")
print(f"W' Utilization: {analysis['w_prime_utilization_percent']:.1f}%")
print(f"Critical segments: {len(analysis['critical_segments'])}")
```
