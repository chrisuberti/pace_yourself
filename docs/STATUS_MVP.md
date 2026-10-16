# MVP Status (Operational Source of Truth)

Last updated: 2026-10-16

## Goal
Deliver an MVP in 3-4 weeks with one canonical app path and staged legacy deprecation.

## Document Role
This is the **master operational workplan** for the active MVP. Current scope,
priorities, acceptance criteria, blockers, and execution updates belong here.

- `README.md`: setup and quick start.
- `docs/ARCHITECTURE.md`: current system structure and contracts.
- `PROJECT_ROADMAP.md`: long-range strategy after the MVP.
- `.github/copilot-instructions.md`: repository rules for AI coding agents.

## Canonical Runtime Path
- Entry: main.py
- App shell: pages_vibe/01_Race_Lab.py
- Active UI modules:
  - pages_vibe/tabs/tab_course.py
  - pages_vibe/tabs/tab_segmentation.py
  - pages_vibe/tabs/tab_rider.py
  - pages_vibe/tabs/tab_optimization.py

## MVP Scope (In)
- Course load/import and segmentation
- Rider setup
- Constant and variable pacing comparison
- Database persistence and course library
- Strava OAuth/API flow

## MVP Scope (Out for now)
- Broader advanced analytics expansion
- Legacy page parity beyond required migrations
- Notebook-to-app full parity work (notebooks remain for experimentation)

## Workstreams
### A. Canonical Development
- pages_vibe and app modules used by pages_vibe
- All new feature work lands here

