import os
from unittest.mock import patch

import pytest
from dotenv import load_dotenv
from streamlit.testing.v1 import AppTest

import app.rider as rider_module
from app.db import connect
from pages_vibe.tabs import _charts

load_dotenv()

# These tests mutate rider tables, so they require an ISOLATED throwaway database
# (e.g. `createdb pace_yourself_test`), not the development database.
TEST_DB_URL = os.getenv("PACE_TEST_DATABASE_URL")
TEST_RIDER_IDS = ["42", "77", "88", "99", "100"]


def _cleanup():
    with connect(TEST_DB_URL) as conn:
        conn.execute("DELETE FROM best_efforts WHERE rider_id = ANY(%s)", (TEST_RIDER_IDS,))
        conn.execute("DELETE FROM rider_info WHERE rider_id = ANY(%s)", (TEST_RIDER_IDS,))


@pytest.fixture
def rider_db(monkeypatch):
    if not TEST_DB_URL:
        pytest.skip(
            "Set PACE_TEST_DATABASE_URL to an isolated throwaway database to run "
            "rider cache tests."
        )
    monkeypatch.setenv("DATABASE_URL", TEST_DB_URL)
    rider_module.initialize_rider_database()
    _cleanup()
    yield
    _cleanup()


RIDER_APP = '''
from pages_vibe.tabs.state import init_session_state
from pages_vibe.tabs.tab_rider import render

init_session_state()
render()
'''


def test_profile_verification_does_not_claim_power_refresh(rider_db):
    cached = rider_module.save_strava_profile({
        'id': 77,
        'firstname': 'Profile',
        'lastname': 'Only',
        'weight': 68.2,
    })

    assert cached['athlete_first_name'] == 'Profile'
    assert cached['athlete_last_name'] == 'Only'
    assert cached['strava_weight'] == 68.2
    assert cached['strava_profile_checked_at'] is not None
    assert cached['strava_last_synced_at'] is None
    assert cached['best_efforts'] == {}


def test_forced_refresh_bypasses_cache_and_stores_hour_power(rider_db):
    rider_module.save_strava_profile({
        'id': 88,
        'firstname': 'Old',
        'lastname': 'Cache',
    })
    efforts = {
        30: 700.0,
        60: 500.0,
        300: 350.0,
        1200: 290.0,
        3600: 255.0,
    }
    profile = {
        'id': 88,
        'firstname': 'Fresh',
        'lastname': 'Athlete',
        'weight': 72.5,
    }

    with patch.object(rider_module, 'get_athlete_profile', return_value=profile), \
         patch.object(rider_module, 'get_activities', return_value=[{'id': 1}]), \
         patch.object(rider_module, 'calculate_critical_power', return_value=efforts):
        rider = rider_module.Rider(
            height=1.78,
            weight=74.0,
            days=90,
            force_strava_refresh=True,
        )

    cached = rider_module.get_cached_strava_rider('88')
    assert rider.athlete_first_name == 'Fresh'
    assert rider.best_efforts[3600] == 255.0
    assert cached['best_efforts'][3600] == 255.0
    assert cached['effort_source'] == 'strava'
    assert cached['strava_lookback_days'] == 90
    assert cached['strava_last_synced_at'] is not None


def test_cached_identity_and_key_pbs_render_without_api_call(rider_db):
    rider_module.save_strava_profile({
        'id': 99,
        'firstname': 'Cached',
        'lastname': 'Rider',
    })
    with connect(TEST_DB_URL) as conn:
        for duration, power in [(60, 500.0), (300, 350.0), (1200, 290.0), (3600, 255.0)]:
            conn.execute(
                """INSERT INTO best_efforts
                   (rider_id, duration, power, source, refreshed_at)
                   VALUES (%s, %s, %s, 'strava', '2025-02-03T04:05:06+00:00')""",
                ('99', duration, power),
            )
        conn.execute(
            """UPDATE rider_info
               SET strava_last_synced_at = '2025-02-03T04:05:06+00:00',
                   strava_lookback_days = 90
               WHERE rider_id = '99'"""
        )

    with patch(
            'pages_vibe.tabs.tab_rider.get_athlete_profile',
            side_effect=AssertionError('ordinary render called Strava')):
        app = AppTest.from_string(RIDER_APP).run()

    assert not list(app.exception)
    assert app.session_state['rider_power_source_mode'] == 'Strava Import'
    expected_cp, expected_w_prime = rider_module.fit_power_profile({
        60: 500.0, 300: 350.0, 1200: 290.0, 3600: 255.0,
    })
    active_rider = app.session_state['vibe_rider']
    assert active_rider['critical_power'] == round(expected_cp)
    assert active_rider['w_prime'] == round(expected_w_prime)
    assert active_rider['critical_power'] != 250
    assert active_rider['power_source'] == 'strava'
    assert any(item.value == '### Cached Rider' for item in app.markdown)
    metrics = {metric.label: metric.value for metric in app.metric}
    assert metrics['1 min'] == '500 W'
    assert metrics['5 min'] == '350 W'
    assert metrics['20 min'] == '290 W'
    assert metrics['60 min'] == '255 W'


