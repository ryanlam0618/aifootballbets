# aifootballbets — Project 實際狀態

> 📌 **更新：2026-11-07 04:2x（Duncan，經 artifact 全盤核實）**。同舊 memory 印象唔同嘅位會標 ⚠️。
> 規則：每完成一個 phase / backtest 就更新呢份。

## 1. Layer 1 — 數據地基 ✅（2026-09 完成）

- Sofascore 全量 backfill：15/16–25/26 + 26/27（唯一結構性缺口 = Australia Cup 20/21，COVID 取消）
- DB schema + loader + `afb_layer` 基建
- match_odds UNIQUE key `uq_match_odds_identity` deployed（2026-09-27）

## 2. Layer 2 — 模型層 v1 ✅（⚠️ 2026-10-28 ~ 10-31 已完成，唔係「未開工」）

**全部有 completed artifact 證據（`docs/reports/coding/afb-layer2-*`）：**

- **T1 DC 模型**（10-28，commit `66fd235`）：DC(1997) 完整實現 — 攻守 MLE + tau 四格修正 + 時間衰減 + per-league HA + AH quarter-line 定價。全 DB fit：51,969 場 / 858 隊 / rho=+0.010 / home_adv=+0.265。19 新測試全綠（全套 81 passed / 1 failed 既有）
- **T1.3 Cup Round HA**（10-31）：cup round 拆 bucket 調 HA — ACCEPTANCE PASS（ECE 0.0594→0.0548）
- **T2 pi-ratings**（10-31）：戰力值模型完成
- **T2 calibration**（10-31）：isotonic / temperature / grouped-T 對比 — 最佳 grouped temperature（continental 1.475 / cup 1.325 / league 1.1）；test ll 1.0448→1.0381
- **T3 xG 特徵**（10-31）：xG 特徵工程完成（DB 有 `afb_team_rolling_xg` 21K rows + `match_shotmap` 766K rows）
- **T4 market blend**（10-31）：**關鍵發現 — market baseline rps=0.20645，全部 blend 權重 w=0 最優** ⇒ 而有模型（DC/pi，temp 校準後）都跑唔贏 de-vig 市場；ROI 全 grid 負數。同業界 Shams 2024 結論一致
- **T5 pipeline**（10-31，commit `3fab022`）：`run_pipeline(day)` v1 收官 — pick_day → odds snapshot → predictions（DC + pi 雙模型）→ settle；冪等驗證（重跑 0 寫入）；連續兩日實跑成功（10-03：45 fixtures → 270 predictions；10-04：7 fixtures → 42 predictions）；覆蓋盤點 24 competitions 全有 1x2 賠率（16-25% 場次密度）
- **T1 backtest**（10-30）：走向前 backtest 基線

**⚠️ Backtest 證據（`reports/backtest_*.md`，repo 根）**：模型 v1 對市場冇優勢（market w=0 最優、ROI 負）— 呢個係誠實基線，唔係失敗；下一步靠 T9 CLV 管線 + 更多數據（odds 覆蓋後）重測。

## 3. Odds 數據工程 ✅（2026-11-05 ~ 11-07）

- OddHarvester：security audit CLEAN → smoke test → Patchright 遷移 → SLUGFIX（OddsPortal 覆蓋 11→24 competitions，commit `39e709c`）
- CLV backfill Batch 1（11 聯賽 × 2024-25+2023-24）+ Batch 2（UCL/UEL/UECL/EFL Cup/CSL/AFC comps × 2 季）→ 96,893 rows / 5,474 matches / 15 bookies
- teams 表校準 Phase 1-7：49+ 行驗證改名 + 4 對 same-club dedupe（146 FK rewrites）→ alias remap **99.9%**（剩 3 條結構性 unmatched 如實記錄）
- **T9 CLV 基礎設施**（11-07，commit `526ca48`）：de-vig（proportional + Shin）→ closing line 32,215 rows → 共識表 5,431 場（99.1% 覆蓋，dispersion 中位 ~2%）→ CLV 函數（clv_ratio / ev_vs_fair）

