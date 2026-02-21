# ⚽ AI 足球博彩分析系統 (v7.0)

一個結合數學模型、機器學習與 LLM 的智能足球博彩分析系統。

## 🚀 快速開始

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

### 3. 訓練模型（可選，首次運行建議執行）
```bash
python scripts/train_model.py
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

### AI 整合
- **Grok** - 市場情報搜尋（傷停、陣容、新聞）
- **ChatGPT** - 模型 vs 市場對比、價值注識別

### 數據源
- **即時賠率**: The Odds API (全球 50+ 博彩公司)
- **傷停數據**: API-Football、Transfermarkt
- **歷史數據**: 本地 CSV (60+ 聯賽)

## 📁 項目結構

```
fb_ai_bets/
├── app.py                    # 🎯 主程式入口 (Streamlit UI)
├── config.py                 # 配置文件
├── src/                      # 核心程式碼
│   ├── math_models.py        # 數學模型 (整合版 v7.0)
│   ├── data_modules.py       # 數據處理
│   ├── llm_clients.py       # LLM 客戶端
│   ├── finance.py           # 資金管理
│   ├── advanced_models.py    # 高級模型 (xG, 貝葉斯, LSTM, RL)
│   └── ...
├── scripts/                  # 訓練腳本
│   └── train_model.py       # 模型訓練
├── data/                     # 數據目錄
│   ├── history_data.csv     # 歷史數據
│   └── lineup/               # 陣容數據
└── tests/                    # 測試文件
```

## 💰 資金管理

- **Kelly Fraction**: 0.75 (半 Kelly)
- **最小期望值門檻**: 9%
- **風險控制**: 三級風險狀態 (normal/warning/critical)

## 🔧 使用說明

### 命令行模式
```bash
# 訓練模型
python scripts/train_model.py

# 啟動 Web 介面
python app.py
```

### Web 介面
1. 選擇聯賽與比賽
2. 系統自動分析：
   - 歷史數據 (Glicko-2, xG, H2H)
   - 傷停與陣容
   - 多模型預測
   - 即時賠率
   - AI 市場情報
3. 顯示投注建議與金額

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

**版本**: v7.0 (整合版)  
**最後更新**: 2026-02-18
