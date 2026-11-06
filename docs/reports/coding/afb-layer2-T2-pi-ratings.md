⭐ LAYER 2 afb-T2 — Pi-Ratings（賽果序列評分，逐場進化）
任務：afb-layer2-T2-pi-ratings
日期：2026-10-31 ｜ 執行：Forge（coding agent）
Repo：aifootballbets @ main，commit 642add0（已 push origin/main ✓）
Workboard：afb-layer2 卡 dc01fa34（running → 完成待標）

═══════════════════════════════
⚡ 總結
═══════════════════════════════

1️⃣ Pi-Ratings 系統完整實現（Constantinou & Fenton 制式：每隊 home/away 兩個 rating、逐場進化、4-way 誤差更新），純 stdlib。
2️⃣ **驗收通過**：walk-forward RPS 相對改善 **+5.79%**（目標 ≥1%；DC 0.22862 → PI 0.21538）— 超出細樣本預期上限（1-4%）。
3️⃣ 全面勝出：log-loss 0.98702 vs 1.03792、Brier 0.19661 vs 0.20664、hit 52.0% vs 49.6% — 三指標全部改善。
4️⃣ 溫度校準 T=0.875（pi 概率偏保守需 sharpening）— 校準後 test 半窗 RPS +4.77%，仍然 PASS。
5️⃣ 分聯賽全面改善：UECL +7.1%、UEL +7.0%、FA Cup +9.0%、Bundesliga +3.5%、Serie A +2.4%、EPL +2.2%、J1 +2.0%；僅 La Liga 持平（+0.02%）。

═══════════════════════════════
🔧 實現細節
═══════════════════════════════

• models/pi_ratings.py
  – 每隊 h（home）/ a（away）兩個 rating（goal-difference 尺度，均值 0 起步）
  – Expected supremacy：sup = h_i − a_j
  – 更新（誤差 δ = y − sup，4-way 分配）：h_i += κωδ、a_i += κ(1−ω)δ、a_j −= κωδ、h_j −= κ(1−ω)δ
  – 概率轉換：sup → λ_home = (μ_total+sup)/2、λ_away = (μ_total−sup)/2 → Poisson 矩陣 → 1X2
  – μ_total：per-league as-of（時間衰減 + shrink 50 場等效到 global）
• 常數調參：κ × ω grid（6×5=30 點）喺 train 序列上以 supremacy MAE 揀出（κ=0.05、ω=0.6）— 只用 train，零洩漏
• scripts/backtest_pi.py：warm-up（36,412 場 train）→ val 逐場「先預測後更新」（結構性零洩漏）→ 溫度校準（val 前半 fit、後半 apply，同 T2① 紀律）→ DC baseline 對比
• models/metrics.py：RPS / Brier / ECE（驗收指標要求）

═══════════════════════════════
📊 實測數字（52,021 場；val 15,609 場 walk-forward）
═══════════════════════════════

驗收指標：
• DC raw RPS = 0.22862 ｜ PI raw RPS = **0.21538** ｜ 相對改善 **+5.79%** → PASS ✅
• 校準後 test 半窗：DC temp 0.22893 vs PI temp 0.21801 → +4.77% ✅

全 val 指標：
• DC：RPS 0.22862 / ll 1.03792 / Brier 0.20664 / hit 0.4957
• PI：RPS **0.21538** / ll **0.98702** / Brier **0.19661** / hit **0.5201**

溫度校準：PI T=0.875（sharpening — pi 原始概率偏保守），校準後指標基本持平（0.99417→0.99422）— pi-ratings 經 supremacy→Poisson 轉換後本身校準已良好。

分聯賽 RPS 相對改善（n≥50）：
• FA Cup +8.98%、UECL +7.06%、UEL +6.96%、Bundesliga +3.51%、UCL +2.45%、Serie A +2.44%、EPL +2.24%、J1 +1.98%、Ligue 1 +0.39%、La Liga +0.02%
• 觀察：盃賽/ continental 賽事改善最大（DC 喺杯賽弱），頂級聯賽 PI 仍有細幅優勢

⚠️ 誠實備註：
• RPS 改善唔等於市場 edge — 今次冇做 ROI 對比（pi 概率 vs 市場 de-vig 未測；T2① 已證明 DC 校準後都無 edge，pi 大概率同樣需要 market blend 先有機會）
• 常數係數據調參（唔係 paper 原值）— paper 喺自己數據集調參，呢度喺 appdb 調，方法一致
• pi-ratings 係逐場序列模型 — 無法預測「冇歷史交手資料嘅新隊」（新升班馬起步 rating=0 中性，熱身期約 10 場）

═══════════════════════════════
✅ 驗證
═══════════════════════════════

• pytest 全套：121 passed / 1 failed（唯一 fail 係既有 test_paper_repro_7d；111 baseline 保持 ✓）
  – 新增 10 測試：更新方向、supremacy 符號、概率歸一、參數調叽、μ_total shrinkage、RPS 已知值 + 排序性
• 實跑：真 DB walk-forward（52,021 場序列、1,971 隊、15,609 val 預測）
• Commit 642add0 已 push origin/main ✓
