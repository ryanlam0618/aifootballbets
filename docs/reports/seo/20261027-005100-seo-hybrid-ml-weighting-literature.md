📚 HYBRID 實證文獻盤點 — 「統計模型做 ML 底 + testing 權重」會唔會提升準確率？
任務：20261027-005100-seo-hybrid-ml-weighting-literature
日期：2026-10-27 ｜ 整理：Scout（SEO agent）
回答對象：Kris 構想 — 以唔同數學模型做 ML 底／特徵，再按 testing 結果加權，會唔會提升準確率？
角度：唔重複上兩份（優化清單／權重理論），今次 100% 實證文獻 + 數字 + 可信度評級
格式：純文字 + emoji 分組，無 markdown 表格

═══════════════════════════════
⚡ TL;DR — 直接答「會唔會提升」（分條件）
═══════════════════════════════

✅ 解讀 A（統計模型輸出做 ML 特徵）— 會提升，證據最硬：
2017 Soccer Prediction Challenge 之後嘅文獻鏈一致顯示「rating／模型輸出做特徵 + gradient boosting」係最強公開配方。旗艦數字：CatBoost + pi-ratings 達 RPS 0.1925（Razali 2022），好過純 Elo ordered logit（0.2035）、好過 2017 Challenge 冠軍 XGBoost（0.2063）、甚至好過 bookmaker 水平（0.2020）。但幅度細：RPS 只降 ~0.01–0.02，係「細步升級」唔係質變。

🟡 解讀 B（統計模型做 base learner，ML 做 meta-learner）— 足球專門證據薄，跨運動間接支持「細幅提升」：
NHL meta-classifier majority voting 60.25% > 個別分類器；KBO 統計+NLP 逐級加特徵 0.6508→0.7222→0.7430；Stübinger (2019) ML 集成 47,856 場回報 +1.58%/場 跑贏個別模型。共同點：增益存在但細，且 meta 層越複雜越易爆。

🟡 解讀 C（多模型按 testing 指標加權組合）— 大樣本文獻支持、小樣本存疑：
組合預測 50 年實證：組合平均好過單一模型（Makridakis 1982、Clemen 1989、M4 競賽），但「unanimous conclusion：simple combination schemes are hard to beat」（等權難敗，50-year review 原文）。按 testing 加權要喺大樣本先企得住；非負約束 regression 係 regression 類入面最穩（Aksu & Gunter 1992：「至少同等權一樣穩」）。

❌ 幾時唔會提升（反面證據）：
① 成員誤差高度相關（同數據同方法 — Hubáček 2022：各 rating 系統 RPS 只差 ~0.005，有上限效應）② 池入有弱成員（Mannes 2014）③ 樣本細 + 複雜權重（forecast combination puzzle）④ 無 out-of-fold 洩漏 ⑤ 就算全做得啱 — bookmaker consensus 仲係 2023 Challenge 最強 DL 模型嘅牆（輸 6.42%）。

💎 總結一句：你嘅構想方向有實證支持（尤其解讀 A），預期 RPS 由純統計 ~0.2035–0.2101 壓到 0.1925–0.2083 區間（相對改善約 1–4%）— 但要留意 0.1925 嗰個數字係用 21 萬場大數據訓練嘅結果，你幾百至千場樣本要打個折；最終裁判唔係 RPS，係有冇跑贏 closing line。

═══════════════════════════════
📄 文獻逐篇盤點（按解讀對號 + 可信度評級）
═══════════════════════════════

🟢 A 組：解讀 A 實證（統計模型輸出做 ML 特徵）— 大樣本＋out-of-sample

① Hubáček, Šourek & Železný (2019, Machine Learning) — Challenge 2017 亞軍
• 做法：pi-ratings + PageRank 等 rating 做特徵 → XGBoost（feature-based）+ RDN-Boost（relational）
• 樣本/驗證：OISD 大數據；challenge test 206 場
• 結果：RPS 0.2083 / acc 0.5146；GBT 好過 neural network
• 評級：🟢

② Berrar, Lopes & Dubitzky (2019, Machine Learning) — Challenge 2017 冠軍
• 做法：recency features vs rating features 兩組 → XGBoost / k-NN
• 結果：rating features > recency features（兩種模型都係）；XGBoost+ratings RPS 0.2054 / acc 0.5194（賽後重跑）
• 意義：呢個係 ablation 式證據 — 特徵質素（ratings）比模型選擇重要
• 評級：🟢

