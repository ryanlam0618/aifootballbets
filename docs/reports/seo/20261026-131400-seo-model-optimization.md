🔍 aifootballbets 模型優化研究報告
任務：20261026-131400-seo-model-optimization
日期：2026-10-26 ｜ 整理：Scout（SEO agent）
基準：Forge 真 code 審查（20261026-051100-coding-aifootballbets-compare.md）
目標：針對 repo 現狀（獨立雙 Poisson、無 DC tau、無 calibration、xG 未用、xgboost 零用）提供有網上證據嘅優化方向
格式：純文字 + emoji 分組，無 markdown 表格

═══════════════════════════════
🎯 優化清單（按優先級排序）
═══════════════════════════════

🥇 1. 加入 Dixon-Coles tau 低分修正
咩優化：喺 Poisson 進球矩陣加入 τ(ρ) 修正因子，針對 0-0、1-0、0-1、1-1 四個低分 scoreline 做相關性調整。ρ（rho）用歷史數據 MLE fit（scipy.optimize.minimize L-BFGS-B），配合指數時間衰減權重（exp(−ξ·t)，ξ≈0.0065/日，半衰期≈107 日，或手動 ξ=0.0018 半衰期≈1 年）。
網上證據：
• Dixon-Coles 1997 原始 paper：ρ 控制低分相關性，τ 函數只動四個 scoreline，其餘保持獨立 Poisson。
• predictionengine.app (2026)：詳細公式 + MLE 優化流程 + 1,216 場 walk-forward backtest 結果；python 實現用 scipy.optimize.minimize。
• dashee87.github.io：完整 python 實現（含時間衰減），展示 τ(ρ) 對 draw 概率嘅具體影響。
• penaltyblog (PyPI)：pip install penaltyblog 即有現成 DixonColes、KarlisNtzoufras、TimeDecay 類，幾行代碼可用。
• dev.to (commodus67, 39dc)：實戰 ξ=0.0018（半衰期≈1 年）同 3 季數據 fit。
• MetricGate、statsultra.com：tau 修正點解要、點樣改善 0-0/1-1 under-prediction。
對 repo 預期效果：O/U 2.5 同 AH 定價直接受益（low-score 相關性係定價關鍵）；draw 概率校準；RPS 有望改善 0.005–0.015（常見文獻報告幅度）；更準確嘅 0-0/1-1 概率 = 更準確嘅 O/U 2.5 edge。
實施難度：🟢 低（penaltyblog 現成，或自行加 tau 函數約 50 行 python，MLE fit 幾分鐘）。
優先級：🔴 P0（最高，Forge 已列為頭 2 優先改進，模型基石，風險極低）。

🥈 2. 換用 / 加入指數時間衰減加權（替換簡單 10 場均值）
咩優化：team_strength 而家用「近 10 場簡單均值 + 12 場 shrinkage」。改用指數衰減加權：最近場次權重高，舊場次按半衰期遞減（文獻常用 half-life 30–90 日，或 DC 原文 ξ=0.0065 → half-life ≈107 日）。保留 shrinkage 防極端值。
網上證據：
• Dixon-Coles 1997 原文：引入 exp(−ξ·t) 時間權重，ξ=0.0065/日（half-life ≈107 日）。
• dashee87.github.io / dev.to：同樣建議 ξ≈0.0065 或按 league tune 半衰期 30–100 日。
• arXiv 2608.11505 (2026-08)："Does a Structural Model Add Anything to the Closing Price?" — 明確用 exp(−ξ·t) 加權 + Elo rating 做基準，證實近期數據信息量大。
• arXiv 2404.08136：Exponentially Weighted Moving Models 理論框架，half-life 參數直接可解釋。
對 repo 預期效果：球隊狀態變化（傷兵、換帥、士氣）能更快反映入攻防強度；去除「10 場硬切」嘅邊界效應；預期 1X2 準確率微升、RPS 改善、CLV 更穩（特別係賽季初同轉會窗後）。
實施難度：🟢 低（把均值換做加權均值，保留 shrinkage 邏輯，約 30 行改動）。
優先級：🟠 P1（高，配合 DC tau 做完整統計模型基石，無外部依賴）。