## 4. 業界對標（Scout 研究，`docs/reports/seo/`）

- 藍圖同業界 2026 主力組合一致（DC + pi-ratings + GBM + de-vig + 校準 + Kelly + market prior）
- 硬指標：ML 1X2 天花板 50-56%；DC 1997 難打敗；CLV = 唯一北極星；Kaunitz 2017 實戰 8.5% 後封帳
- T4 實測（w=0 最優）已驗證「模型難贏市場」— 下一步差異化要靠：xG/rolling_xg 特徵（DB 有現貨）、CLV 管線、或次級市場

## 5. T9b 模型重考 ✅（2026-11-07，commit 526ca48 + 本 commit）

- 樣本升級：clv_consensus_closing 5,430 場（2023-02-17 ~ 2025-05-31；T4 舊樣本 1,908）— calib/test 對半
- 特徵升級：DC + pi + xG-Poisson（rolling_xg 特徵，覆蓋 2,413/5,430 = 44.4% 有 n_history>=3）
- KPI 升級：主 KPI = CLV（對 de-vig closing consensus）；RPS/log-loss 參考
- **結果（誠實）：重考確認 T4 結論** — market（closing consensus）rps=0.19482 vs 最佳模型（pi）rps=0.21236；全部源 positive raw edge（pi +13.5pp / dc +23.7pp / xg +37.6pp）但 ROI 全負（pi -1.2% / dc -7.4% / xg -9.9%）= 模型相對 closing 系統性 miscalibrated，唔係 value。closing consensus 比 T4 市場基線更銳利（0.19482 vs 0.20645）
- rolling-xG 特徵零增益：pi_xg w*=1.0（純 pi 主導）、dc_xg w*=0.9；xG-Poisson standalone 最弱（rps 0.23187 / hit 0.351）
- 順手任務：shotmap xG 覆蓋核實 — official xG 只有大五聯賽 100% + UCL 77-82%；Emperor's Cup 0%、FA Cup 27-30%、UECL ~50% shotmap 缺；rolling_xg 經 calibrated fill ~100%
- 報告：reports/backtest_t9b_report.md/json；腳本：scripts/backtest_t9b.py（commit 526ca48 + 本 commit）

## 6b. T10-AH 賠率爬蟲 ✅（2026-11-07，Kris 拍板「刮，先做爬蟲」）

- **目標**：Batch 1+2 同批 matches 補刮 OddsPortal AH FullTime 賠率（亞洲讓球，含 quarter-line）
- **結果**：`afb_odds_snapshots` run_id='clv_backfill_ah' — **430,381 rows / 8,408 場 / 72 條 distinct lines**（遠超 1x2 嘅 96,893 rows / 5,474 場）
- 覆蓋：PL 760 / La Liga 760 / Serie A 759 / J1 682 / Ligue 1 617 / Bundesliga 616 / UECL 593 / CSL 467 / K1 464 / FA Cup 457 / UEL 417 / UCL 378 / A-League 345 / AFC CL 279 / Copa del Rey 240 / EFL Cup 185 / AFC CL2 121 / Emperor's 114 / Coppa 88 / Australia Cup 66
- 配對：8,582 刮 / 8,375 配對（97.6%，alias-table 機制 + PHASE7 side-swap）/ 207 no-match（2.4%，集中 FA Cup/Copa del Rey 低輪次）
- **誠實聲明**：preview-only passive 模式 — 一條 line 一個 quote（OddsPortal average view），**冇 per-bookmaker breakdown**（full-line click 模式量度過要 ~15 日所以放棄）；closing-only snapshot（同 1x2 一致，無 open->close 序列）
- 執行環境：afb-ah-scraper-tmp 容器（Kris option C，12GB memory — gateway 容器 4GiB cgroup 裝唔落 chromium）；工具 OH_LOW_MEM patch（oddsharvester ae4bfbe）+ ah_backfill.py（19e7b47, 67fdb24）
- 報告：reports/ah_coverage_inventory.md（gitignored per convention）