③ Razali et al. (2022) — 旗艦數字
• 做法：XGBoost/LightGBM/CatBoost × Elo/pi-ratings 特徵
• 結果：CatBoost+pi-ratings RPS 0.1925 — 好過 2017 Challenge 全部參賽者（冠軍 0.2063）、好過 bookmaker 水平（0.2020）；TabNet+pi-ratings RPS 0.1956
• ⚠️ 大 caveat：訓練用 OISD v2 全量（>21 萬場）— Kris 幾百至千場樣本唔可以期望直接複製呢個數
• 評級：🟢（樣本大）但外推到小樣本要打折

④ Hubáček et al. (2022) — 上限效應證據
• 做法：比較 Bivariate/Double Poisson、Weibull、Elo/Steph/Gaussian-OD/Berrar/pi-ratings（純統計+rating，無 boosting）
• 樣本/驗證：OISD，2010 年 7 月前做 validation、後 91,155 場做 test — 教科書級 protocol
• 結果：全部分 Rating 系統 RPS 集中喺 ~0.2101±0.005；原文結論「suggesting the existence of some limits to match prediction performance」
• 意義：唔同數學模型之間差距極細 — ensemble 嘅可搾空間唔大，但亦證明「邊個模型」唔係重點，「點組合」先係
• 評級：🟢

⑤ Yeung, Bunker, Umemoto & Fujii (2024, Springer Machine Learning) — 2023 Challenge 實證
• 做法：DL（TimesNet/Transformer 混合）vs CatBoost + 205 個特徵庫（收集 2017 Challenge 冠亞軍+第 4 名全部 feature sets）經 CFS 揀剩 ~40
• 結果：① CatBoost+pi-ratings 仍然係 GBT 最好（validation loss 0.1991）② DL（Inception+TE+MLP）跑贏晒 2017 所有 published models ③ 但 DL 喺 Task 2 輸俾 bookmaker consensus 模型 6.42% ④ 波膽（exact score）任務：Berrar ratings + 簡單統計 baseline 反而贏 DL 同 GBT
• 意義：反面警告 — 就算 2026 年 SOTA DL，都未過 bookmaker 呢關；且「簡單統計模型喺某啲任務反勝」係對 hybrid 迷信嘅降溫劑
• 評級：🟢

⑥ Robberechts & Davis (2019) — 純統計 baseline 錨點
• 做法：Elo ordered logit；ELO+offensive-defensive ordered logit
• 樣本：FIFA WC + OISD
• 結果：ELO RPS 0.2035 / acc 0.5146；ELO+OD 0.2045；bookmaker odds RPS 0.2020 / acc 0.5194 — bookmaker 仲係好過兩個統計模型
• 評級：🟢 — 呢組數字係你嘅「要打敗嘅牆」

⑦ Groll, Ley, Van Eetvelde & Zeileis (2019) — 直接對號入座
• 做法：Random Forest 以 Poisson ranking model 出嘅球隊能力值做特徵（正正係「統計模型輸出做 ML 底」）
• 樣本：FIFA World Cup 2002–2014
• 結果：「substantial improvement over traditional models」（綜述引述；定性）
• 評級：🟡（WC 樣本細，但做法同你構想 A 完全同構）

🟡 B 組：解讀 B 實證（stacking／meta-learner）— 間接但有用

⑧ Stübinger, Mangold & Knoll (2019) — 交易指標級證據
• 做法：ML 算法 ensemble（唔同 base learner 組合）
• 樣本/驗證：五大聯賽 47,856 場（2006–2018），out-of-sample
• 結果：回報 +1.58%/場，跑贏個別模型同 naive 策略
• 評級：🟢 — 罕有以「真回報」做終點指標嘅集成研究

⑨ Weissbock & Inkpen (2014) — stacking 原型實證（NHL）
• 做法：統計數據 + 賽前文本 + 情緒 三個分類器 → meta-classifier（cascade/majority voting）
• 結果：majority voting 60.25% > 個別分類器；對照 baseline（主場優勢）56%、理論上限 ~62% — 即係吃咗一半可搾空間
• 評級：🟡（單季 708 場）

⑩ Kim & Lee (2023) — 特徵逐級疊加實證（KBO）
• 做法：傳統統計 → +NLP 情緒 → +新聞 embeddings
• 結果：0.6508 → 0.7222 → 0.7430（每加一層異源信息源都有增益）
• 意義：支持「異源成員」嘅價值 — 同多樣性理論一致
• 評級：🟡（樣本中細，但增益方向清晰）

