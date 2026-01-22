# API 文檔

## 核心模組 API

### data_modules.py

#### HistoryRepo

歷史數據儲存庫，負責讀取與處理歷史比賽數據。

```python
from src.data_modules import HistoryRepo

repo = HistoryRepo(csv_path="data/big_five_history.csv")
context = repo.get_match_context(home="Arsenal", away="Chelsea", league="Premier League")
```

**方法**:

- `get_match_context(home, away, league)`: 獲取比賽上下文數據
  - 返回: 包含歷史戰績、統計數據、評分等的字典
  
- `get_lineup_prediction(home, away)`: 基於陣容預測勝率
  - 返回: 主隊勝率 (float) 或 None

#### RealOddsFetcher

即時賠率獲取器，透過 The Odds API 獲取賠率數據。

```python
from src.data_modules import RealOddsFetcher

fetcher = RealOddsFetcher()
odds = fetcher.get_real_odds(
    league_key="soccer_epl",
    home="Arsenal", 
    away="Chelsea"
)
```

**方法**:

- `get_real_odds(league_key, home, away)`: 獲取即時賠率
  - 返回: 賠率數據結構 (OddsDataStructure)

#### LEAGUE_OPTIONS

聯賽配置字典，包含 60+ 個支援的聯賽。

```python
from src.data_modules import LEAGUE_OPTIONS

# 獲取英超配置
epl = LEAGUE_OPTIONS["1"]
print(epl["name"])  # "Premier League (England)"
print(epl["key"])   # "soccer_epl"
```

---

### llm_clients.py

#### LLMOrchestrator

LLM 客戶端協調器，整合 GPT-4、Grok 等模型。

```python
from src.llm_clients import llm

# Grok 市場情報搜尋
reaction = llm.search_and_analyze_market_reaction(
    match_info="Arsenal vs Chelsea",
    odds_data_input=odds_summary
)

# GPT-4 綜合決策
decision = llm.analyze_with_super_prompt(
    match_context=context,
    odds_data_package=odds_package,
    math_model_results=math_results
)
```

**方法**:

- `search_and_analyze_market_reaction(match_info, odds_data_input)`: Grok 聯網分析
- `analyze_with_super_prompt(match_context, odds_data_package, math_model_results)`: GPT-4 決策

---

### finance.py

#### calculate_kelly_stake

Kelly Criterion 資金管理計算。

```python
from src.finance import calculate_kelly_stake

stake_info = calculate_kelly_stake(
    prob=0.65,        # 模型勝率
    odds=2.5,         # 賠率
    bankroll=1000     # 資金
)

print(stake_info["stake"])  # 建議投注金額
print(stake_info["ev"])     # 期望值
```

**返回**:
```python
{
    "stake": 150.0,   # 建議投注金額
    "pct": 0.15,      # 投注比例
    "ev": 0.125       # 期望值
}
```

#### ExcelLogger

Excel 記錄器，自動記錄投注歷史。

```python
from src.finance import ExcelLogger

logger = ExcelLogger()
logger.log_bet(match_info, bet_info, stake_info)
logger.show_stats()  # 顯示勝率統計
```

---

### math_models.py

#### PoissonModel

泊松分佈預測模型。

```python
from src.math_models import PoissonModel

model = PoissonModel(home_expect=1.5, away_expect=1.0)
probs = model.calculate_probabilities()
```

#### DixonColesModel

Dixon-Coles 模型（考慮低比分修正）。

```python
from src.math_models import DixonColesModel

model = DixonColesModel(home_expect=1.5, away_expect=1.0, rho=-0.13)
probs = model.calculate_probabilities()
```

#### MonteCarloSimulator

蒙地卡羅模擬器。

```python
from src.math_models import MonteCarloSimulator

sim = MonteCarloSimulator(home_expect=1.5, away_expect=1.0, iterations=10000)
results = sim.run_simulation()
```

---

### math_models_v2.py

#### Glicko2System

Glicko-2 評分系統。

```python
from src.math_models_v2 import Glicko2System

system = Glicko2System()
system.update_ratings("Arsenal", "Chelsea", 2, 1)
prob = system.expected_win_prob("Arsenal", "Chelsea")
```

#### LineupModel

陣容評分模型。

```python
from src.math_models_v2 import LineupModel

model = LineupModel(lineup_data)
win_prob = model.predict_win_prob()
```

---

## 數據結構

### OddsDataStructure

```python
{
    "1x2": {
        "Home": {
            "max": [OddsPoint(...)],
            "min": [OddsPoint(...)],
            "avg": [OddsPoint(...)]
        },
        "Draw": {...},
        "Away": {...}
    },
    "Asian Handicap -0.5": {...},
    "Over/Under 2.5": {...}
}
```

### MatchContext

```python
{
    "home_last_5": [...],      # 主隊近 5 場
    "away_last_5": [...],      # 客隊近 5 場
    "h2h": [...],              # 對戰記錄
    "stats": {
        "home_weighted_xg": 1.5,
        "away_weighted_xg": 1.0,
        "league": "Premier League"
    },
    "glicko": {
        "home_rating": 1650,
        "away_rating": 1580,
        "win_prob": 0.62
    },
    "lineup": {...}
}
```

---

## 配置參數

### config.py

```python
# API 設定
ODDS_API_KEY = "your_key"
OPENAI_API_KEY = "your_key"
GROK_API_KEY = "your_key"

# 資金管理
INITIAL_BANKROLL = 1000
KELLY_FRACTION = 0.75
MIN_EDGE = 0.09

# 路徑設定
HISTORY_CSV_PATH = "data/big_five_history.csv"
EXCEL_FILEPATH = "Betting_Records.xlsx"
```

---

## 使用範例

### 完整分析流程

```python
from config import settings
from src.data_modules import HistoryRepo, RealOddsFetcher, LEAGUE_OPTIONS
from src.llm_clients import llm
from src.finance import calculate_kelly_stake, ExcelLogger
from src.math_models_v2 import OptimizedDixonColes, MonteCarloSimulator

# 1. 初始化
repo = HistoryRepo(settings.HISTORY_CSV_PATH)
fetcher = RealOddsFetcher()
logger = ExcelLogger()

# 2. 獲取數據
context = repo.get_match_context("Arsenal", "Chelsea", "Premier League")
odds = fetcher.get_real_odds("soccer_epl", "Arsenal", "Chelsea")

# 3. 數學模型
dc_model = OptimizedDixonColes(1.5, 1.0)
mc_sim = MonteCarloSimulator(1.5, 1.0)

# 4. LLM 分析
grok_analysis = llm.search_and_analyze_market_reaction("Arsenal vs Chelsea", odds)
decision = llm.analyze_with_super_prompt(context, odds, math_results)

# 5. 資金管理
stake_info = calculate_kelly_stake(0.65, 2.5, 1000)

# 6. 記錄
logger.log_bet(match_info, bet_info, stake_info)
```
