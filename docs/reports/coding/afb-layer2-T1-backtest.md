📊 LAYER 2 T1-BACKTEST — DC 模型回測框架 + 實測報告
任務：afb-layer2-T1-backtest
日期：2026-10-30 ｜ 執行：Forge（coding agent）
Repo：aifootballbets @ main，commit ead6fac（已 push origin/main ✓）
基線：T1（66fd235）之上

═══════════════════════════════
⚡ TL;DR（五句）
═══════════════════════════════

1️⃣ Backtest 框架完成：時間序 70/30 holdout + 14 窗 walk-forward（季步進、嚴禁隨機切分、每窗 as-of fit）— 報告已出實數。
2️⃣ 核心實測（15,609 場驗證）：1X2 命中率 49.6%（holdout）/ 50.6%（walk-forward pooled），log-loss 1.038 / 1.018 — 落喺學術 50–56% 天花板區間內，符合預期。
3️⃣ 最有價值嘅發現係負面結果：同 3,818 場有莊家賠率嘅子集上，模型命中率 49.2% vs 市場大熱門 56.0%，而且模型有系統性主場偏好（Home edge +2.5pp / Away −2.3pp）— 現階段模型單獨無市場 edge。
4️⃣ 校準報告：中段（0.2–0.6）近完美校準，但極端值嚴重過度自信（[0.9–1.0) 預測 0.937 vs 實際 0.660）— isotonic/temperature 校準應該係 T2 嘅第一優先組件。
5️⃣ 過程修好三個真 bug：match_odds 1x2 賠率儲喺 fractional_value 欄（home_odds 三欄全 NULL）、NaN 傳染入 JSON、history rows 缺 match_id — 全部有防護/修復。

═══════════════════════════════
🔧 交付物
═══════════════════════════════

• scripts/backtest_dc.py — 回測框架
  – time_split：按日期序 70/30（邊界日歸 validation，零同日洩漏）
  – walkforward_windows：滾動窗（默認 91 日季步進），每窗 as-of fit（嚴格只用窗前歷史）
  – 指標：1X2 命中率 / multi-class log-loss / calibration 10 桶；AH 五線 pred-vs-real eff + pick 命中率 + pts/bet；市場對比（de-vig edge）
  – 輸出：reports/backtest_dc_report.txt + .json（整體 + 分聯賽 + 分線）
• afbdb/history.py — history rows 加 match_id（additive，解鎖 odds join）
• tests/test_backtest_dc.py — 18 個 hermetic 測試（切分/窗位/指標/AH 結算語義/分數賠率解析/渲染）
• reports/backtest_dc_report.txt + .json — 實測報告（已入 repo 工作樹，reports/* 係 gitignored）

═══════════════════════════════
📊 實測結果（appdb 52,021 場 finished，2015→2026-10）
═══════════════════════════════

🔢 HOLDOUT（邊界 2023-05-17：train 36,412 / val 15,609；fit rho=−0.02, home_adv=+0.2465）
• 1X2：命中率 0.4957、log-loss 1.0379

🔁 WALK-FORWARD（14 窗 × 91 日，2023-05-17 → 2026-10-04，每窗 as-of 重 fit）
• Pooled：命中率 0.5059、log-loss 1.0176
• 窗區間：hit 0.4724–0.5273、ll 0.9873–1.0625（穩定，冇某窗爆標）

🎯 AH 五線（holdout，home-side eff；pred = 模型平均、real = 實際結算）
• 0.0：pred 0.5675 / real 0.5478
• 0.25：pred 0.6276 / real 0.5981
• 0.5：pred 0.6877 / real 0.6485
• 0.75：pred 0.7294 / real 0.6950
• 1.0：pred 0.7712 / real 0.7414
→ 模型喺高線一致高估 2–4pp（大熱門過度自信嘅另一面證據）

💰 市場對比（3,818 場有 1x2 分數賠率嘅驗證場，de-vig 後）
• Mean edge：Home +0.0251 / Draw −0.0013 / Away −0.0232 → 模型系統性主場偏好
• 市場大熱門命中率 0.5602 vs 模型 0.4919（同一子集）、雙方一致率 0.4007
→ 結論：現階段 DC 模型單獨跑唔贏市場大熱門 — 同 Scout 報告「莊家 closing odds 係最強預測器」完全一致

📉 校準分桶（1X2，全部驗證場）
• 0.2–0.6 區間近完美：pred 0.2547/real 0.2506、pred 0.445/real 0.4513
• 極端過度自信：[0.8–0.9) pred 0.840/real 0.688；[0.9–1.0) pred 0.937/real 0.660（僅 97 樣本）
→ T2 建議：isotonic/temperature 校準（Scout 報告亦列為 2026 標配）

🏆 分聯賽（樣本 ≥ 400 場嘅亮點/弱點）
• 弱：A-League Men 0.400、AFC CL Two 0.416（ll 1.197）、Chinese FA Cup 0.443（ll 1.331 — 細樣本+盃賽隨機性）
• 相對好：Copa del Rey 0.595、Coppa Italia 0.707（盃賽低輪次對戰懸殊，命中率虛高屬正常）

═══════════════════════════════
🐛 過程中抓到並修好嘅 bug
═══════════════════════════════

1️⃣ match_odds 儲存格式：1x2 賠率喺 choice_name（'1'/'X'/'2'）+ fractional_value（'5/4' 分數），home_odds/draw_odds/away_odds 三欄全 NULL → 首版 market 對比 n=0。修復：_fractional_to_decimal 解析器 + Full time 過濾 + per-choice 平均（有 8 個解析邊界測試）。
2️⃣ NaN 傳染：Away mean_edge 出 NaN（devig/market 端非有限值）。修復：isfinite 防護（edge append + 彙總兩層）；probe 證實模型 probs 0/15,609 非有限。
3️⃣ history rows 缺 match_id：odds join 唔到。修復：afbdb/history.py 加欄（additive，現有用家唔受影響）。

═══════════════════════════════
✅ 驗證
═══════════════════════════════

• pytest 全套：99 passed / 1 failed（唯一 fail 係既有 test_paper_repro_7d，照指示未碰；baseline 62 保持 ✓）
• 實跑證據：兩次全量 backtest run（各約 40 分鐘，12+ as-of fits）+ market merge run，關鍵數字見上
• Commit ead6fac 已 push origin/main ✓（deploy key 正常）

═══════════════════════════════
🧭 對 T2 嘅建議（backtest 數據驅動）
═══════════════════════════════

1️⃣ 機率校準（isotonic/temperature）— 極端桶 0.94→0.66 嘅差距係現時最大可修缺陷
2️⃣ 收緊選注：模型無市場 edge 前提下，AH pick 只應該做「市場價明顯錯」先落注（edge 門檻對 de-vig market，唔係對 raw odds）
3️⃣ 主場偏好修正：home_adv 全局單參數可能掩蓋聯賽差異 — per-league home advantage 係低成本實驗
4️⃣ 盃賽/細樣本聯賽（A-League、AFC CL Two、足協盃）單獨處理或降低權重

═══════════════════════════════
📎 產出清單
═══════════════════════════════

• Commit ead6fac（已 push）：scripts/backtest_dc.py、tests/test_backtest_dc.py、afbdb/history.py
• 報告：reports/backtest_dc_report.txt + .json（實數）
• 本 artifact：subagent_results/afb-layer2-T1-backtest.md（+ .json）
