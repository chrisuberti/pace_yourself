---
name: notebook-to-app
description: Promote a notebook prototype into the production app. Defines the extract → expose → wire → test checklist. Use when an experiment in notebooks/ should become a real feature in pages_vibe.
---

# Notebook → App Promotion

## When to invoke
- A notebook cell sequence produces a useful pipeline that the UI should run.
- A new analysis in `notebooks/` needs to be reachable from the 4-tab workflow.

## Hard rules
- **Never edit the source notebook** in a promotion change. Notebooks are
  preserved as reference. If the notebook itself has a bug, log it separately.
- **All promoted code lives in `app/`** for domain logic and
  `pages_vibe/tabs/` for UI. No business logic in tabs.

## Checklist
1. **Identify pure functions.** Distill the notebook flow into one or more
   stateless functions (input DataFrame/params → output DataFrame/scalar).
2. **Place in the right module.**
   - Physics / pacing math → [app/optimization.py](../../app/optimization.py)
     or [app/cycling_physics.py](../../app/cycling_physics.py).
   - Course/segmentation → [app/course.py](../../app/course.py).
   - Rider modeling → [app/rider.py](../../app/rider.py).
   - Persistence → [app/database.py](../../app/database.py).
3. **Respect the boundary contract.** Inputs/outputs at the optimizer boundary
   must use the canonical schema: `distance` (m), `gradient` (decimal),
   `altitude` (m), `wind` (m/s). See [optimization-debug](../optimization-debug/SKILL.md).
4. **Wire into a tab.** Add or extend a `render(...)` in
   [pages_vibe/tabs/](../../pages_vibe/tabs/). All state writes go through
   `_workflow.mark_*` helpers (see [streamlit-flow](../streamlit-flow/SKILL.md)).
5. **Extract chart code to `_charts.py`.** Pure builders only; the tab calls
   `st.plotly_chart(_charts.build_X(...))`.
6. **Add a boundary or unit test** in `tests/tests/`. At minimum, cover the
   public function's contract — column names, units, idempotency where relevant.
7. **Update `docs/STATUS_MVP.md`** if the promotion changes MVP scope or
   exit-criteria status. Do not create a new markdown file.
8. **Smoke test.** `.venv/bin/python -m streamlit run main.py` and walk the
   affected tab.

## Do not
- Don't import from `archive/`, `app/visualizations*.py`, or `pages_old/`.
- Don't `import notebooks.*` from app code; notebooks may import from `app.*`
  but never the reverse.
- Don't create a separate workplan when the update belongs in
   [docs/STATUS_MVP.md](../../docs/STATUS_MVP.md).
