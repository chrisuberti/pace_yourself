import sympy as sp
import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import root_scalar, curve_fit
import os, sys
import sqlite3
import unittest
import traceback
from dotenv import load_dotenv
load_dotenv()
app_path = os.getenv('APP_PATH')
if app_path:
    sys.path.append(app_path)

from app.helpers import mps_to_mph  # Assuming this is defined in the helpers module
from app.strava_calls import *

def initialize_rider_database():
    """Initialize the rider database with proper schema."""
    db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'rider_data.db')
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    # Create best_efforts table
    c.execute('''CREATE TABLE IF NOT EXISTS best_efforts (
                    rider_id TEXT,
                    duration INTEGER,
                    power REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (rider_id, duration)
                )''')
    
    # Create rider_info table
    c.execute('''CREATE TABLE IF NOT EXISTS rider_info (
                    rider_id TEXT PRIMARY KEY,
                    strava_athlete_id TEXT UNIQUE,
                    height REAL,
                    weight REAL,
                    bike_type TEXT,
                    position TEXT,
                    CdA REAL,
                    critical_power REAL,
                    WTank REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )''')
    
    conn.commit()
    conn.close()
    print(f"Database initialized at: {db_path}")

def get_all_riders():
    """Get information about all riders in the database."""
    db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'rider_data.db')
    try:
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute('''SELECT rider_id, strava_athlete_id, height, weight, bike_type, position, 
                            critical_power, WTank, created_at, updated_at 
                     FROM rider_info ORDER BY updated_at DESC''')
        rows = c.fetchall()
        conn.close()
        
        riders = []
        for row in rows:
            rider_dict = {
                'rider_id': row[0],
                'strava_athlete_id': row[1],
                'height': row[2],
                'weight': row[3],
                'bike_type': row[4],
                'position': row[5],
                'critical_power': row[6],
                'WTank': row[7],
                'created_at': row[8],
                'updated_at': row[9]
            }
            riders.append(rider_dict)
        return riders
    except sqlite3.Error as e:
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
                 days=60, rider_id=None):
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
            weight: Total weight in kg (rider + bike + gear)
            bike_type: "Road", "TT", "Gravel", or "MTB"
            position: "Hoods", "Drops", "Aero", or "Flat"
            rider_type: For Method A - "time_trialist", "sprinter", or "all_rounder"
            critical_power: For Method A - your critical power in watts
            best_efforts: For Method B - dict of {duration_seconds: power_watts}
            days: For Method C - number of days to look back in Strava (default 60)
            rider_id: Optional - used to cache/retrieve data from local database
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
        self.strava_athlete_id = None
        
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
                self.strava_athlete_id = get_athlete_id()
                self.rider_id = str(self.strava_athlete_id)
                print(f"Got Strava athlete ID: {self.rider_id}")
            except Exception as e:
                print(f"No Strava authentication available: {e}")
                print("Tip: Provide rider_type + critical_power, or best_efforts dict")
                return  # Can't proceed without identification
        
        # Check if we have cached data in the database
        existing_rider_ids = self.get_existing_rider_ids()
        
        if self.rider_id in existing_rider_ids:
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
            if not self.strava_athlete_id:
                self.strava_athlete_id = get_athlete_id()
                if not self.rider_id:
                    self.rider_id = str(self.strava_athlete_id)
            
            self.best_efforts = self.get_best_power_from_strava(days)
            
            if self.best_efforts:
                self.WTank_calculator = WTankCalculator(best_efforts=self.best_efforts)
                self.WTank = self.WTank_calculator.calculate_w_tank()
                self.critical_power = self.WTank_calculator.critical_power
                
                # Cache for future use
                self.save_best_efforts_to_db()
                print(f"Calculated and cached: CP={self.critical_power:.0f}W, W'={self.WTank:.0f}J")
            else:
                print("No power data found in Strava activities")
                
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
        activities = get_activities(days)
        durations = [30, 60, 120, 300, 1200, 60*30]  # Durations in seconds (30s, 1min, 2min, 5min, 20min, 30min)
        return calculate_critical_power(activities, durations)

    def save_best_efforts_to_db(self):
        """Save best efforts to a database."""
        if not hasattr(self, 'rider_id') or not self.rider_id:
            raise ValueError("Rider ID must be provided to save best efforts to the database.")

        # Use data directory for database
        db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'rider_data.db')
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        
        # Create tables if they don't exist
        c.execute('''CREATE TABLE IF NOT EXISTS best_efforts (
                        rider_id TEXT,
                        duration INTEGER,
                        power REAL,
                        PRIMARY KEY (rider_id, duration)
                    )''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS rider_info (
                        rider_id TEXT PRIMARY KEY,
                        strava_athlete_id TEXT,
                        height REAL,
                        weight REAL,
                        bike_type TEXT,
                        position TEXT,
                        CdA REAL,
                        critical_power REAL,
                        WTank REAL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )''')

        # Save best efforts
        if hasattr(self, 'best_efforts'):
            for duration, power in self.best_efforts.items():
                c.execute('''INSERT OR REPLACE INTO best_efforts (rider_id, duration, power)
                             VALUES (?, ?, ?)''', (self.rider_id, duration, power))

        # Save rider info
        strava_id = getattr(self, 'strava_athlete_id', None)
        c.execute('''INSERT OR REPLACE INTO rider_info 
                     (rider_id, strava_athlete_id, height, weight, bike_type, position, CdA, critical_power, WTank, updated_at)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)''', 
                  (self.rider_id, strava_id, self.height, self.weight, self.bike_type, 
                   self.position, self.CdA, self.critical_power, self.WTank))

        conn.commit()
        conn.close()

    def load_best_efforts_from_db(self):
        """Load best efforts from a database."""
        if not hasattr(self, 'rider_id') or not self.rider_id:
            raise ValueError("Rider ID must be provided to load best efforts from the database.")

        # Use data directory for database
        db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'rider_data.db')
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute('''SELECT duration, power FROM best_efforts WHERE rider_id = ?''', (self.rider_id,))
        rows = c.fetchall()
        conn.close()

        self.best_efforts = {duration: power for duration, power in rows}

    def load_rider_info_from_db(self):
        """Load rider information from the database."""
        if not hasattr(self, 'rider_id') or not self.rider_id:
            raise ValueError("Rider ID must be provided to load rider info from the database.")

        # Use data directory for database
        db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'rider_data.db')
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute('''SELECT strava_athlete_id, height, weight, bike_type, position, CdA, critical_power, WTank 
                     FROM rider_info WHERE rider_id = ?''', (self.rider_id,))
        row = c.fetchone()
        conn.close()

        if row:
            (self.strava_athlete_id, self.height, self.weight, self.bike_type, 
             self.position, self.CdA, self.critical_power, self.WTank) = row
            return True
        return False

    def get_existing_rider_ids(self):
        """Get all existing rider IDs from the database."""
        # Use data directory for database
        db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'rider_data.db')
        try:
            conn = sqlite3.connect(db_path)
            c = conn.cursor()
            c.execute('''SELECT rider_id FROM rider_info''')
            rows = c.fetchall()
            conn.close()
            return [row[0] for row in rows]
        except sqlite3.Error:
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
        if self.rider_type == "time_trialist":
            multipliers = {60: 1.4, 300: 1.2, 600: 1.1, 1200: 1.05, 1800: 1.02, 3600: 1.0}
        elif self.rider_type == "sprinter":
            multipliers = {60: 1.8, 300: 1.4, 600: 1.2, 1200: 1.1, 1800: 1.05, 3600: 1.0}
        elif self.rider_type == "all_rounder":
            multipliers = {60: 1.6, 300: 1.3, 600: 1.15, 1200: 1.08, 1800: 1.03, 3600: 1.0}
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
        Modified power-duration model: P(t) = CP + W' / t
        The parameter `k` adjusts the curve's shape and asymptote.
        """
        return CP + W_prime / (t)

    def _estimate_w_tank_from_curve(self):
        """Estimate W' based on the modified power-duration curve."""
        if not self.best_efforts:
            self._populate_best_efforts()  # Populate best efforts if not provided

        durations = np.array(list(self.best_efforts.keys()))
        powers = np.array(list(self.best_efforts.values()))

        # Apply weights: prioritize durations >= 1200 seconds
        weights = np.ones_like(durations)
        weights[durations >= 1200] = 10  # Assign higher weight to longer durations

        # Curve fitting with weights
        popt, _ = curve_fit(
            self._power_duration_model,
            durations,
            powers
        )
        self.popt = popt  # Store the fitted parameters (CP, W_prime
        estimated_cp, w_prime= popt

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
        """Plot the power-duration curve if best efforts data is available."""
        if not self.best_efforts:
            self._populate_best_efforts()  # Populate best efforts if not provided

        durations = np.array(list(self.best_efforts.keys()))
        powers = np.array(list(self.best_efforts.values()))

        # Unpack the fitted parameters
        estimated_cp, w_prime = self.popt

        # Generate a smooth curve with fewer points
        t_fit = np.linspace(min(durations), max(durations), 200)  # Reduced from 500 to 200 points
        p_fit = self._power_duration_model(t_fit, estimated_cp, w_prime)

        # Create the plot with a smaller figure size
        fig, ax = plt.subplots(figsize=(6, 4))  # Adjusted figure size
        ax.scatter(durations, powers, color='red', label='Best Efforts Data')
        ax.plot(t_fit, p_fit, label=f'Fitted Curve\nCP={estimated_cp:.2f} W, W\'={w_prime:.2f} J')
        ax.axhline(y=estimated_cp, color='gray', linestyle='--', label=f'Asymptote (CP={estimated_cp:.2f} W)')
        ax.text(max(durations) * 0.8, estimated_cp * 1.05, f'CP={estimated_cp:.2f} W', color='gray')
        ax.set_xlabel('Duration (s)')
        ax.set_ylabel('Power (W)')
        ax.grid()
        ax.legend()

        return fig  # Return the figure object

def calculate_critical_power(activities, durations):
    best_power = {duration: 0.0 for duration in durations}

    for activity in activities:
        activity_id = activity["id"]

        try:
            power_stream = get_power_stream(activity_id)
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



def get_critical_power_profile(days=60):
    try:
        print('Starting critical power profile calculation')
        activities = get_activities(days)  # Retrieve activities from the past `days` days
        print('Activities:', activities)
        durations = [15, 30, 60, 120, 300, 1200, 60*30, 60*60]  # Durations in seconds (5s, 30s, 1min, 5min, 20min)
        critical_power = calculate_critical_power(activities, durations)

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