## 6c. T11-AH 回測 ✅（2026-11-07，Kris 批准「批做AH回測」）

- **問題**：「AH（兩個 option + 走水）會唔會易贏過 1x2？」
- **答案（誠實）**：**market 仍贏，但 AH 對模型友善 ~4.4 倍** — market Brier 0.21037 vs 最佳校準模型（pi）0.21435（gap 0.0040）對比 T9b 1x2 嘅 gap 0.0175；5 個聯賽 pi 與 market 差距喺噪聲內（A-League/Bundesliga/Ligue 1/PL/Serie A，部分負數=模型名義上更好但喺噪聲內）
- **Raw CLV signature 同 T9b 一致**：positive edge（dc +30.3pp / pi +20.9pp）+ negative ROI at actual odds（-3.4% / -3.1%）= miscalibration 非 value（每源 4,000+ 注，非小樣本噪聲）
- **Isotonic 陷阱（如實列出）**：校準後人人轉正 — 連 market 自己 recalibrate 都 +3.38% >= pi +2.96% >= dc +2.48% — 增益嚟自 average-view 軟線（人人可得，非模型技能）；對 sharp book 大概率消失；法律紅線不變（唔落真錢）
- **結構發現**：DC miscalibration 集中深線（|line|>=2.0 gap +0.123）同不平衡聯賽（CSL +0.108 / Coppa +0.103）；pi 全域平坦（max +0.026）— 模型層若用 AH，pi + 淺線係唯一可辯護配置
- **方法**：8,408 場 / 每場主線（最接近平衡）/ calib-test 對半 / DC frozen 2023-02-16 / pi walk-forward / settlement 用真實 quarter-line 規則（單元測試鎖死慣例）/ binary isotonic 校準先行
- 過程修復：`_ah_side` 深度 guard 放寬（439ddc4，20 tests 綠）、'AH 100.0' scrape artifact 過濾、away settlement 符號、common-subset join 型別
- 報告：reports/backtest_t11_ah_report.md/json；腳本：scripts/backtest_t11_ah.py

## 6d. T12 本金模擬 ✅⚠️已更正（2026-11-08，Kris 要求「純勝率落注，本金 10000」）

- ⚠️ **更正（2026-11-08）**：第一版有 stake bug — run_bankroll 將 per-unit P/L 當美元入帳（實際每注 1 蚊而唔係 100 蚊），最初報告嘅「冇破產、貼近打和」（-101.62/+242.53）係 1-unit journey，100 倍低估。已修正並公開更正；正確結果同 T12b flat 完全一致
- **規則**：唔睇 ROI/edge，每場必落注（1x2 揀模型機率最高 outcome；AH 揀模型 cover prob > 0.5 嗰邊），flat 100/注，本金 10,000，結算用 de-vig 前真實報價
- **修正後結果（如實）**：**1x2_pi 破產**（bet 2,066，final 67.20，輸 9,933）；**ah_pi +24,253**（final 34,253；ROI on staked +5.77%，avg odds 1.98，hit 53.55% vs break-even 50.48%）；**combined_pi +14,091**（1x2 腿破產路徑被 AH 利潤交錯救起）；**DC 全滅**（ah_dc 破產 bet 2,927 / combined_dc 破產 bet 1,022 / 1x2_dc -7,854）
- **ah_pi +5.77% 嘅誠實警示**：(a) 軟 average-view 線（冇 per-bookie dispersion）；(b) 同 T11 max-edge 規則（-3.08%）相反 — 兩個規則喺 favourite-aligned 場次揀相反邊，符號取決於規則唔係穩健模型特性；(c) T11 isotonic market-recal +3.38% 已顯示 average view 軟。唔構成可交易結論；法律紅線不變
- 報告：reports/bankroll_sim_t12_report.md/json（含更正段）；腳本：scripts/bankroll_sim_t12.py

