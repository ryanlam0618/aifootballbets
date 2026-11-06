🧮 ENSEMBLE 權重理論盤點 — 俾 Kris 嘅動工前理論武裝
任務：20261027-002900-seo-ensemble-weighting-theory
日期：2026-10-27 ｜ 整理：Scout（SEO agent）
場景：aifootballbets 異源模型集成（DC-Poisson／pi-rating／xG-feature + 市場概率），walk-forward 樣本幾百至千場
格式：純文字 + emoji 分組，無 markdown 表格
⚠️ 備註：本次研究期間搜尋供應商一度故障，部分次要理論（GR1984 細節、Hedge 算法）未能取得額外網上錨點，已引用權威 review（arXiv 2205.04216）同穩定經典文獻（paper 年份+venue）作底，並如實標註。

═══════════════════════════════
⚡ TL;DR 五句核心結論
═══════════════════════════════

1️⃣ 以你場景（3-5 個模型、幾百至千場樣本），開局用「等權 linear opinion pool」— 呢個唔係偷懶，係 20 年實證撐住嘅理論結果：Stock & Watson (2004) forecast combination puzzle — 等權平均實證上極難被打敗，因為估「最優權重」本身引入估計誤差。
2️⃣ 權重升級唯一安全路線：等權 → inverse-MSE（大窗＋向等權收縮）→ 受約束 regression（非負+加總1）→ 樣本過千場先考慮 stacking meta-learner。每一級都要喺 walk-forward 內跑贏等權 baseline 先有資格上。
3️⃣ 概率池化用 linear pool 起步；但有個關鍵陷阱（Ranjan & Gneiting 2010）：calibrated 模型嘅 linear pool 必定唔再 calibrated（過度彌散）— 所以 pool 完一定要 re-calibrate。
4️⃣ 多樣性係免費午餐嘅上限：Krogh & Vedelsby (1995) — ensemble 誤差 = 成員平均誤差 − 分歧度。你嘅三個統計模型同食同一歷史數據，誤差相關會高；「市場概率」成員相關性最低、增益最大 — 你計劃將市場做第四員係理論上最值錢嘅一步。
5️⃣ BMA／online 算法理論靚，但喺模型必然 misspecified + 幾百場樣本下通常退化成 model selection 或估計噪聲 — 全部留做 P3，唔好一開始掂。

═══════════════════════════════
📚 A. 經典 forecast combination 理論
═══════════════════════════════

① Bates & Granger (1969) — 開山之作【Operations Research 17(3)】
• 數學定義：兩個預測器，權重由誤差 MSE 協方差矩陣求：w₁ = (σ₂² − σ₁₂) / (σ₁² + σ₂² − 2σ₁₂)；簡化版（忽略相關）即 inverse variance：wᵢ ∝ 1/σᵢ²。
• 優劣：封閉解、無需 regression、受組合分散理論（portfolio diversification）啟發；CRAN ForecastComb::comb_BG 有現成實現。
• 陷阱：忽略誤差相關性 — 兩模型誤差高度相關時（你嘅情況！三個統計模型同食歷史數據）σ₁₂ 大，inverse variance 權重會失真；MSE 本身要用歷史窗口估，樣本細時方差大。
• 適用場景：2-3 個誤差相關性低嘅模型；權重唔需要經常更新。

② Granger-Ramanathan (1984) — regression 權重【Int. J. Forecasting 前身；轉載 JBF】
• 數學定義：用 OLS 回歸實際值 y = α + β₁f₁ + β₂f₂ + … + βₖfₖ，回歸係數 (β) 就係權重；截距 α 順手修正 bias。
• 優劣：直接最小化 MSFE、自動處理誤差相關與偏倚；50-year review（arXiv 2205.04216，Wang/Hyndman 等）確認佢係「regression-based 派」代表。
• 陷阱：權重可以係負數（數學上有意義、實務上放大方差兼難解釋）；無約束 OLS 喺小樣本+多重共線（成員輸出高度相關）時係災難 — 你 3 個統計模型輸出會好接近，共線性爆錶。
• 適用場景：樣本大（>1,000）、成員少而相關性中低。

