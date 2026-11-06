🔍 AI BETS 數學模型 — 業界現況盤點（2026）
任務：20261026-133000-seo-ai-bets-math-models
日期：2026-10-26 ｜ 整理：Scout（SEO agent）
角度：唔講「可以點優化」（上份做咗），今次盤點「業界而家真係用緊咩、邊個用」
格式：純文字 + emoji 分組，無 markdown 表格

═══════════════════════════════
⚡ 總覽 + 2026 主力答案（先講結論）
═══════════════════════════════

🌐 業界生態一句話：數據商（Opta/Sportradar/StatsBomb）供應彈藥 → 莊家用 xG+GBM 定價 → 專業 syndicate 用 power ratings+Monte Carlo 搵市場錯價 → 散戶產品多數係黑盒 tipster 包裝。

🏆 2026 年 AI betting 主力組合（明確答案）：
「Dixon-Coles 系 Poisson + Elo/pi-ratings + xG features + gradient boosting（LightGBM/XGBoost/CatBoost）+ de-vig（power/Shin）+ fractional Kelly + 機率校準 + market prior」
• 公開 benchmark 嘅單一最強方法 = gradient boosted trees 食 rating+xG features（RPS ~0.19–0.20 區間）
• 實戰地基（莊家同 syndicate 共用）= Poisson/DC 進球矩陣 + shot-level xG
• 盈利判準（所有人最終都要過）= 跑贏 closing line
• DL/LLM 係「有話題、冇接棒」— benchmark 未贏過 GBM，更未贏過市場

═══════════════════════════════
📐 A. 統計／概率模型（經典基石 — 業界仍在用嘅地基）
═══════════════════════════════

① 獨立雙 Poisson
• 原理：兩隊進球各自獨立服從 Poisson(λ_home, λ_away)，外積成比分矩陣。
• 邊個用：幾乎所有入門模型、消費級預測網站、repo 個 baseline；莊家用佢做「起點」再人手調。
• 實戰：系統性低估 0-0/1-1 同和波 — 1997 年已被 Dixon-Coles 證實，作為獨立模型已過時，但係所有進階版嘅基座。

② Dixon-Coles（tau 修正 + 時間衰減）
• 原理：τ(ρ) 只調 0-0/1-0/0-1/1-1 四格相關性 + exp(−ξ·t) 時間衰減權重，MLE fit。
• 邊個用：學術界 30 年基準模型；開源實現 penaltyblog/dashee87；業界 Poisson 系定價嘅事實標準；2026 年 predictionengine 等教學/回測仍以佢做 baseline。
• 實戰：1X2 RPS 約 0.19–0.21 區間；「rarely beaten by 40–100 feature 嘅 XGBoost」（predictionengine 2026）。29 年歷史仍是 SOTA 候選 — 呢個本身係業界最重要事實。

③ Bivariate Poisson（Karlis & Ntzoufras 2003）
• 原理：加入共同進球潛變量 λ₃（或對角膨脹），直接建模雙方進球相關，改善 draw 校準。
• 邊個用：學術正統（RSS）；penaltyblog 現成實現；Koopman & Lit 2015 嘅動態版（非高斯 state-space + Kalman smoother）係計量經濟派標配。
• 實戰：改善主要集中 draw 概率；效果比 DC tau 溫和，多做「第二層升級」唔做第一刀。

④ Skellam（進球差分布）
• 原理：兩個獨立 Poisson 之差嘅分布 — 直接對「讓球/淨勝球」定價而唔使全矩陣。
• 邊個用：AH/讓球市場定價嘅輕量選擇；Sage 2026「簡單模型+recent xG+Skellam+isotonic 校準」實證可以打到接近市場水平。
• 實戰：勝在快同簡潔，適合實時服務。

⑤ Elo
• 原理：勝負後按期望差更新評分（K·(result−expected)），國際足協世界排名 2018 後就用 Elo 變體。
• 邊個用：FIFA World Ranking（官方！）、clubelo.com、唔少莊家內部 rating、FiveThirtyEight 模型組件、Nature 2026 multi-parameter fusion 研究。
• 實戰：簡單、自適應、幾十年驗證；單用偏粗，做特徵一流。

