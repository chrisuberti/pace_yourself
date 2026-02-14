# GitHub Copilot Instructions for pace_yourself

## Python Environment
- **Always use the virtual environment located at `.venv/`** in the project root
- When running Python commands in terminal, ensure the venv is activated first
- For Python code execution tools, use the workspace's configured Python interpreter from `.venv/bin/python`
- When installing packages, use the venv's pip: `.venv/bin/pip`

## Project Overview
- This is a cycling performance optimization application using **Streamlit** as the UI framework
- The project uses **Strava API** for activity data integration
- Database: **SQLite** (`rider_data.db`)
- Entry point: `main.py` (run with `streamlit run main.py`)
- Current status: **Phase 1 Complete**, Phase 2 (User Experience & Performance) in progress

## Architecture & Key Modules
- **`app/optimization.py`** - `CourseOptimizer` class: race simulation, constant power optimization, pacing analysis
- **`app/course.py`** - `Course` class: course processing, segmentation (equal distance, clustering)
- **`app/cycling_physics.py`** - Physics calculations (air resistance, rolling resistance, gradient, wind)
- **`app/rider.py`** - `Rider` class: critical power, W', CdA estimation, Strava best efforts
- **`app/critical_power.py`** - Critical power profile calculations
- **`app/course_management.py`** - Course storage and segmentation management
- **`app/visualizations.py`** - Plotting functions (course profiles, power strategy summaries)
- **`app/auth.py`** / **`app/strava_calls.py`** - Strava OAuth and API integration

## Streamlit Pages
- `main.py` - Landing page
- `pages/01_Segment_Data_and_Course_Segmentation.py` - Course data and segmentation
- `pages/02_Rider_Profile.py` - Rider parameter configuration
- `pages/03_Course_Optimization.py` - Power optimization and race strategy

## Key Domain Concepts
- **Critical Power (CP)**: Sustainable aerobic power threshold (watts)
- **W' (W prime)**: Anaerobic work capacity above CP (joules), typically 15,000-25,000J
- **W' depletion/recovery**: Energy tank model — depletes above CP, recovers below CP
- **CdA**: Aerodynamic drag area (coefficient of drag × frontal area)
- **TSS/IF**: Training Stress Score and Intensity Factor — training load metrics

## Coding Standards
- **Default Behavior**: Functions should have sensible defaults for typical use cases, everything should run with no arguments or user input for a new user
- **Units**: Internal calculations use meters, m/s, watts, joules. Display uses km, km/h where appropriate
- **Power visualization**: Use step functions or line charts, not bar charts
- **Power Visualization**: Always show the power curve relative to the CP and where you are on the course (give context of the terrain with course profile or map)s
- **Gradients**: Stored as decimals internally (e.g., 0.05 = 5%), displayed as percentages
- **Error handling**: Optimization functions must include fallback strategies; avoid `float('inf')` — use finite penalties (e.g., `1e6 + penalty`)
- **Visualization**: Must support dark theme with consistent color mapping

## Testing
- **Test structure**: `tests/tests/` for validation/unit tests, `tests/debug/` for debugging scripts
- Run tests with: `.venv/bin/python -m pytest tests/tests/`
- Key test files:
  - `tests/tests/test_w_prime_optimization.py` - W' optimization validation
  - `tests/tests/test_enhanced_course_optimization.py` - Integration testing
  - `tests/debug/integration_demo.py` - Full workflow demonstration
- Run tests before making significant changes

## Development Workflow
- Run tests before making significant changes
- Update relevant documentation when changing core functionality
- Use the notebooks in `notebooks/` for experimentation and validation only — production code lives in `app/`
- Check `PROJECT_ROADMAP.md` for current priorities and phase status
- **Streamlit URL pattern**: Page filenames drop their number prefix in URLs (e.g., `01_Segment_Data_and_Course_Segmentation.py` → `/Segment_Data_and_Course_Segmentation`)

## Common Patterns
```python
# Standard optimization workflow
from app.course import Course
from app.optimization import CourseOptimizer, create_course_segments_from_course

course = Course(course_dataframe)
course.equal_segmentation(8)
segments = create_course_segments_from_course(course)
optimizer = CourseOptimizer(critical_power=300, w_prime=25000)
optimal_power, time, results = optimizer.optimize_constant_power(segments)
```

## Environment Variables (`.env`)
- `ROUTE_PATH` - Path to route CSV files (default: `data/sample_routes`)
- `STRAVA_CLIENT_ID` / `STRAVA_CLIENT_SECRET` - Strava API credentials
- `STRAVA_ACCESS_TOKEN` / `STRAVA_REFRESH_TOKEN` - Strava auth tokens