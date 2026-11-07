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

## 7. 下一步（等 Kris 拍板）
- GBM（T6）— 業界主力，但要夠數據；paper trading + CLV 追蹤 3 個月
- PHASE8（剩餘 duplicate rows）— 未批；合成 ID 對賬（Sofascore backfill 前）
- 實時賠率（要 proxy / cron 設計）
- 2,091 條 26/27 incident errors patch + re-run

## 6. 法律紅線

只有 HKJC 合法；離岸投注刑事；**repo 刻意唔做執行層**。未驗證（正 CLV 幾千注樣本）唔好落真錢；Kelly 只用 1/4。
