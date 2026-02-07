import sys
import os
os.chdir('c:/Users/Ryan/python/.vscode/fb_ai_bets')
sys.path.insert(0, 'c:/Users/Ryan/python/.vscode/fb_ai_bets')

from config import settings
from src.data_modules import HistoryRepo, RealOddsFetcher, OddsPoint, LEAGUE_OPTIONS
from src.llm_clients import llm
from src.finance import calculate_kelly_stake, ExcelLogger
from src.math_models import PoissonModel, MonteCarloSimulator, DixonColesModel
from src.math_models_v2 import OptimizedDixonColes, MonteCarloSimulator as MCSim_v2
from src.math_models_v3 import (
    NegativeBinomialModel,
    DynamicKEloSystem,
    MonteCarloSimulatorV3,
    ConfidenceKelly
)
from src.advanced_models import (
    ExponentialDecayXGForecaster,
    BayesianGoalModel,
    TeamFormLSTM,
    BettingRLAgent
)
from src.injury_api import InjuryDataAggregator, get_injury_report
from src.lineup_api import LineupAggregator, get_lineup
from src.team_name_matcher import match_teams, get_team_info

import pandas as pd
import numpy as np
import datetime
import time
import json
from fuzzywuzzy import fuzz

print("="*70)
print("   MANCHESTER UNITED VS TOTTENHAM HOTSPUR ANALYSIS")
print("="*70)

# Match input
api_home = "Manchester United"
api_away = "Tottenham Hotspur"
print(f"\n[MATCH] {api_home} vs {api_away}")

# Fuzzy match first
print(f"\n[1/4] Team Name Matching...")
repo = HistoryRepo('data/history_data.csv')

all_teams = set(list(repo.df['home_team'].unique()) + list(repo.df['away_team'].unique()))
print(f"      Database contains {len(all_teams)} teams")

ALIAS_MAP = {
    "manchester united": "Manchester United",
    "man utd": "Manchester United",
    "manchester city": "Manchester City",
    "man city": "Manchester City",
    "tottenham": "Tottenham Hotspur",
    "spurs": "Tottenham Hotspur",
}

def fuzzy_match(input_name, team_list):
    clean = input_name.lower().strip()
    if clean in ALIAS_MAP:
        matched = ALIAS_MAP[clean]
        if matched in team_list:
            return matched
    if input_name in team_list:
        return input_name
    for team in team_list:
        scores = [fuzz.ratio(clean, team.lower()),
                  fuzz.partial_ratio(clean, team.lower()),
                  fuzz.token_sort_ratio(clean, team.lower())]
        if max(scores) >= 60:
            return team
    return input_name

target_home = fuzzy_match(api_home, all_teams)
target_away = fuzzy_match(api_away, all_teams)

print(f"      [FUZZY] \"{api_home}\" -> \"{target_home}\"")
print(f"      [FUZZY] \"{api_away}\" -> \"{target_away}\"")

# Get odds from Odds API
print(f"\n[2/4] Loading Odds from The Odds API...")
real_odds = RealOddsFetcher()
match_odds = real_odds.get_real_odds('soccer_epl', target_home, target_away)

# Extract odds
if match_odds and isinstance(match_odds, dict):
    home_odds = match_odds.get('home_odds', 2.0)
    away_odds = match_odds.get('away_odds', 3.5)
    draw_odds = match_odds.get('draw_odds', 3.5)
    print(f"      [ODDS] Found: Home {home_odds}, Draw {draw_odds}, Away {away_odds}")
else:
    print(f"      [WARNING] Match not found in API, using default odds")
    home_odds, away_odds, draw_odds = 2.0, 3.5, 3.5
    print(f"      [ODDS] Default: Home {home_odds}, Draw {draw_odds}, Away {away_odds}")

# Load advanced models (only the ones we need)
print(f"\n[3/4] Loading Advanced Models...")
xg_model = ExponentialDecayXGForecaster(decay_rate=0.1, min_games=2)
bayes_model = BayesianGoalModel()
lstm_model = TeamFormLSTM(min_games=2)

