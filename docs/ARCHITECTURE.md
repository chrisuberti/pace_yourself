# Architecture (Condensed)

## System Overview
Pace Yourself is a Streamlit application for cycling course optimization. The
active product architecture uses a tab-styled workflow navigator centered on a
single runtime path.

## Runtime Flow
1. main.py starts the app and routes to Race Lab.
2. pages_vibe/01_Race_Lab.py initializes session state, authentication, the
   top workflow navigator, and the persistent setup summary.
3. Workflow modules handle feature domains:
- Course source/load and previews
- Segmentation preview/apply
- Rider profile setup
- Optimization execution and result visualization
4. Core domain logic in app/* performs course processing, physics simulation, optimization, persistence, and Strava integration.

## Active Module Boundaries
### UI
- pages_vibe/01_Race_Lab.py
- pages_vibe/tabs/state.py
- pages_vibe/tabs/tab_course.py
- pages_vibe/tabs/tab_segmentation.py
- pages_vibe/tabs/tab_rider.py
- pages_vibe/tabs/tab_optimization.py

### Domain/Core
- app/course.py
- app/optimization.py
- app/cycling_physics.py
- app/rider.py
- app/database.py
- app/auth.py
- app/strava_calls.py

## Data Contracts (High-Level)
- Course processing outputs normalized segment data used by optimization.
- Course point grades (including `gradient_smoothed`) are percentages. Canonical
  optimizer segments use decimal grades and meter distances; aggregated aliases
  `gradient_mean` and `distance_sum` use percentages and kilometers. Conversion
  follows the input schema, never a value's magnitude.
- Optimization supports both constant power and variable pacing paths.
- `CourseOptimizer` owns the canonical speed and W' transition kernels used by
	segment optimization and granular result simulation.
- Variable pacing uses a deterministic global-to-local search: differential
  evolution seeds low-dimensional terrain zones and constrained SLSQP refines
  all cluster powers. W' feasibility, a granular-simulation reserve, and
  nondecreasing power by average gradient are explicit constraints.
- The canonical UI passes total system mass (rider plus bike), CdA, and Crr into
	`CourseOptimizer`; legacy callers retain documented constructor defaults.
- Segment and granular simulations may differ in resolution, but must use the
	same rider physics and exponential W' recovery model.
- Exact elapsed-time equality is not required when point-resolution and
  segment-average inputs use different discretizations. Kernel and rider-input
  parity are the contract; detailed simulation is the canonical final comparison
  layer.
- Detailed simulation is the common comparison layer for final strategy
	visualization.

### Recurring Terrain Clustering
- `Course.preview_clustering_segmentation()` and `Course.auto_segmentation()`
	use the same deterministic clustering path.
- Features are robustly scaled smoothed gradient plus circular bearing
	(`sin`/`cos`), with user-controlled weighting and distance-based smoothing.
- Requested cluster types reuse the same `segment` ID wherever similar terrain
	recurs along the route; IDs are ordered from descending to climbing terrain.
- Minimum-run cleanup may absorb repeated short fragments but must not delete a
	requested terrain type. GPS gradient spikes are capped before fitting.

## State and Orchestration
- `pages_vibe/tabs/state.py` owns Streamlit session defaults and state access.
- `pages_vibe/tabs/_workflow.py` owns workflow transitions and prerequisite checks.
- `pages_vibe/tabs/_charts.py` contains pure Plotly figure builders with no
	Streamlit calls.
- The navigator updates only `vibe_active_step`; it is not a committed analysis
  transition and renders exactly one workflow module per rerun.
- Course, segmentation, rider, and optimization revisions define whether the
  last successful result is current or stale. Stale results retain their rider
  and course display context until a successful replacement or explicit reset.
- Network calls and expensive calculations require explicit user actions.

## Persistence
- PostgreSQL is the runtime store. `app/auth_store.py` owns `users` and
  `strava_tokens`; `app/db.py` provides per-operation connections for
  `app/database.py` and `app/rider.py`.
- PostgreSQL conversion and application-user ownership are implemented. The
  supported initial deployment uses a fresh PostgreSQL database.
- `courses` stores raw and processed route data plus summary metadata.
- `course_segmentations` stores named segmentation methods, parameters, and
	segment data associated with a course.
- `optimization_results` caches rider inputs, optimization parameters, results,
	and execution timing for a course/segmentation pair.
- Rider power efforts and profile data are managed separately by `app/rider.py`.
- Non-Strava courses and their terrain segmentations may be shared. Every
  Strava-derived course is private to `courses.owner_user_id`; its segmentations
  inherit privacy through course access checks. Rider caches and optimization
  results are also private. All private rows use application `user_id`
  ownership backed by `users` foreign keys. Legacy ownerless Strava courses and
  ownerless private rows are not returned by application queries.

### PostgreSQL Migration Order
1. Authentication: `users` and encrypted `strava_tokens` (implemented).
2. PostgreSQL rider/course/segmentation/result storage (implemented).
3. Enforce rider ownership by application user and define explicit shared/private
   course and segmentation policy (implemented).
4. Enforce result ownership and auth relationships at the schema boundary
   (implemented).
5. External legacy SQLite import remains unsupported for the initial launch.

## Strava Identity and Authentication Boundary
- PostgreSQL backs authentication and the rider/course/optimization stores.
  Ownership hardening and legacy data backfill remain separate work.
- `users` owns application identity and `strava_tokens.user_id` is a cascading
	foreign key. Access and refresh tokens are encrypted with
	`TOKEN_ENCRYPTION_KEY`; raw tokens are never stored in `.env` or logs.
- `pages_vibe/auth_ui.py` performs the authorize/callback flow, validates OAuth
  state, binds the returned `user_id` to the Streamlit session, explains
  requested scopes, and keeps logout separate from destructive disconnection.
- Issued OAuth states are single-use, expire after ten minutes, and are stored in
  process memory so they survive the Streamlit redirect/session boundary. Until
  that store becomes shared and durable, production must use one non-sleeping web
  instance; horizontal callback routing is unsupported.
- `app/auth.py` exchanges authorization codes, records accepted scopes,
  refreshes tokens per user, deauthorizes Strava, and deletes the local user.
  Cascading foreign keys remove tokens, rider caches, private courses and
  segmentations, and private results. `app/strava_calls.py` requires the user ID
  and converts scope/authentication and rate-limit responses into typed errors.
- `Verify Strava Account` calls `/athlete` only, then stores the athlete ID,
	name, optional profile weight, and profile-check time. It does not refresh PBs.
- `Refresh My Strava Data` is the explicit activity/power operation. It bypasses
	the local cache and stores best efforts, source, lookback, and a separate PB
	refresh timestamp. Ordinary reruns only read cached identity and efforts.
- Persisted rider profiles, best efforts, Strava courses, and optimization
  results use enforced application-user ownership. Only non-Strava courses and
  their terrain segmentations use the shared-library policy described above.
- Strava authentication is optional for the core Race Lab flow. Guest sessions
  may read the shared course/segmentation library, upload CSV data, and use
  prefilled or manually calculated rider profiles. Guest sessions cannot fetch
  Strava segments, verify an athlete, or import Strava power data.

## Legacy/Reference Areas
- archive/* and older page paths are reference-only and not canonical runtime.
- app/visualizations.py and app/visualizations_granular.py are retained for compatibility and reference, not active page rendering.

## Notebooks
- notebooks/* are retained for experimentation and validation.
- Production behavior must be implemented in app/* and pages_vibe/*.
