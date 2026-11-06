# aifootballbets — DB 數據目錄

> 📌 **講任何「有冇 X 數據」之前必查呢份 / 直接 query DB。**
> 實測時間：2026-11-07 04:0x（agent vivid-breeze 等 session，`afb_mysql_connect`）
> 連接方式：`/root/.openclaw/workspace-coding/aifootballbets/afbdb/connection.py` → `afb_mysql_connect()`

## 1. 核心數據表（實測 row counts @ 2026-11-07）

- `matches` — fixtures/結果（Sofascore 口徑，~52K；PHASE4 後 FA Cup 274→480）
- `teams` — 3,740+ rows；經 4 輪 teams-fix（2026-11-05~07）後 EPL/La Liga/Ligue 1/Serie A/J1/A-League/K League + 盃賽 duplicate-label 已驗證改名/合併
- `afb_odds_snapshots` — **96,893 rows / 5,474 distinct matches / 15 bookies**（run_id='clv_backfill_batch1' 起，INSERT IGNORE 冪等；OddsPortal 1x2 FullTime；alias remap 配對率 99.9%）
- `afb_predictions` — 模型預測（uq_afb_pred：run_id+match_id+market+line+selection；line 用空字串唔用 NULL）
- `clv_closing_line` — 32,215 rows（每 match × bookmaker 收盤 trio + de-vig 機率）
- `clv_consensus_closing` — 5,431 場（median consensus + dispersion；覆蓋 99.1%）

## 2. xG 數據 ✅ 有（2026-11-07 04:0x 實測核實）

⚠️ 教訓：業界報告話「缺 xG」係錯 — **DB 一直有，講之前必查**。

- `match_shotmap` — **766,488 rows**：每射門 xG / xgot / xg_source
- `match_statistics` — 376,876 rows（球隊層面統計）
- `afb_team_rolling_xg` — **21,194 rows**：rolling_xg_for / rolling_xg_against（每隊每場近期攻防 xG，可直接入模型特徵）
- `match_player_stats` — 20,479 rows（xg/expected_goals/expected_assists 欄位；xg 直填僅 688 rows / 30 場稀疏，唔好當全覆蓋）
- `match_lineups` — expected_goals / expected_assists / expected_goals_on_target 欄位齊
- `afb_shotmap_xg_backup` — shotmap xG 備份
- ⚠️ 待驗證：shotmap 按季/聯賽覆蓋率未逐季核實（模型層開工時順手做）

## 3. 其他表

- `match_incidents` / `v_match_incidents_fixed` — 事件（26/27 有 2,091 insert errors 遺留：period enum + minute NOT NULL）
- `match_lineups` / `v_match_lineups_fixed` / `v_match_player_stats_fixed` — lineups 修復視圖
- `player_season_stats` — 季度球員統計（xg 欄位有）
- `afb_state` — pipeline 狀態
- backups：`afb_backup_teams_20261105`（3,740）、`afb_backup_teams_20261106`、`afb_backup_teams_20261106b`（3,801）、`afb_backup_matches_20261105`（52,154）、`afb_backup_matches_20261107`（PHASE7 dedupe 雙表備份）

## 4. 已知數據缺口 / 遺留（如實記錄）

- 3 條結構性 unmatched odds records（作廢場次 / 錯聯賽 scrape / side-flip final）— PHASE7 判定冇得 match
- 2,091 條 26/27 incident insert errors（要 patch runner 再 re-run）
- 合成 ID（≥ 900000001）要喺將來 Sofascore backfill 前對賬
- 非合併 duplicate team rows：Man City 3052 / Lille 4860 / Hamburg 3-id 等 identity 未明（PHASE8 候選，Kris 未批）
- OddsPortal 覆蓋：24 competitions（SLUGFIX 後）；J.League Cup / Chinese FA Cup / ACL Elite season selector 未解
- OddHarvester `.git/config` 有 raw ghp_ token — 未 rotate（hygiene）