# Prepare data
df = repo.df.copy()
df.columns = df.columns.str.strip().str.lower().str.replace('\ufeff', '')
df = df.dropna(subset=['home_team', 'away_team'])

# Filter for xG data
valid_df = df
if 'xg' in df.columns:
    valid_df = df[df['xg'].notna()]

print(f"      Total matches: {len(df)}, With xG: {len(valid_df)}")

# Load xG data
match_count = 0
for _, row in valid_df.tail(300).iterrows():
    try:
        home_xg = float(row.get('xg', 1.5))
        away_xg = float(row.get('xga', 1.0))
        if pd.notna(home_xg) and pd.notna(away_xg):
            xg_model.add_match(row['home_team'], home_xg, True, str(row.get('date', '')))
            xg_model.add_match(row['away_team'], away_xg, False, str(row.get('date', '')))
            match_count += 1
    except:
        pass
print(f"      [xG] Loaded {match_count} matches into Exponential Decay model")

# Load LSTM data
lstm_count = 0
for _, row in valid_df.tail(150).iterrows():
    try:
        result = str(row.get('ftr', 'D')).upper()
        home_res, away_res = ('W', 'L') if result == 'W' else ('L', 'W') if result == 'L' else ('D', 'D')
        home_xg = float(row.get('xg', 1.5))
        away_xg = float(row.get('xga', 1.0))
        lstm_model.add_match(row['home_team'], int(row.get('home_goals', 0)), int(row.get('away_goals', 0)), 
                            home_xg, 50, 3, home_res, True)
        lstm_model.add_match(row['away_team'], int(row.get('away_goals', 0)), int(row.get('home_goals', 0)), 
                            away_xg, 50, 3, away_res, False)
        lstm_count += 1
    except:
        pass
print(f"      [LSTM] Loaded {lstm_count} matches into LSTM model")

# Get predictions
ref_date = datetime.datetime.now()
home_xg_raw = xg_model.get_team_xg(target_home, ref_date, True)
away_xg_raw = xg_model.get_team_xg(target_away, ref_date, False)

# Debug
print(f"      [DEBUG] home_xg_raw: {home_xg_raw}")
print(f"      [DEBUG] away_xg_raw: {away_xg_raw}")

# Handle None returns - extract values safely
if home_xg_raw and isinstance(home_xg_raw, dict):
    h_xg_val = home_xg_raw.get('xg')
    h_xg = float(h_xg_val) if h_xg_val is not None else 1.2
    h_n = home_xg_raw.get('n_games', 0)
else:
    h_xg, h_n = 1.2, 0

if away_xg_raw and isinstance(away_xg_raw, dict):
    a_xg_val = away_xg_raw.get('xg')
    a_xg = float(a_xg_val) if a_xg_val is not None else 1.0
    a_n = away_xg_raw.get('n_games', 0)
else:
    a_xg, a_n = 1.0, 0

print(f"\n[4/4] Running Analysis...")
print(f"\n{'='*70}")
print(f"   MODEL PREDICTIONS")
print(f"{'='*70}")

print(f"\n[EXPONENTIAL DECAY xG]")
print(f"   {target_home} (Home):  {h_xg:.2f} xG (n={h_n})")
print(f"   {target_away} (Away):  {a_xg:.2f} xG (n={a_n})")

# Bayesian model - simple Poisson-based prediction
h_lambda = h_xg
a_lambda = a_xg
bayes_home = h_lambda / (h_lambda + a_lambda + 0.001)
bayes_away = a_lambda / (h_lambda + a_lambda + 0.001)
bayes_draw = 1.0 - bayes_home - bayes_away
# Ensure non-negative
bayes_home = max(0, bayes_home)
bayes_away = max(0, bayes_away)
bayes_draw = max(0, bayes_draw)
# Normalize
total = bayes_home + bayes_away + bayes_draw
if total > 0:
    bayes_home /= total
    bayes_away /= total
    bayes_draw /= total