## 6e. T12b 動態注碼模擬 ✅（2026-11-08，Kris 拍板「跑咗先知會唔會輸」）

- **三種注碼對比**（同 T12 樣本/pick 規則/settlement）：flat 100 vs quarter-Kelly（cap 5%/注，kelly≤0 跳過）vs bankroll 1%
- **Kelly 兩邊放大（理論預期）**：AH_pi_kelly 10,000 → **17,148,783**（1,715x，3,890 注，maxDD 14.0M）；1x2_pi_kelly → 175.9（近滅，1,416/2,715 注被負 Kelly 跳過）；dc_kelly 全部 ~19（近全滅）
- **1% bankroll 複利同方向**：AH_pi → 94,942（+849%）；1x2_pi → 3,105.8（-69%）；dc 全負
- **Kelley 特別報告**：單注最大損失 1,120,198（AH_pi_kelly）；max stake 5% cap；stake std 同 heavy-streak 喺 JSON
- **誠實結論**：17M 係噪聲級 edge 嘅路徑依賴複利（比例注碼唔會破產但變異數主導）；AH_pi 正路徑有 T12 之軟線警示 + 同 T11 max-edge 規則相反；全部唔構成可交易策略
- 報告：reports/bankroll_sim_t12b_report.md/json；腳本：scripts/bankroll_sim_t12b.py（重用 T12 build_priced_bets）

## 6f. T12c AH bootstrap + 敏感性 ✅（2026-11-08，Kris 指示驗證「真 edge 定路徑運氣」）

- **Bootstrap（1,000 i.i.d. 路徑）**：flat-100 全部 1,000 條路徑正回報（median 33,739、p5 24,600、0% 破產）；kelly/pct1 同樣 100% 正 — **+5.77% 唔係單一路徑運氣**（per-bet P/L 分佈正平均內部一致），**但 bootstrap 答唔到個 mean 本身係咪真**（重採樣同一 window，要 out-of-sample 先知）
- **線深切分（結構答案）**：淺線（|line|≤0.5）ROI **+6.83%**（2,261 注）/ 中線 **+7.22%**（1,295 注）/ **深線（≥1.5）-0.81%**（只有 42.2% 路徑正）— edge 完全集中淺/中線，同 T11 結構一致：模型 AH 意見只喺接近平衡線上有訊息
- **抽水敏感性（致命）**：+5.73%（0%）→ +3.25%（+5%）→ +0.78%（+10%）→ **-1.70%（+15%）** — **edge 食唔起 HKJC 級成本，唔可利用**（vig 表用二元結算近似，5.73% vs 精確 5.77% 差異無關痛癢）
- **Kelly 分數敏感性**：1/8 最穩（boot min 83,478）；1/4 median 16.5M（boot min 11,060）；full Kelly median 反而低過 1/4 且有路徑 -70%（3,020）— 過度下注拖累
- 量綱 sanity check 全綠（T12 教訓應用：flat 420,400 staked / +24,253 / final 34,253 重算吻合）；vig ROI 段曾犯同一量綱錯誤（100 倍低估）已修正
- **總結**：+5.77% 唔係路徑運氣但亦唔可以當已驗證真 edge — 單一 window、軟 average-view 線、規則依賴（T11 max-edge -3.08%）、食唔起 HKJC 級抽水；法律紅線不變
- 報告：reports/bankroll_sim_t12c_report.md/json；腳本：scripts/bankroll_sim_t12c.py

## 7. 下一步（等 Kris 拍板）
- GBM（T6）— 業界主力，但要夠數據；paper trading + CLV 追蹤 3 個月
- PHASE8（剩餘 duplicate rows）— 未批；合成 ID 對賬（Sofascore backfill 前）
- 實時賠率（要 proxy / cron 設計）
- 2,091 條 26/27 incident errors patch + re-run

## 6. 法律紅線

只有 HKJC 合法；離岸投注刑事；**repo 刻意唔做執行層**。未驗證（正 CLV 幾千注樣本）唔好落真錢；Kelly 只用 1/4。