⑥ pi-ratings（Constantinou & Fenton 2012）
• 原理：用「比分差 vs 期望比分差」雙向動態更新 home/away 兩套評分，收斂快。
• 邊個用：Constantinou 全系列模型（pi-football、Dolores）、CatBoost 55.82% 學術 SOTA（Razali 2022）、2022 JSA 亞洲讓球盤效率研究。
• 實戰：證實係 GBM 特徵嘅高性價比組件。

⑦ Glicko / Massey / Colley
• 原理：Glicko=Elo+評分不確定度（RD）；Massey=勝差最小二乘線性系統；Colley=考慮賽程強度嘅 Laplace 近似。
• 邊個用：Massey/Colley 曾係 BCS 大學美式足球官方排名組件（ESPN/BCS 時代）、Massey Ratings 網站至今追蹤幾十套系統；Glicko 多見於棋類/電競，體育投注用得少。
• 實戰：美式市場主流，足球圈 Elo/pi-rating 更常見；thepowerrank 等仍用佢哋做 CFB 預測。

⑧ State-space / Kalman 濾波
• 原理：球隊強度做隨機遊走潛狀態，每場比賽後 Bayesian 更新，天然處理狀態隨時間演變。
• 邊個用：Stern 1994 NFL 經典 → Koopman & Lit（Tinbergen）動態 bivariate Poisson → 2018 IJF score-driven 時間序列（Kalman filter + recursive mode estimation）；學術派預測主力，澳洲足球聯賽等應用（Maastricht「Beating the Odds」）。
• 實戰：計量經濟學者嘅最愛；工程複雜度高過 Elo，業界商用未見主流，但係「正確處理時間演變」嘅黃金標準。

⑨ Bayesian 分層／球員級模型（KickScore）
• 原理：球隊強度唔係單一數，而係「球員技巧潛變量嘅集合」，技巧隨時間平滑演變，用近似推斷（message passing/factor graph 類）聚合。
• 邊個用：Kickoff.ai（EPFL INDY Lab）— 官方明言模型「把球隊看成球員嘅集合」，近百年歷史數據動態加權；Bayesian hierarchical 亦係 StatsBomb 級數據商做 player-adjusted 指標嘅常用框架。
• 實戰：Kickoff.ai 公開歷史預測、平均 log loss 低；單獨公開文檔有限（官方自述+LinkedIn 解說為主），屬「研究型精品」多過「投注工具」。

⑩ 點過程／Hawkes / in-play 隨機強度
• 原理：進球做時間軸上嘅點過程，強度 λ(t) 隨比分/時間/紅牌即時變化；Hawkes 過程再加「事件自我激發」。
• 邊個用：in-play（賽中盤口）定價嘅學術主流 — MDPI 2020 Bayesian in-play 模型、Lund/UCL 賽中賠率建模 thesis、arXiv 2018 風險中性對沖定價；專業 in-play 交易團隊同 Stats Perform UltraFast data 場景嘅底層數學。
• 實戰：Nature 2021 用 event/positional data 做 in-play 預測 — 證實「賠率本身仍然大幅跑贏」呢類模型；in-play 係速度戰，數據延遲決定生死。

═══════════════════════════════
🤖 B. Machine Learning 層
═══════════════════════════════

① Gradient Boosting（XGBoost / LightGBM / CatBoost）— 業界公開最強
• 原理：循序加法決策樹擬合梯度殘差；對表格數據（rating+xG+賠率特徵）近乎最優。
• 邊個用：2023 Soccer Prediction Challenge 得獎方案系、Razali 2022（CatBoost+pi-ratings，acc 55.82%/RPS 0.1925）、Gevorgyan 2026（XGBoost+xG+calibration）、arXiv 2305.17094 benchmark（LightGBM 顯著最佳）、systematic review 2024（GBT 全場最低 RPS）。
• 實戰：公開數據上 RPS 0.19–0.20 天花板；特徵質素＞算法選擇。

② Logistic Regression — 而家仲用緊，而且喺最重要嘅位置
• 原理：線性 log-odds 分類，輸出天然概率、可解釋、穩。
• 邊個用：xG 模型嘅業界 baseline！Opta/StatsBomb 級 xG 研究（arXiv 2401.09940 用 StatsBomb 開放數據 logistic 建模）、thexgfootballclub 2026 分析「logistic regression 選作基準因為可解釋性」、賠率隱含概率回歸、calibration 前處理。
• 實戰：xG（43,110 shots 級數據）上 logistic 與 GBM 差距好細；莊家定價 pipeline 鍾意佢嘅穩定性同可審計性。「最古老但未死」嘅模範生。