③ Constrained Least Squares（CLS）
• 數學定義：同一條 GR 回歸，加約束 βᵢ ≥ 0 及 Σβᵢ = 1（二次規劃解）。
• 優劣：權重變成「可信嘅混合比例」、杜絕負權爆炸；係 Granger-Ramanathan 原文有提嘅變體， Timmermann (2006) 綜述列為標準做法。
• 陷阱：約束唔消除估計方差 — 幾百場之下 CLS 權重仍然跳；需要 shrinkage（見 C10）。
• 適用場景：3-8 個模型、想要「可解釋權重」時 — 係你升級路線嘅第一個真權重目標。

④ ⭐ Forecast Combination Puzzle（Stock & Watson 2004）【J. Forecasting 23, 405-430】— 今次最重要理論
• 數學定義（其實係實證結論）：7 國 GDP 多模型組合比賽入面，表現最好嘅係 simple mean（等權）同 trimmed mean；連最佳嘅 time-varying parameter 組合，權重都幾乎等於 1/n。
• 點解：估計誤差 — 「最優權重」要估 covariance，而權重嘅估計誤差造成嘅損失，好過估準權重嘅收益（Elliott「On Why Averaging beats Optimal Linear Combination」；Smith & Wallis 2009, Oxford Bulletin — 正式命名 puzzle）。模型多、樣本相對細時最嚴重 — 100% 係你場景。
• 實戰啟示：任何 fancy 權重方案嘅入場券 = 喺 walk-forward 上跑贏等權。跑唔贏就返去等權。呢條規則寫入 repo 做硬性 A/B。
• （後續 2023-25 文獻仍在求解：UCR Lee & Kang 2025 working paper、arXiv 2308.05263 — 證明呢個係活躍理論領域，唔係老黃曆。）

═══════════════════════════════
🎲 B. 概率池化（probability pooling）
═══════════════════════════════

⑤ Linear opinion pool（算術平均）
• 數學定義：P(y|x) = Σᵢ wᵢ · pᵢ(y|x)，直接加權平均概率。
• 優劣：簡單、穩健、唔會爆 0；保留「唔肯定」嘅態度（外圍保守）。
• 陷阱（重要！）：Ranjan & Gneiting (2010, UW TR543；正式版 Statistica Sinica) 證明「一個 striking result」— 任何由各自 calibrated 模型組成嘅加權 linear pool，必然 uncalibrated 且缺乏 sharpness（過度彌散）。即係：pool 完嘅概率系統性「太温和」→ 直接攞去計 edge 會低估極端事件 → 要 re-calibrate（isotonic/temperature）先可用。
• 適用：3-5 個模型嘅起步 baseline — 你的 P0。

⑥ Logarithmic opinion pool（幾何平均／log-odds 相加）
• 數學定義：P(y|x) ∝ Πᵢ pᵢ(y|x)^wᵢ，即 log 空間加權相加後歸一。
• 優劣：懲罰極端分歧、保留 sharpness、不確定性會「投票淘汰」少數派。
• 陷阱：zero problem — 一個成員出 p(y)≈0 即令整個 pool 歸零（足球 Poisson 模型對極端比分成日出接近 0 嘅概率！）；且 log pool 系統性過度自信。arXiv 2202.11219 例子：calibrated 模型 (50%,50%) 配另一個 (0.1%,99.9%)，log pool 出 (3%,97%) 而 linear pool 出 (25%,75%) — 差別驚人。
• 適用：成員個個有底（概率 floor，例如 clip 到 1e-6）而且你想放大分歧信號時；對照用。

⑦ 兩者實證比較 + 何時用邊個
• Judgment & Decision Making (2023) 人類判斷聚合實證：「先校準、後 log-odds 平均」（HCTALO）優於未校準 linear pool 同 probit 平均 — 呢個「calibrate-then-combine」流程值得抄。
• 你的場景建議：linear pool 等權起步 + 事後 isotonic 校準（P0）；log-odds pool 做對照組（P1）；任何情況下成員概率都要 clip（如 0.001–0.999）。

═══════════════════════════════
⚖️ C. Performance-based weighting
═══════════════════════════════

⑧ Inverse error / inverse MSE weighting
• 數學定義：wᵢ ∝ 1/MSEᵢ，MSE 用 rolling window（近 N 場）估計後歸一。
• 優劣：一行代碼、自適應、直覺。
• 陷阱：MSE 估計噪聲大（200 場窗口嘅 MSE 仍然唔穩）；市場概率成員經常明顯好過統計模型 → 權重會狂壓統計模型，變相 model selection；建議配 shrinkage（見下）。
• 適用：P1 升級首選，一定同等權 A/B。

