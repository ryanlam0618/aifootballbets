# ai_fb_bets v2 (Prompt-aligned Refactor)

此版本按照更新版 prompt 重構，重點：

- 多場比賽輸入（可逐行）
- fixture 基本資料輸出 CSV
- The Odds API 僅作即時賠率（token-saving）
- 24h odds 變化改由 OddsPortal/OddsHarvester 輸出解析
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

# OddsPortal/OddsHarvester 24h 來源
ODDSHARVESTER_DATA_DIR=OddsHarvester
ODDSHARVESTER_CMD=
ODDS_API_MAX_LEAGUES_PER_RUN=4

# SofaScore lineup + missingPlayers (default OFF)
# 設成 1 才會在 ingest/team_news.collect_lineup_and_injury 啟用 SofaScore 公開 JSON endpoints
SOFASCORE_ENABLED=0
```

## SofaScore lineup / injury ingestion (optional, default OFF)

- 來源：SofaScore 公開 JSON endpoints（例如：
  - `/api/v1/sport/football/scheduled-events/YYYY-MM-DD`
  - `/api/v1/event/{event_id}/lineups`
  - `/api/v1/event/{event_id}`（備用 / debug）
- Raw JSON 落地：`data/v2/sofascore_raw/`（方便 backtest replay / debug）

啟用：

```bash
SOFASCORE_ENABLED=1 python -m v2.main --matches "soccer_epl|Fulham vs Arsenal"
```

Rate limit / etiquette（非常保守）：

- 每個 request 之間 sleep ~0.2s（module 內預設）
- 建議只在需要 lineup / missingPlayers 時啟用
- 若遇到 429/封鎖，請加大 sleep 或改用本地 raw replay

- `ODDSHARVESTER_DATA_DIR`：OddsHarvester 輸出 JSON 目錄（會在 24h 內掃描）
- `ODDSHARVESTER_CMD`：可選；每次 run 前先執行一次刷新命令
- `ODDS_API_MAX_LEAGUES_PER_RUN`：限制 The Odds API 每次最多查幾個聯賽，節省 token

> `GOOGLE_SERVICE_ACCOUNT_JSON` 內容可直接放 JSON 字串。