🥈 3. 引入動態評級系統（pi-ratings 或 Elo）作為額外特徵
咩優化：現行 strength 純用進球數。引入 pi-ratings（Constantinou & Fenton 2012）或 Elo（經典）作為獨立強度指標，可作為模型輸入特徵或 shrinkage target。
網上證據：
• Constantinou & Fenton (2012) "Determining the level of ability of football teams by dynamic ratings based on the relative discrepancies in scores between adversaries"：pi-rating 只用相對比分差動態更新，無需進球期望，證實比 Elo 更快收斂、更穩健。
• pi-football Bayesian network (Knowledge-Based Systems 2012/2013)：pi-rating 嵌入 Bayesian network 做 joint inference。
• 2022 JSA (Sage) "Investigating the efficiency of the Asian handicap football betting market"：用修改版 pi-rating 做 AH 定價，表現優於純 Elo。
• arXiv 2403.07669 (Ch.1 ML for Soccer) 引用 Constantinou 2019 Dolores (Machine Learning 108, 49–75)：Hybrid Bayesian Network 結合動態評級 + 多源特徵，達到 SOTA 水平。
• betsystore.com (2026-07)：列出 pi-rating 為三大傳統統計模型之一（同 DC bivariate Poisson、Elo 併列）。
對 repo 預期效果：提供與進球數正交嘅強度信號，針對「大勝/險勝」差異更敏感；作為 ML 層特徵（見第 4 項）極高價值；shrinkage target 更合理。
實施難度：🟢 低（pi-rating 更新公式簡單：π_new = π_old + k·(result_diff - expected_diff)，約 20 行；Elo 更簡單）。
優先級：🟠 P1（高，零成本特徵增強，為 ML 層鋪路）。

🥈 4. 加入 rolling xG features（隊級 xG for/against 加權移動平均）
咩優化：repo 已有 SofaScore shotmap xG（10 年 backfill），但未入模型。建議：計算每隊近 N 場（如 5/10/20 場）加權移動平均 xG_for、xG_against、xG_diff，作為 team_strength 補充或 ML 特徵。
網上證據：
• Sage Journals (2026-02) "Can simple models predict football — and beat the odds?"：用近期 xG 經 Skellam 分布估計 1X2，再配 isotonic calibration，證實 xG 比進球數更早反映底層表現。
• MDPI (2026, 14/9/195) Gevorgyan：calibrated probabilistic forecasting 明確用 xG + dynamic ratings 輸入 XGBoost，XGBoost 被選為最佳 boosting。
• smartmatchpick.com (2026) "XGBoost Football Prediction Today"：Brier score <0.210、log loss <0.930 係 2026 競爭門檻；xG-based features 是關鍵。
• arXiv 2403.07669 (Ch.1)：系統性回顧指 xG features 在 gradient boosting 入面 consistently 提升 RPS。
• researchgate 396727382 (2025-10) "Success Score: Deep Learning Framework"：xG 特徵經非線性變換放大小值、壓縮大值，提升模型敏感度。
對 repo 預期效果：現有 xG 數據即時可用，無需外部 API；xG 比進球數少受隨機波動影響（signal-to-noise 更高），特別適合早季同小樣本；預期 RPS 改善 0.01–0.02、CLV 更穩。
實施難度：🟡 中（需寫 rolling window 計算、處理缺失值、決定半衰期/窗口大小，約 100–150 行）。
優先級：🟠 P1（高，數據已有卻未用，ROI 極高）。

🥈 5. 機率校準（Platt Scaling / Isotonic Regression）針對 CLV/EV
咩優化：模型輸出原始概率 → de-vig → edge → Kelly。中間缺校準環節。建議：在 walk-forward validation 期間，用 per-(league, market) Platt scaling（sigmoid）或 isotonic regression（非參數），配合時間衰減權重（近期樣本權重高），再設硬概率上限（如 0.80）防極端邊界。
網上證據：
• Reddit r/algobetting (2026-05) "Calibration findings from a 6-month sports prediction model"：實戰分享 — per-(sport, verdict) Platt scaling + time-decayed weights，硬 cap 0.80，顯著改善 Brier score 同 log loss，EV 計算更可信。
• betliz.com (2026) "How to Improve Smart EPL Predictions"：明確建議 isotonic/Platt + log loss/Brier/calibration plots + out-of-sample backtest。
• Gevorgyan (2026, MDPI/AUA) "Calibrated probabilistic forecasting of football match outcomes using xG and dynamic team ratings"：直接用 XGBoost + isotonic calibration，針對足球 1X2/O/U。
• arXiv 2410.21484 (Systematic Review of ML in Sports Betting)：校準係從模型概率到可投注 EV 必經步驟，未校準概率會高估 edge。
對 repo 預期效果：edge 計算更準 → Kelly 注碼更合理 → 避免過度下注高邊界概率（如 0.9+）→ CLV 更貼真、long-run bankroll 增長更穩；Brier score / log loss 可量化改善。
實施難度：🟡 中（sklearn.calibration.CalibratedClassifierCV 或自行寫 Platt/isotonic，需在 walk-forward 循環內 fit，約 80–120 行）。
優先級：🟠 P1（高，直接影響錢包層面，風險極低）。

