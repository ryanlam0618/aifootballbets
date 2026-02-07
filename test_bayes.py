import sys
sys.path.insert(0, 'c:/Users/Ryan/python/.vscode/fb_ai_bets')

from src.advanced_models import BayesianGoalModel
import pandas as pd

print('=' * 50)
print('Testing Bayesian Model with Valid xG Data')
print('=' * 50)

bayes = BayesianGoalModel()
df = pd.read_csv('c:/Users/Ryan/python/.vscode/fb_ai_bets/data/history_data.csv')

# Only use rows with valid xG
valid_df = df.dropna(subset=['home_goals', 'away_goals', 'xG', 'xGA'])
print(f'Valid xG rows: {len(valid_df)}')

obs_count = 0
for _, row in valid_df.tail(50).iterrows():
    try:
        # Home observation
        home_xg = float(row['xG'])
        bayes.add_observation(
            int(row['home_goals']), 
            int(row['away_goals']),
            home_xg=home_xg,
            is_home=True
        )
        # Away observation
        away_xg = float(row['xGA'])
        bayes.add_observation(
            int(row['away_goals']),
            int(row['home_goals']),
            home_xg=away_xg,
            is_home=False
        )
        obs_count += 2
    except:
        continue

print(f'Observations: {obs_count}')

pred = bayes.predict()

print()
print('Results:')
print(f'  Home lambda: {pred["home_lambda"]:.3f}')
print(f'  Away lambda: {pred["away_lambda"]:.3f}')
probs = pred.get('probabilities', {})
print(f'  Home win: {probs.get("home_win", 0):.1%}')
print(f'  Draw: {probs.get("draw", 0):.1%}')
print(f'  Away win: {probs.get("away_win", 0):.1%}')
print(f'  Uncertainty: {pred["uncertainty"]["average"]:.1%}')
