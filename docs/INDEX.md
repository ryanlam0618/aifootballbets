# aifootballbets — Project Knowledge Index

> 📌 **CANONICAL SOURCE OF TRUTH**。任何 agent 講呢個 project 之前，**必先讀呢份 INDEX + project-state.md**，唔准靠 memory 印象。
> 建立：2026-11-07 04:1x（Kris 指令：整理 project 架構，防止 memory 出錯）
> 維護規則：每次完成新 phase / 新 backtest，**同一次 commit 內更新 INDEX + project-state.md**。

## 1. Project 係乜（一句）

用 Sofascore（fixtures/結果/lineups/xG）+ OddsPortal（1x2 賠率）數據，建立足球賽果預測模型，以 **CLV（Closing Line Value）為唯一北極星 KPI** 驗證有冇真 edge。**刻意唔做執行層**（HK 法律：只有 HKJC 合法，離岸投注刑事）。

## 2. 文件地圖

- `docs/project-state.md` — **項目實際狀態**（已完成/進行中/遺留，每次更新）
- `docs/data-catalog.md` — **DB 數據目錄**（表 + 實測 row counts，講數據前必查）
- `docs/lessons.md` — 方法論鐵律 + 事故教訓
- `docs/reports/coding/` — Forge 執行 artifacts（47 份，含 layer2 T1-T13 模型層 + 11/05-07 odds/teams 工程）
- `docs/reports/seo/` — Scout 業界研究（16 份：論文綜述、工具實況、ensemble 理論等）
- `reports/`（repo 根）— **backtest 報告**（backtest_dc / dc_t2 / pi / blend / xg / t13 + odds_coverage_inventory）— 模型測試證據，唔好搬
- `paper/` — paper trading ledger 相關
- `tests/` — pytest 套件（81 passed 基線，T1 後 100/1）

## 3. 五分鐘史（時間線）

- **Layer 1**（~2026-09）：Sofascore 全量 backfill（15/16–25/26 + 26/27）+ DB schema + loader
- **Layer 2 T1-T5 + T13**（2026-10-28 ~ 10-31）：**模型層 v1 完成** — DC + pi-ratings 雙模型、校準（temperature/isotonic 對比）、market blend、xG 特徵、walk-forward backtest、v1 pipeline、cup HA 修正
- **OddHarvester 升級**（2026-11-04 ~ 11-05）：security audit、smoke test、Patchright 遷移、SLUGFIX（覆蓋 11→24 competitions）
- **T9b 模型重考**（2026-11-07）：CLV 樣本 5,430 場 + rolling-xG 特徵重考 — **確認 T4 結論**（market closing rps 0.19482 vs 最佳模型 0.21236；positive edge + negative ROI = miscalibrated 非 value）；報告 reports/backtest_t9b_report.md
- **TEAMFIX / CLV 工程**（2026-11-05 ~ 11-07）：teams 表錯標修復（EPL 10 + La Liga 7 + 18 + 10 + 4 對 dedupe，共 49+ 行改名/合併）、odds backfill（Batch 1+2 → 96,893 rows）、alias remap（57%→99.9%）、T9 CLV 基礎設施（de-vig Shin + closing line + 共識表）

## 4. 反 memory-出錯守則

1. 講「有冇 X 數據」→ 查 `data-catalog.md` 或直接 query DB，唔准跟報告印象
2. 講「做咗/未做」→ 查 `project-state.md` + `docs/reports/`，唔准靠印象
3. 業界結論引用 → 標明來源 artifact（`docs/reports/seo/`）
4. 任何「我當/我以為」→ 即刻查證，錯咗即刻公開更正（誠實鐵律）