🥈 6. Odds Blending / Market Prior：將 closing odds 作 prior 混入模型
咩優化：模型概率 p_model 與 de-vigged closing odds 概率 p_market 做加權融合：p_blend = w·p_model + (1-w)·p_market，w 可定或按 league/樣本量動態調整（如 w = n_model / (n_model + n_market_effective)）。或更進階：用 market odds 作 ML 特徵（見 MDPI 2026 做法）。
網上證據：
• IEEE Access (2026-07) "Football Match Outcome Prediction Using Machine Learning"：結論 — "bookmaker-implied probabilities dominate the predictive signal"，有 market-informed features 時 ML 模型表現顯著提升。
• MDPI (2026) "Predicting Football Match Outcomes Using Machine Learning"：用 power method (Newton-Raphson) 去 vig 得 margin-free market probs，作為輸入特徵 + baseline。
• arXiv 2604.27865 (KellyBench, 2026-04)：benchmark 專門比較 model log loss vs market log loss，量化模型相對市場嘅增值。
• GitHub aarensberg/Beat-the-Bookmakers-using-Machine-Learning：完整 pipeline 包括 "neural-network-based refinement of probabilistic predictions" 即用市場信息 refine 模型。
• arXiv 2403.07669：Constantinou Dolores (2019) 就已經用 hybrid 方式整合市場信息。
對 repo 預期效果：市場已吸納所有公開信息（傷兵、天氣、更衣室風聲），模型只需捕捉市場漏掉嘅細微 edge；blending 能即時提升校準度、降低 log loss、改善 CLV；甚至可作為「無模型 baseline」對照。
實施難度：🟡 中（需可靠 closing odds 來源 + de-vig pipeline 已有，blending 邏輯約 50 行；動態 w 需驗證）。
優先級：🟠 P1（高，理論最強、實證最穩，直接針對「跑贏市場」目標）。

🥉 7. 升級至 Bivariate Poisson (Karlis & Ntzoufras 2003) 替代獨立 Poisson
咩優化：用 bivariate Poisson 取代獨立雙 Poisson，引入共同進球潛變量 λ₃（或對角線膨脹 diagonal inflation），直接建模 home/away 進球相關性，改善 draw 概率校準。
網上證據：
• Karlis & Ntzoufras (2003) RSS Series C 52(3)：bivariate Poisson with diagonal inflation 明顯改善 draw scores calibration；即使微小相關性都有幫助。
• Tinbergen Institute (2015) "A Dynamic Bivariate Poisson Model for Analysing and Forecasting Football Matches" (Koopman & Lit)：動態版本進一步引入時間變化參數，預測力更強。
• ScienceDirect (2017) "A bivariate Weibull count model"：確認 KN2003 diagonal inflation 校準 draws 比獨立 Poisson 好。
• penaltyblog PyPI：現成 KarlisNtzoufras 類，API 與 DixonColes 一致，即插即用。
對 repo 預期效果：draw 概率更準 → 1X2 RPS 改善；對 AH/O/U 定價間接受益（進球相關性影響總進球分布）；但對比 DC tau，改善主要集中於 draw 而非 low-score 全域。
實施難度：🟡 中（penaltyblog 現成，但需 fit 額外參數 λ₃，MLE 收斂較慢，驗證複雜度升）。
優先級：🟡 P2（中，DC tau 已解決 80% low-score 問題，bivariate Poisson 是進階優化，ROI 遞減）。

