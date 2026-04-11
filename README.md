# AI Football Bets

此 repo 現在以 **root-first 結構** 為主。

- 主入口：`python -m main`
- Paper / validation / historical workflows：以 `paper/` + `scripts/` 為準
- 舊版 v1 / v2 compatibility layer 已移除

> 目前保留的是：**root-first Python 模組、scripts、tests、TakeData 爬蟲、必要設定檔**。

---

## 主要目錄

- `paper/`：paper trading / validation / reporting 流程
- `TakeData/`：歷史/即時資料爬蟲
- `data/`：資料輸出目錄（多數為執行產物，不建議入版控）

---

## 快速開始

```bash
pip install -r requirements.txt
python -m main --help
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
python -m main --matches "soccer_epl|Arsenal vs Chelsea"
```

### historical validation（SQLite / MySQL）

```bash
# SQLite-backed historical validation
python scripts/validate_paper_season.py \
  --season 2024-2025 \
  --competition-scope league-and-cups

# MySQL-backed historical validation
python scripts/validate_paper_season.py \
  --season 2024-2025 \
  --competition-scope league-and-cups \
  --historical-source mysql \
  --mysql-host 127.0.0.1 \
  --mysql-port 3306 \
  --mysql-user root \
  --mysql-password '<password>' \
  --mysql-database appdb
```

---

## Paper Trading（7-day value betting）

主要模組：`paper/`

- 聯賽池（單一合併策略）：Big-5 + J1 + K League 1 + A-League Men + CSL
- 每場比賽產生 1X2 / O/U / AH 候選，僅選一筆最佳注單（分數：fractional Kelly log-growth）
- 風險規則：若當日累積 PnL <= 當日起始 bankroll 的 -20%，當日停止新增注單
- 初始 bankroll：`INITIAL_BANKROLL`（預設 2000）
- 寫入：append-only 到 `data/v2/tracking/bets.sqlite` (`bet_log`)

常用指令：

```bash
# 單日：選注並寫入 bet_log
python -m paper.run_day --date 2026-03-15

# 單日：依 ESPN 比分結算
python -m paper.settle --date 2026-03-15

# 單日：輸出 daily + weekly 報告
python -m paper.report --date 2026-03-15 --sqlite data/v2/tracking/bets.sqlite

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

READY 檢查清單請見：`paper/README.md`

---

## Repo Cleanup Status

已清理 / 歸檔的舊項目：
- 舊版 v1 主程式痕跡（此前已不在主樹）
- `REORGANIZATION_REPORT.md` → `archive/docs/REORGANIZATION_REPORT.md`
- 若干 legacy utility / sidecar 已移除

目前 repo 應以以下結構理解：
- `paper/`：核心 paper trading / validation 流程
- `scripts/`：CLI / workflow wrappers
- `TakeData/`：資料抓取與 backfill
- `tests/`：測試

---

## Odds Sources

此 repo 目前採用 **SofaScore-first** odds 流程：
- **SofaScore**（fixtures / results / odds）
- The Odds API（可選 fallback；非主源）

目前 betting / tracking / normalizer 只聚焦 3 個主盤：
- `1X2`
- `Over/Under`
- `Asian Handicap`

> ✅ 已放棄 PP88 / youbaokun 方向。
> ✅ OddsPortal 相關 kickoff tracker / 歷史回填 / mysql schema / scripts 已全面移除。

# (OddsPortal tracker removed)
# (This section kept only as a placeholder for future odds tracking integrations)

## SofaScore 主源盤口

以目前流程為準，主源只處理以下 3 個盤口：
- `1X2`
- `Over/Under`
- `Asian Handicap`

SofaScore 公開 odds endpoint 對部分賽事可能只提供主盤（例如單一 AH line），
因此目前策略是：**只吃主盤，不追全盤口深度**。

## PP88 Match Watcher（已移除）

PP88 / youbaokun 相關 watcher、ingest、capture 腳本已從 repo 移除，
此段僅保留作為遷移說明，不再屬於現行流程。

# (PP88 watcher removed)
# (This section kept only as a migration note; current workflow is SofaScore-first)

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