⑪ Eryarsoy & Delen (2019) — 土耳其超 3,060 場：ensemble methods 表現最好（NB/DT 對照）🟢
⑫ Park et al. (2018) — KBO DNN ensemble：RMSE/MAPE 較傳統回歸改善 15.17%/14.34%（另一運動嘅集成增益實例）🟡

⚖️ 解讀 C 實證（testing 加權組合）— 理論文獻的實證面

⑬ 50-year review（Wang, Hyndman, Li & Kang 2022, IJF）綜合結論
• 「unanimous conclusion that simple combination schemes are hard to beat」— 等權平均係最流行同意外穩健嘅組合規則（M-competition 1001 條序列、M4 競賽、Genre 2013 GDP 預測等全部重複證實）
• Aksu & Gunter (1992)：非負約束 OLS「至少同等權一樣穩健準確，且好過其他 regression 類組合」← 呢句係你「testing 加權」嘅最安全實現方式
• Conflitti et al. (2015)：非負+加總一 約束 = LASSO 特例
• Atiya (2020)：bias-variance 分解證實「增益嚟自成員多樣性」
• Mannes et al. (2014)：池入有低質成員會拖低組合 — 唔係越多越好
• 陷阱補充：組合成員用重疊信息集訓練時「combinations are unlikely to be beneficial」— 你三個統計模型同食歷史賽果，正正中呢個槍口
• 評級：🟢（宏觀大樣本）→ 外推小樣本要靠你自家 walk-forward

💰 校準 vs 準確率 — 加碼證據

⑭ Walsh & Joshi (2024)：校準優化模型 vs 準確率優化模型 — 前者平均回報高 69.86%！
• 意義：Kris 問「提升準確率」— 但文獻話你知：準確率/RPS 嘅微細提升對回報嘅貢獻，遠細過校準嘅貢獻。ensemble 之後記得校準，唔好齋追 RPS
• 評級：🟢

🎯 Bonus：xG 特徵成員嘅直接證據

⑮ Anzer & Bauer (2021)：XGBoost xG 模型，Bundesliga 105,627 shots，RPS 0.197（shot-level；話俾你知 xG 數據確實帶得住 0.197 級信息量）

═══════════════════════════════
🔴 反面／降溫證據（唔好淨睇正面）
═══════════════════════════════

⑯ Elmiligi & Saad (2022)：hybrid（ML+統計分析）205,182 場，得 46.6% accuracy / RPS 0.2176 — 低過 bookmaker 水平（0.2020）好多。Hybrid 包裝唔會自動變強，實現質素先係一切
⑰ Hervert-Escobar et al. (2018)：Bayesian + 三角分布，20 萬場，RPS 0.2620 — 差
⑱ Hubáček et al. (2022) 上限效應：各 rating 系統 RPS 差距 ~0.005 — 模型之間冇乜位搾
⑲ 2023 Challenge：SOTA DL 輸 bookmaker consensus 6.42%；波膽任務統計 baseline 反勝 ML — 「ML 永遠更好」係迷思
⑳ Forecast combination puzzle（Stock & Watson 2004；Smith & Wallis 2009）：小樣本估權重嘅誤差會吃掉增益 — 你幾百場樣本正正喺危險區

═══════════════════════════════
🧮 綜合證據強度
═══════════════════════════════

• 解讀 A（rating/模型輸出做特徵）：證據強度 ★★★★☆ — 4+ 篇獨立大樣本研究一致指好過純統計；旗艦數字 RPS 0.1925（但大數據訓練）
• 解讀 B（stacking meta）：★★★☆☆ — 跨運動間接證據一致（細幅），足球專門研究少，需自行驗證
• 解讀 C（testing 加權組合）：★★★☆☆ — 宏觀大樣本證據強（等權基準+非負約束），小樣本外推係你嘅風險區
• 上限：bookmaker 0.2020 係大多數學術模型過唔到嘅牆；rating 系統間差 ~0.005 = 模型選擇空間細，組合/特徵先係槓桿

═══════════════════════════════
🎯 對 Kris 場景嘅結論（3-4 個異源統計模型 + testing 權重、幾百至千場）
═══════════════════════════════

預期提升幅度（有文獻錨點嘅誠實版）：
• RPS：由純統計模型 ~0.2035–0.2101 → ensemble 後 0.1956–0.2083 區間（相對改善約 1–4%；0.1925 嗰級數要大數據訓練先達到）
• 準確率：~0.515 → ~0.52–0.53（細幅；且準確率唔係好 KPI — 見 Walsh & Joshi）
• 真正嘅裁判：有冇長期正 CLV（書商水位 2–5%，RPS 微改善未必過到條線）

