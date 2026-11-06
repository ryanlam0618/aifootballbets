🧪 OddHarvester 實測 SMOKE TEST — EPL 2024-2025 1x2 historic（afb-ODDSH-SMOKE）
任務：afb-ODDSH-SMOKE（Kris 2026-11-04 18:36 指示「做測試睇下係咪成功攞到 data 返嚟」）
日期：2026-11-04 ｜ 執行：Forge（coding agent）
Repo：/root/.openclaw/workspace/oddsharvester @ master，commit 9dfda39（已 push origin ✓）

═══════════════════════════════
🏆 結論：PASS — 數據成功攞到（1 個完整 match record 實證）
═══════════════════════════════

1️⃣ **數據驗證全過**：1 個完整 match record（Newcastle 4-1 Manchester Utd，2025-04-13，EPL 2024-2025）— **8 個 bookmakers**（1xBet / 22Bet / bet-at-home / bet365 / Betfury / Betsson / Cloudbet / GGBET）、24 個 odds 值全部喺合理範圍（**1.55–5.54，0 個越界**）、implied margin 2.8–6.8%（真實市場水位）。
2️⃣ **根因發現 + 修復**：首版 headless 攝到 68px 空頁 — 二分法定位 = **STEALTH_SCRIPT 指紋補丁整爛 OddsPortal SPA 渲染**（baseline/no_route 都空白；no_stealth/neither 渲染全頁 43 anchors）。Workaround：禁用 STEALTH_SCRIPT，UA/locale/timezone 反偵測單獨用就渲染正常。
3️⃣ 誠實限制：per-match odds 歷史抓取需時 ~1-2 分鐘/場 — 完整 EPL 季（380 場）超出 20 分鐘 smoke 預算（15 分鐘邊界殺掉時得 1 個完整 record，checkpoint 增量儲存令數據保留 ✓）。默認模式無 per-bookmaker opening/closing 時間戳（odds 歷史要 scrape_odds_history 選項）。

═══════════════════════════════
📋 實際使用嘅完整命令
═══════════════════════════════

```
.venv/bin/oddsharvester historic -s football -l england-premier-league \
  --season 2024-2025 -m 1x2 --headless \
  --user-agent "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36" \
  --locale en-GB --timezone Europe/London \
  -f json -o data/smoke_test/epl_1x2_2024_2025.json
```
（經 data/smoke_test/run_smoke.py wrapper 執行：先禁用 STEALTH_SCRIPT 再調用 CLI main）

═══════════════════════════════
🧪 診斷過程（邊條路徑行得通）
═══════════════════════════════

1. 首跑 headless：頁面載入成功但渲染 68px / 0 event rows — 「page loaded successfully, no data」
2. 頁面 probe 取證：用真 UA（Chrome/131）+ locale + timezone 直接 Playwright probe → **全頁渲染**（1.28MB HTML、42 個 EPL match anchors、無 Cloudflare challenge）— 證明唔係被擋/改版，係 scraper stack 內部問題
3. 二分法（4 變體）：baseline ❌空 / no_route ❌空 / **no_stealth ✅全頁（43 anchors, height 26432）** / neither ✅ → 根因 = STEALTH_SCRIPT
4. Args probe：scraper 嘅 DOCKER args（含 --headless）直接 launch 都渲染正常 — 排除 browser args 嫌疑
5. 修復後重跑 → 成功抓數 ✓

═══════════════════════════════
📊 數據驗證明細
═══════════════════════════════

• 行數：1 個完整 match record（checkpoint 增量儲存 — timeout 殺掉後數據保留 ✓）
• 欄位：scraped_date / match_date / season / match_link / home_team / away_team / league_name / home_score / away_score / partial_results / venue / venue_town / venue_country / match_info / 1x2_market
• 1x2_market：8 bookmaker entries，每個含 '1'/'X'/'2' 賠率（字串）+ bookmaker_name + period(FullTime) + submarket(1X2)
• 樣本（Newcastle vs Man Utd）：1xBet 1.66/4.40/5.03（margin 2.8%）、bet365 等共 8 家
• Odds 範圍：1.55–5.54（24 值，0 越界）✅
• 時間戳：有 scraped_date + match_date（開賽時間）；**無 per-bookmaker opening/closing 時間戳** — 完整 odds 歷史要加 scrape_odds_history 選項（後續）

═══════════════════════════════
⚠️ 誠實限制 + 下一步
═══════════════════════════════

1️⃣ 速度：~1-2 分鐘/場（每場要 navigate 到 odds 頁 + 抽 8 家賠率）— 完整 EPL 季（380 場）估計 10-30 小時。大規模回填前建議：(a) 加 concurrency、(b) 限制 odds 歷史深度、(c) 分批跑
2️⃣ STEALTH_SCRIPT 修復應該永久化：建議 bisect 邊個指紋補丁整爛 SPA（嫌疑最大：canvas noise / AudioContext patch），只保留無害補丁 — 否則每次都要 workaround
3️⃣ 環境修復記錄：host 重啟清咗 uv Python 3.14 + venv 壞 symlink — 已重裝（uv python install 3.14）+ chromium 下載 + playwright install-deps（缺 libglib/libnss3/libatk 等 10+ 系統庫）
4️⃣ 無 per-bookmaker opening/closing 時間戳 — CLV 要 closing odds 嘅話，現有數據係「closing/current」快照；opening 需要 odds 歷史模式

═══════════════════════════════
✅ 驗證
═══════════════════════════════

• oddsharvester pytest（venv）：**1106 passed, 5 skipped**（9/18 baseline 無回歸 ✓ — smoke test 只加數據檔無改代碼）
• 數據檔：data/smoke_test/epl_1x2_2024_2025.json（1 record）+ 探針/日誌/截圖/HTML dump 全套證據
• Commit 9dfda39 已 push origin/master ✓（首推 GitHub Internal Server Error，重試成功）
• 本 artifact 無任何 token/secret/chat ID

═══════════════════════════════
🧭 下一步建議
═══════════════════════════════

1️⃣ 批 [afb-CLV-backfill] 前建議：先修 STEALTH_SCRIPT（bisect 補丁）+ 決定 backfill 深度/批次策略（380 場 × 全歷史 ≈ 10-30 小時；或先回填 closing-only 快很多）
2️⃣ smoke 數據已喺 repo data/smoke_test/ — Kris 睇過 + 拍板先寫 aifootballbets DB（照指示未寫 DB）
3️⃣ 大規模回填建議分批（每批一個聯賽一季）+ checkpoint 續跑（已內建 ✓）
