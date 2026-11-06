🧮 LAYER 2 T1 — Dixon-Coles + tau 時距校正 + 時間衰減 + AH quarter-line 定價
任務：afb-layer2-T1-dc-coles
日期：2026-10-28 ｜ 執行：Forge（coding agent）
Repo：aifootballbets @ main
Commit：66fd235（**local only — push 被 blocker 擋住**，見下）
基線：Layer 1（c405104）之上

═══════════════════════════════
⚡ TL;DR
═══════════════════════════════

1️⃣ DC(1997) 完整實現：攻守 + 主場優勢閉式座標上升 MLE、tau 四格修正（in-sweep rho grid search）、指數時間衰減（half-life 參數化）、gauge fix、min_matches 中性 pin。
2️⃣ AH quarter-line 定價照足結算規則：0.25/0.75 = 相鄰兩線對半拆分，push 計半；fair odds = (1−push)/win；雙方互補性 eff_home + eff_away = 1 有測試鎖住。
3️⃣ 實測 fit 全 DB：51,969 場 / 858 隊 / rho=+0.010 / home_adv=+0.265 / avg loglik=−1.507（約 2-3 分鐘純 Python，零依賴）。
4️⃣ 真 DB run 驗證：FA Cup 2026-10-03 → 520 行預測寫入 afb_predictions（120 1X2 + 400 AH）讀回一致；smoke 行已清理。
5️⃣ 測試：19 個新 hermetic 單元測試全綠；全套 81 passed / 1 failed（唯一 fail 係既有 test_paper_repro_7d，62-pass baseline 保持 ✓）。

═══════════════════════════════
🔧 實施明細
═══════════════════════════════

新檔 3 個（commit 66fd235）

📄 models/dc_model.py（核心庫，純 stdlib）
• decay_weight：exp(−ln2 · age / half_life)，age=half_life 時權重=0.5（1997 paper 嘅 (1−ξ)^t 實務等價形式）
• tau_factor：DC 四格修正 — τ(0,0)=1−λμρ / τ(0,1)=1+λρ / τ(1,0)=1+μρ / τ(1,1)=1−ρ / 其他=1
• tau_corrected_matrix：修正後 renormalise（負值 clamp、截斷 max_goals=10）
• fit_dc：座標上升 MLE
  – attack_i 閉式更新：log(Σw·scored) − log(Σw·exp(defense_opp + home_adv))
  – defense_j 閉式更新（conceded 方向）
  – home_adv 閉式更新
  – rho：in-sweep 1-D grid（[-0.15, +0.10] step 0.01，infeasible τ≤0 自動剔除）
  – gauge fix：每 sweep 後 mean(attack)=0（消除 a+=c/d−=c 平坦方向）
  – min_matches（預設 10）：窗口內場數不足嘅隊 pinned 喺中性 0，但其場數仍貢獻對手估計
• ah_probs / _ah_side：AH 定價
  – 語義：line L = home +L（home 收 L 球）；home 贏 = x+L>y、push = x+L=y
  – half line 冇 push；quarter = 兩半注（如 +0.25 = 0 同 +0.5 各半）
  – eff = 0.5(w1+p1/2) + 0.5(w2+p2/2)；fair odds = (1−push)/win
  – away side = 同一市場互補面（away 贏 ⇔ home 輸）→ eff_away = 1 − eff_home
• DCModel.predict_markets：1X2（3 行）+ AH 五線雙邊（10 行）= 13 行/場
• fit_half_life_by_validation：--fit-xi 用最新 25% hold-out log-likelihood 揀 half-life（候選 180/270/365/540/730 日）

📄 scripts/run_dc_predictions.py（獨立 day runner）
• python scripts/run_dc_predictions.py --date YYYY-MM-DD [--leagues "..."] [--all-leagues] [--fit-xi] [--status scheduled|finished|postponed|all] [--dry-run]
• 流程：連 DB → as-of 讀歷史（afbdbh.history）→ fit → 攞當日 fixtures（默認 9 聯賽宇宙，status=scheduled）→ 預測 → 寫 afb_predictions（model_name='dc_tau_v1'）→ readback 驗證
• --status finished 支持歷史場 backtest run（DB snapshot 冇未來 scheduled 場時嘅驗證路徑）
• 默認 half_life=365d；寫入用 afbdb.ledger.db_write_predictions（INSERT IGNORE，uq 鍵 run_id+match+market+line+selection）

📄 tests/test_dc_model.py（19 測試，hermetic）
• decay：half-life 語義、單調遞減、禁用 decay
• tau：四格數值、rho=0 = 獨立 Poisson（renormalised）、矩陣歸一化、負 rho 增加 low-score mass
• AH：+0.5 含 draw / −0.5 唔含、雙方互補（5 線）、quarter 拆分恆等式（0.25 同 0.75）、概率分割
• fit：合成 4 隊 round-robin 恢復強度排序、預測行和=1（13 行/場）、min_matches pin、gauge、as-of 排除、draw-heavy 數據提升 low-draw mass

