# AI Football Bets — `clawbot_v2`

此分支只保留 **v2 管線** + **資料爬蟲（TakeData）**。

> v1 程式（`app.py` / `src/` / `scripts/` / `tests/` / 舊 docs）已移除。

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

範例：

```bash
python -m v2.main --matches "soccer_epl|Arsenal vs Chelsea"
```

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
