# 20261106 — TEAMFIX Phase 2：CLV-BACKFILL Batch 1 完成（11 聯賽 × 2024-25 + 2023-24）

## 最終結果（全部 22 個 league-season jobs done）

**總計：3,944 records 刮取 → 2,245 mapped（57%）→ 40,201 snapshot rows 寫入 `afb_odds_snapshots`（INSERT IGNORE 冪等，DB 核實 2,242 distinct matches）**

| League | 24-25 scraped/mapped | 23-24 scraped/mapped |
|---|---|---|
| Premier League | 230 / 187 | 144 / 102 |
| La Liga | 211 / 63 | 151 / 33 |
| Serie A | 270 / 171 | 313 / 252 |
| Bundesliga | 197 / 117 | 262 / 132 |
| Ligue 1 | 168 / 58 | 222 / 99 |
| J1 League（曆年制 2024/2023） | 264 / 123 | 232 / 119 |
| K League 1（曆年制 2025/2024） | 204 / 201 | 230 / 228 |
| A-League Men | 138 / 81 | 91 / 50 |
| FA Cup | 155 / 51 | 235 / 84 |
| Copa del Rey | 80 / 25 | 92 / 31 |
| Coppa Italia | 32 / 21 | 23 / 17 |

## 執行過程中發現並修復嘅 5 個 pipeline bugs

1. **`--league` argparse 單值覆蓋**：`action="append"` 修正（首次 launch 淨係跑咗每個 worker 最後一個 league）
2. **Scrape timeout 25min 太短**：全季實測 ~85 分鐘 → 7200s
3. **MIN_RECORDS=20 partial guard**：CLI timeout / Node crash 嘅 1-record 垃圾唔會再被當成功（quarantine + re-scrape）
4. **State clobber race**：per-worker state files（state.json / state-w2.json）
5. **OH_CHECKPOINT_SAVE=0（最關鍵）**：CLI checkpoint wiring 令 output file 每場 match 被單 record 覆寫、最終聚合寫入被跳過 — output 永遠只剩最後一場。修復後 5/5 驗證 + 全量跑通
6. **rc≠0 guard 誤殺**：CLI 對 listing page 部分失敗會 return rc=1 但數據有效（實測 PL 24-25 rc=1 有 230 records）— guard 改為 n≥MIN_RECORDS 就接受
7. **曆年制聯賽**：J1 League / K League 1 season 映射 "2024-2025"→"2024"（K League 映射率 99% 證明正確）

## 已知限制（如實記錄）

- **Mapping no-match 率 43%**（1,699/3,944）：OddsPortal 短名 vs DB 全名（如 La Liga 70% no-match、Copa del Rey 69%）。Token-subset matcher 只處理子集關係，唔處理完全不同嘅名（"Bilbao" vs "Athletic Club"）。未匹配記錄如實跳過（永不猜測）。改善方向：alias 表（後續 task）
- **Listing page 部分失敗**：每季約 1-4 個 listing pages 失敗（rc=1），有少量 matches 從未被發現 — 覆蓋率約 40-80% per league-season
- 統計口徑：mapped 率以「刮到嘅記錄」為分母，唔係「DB 全部場次」

## 產物

- `data/clv_backfill/*.json`（22 個 scrape 產物）+ `state.json` / `state-w2.json`（checkpoint）
- DB：`afb_odds_snapshots` 40,201 rows（run_id='clv_backfill_batch1'，source='oddsharvester_backfill'）
- 腳本：`scripts/clv_backfill.py`（已 commit，見下）

## Commit

- oddsharvester master：`39e709c`（SLUGFIX）+ clv_backfill.py 首次 commit（本次修復全部入去）

## 前置依賴（已完成）

- TEAMFIX Phase 1（teams 表 10 行錯標修復）— mapping 解鎖嘅前提（Fulham vs Nottingham exact match 驗證 ✓）
- SLUGFIX（白名單 +9 slugs + 曆年制修正）
