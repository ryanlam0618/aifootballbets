🔒 OddHarvester 安全審查 + 技術棧解釋（afb-ODDSH-AUDIT）
任務：OddHarvester 安全審查 + 技術棧解釋（Kris 2026-11-04 親口指示）
日期：2026-11-04 ｜ 執行：Forge（coding agent）｜ 性質：只讀靜態審查（零 repo 改動）
Repo：/root/.openclaw/workspace/oddsharvester（fork ryanlam0618/oddsharvester，sync 上游 jordantete/OddsHarvester v0.12.0，HEAD dc76466）

═══════════════════════════════
🏆 結論：CLEAN（附 4 項低風險建議）
═══════════════════════════════

審查範圍：網絡端點全清單、混淆代碼、subprocess、憑證處理、依賴供應鏈、.git/config、本地 vs 上游 diff。
結論：**無惡意行為、無數據外傳、無憑證收集**。發現 4 項低風險（LOW）衛生問題 + 3 項資訊性（INFO）記錄，全部有具體修復建議。可以放心用佢做 aifootballbets 歷史賠率回填。

═══════════════════════════════
1️⃣ 可疑內容審查結果
═══════════════════════════════

🌐 網絡外呼端點全清單（運行時會接觸嘅）：
• www.oddsportal.com — 主目標（賽程/賠率頁面，數十個聯賽路徑全部喺呢個 domain 下）✅
• api.proxyscrape.com/v2 — 免費 proxy 名單來源（fetch_free_proxies.py，文檔化功能）✅
• 其他全部係文檔/README 連結（github.com、img.shields.io、codecov.io、pypi.org、opensource.org）— 唔會喺運行時外呼
• centroquote.it — 只是 --base-url 參數嘅幫助文字「例子」（regional mirror 示範），唔係硬編碼調用 ✅
• proxy.example.com / http://user — 文檔格式示例 ✅
• ❌ 無 telemetry、無 analytics、無第三方追蹤 domain

🔓 混淆代碼：零。全 repo 無 base64 解碼、無 exec()、無 eval()、無動態 import（唯一 importlib.metadata 係標準版本讀取）。

⚙️ subprocess（3 個檔案，全部合理）：
• scripts/orchestrator_v1.py:396 — 行自己嘅 oddsharvester CLI（cwd=REPO_ROOT、有 log、有 env copy）
• scrape_all_leagues.py:95 — 每個聯賽-賽季行一次 CLI（10 分鐘 timeout）
• scripts/capture_all_hars.py:192 — HAR 網絡錄製輔助
• 全部行嘅係項目自身命令，無 curl 外傳、無奇怪二進制

🔑 憑證處理：
• login_oddsportal.py（126 行）— 独立小工具：Playwright 開 OddsPortal 登入頁、填 email/password（函數參數傳入，無默認值、無硬編碼）、存 cookies JSON。**全 repo 無任何地方調用佢**（純手動工具）。
• cookies 檔案：默認儲存路徑喺 repo 外（見 LOW-2）；repo 內無 cookies.json、git 無追蹤任何 cookie 檔 ✓
• 無 credential.helper、無 ~/.git-credentials ✓
• AWS：boto3 標準憑證鏈（env/shared file），無硬編碼 key ✓；S3 bucket/region 係上游默認值，可用 OH_S3_BUCKET/OH_AWS_REGION 環境變數覆寫

📦 依賴供應鏈：
• pyproject：beautifulsoup4 / boto3 / click / lxml / mysql-connector-python / playwright / pytz / tzdata + dev 工具（pytest/ruff/pre-commit）— 全部主流知名套件，無山塞套件
• uv.lock：36 個套件全部 recognizable，無 typosquatting 疑似
• 無 postinstall / build hooks ✓

📋 .git/config（9/18 audit flag 跟進）：
• **已解決**：config 現在只有兩個 HTTPS remote（origin + upstream，無內嵌憑證）+ user 名稱。9/18 flag 嘅 GitHub token 已經唔喺度 ✅
• 無 credential.helper ✓

═══════════════════════════════
2️⃣ 本地 vs 上游 diff 審查（自家加嘅檔案）
═══════════════════════════════

Diff 規模：89 files，+94,136/−349（含上游 drift + 我哋自家功能）。自家新增：
• src/oddsharvester/cli/commands/scrape_full.py（+340 行）— full scrape CLI 命令
• src/oddsharvester/core/browser_helper.py（+1,072 行）— 反偵測 + cookie 橫幅處理 + 盤口商過濾 + 時段選擇
• src/oddsharvester/core/full_odds_extractor.py（+567 行）— 賠率抽取器
• src/oddsharvester/utils/rate_limiter.py（+93 行）— 請求限速
• scripts/orchestrator_v1.py — 批次 orchestration（subprocess 行 CLI + proxy pool 輪換）
• core/odds_portal_scraper.py / base_scraper.py / playwright_manager.py 修改 — 反偵測同步（merge commit dc077ae「sync anti-detection from SofaScore backfill」）

危險行為掃描結果：
• 越權寫出路徑：❌ 無。輸出全部喺 REPO_ROOT/data/ 下（DEFAULT_OUTPUT_ROOT = data/orchestrator_v1）✅
  （唯一例外見 LOW-2：cookies 默認路徑喺 repo 外，屬憑證檔案非數據外傳）
• 讀取無關憑證：❌ 無。env 讀取只有 os.environ.copy()（subprocess 繼承，標準做法）
• 危險命令：❌ 無。subprocess 只行項目自身 CLI

═══════════════════════════════
3️⃣ 技術棧解釋（小朋友都明版）
═══════════════════════════════

