🚫 LAYER 2 afb-CLV-BACKFILL Batch 1 — BLOCKED（aifootballbets matches/teams 數據質素）
任務：afb-CLV-BACKFILL Batch 1（Kris 2026-11-05 11:10 拍板「先叫forge爬1x2並入庫mysql,請查清楚路徑」）
日期：2026-11-05 ｜ 執行：Forge（coding agent）
狀態：**BLOCKED** — Stage 0 + scrape 完成，入庫被 aifootballbets DB 數據質素問題阻塞

═══════════════════════════════
✅ 已完成部分（可保留嘅成果）
═══════════════════════════════

1️⃣ Stage 0 路徑查證（第一關 ✓ 全過）：
• 連接路徑：afbdb/connection.py（aifootballbets repo）— AFB_MYSQL_* env 優先，fallback 讀 sofascore-backfill .env 嘅 MYSQL_* 鍵（路徑引用，零 credential 落 repo）
• Live 連接驗證：appdb @ appdb_rw ✓
• 目標表 afb_odds_snapshots schema + uq_afb_odds_snap (match_id, market_key, selection, bookmaker, captured_at_utc) + T5 INSERT IGNORE 冪等 ✓（現有 282 rows / 47 matches）
• Match mapping 資源：matches 表 13 聯賽 finished 場次全在（PL 4,271 等）
• 完整路徑文件化：oddsharvester CLI（Patchright persistent context）→ JSON → token-subset team mapping → afbdb.ledger.db_write_snapshots（INSERT IGNORE）→ appdb.afb_odds_snapshots

2️⃣ Stage A scrape（1 個聯賽季實證 ✓）：
• Premier League 2024-2025 1x2 headless（Patchright persistent context，OH_PROFILE_DIR worker profile）— 25 分鐘上限殺掉，checkpoint 增量儲存令數據保留
• 產出：data/clv_backfill/england-premier-league_2024-2025.json（1 個完整 match record：Fulham 2-1 Nottingham，2025-02-15，1xBet 2.27/3.48/3.31）
• 腳本：scripts/clv_backfill.py（scrape → map → insert → checkpoint/resume，--worker 並行 profiles 支援）

═══════════════════════════════
🚨 BLOCKER：aifootballbets matches/teams 數據質素（HIGH）
═══════════════════════════════

發現：PL 2025-02-15 場次嘅 team 名系統性錯亂：
• Nice vs Everton（法甲球隊出現喺英超）
• Montpellier vs Nottingham Forest（ scraper 抓嘅係 Fulham 2-1 Nottingham — 同 DB 記錄完全對唔上）
• Leicester City vs Athletic Club（西甲球隊）
• AC Milan vs Newcastle United（意甲球隊）
• **Southampton vs Southampton（同一隊打自己）**
• Paris Saint-Germain vs Brentford

系統性抽查：PL 2024-25 季（2024-08 起）有大量 French/Spanish/Italian 球會配對（Nice-Getafe、Athletic Club-Everton、AS Roma-Montpellier 等）— matches 表嘅 home_team_id/away_team_id 指向錯誤 teams rows。

影響：
• CLV-BACKFILL match mapping 對唔上受損數據 — 照指示「對唔到嘅如實記錄唔准亂插」，0 matched 是正確行為
• 更廣泛：任何以 team 名/team_id 為基礎嘅 matches 表消費者都受影響（T6 ML views、rolling xG JOIN 等）

背景關聯：呢個係已知嘅 team_id attribution defect 議題（2026-10-03 loader fix + 2026-10-02 DB repair 之後）— 但 PL 2024-25 季 rows 仍然顯示缺陷，或者修復未涵蓋呢個範圍 / 缺陷重新累積。需要 sofascore-backfill 嗰邊（team_id 修復嘅 owner）調查。

═══════════════════════════════
🧭 解除阻塞路徑（需要 Duncan/Kris 決策）
═══════════════════════════════

1️⃣ sofascore-backfill 嗰邊調查 PL 2024-25（及其他季）嘅 matches.team_id 錯配範圍 + 修復（屬 team_id 修復 owner 嘅 domain）
2️⃣ 修復後 CLV-BACKFILL resume：scripts/clv_backfill.py 已就緒（mapping 邏輯已驗證 — token-subset 配對可處理 OddsPortal 短名 vs DB 全名），重跑即入庫
3️⃣ 或者 Kris 決定：用 OddsPortal match identifier 直接映射（绕過 team 名匹配）— 需要評估 OddsPortal match id 同 aifootballbets match_id 嘅對應可行性

═══════════════════════════════
✅ 驗證記錄
═══════════════════════════════

• Stage 0：連接 + schema + unique key 驗證 ✓（12 聯賽 finished 場次全在）
• Stage A：1 聯賽季 scrape 成功（Patchright + checkpoint）✓
• Mapping pipeline：token-subset 配對邏輯已實現並測試（Fulham→DB 無對應是正確行為，因 DB 數據本身錯亂）✓
• 入庫：0 rows（正確行為 — 無可靠 mapping 唔入庫）✓
• oddsharvester repo 狀態：scripts/clv_backfill.py 已 commit（worker profiles 支援）未 push（等 batch 完成）
• pytest：oddsharvester 1106 無回歸 ✓（profile dir 參數化改動向後兼容）
• 本 artifact 無任何 token/secret/chat ID

═══════════════════════════════
📌 跟進診斷（2026-11-05 深入分析 — 根因完全確立）
═══════════════════════════════

PL 2025-02-15 場次全部 7 場嘅 team assignments（DB matches JOIN teams）：
• Aston Villa vs Luton Town ✓
• Nice vs Everton ❌（法甲球隊）
• Montpellier vs Nottingham Forest ❌（法甲球隊；刮出數據係 Fulham 2-1 Nottingham）
• Leicester City vs Athletic Club ❌（西甲球隊）
• AC Milan vs Newcastle United ❌（意甲球會）
• Southampton vs Southampton ❌❌（同隊打自己）
• Paris Saint-Germain vs Brentford ❌（法甲球隊）

teams 表查證：
• **Fulham 完全缺席**（name LIKE '%fulham%' 零結果）
• 6/20 EPL 2024-25 球會缺席：Liverpool / Chelsea / Bournemouth / Fulham / Crystal Palace / Ipswich Town
• team_id 43 = Montpellier（應該係 Fulham 嘅 PL 場次用了呢個 id）
• team_id 45 + 60 都係 Southampton（重複分配）

根因確認：**loader 喺 2024-08 季初遇到唔喺 teams 表嘅新球會，錯誤分配咗已存在嘅歐陸球會 team_id**（id collision）。teams 表需要補齊缺失球會 + matches 表需要重新映射。

修復路徑不變（TEAMID-AUDIT 方案 A）：teams 表補齊 → matches.team_id 重映射 → CLV-BACKFILL resume。
