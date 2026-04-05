# AI Football Bets — `clawbot_v2`

此分支只保留 **v2 管線** + **資料爬蟲（TakeData）**。

> v1 程式（`app.py` / `src/` / 舊 docs）已移除；目前保留的是 v2 專用 `scripts/` 與 `tests/`。

---

## 主要目錄

- `v2/`：v2 預測與報表流程
- `TakeData/`：歷史/即時資料爬蟲
- `data/`：資料輸出目錄（多數為執行產物，不建議入版控）

---

## 快速開始（v2）

```bash
pip install -r requirements.txt
python -m v2.main --help
```

### 環境安裝（無 ensurepip / 無 sudo）

若系統 Python 沒有 `pip`/`ensurepip`，可直接執行：

```bash
bash scripts/setup_env.sh
```

此腳本會：
- 用 `get-pip.py` 安裝使用者層級 pip（`~/.local/bin/pip`）
- 安裝 `virtualenv`（user site）
- 建立專案內 `.venv`
- 安裝 `requirements.txt` + `lxml`
- 驗證 `dotenv/requests/pandas` 匯入與 `scripts/paper_one_day.py --help`

重建 `.venv`：

```bash
bash scripts/setup_env.sh --recreate
```

範例：

```bash
python -m v2.main --matches "soccer_epl|Arsenal vs Chelsea"
```

---

## Paper Trading（7-day value betting）

新模組：`v2/paper/`

- 聯賽池（單一合併策略）：Big-5 + J1 + K League 1 + A-League Men + CSL
- 每場比賽產生 1X2 / O/U / AH 候選，僅選一筆最佳注單（分數：fractional Kelly log-growth）
- 風險規則：若當日累積 PnL <= 當日起始 bankroll 的 -20%，當日停止新增注單
- 初始 bankroll：`INITIAL_BANKROLL`（預設 2000）
- 寫入：append-only 到 `data/v2/tracking/bets.sqlite` (`bet_log`)

常用指令：

```bash
# 單日：選注並寫入 bet_log
python -m v2.paper.run_day --date 2026-03-15

# 單日：依 ESPN 比分結算
python -m v2.paper.settle --date 2026-03-15

# 單日：輸出 daily + weekly 報告
python -m v2.paper.report --date 2026-03-15 --sqlite data/v2/tracking/bets.sqlite

# 7 日流程（每天：選注 -> 結算 -> 出報告）
python scripts/paper_run_7d.py --bankroll 2000 --sqlite data/v2/tracking/bets.sqlite

# 一鍵可重現 7-day（預設 bankroll=2000，直接輸出 final PnL/ROI/maxDD）
python scripts/paper_run_7d_repro.py

# 可重播（deterministic）模式（自訂路徑）
python scripts/paper_run_7d.py \
  --start-date 2026-03-10 \
  --provider-json tests/fixtures/paper7d_provider.json \
  --sqlite data/v2/tracking/bets.sqlite
```

最終會輸出 7 天總結（含 final PnL / ROI / max drawdown / winrate / avg edge / by market / flat-stake baseline）。

READY 檢查清單請見：`v2/paper/README.md`

---

## Odds Sources

此 repo 目前使用：
- SofaScore（fixtures/results/features）
- The Odds API（realtime odds）

> ✅ OddsPortal 相關 kickoff tracker / 歷史回填 / mysql schema / scripts 已全面移除。

# (OddsPortal tracker removed)
# (This section kept only as a placeholder for future odds tracking integrations)

## PP88 Match Watcher（MySQL 模板重播）

新增腳本：
- `scripts/pp88_watcher.js`：匯出 `watchMatchOdds({...})`
- `scripts/pp88_watch_cli.js`：CLI wrapper（由 env 控制）

### 支援 env 參數

