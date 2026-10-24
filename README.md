# Pace Yourself

Cycling performance optimization with Streamlit, Strava integration, and physics-based pacing simulation.

## Current Runtime (Canonical)
- Entry point: `main.py`
- App shell: `pages_vibe/01_Race_Lab.py`
- Active tabs:
  - `pages_vibe/tabs/tab_course.py`
  - `pages_vibe/tabs/tab_segmentation.py`
  - `pages_vibe/tabs/tab_rider.py`
  - `pages_vibe/tabs/tab_optimization.py`

Legacy files under `archive/` are reference-only and are being deprecated in staged cleanup sprints.

## MVP Scope (3-4 Weeks)
- Course load/import and segmentation
- Rider setup
- Constant vs variable pacing comparison
- Database-backed course persistence
- Strava OAuth/API data flow

Strava connection is optional for the core workflow. Guest users can load the
shared course library or upload a CSV, apply the prefilled segmentation settings,
and optimize with the prefilled or manually edited rider profile. Fetching new
Strava segments and importing athlete data require authentication.

## Setup
1. Create and activate the project virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```
2. Install dependencies:
   ```bash
   .venv/bin/pip install -r requirements.txt
   ```
3. Start PostgreSQL (or use an existing server) and copy the environment template:
   ```bash
   docker compose up -d db
   cp .env.example .env
   ```
   Set these values in `.env`; the example database URL matches Docker Compose:
   ```bash
   ROUTE_PATH=data/sample_routes
   DATABASE_URL=postgresql://pace:pace@localhost:5432/pace_yourself
   TOKEN_ENCRYPTION_KEY=your_fernet_key
   STRAVA_CLIENT_ID=your_client_id
   STRAVA_CLIENT_SECRET=your_client_secret
   STRAVA_REDIRECT_URI=http://localhost:8501
   ```
   Generate `TOKEN_ENCRYPTION_KEY` with
   `.venv/bin/python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
   Register the redirect URI's domain as the Strava app's Authorization Callback
   Domain. Never commit `.env`, Streamlit secrets, or local databases.
4. Run app:
   ```bash
   .venv/bin/python -m streamlit run main.py
   ```

## Development and Validation
With `.venv` activated, install development dependencies and run the suite:
```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest tests/ -q
```
The supported runtime uses pandas 2.x (`>=2.3,<3`) and Streamlit 1.52.x.
Major pandas upgrades and Streamlit minor upgrades require a compatibility pass
over segmentation and the AppTest widget/form contracts before widening these
ranges.
Database integration tests require an isolated, disposable PostgreSQL database:
```bash
createdb pace_yourself_test
PACE_TEST_DATABASE_URL=postgresql:///pace_yourself_test .venv/bin/python -m pytest tests/ -q
```
Never point integration tests at production. GitHub Actions runs the suite
against a fresh PostgreSQL service for pull requests to `main` or `master`.

## Deployment Status
`Dockerfile` and `render.yaml` provide container and Render deployment scaffolding.
Auth, private rider data, private Strava-derived courses/segmentations, shared
non-Strava courses, and private results use PostgreSQL. Ownership is enforced
with application-user foreign keys. The MVP supports a fresh PostgreSQL
deployment; importing an external legacy SQLite database is not supported for
the initial launch. The production smoke test remains the final release gate.
See `docs/STATUS_MVP.md` for status.

### Render MVP deployment
1. Create the service from `render.yaml`. Keep `numInstances: 1`; OAuth state is
   process-local for the MVP.
2. Set `TOKEN_ENCRYPTION_KEY`, `STRAVA_CLIENT_ID`, `STRAVA_CLIENT_SECRET`, the
   final HTTPS `STRAVA_REDIRECT_URI`, and `APP_SUPPORT_URL` in Render. Do not
   reuse development credentials or commit secret values.
3. Register the deployed hostname as the Strava Authorization Callback Domain.
4. Deploy, confirm `/_stcore/health` returns success, then test both guest mode
   and an authenticated Course -> Segment -> Rider -> Optimize run.
5. Enable PostgreSQL backups before inviting users.
6. Keep Strava-fetched courses private. Do not publish or export one athlete's
   Strava data to another user without written Strava approval.
7. Test **Disconnect Strava and delete my data**, including its local-delete
   fallback when Strava is unavailable.

## Documentation Map
- Master MVP workplan and status: `docs/STATUS_MVP.md`
- Condensed architecture: `docs/ARCHITECTURE.md`
- Long-range strategy: `PROJECT_ROADMAP.md`

## Notes
- Notebooks in `notebooks/` are retained for experimentation/validation.
- Production behavior should live in `app/` and `pages_vibe/`.