③ Random Forest / SVM / k-NN — 已退居二線
• 原理：bagging 樹/最大間隔分類/近鄰投票。
• 邊個用：2015–2020 文獻主力，2024–26 benchmark 已被 GBM 全面超越（k-NN rating features 僅 acc 0.5049/RPS 0.2149，arXiv 2403.07669）。
• 實戰：教學價值大於實戰價值。

④ Hybrid ensemble / stacking — 學術派簽名
• 原理：統計模型（Poisson/Elo）+ ML 模型概率經 meta-learner 融合。
• 邊個用：Constantinou Dolores（Machine Learning 108, 2019，Hybrid Bayesian Network，全球賽事預測）、MDPI 2026 多模型比較、IPP hybrid thesis。
• 實戰：穩定細幅改善單一模型；業界共識係「融合市場信息嘅 ensemble」比「純模型 ensemble」更有用。

═══════════════════════════════
🧠 C. Deep Learning／LLM 前沿實況
═══════════════════════════════

① LSTM / Transformer / TabNet
• 原理：序列神經網絡學隊伍表現時間依賴；TabNet 用注意力做表格數據。
• 邊個用：2022 TabNet+pi-rating（RG）號稱超越現有模型；各類 2023–25 DL 論文（Eredivisie 框架、metaheuristic ensemble DL）。
• 實戰：Springer Machine Learning 2024 權威 benchmark — DL 仲係輸 bookmaker odds（RPS 0.2020/acc 0.5194）一皮；小樣本易過擬合、可解釋性差。2026 現況：有話題、冇主導。

② LLM agents（GPT/Claude/Grok 預測）
• 原理：把數值特徵轉成文字 prompt 交 LLM 出概率，或 multi-LLM 對賽取共識。
• 邊個用：ScoreGPT（多 LLM 同場對賽、公開評分）、LLM-SoccerArena（2026-07 live benchmark）、AI World Cup 2026 benchmark、OSF 2024 GPT-4 對比研究。
• 實戰：GPT-4「competitive accuracy 無需特徵工程」但未超 GBM/SOTA；repo 嘅用法（LLM 做賽前研究/註釋、唔做決策）同目前證據一致 — 2026 業界位置：註釋員，唔係模型。

═══════════════════════════════
🏢 D. 業界／專業實況（邊個真係用緊咩）
═══════════════════════════════

📡 數據商模型（莊家嘅軍火庫）
• Opta（Stats Perform）：xG pipeline = shot-level logistic regression baseline + gradient boosting 家族升級（Hudl 2025 研究：logistic/RF/NN/GBM 並列比較；XGBoost 達 AUC 0.878/Brier 0.0686）；UltraFast in-play live xG feed 供莊家實時定價。
• StatsBomb：開放數據 + shot-level xG（43k shots 級），學術界最常用佢嘅數據驗證模型（arXiv 2401.09940 等）。
• Sportradar：NFL/NBA/英超官方數據夥伴；odds feed+賽事模型服務 sportsbook，另一條產品線係賽事操守/異常投注偵測（統計異常模型）。
• 💡 重點：呢啲模型嘅輸出大部分直接入莊家定價 — 散戶模型要贏，本質係要贏呢條 pipeline 嘅殘差。

🎯 專業 syndicate／sharp bettor（唔公開但可考證嘅輪廓）
• Power ratings（Elo/pi-rating 變體）+ 對每場出「真實賠率線」→ 同莊家開價比對，差異夠大先落注。
• Monte Carlo simulation：賽季/錦標賽級別 10,000+ 次模擬（World Cup 2026 消費級工具都係咁做；FiveThirtyEight SPI 模型遺產 — 2023 年停運後由開源社群接棒）。
• Closing line 為王：sharp money 推動 closing line，長期跑贏 CLV 係業界唯一公認嘅「真實 edge」證明（Karl Whelan 2026 亦提醒 CLV 非充分）。
• Ziemba《Sports Analytics》文集記載專業 syndicate 團隊運作 — 共同點：紀律、規模化、唔公開。
• 💡 實戰表現：Pinnacle「Winners Welcome」+ 唔限贏家 = 全行最 sharp 嘅價，就係呢班人磨出嚟。