- `HOME_NEEDLE`（必要）
- `AWAY_NEEDLE`（必要）
- `QUERY`（可選，額外關鍵字）
- `INTERVAL_SEC`（預設 30）
- `TIMEOUT_SEC`（預設 1800）
- `LIST_ENDPOINT`（可選：預設會依序嘗試 `popularRecommendPB`、`getAddedOddsMatchesPB`）
- `ALL_MARKETS`（`1` 開啟全部市場）
- `DRY_RUN`（`1`：只印出解析到的 MID 並結束）
- `ONCE`（`1`：單次掃描，不輪詢）
- `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`（或 `DB_PASS`）, `DB_NAME`

### 執行方式

```bash
HOME_NEEDLE="Arsenal" \
AWAY_NEEDLE="Chelsea" \
QUERY="premier league" \
INTERVAL_SEC=20 \
TIMEOUT_SEC=900 \
ALL_MARKETS=1 \
DB_HOST=127.0.0.1 \
DB_PORT=3306 \
DB_USER=myuser \
DB_PASSWORD=mypass \
DB_NAME=odds_capture \
node scripts/pp88_watch_cli.js
```

成功後會輸出 CSV 到：
- `reports/pp88/<timestamp>_<home>_vs_<away>.csv`

### Smoke / dry-run

```bash
HOME_NEEDLE="Arsenal" \
AWAY_NEEDLE="Chelsea" \
DRY_RUN=1 \
ONCE=1 \
DB_HOST=127.0.0.1 \
DB_USER=myuser \
DB_PASSWORD=mypass \
DB_NAME=odds_capture \
node scripts/pp88_watch_cli.js
```

若成功解析，會輸出類似：
- `[pp88 dry-run] resolved MID=123456 :: Arsenal vs Chelsea`

---

## 主要爬蟲腳本

- `TakeData/sofa_score/backfill_10y_leagues_cups.py`
- `TakeData/sofa_score/shotmap_xg_backfill.py`
- `TakeData/sofa_score/shotmap_detail_backfill.py`
- `TakeData/sofa_score/backfill_event_odds_10y.py`
- `TakeData/sofa_score/run_sofascore_season_backfill.py`（新增：按賽季一鍵 backfill）
- `TakeData/odds_batch_scraper.py`（已停用/可選：如需請另接入合法來源）

---

## Season-by-season 歷史回填（SofaScore）

（已移除 OddsPortal 歷史回填/追蹤；如需歷史 odds，建議接入合規 API 或自有數據源。）

### 前置需求

1. Python 3.9+（建議用專案 `.venv`）
2. `pip install -r requirements.txt`

### SofaScore：單賽季一鍵回填

以 `2015-2016` 為例（預設賽季區間 `08-01` 到隔年 `07-31`）：

```bash
python3 TakeData/sofa_score/run_sofascore_season_backfill.py \
  --season 2015-2016
```

此 wrapper 會依序執行：
1. `backfill_10y_leagues_cups.py`（主資料）
2. `shotmap_xg_backfill.py`
3. `shotmap_detail_backfill.py`
4. `backfill_event_odds_10y.py`

皆為 resume-safe，並把 state JSON 寫到：
- `data/backfill_sofascore_10y/state_sofascore_<season>.json`
- `data/backfill_sofascore_10y/shotmap_backfill_state_<season>.json`
- `data/backfill_sofascore_10y/shotmap_detail_state_<season>.json`
- `data/backfill_sofascore_10y/event_odds_backfill_state_<season>.json`

另外 `backfill_10y_leagues_cups.py` 會輸出 raw dumps（可關閉）：
- `data/backfill_sofascore_10y/raw/scheduled-events/YYYY-MM-DD.json`
- `data/backfill_sofascore_10y/raw/lineups/<event_id>.json`（best-effort，僅 200 時落檔）

---

## 注意

- 大型輸出（csv/sqlite/tar/zip）請放 `release/` 或外部儲存，不要直接提交到 git。
- 本專案以 Python 3.11+ / `.venv` 為主。

---

## 免責

本專案僅供研究用途，請遵守當地法律與平台條款。
