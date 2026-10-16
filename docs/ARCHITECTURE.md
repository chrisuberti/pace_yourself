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
- The canonical UI passes total system mass (rider plus bike), CdA, and Crr into
	`CourseOptimizer`; legacy callers retain documented constructor defaults.
- Segment and granular simulations may differ in resolution, but must use the
	same rider physics and exponential W' recovery model.
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
- PostgreSQL conversion is implemented, but ownership/backfill validation remains
  a deployment blocker; changing the database engine alone is not user isolation.
- `courses` stores raw and processed route data plus summary metadata.
- `course_segmentations` stores named segmentation methods, parameters, and
	segment data associated with a course.
- `optimization_results` caches rider inputs, optimization parameters, results,
	and execution timing for a course/segmentation pair.
- Rider power efforts and profile data are managed separately by `app/rider.py`.
- Courses and segmentations currently form a shared library with `created_by`
  provenance, not enforced private ownership. Optimization queries filter
  `owner_user_id`, which is nullable and has no auth foreign key. Rider cache
  operations currently identify rows by athlete ID; the intended application-user
  ownership contract is not yet enforced.

### PostgreSQL Migration Order
1. Authentication: `users` and encrypted `strava_tokens` (implemented).
2. PostgreSQL rider/course/segmentation/result storage (implemented).
3. Enforce rider ownership by application user and define explicit shared/private
   course and segmentation policy.
4. Enforce result ownership and auth relationships at the schema boundary.
5. Validate SQLite backfill and persistence parity before multi-user deployment.

## Strava Identity and Authentication Boundary
- PostgreSQL backs authentication and the rider/course/optimization stores.
  Ownership hardening and legacy data backfill remain separate work.
- `users` owns application identity and `strava_tokens.user_id` is a cascading
	foreign key. Access and refresh tokens are encrypted with
	`TOKEN_ENCRYPTION_KEY`; raw tokens are never stored in `.env` or logs.
- `pages_vibe/auth_ui.py` performs the authorize/callback flow, validates OAuth
	state, binds the returned `user_id` to the Streamlit session, and clears all
	session state on logout.
- `app/auth.py` exchanges authorization codes and refreshes tokens per user.
	`app/strava_calls.py` requires that user ID when resolving a token.
- `Verify Strava Account` calls `/athlete` only, then stores the athlete ID,
	name, optional profile weight, and profile-check time. It does not refresh PBs.
- `Refresh My Strava Data` is the explicit activity/power operation. It bypasses
	the local cache and stores best efforts, source, lookback, and a separate PB
	refresh timestamp. Ordinary reruns only read cached identity and efforts.
- Persisted rider profiles, best efforts, and optimization results must gain
  enforced application-user ownership; course sharing must be explicit.

## Legacy/Reference Areas
- archive/* and older page paths are reference-only and not canonical runtime.
- app/visualizations.py and app/visualizations_granular.py are retained for compatibility and reference, not active page rendering.

## Notebooks
- notebooks/* are retained for experimentation and validation.
- Production behavior must be implemented in app/* and pages_vibe/*.
