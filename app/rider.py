import sympy as sp
import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import root_scalar, curve_fit
import os, sys
import sqlite3
import unittest
from dotenv import load_dotenv
load_dotenv()
sys.path.append(os.getenv('APP_PATH'))

from app.helpers import mps_to_mph  # Assuming this is defined in the helpers module
from app.strava_calls import *

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
        self.height = height  # Rider height in meters
        self.weight = weight  # Rider weight in kilograms
        self.bike_type = bike_type  # Bike type (e.g., Road, TT, Gravel, MTB)
        self.position = position  # Riding position (e.g., Hoods, Drops, Aero)
        self.CdA = self.estimate_CdA()
        self.critical_power = critical_power
        self.WTank = None
        
        #if rider id isn't supplied, get the rider_id from strava
        #rider id is used to store the best efforts in the database for strava calls so we don't hit hte api too much and get throttled
        if (rider_id==None)&(rider_type==None)&(critical_power==None) & (best_efforts==None):
            #make sure to only call this condition if there are no other ways to estimate power supplied
            self.rider_id = get_athlete_id()
        elif rider_id:
            self.rider_id = rider_id
        

        #important block to populate critical power and WTank

        if rider_type and critical_power:
            self.WTank_calculator = WTankCalculator(rider_type=rider_type, critical_power=critical_power)
            self.WTank = self.WTank_calculator.calculate_w_tank()
        else: 
            #Try the few different methods in order to get your best_efforts variable if we're not estimating based on
            #load the best efforts from the database if they exist and pull out all the rider_ids
            # if the rider_id is not in the database, then we need to calculate the best efforts from strava

            #check if the database exists
            # if it does, pull out all the rider_ids
            # if the rider_id is in the database, load the best efforts from the database
            rider_ids = []
            
            if best_efforts:
                self.best_efforts = best_efforts
            elif rider_id in rider_ids:
                self.load_best_efforts_from_db()
            else:
                try:
                    #This one hit's the Strava API and is call intensive:
                    best_efforts = self.get_best_power_from_strava(days)
                    self.save_best_efforts_to_db()
                except Exception as e:
                    print(f"Error calculating WTank, user probably not authenticated from strava, see error: {e}")
                    print('OR you need to include a rider_type and critical_power')

            self.WTank_calculator = WTankCalculator(critical_power=critical_power, best_efforts=best_efforts)
            self.WTank = self.WTank_calculator.calculate_w_tank()
            self.critical_power = self.WTank_calculator.critical_power

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
        if not self.rider_id:
            raise ValueError("Rider ID must be provided to save best efforts to the database.")

        conn = sqlite3.connect('rider_data.db')
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS best_efforts (
                        rider_id TEXT,
                        duration INTEGER,
                        power REAL,
                        PRIMARY KEY (rider_id, duration)
                    )''')

        for duration, power in self.best_efforts.items():
            c.execute('''INSERT OR REPLACE INTO best_efforts (rider_id, duration, power)
                         VALUES (?, ?, ?)''', (self.rider_id, duration, power))

        conn.commit()
        conn.close()

    def load_best_efforts_from_db(self):
        """Load best efforts from a database."""
        if not self.rider_id:
            raise ValueError("Rider ID must be provided to load best efforts from the database.")

        conn = sqlite3.connect('rider_data.db')
        c = conn.cursor()
        c.execute('''SELECT duration, power FROM best_efforts WHERE rider_id = ?''', (self.rider_id,))
        rows = c.fetchall()
        conn.close()

        self.best_efforts = {duration: power for duration, power in rows}

    def update_height(self, height):
        """Update the height of the rider and recalculate CdA."""
        self.height = height
        self.CdA = self.estimate_CdA()

    def update_weight(self, weight):
        """Update the weight of the rider."""
        self.weight = weight

    def update_bike_type(self, bike_type):
        """Update the bike type and recalculate CdA."""
        self.bike_type = bike_type
        self.CdA = self.estimate_CdA()

    def update_position(self, position):
        """Update the riding position and recalculate CdA."""
        self.position = position
        self.CdA = self.estimate_CdA()

    def __str__(self):
        """String representation of the Rider instance."""
        return (f"Rider: {self.height}m, {self.weight}kg, Bike: {self.bike_type}, "
                f"Position: {self.position}, Estimated CdA: {self.CdA} m^2, "
                f"Critical Power: {self.critical_power} W, WTank: {self.WTank/1000} kJ")

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
    best_power = {duration: 0 for duration in durations}

    for activity in activities:
        activity_id = activity["id"]

        try:
            power_stream = get_power_stream(activity_id)
        except Exception as e:
            print(f"Error processing activity {activity_id}: {e}")
            continue

        for duration in durations:
            if len(power_stream) >= duration:
                avg_power = max(
                    np.mean(power_stream[i:i + duration])
                    for i in range(len(power_stream) - duration + 1)
                )
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