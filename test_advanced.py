#!/usr/bin/env python3
import sys
sys.stdout.reconfigure(encoding='utf-8')
from src.advanced_models import (
    ExponentialDecayXGForecaster,
    InjuryImpactModel,
    Player,
    BayesianGoalModel,
    BettingRLAgent
)
import datetime

print('='*50)
print('Advanced Models Test')
print('='*50)

# 1. Exponential Decay xG
print('\n[1] Exponential Decay xG Model:')
xg = ExponentialDecayXGForecaster(decay_rate=0.1)
base_date = datetime.datetime.now()
for i in range(5):
    xg.add_match('TestTeam', xg=1.5-i*0.1, is_home=True, 
                date=base_date - datetime.timedelta(days=7*(5-i)))
pred = xg.get_team_xg('TestTeam', base_date, is_home=True)
print(f'   Predicted xG: {pred["xg"]:.3f} (n={pred["n_games"]})')

# 2. Injury Impact
print('\n[2] Injury Impact Model:')
injury = InjuryImpactModel()
injury.add_player('TeamA', Player('GK1', 'GK', 8.0, 90, 0.1, 0.8))
injury.add_player('TeamA', Player('FWD1', 'FWD', 25.0, 85, 0.6, 0.1))
impact = injury.calculate_team_impact('TeamA')
print(f'   Total Impact: {impact["total_impact"]:.2%}')

# 3. Bayesian Model
print('\n[3] Bayesian Goal Model:')
bayes = BayesianGoalModel()
for _ in range(10):
    bayes.add_observation(1, 1)
pred = bayes.predict()
print(f'   Home Lambda: {pred["home_lambda"]:.3f} [{pred["home_ci"][0]:.2f}-{pred["home_ci"][1]:.2f}]')
print(f'   Home Win Prob: {pred["probabilities"]["home_win"]:.1%}')
print(f'   Uncertainty: {pred["uncertainty"]["average"]:.2%}')

# 4. RL Betting
print('\n[4] RL Betting Strategy:')
rl = BettingRLAgent(bankroll=1000)
decision = rl.place_bet(edge=0.1, confidence=0.8, odds=2.2,
                       home_form=0.7, away_form=0.4, predicted_prob=0.55)
print(f'   Bet Pct: {decision["bet_pct"]:.1%}')
print(f'   Bet Amount: ${decision["bet_amount"]:.2f}')

print('\n' + '='*50)
print('Test Complete!')
print('='*50)
