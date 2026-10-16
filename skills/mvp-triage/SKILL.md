---
name: mvp-triage
description: Decide whether an incoming task, bug, or feature request belongs in the current MVP scope before doing any work. Use first when a user asks for "a quick fix", "while you're at it…", or anything that might balloon scope.
---

# MVP Triage

## When to invoke
- New bug report or feature ask that is not obviously in the canonical MVP scope.
- Anything that touches files outside the canonical runtime path.
- Any request that says "also", "and another thing", or "small change".

## Authoritative source
[docs/STATUS_MVP.md](../../docs/STATUS_MVP.md) — read the "MVP Scope In/Out" section first.
Strategic / long-range items live in [PROJECT_ROADMAP.md](../../PROJECT_ROADMAP.md) and are NOT MVP unless promoted to STATUS_MVP.

## Decision rules
1. If the task changes behavior in the canonical runtime path
   (main.py → pages_vibe/01_Race_Lab.py → pages_vibe/tabs/*), it is in-scope.
2. If it touches `app/optimization.py`, `app/course.py`, `app/cycling_physics.py`,
   `app/rider.py`, `app/database.py`, `app/auth.py`, or `app/strava_calls.py`,
   it is in-scope IF it affects one of the four MVP flows:
   load course → segment → rider setup → optimize.
3. If it touches `archive/`, `app/visualizations*.py`, `notebooks/`,
   `docs/architecture/`, `docs/notebook_based_workplans/`,
   or any doc carrying a "REFERENCE ONLY" banner, it is OUT of MVP scope —
   defer to a later sprint.
4. If it adds a new markdown file, it is OUT of scope. Update the canonical doc set instead.
5. If it modifies a notebook, it is OUT of scope. Notebooks are preserved as-is.

## Output expectation
For each triage:
- Verdict: `IN MVP` / `OUT OF MVP` / `SPLIT (in-scope part: X, out-of-scope part: Y)`.
- Pointer to the canonical doc that justifies the verdict.
- One-line action: "do now", "log in STATUS_MVP.md backlog", or "defer to roadmap".

## Exit criteria check
Refer to the "Exit Criteria" section of `docs/STATUS_MVP.md`. Any task that
materially helps a criterion turn green is in-scope.