⑨ Softmax-of-score weighting
• 數學定義：wᵢ = exp(sᵢ/T) / Σⱼ exp(sⱼ/T)，sᵢ 係窗口 score（如 −log loss），T 係溫度。
• 優劣：T→∞ 退化做等權、T→0 退化做 argmax — 一條參數連起兩個極端，方便 sensitivity analysis。
• 陷阱：T 同 score scale 敏感；score 噪聲大時 softmax 會放大噪聲；T 本身要 walk-forward tune，又多一層過擬合面。
• 適用：P2；當你已有穩定 scoring 流程先玩。

⑩ Rolling window re-weighting + shrinkage
• 數學定義：每輪 re-fit 權重 ŵ，然後收縮：w = λ·ŵ + (1−λ)·(1/n)，λ∈[0,1]。
• 優劣：直接回應「模型狀態漂移」（球隊換帥、賽季轉折）；shrinkage 令你喺「估得準嘅自信」同「等權嘅穩陣」之間連續調節。
• 陷阱：window 細 + λ 大 = puzzle 重演；λ 要 walk-forward 揀；唔好 window 短過 ~100 場。
• 適用：P1-P2 主力；呢個「收縮等權」設計係對付 puzzle 最務實嘅工程答案。

═══════════════════════════════
📐 D. Bayesian Model Averaging（BMA）
═══════════════════════════════

⑪ 後驗概率加權
• 數學定義：P(y|x,D) = Σᵢ P(y|x,Mᵢ) · P(Mᵢ|D)，其中 P(Mᵢ|D) ∝ P(D|Mᵢ)·P(Mᵢ)；實務用 BIC 近似 log 後驗（Raftery 1995；R ensembleBMA/BMA 包）。
• 理論地位：M-closed（真模型喺候選入面）假設下 Bayes 最優；分類場景有 Haussler et al. (1994) 上界 — 誤差 ≤ 2× Bayes optimal classifier。
• 陷阱（致命）：M-open 現實 — 足球模型全部 misspecified，P(D|Mᵢ) 個個趨近 0，後驗由「誰最唔差」主導 → BMA 實際退化成「選單一模型」（Ensemble learning 綜述原文：BMA「tends to converge toward giving all weight to a single model」）；BMC（權重抽自 Dirichlet）係修正，但計算貴。
• 你的場景實用性：低-中（P3）。幾百場樣本下後驗極度集中，等於放棄 ensemble 嘅初衷。想要 Bayesian 味道，CLS+shrinkage 已經係佢嘅實用化身。

═══════════════════════════════
🏗 E. Stacking / Super Learner
═══════════════════════════════

⑫ Wolpert (1992) stacked generalization【Neural Networks 5(2), 241-259；Breiman 1996 註入回歸版】
• 數學定義：level-0 各模型嘅輸出做 meta-features，訓練 level-1 meta-learner g() → P = g(p₁,…,pₖ)；g 可以係線性（=CLS）或更複雜。
• Super Learner（van der Laan et al. 2007）：凸組合權重 + 交叉驗證揀權重，有漸近最優保證（不差過任何成員）。
• 防洩漏要點（成敗關鍵）：meta-features 必須用 out-of-fold 預測 — 即每場嘅成員概率要由「冇見過嗰場」嘅版本生成。時間序列用 walk-forward/rolling origin，唔可以用隨機 K-fold（會用未來數據訓練 → meta-learner 假強）。
• 陷阱：meta-learner 過擬合 — 3-4 個模型、幾百場樣本，meta 只可以係 4-6 參數嘅 constrained linear；拿 XGBoost 做 meta-learner = 自殺。
• 體育應用例：Constantinou Dolores (2019, Machine Learning 108) 係「rating+多源特徵 + hybrid BN」嘅 stacking 思想；這條線證明 sports stacking 可行，但都係喺大樣本下。
• 適用：P2+；樣本 >1,000 場先有足夠 meta 訓練數據。

═══════════════════════════════
🔄 F. Online／adaptive weighting
═══════════════════════════════