想像 OddHarvester 係一間「賠率影印舖」：

• 🎭 Playwright 反偵測 = 一個「隱身司機」開真瀏覽器去 OddsPortal 行街。佢會先拆走車上「我是機器人」嘅牌子（navigator.webdriver 改成 false）、幫你自動撳走「接受 cookies」彈窗、仲會揀啱你想睇嘅盤口商同時段（好似喺超市揀牌子同埋大細碼）。
• 🔍 賠率解析器 = 舖內嘅「影印員」。佢識得喺頁面入面認出邊度係主勝/和/客勝嘅數字，逐個抄低（full_odds_extractor + odds_parser）。
• ⏳ Historic 模式 = 「時光機」。OddsPortal 每場波嘅頁面留低咗開賽前賠率變化嘅歷史，時光機會一場一場返轉去，將每個時間點嘅賠率影印落來（odds_history_extractor）。
• 📦 輸出 = 「快遞」。影印好嘅賠率可以打包成 JSON 或者 CSV 檔案放喺 data/ 文件夾，想嘅話仲可以直機寄去 AWS S3 或者寫入 MySQL（remote_data_storage）。
• 🐢 Rate limiter = 「行路禮儀員」。佢會叫我哋唔好行太快，每次請求之間停一停，等網站唔會覺得你係喺度狂抄書嘅機械人。
• 🌍 Proxy = 「轉地址出門」。每個 job 可以用唔同嘅 IP 地址出發（proxy pool 輪換），令網站見到嘅訪客來源更加分散自然。

═══════════════════════════════
🚨 發現清單（4 LOW + 3 INFO）
═══════════════════════════════

🟡 LOW-1：proxy 憑證以命令行參數傳遞
  證據：scripts/orchestrator_v1.py:292（cli_args.extend(["--proxy-user", p[1], "--proxy-pass", p[2]])）
  風險：proxy 帳密會出現喺 process list（ps / /proc/pid/cmdline），同一台機嘅其他用戶可見
  建議：改用環境變數或 stdin 傳遞 proxy 憑證

🟡 LOW-2：cookies 默認儲存路徑寫死喺 repo 外嘅個人目錄
  證據：src/oddsharvester/cli/commands/scrape_full.py:108（default="/home/openclaw/.openclaw/workspace/projects/OddsHarvester/cookies.json"）
  風險：cookies 係 session 憑證（等如已登入狀態）；路徑硬編碼影響可移植性，且憑證檔案放喺固定可預測位置
  建議：默認路徑改為 repo 內 data/（gitignore）或明確參數化；cookies 檔案永不入 git

🟡 LOW-3：data/proxy_webshare.txt 唔喺 .gitignore
  證據：git check-ignore 無覆蓋；檔案現時不存在（無即時洩漏），但格式係 IP:PORT:USER:PASS 憑證檔
  建議：.gitignore 加 data/proxy_webshare.txt（或 data/*.proxy.txt pattern），防止將來意外 commit

🟡 LOW-4：63 個 data/ 輸出檔已被 git 追蹤（batch logs + 刮下來嘅賠率 JSON）
  證據：git ls-files data/ = 63 個檔案（a-league-men__2016-2017.log 等）
  風險：repo 膨脹 + 數據產物混入版本控制
  建議：考慮 .gitignore 加 data/ 輸出 pattern（保留 .gitkeep）

🔵 INFO-1：orchestrator 以 os.environ.copy() 將完整環境變數傳給子進程（標準做法，但子進程會見到 env 內所有秘密）
🔵 INFO-2：match_odds 表部分批次 odds_type=NULL（2026-10-03 場次）— 數據質素記錄（非安全問題；T5 已加 tolerant 查詢兼容）
🔵 INFO-3：9/18 audit 嘅 .git/config token flag 已解決 ✅（config 乾淨）

═══════════════════════════════
✅ 驗證方法（全部只讀）
═══════════════════════════════

• 端點清單：grep -rhoE "https?://..." 全 src/ scripts/ *.py（去重 30+ 條）
• 混淆掃描：grep base64/exec(/eval(/__import__/importlib
• subprocess：grep subprocess/os.system/popen + 逐個檔案讀上下文
• 憑證：git config / ls ~/.git-credentials / grep password|email|cookie|token（login_oddsportal.py 逐行）
• 供應鏈：pyproject dependencies + uv.lock 36 套件名單全檢 + hooks grep
• diff：git diff upstream/master --stat + 自家檔案逐個 grep（越權路徑/env/憑證）
• git 衛生：git ls-files（cookies/scraped_data/data 追蹤狀態）+ git check-ignore

═══════════════════════════════
🧭 建議行動（按優先級）
═══════════════════════════════

1️⃣ .gitignore 加 proxy 憑證檔 pattern（LOW-3，一分鐘）
2️⃣ scrape_full.py cookies 默認路徑參數化/改 repo 內（LOW-2）
3️⃣ proxy 憑證傳遞改 env/stdin（LOW-1，orchestrator 小改）
4️⃣ data/ 輸出 gitignore 考慮（LOW-4，repo hygiene）
5️⃣ 生產回填前對 pip 依賴樹做同樣審查（uv.lock 今日乾淨，鎖定版本後重審一次）
6️⃣ 維持 .git/config 乾淨（9/18 flag 已解決，未來 sync 注意）

═══════════════════════════════
📌 範圍聲明
═══════════════════════════════

• 只讀靜態審查 — 零 repo 改動、零運行 scraper、pytest 未重跑（9/18 audit 已確認 1106 passed）
• 審查基準：HEAD dc76466（upstream v0.12.0 merge）+ 工作樹現狀
• 本報告無任何 token/secret/chat ID