🥉 8. ML 層實證：XGBoost/LightGBM + 統計模型 Ensemble/Stacking
咩優化：在統計模型（DC + pi-rating + xG features）基礎上，訓練 XGBoost/LightGBM 分類器（1X2）或回歸器（進球數），做 stacking：meta-learner 學習何時信統計、何時信 ML。保留 statistical baseline 做 fallback。
網上證據：
• arXiv 2403.07669 (Ch.1 ML for Soccer Match Result Prediction)：全面 benchmark 指出 gradient boosting (XGBoost/LightGBM/CatBoost) 在 rating + xG features 上 consistently 達到最低 RPS。
• arXiv 2305.17094 "Benchmarking state-of-the-art gradient boosting algorithms"：LightGBM 在足球預測上 "performs the best by a significant margin"。
• arXiv 2309.14807 / Springer 2024 (s10994-024-06608-w)：2023 Soccer Prediction Challenge 環境下，bookmaker odds RPS 0.2020 / acc 0.5194，略優於 DL models；Razali et al. 2022 用 gradient-boosted trees 在 Open International Soccer Database 取得最佳 RPS。
• Gevorgyan 2026 (MDPI/AUA)：XGBoost + xG + dynamic ratings + isotonic calibration，完整可複製 pipeline。
• arXiv 2410.21484 (Systematic Review)：gradient boosted trees 係 soccer betting 入面最穩健 ML 方法；deep learning (LSTM/Transformer) 無顯著優勢。
• Constantinou Dolores (ML 108, 2019)：Hybrid Bayesian Network 本身就是 statistical + ML ensemble 思想。
對 repo 預期效果：若特徵工程做好（pi-rating + xG + DC params + market prior），ML 層可捕捉非線性交互（如強隊主場大勝模式），預期 RPS 再降 0.005–0.01；但需嚴格 walk-forward 防 overfitting。
實施難度：🔴 高（需完整 ML pipeline：特徵工程、時序 split、hyperparameter tuning、calibration、model versioning、監控；約 500+ 行 + 持續維護）。
優先級：🟡 P2（中，上限高但工程成本大，建議先做完 1–6 打穩基石再上）。

🥉 9. Deep Learning (LSTM/Transformer) — 現階段不建議投入
咩優化：評估 LSTM/Transformer/TabNet 等 DL 架構是否能打破統計+GBM 天花板。
網上證據：
• Springer Machine Learning (2024, s10994-024-06608-w) "Evaluating soccer match prediction models: a deep learning approach..."：2023 Soccer Prediction Challenge 環境，bookmaker odds (RPS 0.2020, acc 0.5194) 略優於 DL models；DL 無顯著優勢。
• arXiv 2309.14807 / ar5iv 同文：同樣結論 — bookmaker odds slightly better than DL；缺乏公開 benchmark dataset 限制 DL 發揮。
• arXiv 2410.21484 (Systematic Review 2024-10)：gradient boosted trees 為 lowest RPS 方法；DL 未展示明顯優勢。
• arXiv 2607.24573 / 2608.03416 (2026-07/08)：LLM-SoccerArena、AI World Cup 2026 等新 benchmark 剛登場，GPT-4 等 LLM 在足球預測上 "competitive accuracy without extensive feature engineering" 但未超越 SOTA GBM。
• 多篇 2022-2025 文獻：TabNet、Transformer、LSTM 在小樣本足球數據上易 overfit，interpretability 差，不利 betting 風控。
對 repo 預期效果：現階段投入 ROI 極低；repo 數據量（~10 年 x ~20 聯賽 ≈ 30k 場）對 DL 仍屬小樣本；維護成本高、不可解釋、難以融入風控。
實施難度：🔴 高（架構複雜、調參難、需 GPU、難以 walk-forward 監控）。
優先級：🔵 P3（低，觀望即可，待 benchmark 成熟再評估）。

═══════════════════════════════
🗺 建議路線圖（第一步做咩）
═══════════════════════════════

📋 Phase 0（先決，半日）：工程收尾 — 修 CI (pytest -m "not integration")、修 test_paper_repro_7d、清理 v3 死引用、合併雙 pipeline Poisson 實現、統一 KELLY_FRACTION=0.5 / MAX_STAKE=3%。👉 Forge 已列為頭 1/3/5，做完先有綠燈跑實驗。

📋 Phase 1（1–2 日）：統計模型核心 — 加 Dixon-Coles tau (penaltyblog 或自寫) + 指數時間衰減 (ξ=0.0065 或 tune half-life) + pi-rating/Elo 特徵。呢三樣零外部依賴、風險極低、即時見效。預期：O/U AH 定價明顯改善、RPS 降 0.01+。

📋 Phase 2（2–3 日）：數據特徵增強 — 接入 rolling xG features（xG_for/against/diff 加權移動平均）+ market prior blending（de-vigged closing odds 加權融合，w 先定死 0.5 再優化）。預期：CLV 更穩、edge 更準、Brier/log loss 下降。

