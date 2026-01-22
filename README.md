# ⚽ AI 足球分析系統 v6.0

一個結合數學模型、機器學習與 LLM 的智能足球博彩分析系統。

## 📋 功能特色

- **多模型預測**: 整合 Glicko-2、Dixon-Coles、蒙地卡羅模擬等數學模型
- **即時賠率分析**: 透過 The Odds API 獲取全球博彩公司即時賠率
- **AI 決策引擎**: 使用 GPT-4 與 Grok 進行綜合分析與市場情報搜尋
- **陣容評分系統**: 基於球員評分的首發陣容強度分析
- **資金管理**: Kelly Criterion 最佳化投注策略
- **Excel 記錄**: 自動記錄投注歷史與績效追蹤

## 🗂️ 專案結構

```
fb_ai_bets/
├── app.py                  # 主程式入口
├── config.py               # 配置文件
├── requirements.txt        # Python 依賴套件
├── src/                    # 核心程式碼
│   ├── data_modules.py     # 數據模組（歷史數據、賠率獲取）
│   ├── llm_clients.py      # LLM 客戶端（GPT、Grok）
│   ├── networking_llm.py   # 聯網 LLM 模組
│   ├── finance.py          # 資金管理與 Excel 記錄
│   ├── math_models.py      # 數學模型 v1
│   └── math_models_v2.py   # 數學模型 v2（Glicko-2、陣容模型）
├── scripts/                # 工具腳本
│   ├── TakeHistoryData.py  # 歷史數據下載腳本
│   └── train_model.py      # 機器學習模型訓練
├── tests/                  # 測試文件
│   ├── test_api.py         # API 連線測試
│   ├── test.py             # Grok 搜尋測試
│   ├── test_leagues.py     # 聯賽配置測試
│   └── test_debug.py       # 快取清理工具
├── data/                   # 數據目錄
│   ├── big_five_history.csv    # 五大聯賽歷史數據
│   ├── odds.csv                # 賠率數據
│   └── lineup/                 # 陣容 JSON 文件
├── docs/                   # 文檔目錄
└── OddsHarvester/          # 賠率爬蟲模組（第三方）
```

## 🚀 快速開始

### 1. 安裝依賴

```bash
pip install -r requirements.txt
```

### 2. 配置 API 金鑰

在 `config.py` 中設定以下 API 金鑰：

```python
ODDS_API_KEY = "your_odds_api_key"      # The Odds API
OPENAI_API_KEY = "your_openai_key"      # GPT-4
GROK_API_KEY = "your_grok_key"          # Grok (xAI)
```

### 3. 下載歷史數據（可選）

```bash
python scripts/TakeHistoryData.py
```

### 4. 執行主程式

```bash
python app.py
```

## 📊 支援的聯賽

系統支援 60+ 個足球聯賽，包括：

- **五大聯賽**: 英超、西甲、德甲、義甲、法甲
- **歐洲杯賽**: 歐冠、歐霸、歐協聯
- **其他歐洲聯賽**: 荷甲、葡超、蘇超等
- **美洲聯賽**: MLS、墨超、巴甲、阿甲
- **亞洲聯賽**: 中超、J聯賽、K聯賽
- **國際賽事**: 世界盃、歐洲國家盃等

完整列表請參考 `src/data_modules.py` 中的 `LEAGUE_OPTIONS`。

## 🧠 分析流程

1. **選擇聯賽與比賽**: 從 60+ 個聯賽中選擇目標比賽
2. **歷史數據分析**: 
   - Glicko-2 評分系統計算球隊實力
   - 加權 xG（預期進球）計算
   - 近期戰績與對戰記錄分析
3. **陣容評分**: 基於首發球員評分預測勝率
4. **數學模型預測**:
   - Dixon-Coles 模型
   - 蒙地卡羅模擬（10,000 次）
   - 亞洲盤口機率計算
5. **即時賠率獲取**: 透過 The Odds API 獲取多家博彩公司賠率
6. **Grok 市場情報**: 聯網搜尋最新傷停、陣容與新聞
7. **GPT-4 綜合決策**: 
   - 模型勝率 vs 市場隱含勝率對比
   - 異常檢測（模型失真警告）
   - 價值注識別
8. **Kelly Criterion 資金管理**: 計算最佳投注金額
9. **Excel 記錄**: 自動記錄投注與績效追蹤

## 🔧 測試工具

```bash
# 測試 API 連線
python tests/test_api.py

# 測試 Grok 即時搜尋
python tests/test.py

# 驗證聯賽配置
python tests/test_leagues.py

# 清理快取
python tests/test_debug.py
```

## 📈 資金管理

系統使用 **Kelly Criterion** 計算最佳投注比例：

- **Kelly Fraction**: 0.75（保守型）
- **最小期望值門檻**: 9%
- **自動風險控管**: EV < 0 時不建議下注

## ⚠️ 免責聲明

本系統僅供學術研究與教育用途。博彩涉及風險，請謹慎評估並遵守當地法律。

## 📝 授權

本專案採用 MIT 授權條款。

## 🤝 貢獻

歡迎提交 Issue 或 Pull Request！

---

**版本**: v6.0  
**最後更新**: 2026-01-23
