# ML Model Training Summary

## Training Data
- **Total matches in database**: 29,640
- **Valid samples for training**: 10,144 (with xG data)

## Model Configuration
- **Algorithm**: XGBoost Classifier
- **n_estimators**: 200
- **learning_rate**: 0.05
- **max_depth**: 6
- **min_child_weight**: 3
- **subsample**: 0.8
- **colsample_bytree**: 0.8

## Features (10 total)
1. `home_advantage` - Fixed value (1)
2. `league_home_adv` - Home win rate advantage per league
3. `rolling_5_home_goals` - Home team 5-match rolling avg goals
4. `rolling_5_away_goals` - Away team 5-match rolling avg goals
5. `rolling_10_home_goals` - Home team 10-match rolling avg goals
6. `rolling_10_away_goals` - Away team 10-match rolling avg goals
7. `rolling_5_xg` - Home team 5-match rolling avg xG
8. `rolling_10_xg` - Home team 10-match rolling avg xG
9. `rolling_5_xga` - Away team 5-match rolling avg xGA
10. `rolling_10_xga` - Away team 10-match rolling avg xGA

## Performance Metrics
| Metric | Value | Interpretation |
|--------|-------|----------------|
| Accuracy | 61.71% | Correct predictions (random baseline: 33%) |
| Brier Score | 0.4923 | Lower is better (0=perfect) |
| Cross-Entropy | 0.8351 | Lower is better (0=perfect) |

## Feature Importance
| Rank | Feature | Importance |
|------|---------|------------|
| 1 | rolling_5_home_goals | 27.75% |
| 2 | rolling_5_away_goals | 22.87% |
| 3 | rolling_10_away_goals | 9.05% |
| 4 | rolling_10_home_goals | 8.61% |
| 5 | rolling_5_xg | 6.55% |
| 6 | rolling_10_xg | 6.38% |
| 7 | rolling_5_xga | 6.37% |
| 8 | rolling_10_xga | 6.35% |
| 9 | league_home_adv | 6.07% |
| 10 | home_advantage | 0.00% |

## Model Files
- `scripts/xgb_model.pkl` - Training script output
- `src/xgb_model.pkl` - Main application uses this

## Usage
```bash
# Retrain model
python scripts/train_model_v2.py

# The model will be automatically loaded by app.py
python app.py
```

## Notes
- Model predicts 3 outcomes: Home Win (0), Draw (1), Away Win (2)
- xG data from MatchPlayerData significantly improves predictions
- Rolling goals averages are the most important features
