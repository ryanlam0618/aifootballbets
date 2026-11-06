🌏 LAYER 2 afb-ODDSH-SLUGFIX — 11 個 UNSUPPORTED 聯賽 slug 修復 + 重試驗證
任務：afb-ODDSH-SLUGFIX（Kris 2026-11-05 11:49 指示）
日期：2026-11-05 ｜ 執行：Forge（coding agent）
Repo：/root/.openclaw/workspace/oddsharvester @ master（ba6ac74+，patchright-swap 已 merge）
方法：Patchright 索引頁探測（11 地區頁 → 72 個 slug）+ links-only 驗證 + 樣本 odds 抽取

═══════════════════════════════
⚡ 總結：11 個 UNSUPPORTED → 4 PASS + 1 需重試 + 6 真不支援
═══════════════════════════════

1️⃣ **4 個升級 PASS**（slug 搵到 + 樣本 odds 全數驗證）：
   • UCL → `champions-league`（europe）— 161 links、10/10 場有效、8 bookies、odds 1.53-5.85 ✅（證實無 uefa 前綴）
   • UEL → `europa-league`（europe）— 179 links、8/8 場有效、8 bookies、odds 1.55-5.71 ✅
   • AFC Champions League → `afc-champions-league`（asia）— 164 links、10/10 場有效、6 bookies、odds 1.22-9.5 ✅（2023-24 季 = 舊名最後一季）
   • UECL → `conference-league`（europe）— 310 links、10/10 場有效、4 bookies、odds 1.41-8.72 ✅
2️⃣ **2 個 slug 存在但 NO-DATA**（season 格式問題，需再調查）：
   • EFL Cup → `efl-cup`（england）— index 有（4 entries）但 2023-2024 links-only 0 matches（season 格式可能唔同）
   • Chinese Super League → `super-league`（china）— index 有（8 entries）但 2024 calendar-year 0 matches（season 格式需核對）
3️⃣ **1 個改名確認**：AFC Champions League Two → `afc-champions-league-2`（asia，6 entries）— index 有但 2024-25 links-only 0 matches（首季賽事 OddsPortal 可能未入 historic odds）
4️⃣ **4 個盃賽真唔喺 OddsPortal 索引**（Emperor's Cup / J.League Cup / Australia Cup / Chinese FA Cup）— 地區索引頁 + 直接 slug probe 都 0 matches。如實記錄：呢 4 個盃賽喺 OddsPortal 冇歷史賠率覆蓋（或需要更深入嘅 site 結構探索）。
5️⃣ 淨效果：**SLUGFIX 後 OddsPortal 歷史賠率覆蓋 = 11 PASS + 4 新 PASS = 15 個 competition**（原 11 + 新 4），較原 24 個覆蓋 62.5%；核心聯賽宇宙（五大 + J1/K/A-League）全數 PASS ✅

═══════════════════════════════
🔍 slug 搜索過程（逐個 competition）
═══════════════════════════════

方法：Patchright persistent context 瀏覽 11 個地區索引頁（europe/england/asia/australia/china/japan/south-korea/spain/italy/germany/france），抽取全部 a[href*='/football/'] 連結 → 72 個唯一 slug → 配對 11 個目標

• UCL：europe 索引頁搵到 `champions-league`（Champions League, 18 entries）— 原候選 uefa-champions-league/europe-champions-league 都錯 ✅
• UEL：europe 索引頁搵到 `europa-league`（Europa League, 17 entries）✅
• UECL：europe 索引頁搵到 `conference-league`（Conference League, 18 entries）✅
• EFL Cup：england 索引頁搵到 `efl-cup`（EFL Cup, 4 entries）✅（slug 對，season 格式問題）
• CSL：china 索引頁搵到 `super-league`（Super League, 8 entries）✅（slug 對，season 格式問題）
• AFC CL Two：asia 索引頁搵到 `afc-champions-league-2`（AFC Champions League 2, 6 entries）✅
• AFC CL：asia 索引頁只有 afc-champions-league-2（2024 改名後舊賽事唔喺現行索引）— 用舊名 slug `afc-champions-league` 直接 probe 2023-2024 → 164 links ✅
• Emperor's Cup / J.League Cup：japan 索引頁只有 j1-league/j2-league — 無盃賽 ❌
• Australia Cup：australia 索引頁只有 a-league/a-league-women/australian-championship — 無盃賽 ❌（australian-championship 係 2025 新賽事，唔係 Australia Cup）
• Chinese FA Cup：china 索引頁只有 super-league/league-one-women — 無盃賽 ❌
• 4 盃賽直接 slug probe（japan-emperors-cup / japan-j-league-cup / australia-australia-cup / australia-ffa-cup / china-chinese-fa-cup × 各季格式）：全部 0 links ❌

═══════════════════════════════
📊 樣本驗證明細（4 個新 PASS）
═══════════════════════════════

• UCL 2022-2023：10 場樣本、10 有效、8 bookies、odds 1.53-5.85、0 越界
• UEL 2023-2024：8 場樣本、8 有效、8 bookies、odds 1.55-5.71、0 越界
• AFC CL 2023-2024：10 場樣本、10 有效、6 bookies、odds 1.22-9.5、0 越界
• UECL 2023-2024：10 場樣本、10 有效、4 bookies、odds 1.41-8.72、0 越界

═══════════════════════════════
📋 完整 24+ slug map（backfill 第二批輸入）
═══════════════════════════════

PASS（15 — 原有 11 + 新 4）：
1. Premier League → england-premier-league（近期季已證 8 bookies）
2. La Liga → spain-laliga
3. Serie A → italy-serie-a
4. Bundesliga → germany-bundesliga
5. Ligue 1 → france-ligue-1
6. J1 League → japan-j1-league
7. K League 1 → south-korea-k-league-1
8. A-League Men → australia-a-league
9. FA Cup → england-fa-cup
10. Copa del Rey → spain-copa-del-rey
11. Coppa Italia → italy-coppa-italia
12. DFB Pokal → germany-dfb-pokal
13. **UCL → champions-league（新）**
14. **UEL → europa-league（新）**
15. **AFC Champions League → afc-champions-league（新，舊名；AFC CL Two → afc-champions-league-2 另計）**
16. **UECL → conference-league（新）**

PARTIAL（1）：
17. EFL Cup → efl-cup（slug 對，season 格式需調查）

需調查（1）：
18. Chinese Super League → super-league（slug 對，season 格式需調查）

首季/無歷史（1）：
19. AFC Champions League Two → afc-champions-league-2（index 有，2024-25 historic odds 未入）

真不支援（4 — OddsPortal 無覆蓋）：
20-23. Emperor's Cup / J.League Cup / Australia Cup / Chinese FA Cup

═══════════════════════════════
✅ 驗證
═══════════════════════════════

• 索引探測：11 地區頁 / 72 slug / Patchright persistent context ✓
• 7 slug 驗證：links probe + 樣本 odds（UCL 10/10、UEL 8/8、AFC CL 10/10、UECL 10/10 全有效）✓
• 5 盃賽 slug probe：全部 0 links（如實記錄不支援）✓
• 數據邊界：數據只喺 repo data/coverage_verify/ + data/smoke_test/（未寫 aifootballbets DB ✓）
• 本 artifact 無任何 token/secret/chat ID
