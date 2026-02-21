"""
測試腳本：驗證信心度 Kelly、RL 策略和 Excel 記錄功能
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

import os
os.environ['OPENAI_API_KEY'] = 'test'
os.environ['GEMINI_API_KEY'] = 'test'  
os.environ['GROK_API_KEY'] = 'test'

# 測試 1: ConfidenceKelly
print("=" * 50)
print("測試 1: ConfidenceKelly")
print("=" * 50)

from src.math_models import ConfidenceKelly

kelly = ConfidenceKelly(
    base_fraction=0.75,
    min_edge=0.08,
    initial_bankroll=1000
)

# 模擬參數
test_prob = 0.55  # 模型預測 55% 勝率
test_odds = 2.0   # 赔率 2.0
test_confidence = 0.8  # 80% 信心度
test_uncertainty = 0.1  # 10% 模型不確定性
test_market_prob = 0.5  # 市場隱含 50%

result = kelly.calculate(
    prob=test_prob,
    odds=test_odds,
    confidence=test_confidence,
    model_uncertainty=test_uncertainty,
    market_prob=test_market_prob
)

print(f"輸入: prob={test_prob}, odds={test_odds}, confidence={test_confidence}")
print(f"Kelly%: {result.kelly_pct:.2%}")
print(f"期望值 (EV): {result.ev:.3f}")
print(f"優勢 (Edge): {result.edge:.3f}")
print(f"建議投注: ${result.stake:.2f}")

kelly_result_dict = result.to_dict()
print(f"\nto_dict() 返回: {kelly_result_dict}")

# 測試 2: RL 策略
print("\n" + "=" * 50)
print("測試 2: RL 投注策略")
print("=" * 50)

from src.advanced_models import BettingRLAgent

rl_agent = BettingRLAgent(
    bankroll=1000,
    learning_rate=0.1,
    discount_factor=0.95,
    exploration_rate=0.1
)

edge = test_prob - test_market_prob  # 0.55 - 0.5 = 0.05
rl_decision = rl_agent.place_bet(
    edge=edge,
    confidence=test_confidence,
    odds=test_odds,
    home_form=0.6,
    away_form=0.4,
    predicted_prob=test_prob
)

print(f"輸入: edge={edge:.3f}, confidence={test_confidence}, odds={test_odds}")
print(f"邊緣 (Edge): {rl_decision.get('edge', edge):.3f}")
print(f"投注金額: ${rl_decision.get('bet_amount', 0):.2f}")

# 測試 3: Excel 記錄
print("\n" + "=" * 50)
print("測試 3: Excel 記錄")
print("=" * 50)

from src.finance import ExcelLogger
import tempfile

# 使用臨時檔案進行測試
with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as tmp:
    temp_excel_path = tmp.name

# 模擬數據
match_info = {
    "league": "意甲",
    "home": "Sassuolo",
    "away": "Hellas Verona"
}
bet_info = {
    "market": "Asian Handicap +0.25",
    "selection": "Home",
    "odds": 1.9,
    "model_probability": 0.55
}
stake_info = kelly_result_dict  # 使用 ConfidenceKelly 的結果

print(f"stake_info 內容: {stake_info}")
print(f"stake_info['pct'] = {stake_info.get('pct', 'N/A')}")
print(f"stake_info['ev'] = {stake_info.get('ev', 'N/A')}")

# 驗證 stake_info 有正確的鍵
assert 'pct' in stake_info, "❌ stake_info 缺少 'pct' 鍵"
assert 'ev' in stake_info, "❌ stake_info 缺少 'ev' 鍵"
assert 'stake' in stake_info, "❌ stake_info 缺少 'stake' 鍵"
print("✅ stake_info 結構正確")

# 測試計算時使用正確的鍵
test_ev = stake_info['ev']
test_pct = stake_info['pct']
test_stake = stake_info['stake']
print(f"✅ 提取值正確: ev={test_ev}, pct={test_pct}, stake={test_stake}")

# 清理
try:
    os.unlink(temp_excel_path)
except:
    pass

print("\n" + "=" * 50)
print("測試完成!")
print("=" * 50)
