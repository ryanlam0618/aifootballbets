# ⚽ AI 足球分析系統 v6.5

一個結合數學模型、機器學習與 LLM 的智能足球博彩分析系統。

## 功能特色

### 核心模型
- **數學模型 v3**: 負二項分布、動態 K Elo、蒙地卡羅 V3
- **高級模型**: 指數衰減 xG、貝葉斯進球、LSTM 時序、RL 投注優化
- **機器學習**: Stacking Ensemble (XGBoost + Random Forest + Gradient Boosting)
- **Glicko-2 評分**: 帶置信區間的球隊實力評估

### AI 整合
- **Grok 市場情報**: 聯網搜尋最新傷停、陣容與新聞
- **ChatGPT 決策**: 模型 vs 市場對比、價值注識別

### 數據源
- **即時賠率**: The Odds API (全球 50+ 博彩公司)
- **傷停數據**: API-Football、Transfermarkt
- **歷史數據**: 本地 CSV (支持 60+ 聯賽)

## 專案結構

```
fb_ai_bets/
├── app.py                    # 主程式入口 (v6.5)
├── app_v3.py                 # v3 專用版本
├── config.py                 # 配置文件 (環境變量)
├── requirements.txt          # Python 依賴
│
├── src/                      # 核心程式碼
│   ├── advanced_models.py    # 高級模型 (LSTM, RL, 貝葉斯)
│   ├── math_models.py        # 基礎數學模型
│   ├── math_models_v2.py     # Glicko-2、陣容模型
│   ├── math_models_v3.py     # v3 模型 (負二項、動態 K)
│   ├── data_modules.py       # 數據模組
│   ├── injury_api.py         # 傷停 API
│   ├── injury_data.py        # 傷停數據處理
│   ├── lineup_api.py         # 陣容 API
│   ├── llm_clients.py        # LLM 客戶端
│   ├── networking_llm.py     # 聯網 LLM
│   └── finance.py            # 資金管理
│
├── scripts/                  # 訓練腳本
│   ├── train_model.py        # XGBoost 訓練
│   ├── train_model_v2.py     # v2 訓練
│   ├── train_model_v3.py     # Stacking Ensemble 訓練
│   └── train_model_with_injury.py
│
├── tests/                    # 測試文件
├── data/                     # 數據目錄
│   ├── history_data.csv      # 歷史數據
│   └── lineup/               # 陣容 JSON
├── archive/                  # 歸檔 (舊版腳本)
├── docs/                     # 文檔
└── OddsHarvester/            # 賠率爬蟲
```

## 快速開始

### 1. 安裝依賴
```bash
pip install -r requirements.txt
```

### 2. 配置環境變量

複製範例文件並填入 API Keys：
```bash
copy env.example .env
```

編輯 `.env`：
```env
ODDS_API_KEY=your_odds_api_key
OPENAI_API_KEY=your_openai_key
GROK_API_KEY=your_grok_key
API_FOOTBALL_KEY=your_football_key
```

### 3. 執行主程式
```bash
python app.py
```

## 數學模型

### v3 核心模型
| 模型 | 功能 | 輸出 |
|------|------|------|
| Negative Binomial | 過離散進球建模 | 進球分佈 |
| Dynamic K Elo | 自適應 K 因子 | 評分變化 |
| Monte Carlo V3 | Gamma-Poisson 模擬 | 10,000 次預測 |
| Confidence Kelly | 信心度調整 | 投注金額 |

### 高級模型
| 模型 | 功能 | 輸出 |
|------|------|------|
| Exponential Decay xG | 指數衰減加權 | 動態 xG |
| Bayesian Goal | 貝葉斯推斷 | 置信區間 |
| LSTM Form | 時序狀態追蹤 | 趨勢預測 |
| RL Betting | Q-Learning 策略 | 最優投注 |

## 支援的聯賽

60+ 足球聯賽，包括：
- 五大聯賽 (英超、西甲、德甲、義甲、法甲)
- 歐洲杯賽 (歐冠、歐霸、歐協聯)
- 其他歐洲聯賽 (荷甲、葡超、蘇超等)
- 美洲聯賽 (MLS、巴甲、阿甲)
- 亞洲聯賽 (J聯賽、K聯賽)
- 國際賽事 (世界盃、國家聯賽)

## 分析流程

```
1. 選擇聯賽與比賽
      ↓
2. 歷史數據分析 (Glicko-2, xG, H2H)
      ↓
3. 傷停與陣容評估
      ↓
4. 多模型預測 (v3 + 高級模型)
      ↓
5. 即時賠率獲取 (The Odds API)
      ↓
6. Grok 市場情報搜尋
      ↓
7. GPT-4 綜合決策
      ↓
8. Kelly + RL 資金管理
      ↓
9. Excel 記錄與追蹤
```

## 資金管理

- **Kelly Fraction**: 0.75 (半 Kelly)
- **最小期望值門檻**: 9%
- **RL 風險調整**: Q-Learning 自動優化

## 免責聲明

本系統僅供學學術研究與教育用途。博彩涉及風險，請謹慎評估並遵守當地法律。

---

**版本**: v6.5  
**最後更新**: 2026-02-06
