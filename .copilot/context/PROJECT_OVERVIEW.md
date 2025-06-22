# Project Context: Pace Yourself - Cycling Optimization App

## 🎯 **Project Overview**
Pace Yourself is a data-driven cycling performance optimization application that uses physics-based modeling to help cyclists plan optimal pacing strategies for different courses.

## 🏗️ **Current Architecture Status**

### **Phase 1: Core Functionality (85% Complete)**
- ✅ **Course Processing**: Elevation data import, segmentation, and analysis
- ✅ **W' Energy Modeling**: Anaerobic energy depletion and recovery tracking
- ✅ **Optimization Engine**: Constant power optimization with W' targeting
- ✅ **Visualization System**: Course profiles with power/speed overlays
- ⏳ **Fine-grained Physics**: Acceleration modeling for point-by-point prediction

### **Key Technical Achievements**
1. **Robust W' Optimization**: Targets specific W' utilization (50-95%) with high accuracy
2. **Segment-based Strategy**: Divides courses into manageable segments for optimization
3. **Physics Integration**: Real cycling physics (aerodynamics, rolling resistance, gravity)
4. **Streamlit Interface**: Interactive web app for course analysis and optimization

## 🔬 **Technical Architecture**

### **Core Modules**
- **`app/course.py`**: Course data processing, segmentation algorithms
- **`app/optimization.py`**: Physics-based optimization using Critical Power model
- **`app/cycling_physics.py`**: Fundamental physics calculations for cycling
- **`app/visualizations.py`**: Plotly-based visualization functions
- **`pages/03_Course_Optimization.py`**: Main user interface for optimization

### **Data Flow**
```
Raw GPS Data → Course Segmentation → Physics Optimization → Visualization
     ↓                ↓                     ↓               ↓
 (lat,lon,alt)    8-15 segments      Optimal Power    Interactive Charts
```

### **Optimization Approach**
1. **Input**: Course segments with distance, gradient, wind conditions
2. **Model**: 2-parameter Critical Power model (CP + W')
3. **Objective**: Minimize time while targeting specific W' utilization
4. **Output**: Optimal constant power with segment-by-segment breakdown

## 📊 **Current Capabilities**

### **What Works Well**
- ✅ Accurate W' depletion modeling (tested with 20km hilly course)
- ✅ Realistic power recommendations (305-310W for 300W CP rider)
- ✅ Proper numerical optimization (eliminates infinite results)
- ✅ Segment-by-segment power strategy breakdown
- ✅ Integration with existing visualization patterns

### **Known Limitations**
- ⚠️ Only constant power optimization (no variable power per segment)
- ⚠️ No acceleration modeling between course points
- ⚠️ Limited to pre-segmented courses (no raw GPS point processing)
- ⚠️ Power displayed as line charts instead of step functions

## 🎯 **Immediate Development Priorities**

### **Phase 1 Completion Tasks**
1. **Visualization Enhancement**: Replace line charts with step functions for power
2. **Fine-grained Physics**: Implement acceleration-aware speed solver
3. **Power Strategy Display**: Show segment-based power as bar charts
4. **Energy Tracking**: Add per-segment energy usage calculations

### **Technical Debt**
- Unit consistency issues between meters/kilometers in overlays
- `plot_power_strategy_summary` function needs simplification
- Missing acceleration physics for realistic speed transitions
- Need better integration between segment optimization and point visualization

## 🚴‍♂️ **Domain Knowledge**

### **Critical Power Model**
- **Critical Power (CP)**: Sustainable power output (threshold)
- **W' (W-prime)**: Anaerobic energy capacity above CP
- **Typical Values**: CP=250-400W, W'=15-35kJ for trained cyclists

### **Physics Modeling**
- **Forces**: Aerodynamic drag, rolling resistance, gravity, acceleration
- **Power Equation**: P = F_total × velocity
- **W' Depletion**: Rate depends on power above CP
- **Recovery**: W' recovers when power below CP

### **Course Analysis**
- **Segmentation**: Group similar terrain for optimization efficiency
- **Gradient Impact**: 1% grade ≈ 10W additional power requirement
- **Strategy**: Use W' on climbs, recover on flats/descents

## 🔄 **Development Workflow**

### **Testing Strategy**
- Unit tests for physics calculations
- Integration tests with sample courses
- Performance validation with known cycling data
- User interface testing in Streamlit

### **Code Organization**
- Modular design with clear separation of concerns
- Physics calculations isolated from UI logic
- Optimization algorithms independent of visualization
- Configuration through environment variables and session state

## 📈 **Future Roadmap**

### **Phase 2: Advanced Optimization**
- Variable power per segment optimization
- Dynamic pacing based on real-time conditions
- Multiple rider optimization (group dynamics)
- Integration with live power meter data

### **Phase 3: Competition Features**
- Race simulation with competitors
- Weather condition modeling
- Nutrition and hydration planning
- Performance prediction and goal setting

---
*Context last updated: June 22, 2025*
*Current Phase: 1 (Core Functionality) - 85% Complete*
