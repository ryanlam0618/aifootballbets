# ai_fb_bets v2 (Prompt-aligned Refactor)

此版本按照更新版 prompt 重構，重點：

- 多場比賽輸入（可逐行）
- fixture 基本資料輸出 CSV
- The Odds API 24h odds snapshot + 變化 CSV
- T-60 才觸發 Grok web research（X 平台）
- 首發與傷停整合（lineup text + injuries.csv）
- features_master.csv（含 prompt 要求的大部分核心欄位，缺失用 NA）
- 計數模型整合（Poisson + Dixon-Coles + Negative Binomial）
- 只分析三市場：1X2 / Asian Handicap / Over-Under
- bankroll 第二階段輸入後做下注分配（Kelly + 風險上限）
- 輸出 betting_recommendations.csv + betting_records.xlsx + summary_report.md
- 支援 Google Drive 同步（掛載路徑或 service account）

## Quick Start

```bash
cd aifootballbets
python -m v2.main --matches "soccer_epl|Arsenal vs Chelsea" "soccer_epl|Liverpool vs Man City"
```

或互動模式：

```bash
python -m v2.main
```

## Output

- `data/v2/fixtures_master.csv`
- `data/v2/odds_24h.csv`
- `data/v2/injuries.csv`
- `data/v2/features_master.csv`
- `data/v2/lineup_texts/*_lineup_text.txt`
- `reports/v2/betting_recommendations.csv`
- `reports/v2/betting_records.xlsx`
- `reports/v2/summary_report.md`

## Env (新增可選)

`.env` 可新增：

```env
GOOGLE_DRIVE_FOLDER_ID=
GOOGLE_SERVICE_ACCOUNT_JSON=
DEFAULT_TIMEZONE=Asia/Hong_Kong
```

> `GOOGLE_SERVICE_ACCOUNT_JSON` 內容可直接放 JSON 字串。
