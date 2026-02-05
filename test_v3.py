#!/usr/bin/env python3
import sys
sys.stdout.reconfigure(encoding='utf-8')
from src.math_models_v3 import NegativeBinomialModel, DynamicKEloSystem, ConfidenceKelly, MonteCarloSimulatorV3
print('='*60)
print('數學模型 v3 測試')
print('='*60)
nb = NegativeBinomialModel(1.5, 1.0)
p = nb.calculate_probabilities()
print(f'[1] 負二項分布: 主勝={p["home_win"]:.1%}, 離散={p["dispersion"]:.2f}')
elo = DynamicKEloSystem()
elo.update_ratings('A', 'B', 2, 1)
print(f'[2] 動態K Elo: A={elo.get_rating("A"):.1f}')
kelly = ConfidenceKelly(base_fraction=0.5, initial_bankroll=500)
r = kelly.calculate(prob=0.55, odds=2.0, confidence=0.7, market_prob=0.5)
print(f'[3] 信心度Kelly: Kelly%={r.kelly_pct:.2%}, 投注=${r.stake:.2f}')
mc = MonteCarloSimulatorV3(1.5, 1.0, iterations=2000, use_nbinom=True)  # 使用 Poisson
m = mc.run_simulation()
print(f'[4] 蒙地卡羅V3: 主勝={m["mc_home_win"]:.1%}, 大2.5={m["mc_over_2.5"]:.1%}')
print('='*60)
print('測試完成!')
print('='*60)
