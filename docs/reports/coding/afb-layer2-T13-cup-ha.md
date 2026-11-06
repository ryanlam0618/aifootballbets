🎯 LAYER 2 afb-T1.3 — 盃賽 HA 分簿 + 輪次特徵（平玩版）
任務：afb-layer2-T13-cup-ha
日期：2026-10-31 ｜ 執行：Forge（coding agent）
Repo：aifootballbets @ main，commit 642add0（已 push origin/main ✓）
Workboard：afb-layer2 卡 27e6e061（running → 完成待標）

═══════════════════════════════
⚡ 誠實總結
═══════════════════════════════

1️⃣ **驗收半通過**：盃賽場次（n=3,083）校準誤差 **ECE 0.05944 → 0.05483（−0.00461 改善 ✅）**，但 **Brier 0.20249 → 0.20325（+0.00076 基本持平/微差）**。即係：輪次調整改善咗校準誤差，但冇改善整體 Brier — 兩個指標一升一降，照實講。
2️⃣ 輪次 delta 分佈符合直覺但幅度細：early +0.061、middle +0.024、late +0.002、final +0.033 — 盃賽 HA 高主要嚟自 league-per-league 層級（T2③ 已捕獲），輪次特徵增量細。
3️⃣ 進取版（分開 fit 攻防）照指示冇做 — 平玩版結果支持呢個決定：輪次效應太細，分開 fit 大概率過擬合。
4️⃣ walk-forward 紀律：adjustment 只用 train 盃賽場（6,798 場）單次 as-of fit，驗證集（3,083 場）零洩漏。
5️⃣ 產出仍然有用：per-cup × per-bucket 校準表已入報告，做 T6 特徵或者 T3 盃賽建模嘅基礎數據。

═══════════════════════════════
🔧 實現細節
═══════════════════════════════

• models/cup_round.py
  – round_bucket()：round_name → {early, middle, late, final}（關鍵字解析，semi/quarter 先於 final 檢查 — 修咗「Quarter-finals」誤判做 final 嘅 substring bug，有測試鎖住）
  – fit_cup_round_adjustment()：train 盃賽場按 bucket 組別，δ_b = shrink · ln(Σw·observed_home_goals / Σw·model_home_mean)，shrink 300 場等效
  – CupRoundModel：包住 per-league-HA base model；盃賽場 home mean × exp(δ_b)，非盃賽 passthrough（有 passthrough 測試）
• afbdb/history.py：round_name 欄（additive）
• scripts/backtest_t13.py：base fit（per-league HA）→ 盃賽輪次 adjustment → val 盃賽場 Brier/ECE before/after + per-bucket + per-cup

═══════════════════════════════
📊 實測數字（盃賽 val 場 3,083 場，train 盃賽 6,798 場）
═══════════════════════════════

驗收指標：
• Brier：0.20249 → 0.20325（delta **+0.00076**，基本持平微差）
• ECE：0.05944 → **0.05483**（delta **−0.00461**，改善 ✅）
• 依 board 指標「Brier/ECE 下降」— ECE 達標、Brier 未達標 → 半通過

輪次 delta（log home-goal multiplier）：
• early +0.061（n=49）、middle +0.024（n=5,938）、late +0.002（n=750）、final +0.033（n=61）
• 觀察：middle（主體）輕微正調整；late（半準/準決賽）幾乎零 — 準決賽階段主場優勢回落至聯賽水平

per-cup 亮點（n≥30）：
• 報告 JSON 有每個盃賽嘅 before/after Brier/ECE — Coppa Italia / Emperor's Cup 等 HA 高嘅盃賽喺 T2③ per-league HA 已受益，輪次層級增量集中喺 early/middle 桶

⚠️ 誠實備註：
• ECE 改善幅度（−0.005）屬細；Brier 無改善 — 輪次特徵唔係盃賽預測嘅遊戲規則改變者
• 輪次解析係關鍵字映射（round_name 格式各盃賽不一）— 已測常見格式，極端命名可能跌入 middle fallback
• 平玩版結論支持唔做進取版：連輪次加項都咁細，分開 fit 攻防嘅過擬合風險不成比例

═══════════════════════════════
✅ 驗證
═══════════════════════════════

• pytest 全套：121 passed / 1 failed（唯一 fail 係既有 test_paper_repro_7d；111 baseline 保持 ✓）
  – 新增 10 測試（與 T2 pi-ratings 共用檔案）：bucket 解析（含 Quarter-finals substring bug 回歸）、Brier 改善方向、non-cup passthrough、RPS 已知值
• 實跑：真 DB（52,021 場；盃賽 val 3,083 場）
• Commit 642add0 已 push origin/main ✓

═══════════════════════════════
📎 產出清單
═══════════════════════════════

• Commit 642add0（已 push）：models/cup_round.py、scripts/backtest_t13.py、models/metrics.py、afbdb/history.py（round_name）、tests/test_t2_pi_and_cup.py
• 報告：reports/backtest_t13_report.txt（md 版）+ .json
• 本 artifact：subagent_results/afb-layer2-T13-cup-ha.md（+ .json）