💱 交易所 bot（Betfair 生態）
• 模型：Poisson/Skellam 定價 + market making（報價兩邊賺差價）+ in-play 點過程實時更新 + 對沖。
• 開源代表：flumine（Betfair 自動化框架）+ betfair-datascientists 社群教程；學術支撐 = arXiv 1811.03931 風險中性定價對沖。
• 實戰：交易所係唯一合法 API 自動化場地（UK 等），盈利靠速度+存貨管理多過預測精度。

🛒 消費級產品（數學透明度光譜）
• Kickoff.ai — 半透明：方法（KickScore 球員級 Bayesian）有官方解說+公開歷史記錄，深度細節未全公開。研究型精品。
• ZCode — 不透明：閉源黑盒，宣稱 65%+ 勝率，無公開方法論/審計。tipster 包裝。
• Betegy — 不透明（B2B）：賣預測+視覺化引擎畀 sportsbook/媒體，方法論未公開，但客戶係機構唔係散戶。
• Oddalerts/ScoutingStats 等 — 半透明：預測公開逐日評分（1X2 30 日 51.7% 級別），模型細節不公開。
• 💡 落差觀察：越係「消費級」,數學越唔透明；越係「研究型/B2B」，越經得起對照。

═══════════════════════════════
🎲 E. 底層數學工具（貫穿所有層）
═══════════════════════════════

① De-vig（去水位）四法
• Equal margin（等比例縮放）：最簡單，最常用。
• Power method：解 over^a + under^a = 1（Newton-Raphson），對長短賠偏置更準 — MDPI 2026 用佢做 market feature。
• Shin method（1991/93 insider 模型）：假設盤口混合「公眾注+知情注比例 z」，莊家為防內幕而 shading — 反解 z 同真實概率；Claw Arbs/Whet 等 2026 工具全部內置。業界共識：3-way 市場 Shin/power 優於 equal margin。
• 實戰：edge 計算嘅第一口井；用錯方法會造出假 edge。

② Kelly criterion 家族
• 原理：最大化 log 財富增長 f*=(bp−q)/b；full Kelly 波動大（回撤 35%+ backtest），實務 0.25–0.5 fractional；simultaneous Kelly 處理多注同時下注嘅相關性。
• 邊個用：所有嚴肅 bot/syndicate；repo 已內建（KELLY_FRACTION 需收至 0.5）。
• 實戰：數學冇爭議，執行全靠紀律。

③ 機率校準（Platt / isotonic / temperature）
• 原理：用驗證集將模型輸出映射到真實頻率；Platt=sigmoid 參數化，isotonic=非參數單調，temperature=單參數縮放。
• 邊個用：Gevorgyan 2026（isotonic）、Sage 2026（isotonic）、r/algobetting 實戰（per-sport Platt+時間衰減+cap 0.80）、xG 模型生產線（Brier 0.0686 級）。
• 實戰：未校準概率 → 假 edge → 錯 Kelly 注碼；2026 年校準已係標配唔係可選。

④ Monte Carlo simulation
• 原理：由概率模型重複抽樣（萬次級）得賽果/賽季/錦標賽分布。
• 邊個用：syndicate 賽季規劃、World Cup 工具（10,000+ brackets）、FiveThirtyEight SPI 遺產、物理/市場值出發嘅錦標賽模擬（ScienceDirect 2022）、Nature 2026 fusion 研究。
• 實戰：單場預測佢幫唔到手，長期/組合層面（賽季盤、未來盤、組合曝險）唔少得。

═══════════════════════════════
⚖️ 業界共識 vs 現實落差
═══════════════════════════════

✅ 共識區（有數據、有人用、重現得出）
1. Poisson/DC + Elo/pi-rating + xG 特徵 + GBM = 公開 SOTA 組合
2. 市場（closing line）係最強預測器 — IEEE 2026「bookmaker implied probs dominate」
3. 校準 + fractional Kelly + de-vig 細節 = 盈利基建
4. 樣本量：幾千注先有意義