def test_strava_power_chart_includes_athlete_and_cached_efforts():
    efforts = {60: 500.0, 300: 350.0, 1200: 290.0, 3600: 255.0}

    figure = _charts.build_power_duration_curve(
        250,
        20000,
        best_efforts=efforts,
        athlete_label='Cached Rider · Strava #99',
        provenance='Cached best efforts · Refreshed Feb 03, 2025',
    )

    assert len(figure.data) == 2
    assert figure.data[1].name == 'Strava best efforts'
    assert list(figure.data[1].x) == [60, 300, 1200, 3600]
    assert list(figure.data[1].y) == [500.0, 350.0, 290.0, 255.0]
    assert 'Cached Rider · Strava #99' in figure.layout.title.text
    assert 'Refreshed Feb 03, 2025' in figure.layout.title.text
    assert list(figure.layout.yaxis.range) == [0, 1500]


def test_cp_fit_uses_sustained_efforts_not_sprint_records():
    sustained = {120: 486.325, 300: 403.98, 1200: 365.9125, 1800: 361.1578}
    modest_sprints = {30: 664.5, 60: 647.3, **sustained}
    exceptional_sprints = {30: 1400.0, 60: 900.0, **sustained}

    modest_cp, modest_w_prime = rider_module.fit_power_profile(modest_sprints)
    exceptional_cp, exceptional_w_prime = rider_module.fit_power_profile(
        exceptional_sprints)

    assert modest_cp == pytest.approx(351.887, abs=0.01)
    assert modest_cp < min(sustained.values())
    assert exceptional_cp == pytest.approx(modest_cp)
    assert exceptional_w_prime == pytest.approx(modest_w_prime)


def test_cp_fit_requires_two_sustained_efforts():
    assert rider_module.fit_power_profile({30: 900.0, 60: 650.0}) is None


def test_account_verification_preserves_stable_optimization_results(rider_db):
    app = AppTest.from_string(RIDER_APP)
    app.session_state['vibe_rider'] = {
        'height': 1.78,
        'weight': 80.0,
        'bike_type': 'Road',
        'bike_mass': 8.5,
        'position': 'Hoods',
        'critical_power': 250,
        'w_prime': 20000,
        'cda': 0.356,
        'crr': 0.004,
        'strava_athlete_id': None,
        'strava_name': None,
        'strava_weight': None,
        'strava_last_synced_at': None,
        'strava_lookback_days': None,
        'best_efforts': {},
        'power_source': None,
    }
    app.session_state['vibe_optimization_results'] = {'sentinel': True}
    profile = {'id': 100, 'firstname': 'Verified', 'lastname': 'Rider'}

    with patch(
            'pages_vibe.tabs.tab_rider.get_athlete_profile',
            return_value=profile):
        app.run()
        # AppTest models all button groups as multi-value even when the
        # runtime widget is single-select.
        app.get('button_group')[0].set_value(['Rider Type'])
        next(button for button in app.button
             if button.label == 'Verify Strava Account').click().run()

    assert not list(app.exception)
    assert app.session_state['vibe_optimization_results'] == {'sentinel': True}
    assert app.session_state['vibe_rider']['strava_athlete_id'] == '100'
    assert app.session_state['rider_power_source_mode'] == 'Strava Import'
    assert any(item.value == '### Verified Rider' for item in app.markdown)
