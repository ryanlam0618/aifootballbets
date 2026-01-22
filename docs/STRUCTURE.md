# 專案結構說明

## 📁 目錄結構

```
fb_ai_bets/
│
├── app.py                      # 主程式入口
├── config.py                   # 全域配置文件
├── requirements.txt            # Python 依賴套件清單
├── .env.example                # 環境變數範例文件
├── .gitignore                  # Git 忽略規則
├── README.md                   # 專案說明文件
│
├── src/                        # 核心程式碼目錄
│   ├── __init__.py             # 模組初始化文件
│   ├── data_modules.py         # 數據模組
│   ├── llm_clients.py          # LLM 客戶端
│   ├── networking_llm.py       # 聯網 LLM 功能
│   ├── finance.py              # 資金管理
│   ├── math_models.py          # 數學模型 v1
│   └── math_models_v2.py       # 數學模型 v2
│
├── tests/                      # 測試文件目錄
│   ├── __init__.py
│   ├── test_api.py             # API 連線測試
│   ├── test.py                 # Grok 搜尋測試
│   ├── test_leagues.py         # 聯賽配置測試
│   └── test_debug.py           # 快取清理工具
│
├── scripts/                    # 工具腳本目錄
│   ├── __init__.py
│   ├── TakeHistoryData.py      # 歷史數據下載
│   └── train_model.py          # 模型訓練腳本
│
├── docs/                       # 文檔目錄
│   ├── USAGE.md                # 使用指南
│   ├── API.md                  # API 文檔
│   └── STRUCTURE.md            # 專案結構說明（本文件）
│
├── data/                       # 數據目錄
│   ├── big_five_history.csv    # 五大聯賽歷史數據
│   ├── odds.csv                # 賠率數據
│   └── lineup/                 # 陣容 JSON 文件
│
├── OddsHarvester/              # 賠率爬蟲模組（第三方）
└── TakeData/                   # 數據爬取工具
```

## 📄 核心文件說明

### app.py
主程式入口，負責：
- 用戶交互界面
- 流程協調
- 結果展示

### config.py
全域配置文件，包含：
- API 金鑰設定
- 路徑配置
- 資金管理參數
- 模型名稱設定

### requirements.txt
Python 依賴套件清單，包含所有必要的第三方庫。

## 🔧 src/ 目錄

### data_modules.py
數據模組，包含：
- `HistoryRepo`: 歷史數據儲存庫
- `RealOddsFetcher`: 即時賠率獲取器
- `LEAGUE_OPTIONS`: 聯賽配置字典
- `OddsAnalyzer`: 賠率分析器

### llm_clients.py
LLM 客戶端協調器，整合：
- GPT-4: 綜合決策分析
- Grok: 市場情報搜尋
- Gemini: 數據輔助（可選）

### networking_llm.py
聯網 LLM 功能模組，提供：
- Web Search 整合
- X (Twitter) 搜尋
- 即時新聞獲取

### finance.py
資金管理模組，包含：
- `calculate_kelly_stake()`: Kelly Criterion 計算
- `ExcelLogger`: Excel 記錄器

### math_models.py
數學模型 v1，包含：
- `PoissonModel`: 泊松分佈模型
- `DixonColesModel`: Dixon-Coles 模型
- `MonteCarloSimulator`: 蒙地卡羅模擬
- `EloSystem`: Elo 評分系統

### math_models_v2.py
數學模型 v2（進階版），包含：
- `Glicko2System`: Glicko-2 評分系統
- `LineupModel`: 陣容評分模型
- `OptimizedDixonColes`: 優化版 Dixon-Coles
- `MonteCarloSimulator`: 進階蒙地卡羅模擬

## 🧪 tests/ 目錄

### test_api.py
API 連線診斷工具，用於測試：
- API 金鑰有效性
- 網路連線狀態
- 模型可用性

### test.py
Grok 即時搜尋測試，驗證：
- Web Search 功能
- X (Twitter) 搜尋
- 時效性驗證

### test_leagues.py
聯賽配置驗證工具，檢查：
- 聯賽數量
- 配置完整性
- 分類統計

### test_debug.py
快取清理工具，用於：
- 清理 `__pycache__`
- 解決模組載入問題

## 🛠️ scripts/ 目錄

### TakeHistoryData.py
歷史數據下載腳本，功能：
- 從 football-data.co.uk 下載數據
- 支援五大聯賽
- 自動清理與轉換

### train_model.py
機器學習模型訓練腳本，功能：
- 特徵工程
- XGBoost 模型訓練
- 模型評估與儲存

## 📚 docs/ 目錄

### USAGE.md
使用指南，包含：
- 安裝與配置步驟
- 基本使用教學
- 進階功能說明
- 常見問題解答

### API.md
API 文檔，包含：
- 核心模組 API 說明
- 數據結構定義
- 使用範例

### STRUCTURE.md
專案結構說明（本文件）。

## 📊 data/ 目錄

### big_five_history.csv
五大聯賽歷史數據，包含：
- 比賽日期
- 球隊名稱
- 比分
- 統計數據（射門、角球等）
- 賠率數據

### lineup/
陣容 JSON 文件目錄，格式：
```json
{
  "home_team": {
    "starters": [
      {"name": "Player Name", "rating": 7.5, "position": "FW"}
    ]
  },
  "away_team": {...}
}
```

## 🔄 數據流程

```
用戶輸入
    ↓
app.py (主程式)
    ↓
├─→ data_modules.py (獲取歷史數據)
├─→ math_models_v2.py (數學模型預測)
├─→ data_modules.py (獲取即時賠率)
├─→ llm_clients.py (Grok 市場情報)
├─→ llm_clients.py (GPT-4 綜合決策)
└─→ finance.py (資金管理 & 記錄)
    ↓
結果輸出
```

## 🔐 配置文件

### .env
環境變數文件（不納入版本控制），包含：
- API 金鑰
- 敏感配置

### .env.example
環境變數範例文件，提供配置模板。

### .gitignore
Git 忽略規則，排除：
- `__pycache__/`
- `.env`
- 數據文件
- 模型文件

## 📦 依賴管理

所有 Python 依賴套件列於 `requirements.txt`，主要包括：
- `pandas`: 數據處理
- `numpy`: 數值計算
- `scipy`: 科學計算
- `openai`: OpenAI API 客戶端
- `requests`: HTTP 請求
- `openpyxl`: Excel 操作
- `xgboost`: 機器學習
- `scikit-learn`: 機器學習工具

## 🚀 擴展指南

### 添加新聯賽
編輯 `src/data_modules.py` 中的 `LEAGUE_OPTIONS`。

### 添加新模型
在 `src/math_models_v2.py` 中創建新類別。

### 添加新 LLM
在 `src/llm_clients.py` 中添加新方法。

### 添加新測試
在 `tests/` 目錄中創建新測試文件。