防過擬合條件（文獻逐條對應）：
1. 任何權重方案必須跑贏等權 baseline（Stock-Watson puzzle）
2. 權重用非負+加總一約束（Aksu-Gunter：regression 類最穩）
3. Meta/權重估計用 out-of-fold + rolling origin（Wolpert 紀律；50-year review 建議）
4. 成員篩選：寧缺勿濫 — 弱成員拖低組合（Mannes 2014）；三個統計模型誤差相關高，市場概率成員係最大增益源
5. 窗口 ≥200 場先重估權重（Baumeister & Kilian 2015：窗口太短 = 權重噪聲）
6. 校準優先於準確率（Walsh & Joshi +69.86%）
7. 期望管理：以「跑贏 bookmaker 0.2020」做里程碑，唔好以「跑贏自己舊模型」自滿（2023 Challenge 教訓）

💎 一句總結：文獻話你知「會提升，但係細步」— rating/模型輸出做特徵 + 簡單穩陣權重（等權起步→非負約束）係有證據嘅路；提升幅度 ~1–4% RPS，真正嘅挑戰唔係「會唔會提升」，係「提升完過唔過得到 closing line 嗰條牆」— 所以 paper trading 驗 CLV 仲係最後關卡。

═══════════════════════════════
📚 主要來源
═══════════════════════════════

足球核心（對號入座）：
1. Hubáček, Šourek & Železný (2019) Machine Learning 108 — GBT+ratings，Challenge 2017 亞軍（RPS 0.2083）
2. Berrar, Lopes & Dubitzky (2019) Machine Learning 108 — Challenge 2017 冠軍；ratings>recency ablation（XGBoost 0.2054）
3. Razali et al. (2022) — CatBoost+pi-ratings RPS 0.1925；TabNet 0.1956（OISD v2）
4. Hubáček et al. (2022) — 91,155 場 rating 系統對比（上限效應 0.2101±0.005）
5. Yeung, Bunker, Umemoto & Fujii (2024) Springer ML (s10994-024-06608-w / arXiv 2309.14807) — 2023 Challenge：DL 跑贏 2017 全部、輸 bookmaker consensus 6.42%；pi-ratings 仍係 GBT 最佳特徵
6. Robberechts & Davis (2019) — Elo ordered logit 0.2035 vs bookmaker 0.2020
7. Groll, Ley, Van Eetvelde & Zeileis (2019) — RF + Poisson abilities hybrid（WC 2002-2014）
8. Constantinou (2019) Dolores, ML 108, 49-75 — Hybrid BN RPS 0.2083
9. Tax & Joustra (2015) — Eredivisie 13 季 hybrid（public+odds）56.054%
10. Stübinger, Mangold & Knoll (2019) — ML ensemble 47,856 場 +1.58%/場
11. Anzer & Bauer (2021) — xG XGBoost 105,627 shots RPS 0.197

跨運動間接：
12. Weissbock & Inkpen (2014) — NHL meta-classifier 60.25%（上限 62%）
13. Kim & Lee (2023) — KBO 0.6508→0.7222→0.7430 ｜ Park et al. (2018) — DNN ensemble RMSE −15.17%
14. Eryarsoy & Delen (2019) — 3,060 場 ensemble 最優

組合/校準理論實證：
15. Wang, Hyndman, Li & Kang (2022) Forecast combinations: an over 50-year review, IJF（arXiv 2205.04216）— 等權難敗 unanimous conclusion；Aksu & Gunter 1992 非負約束最穩；Atiya 2020 多樣性分解；Mannes 2014 弱成員拖累
16. Stock & Watson (2004) J. Forecasting 23, 405-430 ｜ Smith & Wallis (2009) Oxford Bulletin 71(3) — puzzle
17. Walsh & Joshi (2024) — 校準優化回報 +69.86%（經 arXiv 2410.21484 系統綜述引述）
18. arXiv 2410.21484 — ML in sports betting 系統綜述（PRISMA，219 篇）
19. Constantinou & Fenton (2013) — 14 聯賽 7 季 RPS：odds 準確度「no improvement over time」（市場效率背景）

———
📌 備註：Razali (2022) 訓練樣本為 OISD 全量（>21 萬場），其 RPS 0.1925 唔可以直接預期喺 Kris 幾百至千場樣本重現 — 本報告已喺結論標明打折。所有評級（🟢🟡🔴）為「樣本量×驗證方式」證據強度評級。本報告唔構成投注意見。