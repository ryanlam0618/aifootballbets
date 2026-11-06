🔀 LAYER 2 afb-ODDSH-PATCHRIGHT — Patchright swap 實測（protocol-level stealth）
任務：afb-ODDSH-PATCHRIGHT（Kris 2026-11-05 00:46 批准）
日期：2026-11-05 ｜ 執行：Forge（coding agent）
Repo：/root/.openclaw/workspace/oddsharvester @ branch **patchright-swap**（commits 1c9aa0c + 0c3c7bb，已 push ✓；master 未動）

═══════════════════════════════
⚡ 誠實結論（混合結果）
═══════════════════════════════

1️⃣ **①渲染根治 CONFIRMED ✅**：Patchright（protocol-level stealth：鏟 Runtime.enable / Console.enable / command flag leaks）+ persistent context + **完全唔載 STEALTH_SCRIPT** — 頁面渲染正常（無 68px 空頁、無 Cloudflare/驗證彈出、119 個 match links 成功收集、per-match odds 抽取正常運行）。STEALTH_SCRIPT 根因徹底解決。
2️⃣ **②≥5 records 目標未達**：25 分鐘上限內得 **1 個完整 record**（Aston Villa 2-1 Chelsea，2025-02-22）— 瓶頸係網站本身嘅 odds-history 頁面速度（每場 odds 歷史導航需 ~15-20 分鐘，多場並發在途但完成率低），同舊 workaround 速度相若（舊版 15 分鐘得 1 record）— 唔係 Patchright 嘅錯，但目標如實未達。
3️⃣ 數據質素佳：**10 bookmakers**（比舊 workaround 多 2 個：BetInAsia、Bets.io）、30 odds 值 2.60-3.67（0 越界）、period FullTime ✓。
4️⃣ **pytest 回歸 7 個**（test_playwright_manager.py）：全部斷言舊 browser.new_context 架構（multi-proxy contexts / rotated pages / HAR）— persistent-context 路徑有意取代呢啲行為。測試遷移係 branch 上嘅 follow-up 工作項，master 未受影響。
5️⃣ 建議：採用 Patchright（渲染根治 + 更強反偵測），代價係遷移 7 個架構測試 + multi-proxy 模式需重新設計（persistent context 單 profile，多 proxy 需 per-profile dirs）。

═══════════════════════════════
🔧 實現細節（branch patchright-swap）
═══════════════════════════════

• 依賴：patchright==1.64.4（PyPI）加入 venv + pyproject dependencies（playwright 保留俾 tests/遷移期）
• 瀏覽器：patchright install chromium → Chrome Headless Shell 156.0.8078.4（v1248，同 ms-playwright cache 結構）
• src/oddsharvester/core/playwright_manager.py 改動（2 處）：
  1. import：playwright.async_api → patchright.async_api（drop-in，API 相同）
  2. initialize()：launch → **launch_persistent_context**（user_data_dir = data/.patchright-profile，.gitignore 已加）— Patchright stealth 要求；STEALTH_SCRIPT 有意不載入（bisect 證明佢整爛 SPA；patchright 取代）
  – 保留：OneTrust/第三方廣告/route blocking（bisect 證明無害）、UA/locale/timezone、per-league HA 等全部不變
• 改動行數：約 −25/+30 行（playwright_manager.py）+ pyproject 1 行 + .gitignore 1 行 — 極小 diff

═══════════════════════════════
📊 Smoke 實測對比（Patchright vs 舊 workaround）
═══════════════════════════════

• 渲染：Patchright ✅ 正常（無 STEALTH_SCRIPT）｜舊 workaround ❌ 需禁用 STEALTH_SCRIPT 先得
• 反偵測：Patchright protocol 級（無 Runtime.enable leak）｜舊版靠 STEALTH_SCRIPT 補（但補丁本身有副作用）
• Bookmakers/場：10（1xBet、22Bet、bet-at-home、bet365、Betfury、BetInAsia、Bets.io、Betsson、Cloudbet、GGBET）vs 舊 8 — Patchright 多 2 家 ✅
• Match links 收集：119 個成功 ✓（EPL 全季 links 覆蓋）
• 速度：1 完整 record / ~20 分鐘 vs 舊 1 / 15 分鐘 — 相若（瓶頸係網站 odds-history 頁面，唔係 stealth 層）
• Cloudflare/驗證：兩者都無 ✓
• 穩定性：Patchright 全程無渲染問題；舊版要 workaround 先行

═══════════════════════════════
⚠️ 誠實限制
═══════════════════════════════

1️⃣ ≥5 records 目標未達（25 分鐘得 1 個完整）— 瓶頸係每場 odds-history 頁面導航（網站端），並發在途匹配未完成。要達標需要更長時間窗或限制 odds 歷史深度
2️⃣ pytest 回歸 7 個（1099 passed / 7 failed / 5 skipped）：全部係 test_playwright_manager.py 對舊架構嘅斷言 — 遷移工作項（改斷言至 persistent-context 行為）
3️⃣ Multi-proxy 模式暫不支援（persistent context 單 profile）— orchestrator 嘅 proxy pool 輪換需要 per-profile dirs 重設計（migration note）
4️⃣ 持久 profile 目錄（data/.patchright-profile）已加 .gitignore — 淨瀏覽器狀態累積，建議定期清理

═══════════════════════════════
✅ 驗證
═══════════════════════════════

• Smoke 實測：Patchright 渲染正常（無 68px）、無 Cloudflare、119 links、1 完整 record、10 bookmakers、30 odds 全部 2.60-3.67 合理 ✓
• pytest：1099 passed / 7 failed（7 個全部係舊架構斷言測試 — 如實報告為遷移工作項）
• 數據檔：data/smoke_test/epl_1x2_2024_2025_patchright.json + patchright_run.log（repo 內 ✓）
• master 未動 ✓（分支 patchright-swap：1c9aa0c + 0c3c7bb 已 push）
• 本 artifact 無任何 token/secret/chat ID

═══════════════════════════════
🧭 永久遷移建議（如果採納）
═══════════════════════════════

1️⃣ import 清單（playwright → patchright）：
   – src/oddsharvester/core/playwright_manager.py（已完成，本 branch）
   – 其餘 Page/TimeoutError type imports（base_scraper.py、market_extraction/*、browser_helper.py、browser/selection.py 等 9 處）— type-only，可逐漸換或保持 playwright type imports（兩者 API 相容）
2️⃣ 執行清單：
   – pyproject：patchright>=1.64.0 ✓（本 branch 已加）
   – .venv：pip install patchright ✓
   – patchright install chromium ✓（v1248）
   – .gitignore：data/.patchright-profile/ ✓
   – 刪除/停用 STEALTH_SCRIPT 載入 ✓（persistent 路徑根本唔載）
   – TODO：遷移 7 個架構測試 + multi-proxy per-profile dirs 設計
3️⃣ 驗收建議：合併前用 2-3 個聯賽做再現測試（本 smoke 嘅 command 照跑）

═══════════════════════════════
📎 產出清單
═══════════════════════════════

• Branch patchright-swap（已 push）：playwright_manager.py、pyproject.toml、uv.lock、.gitignore
• 數據：data/smoke_test/epl_1x2_2024_2025_patchright.json + patchright_run.log（repo 內 ✓，未寫 aifootballbets DB）
• 本 artifact：subagent_results/20261105-oddsharvester-patchright.md（+ .json）