### B. Legacy Reference (Read-Only)
- archive/* and prior page implementations
- Used for migration reference only
- Scheduled for deletion in staged cleanup sprints

## Current Decisions
- Continue development in pages_vibe path
- Keep all notebooks
- Keep Streamlit through the MVP and reevaluate the UI framework afterward
- Use this file as the only active implementation workplan

## Active Priority
**Next implementation phase:** MVP Streamlit UX Workplan, Phase 4 - Feedback
and Layout Polish. Complete the phases below in order unless a
blocking defect takes priority.

| Phase | Status |
|---|---|
| Documentation consolidation | Complete |
| 1. Guided App Shell | Complete |
| 2. Explicit Commit and Action Boundaries | Complete |
| 3. Durable Results and Stale-State Model | Complete |
| 4. Feedback and Layout Polish | Next |
| 5. MVP Validation and Migration Decision | Queued |

Phases 1 and 2 completed 2026-08-08: the canonical runtime now renders one
workflow step at a time from a persistent workflow navigator, shows the active setup,
provides contextual Continue actions, and requires explicit Load, Process,
Fetch, Apply, Calculate, Import, and Optimize actions before committing work.
Integrated AppTest coverage verified the Course -> Segment -> Rider -> Optimize
path and confirmed that opening a step or changing a draft control does not
implicitly load a course, apply segmentation, fetch API data, or optimize.

Blocking defect completed 2026-08-08: recurring terrain clustering now uses
robust gradient/circular-bearing features, preserves requested types during
spatial cleanup, and exposes live tuning controls and diagnostics in Segment.

Simulation alignment completed 2026-08-09: segment optimization and granular
results now share total system mass (rider plus editable bike mass), CdA/Crr
physics, and the same exponential W' transition model. Bike-type defaults
differentiate Road, TT/Tri, Gravel, and MTB setups. The separate granular
acceleration approximation and the Climb Aggression UI control were removed.
Synthetic contracts enforce model parity without coupling optimization behavior
to a specific route.

Strava rider provenance completed 2026-08-10: Rider now names the authenticated
athlete, shows cached 1/5/20/60-minute PBs and refresh age, distinguishes a
lightweight account verification from an explicit PB refresh, and records
source, lookback, profile-check time, PB-refresh time, and optional Strava
weight. PB refresh bypasses the local cache. Rider, course, and result stores
remain transitional until their PostgreSQL schemas enforce `user_id` ownership.

PostgreSQL authentication slice completed 2026-08-10: the application now has a
Strava authorize/callback boundary, OAuth state validation, session-bound users,
logout isolation, PostgreSQL `users`, and encrypted FK-backed `strava_tokens`.
Token refresh is per user and no longer reads athlete grants from or rewrites
`.env`. The persistence decision is now PostgreSQL for the entire application.
Remaining migration order: rider profiles/PBs, courses/segmentations, then
optimization results; each table must carry `user_id` ownership before the
deployment is considered multi-user safe.

Branch consolidation completed 2026-10-15: rider profiles/PBs, courses,
segmentations, and results now use PostgreSQL through per-operation connections.
The engine migration does not close the deployment gate: rider cache keys still
use athlete IDs, the course/segmentation library is global, and result ownership
is query-scoped rather than enforced by auth foreign keys. Before multi-user
deployment, enforce rider/result ownership, define explicit shared/private course
policy, and validate legacy SQLite backfill.

Consolidation also fixes Strava course persistence against the PostgreSQL API,
stages imported profile weight before Streamlit widget creation, and locks short
meter distances and gentle percentage grades to their schema-defined units.
Regression coverage runs in GitHub Actions with an isolated PostgreSQL service.
Local databases, OS metadata, secrets, and conversation exports are excluded from
application commits/container context. Docker/Render configuration is scaffolding,
not confirmation that the remaining deployment gates are complete.

Historical context reconciliation completed 2026-10-16: the imported rider,
terrain/optimizer, workflow, authentication, and PostgreSQL work is already
represented on current master by the 2026-10-15 consolidation. There is no
remaining branch-recovery or re-integration task. Historical test counts are
evidence from their original worktrees, not current validation results.

### Outstanding Deployment Requirements and Decisions

Requirements before a multi-user deployment:
- Replace athlete-ID rider cache ownership with enforced application `user_id`
  ownership and auth foreign keys.
- Add an auth foreign key for optimization result ownership and reject
  ownerless result writes in authenticated flows.
- Validate the legacy SQLite backfill into an isolated PostgreSQL database,
  including the expected handling of orphaned segmentations and non-finite JSON
  values.
- Add an integration regression proving the canonical UI constructs
  `CourseOptimizer` with committed rider mass plus bike mass, CdA, and Crr.
- Provision the production PostgreSQL and web service, configure
  `TOKEN_ENCRYPTION_KEY`, Strava credentials, and the registered production
  callback, then run the authenticated Course -> Segment -> Rider -> Optimize
  smoke test.

Product/deployment decisions that require owner input before changing direction:
- **Course visibility:** the implementation currently provides one deduplicated,
  globally shared course/segmentation library with creator provenance. Decide
  whether that remains the approved MVP policy or whether private/"My Courses"
  ownership is required before deployment.
- **OAuth scaling:** issued OAuth states currently live in process memory. Keep
  one non-sleeping web instance for the MVP, or approve shared durable OAuth
  state before horizontal scaling. The current implementation is not safe for
  callback routing across multiple instances.

## Exit Criteria for MVP
- End-to-end app path works from Course -> Segment -> Rider -> Optimize
- Strava auth and data ingestion happy path succeeds
- DB load/save/reload works for courses and rider settings
- Core optimization comparison renders without manual patching

## MVP Streamlit UX Workplan

### Platform Decision
Keep Streamlit for the MVP. It remains the fastest way to deliver the current
Python-heavy workflow without introducing a separate frontend and API contract.
Re-evaluate NiceGUI, Dash, or FastAPI + React after the MVP based on observed
UX limits, deployment needs, and whether the app becomes multi-user.

Streamlit's constraints are understood:
- Each interaction reruns the script from top to bottom.
- Widget state and domain state can become entangled.
- Fine-grained layouts, transitions, routing, modals, responsive behavior, and
  asynchronous work are limited.
- Broad tabs tend to feel like notebook controls instead of a guided workflow.

The MVP response is to design around those constraints rather than migrate the
UI framework now.

### Target Experience
- A persistent top workflow navigator for Course -> Segment -> Rider -> Optimize.
- One focused workspace at a time instead of four simultaneously rendered tabs.
- A persistent course/rider summary visible throughout the workflow.
- Forms that commit related values together and distinguish draft inputs from
  applied domain state.
- Explicit buttons for every API call and expensive calculation: Fetch,
  Process, Calculate, Apply, Optimize, and Re-optimize.
- Clear empty, loading, success, stale-result, and failure states with an
  actionable recovery message.
- Existing optimization results remain visible while parameters are edited;
  edits mark results stale and replacement occurs only after an explicit run.

### Implementation Principles
- Keep physics, course, rider, optimization, and chart builders independent of
  Streamlit. Streamlit modules orchestrate them but do not own domain logic.
- Route workflow state transitions through `pages_vibe/tabs/_workflow.py`.
- Store only committed values in canonical `vibe_*` state; use widget/form keys
  for drafts.
- Never trigger Strava, database writes, curve fitting, segmentation, or
  optimization from an ordinary widget rerun.
- Preserve the last valid result when a new operation fails.
- Optimize desktop first for the MVP, while ensuring controls stack cleanly on
  narrow screens and no information depends on hover alone.

### Phase 1 - Guided App Shell (Must Have)
Target: `pages_vibe/01_Race_Lab.py`, `pages_vibe/tabs/state.py`, and
`pages_vibe/tabs/_workflow.py`.

- Replace the four top-level `st.tabs` with a tab-styled workflow navigator
  backed by a single `vibe_active_step` value.
- Render only the active step's module.
- Show completion, current, blocked, and stale states in the rail.
- Allow revisiting completed steps; block forward navigation only when a true
  prerequisite is missing.
- Add a compact persistent summary containing course, distance, segmentation,
  rider CP/W', CdA, Crr, and result status.

Acceptance criteria:
- Only one workflow module renders per rerun.
- Refreshing the page preserves the current step for the session.
- A user can always see what is complete, what is required next, and which
  course/rider configuration is active.

### Phase 2 - Explicit Commit and Action Boundaries (Must Have)
Targets: all four modules under `pages_vibe/tabs/`.

- Group related editable controls in `st.form` where live preview is not needed.
- Course: require explicit buttons for CSV processing, database loading when
  appropriate, and Strava segment fetch. Entering or changing an ID must not
  call the API.
- Segmentation: keep draft strategy/parameters separate from the applied
  segmentation; apply only on button click.
- Rider: retain immediate local CdA preview for height/bike/position changes,
  but require explicit Calculate or Import actions for all power methods and
  Strava calls.
- Optimize: remove first-visit auto-run. Require Optimize/Re-optimize and retain
  the previous results while controls are edited.
- Disable duplicate submissions while an operation is running where Streamlit
  supports it.

Acceptance criteria:
- No API call or expensive calculation occurs from changing a regular widget.
- Every operation has an unambiguous primary action.
- Cancelling or abandoning draft edits cannot silently mutate applied results.

### Phase 3 - Durable Results and Stale-State Model (Must Have)
Targets: `pages_vibe/tabs/_workflow.py`, `pages_vibe/tabs/state.py`, and
`pages_vibe/tabs/tab_optimization.py`.

- Track a lightweight input signature or revision for course, segmentation,
  rider, and optimization settings.
- Mark results stale when committed upstream inputs change instead of clearing
  the result immediately.
- Display the previous result with a visible "Inputs changed" status and a
  Re-optimize action.
- Replace stored results atomically only after a successful optimization.
- Provide an explicit reset/new-analysis action rather than relying on implicit
  downstream state deletion.

State and navigation contract:
- Navigation-only actions update `vibe_active_step` and never revise committed
  inputs, stale a result, call an API, or start computation.
- Committed course, segmentation, rider/physics, and optimization settings own
  separate revisions. A successful result stores the revisions and lightweight
  rider/course display context that produced it.
- Upstream commits invalidate current prerequisites where necessary but retain
  the last result. The Optimize workspace remains reachable to inspect stale
  output, and replacement occurs only after a complete successful rerun.
- New analysis is the explicit clearing boundary for course, segmentation, and
  results; authentication and the rider profile remain available.

Acceptance criteria:
- Parameter edits never make a valid result disappear unexpectedly.
- Failed recalculation leaves the last valid result available.
- Export clearly identifies whether it represents current or stale inputs.

Completed 2026-10-16: the canonical Race Lab combines a status-aware top
navigator with single-workspace rendering. Result signatures now distinguish
navigation from committed state changes, preserve stale results and their chart
context, label exports, and keep the prior result after failed recalculation.

### Phase 4 - Feedback and Layout Polish (Should Have)
- Standardize operation feedback: pending spinner/status, success confirmation,
  concise failure summary, expandable technical detail, and recovery action.
- Replace passive gating messages with a direct action such as "Go to Course"
  or "Apply Segmentation".
- Use consistent button labels and hierarchy across steps.
- Keep key charts and summary metrics above detailed tables.
- Use compact expanders for advanced parameters and diagnostics.
- Verify narrow-screen stacking, label wrapping, chart sizing, keyboard focus,
  and color contrast.

Acceptance criteria:
- Course -> Segment -> Rider -> Optimize can be completed without guessing the
  next action.
- Errors explain what the user can do next without exposing a traceback by
  default.
- The primary workflow remains usable at desktop and narrow browser widths.

### Phase 5 - MVP Validation and Migration Decision
- Add focused tests for workflow transitions, stale-result behavior, and action
  boundaries around Strava and optimization calls.
- Add a UI-to-optimizer integration regression proving committed rider mass plus
  bike mass, CdA, and Crr reach `CourseOptimizer`.
- Run the canonical test suite and a manual happy-path/error-path walkthrough.
- Record rough timings for course processing, Strava fetch, segmentation, and
  optimization so slow operations are visible and cancellable where practical.
- Conduct a short usability pass with at least one rider unfamiliar with the
  implementation.
- After MVP feedback, prototype one representative screen in the leading
  alternative framework before deciding on migration.

MVP UX exit criteria:
- A first-time user completes the core flow without developer guidance.
- No network or compute-heavy work starts without an explicit action.
- Current inputs, applied inputs, and stale results are visibly distinguishable.
- The last valid optimization remains inspectable during parameter refinement.
- The canonical Course -> Segment -> Rider -> Optimize path passes smoke tests.

### Deferred Companion Output
An interactive Plotly HTML race report remains a valuable post-MVP companion,
not a replacement for the application. It can provide portable maps, charts,
hover details, pacing tables, and summary metrics, but new segmentation,
optimization, Strava access, and database writes still require a Python runtime.

## Notes
- PROJECT_ROADMAP.md is strategic/long-range.
- This file is the operational status source for near-term execution.

## Validation Commands
- Full unit suite: `.venv/bin/python -m pytest tests/tests/`
- Optimization boundary contract:
  `.venv/bin/python -m pytest tests/tests/test_optimization_boundary_contract.py -v`
- App smoke test: `.venv/bin/python -m streamlit run main.py`
