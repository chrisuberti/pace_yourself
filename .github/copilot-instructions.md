# GitHub Copilot Instructions for pace_yourself

## Python Environment
- **Always use the virtual environment located at `.venv/`** in the project root
- When running Python commands in terminal, ensure the venv is activated first
- For Python code execution tools, use the workspace's configured Python interpreter from `.venv/bin/python`
- When installing packages, use the venv's pip: `.venv/bin/pip`

## Project Overview
- This is a cycling performance optimization application using Streamlit
- The project uses Strava API for activity data integration
- Persistence: PostgreSQL for auth, rider, course, segmentation, and result stores. Rider/result ownership, explicit shared/private course policy, and SQLite backfill validation remain deployment gates.
- Entry point: `main.py` (run with `streamlit run main.py`)
- Development target: pages_vibe runtime path (legacy paths are reference-only)

## Architecture & Key Modules
- **`app/optimization.py`** - `CourseOptimizer` class: race simulation, constant power optimization, pacing analysis
- **`app/course.py`** - `Course` class: course processing, segmentation (equal distance, clustering)
- **`app/cycling_physics.py`** - Physics calculations (air resistance, rolling resistance, gradient, wind)
- **`app/rider.py`** - `Rider` class: critical power, W', CdA estimation, Strava best efforts
- **`app/critical_power.py`** - Critical power profile calculations
- **`app/course_management.py`** - Course storage and segmentation management
- **`app/visualizations.py`** - Plotting functions (course profiles, power strategy summaries)
- **`app/auth.py`** / **`app/strava_calls.py`** - Strava OAuth and API integration

## Streamlit Runtime (Canonical)
- `main.py` -> `pages_vibe/01_Race_Lab.py`
- Active tab modules:
  - `pages_vibe/tabs/tab_course.py`
  - `pages_vibe/tabs/tab_segmentation.py`
  - `pages_vibe/tabs/tab_rider.py`
  - `pages_vibe/tabs/tab_optimization.py`
- `archive/` and old page variants are reference-only and scheduled for staged deprecation

## Rider Setup Workflow (Current)
- `pages_vibe/tabs/tab_rider.py` is a top-to-bottom flow: General Characteristics -> Power Profile -> CdA.
- General inputs shared by every rider are height, rider weight, bike type, bike mass, position, and Crr; defaults live in `pages_vibe/tabs/state.py`.
- Bike type constrains valid positions and resets Crr and bike mass when changed. Crr defaults: TT `0.003`, Road `0.004`, Gravel `0.008`, MTB `0.012`. Bike mass defaults: TT/Tri `9.5kg`, Road `8.5kg`, Gravel `10.5kg`, MTB `12.5kg`. Users may override Crr and bike mass afterward.
- Height, bike type, and position update estimated CdA immediately. CdA is the bike/position baseline scaled by `height / 1.75`; no explicit calculate button or API call should be required.
- Power inputs and every API operation require an explicit button click. Never fetch Strava data in response to an ordinary widget change or page rerun.
- Strava authentication is per user: OAuth callback identity lives in PostgreSQL `users`, encrypted grants live in FK-backed `strava_tokens`, and each Streamlit session carries `auth_user_id`. Never read athlete access/refresh tokens from `.env`, mutate `.env`, log tokens, or call a Strava endpoint without the current user ID.
- Cached Strava identity, 1/5/20/60-minute PBs, lookback, source, profile-check time, and PB-refresh time should remain visible without a network call. Profile verification and PB refresh have separate timestamps. Strava profile weight is optional and may require `profile:read_all` scope.
- When Strava Import is selected and the cached athlete has at least two valid 2–30 minute efforts, actively fit the Rider CP/W' from those cached PBs. Exclude efforts under 2 minutes from CP/W' estimation; they may be displayed but cannot control the aerobic asymptote. Bound CP below the lowest sustained PB used in the fit. The graph and optimization must use that Strava-derived profile instead of the `250W`/`20kJ` new-rider defaults; this cache load must not call Strava.
- Power Profile uses a stateful source selector beside a persistent power-duration plot: Rider Type + CP estimate, Manual Best Efforts, and Strava Import. Default to Strava Import when a cached authenticated athlete exists; in that mode the chart shows athlete identity, refresh provenance, and cached PB markers alongside the CP + W' model.
- Manual best-effort defaults must work without editing: 30s `800W`, 60s `500W`, 120s `400W`, 300s `320W`, 1200s `270W`; require at least two non-zero efforts before curve fitting.
- Constructing `Rider` without a power method falls through to database/Strava lookup. CdA-only UI updates must explicitly avoid that path; a one-point `best_efforts` placeholder is invalid because SciPy fits two parameters and raises `N=2, M=1`.

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
- **Gradients**: Canonical optimizer segments use decimals (0.05 = 5%); Course point frames store percentages. Aggregated `gradient_mean` is percent and `distance_sum` is km. Convert by schema, never value magnitude.
- **Error handling**: Optimization functions must include fallback strategies; avoid `float('inf')` — use finite penalties (e.g., `1e6 + penalty`)
- **Simulation parity**: `CourseOptimizer` owns shared speed and W' transition kernels. Segment optimization and granular results must use the same rider physics, fallback speed behavior, and exponential recovery model. Canonical UI physics mass is rider weight plus bike mass.
- **Visualization**: Must support dark theme with consistent color mapping