⚠️ 落差區（宣傳 vs 實證）
1. 消費級「AI 72% 準確率」vs 公開追蹤 51–52% — 命中率遊戲，唔係 edge
2. DL/LLM 論文熱度 vs benchmark 現實 — 2024–26 三份權威 benchmark 都未見 DL 贏 GBM，更未贏市場
3. 「AI 產品」包裝 vs 黑盒無審計 — ZCode 式宣稱 65% 勝率無人可以驗證
4. in-play event-data 模型 vs 賠率 — Nature 2021：賠率仍大幅領先；數據商 live feed 才係 in-play 嘅真武器
5. 學術 SOTA（55.82%）vs 市場效率 — 學術唔交水位、唔使面對限紅；「跑贏學術基準」≠「跑贏 closing line」
6. 透明度倒掛 — 越面向散戶越黑盒，越研究型/B2B 越可對照

═══════════════════════════════
🔮 前沿趨勢（2026 觀察）
═══════════════════════════════

1️⃣ Prediction markets（Kalshi/Polymarket）同莊家賠率之間嘅 arb bot 成新戰場
2️⃣ State-space/score-driven 模型復興（IJF 系持續產出，處理動態更正統）
3️⃣ LLM 從「預測器」退位轉型「研究助理+benchmark 對照組」（LLM-SoccerArena 式 live grading）
4️⃣ Event/positional data（追蹤數據）逐步進入 in-play 定價 — 數據商護城河加深
5️⃣ Calibration-first 工作流成為教學/實戰標配
6️⃣ FiveThirtyEight 停運後，開源公開 projection 模型社群補位

═══════════════════════════════
📚 主要來源
═══════════════════════════════

統計模型：
1. Dixon & Coles (1997, JRSS-C) ｜ predictionengine.app 2026 解析+backtest
2. Karlis & Ntzoufras (2003, RSS-C) bivariate Poisson
3. Koopman & Lit (2015/Tinbergen 12099) dynamic bivariate Poisson state-space
4. IJF 2018 (sciencedirect S0169207018302048) score-driven 賽果預測
5. Sage 2026 (22150218261416681) Skellam+recent xG+isotonic
6. Constantinou & Fenton 2012 pi-ratings ｜ Constantinou 2019 Dolores (ML 108)
7. Maastricht Beating the Odds（Kalman state-space）｜ Stern 1994（NFL state-space）
8. kickoff.ai/about ｜ LinkedIn Ovidiu Alexandru（KickScore 球員級模型官方解說）
9. MDPI 2020 (10/8/2904) Bayesian in-play ｜ arXiv 1811.03931 in-play 定價對沖 ｜ Nature 2021 (s41598-021-03157-3) in-play event data
10. impliedscore.com Poisson limitations（非齊次強度/紅牌）

ML/DL/LLM：
11. arXiv 2403.07669 ML for Soccer 綜述 ｜ arXiv 2410.21484 sports betting 系統綜述
12. arXiv 2305.17094 GBM benchmark（LightGBM 最優）
13. Springer ML 2024 (s10994-024-06608-w) DL vs bookmaker（RPS 0.2020）
14. Razali et al. 2022（CatBoost+pi-ratings 55.82%/RPS 0.1925，經 thexgfootballclub 綜述）
15. Gevorgyan 2026（XGBoost+xG+isotonic）｜ smartmatchpick 2026（Brier<0.210 門檻）
16. arXiv 2607.24573 LLM-SoccerArena ｜ arXiv 2608.03416 AI World Cup 2026 ｜ OSF 2024 GPT-4 對比
17. TabNet+pi-rating 2022（ResearchGate 365213939）

業界實況：
18. Hudl 2025「One xG model to rule them all」(xG 模型比較) ｜ arXiv 2401.09940（StatsBomb 數據 logistic xG）｜ RG 395517114（XGBoost xG AUC 0.878/Brier 0.0686）
19. Stats Perform Opta + UltraFast Data（官方）｜ Sportradar 官方
20. FiveThirtyEight SPI 遺產（fromthebyline.substack 2023）｜ smartmatchpick World Cup Monte Carlo
21. flumine/betfair-datascientists（交易所自動化）｜ Ziemba《Sports Analytics》（syndicate）
22. ESPN BCS（Massey/Colley 官方歷史）｜ thepowerrank.com

底層工具：
23. krokodds/clawarbs/whet/smartstake 2026 de-vig 四法對照（Shin z 解說）
24. Kelly criterion — Wikipedia ｜ r/algobetting 校準實戰（Platt+cap 0.80）

———
📌 備註：KickScore/ZCode/Betegy 內部方法論公開程度有限，相關描述已標明來源層級（官方自述 vs 獨立審計）。本報告為資訊整合，唔構成投注或投資建議。
