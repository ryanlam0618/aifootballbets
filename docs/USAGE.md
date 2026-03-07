# 使用指南

## 📖 目錄

1. [安裝與配置](#安裝與配置)
2. [基本使用](#基本使用)
3. [進階功能](#進階功能)
4. [常見問題](#常見問題)

## 安裝與配置

### 1. 安裝 Python 依賴

```bash
pip install -r requirements.txt
```

### 2. 配置 API 金鑰

複製 `.env.example` 為 `.env`：

```bash
cp .env.example .env
```

然後編輯 `.env` 文件，填入你的 API 金鑰：

```env
ODDS_API_KEY=你的_odds_api_金鑰
OPENAI_API_KEY=你的_openai_金鑰
GROK_API_KEY=你的_grok_金鑰
GEMINI_API_KEY=你的_gemini_金鑰
```

### 3. 測試模式（驗證安裝）

```bash
python app.py test
```

這會使用模擬數據測試所有組件是否正常運作。

### 3. 下載歷史數據（可選）

```bash
python scripts/TakeHistoryData.py
```

這會從 football-data.co.uk 下載 2020-2024 賽季的五大聯賽數據。

## 基本使用

### 執行主程式

```bash
python app.py
```

### 操作流程

1. **選擇聯賽**: 輸入數字選擇目標聯賽（1-61）
2. **輸入比賽**: 格式為 `主隊 vs 客隊`，例如：`Bournemouth vs Tottenham`
3. **查看分析**: 系統會自動執行以下步驟：
   - 歷史數據分析
   - 陣容評分
   - 數學模型預測
   - 即時賠率獲取
   - Grok 市場情報搜尋
   - GPT-4 綜合決策
4. **資金管理**: 系統會自動計算建議投注金額
5. **記錄投注**: 選擇是否記錄到 Excel

## 進階功能

### 訓練機器學習模型

```bash
python scripts/train_model.py
```

這會訓練一個 XGBoost 模型並儲存為 `xgb_model.pkl`。

### 使用模型評估框架

```python
from src.model_evaluation import CrossValidator, Backtester, DataValidator

# 數據驗證
validator = DataValidator()
result = validator.validate_match_data(df)
print(f"數據質量分數: {result['quality_score']}")

# 交叉驗證
cv = CrossValidator(n_splits=5)
metrics = cv.evaluate_model(df, my_prediction_function)

# 回測
backtester = Backtester(initial_bankroll=10000)
result = backtester.run_backtest(df, prediction_fn)
print(f"ROI: {result.roi * 100:.2f}%")
```

### 使用投注策略

```python
from src.math_models_v3 import ConfidenceKelly, DutchingCalculator, PortfolioKelly

# 信心度 Kelly
kelly = ConfidenceKelly(base_fraction=0.5)
result = kelly.calculate(prob=0.55, odds=2.0, confidence=0.8)
print(f"建議投注: ${result.stake:.2f}")

# Dutching
dutching = DutchingCalculator(target_return=1.0)
odds = {'home': 2.0, 'draw': 3.5, 'away': 4.0}
result = dutching.calculate(odds_dict=odds, total_stake=100)
print(result['bets'])

# 組合 Kelly
portfolio = PortfolioKelly([kelly], risk_tolerance='moderate')
results = portfolio.allocate_bets(bets, bankroll, markets, outcomes)
```

### 模型監控

```python
from src.model_evaluation import ModelMonitor

monitor = ModelMonitor("my_model")
monitor.set_baseline(metrics)

# 記錄預測
monitor.record_prediction(features, prediction, actual)

# 檢查漂移
drift_report = monitor.check_performance_drift()
print(f"狀態: {drift_report['status']}")
```

### 測試 API 連線

```bash
python tests/test_api.py
```

### 測試 Grok 即時搜尋

```bash
python tests/test_web_search.py
```

### 驗證聯賽配置

```bash
python tests/test_leagues.py
```

### 清理快取

```bash
python tests/test_debug.py
```

## 常見問題

### Q: 為什麼找不到比賽？

A: 請確認：
1. 隊名拼寫正確（系統會自動模糊匹配）
2. 該聯賽在 The Odds API 有提供數據
3. 比賽時間在近期（API 通常只提供未來 7 天的比賽）

### Q: 為什麼 Grok 搜尋失敗？

A: 可能原因：
1. API 金鑰錯誤或過期
2. 網路連線不穩定
3. API 服務暫時不可用

解決方法：執行 `python tests/test_api.py` 診斷連線問題。

### Q: 如何調整資金管理參數？

A: 編輯 `.env`（或環境變數）：

```env
INITIAL_BANKROLL=1000
KELLY_FRACTION=0.75
MIN_EDGE=0.09
```

### Q: Excel 記錄失敗？

A: 請確認：
1. Excel 文件未被其他程式開啟
2. 有寫入權限
3. 路徑設定正確（`.env` 中的 `GDRIVE_PATH` / `EXCEL_FILENAME`）

### Q: 如何添加新聯賽？

A: 編輯 `src/data_modules.py` 中的 `LEAGUE_OPTIONS`：

```python
"62": {"name": "新聯賽名稱", "key": "soccer_league_key"}
```

聯賽 key 請參考 [The Odds API 文檔](https://the-odds-api.com/sports-odds-data/sports-apis.html)。

## 技術支援

如有問題，請提交 Issue 或聯繫開發團隊。
