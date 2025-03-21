import numpy as np

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
            multipliers = {60: 1.4, 300: 1.2, 600: 1.1, 1200: 1.05, 1800: 1.02}
        elif self.rider_type == "sprinter":
            multipliers = {60: 1.8, 300: 1.4, 600: 1.2, 1200: 1.1, 1800: 1.05}
        elif self.rider_type == "all_rounder":
            multipliers = {60: 1.6, 300: 1.3, 600: 1.15, 1200: 1.08, 1800: 1.03}
        else:
            raise ValueError("Invalid rider type. Choose from 'time_trialist', 'sprinter', or 'all_rounder'.")

        # Populate best efforts based on multipliers
        for duration, multiplier in multipliers.items():
            self.best_efforts[duration] = self.critical_power * multiplier

    def _estimate_w_tank_from_profile(self):
        """Estimate W' based on rider type and critical power."""
        if self.rider_type == "time_trialist":
            return 10_000 + 0.5 * self.critical_power
        elif self.rider_type == "sprinter":
            return 25_000 + 0.7 * self.critical_power
        elif self.rider_type == "all_rounder":
            return 15_000 + 0.6 * self.critical_power
        else:
            raise ValueError("Invalid rider type. Choose from 'time_trialist', 'sprinter', or 'all_rounder'.")

    def _power_duration_model(self, t, CP, W_prime):
        """Power-duration model: P(t) = CP + W'/t."""
        return CP + W_prime / t

    def _estimate_w_tank_from_curve(self):
        """Estimate W' based on the power-duration curve."""
        if not self.best_efforts:
            self._populate_best_efforts()  # Populate best efforts if not provided

        durations = np.array(list(self.best_efforts.keys()))
        powers = np.array(list(self.best_efforts.values()))

        # Curve fitting to estimate CP and W'
        popt, _ = curve_fit(self._power_duration_model, durations, powers, bounds=(0, np.inf))
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
        """Plot the power-duration curve if best efforts data is available."""
        if not self.best_efforts:
            self._populate_best_efforts()  # Populate best efforts if not provided

        durations = np.array(list(self.best_efforts.keys()))
        powers = np.array(list(self.best_efforts.values()))

        # Fit the curve
        popt, _ = curve_fit(self._power_duration_model, durations, powers, bounds=(0, np.inf))
        estimated_cp, w_prime = popt

        # Generate a smooth curve
        t_fit = np.linspace(min(durations), max(durations), 500)
        p_fit = self._power_duration_model(t_fit, *popt)

        # Plot
        plt.figure(figsize=(8, 5))
        plt.scatter(durations, powers, color='red', label='Best Efforts Data')
        plt.plot(t_fit, p_fit, label=f'Fitted Curve\nCP={estimated_cp:.2f} W, W\'={w_prime:.2f} J')
        plt.xlabel('Duration (s)')
        plt.ylabel('Power (W)')
        plt.title('Power-Duration Curve')
        plt.legend()
        plt.grid()
        plt.show()

# Example Usage
# Rider profile (time trialist) with CP=300 W and no best_efforts provided
wt_calculator = WTankCalculator(rider_type='time_trialist', critical_power=300)
w_tank = wt_calculator.calculate_w_tank()
print(f"Estimated WTank: {w_tank:.2f} J")

# Plot the estimated power-duration curve
wt_calculator.plot_power_duration_curve()