⑬ Multiplicative Weights / Hedge【Freund & Schapire 1997；Cesa-Bianchi & Lugosi 2006《Prediction, Learning, and Games》】
• 數學定義：wᵢ,ₜ₊₁ ∝ wᵢ,ₜ · exp(−η·ℓᵢ,ₜ)（按每輪損失乘法更新），最終混合預測 Pₜ = Σwᵢ,ₜpᵢ,ₜ；regret 保證 O(√(T·ln n)) — 平均而言唔會差過最佳專家太多。
• 優劣：無分佈假設、有理論保證、天然線上更新。
• 陷阱：η 要 tune（理論值依賴未知損失範圍）；T=幾百場時保證鬆到冇實際約束力；對概率預測要用 clipped log-loss 版本（避免極端損失炸開權重）。
• 適用：成員數多（>10）或者環境劇烈漂移；你的 4-5 成員場景用佢係殺雞牛刀（P3）。

⑭ Confidence-based / gating weighting
• 數學定義：權重唔係固定 — wᵢ(x) 按單場置信度生成，例如 gating model g(x) 輸出邊個成員「今日」啱用（mixture of experts 思想）。
• 優劣：理論上能捕捉「某類場景信某模型」（如盃賽信 rating、大聯賽信 xG）。
• 陷阱：gating 本身又要訓 → 過擬合面再翻倍；幾百場下子場景樣本極薄；是「參數預算」大敵。
• 適用：P3，同 stacking meta-learner 進化版掛鈎。

═══════════════════════════════
⚽ G. 足球／體育實證 + 多樣性理論
═══════════════════════════════

⑮ football ensemble weighting 實證現況 — 誠實聲明
• 專門比較「邊種權重喺足球預測贏」嘅 peer-reviewed paper 好罕有 — 搜尋期內未能找到直接對比研究（本身係一個發現：呢個理論喺體育場景屬實證空白，你做起來冇直接答案抄，要自己 walk-forward 驗）。
• 間接證據鏈：① arXiv 2410.21484 系統綜述 — 體育預測最高 RPS 表現多為 GBT/集成；② Constantinou 2019 Dolores — hybrid（rating+多源）路線嘅學術代表作；③ Springer ML 2024（2023 Soccer Prediction Challenge 回顧）— 頂級方案普遍係「多信號+校準」，冇人靠花巧權重贏；④ IEEE 2026 — bookmaker implied probabilities dominate → 市場概率做集成成員係最有證據嘅一員。
• 競賽/業界慣例：多模型 + 簡單池化 + 校準，權重複雜度永遠排最後。

⑯ 多樣性理論：ensemble 增益嘅數學上限
• Krogh & Vedelsby (1995) ambiguity decomposition：E_ensemble = Ē_member − Āmbiguity（平方損失下逐點成立；MetricGate 2026 解讀：ensemble 誤差 = 成員平均誤差 − 分歧度）。
• Ueda & Nakano (1996) bias-variance-covariance 分解：E = bias² + (1/n)·variance + (1−1/n)·covariance — 成員誤差相關性（covariance）越大，ensemble 抵消得越少。
• 直接推論（對你嘅組成）：DC-Poisson、pi-rating、xG 模型三個都食同一批歷史賽果 → 誤差相關高 → 佢哋之間嘅池化增益有限；「de-vigged 市場概率」成員同統計模型誤差相關最低 → 理論增益最大。你將市場做第四員，唔單止係加一個好模型，係拉開分歧度 — 理論上最值錢嘅一步。
• 反面教訓：與其加第 4、5 個統計模型（誤差相關只會更高），唔如：同市場成員比過、確保各成員誤差唔同質（唔同損失函數/唔同數據切片訓練）。

═══════════════════════════════
🧭 實戰推薦組合（Kris 場景：4-5 員、幾百至千場、防 overfit）
═══════════════════════════════

🎯 P0 — 起步（即刻可以做）
1. 成員：DC-Poisson、pi-rating、xG-feature 模型 + de-vigged 市場概率（等權 1/4）
2. 池化：linear opinion pool；成員概率 clip 到 [0.001, 0.999]
3. Pool 完 re-calibrate（isotonic，喺 walk-forward loop 內 fit — 校準數據同評估數據完全分開）
4. 三個硬性 benchmark：等權 ensemble vs 最佳單模型 vs market-only（去水位 closing odds）— 用 RPS/log loss/Brier 三箭齊發
5. 只出 CLV 證明正嘅注（沿用 repo 現有 edge 流程）

📈 P1 — 權重升級（跑贏 P0 先上）
6. Inverse-MSE 權重：窗口 ≥200 場 + shrinkage w = 0.5·ŵ + 0.5·(1/n)
7. CLS 權重（β≥0、Σβ=1）：walk-forward 內重估
8. Log-odds pool（clip 後）做對照組
9. 每一級嘅裁決標準：walk-forward 上跑贏等權，唔係 in-sample 好睇

