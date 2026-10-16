"""Quick sanity check: linear vs exponential W' recovery."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from app.rider import calculate_w_prime_recovery

CP = 250
W_max = 20000

# Single recovery comparison
linear_recovery = min(W_max, 10000 + (CP - 230) * 600)
exp_recovery = calculate_w_prime_recovery(W_max, 10000, CP, 230, 600)
print(f"After 10min at 230W (20W below CP), starting from 10kJ W':")
print(f"  Old linear:      +{linear_recovery - 10000:.0f}J  -> {linear_recovery:.0f}J")
print(f"  New exponential:  +{exp_recovery - 10000:.0f}J  -> {exp_recovery:.0f}J")
print()

# Repeated spend/recover cycles (the broken perpetual-motion pattern)
w_lin = W_max
w_exp = W_max
print("Repeated 3min@300W / 5min@200W cycles (CP=250W):")
for cycle in range(5):
    # Spend: 3min at 300W -> 50W above CP * 180s = 9000J depleted
    w_lin -= 50 * 180
    w_exp -= 50 * 180

    # Recover: 5min at 200W
    w_lin = min(W_max, w_lin + (CP - 200) * 300)
    w_exp = calculate_w_prime_recovery(W_max, w_exp, CP, 200, 300)

    print(f"  Cycle {cycle+1}: Linear W'={w_lin:>7.0f}J   Exponential W'={w_exp:>7.0f}J")

print()
print("Key takeaway: linear model fully refills every cycle (perpetual motion),")
print("exponential model progressively depletes — physically correct.")
