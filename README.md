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
python scripts/paper_run_7d.py --sqlite data/v2/tracking/bets.sqlite

# 可重播（deterministic）模式
python scripts/paper_run_7d.py \
  --start-date 2026-03-10 \
  --provider-json tests/fixtures/paper7d_provider.json \
  --sqlite data/v2/tracking/bets.sqlite
```

最終會輸出 7 天總結（含 final PnL / ROI / max drawdown / winrate / avg edge / by market / flat-stake baseline）。

READY 檢查清單請見：`v2/paper/README.md`

---

## 主要爬蟲腳本

- `TakeData/sofa_score/backfill_10y_leagues_cups.py`
- `TakeData/sofa_score/shotmap_xg_backfill.py`
- `TakeData/sofa_score/shotmap_detail_backfill.py`
- `TakeData/sofa_score/backfill_event_odds_10y.py`
- `TakeData/odds_batch_scraper.py`

---

## 注意

- 大型輸出（csv/sqlite/tar/zip）請放 `release/` 或外部儲存，不要直接提交到 git。
- 本專案以 Python 3.11+ / `.venv` 為主。

---

## 免責

本專案僅供研究用途，請遵守當地法律與平台條款。
