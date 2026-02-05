#!/usr/bin/env python3
import sys
sys.stdout.reconfigure(encoding='utf-8')
from src.math_models_v3 import MonteCarloSimulatorV3
import numpy as np

print('Debug Monte Carlo Simulation - Fixed')
print('='*60)

# Run the actual simulation with new formula
print('\nRunning MonteCarloSimulatorV3...')
mc = MonteCarloSimulatorV3(1.5, 1.0, iterations=10000, use_nbinom=True, dispersion=1.5)
result = mc.run_simulation()
print(f'mc_home_win: {result["mc_home_win"]:.1%}')
print(f'mc_draw: {result["mc_draw"]:.1%}')
print(f'mc_away_win: {result["mc_away_win"]:.1%}')
print(f'expected_goals: home={result["expected_goals"]["home"]:.2f}, away={result["expected_goals"]["away"]:.2f}')
print(f'over_2.5: {result["mc_over_2.5"]:.1%}')
print(f'95% CI home: {result["confidence_95"]["home_goals_ci"]}')

# Also test with Poisson only
print('\n--- Testing with Poisson only ---')
mc2 = MonteCarloSimulatorV3(1.5, 1.0, iterations=10000, use_nbinom=False)
result2 = mc2.run_simulation()
print(f'Poisson - home_win: {result2["mc_home_win"]:.1%}, draw: {result2["mc_draw"]:.1%}')
