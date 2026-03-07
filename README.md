# ⚽ AI 足球博彩分析系統 (v7.1)

一個結合數學模型、機器學習與 LLM 的智能足球博彩分析系統。

## 🚀 快速開始

### 1. 安裝依賴
```bash
pip install -r requirements.txt
```

### 2. 配置環境變量

複製範例文件並填入 API Keys：
```bash
# macOS / Linux
cp .env.example .env

# Windows (PowerShell)
Copy-Item .env.example .env
```

編輯 `.env`：
```env
ODDS_API_KEY=your_odds_api_key
OPENAI_API_KEY=your_openai_key
GROK_API_KEY=your_grok_key
API_FOOTBALL_KEY=your_football_key
GEMINI_API_KEY=your_gemini_key
```

### 3. 測試模式（驗證安裝）
```bash
python app.py test
```

### 4. 啟動主程式
```bash
python app.py
```

## 📊 功能特色

### 核心預測模型
| 模型 | 功能 | 說明 |
|------|------|------|
| **Poisson** | 基礎進球建模 | 經典統計模型 |
| **Negative Binomial** | 過離散進球 | 解決 Poisson 方差問題 |
| **Dixon-Coles** | 低比分校正 | 修正 0-0, 1-1 相關性 |
| **Glicko-2** | 球隊評分 | 含置信區間的實力評估 |
| **Dynamic K Elo** | 動態評分 | 自適應 K 因子的實力系統 |
| **Monte Carlo** | 模擬預測 | 10,000+ 次模擬，支持多種投注市場 |

### 高級 AI 模型
| 模型 | 功能 | 說明 |
|------|------|------|
| **指數衰減 xG** | 時間加權 xG | 近期比赛權重更高 |
| **貝葉斯進球** | 不確定性量化 | 置信區間估計 |
| **LSTM 狀態** | 時序模式識別 | 球隊形態追蹤 |
| **xGOT 效率** | 射門質量評估 | 進球轉化率分析 |
| **防守質量模型** | 防守能力評估 | 失球模式分析 |
| **射門位置模型** | 射門風格分析 | 進球位置分佈 |

### 投注策略
| 策略 | 功能 | 說明 |
|------|------|------|
| **Confidence Kelly** | 信心度調整 | 波動率、連勝/連敗追蹤 |
| **Portfolio Kelly** | 組合管理 | 多元化投資、風險分散 |
| **Dutching** | 荷蘭投注 | 多選項同時投注 |
| **Betting RL Agent** | 強化學習 | Q-Learning 策略優化 |

### 數據驗證與監控
| 功能 | 說明 |
|------|------|
| **CrossValidator** | 時間序列交叉驗證 |
| **Backtester** | 歷史回測系統 |
| **ModelMonitor** | 性能漂移檢測 |
| **DataValidator** | 異常值檢測與清洗 |

### AI 整合
- **Gemini** - 球隊名稱智能匹配
- **Grok** - 市場情報搜尋（傷停、陣容、新聞）
- **ChatGPT** - 模型 vs 市場對比、價值注識別

### 數據源
- **即時賠率**: The Odds API (全球 50+ 博彩公司)
- **傷停數據**: API-Football、Transfermarkt
- **陣容數據**: SofaScore
- **歷史數據**: 本地 CSV (60+ 聯賽)

## 📁 項目結構

```
fb_ai_bets/
├── app.py                    # 🎯 主程式入口
├── config.py                 # 配置文件
├── src/                      # 核心程式碼
│   ├── math_models.py        # 數學模型 (基礎版)
│   ├── math_models_v2.py     # 數學模型 (v2)
│   ├── math_models_v3.py     # 數學模型 (v3 - ML集成)
│   ├── advanced_models.py    # 高級模型 (xG, 貝葉斯, LSTM, RL)
│   ├── model_evaluation.py    # 模型評估與監控
│   ├── feature_engineering.py # 特徵工程
│   ├── corner_models.py      # 角球預測模型
│   ├── data_modules.py       # 數據處理
│   ├── llm_clients.py        # LLM 客戶端
│   ├── finance.py            # 資金管理
│   ├── lineup_api.py         # 陣容 API
│   ├── injury_api.py         # 傷停 API
│   └── league_parameter_estimator.py # 聯賽參數估計
├── scripts/                  # 訓練腳本
│   └── train_model.py        # 模型訓練
├── data/                     # 數據目錄
│   ├── history_data.csv      # 歷史數據
│   └── lineup/               # 陣容數據
├── docs/                     # 文檔
│   ├── USAGE.md             # 使用指南
│   ├── API.md               # API 參考
│   └── STRUCTURE.md         # 結構說明
└── tests/                    # 測試文件
```

## 💰 資金管理

- **Kelly Fraction**: 0.75 (半 Kelly)
- **最小期望值門檻**: 8%
- **風險控制**: 三級風險狀態 (normal/warning/critical)
- **冷卻期**: 連續失敗後自動暫停
- **波動率調整**: 根據歷史波動自動調整投注

## 🔧 使用說明

### 命令行模式
```bash
# 測試模式（驗證安裝）
python app.py test

# 訓練模型
python scripts/train_model.py

# 啟動主程式
python app.py
```

### 輸入格式
```
👉 請輸入比賽對戰組合 (Enter 預設 Bournemouth vs Tottenham): Manchester United vs Liverpool
```

### 輸出示例
```
========== 💡 最終推薦結果 ==========
下注項目: [1x2] Home
模型勝率: 55.0% vs 市場隱含: 48.0%
分析理由: ...

💰 資金管理...
   >>> 建議下注: $50.00 (EV: 0.125)
```

## 📈 支援聯賽

60+ 足球聯賽，包括：
- 五大聯賽 (英超、西甲、德甲、義甲、法甲)
- 歐洲杯賽 (歐冠、歐霸、歐協聯)
- 亞洲聯賽 (J聯賽、K聯賽)
- 美洲聯賽 (MLS、巴甲)
- 國際賽事 (世界盃、國家聯賽)

## ⚠️ 免責聲明

本系統僅供學術研究與教育用途。博彩涉及風險，請謹慎評估並遵守當地法律。

---

**版本**: v7.1 (AI 整合版)  
**最後更新**: 2026-02-22