## Testing
- **Test structure**: `tests/tests/` for validation/unit tests, `tests/debug/` for debugging scripts
- Run tests with: `.venv/bin/python -m pytest tests/tests/`
- Full suite: `.venv/bin/python -m pytest tests/ -q`; set `PACE_TEST_DATABASE_URL` to an isolated disposable PostgreSQL database for integration coverage. Never use production.
- Key test files:
  - `tests/tests/test_w_prime_optimization.py` - W' optimization validation
  - `tests/tests/test_enhanced_course_optimization.py` - Integration testing
  - `tests/scripts/integration_demo.py` - Full workflow demonstration
- Run tests before making significant changes

## Development Workflow
- Run tests before making significant changes
- Update relevant documentation when changing core functionality
- Use the notebooks in `notebooks/` for experimentation and validation only — production code lives in `app/` and `pages_vibe/`
- Operational status source: `docs/STATUS_MVP.md`
- Condensed architecture source: `docs/ARCHITECTURE.md`
- Long-range strategy source: `PROJECT_ROADMAP.md`

## Documentation Consolidation Rules
- Prefer updating canonical docs over creating new overlapping docs
- Canonical docs set:
  - `README.md`
  - `docs/STATUS_MVP.md`
  - `docs/ARCHITECTURE.md`
  - `PROJECT_ROADMAP.md`
  - `.github/copilot-instructions.md`
- `docs/STATUS_MVP.md` is the master operational workplan; do not create
  separate feature workplans unless explicitly requested.

## Skill Packs
Domain-specific AI context lives under `skills/`. Load the relevant pack when working in that area:
- `skills/mvp-triage/` — is this task in MVP scope?
- `skills/optimization-strategy/` — CP/W' theoretical foundation + every non-obvious decision in `CourseOptimizer`
- `skills/optimization-debug/` — pacing / W' / simulation diagnosis
- `skills/streamlit-flow/` — editing `pages_vibe/` or session state
- `skills/strava-data-path/` — OAuth, segments, activities, tokens
- `skills/notebook-to-app/` — promote a notebook prototype into the app
- `skills/release-checklist/` — cut an MVP milestone

## Refactor Conventions (pages_vibe)
- All committed workflow state writes route through `pages_vibe/tabs/_workflow.py` (`mark_course_loaded`, `mark_segmentation_applied`, `mark_rider_profile`, `mark_results`, `reset_analysis`).
- Tab gating uses `_workflow.require_course() / require_segmentation() / require_results()`.
- All Plotly figure construction lives in `pages_vibe/tabs/_charts.py` as pure builders (no `st.*` calls inside builders).
- Tab modules expose only `render(...)`; helpers are `_private`.
- Top navigation changes only `vibe_active_step` and renders one module; do not use native `st.tabs` for the four-step workflow.

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
- `STRAVA_REDIRECT_URI` - OAuth callback URL for this deployment
- `DATABASE_URL` - PostgreSQL connection URL; PostgreSQL is the target for all persistence
- `TOKEN_ENCRYPTION_KEY` - Fernet key used to encrypt per-user Strava grants