print(f"\n[BAYESIAN GOAL MODEL]")
print(f"   Home λ: {h_lambda:.2f}, Away λ: {a_lambda:.2f}")
print(f"   Home Win: {bayes_home:.1%}, Draw: {bayes_draw:.1%}, Away Win: {bayes_away:.1%}")

# LSTM form
home_form_raw = lstm_model.predict_team_form(target_home)
away_form_raw = lstm_model.predict_team_form(target_away)

print(f"      [DEBUG] home_form_raw: {home_form_raw}")
print(f"      [DEBUG] away_form_raw: {away_form_raw}")

# Handle None returns
if home_form_raw and isinstance(home_form_raw, dict) and home_form_raw.get('form_score') is not None:
    home_form = home_form_raw
else:
    home_form = {'form_score': 0.5, 'trend': 'stable'}

if away_form_raw and isinstance(away_form_raw, dict) and away_form_raw.get('form_score') is not None:
    away_form = away_form_raw
else:
    away_form = {'form_score': 0.5, 'trend': 'stable'}

print(f"\n[LSTM TEAM FORM]")
print(f"   {target_home}: {home_form.get('form_score', 0.5):.2f} ({home_form.get('trend', 'stable')})")
print(f"   {target_away}: {away_form.get('form_score', 0.5):.2f} ({away_form.get('trend', 'stable')})")

# Monte Carlo Simulation
from scipy import stats
h_goals, a_goals = [], []
for _ in range(10000):
    h_goals.append(stats.poisson.rvs(h_lambda))
    a_goals.append(stats.poisson.rvs(a_lambda))

mc_home = sum(1 for h, a in zip(h_goals, a_goals) if h > a) / len(h_goals)
mc_draw = sum(1 for h, a in zip(h_goals, a_goals) if h == a) / len(h_goals)
mc_away = sum(1 for h, a in zip(h_goals, a_goals) if h < a) / len(h_goals)
over_25 = sum(1 for h, a in zip(h_goals, a_goals) if h + a > 2.5) / len(h_goals)

print(f"\n[MONTE CARLO SIMULATION (10,000 iterations)]")
print(f"   Home Win: {mc_home:.1%}, Draw: {mc_draw:.1%}, Away Win: {mc_away:.1%}")
print(f"   Over 2.5: {over_25:.1%}")
print(f"   Expected Goals: {np.mean(h_goals):.2f} - {np.mean(a_goals):.2f}")

# Kelly Criterion (simple Kelly formula)
market_home = 1 / home_odds if home_odds > 0 else 0
edge = (mc_home / market_home) - 1 if market_home > 0 else 0
kelly_frac = max(0, edge) * 0.5  # Half Kelly for safety

print(f"\n[KELLY CRITERION]")
print(f"   Market Implied: {market_home:.1%}")
print(f"   Model Edge:    {edge:.2%}")
print(f"   Kelly Fraction: {kelly_frac:.2%}")

# Final recommendation
print(f"\n{'='*70}")
print(f"   FINAL PREDICTION: {api_home} vs {api_away}")
print(f"{'='*70}")
print(f"\n   BETTING ODDS:")
print(f"   Home: {home_odds:.2f} ({1/home_odds:.1%})")
print(f"   Draw: {draw_odds:.2f} ({1/draw_odds:.1%})")
print(f"   Away: {away_odds:.2f} ({1/away_odds:.1%})")
print(f"\n   MODEL PREDICTIONS:")
print(f"   Home Win: {mc_home:.1%}")
print(f"   Draw:     {mc_draw:.1%}")
print(f"   Away Win: {mc_away:.1%}")
print(f"\n   EDGE ANALYSIS:")
print(f"   Home Edge: {edge:+.2%}" + (" [VALUE BET!]" if edge > 0.05 else ""))
print(f"\n   RECOMMENDATION:")
if edge > 0.05:
    print(f"   ✓ BACK HOME ({kelly_frac:.1%} of bankroll)")
elif edge < -0.05:
    print(f"   ✓ LAY HOME / BACK AWAY")
else:
    print(f"   - NO VALUE - SKIP")

print(f"\n{'='*70}")
