---
name: streamlit-flow
description: Editing the Streamlit UI under pages_vibe/. Covers session state rules, workflow gating, explicit actions, and chart construction conventions. Use whenever a change touches a workflow module, state.py, _workflow.py, or _charts.py.
---

# Streamlit Flow

## Canonical runtime
`main.py` → `pages_vibe/01_Race_Lab.py` → one active workflow module from
`pages_vibe/tabs/`:
- [tab_course.py](../../pages_vibe/tabs/tab_course.py)
- [tab_segmentation.py](../../pages_vibe/tabs/tab_segmentation.py)
- [tab_rider.py](../../pages_vibe/tabs/tab_rider.py)
- [tab_optimization.py](../../pages_vibe/tabs/tab_optimization.py)

Shared:
- [state.py](../../pages_vibe/tabs/state.py) — defaults + getters (`get_rider`, `get_course`, `get_results`).
- [_workflow.py](../../pages_vibe/tabs/_workflow.py) — gating + state write funnel.
- [_charts.py](../../pages_vibe/tabs/_charts.py) — pure Plotly builders (no `st.*` calls inside).

## Rules
1. **State writes funnel through `_workflow`.** Never assign `vibe_*` keys
   directly from a workflow module. Use:
   - `_workflow.mark_course_loaded(course, course_id, name)`
   - `_workflow.mark_segmentation_applied(course, name, params)`
   - `_workflow.mark_rider_profile(rider, rider_obj=None)`
   - `_workflow.mark_optimization_settings(params)`
   - `_workflow.mark_results(results, params=None)`
   - `_workflow.set_active_step(step)`
   - `_workflow.reset_analysis()`
2. **Gate at the top of `render`.** Use `_workflow.require_course()` /
   `require_segmentation()` / `require_results()`; bail early on `False`. The
   shell uses `can_open_step(step)` to disable blocked forward navigation.
   Optimize is the exception: a stale saved result remains viewable even while
   current prerequisites are incomplete.
3. **Workflow modules export only `render(...)`.** Everything else is `_private`.
4. **Charts are pure builders.** Functions in `_charts.py` return a
   `plotly.graph_objects.Figure`; they do not call `st.plotly_chart`. The tab
   wraps the call: `st.plotly_chart(_charts.build_X(...), width="stretch")`.
5. **New session-state keys** must be added to `SESSION_DEFAULTS` in `state.py`
   so `init_session_state()` initializes them. Use the `vibe_` prefix.
6. **Do not import from `archive/` or `app/visualizations*.py`** — both are
   reference-only and carry deprecation banners.
7. **Keep drafts separate from committed state.** Ordinary widget reruns may
   update local preview values, but API calls, curve fitting, segmentation, and
   optimization require explicit form/button submission. Do not auto-run work
   when a step first opens.
8. **Render one workspace at a time.** The top workflow navigator owns
   `vibe_active_step`. Do not use native `st.tabs` for the four-step workflow
   because every tab body executes on each rerun.
9. **Navigation is not a commit.** Top navigation and contextual Continue
   actions may update only `vibe_active_step`; they must not revise inputs,
   stale results, or trigger API/compute work.
10. **Preserve the last valid result.** Committed upstream changes mark results
    stale. Only a successful optimization replaces them, and only
    `reset_analysis()` intentionally clears the active analysis.

## When to extract
- A chart helper used in more than one tab → move to `_charts.py`.
- A state transition repeated in more than one place → add a `mark_*` helper
  in `_workflow.py`.
- A render path > ~50 lines or doing > one thing → split into a `_render_*` helper
  inside the same tab module.

## Run / smoke test
- `.venv/bin/python -m streamlit run main.py`
- Walk Course -> Segment -> Rider -> Optimize using the top navigator or contextual
   Continue actions. Confirm each step stays idle until its explicit primary
   action is submitted, and that only the active workspace renders.