═══════════════════════════════
🧪 驗證結果
═══════════════════════════════

✅ pytest 全套：81 passed / 1 failed
• baseline 62 pass 保持 ✓（唯一 fail = 既有 test_paper_repro_7d fixture 問題，照指示冇碰）
• 新增 19 個 DC 測試全綠（0.7s，hermetic）

✅ 真 DB fit（as-of 2026-10-03）
• 52,021 場歷史 → 51,969 場進入 fit（52 as-of 後排除）
• 858 隊有專屬參數（min_matches=10 閘門）
• rho=+0.010、home_adv=+0.265（≈0.27 球主場優勢 — 合理量級）
• avg weighted loglik = −1.507/場

✅ 真 DB 寫入（FA Cup 2026-10-03，40 場）
• 520 行預測寫入 afb_predictions（120 1X2 + 400 AH）
• 抽樣核對：Coventry City vs Worcester City → H=0.413 D=0.239 A=0.348；DB 讀回 0.412783 一致
• smoke 行已 DELETE 清理（afb_predictions 現 0 行，留俾真 forward run）

🔧 過程中抓到並修好一個真 bug
• 症狀：runner 寫入報 520 行但 readback 0 行
• 根因：主 connection 早前查詢已開 REPEATABLE READ snapshot transaction，另一 connection（db_write_predictions 自帶）commit 嘅新行喺舊 snapshot 入面不可見
• 驗證：三步 probe（A 開 snapshot → B 寫入 → A 讀 0 → A commit → A 讀 1）重現並確認
• 修復：readback 前 conn.commit() 結束舊 transaction；已註釋說明

═══════════════════════════════
🚫 PUSH BLOCKER（需要 Main Agent/Kris 處理）
═══════════════════════════════

Commit 66fd235 + Layer 1 嘅 c405104 都喺 local main（ahead 2），push 唔到：

1️⃣ SSH 路：origin = git@github-afb:ryanlam0618/aifootballbets.git，但呢台 host 嘅 ~/.ssh 冇 github-afb alias、冇 deploy key（ssh: Could not resolve hostname github-afb）
2️⃣ HTTPS 路：credential helper（workspace/scripts/git-credential-env.sh）讀 .env 嘅 GITHUB_TOKEN — 呢個 token 已 401 失效（Duncan 2026-10-26 已記錄），helper 冇有效 credential 回傳 → non-interactive push 失敗

建議解法（任擇）：
• 將 github-afb deploy key + ~/.ssh/config Host 段落加到呢台 host（Duncan 話 key ✓ 已有 — 可能喺另一台機）
• 或者更新 workspace .env 嘅 GITHUB_TOKEN（另一 task）

Push 恢復後一句 `git push origin main` 即可（兩個 commit 都會上去）。

═══════════════════════════════
📌 備註 / Follow-up
═══════════════════════════════

1️⃣ 純 stdlib 設計：dc_model 零 numpy/scipy 依賴 — 呢個決定喺 host 重啟（system python 被清空）之後證明係正確嘅，fit/測試照跑
2️⃣ 環境事故記錄：2026-10-28 host 重啟後 system python dist-packages 全清（pandas/pymysql/dotenv/requests/pytest 全失蹤、pip/ensurepip 冇埋）— 已用 repo README 記載嘅 get-pip.py --user --break-system-packages 路徑恢復 pytest 9.2.0 + pandas 3.1.0 + pymysql 2.2.8 + dotenv + requests（user-site 喺 /root/.local，重啟後應該仲喺）
3️⃣ fit 約 2-3 分鐘/次（52K 場純 Python）— 日常一天一跑可接受；若要提速可加參數快取（data/v2/models/ 已 gitignored）— 留 follow-up
4️⃣ rho=+0.010 屬細正值：tau 效應喺呢個數據集溫和；--fit-xi 未默認開（跑一次多 5 個 fit）— 建議 Kris 第一次正式 run 時加 --fit-xi 試
5️⃣ 既有紅測試 test_paper_repro_7d 冇碰（照指示）
6️⃣ appdb 齋 snapshot 冇未來 scheduled 場（最新 finished 2026-10-04）— 正式 forward 預測需要先跑 fixtures 同步（TakeData/sofa_score backfill 或者接 SofaScore 今日賽程）— 呢個係 Layer 2 之後嘅數據面跟進項

═══════════════════════════════
📎 產出清單
═══════════════════════════════

• Commit 66fd235（local）：models/dc_model.py、scripts/run_dc_predictions.py、tests/test_dc_model.py
• DB：afb_predictions 已實測寫入/讀回路徑（smoke 行已清）
• 測試：全套 81 pass / 1 fail（既有）
• 本報告：subagent_results/afb-layer2-T1-dc-coles.md（+ .json）
