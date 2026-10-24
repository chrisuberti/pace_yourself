"""Network- and database-free regressions for the canonical Strava imports."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from streamlit.testing.v1 import AppTest

from pages_vibe.tabs import tab_course, tab_rider


RIDER_APP = """
from pages_vibe.tabs.state import init_session_state
from pages_vibe.tabs.tab_rider import render

init_session_state()
render()
"""

COURSE_APP = """
from pages_vibe.tabs.state import init_session_state
from pages_vibe.tabs.tab_course import _render_strava_fetch

init_session_state()
_render_strava_fetch()
"""


@pytest.fixture(autouse=True)
def block_network(monkeypatch):
    request = Mock(side_effect=AssertionError("Unexpected network request"))
    monkeypatch.setattr("requests.sessions.Session.request", request)
    yield
    request.assert_not_called()


def _button(app, label):
    return next(button for button in app.button if button.label == label)


def _run_rider(app):
    # AppTest models single-select segmented controls as multi-value groups.
    if app.button_group:
        app.button_group[0].set_value(["Strava Import"])
    return app.run()


def test_segment_persistence_uses_store_course_deduplication(monkeypatch):
    db = Mock(spec_set=["store_course"])
    db.store_course.return_value = "cached-course"
    monkeypatch.setattr(tab_course, "get_course_db", lambda: db)
    gps = [{"lat": 51.0, "lon": -1.0, "ele": 20.0}]

    assert tab_course._persist_strava_segment(" 123 ", "Climb", gps) == "cached-course"
    assert tab_course._persist_strava_segment("123", "Climb", gps) == "cached-course"

    assert db.store_course.call_count == 2
    db.store_course.assert_called_with({
        "name": "Climb",
        "strava_segment_id": "123",
        "raw_gps_data": gps,
        "created_by": "strava",
        "course_type": "strava_segment",
    })


def test_segment_import_commits_course_only_on_explicit_fetch(monkeypatch):
    details = Mock(return_value={"name": "Imported climb"})
    streams = Mock(return_value={
        "latlng": [[51.0, -1.0], [51.001, -1.0]],
        "altitude": [20.0, 25.0],
    })
    monkeypatch.setattr("app.strava_calls.fetch_segment_details", details)
    monkeypatch.setattr("app.strava_calls.fetch_segment_data", streams)
    db = Mock(spec_set=["store_course"])
    db.store_course.return_value = "saved-course"
    monkeypatch.setattr(tab_course, "get_course_db", lambda: db)
    course = SimpleNamespace(name="processed-course")
    monkeypatch.setattr(tab_course, "Course", Mock(return_value=course))

    app = AppTest.from_string(COURSE_APP)
    app.session_state["auth_user_id"] = "course-owner"
    app.session_state["vibe_segmentation_applied"] = True
    app.session_state["vibe_optimization_results"] = {"old": True}
    app.run()
    app.text_input[0].set_value("123").run()
    app.run()
    details.assert_not_called()
    streams.assert_not_called()
    db.store_course.assert_not_called()

    _button(app, "Fetch Segment").click().run()

    assert not list(app.exception)
    assert not list(app.error)
    details.assert_called_once_with("123", user_id="course-owner")
    streams.assert_called_once_with("123", user_id="course-owner")
    db.store_course.assert_called_once()
    assert app.session_state["vibe_course"] is course
    assert app.session_state["vibe_course_id"] == "saved-course"
    assert app.session_state["vibe_course_name"] == "Imported climb"
    assert not app.session_state["vibe_segmentation_applied"]
    assert app.session_state["vibe_optimization_results"] == {"old": True}
    assert app.session_state["vibe_course_revision"] == 1
    assert app.session_state["auth_user_id"] == "course-owner"

    app.run()
    _button(app, "Fetch Segment").click().run()
    assert details.call_count == streams.call_count == db.store_course.call_count == 1


def test_segment_import_requires_authenticated_user():
    app = AppTest.from_string(COURSE_APP)
    app.run()

    assert not list(app.exception)
    assert not list(app.text_input)
    assert any(
        "Connect Strava" in info.value
        for info in app.info
    )


@pytest.mark.parametrize(
    ("profile_weight", "use_weight", "expected_weight"),
    [(72.5, True, 72.5), (72.5, False, 80.0), (None, True, 80.0)],
)
def test_rider_refresh_stages_weight_before_widget_rerun(
    monkeypatch, profile_weight, use_weight, expected_weight,
):
    imported = SimpleNamespace(
        critical_power=280,
        WTank=24000,
        best_efforts={300: 360.0, 1200: 300.0},
        strava_athlete_id="42",
        athlete_first_name="Imported",
        athlete_last_name="Rider",
        strava_weight=profile_weight,
        strava_last_synced_at="2026-10-15T12:00:00+00:00",
        strava_lookback_days=90,
    )
    rider_factory = Mock(return_value=imported)
    rider_factory.BIKE_TYPE_CDA = tab_rider.Rider.BIKE_TYPE_CDA
    monkeypatch.setattr(tab_rider, "Rider", rider_factory)
    cache = Mock(return_value=None)
    monkeypatch.setattr(tab_rider, "get_cached_strava_rider", cache)
    verify = Mock(side_effect=AssertionError("Verification needs its own button"))
    monkeypatch.setattr(tab_rider, "get_athlete_profile", verify)

    app = AppTest.from_string(RIDER_APP)
    app.session_state["auth_user_id"] = "rider-owner"
    app.session_state["auth_user"] = {"strava_athlete_id": "42"}
    app.run()
    _run_rider(app)
    app.checkbox[0].set_value(use_weight)
    _run_rider(app)
    _run_rider(app)
    rider_factory.assert_not_called()
    verify.assert_not_called()
    app.session_state["vibe_optimization_results"] = {"old": True}
    app.session_state["vibe_segmentation_applied"] = True

    _button(app, "Refresh My Strava Data").click()
    _run_rider(app)

    assert not list(app.exception)
    assert not list(app.error)
    rider_factory.assert_called_once_with(
        height=1.78, weight=80.0, bike_type="Road", position="Hoods",
        days=90, force_strava_refresh=True, auth_user_id="rider-owner",
    )
    active = app.session_state["vibe_rider"]
    assert active["critical_power"] == 280
    assert active["w_prime"] == 24000
    assert active["power_source"] == "strava"
    assert active["strava_athlete_id"] == "42"
    assert active["weight"] == expected_weight
    assert app.number_input(key="rider_general_weight").value == expected_weight
    assert app.session_state["vibe_pending_rider_weight"] is None
    assert app.session_state["vibe_rider_obj"] is imported
    assert app.session_state["vibe_optimization_results"] == {"old": True}
    assert app.session_state["vibe_segmentation_applied"]
    assert app.session_state["auth_user_id"] == "rider-owner"

    _run_rider(app)
    app.number_input(key="rider_general_weight").set_value(76.0)
    _run_rider(app)
    _run_rider(app)
    assert not list(app.exception)
    assert app.session_state["vibe_rider"]["weight"] == 76.0
    assert app.number_input(key="rider_general_weight").value == 76.0
    rider_factory.assert_called_once()
    verify.assert_not_called()
    assert {call.args for call in cache.call_args_list} == {("42",)}
