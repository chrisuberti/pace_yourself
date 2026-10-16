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
Auth, rider, course, segmentation, and result stores now use PostgreSQL. This does
not yet establish a multi-user-safe release: rider ownership, shared/private course
policy, database-enforced ownership, and SQLite data backfill still need review.
See `docs/STATUS_MVP.md` for the deployment gate.

## Documentation Map
- Master MVP workplan and status: `docs/STATUS_MVP.md`
- Condensed architecture: `docs/ARCHITECTURE.md`
- Long-range strategy: `PROJECT_ROADMAP.md`

## Notes
- Notebooks in `notebooks/` are retained for experimentation/validation.
- Production behavior should live in `app/` and `pages_vibe/`.
