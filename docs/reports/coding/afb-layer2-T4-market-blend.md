💰 LAYER 2 afb-T4 — 市場概率 de-vig + market blend（before/after + 誠實結論）
任務：afb-layer2-T4-market-blend
日期：2026-10-31 ｜ 執行：Forge（coding agent）
Repo：aifootballbets @ main，commit 0bddc1c（已 push origin/main ✓）

═══════════════════════════════
⚡ 誠實結論（Duncan 鐵律：冇 edge 就直講）
═══════════════════════════════

1️⃣ **RPS：冇任何 blend 權重跑贏純市場**。1,908 場賠率子集上，market baseline RPS 0.20645 係最強 — 全部 44 個 grid cell（4 概率源 × 11 權重）加權後 RPS 都係變差，且隨 w_model 上升單調惡化。模型概率（DC 或 PI、raw 或校準）喺概率質量層面 add 唔出價值。
2️⃣ 市場校準近乎完美：分桶 pred 0.2542/real 0.2456、pred 0.4484/real 0.4686 — de-vig 後嘅市場概率已經係最強單一預測器，完全符合 Scout 報告核心論點。
3️⃣ ROI 一個誘人但未證實嘅訊號：pi blend w=0.1 出 **+21.7% ROI（215 注）**、pi_temp w=0.1 +12.6%、w=0.2 +2.7% — pi 來源喺低權重區一致正數，但 (a) 樣本細（215-666 注）、(b) 44 格 grid 揀最好有選擇效應、(c) DC 全部負數。**唔夠證據報喜**，需要 out-of-sample 確認。
4️⃣ DC blend 全滅：所有權重 ROI −2.6%~−8.7%。DC 概率連細幅市場增益都提供唔到。
5️⃣ 結論：**現階段系統冇投注價值**。市場已消化模型所知的一切。唯一未證實嘅方向係 pi-blend 低權重區 — 需要 out-of-sample 驗證先可以認真考慮。

═══════════════════════════════
📊 實測數字（1,908 場賠率子集；calib 半窗 1,909 / test 半窗 1,909）
═══════════════════════════════

基準（w=0，純 de-vig 市場）：
• RPS 0.20645 ｜ ll 0.97841 ｜ hit 53.67% ｜ Brier 0.19384
• 校準桶近乎完美（0.1-0.8 區間 pred/real 差 <1pp）

RPS 曲線（隨 w_model 單調惡化 — 全部源）：
• dc_raw：w=0.1 → 0.20672 ... w=1 → 0.23328（+13% 惡化）
• dc_temp：w=1 → 0.22998（溫度校準 T=1.275 有幫助但唔夠）
• pi_raw：w=1 → 0.21997（+6.5% 惡化 — 最接近市場）
• pi_temp：w=1 → 0.22609（T=0.70 sharpening）

ROI 模擬（EV ≥ +2% 先落注，市場平均賠率結算）：
• pi_raw w=0.1：215 注，ROI **+21.7%** ⚠️ 樣本細
• pi_temp w=0.1：225 注，ROI **+12.6%** ⚠️ 同上
• pi_raw w=0.2：592 注，ROI +0.96%；pi_temp w=0.2：666 注，+2.73%
• pi w≥0.4 / 全部 DC w：−0.7%~−8.7%
• w=0（純市場）：0 注（de-vig prob × vigged odds 恆為 −EV，正確行為）

═══════════════════════════════
🧭 方法論紀律
═══════════════════════════════

• 賠率子集自身前後半分窗：前半（1,909 場）fit 溫度校準器、後半（1,908 場）評估 — 零洩漏
• DC：boundary（2023-05-17）單次 as-of fit（frozen）
• PI：逐場 walk-forward（先預測後更新，T2 調參 κ=0.05/ω=0.6 照用）
• 概率源 × 市場 blend：p = w·p_model + (1−w)·p_market_devig（線性組合自動歸一）
• 市場子集數據現實：賠率只覆蓋 2024-12 之後（+2015-16 年代零星）— calib 窗（2023-05→2024-12）零賠率，故改用子集內前後半分窗（已如實記錄）

═══════════════════════════════
📋 CLOSING ODDS 累積機制 SPEC（T10 CLV 前提，按要求交付）
═══════════════════════════════

• 目標：每場喺多個 pre-kickoff 時點捕獲賠率，令 CLV（bet odds vs closing odds）可量度
• 收集器：run_day cron 擴展 — T-72h/T-48h/T-24h/T-6h/T-1h 各取一次 + 開賽後一次作 closing proxy
• 儲存：afb_odds_snapshots（Layer-1 已上線）— (match_id, market_key, selection, bookmaker, captured_at_utc) 一行
• Closing 定義：captured_at_utc ≤ kickoff − 60min 嘅最新快照；窗口冇樣本就退而求 −30min
• 覆蓋要求：afb-T10 需要 ≥30 注有 closing odds（注市場 + 參考莊兩邊齊）
• 冪等：unique key 已存在，重跑 INSERT IGNORE
• 工作量：本卡只交 spec；實作隨 afb-T5 pipeline cron 落地

═══════════════════════════════
✅ 驗證
═══════════════════════════════

• pytest 全套：121 passed / 1 failed（既有 test_paper_repro_7d；121 baseline 保持 ✓）
• 實跑：真 DB（52,021 場；1,908 場賠率子集全量 grid）
• Commit 0bddc1c 已 push origin/main ✓

═══════════════════════════════
📎 產出清單
═══════════════════════════════

• Commit 0bddc1c（已 push）：scripts/backtest_blend.py
• 報告：reports/backtest_blend_report.json + .md（44 格 grid 全數據）
• 本 artifact：subagent_results/afb-layer2-T4-market-blend.md（+ .json）
