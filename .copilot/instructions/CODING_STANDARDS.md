# Coding Standards for Pace Yourself Project

## 🎯 **Core Rules**

### **Azure Integration**
- Use Azure Tools when handling requests related to Azure
- Use Azure Code Gen Best Practices for Azure Functions development
- Use Azure Deployment Best Practices when deploying to Azure

### **Cycling Physics Standards**
- **Unit Consistency**: Always use meters internally for calculations, display in mph
- **Gradient Validation**: Ensure gradients are in decimal format (0.0-0.3 range for 0-30%)
- **W' Energy Modeling**: Target specific W' utilization levels (default 85% depletion)
- **Power Optimization**: Use finite penalty values, never return `float('inf')`

### **Data Processing Patterns**
- Use `CourseOptimizer` for physics simulations and pacing strategy
- Implement `simulate_course_time()` for segment-based optimization
- Always validate numerical stability with `np.isfinite()` checks
- Use conservative optimization bounds for scipy.optimize

### **Visualization Standards**
- Use step functions for segment-based power display (not line charts)
- Maintain distance unit consistency (meters internal, km display)
- Implement dark theme compatibility throughout
- Use existing color mapping patterns from `plot_cumulative_distance_vs_altitude`

### **Streamlit Development**
- Add debug panels with `st.expander()` for variable inspection
- Use session state for persistent optimization results
- Implement spinner feedback for long-running operations
- Provide clear error messages and fallback strategies

## 🔧 **Code Patterns**

### **Optimization Functions**
```python
def optimize_function(self, target_utilization=0.85):
    def objective(power):
        # Never return float('inf') - use finite penalties
        if invalid_condition:
            return 1e6 + (power - self.critical_power) ** 2
        
        # Always validate finite results
        if not np.isfinite(result):
            return 1e6
            
        return result + penalty
```

### **Unit Handling**
```python
# Always standardize to meters internally
if max_distance < 100:  # Likely in km
    distance_m = distance_km * 1000
else:  # Already in meters
    distance_m = distance
```

### **Error Handling**
```python
try:
    result = complex_calculation()
    if not np.isfinite(result):
        return fallback_value
    return result
except Exception as e:
    print(f"Warning: {operation} failed: {e}")
    return safe_fallback
```

## 📊 **Architecture Principles**

### **Data Flow**
1. **Course Data** → Segmentation → Optimization → Fine-grained Prediction
2. **Segment-based** optimization for strategy planning
3. **Point-by-point** physics for detailed visualization
4. **Acceleration modeling** for realistic transitions

### **Module Responsibilities**
- **`app/course.py`**: Course segmentation and data processing
- **`app/optimization.py`**: Physics-based optimization algorithms
- **`app/visualizations.py`**: Plotting functions with unit consistency
- **`app/rider.py`**: Integrate metrics regarding rider and riding style to calculate drag and weight options
- **`pages/03_Course_Optimization.py`**: User interface and workflow
- **`pages/02_Rider_Profile.py`**: Interacts with rider.py to build out appropriate Rider class with all relevant metrics

### **Performance Standards**
- Optimization should converge within 100 iterations
- W' utilization targeting within ±2% of target
- Support courses up to 200km with 50+ segments
- Real-time feedback for operations >2 seconds

## 🚴‍♂️ **Domain-Specific Rules**

### **Critical Power Model**
- Derived from 02_Rider_Profile
    - Highest fidelity is Strava pull of recent efforts (but API call intensive)
    - Next level of fidelity is entering riders' critical power and riding style, using 2-parameter CP model (Critical Power + W')
-   Default W' capacity: 15-35 kJ for trained cyclists depending on rider profile
- Intensity Factor calculation: power / critical_power
- TSS estimation: (time_hours) * (IF)^2 * 100

### **Physics Validation**
- Speed range: 5-120 km/h (realistic cycling speeds)
- Power range: 50-1800W (human physiological limits)
- Gradient range: -30% to +30% (rideable gradients)
- Acceleration limits: ±3 m/s² (realistic bike acceleration)

### **Course Processing**
- Minimum segment length: 100m
- Maximum segments: 50 (for UI performance)
- Elevation smoothing: 3-point moving average
- Gradient calculation: rise/run in decimal format

---
*Updated: June 22, 2025*
