import sympy as sp
import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import root_scalar, lsq_linear
import os, sys
import unittest
import traceback
import json
from datetime import datetime as dt_datetime, timezone
from dotenv import load_dotenv
load_dotenv()
app_path = os.getenv('APP_PATH')
if app_path:
    sys.path.append(app_path)

from app.helpers import mps_to_mph  # Assuming this is defined in the helpers module
from app.strava_calls import *
from app.db import connect


def _to_dt(value):
    """Coerce an ISO string (or None/datetime) to datetime for TIMESTAMPTZ params."""
    if value is None or isinstance(value, dt_datetime):
        return value
    try:
        return dt_datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _iso(value):
    """Render a datetime as an ISO string, preserving the prior string contract."""
    return value.isoformat() if isinstance(value, dt_datetime) else value


# rider_id holds the application user_id; ownership is scoped by that value
# rather than a DDL foreign key so this store initializes independently.
RIDER_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS rider_info (
    rider_id TEXT PRIMARY KEY,
    strava_athlete_id TEXT UNIQUE,
    height DOUBLE PRECISION,
    weight DOUBLE PRECISION,
    bike_type TEXT,
    position TEXT,
    "CdA" DOUBLE PRECISION,
    critical_power DOUBLE PRECISION,
    "WTank" DOUBLE PRECISION,
    athlete_first_name TEXT,
    athlete_last_name TEXT,
    athlete_profile_url TEXT,
    strava_weight DOUBLE PRECISION,
    strava_profile_checked_at TIMESTAMPTZ,
    strava_last_synced_at TIMESTAMPTZ,
    strava_lookback_days INTEGER,
    strava_profile_json TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS best_efforts (
    rider_id TEXT,
    duration INTEGER,
    power DOUBLE PRECISION,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source TEXT DEFAULT 'unknown',
    refreshed_at TIMESTAMPTZ,
    PRIMARY KEY (rider_id, duration)
);

CREATE INDEX IF NOT EXISTS idx_best_efforts_rider ON best_efforts(rider_id);
"""


def fit_power_profile(best_efforts):
    """Fit CP and W' from at least two valid power-duration efforts."""
    efforts = {
        int(duration): float(power)
        for duration, power in (best_efforts or {}).items()
        if duration and power and float(duration) > 0 and float(power) > 0
    }
    if len(efforts) < 2:
        return None
    sustained_efforts = {
        duration: power for duration, power in efforts.items()
        if (WTankCalculator.CP_FIT_MIN_DURATION
            <= duration <= WTankCalculator.CP_FIT_MAX_DURATION)
    }
    if len(sustained_efforts) < 2:
        return None

    calculator = WTankCalculator(best_efforts=sustained_efforts)
    w_prime = float(calculator.calculate_w_tank())
    critical_power = float(calculator.critical_power)
    if not np.isfinite(critical_power) or not np.isfinite(w_prime):
        return None
    if critical_power <= 0 or w_prime <= 0:
        return None
    return critical_power, w_prime


def initialize_rider_database():
    """Ensure the rider tables exist (PostgreSQL)."""
    with connect() as conn:
        conn.execute(RIDER_SCHEMA_SQL)


def get_cached_strava_rider(rider_id=None):
    """Return cached Strava identity, provenance, and best efforts."""
    initialize_rider_database()
    with connect() as conn:
        if rider_id:
            row = conn.execute(
                '''SELECT * FROM rider_info
                   WHERE rider_id = %s AND strava_athlete_id IS NOT NULL''',
                (str(rider_id),),
            ).fetchone()
        else:
            row = conn.execute(
                '''SELECT * FROM rider_info
                   WHERE strava_athlete_id IS NOT NULL
                   ORDER BY COALESCE(strava_last_synced_at, updated_at) DESC
                   LIMIT 1'''
            ).fetchone()
        if row is None:
            return None

        profile = {key: _iso(value) for key, value in dict(row).items()}
        effort_rows = conn.execute(
            '''SELECT duration, power, source, refreshed_at
               FROM best_efforts WHERE rider_id = %s ORDER BY duration''',
            (row['rider_id'],),
        ).fetchall()
    profile['best_efforts'] = {
        effort['duration']: effort['power'] for effort in effort_rows
    }
    profile['effort_source'] = (
        effort_rows[0]['source'] if effort_rows else None)
    profile['efforts_refreshed_at'] = (
        _iso(effort_rows[0]['refreshed_at']) if effort_rows else None)
    return profile


def save_strava_profile(profile):
    """Upsert authenticated athlete identity without refreshing power data."""
    athlete_id = profile.get('id') if profile else None
    if not athlete_id:
        raise ValueError('Strava athlete profile did not include an ID.')

    initialize_rider_database()
    checked_at = dt_datetime.now(timezone.utc)
    profile_weight = profile.get('weight')
    profile_weight = (
        float(profile_weight) if profile_weight not in (None, 0) else None)
    profile_url = profile.get('profile_medium') or profile.get('profile')
    with connect() as conn:
        conn.execute(
            '''INSERT INTO rider_info (
                   rider_id, strava_athlete_id, athlete_first_name,
                   athlete_last_name, athlete_profile_url, strava_weight,
                   strava_profile_checked_at, strava_profile_json, updated_at
               ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
               ON CONFLICT(rider_id) DO UPDATE SET
                   strava_athlete_id = EXCLUDED.strava_athlete_id,
                   athlete_first_name = EXCLUDED.athlete_first_name,
                   athlete_last_name = EXCLUDED.athlete_last_name,
                   athlete_profile_url = EXCLUDED.athlete_profile_url,
                   strava_weight = EXCLUDED.strava_weight,
                   strava_profile_checked_at = EXCLUDED.strava_profile_checked_at,
                   strava_profile_json = EXCLUDED.strava_profile_json,
                   updated_at = NOW()''',
            (
                str(athlete_id), str(athlete_id), profile.get('firstname'),
                profile.get('lastname'), profile_url, profile_weight, checked_at,
                json.dumps(profile),
            ),
        )
    return get_cached_strava_rider(str(athlete_id))

def get_all_riders():
    """Get information about all riders in the database."""
    try:
        initialize_rider_database()
        with connect() as conn:
            rows = conn.execute(
                '''SELECT rider_id, strava_athlete_id, height, weight, bike_type,
                          position, critical_power, "WTank", created_at, updated_at
                   FROM rider_info ORDER BY updated_at DESC'''
            ).fetchall()

        riders = []
        for row in rows:
            rider_dict = {
                'rider_id': row['rider_id'],
                'strava_athlete_id': row['strava_athlete_id'],
                'height': row['height'],
                'weight': row['weight'],
                'bike_type': row['bike_type'],
                'position': row['position'],
                'critical_power': row['critical_power'],
                'WTank': row['WTank'],
                'created_at': _iso(row['created_at']),
                'updated_at': _iso(row['updated_at']),
            }
            riders.append(rider_dict)
        return riders
    except Exception as e:
        print(f"Database error: {e}")
        return []

class Rider:
    """
    A class to represent a cyclist and estimate their aerodynamic drag coefficient (CdA).
    
    Attributes:
        height (float): Height of the rider in meters.
        weight (float): Weight of the rider in kilograms.
        bike_type (str): Type of bike (e.g., "Road", "TT", "Gravel", "MTB").
        position (str): Riding position (e.g., "Hoods", "Drops", "Aero").
        CdA (float): Estimated aerodynamic drag coefficient.
        critical_power (float): Critical power in watts.
        WTank (float): Estimated WTank in joules.
        best_efforts (dict): Dictionary of best effort values.
    """

    # Default CdA values for different bike types and positions (m^2)
    BIKE_TYPE_CDA = {
        "Road": {"Hoods": 0.35, "Drops": 0.33, "Aero": 0.30},
        "TT": {"Aero": 0.22},
        "Gravel": {"Hoods": 0.38, "Drops": 0.36},
        "MTB": {"Flat": 0.40},
    }

    def __init__(self, height, weight, bike_type="Road", position="Hoods", 
                 rider_type=None, critical_power=None, 
                 best_efforts=None, 
                 days=60, rider_id=None, force_strava_refresh=False,
                 auth_user_id=None):
        """
        Initialize a Rider with critical power and W' (WTank) calculated from one of three methods:
        
        METHOD A - Profile Estimation (rider_type + critical_power):
            If you know your CP and rider type, W' is estimated from typical profiles.
            Example: Rider(height=1.80, weight=75, rider_type="all_rounder", critical_power=250)
            
        METHOD B - Manual Best Efforts (best_efforts dict):
            Provide your own power-duration data for curve fitting.
            Example: Rider(height=1.80, weight=75, best_efforts={60: 400, 300: 320, 1200: 270})
            
        METHOD C - Strava API (default when no power data provided):
            Automatically fetches your best efforts from Strava over the last N days.
            Requires Strava authentication. Results are cached in the database.
            Example: Rider(height=1.80, weight=75, days=90)
        
        Args:
            height: Rider height in meters
            weight: Rider body weight in kg
            bike_type: "Road", "TT", "Gravel", or "MTB"
            position: "Hoods", "Drops", "Aero", or "Flat"
            rider_type: For Method A - "time_trialist", "sprinter", or "all_rounder"
            critical_power: For Method A - your critical power in watts
            best_efforts: For Method B - dict of {duration_seconds: power_watts}
            days: For Method C - number of days to look back in Strava (default 60)
            rider_id: Optional - used to cache/retrieve data from local database
            force_strava_refresh: Bypass cached efforts and fetch Strava now
            auth_user_id: Application user whose Strava token may be used
        """
        # Core physical attributes
        self.height = height
        self.weight = weight
        self.bike_type = bike_type
        self.position = position
        self.CdA = self.estimate_CdA()
        
        # Power attributes - will be populated by one of the methods below
        self.critical_power = critical_power
        self.WTank = None
        self.best_efforts = None
        self.WTank_calculator = None
        
        # Rider identification
        self.rider_id = rider_id
        self.auth_user_id = auth_user_id
        self.strava_athlete_id = None
        self.athlete_profile = {}
        self.athlete_first_name = None
        self.athlete_last_name = None
        self.athlete_profile_url = None
        self.strava_weight = None
        self.strava_last_synced_at = None
        self.strava_lookback_days = None
        self.best_efforts_source = None
        
        # ============================================================
        # METHOD A: Profile-based estimation (rider_type + critical_power)
        # ============================================================
        if rider_type and critical_power:
            print(f"Method A: Estimating W' from rider profile ({rider_type}) and CP ({critical_power}W)")
            self.WTank_calculator = WTankCalculator(rider_type=rider_type, critical_power=critical_power)
            self.WTank = self.WTank_calculator.calculate_w_tank()
            self.critical_power = self.WTank_calculator.critical_power
            self.best_efforts = self.WTank_calculator.best_efforts  # Store the estimated best efforts
            return  # Done - no need to check other methods
        
        # ============================================================
        # METHOD B: Manual best efforts provided
        # ============================================================
        if best_efforts:
            print(f"Method B: Calculating CP and W' from provided best efforts")
            self.best_efforts = best_efforts
            self.WTank_calculator = WTankCalculator(best_efforts=best_efforts)
            self.WTank = self.WTank_calculator.calculate_w_tank()
            self.critical_power = self.WTank_calculator.critical_power
            return  # Done
        
        # ============================================================
        # METHOD C: Database lookup or Strava API
        # ============================================================
        # First, try to get rider_id from Strava if not provided
        if not self.rider_id:
            try:
                self._apply_strava_profile(get_athlete_profile(
                    user_id=self.auth_user_id))
                self.rider_id = str(self.strava_athlete_id)
                print(f"Got Strava athlete ID: {self.rider_id}")
            except Exception as e:
                print(f"No Strava authentication available: {e}")
                print("Tip: Provide rider_type + critical_power, or best_efforts dict")
                return  # Can't proceed without identification
        
        # Check if we have cached data in the database
        existing_rider_ids = self.get_existing_rider_ids()
        
        if self.rider_id in existing_rider_ids and not force_strava_refresh:
            # Try to load from database
            if self.load_rider_info_from_db():
                print(f"Method C: Loaded cached rider data for ID: {self.rider_id}")
                if self.critical_power and self.WTank:
                    self.WTank_calculator = WTankCalculator(critical_power=self.critical_power)
                    # Also load best efforts if available
                    self.load_best_efforts_from_db()
                    return  # Done - loaded from cache
            
            # If rider_info didn't have CP/WTank, try loading best_efforts
            self.load_best_efforts_from_db()
            if self.best_efforts:
                print(f"Loaded cached best efforts, recalculating CP and W'")
                self.WTank_calculator = WTankCalculator(best_efforts=self.best_efforts)
                self.WTank = self.WTank_calculator.calculate_w_tank()
                self.critical_power = self.WTank_calculator.critical_power
                return  # Done
        
        # No cached data - fetch from Strava API
        try:
            print(f"Method C: Fetching best efforts from Strava (last {days} days)...")
            if not self.athlete_profile:
                self._apply_strava_profile(get_athlete_profile(
                    user_id=self.auth_user_id))
            if not self.rider_id:
                self.rider_id = str(self.strava_athlete_id)
            
            self.best_efforts = self.get_best_power_from_strava(days)
            self.best_efforts = {
                duration: power for duration, power in self.best_efforts.items()
                if power and power > 0
            }
            
            if len(self.best_efforts) >= 2:
                self.best_efforts_source = 'strava'
                self.strava_lookback_days = days
                self.strava_last_synced_at = dt_datetime.now(timezone.utc).isoformat()
                self.WTank_calculator = WTankCalculator(best_efforts=self.best_efforts)
                self.WTank = self.WTank_calculator.calculate_w_tank()
                self.critical_power = self.WTank_calculator.critical_power
                
                # Cache for future use
                self.save_best_efforts_to_db()
                print(f"Calculated and cached: CP={self.critical_power:.0f}W, W'={self.WTank:.0f}J")
            else:
                print("Fewer than two usable power efforts found in Strava activities")
                
        except Exception as e:
            print(f"Error fetching from Strava: {e}")
            print("Tip: Provide rider_type + critical_power, or best_efforts dict")

    def estimate_CdA(self):
        """
        Estimate the aerodynamic drag coefficient (CdA) based on rider and bike factors.

        Returns:
            float: Estimated CdA value in m^2.
        """
        # Get baseline CdA based on bike type and position
        base_CdA = self.BIKE_TYPE_CDA.get(self.bike_type, {}).get(self.position, 0.35)

        # Adjustments based on height and weight (optional scaling factors)
        # Taller riders tend to have higher CdA due to larger frontal area
        height_factor = self.height / 1.75  # Normalize to average rider height (1.75m)

        # Adjust CdA for height, ensuring adjustments are reasonable
        adjusted_CdA = base_CdA * height_factor

        return round(adjusted_CdA, 3)

    def _apply_strava_profile(self, profile):
        """Attach authenticated Strava identity metadata to this rider."""
        self.athlete_profile = profile or {}
        self.strava_athlete_id = self.athlete_profile.get('id')
        self.athlete_first_name = self.athlete_profile.get('firstname')
        self.athlete_last_name = self.athlete_profile.get('lastname')
        self.athlete_profile_url = (
            self.athlete_profile.get('profile_medium')
            or self.athlete_profile.get('profile')
        )
        profile_weight = self.athlete_profile.get('weight')
        self.strava_weight = (
            float(profile_weight) if profile_weight not in (None, 0) else None)

    def calculate_w_tank_from_profile(self, rider_type, critical_power):
        """
        Calculate WTank based on rider type and critical power.

        Args:
            rider_type (str): Type of rider (e.g., "time_trialist", "sprinter", "all_rounder").
            critical_power (float): Critical power in watts.

        Returns:
            float: Estimated WTank in joules.
        """
        wt_calculator = WTankCalculator(rider_type=rider_type, critical_power=critical_power)
        return wt_calculator.calculate_w_tank()

    def get_best_power_from_strava(self, days=30):
        """
        Calculate WTank using curve fitting based on activities from the past `days` days.

        Args:
            days (int): Number of days to look back for activities.

        Returns:
            dict of best efforts
        """
        activities = get_activities(days, user_id=self.auth_user_id)
        durations = [30, 60, 120, 300, 1200, 1800, 3600]
        return calculate_critical_power(
            activities, durations, user_id=self.auth_user_id)

    def save_best_efforts_to_db(self):
        """Save best efforts to a database."""
        if not hasattr(self, 'rider_id') or not self.rider_id:
            raise ValueError("Rider ID must be provided to save best efforts to the database.")

        initialize_rider_database()
        synced_at = _to_dt(self.strava_last_synced_at)
        with connect() as conn:
            # Save best efforts
            if hasattr(self, 'best_efforts') and self.best_efforts:
                source = self.best_efforts_source or 'unknown'
                for duration, power in self.best_efforts.items():
                    conn.execute(
                        '''INSERT INTO best_efforts
                           (rider_id, duration, power, source, refreshed_at)
                           VALUES (%s, %s, %s, %s, %s)
                           ON CONFLICT(rider_id, duration) DO UPDATE SET
                               power = EXCLUDED.power,
                               source = EXCLUDED.source,
                               refreshed_at = EXCLUDED.refreshed_at''',
                        (self.rider_id, duration, power, source, synced_at),
                    )

            # Save rider info
            strava_id = getattr(self, 'strava_athlete_id', None)
            conn.execute(
                '''INSERT INTO rider_info (
                       rider_id, strava_athlete_id, height, weight, bike_type,
                       position, "CdA", critical_power, "WTank", athlete_first_name,
                       athlete_last_name, athlete_profile_url, strava_weight,
                       strava_profile_checked_at, strava_last_synced_at,
                       strava_lookback_days,
                       strava_profile_json, updated_at
                   ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                             NOW())
                   ON CONFLICT(rider_id) DO UPDATE SET
                       strava_athlete_id = EXCLUDED.strava_athlete_id,
                       height = EXCLUDED.height,
                       weight = EXCLUDED.weight,
                       bike_type = EXCLUDED.bike_type,
                       position = EXCLUDED.position,
                       "CdA" = EXCLUDED."CdA",
                       critical_power = EXCLUDED.critical_power,
                       "WTank" = EXCLUDED."WTank",
                       athlete_first_name = EXCLUDED.athlete_first_name,
                       athlete_last_name = EXCLUDED.athlete_last_name,
                       athlete_profile_url = EXCLUDED.athlete_profile_url,
                       strava_weight = EXCLUDED.strava_weight,
                       strava_profile_checked_at = EXCLUDED.strava_profile_checked_at,
                       strava_last_synced_at = EXCLUDED.strava_last_synced_at,
                       strava_lookback_days = EXCLUDED.strava_lookback_days,
                       strava_profile_json = EXCLUDED.strava_profile_json,
                       updated_at = NOW()''',
                (
                    self.rider_id, strava_id, self.height, self.weight,
                    self.bike_type, self.position, self.CdA,
                    self.critical_power, self.WTank, self.athlete_first_name,
                    self.athlete_last_name, self.athlete_profile_url,
                    self.strava_weight, synced_at,
                    synced_at,
                    self.strava_lookback_days,
                    json.dumps(self.athlete_profile) if self.athlete_profile else None,
                ),
            )

    def load_best_efforts_from_db(self):
        """Load best efforts from a database."""
        if not hasattr(self, 'rider_id') or not self.rider_id:
            raise ValueError("Rider ID must be provided to load best efforts from the database.")

        with connect() as conn:
            rows = conn.execute(
                'SELECT duration, power FROM best_efforts WHERE rider_id = %s',
                (self.rider_id,),
            ).fetchall()

        self.best_efforts = {row['duration']: row['power'] for row in rows}

    def load_rider_info_from_db(self):
        """Load rider information from the database."""
        if not hasattr(self, 'rider_id') or not self.rider_id:
            raise ValueError("Rider ID must be provided to load rider info from the database.")

        initialize_rider_database()
        with connect() as conn:
            row = conn.execute(
                '''SELECT strava_athlete_id, height, weight, bike_type,
                          position, "CdA", critical_power, "WTank",
                          athlete_first_name, athlete_last_name,
                          athlete_profile_url, strava_weight,
                          strava_profile_checked_at, strava_last_synced_at,
                          strava_lookback_days,
                          strava_profile_json
                   FROM rider_info WHERE rider_id = %s''',
                (self.rider_id,),
            ).fetchone()

        if row:
            self.strava_athlete_id = row['strava_athlete_id']
            self.height = row['height']
            self.weight = row['weight']
            self.bike_type = row['bike_type']
            self.position = row['position']
            self.CdA = row['CdA']
            self.critical_power = row['critical_power']
            self.WTank = row['WTank']
            self.athlete_first_name = row['athlete_first_name']
            self.athlete_last_name = row['athlete_last_name']
            self.athlete_profile_url = row['athlete_profile_url']
            self.strava_weight = row['strava_weight']
            self.strava_last_synced_at = _iso(row['strava_last_synced_at'])
            self.strava_lookback_days = row['strava_lookback_days']
            profile_json = row['strava_profile_json']
            self.athlete_profile = json.loads(profile_json) if profile_json else {}
            self.best_efforts_source = 'strava'
            return True
        return False

    def get_existing_rider_ids(self):
        """Get all existing rider IDs from the database."""
        try:
            initialize_rider_database()
            with connect() as conn:
                rows = conn.execute('SELECT rider_id FROM rider_info').fetchall()
            return [row['rider_id'] for row in rows]
        except Exception:
            return []

    @staticmethod
    def create_rider_id_from_strava():
        """Create a rider ID from Strava athlete information."""
        try:
            athlete_id = get_athlete_id()
            return str(athlete_id)
        except Exception as e:
            print(f"Failed to get Strava athlete ID: {e}")
            return None

    def update_height(self, height):
        """Update the height of the rider and recalculate CdA."""
        self.height = height
        self.CdA = self.estimate_CdA()
        if hasattr(self, 'rider_id') and self.rider_id:
            self.save_best_efforts_to_db()  # This also updates rider_info

    def update_weight(self, weight):
        """Update the weight of the rider."""
        self.weight = weight
        if hasattr(self, 'rider_id') and self.rider_id:
            self.save_best_efforts_to_db()  # This also updates rider_info

    def update_bike_type(self, bike_type):
        """Update the bike type and recalculate CdA."""
        self.bike_type = bike_type
        self.CdA = self.estimate_CdA()
        if hasattr(self, 'rider_id') and self.rider_id:
            self.save_best_efforts_to_db()  # This also updates rider_info

    def update_position(self, position):
        """Update the riding position and recalculate CdA."""
        self.position = position
        self.CdA = self.estimate_CdA()
        if hasattr(self, 'rider_id') and self.rider_id:
            self.save_best_efforts_to_db()  # This also updates rider_info

    def __str__(self):
        """String representation of the Rider instance."""
        wtank_display = f"{self.WTank/1000:.1f} kJ" if self.WTank is not None else "Not calculated"
        cp_display = f"{self.critical_power} W" if self.critical_power is not None else "Not calculated"
        return (f"Rider: {self.height}m, {self.weight}kg, Bike: {self.bike_type}, "
                f"Position: {self.position}, Estimated CdA: {self.CdA} m^2, "
                f"Critical Power: {cp_display}, WTank: {wtank_display}")

class WTankCalculator:
    CP_FIT_MIN_DURATION = 120
    CP_FIT_MAX_DURATION = 1800

    def __init__(self, rider_type=None, critical_power=None, best_efforts=None):
        """
        Initialize the WTankCalculator class.

        :param rider_type: str, one of ['time_trialist', 'sprinter', 'all_rounder']
        :param critical_power: float, critical power in watts.
        :param best_efforts: dict, best power outputs for durations in seconds.
                             e.g., {60: 400, 300: 350, 600: 330, 1200: 310, 1800: 290}
        """
        self.rider_type = rider_type
        self.critical_power = critical_power
        self.best_efforts = best_efforts if best_efforts else {}

    def _populate_best_efforts(self):
        """
        Populate estimated best efforts if not provided, based on rider type and critical power.
        """
        if not self.critical_power:
            raise ValueError("Critical power must be provided to estimate best efforts.")

        # Base multipliers for power at different durations (relative to critical power)
        # Extended to 4 hours using endurance decay model (k ≈ 0.05)
        if self.rider_type == "time_trialist":
            multipliers = {
                60: 1.4, 300: 1.2, 600: 1.1, 1200: 1.05, 1800: 1.02, 3600: 1.0,
                7200: 0.965, 10800: 0.945, 14400: 0.93,  # 2h, 3h, 4h
            }
        elif self.rider_type == "sprinter":
            multipliers = {
                60: 1.8, 300: 1.4, 600: 1.2, 1200: 1.1, 1800: 1.05, 3600: 1.0,
                7200: 0.960, 10800: 0.935, 14400: 0.915,
            }
        elif self.rider_type == "all_rounder":
            multipliers = {
                60: 1.6, 300: 1.3, 600: 1.15, 1200: 1.08, 1800: 1.03, 3600: 1.0,
                7200: 0.963, 10800: 0.940, 14400: 0.923,
            }
        else:
            raise ValueError("Invalid rider type. Choose from 'time_trialist', 'sprinter', or 'all_rounder'.")

        # Populate best efforts based on multipliers
        for duration, multiplier in multipliers.items():
            self.best_efforts[duration] = self.critical_power * multiplier

    def _estimate_w_tank_from_profile(self):
        """Estimate W' based on rider type and critical power."""
        _ = self._estimate_w_tank_from_curve() #do this so we populate the popt variable
        
        if self.critical_power is None:
            raise ValueError("Critical power must be provided to estimate W' from profile.")
            
        if self.rider_type == "time_trialist":
            return 10_000 + 0.5 * self.critical_power
        elif self.rider_type == "sprinter":
            return 25_000 + 0.7 * self.critical_power
        elif self.rider_type == "all_rounder":
            return 15_000 + 0.6 * self.critical_power
        else:
            raise ValueError("Invalid rider type. Choose from 'time_trialist', 'sprinter', or 'all_rounder'.")
        
        
        

    def _power_duration_model(self, t, CP, W_prime):
        """
        Power-duration model for curve fitting: P(t) = CP + W' / t
        Used for durations up to ~1 hour to estimate CP and W'.
        """
        return CP + W_prime / (t)

    @staticmethod
    def piecewise_power_duration(t, CP, W_prime, k=0.05):
        """Piecewise power-duration model valid from seconds to 4+ hours.

        For t ≤ 3600s:  P(t) = CP + W'/t       (classic CP model)
        For t > 3600s:   P(t) = CP × (3600/t)^k (endurance decay)

        The endurance exponent *k* captures the slow decline in sustainable
        power beyond one hour due to glycogen depletion, thermal drift,
        and central fatigue.  Typical values:
          k ≈ 0.04  (well-trained endurance athletes)
          k ≈ 0.05  (all-rounders)
          k ≈ 0.07  (pure sprinters / less endurance-adapted)

        The function is continuous at t=3600: both pieces give P=CP.

        Args:
            t: Duration in seconds (scalar or array).
            CP: Critical power in watts.
            W_prime: Anaerobic capacity (W') in joules.
            k: Endurance fatigue exponent (default 0.05).

        Returns:
            Power in watts (same shape as t).
        """
        t = np.asarray(t, dtype=float)
        scalar = t.ndim == 0
        t = np.atleast_1d(t)

        power = np.where(
            t <= 3600,
            CP + W_prime / np.maximum(t, 1.0),
            CP * (3600.0 / np.maximum(t, 1.0)) ** k,
        )

        return float(power[0]) if scalar else power

    def _estimate_w_tank_from_curve(self):
        """Estimate W' based on the modified power-duration curve.
        
        Fit CP+W'/t to sustained efforts from 2–30 minutes. Shorter efforts are
        dominated by neuromuscular/anaerobic power and can push the asymptote
        above observed long-duration power. Longer efforts follow the endurance
        decay model and should not influence CP/W' estimation.
        """
        if not self.best_efforts:
            self._populate_best_efforts()  # Populate best efforts if not provided

        durations = np.array(list(self.best_efforts.keys()))
        powers = np.array(list(self.best_efforts.values()))

        mask = (
            (durations >= self.CP_FIT_MIN_DURATION)
            & (durations <= self.CP_FIT_MAX_DURATION)
        )
        fit_durations = durations[mask]
        fit_powers = powers[mask]

        if len(fit_durations) < 2:
            raise ValueError(
                "At least two best efforts between 2 and 30 minutes are "
                "required to estimate CP and W'.")

        cp_ceiling = np.nextafter(float(np.min(fit_powers)), 0.0)
        design = np.column_stack((
            np.ones_like(fit_durations, dtype=float),
            1.0 / fit_durations,
        ))
        result = lsq_linear(
            design,
            fit_powers,
            bounds=((0.0, 0.0), (cp_ceiling, np.inf)),
        )
        if not result.success:
            raise ValueError(f"CP/W' fit failed: {result.message}")
        popt = result.x
        self.popt = popt  # Store the fitted parameters (CP, W_prime)
        estimated_cp, w_prime = popt

        # Store critical power if not provided
        if self.critical_power is None:
            self.critical_power = estimated_cp

        return w_prime

    def calculate_w_tank(self):
        """Calculate the WTank based on available data."""
        if self.best_efforts:
            self.w_tank = self._estimate_w_tank_from_curve()
        elif self.rider_type and self.critical_power:
            self.w_tank = self._estimate_w_tank_from_profile()
        else:
            raise ValueError("Provide either best efforts data or rider profile and critical power.")

        return self.w_tank

    def plot_power_duration_curve(self):
        """Plot the piecewise power-duration curve (short + endurance)."""
        if not self.best_efforts:
            self._populate_best_efforts()  # Populate best efforts if not provided

        durations = np.array(list(self.best_efforts.keys()))
        powers = np.array(list(self.best_efforts.values()))

        # Unpack the fitted parameters
        estimated_cp, w_prime = self.popt

        # Generate a smooth curve from shortest effort out to 4 hours
        max_t = max(max(durations), 14400)  # At least 4 hours
        t_fit = np.linspace(min(durations), max_t, 400)

        # Use the piecewise model for the full range
        p_fit = self.piecewise_power_duration(t_fit, estimated_cp, w_prime)

        # Create the plot
        fig, ax = plt.subplots(figsize=(7, 4))
        ax.scatter(durations / 60, powers, color='red', zorder=5,
                   label='Best Efforts Data')
        ax.plot(t_fit / 60, p_fit,
                label=f'Piecewise Model\nCP={estimated_cp:.0f} W, W\'={w_prime:.0f} J')

        # Mark the CP transition at 60 min
        ax.axhline(y=estimated_cp, color='gray', linestyle='--', alpha=0.6,
                    label=f'CP = {estimated_cp:.0f} W')
        ax.axvline(x=60, color='orange', linestyle=':', alpha=0.5,
                    label='CP/endurance boundary')

        # Shade the endurance decay region
        endurance_t = t_fit[t_fit > 3600]
        endurance_p = p_fit[len(t_fit) - len(endurance_t):]
        if len(endurance_t) > 0:
            ax.fill_between(endurance_t / 60, endurance_p, estimated_cp,
                            alpha=0.1, color='blue',
                            label='Endurance decay zone')

        ax.set_xlabel('Duration (min)')
        ax.set_ylabel('Power (W)')
        ax.set_title('Power-Duration Curve')
        ax.grid(alpha=0.3)
        ax.legend(fontsize=8)
        ax.set_xlim(left=0)

        return fig  # Return the figure object

def calculate_critical_power(activities, durations, user_id=None):
    best_power = {duration: 0.0 for duration in durations}

    for activity in activities:
        activity_id = activity["id"]

        try:
            power_stream = get_power_stream(activity_id, user_id=user_id)
        except Exception as e:
            print(f"Error processing activity {activity_id}: {e}")
            continue

        for duration in durations:
            if len(power_stream) >= duration:
                avg_powers = [
                    float(np.mean(power_stream[i:i + duration]))
                    for i in range(len(power_stream) - duration + 1)
                ]
                avg_power = max(avg_powers)
                best_power[duration] = max(best_power[duration], avg_power)

    return best_power



def get_critical_power_profile(days=60, user_id=None):
    try:
        print('Starting critical power profile calculation')
        activities = get_activities(days, user_id=user_id)
        print('Activities:', activities)
        durations = [15, 30, 60, 120, 300, 1200, 60*30, 60*60]  # Durations in seconds (5s, 30s, 1min, 5min, 20min)
        critical_power = calculate_critical_power(
            activities, durations, user_id=user_id)

        print("Critical Power Profile:")
        for duration, power in critical_power.items():
            print(f"{duration if duration < 60 else duration / 60}{'s' if duration < 60 else 'm'}: {power:.2f} watts")
        
        return critical_power
    except Exception as e:
        print(f"Error: {e}")
        print("Traceback:")
        print(traceback.format_exc())
        return None

def calculate_w_prime_recovery(
        W_prime_max, 
        W_prime_current, 
        CP, P_recovery, 
        recovery_time, 
        tau_base=2287.2, 
        tau_exponent=-0.688):
    """
    Calculate the W' (anaerobic work capacity) recovery during a recovery period below CP.
    ref: https://journals.humankinetics.com/view/journals/ijspp/13/6/article-p724.xml

    :param W_prime_max: Maximum W' (anaerobic capacity) in joules.
    :param W_prime_current: Current W' value in joules.
    :param CP: Critical power in watts.
    :param P_recovery: Power during recovery in watts.
    :param recovery_time: Duration of recovery in seconds.
    :param tau_base: Base coefficient for tau calculation (default from Skiba model).
    :param tau_exponent: Exponent for tau calculation (default from Skiba model).
    :return: Updated W' after the recovery period.
    """
    # Calculate Deficit Below Critical Power (DCP)
    DCP = CP - P_recovery
    if DCP <= 0:
        # No recovery if power is at or above CP
        return W_prime_current

    # Calculate the time constant of recovery (tau)
    tau_W_prime = tau_base * (DCP ** tau_exponent)

    # Calculate the recovered W' using the exponential recovery formula
    W_prime_recovered = W_prime_max - (W_prime_max - W_prime_current) * np.exp(-recovery_time / tau_W_prime)

    # Ensure W' does not exceed the maximum capacity
    return min(W_prime_recovered, W_prime_max)


# Example usage
if __name__ == "__main__":
    # Initialize database
    initialize_rider_database()
    
    rider = Rider(height=1.75, weight=70, bike_type="Road", position="Hoods", rider_type="sprinter", critical_power=300)
    print(rider)
    rider.update_height(1.80)
    print(rider)
    rider.update_weight(75)
    print(rider)
    rider.update_bike_type("TT")
    print(rider)
    rider.update_position("Aero")
    print(rider)
    rider = Rider(height=1.75, weight=70, bike_type="Road", position="Hoods")
    print(rider)
    rider = Rider(height=1.75, weight=70, bike_type="Road", position="Hoods")
    print(rider)