# Course Optimization Module Documentation

## Overview

The `app/optimization.py` module provides physics-based course optimization and pacing strategy analysis for cycling performance. This module was integrated from `notebooks/StartCourseEstimation.ipynb` as part of Phase 1 consolidation.

## Key Features

### 1. CourseOptimizer Class

The main class that handles all optimization calculations:

```python
from app.optimization import CourseOptimizer

# Initialize with rider parameters
optimizer = CourseOptimizer(critical_power=300, w_prime=25000)
```

#### Key Methods:

- `simulate_course_time(power, course_segments)` - Simulate performance at constant power
- `optimize_constant_power(course_segments)` - Find optimal power for minimum time
- `analyze_pacing_strategy(course_segments)` - Comprehensive analysis with metrics

### 2. Course Integration

Convert Course objects to optimization format:

```python
from app.optimization import create_course_segments_from_course
from app.course import Course

# Create and segment course
course = Course(gps_data)
course.equal_segmentation(8)

# Convert for optimization
opt_segments = create_course_segments_from_course(course)
```

## W' (Anaerobic Capacity) Modeling

The optimization engine includes sophisticated W' modeling:

- **Depletion**: When power > Critical Power, W' depletes at rate of (Power - CP) × time
- **Recovery**: When power < Critical Power, W' recovers at rate of (CP - Power) × time  
- **Failure State**: If W' reaches zero, the rider "blows up" and time becomes infinite

## Physics Integration

Leverages the existing `cycling_physics.py` module:

- Air resistance calculations with altitude/temperature corrections
- Rolling resistance modeling
- Gradient effects on power requirements
- Wind impact (headwind/tailwind)

## Usage Examples

### Basic Simulation

```python
import pandas as pd
from app.optimization import CourseOptimizer

# Define course segments
segments = pd.DataFrame({
    'distance': [1000, 1500, 800],  # meters
    'gradient': [0.02, 0.06, -0.03],  # decimal (2%, 6%, -3%)
    'altitude': [100, 120, 115],  # meters
    'wind': [0, 0, 2]  # m/s (positive = tailwind)
})

# Create optimizer
optimizer = CourseOptimizer(critical_power=300, w_prime=25000)

# Simulate at 350W
results, time, w_remaining, energy = optimizer.simulate_course_time(350, segments)
print(f"Time: {time/60:.1f} min, W' remaining: {w_remaining/1000:.1f} kJ")
```

### Power Optimization

```python
# Find optimal constant power
optimal_power, optimal_time, detailed_results = optimizer.optimize_constant_power(segments)
print(f"Optimal: {optimal_power:.0f}W in {optimal_time/60:.1f} minutes")
```

### Comprehensive Analysis

```python
# Full analysis with performance metrics
analysis = optimizer.analyze_pacing_strategy(segments)

print(f"TSS: {analysis['performance_metrics']['tss_estimate']:.0f}")
print(f"IF: {analysis['performance_metrics']['intensity_factor']:.2f}")
print(f"W' Utilization: {analysis['w_prime_utilization_percent']:.1f}%")
```

## Data Requirements

Course segments must include:

| Column | Description | Units | Required |
|--------|-------------|--------|----------|
| distance | Segment length | meters | Yes |
| gradient | Segment gradient | decimal (0.05 = 5%) | Yes |
| altitude | Segment altitude | meters | No* |
| wind | Wind speed | m/s (+ = tailwind) | No* |

*Optional fields default to 0 if not provided

## Performance Metrics

The optimization engine calculates standard cycling performance metrics:

- **TSS (Training Stress Score)**: Quantifies training load
- **IF (Intensity Factor)**: Ratio of normalized power to FTP/CP
- **Power-to-Weight**: Absolute power divided by rider mass
- **W' Utilization**: Percentage of anaerobic capacity used

## Error Handling

The module includes robust error handling:

- Physics calculation failures fall back to simple speed estimates
- Optimization failures default to Critical Power
- Invalid inputs are caught and reported

## Integration with Streamlit

The optimization module integrates seamlessly with the Streamlit interface via:

- `pages/03_Course_Optimization.py` - Interactive optimization interface
- Automatic course data conversion from existing Course objects
- Real-time visualization of optimization results

## Future Enhancements

Planned improvements include:

- Variable power optimization (non-constant strategies)
- Environmental factor integration (temperature, humidity)
- Equipment optimization (gear selection, aerodynamics)
- Multi-rider drafting effects
- Real-time power target generation

## Technical Notes

### Scipy Warnings

You may see warnings like "RuntimeWarning: invalid value encountered in subtract" during optimization. These are expected when the optimizer tests power values that cause W' depletion. The warnings don't affect functionality.

### Performance

- Typical optimization completes in < 1 second for courses with < 20 segments
- Memory usage scales linearly with segment count
- Physics calculations are the primary computational bottleneck

### Accuracy

The optimization results are only as accurate as:
1. The course segmentation quality
2. The rider's actual Critical Power and W' values  
3. The environmental assumptions (no wind, standard conditions)

For race preparation, validate optimization results against:
- Power meter data from similar courses
- Heart rate and perceived exertion during training
- Historical performance on comparable terrain
