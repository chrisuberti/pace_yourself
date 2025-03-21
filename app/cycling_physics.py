import sympy as sp
import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import root_scalar
from app.helpers import mps_to_mph  # Assuming this is defined in the helpers module
import unittest

def calculate_speed_and_plot(Power, rho=1.225, CdA=0.3, Crr=0.005, mass=75,
                             drivetrain_efficiency=0.95, gradient=0, v_wind=0,
                             altitude=0, temperature=15, dew_point=10, pressure=1013.25,
                             plot=False):
    """
    Calculate the speed for a given power output and optionally plot the power vs. speed curve.
    
    Args:
        Power (float): Power output in watts.
        rho (float): Air density in kg/m^3.
        v_wind (float): Wind speed in m/s. Inline with the cyclist's direction. (positive is tailwind).
        CdA (float): Coefficient of drag times frontal area in m^2.
        Crr (float): Coefficient of rolling resistance.
        mass (float): Rider + bike mass in kg.
        drivetrain_efficiency (float): Fraction of power reaching the drivetrain (0-1).
        gradient (float): Road gradient as a decimal (e.g., -0.05 for a 5% downhill).
        plot (bool): Whether to plot the power vs. speed curve for error checking.

    Returns:
        dict: A dictionary containing the x-intercept (speed in m/s), 
              speed in mph, and optionally the plot figure.
    """
    # Constants
    m = mass
    g = 9.81

    # Define the power equation as a function of speed
    def power_equation(v):
        return ((1 / 2) * rho * CdA * (v - v_wind)**2 +
                m * g * np.sin(np.arctan(gradient)) +
                m * g * Crr * np.cos(np.arctan(gradient))) * v - Power

    # Solve for speed
    result = root_scalar(power_equation, bracket=[0.1, 50], method='brentq')
    speed_mps = result.root if result.converged else None
    speed_mph = mps_to_mph(speed_mps) if speed_mps is not None else None

    # Plot if requested
    fig = None
    if plot:
        speeds = np.linspace(0.1, 50, 500)
        powers = [power_equation(v) + Power for v in speeds]
        fig, ax = plt.subplots()
        ax.plot(speeds, powers, label='Power vs. Speed')
        ax.axhline(0, color='red', linestyle='--', label='Target Power')
        ax.axvline(speed_mps, color='green', linestyle='--', label='Calculated Speed')
        ax.set_xlabel('Speed (m/s)')
        ax.set_ylabel('Power (W)')
        ax.legend()
        plt.show()

    return {
        'speed_mps': speed_mps,
        'speed_mph': speed_mph,
        'plot': fig
    }

def calculate_air_density(temperature=15, dew_point=10, pressure=1013.25, altitude=0):
    """
    Calculate air density given temperature, dew point, pressure, and altitude.
    
    Args:
        temperature (float): Temperature in degrees Celsius. Default is 15°C.
        dew_point (float): Dew point in degrees Celsius. Default is 10°C.
        pressure (float): Atmospheric pressure at sea level in hPa (hectopascals). Default is 1013.25 hPa.
        altitude (float): Altitude in meters. Default is 0 meters.

    Returns:
        float: Air density in kg/m^3.
    """
    # Constants
    R_d = 287.05  # Specific gas constant for dry air (J/(kg·K))
    R_v = 461.495  # Specific gas constant for water vapor (J/(kg·K))
    T0 = 288.15  # Standard temperature at sea level (K)
    P0 = 1013.25  # Standard pressure at sea level (hPa)
    L = 0.0065  # Temperature lapse rate (K/m)
    g = 9.80665  # Acceleration due to gravity (m/s^2)
    M = 0.0289644  # Molar mass of Earth's air (kg/mol)
    R = 8.31447  # Universal gas constant (J/(mol·K))
    
    # Convert temperature to Kelvin
    T = temperature + 273.15
    
    # Adjust pressure for altitude using the barometric formula
    P = pressure * (1 - (L * altitude) / T0)**(g * M / (R * L))
    
    # Calculate saturation vapor pressure (in hPa)
    e_s = 6.11 * 10.0**((7.5 * dew_point) / (237.3 + dew_point))
    
    # Calculate actual vapor pressure (in hPa)
    e = e_s
    
    # Convert pressure to Pa
    p = P * 100.0
    
    # Calculate partial pressures
    p_d = p - e * 100.0  # Partial pressure of dry air (Pa)
    p_v = e * 100.0  # Partial pressure of water vapor (Pa)
    
    # Calculate air density
    rho = (p_d / (R_d * T)) + (p_v / (R_v * T))
    
    return rho

class TestCalculateSpeedAndPlot(unittest.TestCase):
    def test_calculate_speed_and_plot(self):
        test_cases = [
            {'Power': 250, 'rho': 1.225, 'CdA': 0.3, 'Crr': 0.005, 'mass': 75, 'drivetrain_efficiency': 0.95, 'gradient': 0, 'v_wind': 0},
            {'Power': 300, 'rho': 1.225, 'CdA': 0.3, 'Crr': 0.005, 'mass': 75, 'drivetrain_efficiency': 0.95, 'gradient': 0.05, 'v_wind': 2},
            {'Power': 200, 'rho': 1.225, 'CdA': 0.3, 'Crr': 0.005, 'mass': 75, 'drivetrain_efficiency': 0.95, 'gradient': -0.05, 'v_wind': -2},
            # Add more test cases as needed
        ]

        for case in test_cases:
            with self.subTest(case=case):
                result = calculate_speed_and_plot(**case)
                self.assertIsNotNone(result['speed_mps'])
                self.assertIsNotNone(result['speed_mph'])
                self.assertGreater(result['speed_mps'], 0)
                self.assertGreater(result['speed_mph'], 0)

    def test_calculate_air_density(self):
        test_cases = [
            {'temperature': 20, 'dew_point': 10, 'pressure': 1013.25, 'altitude': 0, 'expected_rho': 1.2041},
            {'temperature': 30, 'dew_point': 20, 'pressure': 1000.00, 'altitude': 500, 'expected_rho': 1.1654},
            {'temperature': 15, 'dew_point': 5, 'pressure': 1020.00, 'altitude': 1000, 'expected_rho': 1.2250},
            # Add more test cases as needed
        ]

        for case in test_cases:
            with self.subTest(case=case):
                rho = calculate_air_density(case['temperature'], case['dew_point'], case['pressure'], case['altitude'])
                self.assertAlmostEqual(rho, case['expected_rho'], places=2)

    def test_rider_estimate_CdA(self):
        rider1 = Rider(height=1.75, weight=68, bike_type="Road", position="Drops")
        self.assertAlmostEqual(rider1.CdA, 0.33, places=3)

        rider2 = Rider(height=1.60, weight=60, bike_type="TT", position="Aero")
        self.assertAlmostEqual(rider2.CdA, 0.22, places=3)

        rider3 = Rider(height=1.90, weight=85, bike_type="Gravel", position="Hoods")
        self.assertAlmostEqual(rider3.CdA, 0.38 * (1.90 / 1.75), places=3)

if __name__ == "__main__":
    unittest.main()
    