📋 Phase 3（1–2 日）：機率校準 — walk-forward 循環內加 per-(league, market) Platt/isotonic calibration + time-decay weights + cap 0.80。預期：EV 計算可信度大增、注碼更合理。

📋 Phase 4（1 周+）：進階統計 — Bivariate Poisson (KN2003) 做 A/B test 對比 DC tau，量化 draw 改善幅度；若顯著再保留。

📋 Phase 5（長期，視 Phase 1-4 結果）：ML 層 — 特徵集成 (DC params + pi-rating + xG + market prior) → XGBoost/LightGBM → stacking meta-learner → 嚴格 walk-forward + 校準 + 監控。先跑 offline backtest，再併入 paper trading 驗證 CLV。

📋 Phase 6（持續觀望）：Deep Learning / LLM — 跟進 LLM-SoccerArena、Soccer Prediction Challenge 等 benchmark 進展；有明確 SOTA 突破再評估投入。

═══════════════════════════════
📌 關鍵提醒
═══════════════════════════════

⚠️ 所有優化必須在 walk-forward / paper trading 框架內驗證（repo 已有 validate_paper_season.py），唔好單睇 in-sample 指標。
⚠️ CLV 係唯一 KPI（Forge 驗證已確認 repo 做緊），任何優化最終要睇 avg_clv_pct 在幾百至幾千注樣本下係咪持續正數。
⚠️ 香港法律紅線：保持「研究系統」定位，無執行層，輸出止於建議報告 + bet_log 追蹤。
⚠️ 風控數值必須先收緊（Kelly 0.5、單注 3%），再講模型優化 — 否則模型改得再好，一注 5% Kelly 0.75 都能洗走 bankroll。

═══════════════════════════════
📚 主要來源索引
═══════════════════════════════

1. Dixon & Coles (1997) — 原始 paper（tau, rho, MLE, time decay）
2. predictionengine.app (2026) — DC 公式、MLE、backtest、python 實現指南
3. dashee87.github.io — DC + time weighting 完整 Python 實現
4. penaltyblog (PyPI) — DixonColes、KarlisNtzoufras、TimeDecay 現成類
5. dev.to/commodus67 (39dc) — 實戰 ξ=0.0018、3 季 fit
6. Karlis & Ntzoufras (2003) RSS — Bivariate Poisson diagonal inflation
7. Koopman & Lit (2015) Tinbergen — Dynamic Bivariate Poisson
8. arXiv 2608.11505 (2026-08) — exp(−ξ·t) 加權 + Elo 基準
9. arXiv 2404.08136 — EWMM 理論框架 half-life
10. Constantinou & Fenton (2012) — pi-rating 系統
11. Constantinou (2019) Dolores (ML 108, 49–75) — Hybrid Bayesian Network
12. JSA 2022 (Sage) — pi-rating 用於 AH 定價
13. arXiv 2403.07669 — ML for Soccer 綜述，引用 Dolores、GBM benchmark
14. arXiv 2305.17094 — GBM benchmark：LightGBM 最優
15. arXiv 2309.14807 / Springer 2024 — 2023 Soccer Prediction Challenge：bookmaker RPS 0.2020
16. Gevorgyan 2026 (MDPI/AUA) — xG + dynamic ratings + XGBoost + isotonic calibration
16b. smartmatchpick.com (2026) — Brier <0.210, log loss <0.930 門檻
17. Sage 2026-02 — xG + Skellam + isotonic calibration
18. Reddit r/algobetting (2026-05) — 6-month 校準實戰（Platt + decay + cap 0.80）
19. betliz.com (2026) — isotonic/Platt + Brier/log loss 實戰指南
20. IEEE Access (2026-07) — bookmaker probs dominate predictive signal
21. MDPI (2026, 14/9/195) — market odds 入特徵、power method de-vig
22. arXiv 2604.27865 (KellyBench) — model vs market log loss benchmark
23. GitHub aarensberg/Beat-the-Bookmakers — NN refine pipeline
24. arXiv 2607.24573 (LLM-SoccerArena) / 2608.03416 (AI World Cup 2026) — LLM benchmark
25. Forge 審查報告 20261026-051100-coding-aifootballbets-compare.md — repo 現狀基準

———
📌 本報告為資訊整合，唔構成投注、投資或工程承諾。所有優化建議需經 repo 自身 walk-forward 驗證先落地。