🚀 P2 — 樣本 >1,000 場先考慮
10. Stacking：constrained linear meta-learner（≤6 參數），meta-features 全部用 out-of-fold（rolling origin）預測
11. Rolling re-weighting + λ 收縮網格 walk-forward 揀
12. Softmax 溫度掃描（T 大幅偏向等權做先驗）

🚫 P3 — 理論靚但你場景唔值得
13. BMA（misspecified 退化問題）｜ BMC（計算貴）｜ Hedge/MW（保證鬆）｜ gating/confidence weighting（參數預算爆）｜ deep meta-learner（過擬合）

🛡 防洩漏檢查清單（每級通用）
• 權重/校準/meta 估計用嘅數據，同評估數據時間上完全分離
• 市場成員只能用「落注當刻攞得到」嘅賠率版本（唔可以事後 closing）
• 所有超參數（窗口/λ/T）一律 walk-forward 揀，唔可以全樣本揀
• 每次改動都保留「等權 baseline」對照 — puzzle 係你嘅永恆監考官

💎 一句總結：你的集成旅程應該係「等權起步、market 做第四員拉開分歧、pool 完校準、權重升級用 shrinkage 細步走」— 理論已經替你排好咗優先次數，剩下嘅係 walk-forward 紀律。

═══════════════════════════════
📚 主要來源
═══════════════════════════════

經典理論：
1. Bates & Granger (1969) The Combination of Forecasts, Operations Research 17(3) ｜ CRAN ForecastComb::comb_BG 文檔（公式描述）
2. Granger & Ramanathan (1984) — 見 50-year review 覆蓋（arXiv 2205.04216, Wang, Hyndman et al.）
3. Timmermann (2006) Forecast Combinations 綜述（Handbook）— CLS/權重方法分類
4. ⭐ Stock & Watson (2004) Combination Forecasts of Output Growth in a Seven-Country Data Set, J. Forecasting 23, 405-430 — 原文 PDF（princeton.edu/~mwatson）
5. Smith & Wallis (2009) A Simple Explanation of the Forecast Combination Puzzle, Oxford Bulletin 71(3)
6. Elliott et al. — On Why Averaging beats Optimal Linear Combination（econweb.ucsd.edu）
7. Lee & Kang (2025) Solving the Forecast Combination Puzzle（UCR working paper）｜ arXiv 2308.05263

概率池化：
8. Ranjan & Gneiting (2010) Combining Probability Forecasts（UW TR543；linear pool of calibrated forecasts 必然 uncalibrated）
9. arXiv 2202.11219 — log pool 極端例子（(3%,97%) vs (25%,75%)）
10. Judgment & Decision Making (2023) — HCTALO calibrate-then-average-log-odds 實證

BMA／Stacking／Online：
11. Hoeting et al. (1999) BMA 綜述 ｜ Raftery (1995) BIC 近似 ｜ Wikipedia Ensemble learning（BMA/BMC/gating 節，Haussler 1994 上界、BMC Dirichlet 修正）
12. Wolpert (1992) Stacked Generalization, Neural Networks 5(2) ｜ Breiman (1996) Stacked Regressions ｜ van der Laan et al. (2007) Super Learner
13. Freund & Schapire (1997) Hedge/AdaBoost ｜ Cesa-Bianchi & Lugosi (2006) Prediction, Learning, and Games

足球/多樣性：
14. arXiv 2410.21484 — ML in sports betting 系統綜述 ｜ Springer ML 2024 (s10994-024-06608-w) — 2023 Soccer Prediction Challenge
15. Constantinou (2019) Dolores, Machine Learning 108, 49-75
16. Krogh & Vedelsby (1995) — ambiguity decomposition ｜ Ueda & Nakano (1996) — bias-variance-covariance ｜ MetricGate 2026 解讀
17. IEEE Access 2026 — bookmaker implied probabilities dominate predictive signal（上份 artifact 已驗證）
18. 上游 artifact：20261026-131400-seo-model-optimization.md（成員模型清單底）

———
📌 備註：⑫⑬ 部分（Wolpert/Hedge 具體頁碼）因搜尋供應商故障未能額外抓取網上錨點，引用基於穩定經典文獻元數據 + Ensemble learning 權威條目；report 內所有「對你場景」嘅推論均屬證據加權建議，最終以 repo walk-forward 實測為準。本報告唔構成投注意見。