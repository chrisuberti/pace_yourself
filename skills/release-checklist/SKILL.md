---
name: release-checklist
description: Cut an MVP milestone — run the full verification gauntlet, confirm exit criteria, and produce a clean tag. Use when stamping an MVP candidate.
---

# Release Checklist

## Pre-flight
1. `git status --short` — working tree clean (or only intentional changes).
2. `git switch` to the intended release branch.
3. `git pull --ff-only` — up to date with remote.

## Verification
4. **Targeted pytest subset** (must pass, modulo known non-blocking items in
   [docs/STATUS_MVP.md](../../docs/STATUS_MVP.md)):
   ```
   .venv/bin/python -m pytest tests/ -k "optimization or strava or course or visualization"
   ```
5. **Boundary contract regression** (must pass with 0 failures):
   ```
   .venv/bin/python -m pytest tests/tests/test_optimization_boundary_contract.py -v
   ```
6. **Streamlit smoke walk:**
   ```
   .venv/bin/python -m streamlit run main.py
   ```
   Walk every tab in order:
   - **Course:** load from DB, upload a CSV, fetch a Strava segment.
   - **Segment:** apply Terrain, Equal, and Clustering methods.
   - **Rider:** general characteristics; all three power methods; CdA update.
   - **Optimize:** submit Optimize/Re-optimize; confirm the W' ceiling behavior and rider physics; export CSV.

## Doc audit
7. Canonical set fully reflects current state:
   - [README.md](../../README.md)
   - [.github/copilot-instructions.md](../../.github/copilot-instructions.md)
   - [docs/STATUS_MVP.md](../../docs/STATUS_MVP.md) — exit criteria checked.
   - [docs/ARCHITECTURE.md](../../docs/ARCHITECTURE.md)
   - [PROJECT_ROADMAP.md](../../PROJECT_ROADMAP.md) — strategy only.
8. Every archived `.py` carries the "ARCHIVE / REFERENCE ONLY" header.

## Exit criteria (from `docs/STATUS_MVP.md`)
- End-to-end flow: Course → Segment → Rider → Optimize works.
- DB save/reload works for course + rider state.
- Strava auth + retrieval happy path succeeds.
- Constant + variable pacing comparison renders without manual patching.
- Canonical doc set is the only operational source.
- A new chat can act from canonical instructions alone.

## Tag and push
9. Update `docs/STATUS_MVP.md` "Last updated" date and current status.
10. Commit with imperative subject line:
    `release: MVP v0.X.0 — <one-line summary>`
11. Tag: `git tag -a vX.Y.Z -m "MVP X.Y.Z"`.
12. Push branch and tag (ask user before `git push`).

## Don't
- Don't bypass `--no-verify` on commits.
- Don't tag if any blocking item in `docs/STATUS_MVP.md` is unresolved.
- Keep documentation cleanup separate from a release commit.
