# aifootballbets — 方法論鐵律 + 事故教訓

> 📌 每次 new agent 接手呢個 project 前必讀。來源：實際事故 + 業界研究（`docs/reports/seo/`）。

## 鐵律（方法論）

1. **Walk-forward / 零洩漏**：預測場波只准用賽前已知數據；唔准賽後數據（xG/射門/紅牌）訓練賽前模型；唔准收盤賠率預測收盤賠率；唔准隨機 K-Fold 切時間序列
2. **準確率 ≠ edge**：1X2 天花板 50-56%；真 KPI = **CLV**（去水位收市價擊敗率）；Shams 2024 實證 GBM 準但冇利潤
3. **計 CLV 前必先 de-vig**（Shin / power）；closing = 開賽前最後一次快照
4. **未校準機率 + Kelly = 破產**：模型輸出先校準（isotonic/temperature）再接 1/4 Kelly
5. **DB 寫入 backup 先行**：冇備份唔准郁 teams/matches/afb_odds_snapshots
6. **證據先改名**：teams 校準只准 lineup 球員名單 + W/D/L 指紋雙重驗證；唔夠證據如實留 suspect 唔准亂配
7. **INSERT IGNORE 冪等**：pipeline 重跑 = 0 寫入；uq_afb_pred 嘅 line 用空字串唔用 NULL（MySQL unique index 對 NULL 唔 dedupe）
8. **未驗證唔落真錢**：paper trading + 正 CLV 幾千注樣本先算數；HK 法律紅線 — repo 刻意唔做執行層

## 事故教訓（真事，勿重犯）

### 2026-11-07 xG 事件 🌟
- Duncan 跟 Scout 業界報告印象講「缺 xG 教材」— **冇查 DB**。Kris 糾正「我地有xG喎」→ 實查：match_shotmap 766K rows、afb_team_rolling_xg 21K rows、expected_goals 欄位齊全
- **教訓：講任何數據有冇，必查 DB 或 data-catalog.md，唔准跟報告/印象講咗算**

### 2026-11-07 「模型層未開工」事件 🌟
- Duncan 今晚多次講「部門 4 模型層未開工、等拍板」— **冇查 artifacts**。實況：layer2 T1-T13 早已 2026-10-28~31 全部 completed（DC/pi-ratings/校準/xG/market-blend/pipeline）
- **教訓：講「做咗/未做」必查 docs/reports/ + project-state.md；派工前先查有冇現成 artifact（可能已做過，白俾一份工）**

### 2026-11-07 「校準層漏咗」半錯事件
- Duncan 對比業界報告話「校準層要加」— 實際 T2 calibration 10-31 已做（isotonic/temperature/grouped-T）
- **教訓同上：對比「我哋有冇 X」時先查 layer2 artifacts**

### 2026-10-31 SEO「講咗開始搜就收工」
- Scout LLM 話咗開始搵就當做咗 → 已糾正：**只有 Kris TG 親口拍板先算數**；agent 講「會做」唔等於「做咗」

### 2026-10-31 T5 冪等 bug
- 首版重跑欠寫 270 行：predictions line=NULL（unique index 唔 dedupe NULL）→ 修復 line=""；db_write_predictions 將 "" 轉 None → 修復保留空字串

### 業界血淚（管理期望）
- Kaunitz 2017：模擬 44% ROI → 實戰 8.5% → 5 個月封帳
- Starlizard（£600m/年）：模型只係入場券，模型+資金+執行+法律四位一體
- T4 blend 實測（10-31）：market w=0 最優 — 模型 v1 跑唔贏 de-vig 市場，如實記錄唔粉飾
