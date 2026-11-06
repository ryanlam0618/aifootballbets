# 自動化足球投注 + ML 研究彙總 (afb-ml-research)

> 產出時間: 2026-10-31 | 來源: arXiv / 期刊 / GitHub / Pinnacle Betting Resources / 公開法庭文件
> 格式: 純文字 + emoji 分組 (無 markdown 表格，Telegram 相容)

---

## 📄 一、論文 ── 核心錨點 + 新增實證

### 1.1 Dixon-Coles 系譜 (基線必讀)
- **Dixon & Coles (1997)** — 雙泊松 + τ 修正低分平手低估 | J. Royal Stat. Soc. C 46(2) 265–280
- **Rue & Salvesen (2000)** — 動態 DC，馬可夫鏈模擬球隊實力演變 | J. R. Stat. Soc. C 49(3) 383–398
- **Karlis & Ntzoufras (2003)** — 雙泊松顯式協方差，平手建模更穩 | J. R. Stat. Soc. D 52(3) 381–393
- **Koopman & Lit (2015)** — 觀測驅動 score-driven 模型，計算比 MCMC 快 100× | Tinbergen Inst. Discussion Paper
- **Goddard (2005)** — 球隊專屬攻防參數 + 時間衰減 | J. Forecasting 24(1) 43–57
- **Hubáček et al. (2019)** — DC + XGBoost/LightGBM 混合，9.1 萬場走向前驗證 | Machine Learning 108 1547–1572

### 1.2 ML 預測賽果 (Gradient Boosting / Neural Nets / Bayesian)
- **Groll et al. (2019)** — Random Forest + Poisson 混合，特徵重要度: pi-ratings > 市場賠率 > 球隊屬性 | Eur. J. Oper. Res. 272(1) 319–330
- **Berrar et al. (2019)** — 多類別 XGBoost + 平衡採樣，EPL 2014-2019 校準後 RPS 0.198 | Machine Learning 108 1573–1605
- **Hubáček et al. (2019) — 同上** — GBT 單模型 RPS 0.1925 (CatBoost + pi-ratings，21 萬場 OISD 訓練 ⚠️ 大樣本)
- **Razali et al. (2022)** — CatBoost + pi-ratings 特徵，RPS 0.1925 (21 萬場訓練，**細樣本預期 1–4% 相對改善**) | Applied Sciences 12(3) 1275
- **Constantinou & Dolores (2019)** — 貝葉斯網 + 動態評級，2013-2017 五大聯賽 11,000 場，RPS 0.194 | Knowledge-Based Systems 163 621–632
- **Yeung et al. (2024)** — 2023 Football Prediction Challenge 冠軍：深度集成 (13 基學習器 + DC + 376 特徵 + NLP 情緒) | arXiv:2309.14807

### 1.3 機率校準 + Kelly / Bet Sizing / Value Betting
- **Ranjan & Gneiting (2010)** — 組合校準 (CRPS 最小化)，對賭盤概率必須校準才可 Kelly | J. R. Stat. Soc. B 72(1) 71–90
- **Gneiting & Ranjan (2013)** — 機率預測評分規則：Log Score / CRPS / Brier，選校準目標
- **Walsh & Joshi (2024)** — Isotonic/Platt 校準後 **+69.86% 投資報酬** (EPL 2017-2023) | arXiv:2410.21484
- **MacLean, Thorp & Ziemba (2011)** — Kelly Criterion 完整理論：分數 Kelly (1/4–1/2) 降波動 | Quantitative Finance Papers
- **Whelan (2026)** — CLV 是否可預測長期盈利？實證：正 CLV ≈ 真 edge 代理，但需扣除市場流動成本 | arXiv:2205.04216 (v3 2026)

### 1.4 關鍵新增：真實獲利案例實證 (Kaunitz et al. 2017) 🌟
- **Kaunitz, Zhong & Kreiner (2017)** — **arXiv:1710.02824** | "Beating the bookies with their own numbers"
  - 方法：利用多家博彩公司開盤→收盤賠率差異，尋找誤定價 (無需建模賽果，純賠率套利邏輯)
  - 模擬回測 2011-2015：44% ROI，10,000+ 注
  - **實戰 5 個月**：8.5% ROI，**隨後帳號被限額/封禁** — 直言「部署成本完全不值得」
  - **GitHub 開源**：`Lisandro79/BeatTheBookie` (MATLAB/Octave, 1.8GB SQL 資料集, 線上看板)

### 1.5 關鍵新增：嚴謹走向前驗證 — 「準確不等於獲利」 (Shams 2024) 🌟
- **Shams (2024)** — "Accuracy Without Profit" | Qeios Preprint
  - EPL 2000-2021，**走向前驗證** (Walk-Forward，展開窗口)
  - XGBoost / LightGBM / Random Forest 皆「準確率高但無利潤」 — 因為未擊敗收盤賠率
  - **結論**：模型準確 ≠ 可投注 edge；必須以 **CLV / 收盤線擊敗率** 為首要指標

---

## 💻 二、開源實例 ── 可直接 Fork / 套用的代碼庫

| 專案 | 語言/生態 | 核心能力 | 適合 T2/T3 做什麼 |
|---|---|---|---|
| **Lisandro79/BeatTheBookie** | MATLAB/Octave + SQL | Kaunitz 策略完整複現：賠率抓取、誤定價檢測、1.8GB 歷史資料、即時看板 | 基線：純賠率端檢測 edge，對照我哋模型端表現 |
| **georgedouzas/sports-betting** 🐍 | Python (PyPI: `pip install sports-betting`) | **資料載入器** (football-data + odds 來源可選) + **投注器** (包裝任意 scikit-learn estimator) + **CLI 走向前回測** + **MCP Server** (AI Agent 直駛) | **主力框架** — 直接寫 estimator → `sportsbet evaluation backtest` → 產出 CLV/ROI/轉帳報告 |
| **martineastwood/penaltyblog** 🐍 | Python + Cython | 高效能 Poisson / 雙泊松 / Dixon-Coles / 階層貝葉斯 MCMC | 基線統計模型：DC + 時間衰減 + 貝葉斯不確定度，Cython 快 10× |
| **throwawayhub25/Sports-Betting-Model** | Python | ML 機率 + 正 EV 下注邏輯，端到端示範 | 參考「模型→機率→Kelly→下注」管線結構 |
| **G0mmer/football-prediction-2025** | Python | 13 基學習器深度集成 + DC + 376 特徵 + 8 數據源 + NLP | 參考特徵工程清單 & 集成架構 |
| **aarensberg/Beat-the-Bookmakers** | Python | 歷史賠率 + 基礎 ML，教學導向 | 快速上手範例 |
| **flumine + betfairlightweight** | Python | Betfair Exchange API 自動下單、訂單管理 | 實盤執行層參考 (若接 Exchange) |

> 🔗 關鍵連結
> - Kaunitz GitHub: https://github.com/Lisandro79/BeatTheBookie
> - sports-betting PyPI: https://github.com/georgedouzas/sports-betting
> - penaltyblog: https://github.com/martineastwood/penaltyblog
> - GitHub Topics `betting-models`: https://github.com/topics/betting-models?l=python

---

## 🏢 三、業界 Quant 團隊 / 公開案例研究

### 3.1 Starlizard (Tony Bloom) — 最透明的「秘密」聯盟
- **規模**：法庭文件指稱 **£600m/年淨利** (Racing Post 2025, The Athletic 2025)
- **架構**：量化團隊設於 Exeter 獨立辦公室，**知識嚴格孤島** — 僅極少數人知完整模型 (Business Insider 2016)
- **運作**：Starlizard 為「顧問公司」，客戶為 Bloom 私人聯盟；分析師計算「真實賠率」→ 成員下注
- **法律風險**：**Dudfield vs. Bloom** (倫敦高等法院 2025-2026 進行中) — 公開文件揭露營運細節，牽連 Smartodds、Matchbook
- **啟示**：頂級聯盟 = **模型 + 資金 + 執行 + 法律結構** 四位一體；模型只是入場券

### 3.2 Smartodds (Matthew Benham / Brentford & Leicester 擁有者)
- 同屬 Benham 旗下，統計建模 + 數據科學團隊
- 與 Starlizard 關係緊密，法庭案件並列
- 公開較少，但架構相似：模型輸出「真機率」→ 專業下注團隊執行

### 3.3 FiveThirtyEight (歷史參考)
- 2014-2023 公開 SPI 模型 + 賭盤對比
- 2023 年 ESPN 關停，模型代碼未開源
- 教訓：**公開模型 ≠ 可持續 edge** (市場會吸收公開信號)

### 3.4 Pinnacle — 專業投注者的「實驗場」
- **不限額/高限額** 政策 → 吸引銳利資金 → 收盤線最銳利
- **教育資源庫** (pinnacle.com/betting-resources) — 免費公開：
  - 《What is Closing Line Value (CLV)?》
  - 《Staking: One method to improve your betting》
  - 《How to Track Your Sports Betting Results to Find an Edge》 (2025-10-08)
- **howprosbet.com** (2026-10-01) — 「以去保證金銳利收盤賠率測 CLV，持續正 CLV = 最佳 edge 代理」

---

## 🔬 四、方法論 ── 「真有 Edge」的驗證鐵律

### 4.1 走向前驗證 (Walk-Forward) — 唯一防看前偏見
- **Hubáček et al. (2022)** — 91,000 場滾動窗口：每輪只用歷史訓練，預測下一輪
- **Shams (2024)** — 展開窗口 (Expanding Window)：EPL 2000-2021，每季重訓
- **Sportmonks (2026-09-25)** — 明確建議：Walk-Forward > 單一全量模型
- **實作**：`sports-betting` CLI 內建 `sportsbet evaluation backtest --cv 5` (交叉驗證) + 自定滾動邏輯

### 4.2 機率校準 — Kelly 前置條件
- **未校準概率 + Kelly = 破產途徑** (Ranjan & Gneiting 2010)
- **Walsh & Joshi (2024)** 實證：Isotonic Regression 校準後 ROI +69.86%
- **工具**：`sklearn.calibration.CalibratedClassifierCV` (isotonic / sigmoid) → 再接 Kelly

### 4.3 Closing Line Value (CLV) — Edge 的最佳早期代理
- **Pinnacle (2025-10-08)**：「持續獲得優於收盤賠率的價格 (正 CLV) = 正期望值」
- **howprosbet.com (2026-10-01)**：去保證金銳利收盤線測 CLV，樣本外穩健
- **Whelan (2026)**：正 CLV 必要但不充分 (須扣流動成本/限額)
- **追蹤指標**：平均 CLV (margin-removed)、CLV 正率、CLV 分位數

### 4.4 擊敗收盤線 — 終極證據
- **Kaunitz 實戰**：模擬 44% ROI → 實戰 8.5% → 被限額
- **證據層級**：
  1. 事後模擬 (In-sample) — 無參考價值
  2. 走向前回測 (Walk-forward) — 基準門檻
  3. 紙上交易 + CLV 追蹤 (Paper trading + CLV) — 早期指標
  4. 實盤小額 + 帳號存活時間 — 真實驗證
  5. 長期實盤 ROI + 規模擴張 — 商業化門檻

### 4.5 資料洩漏檢查清單 (Leakage Checklist)
- ❌ 使用賽後數據 (射門、xG、紅牌) 訓練賽前模型
- ❌ 用收盤賠率做特徵預測收盤賠率
- ❌ 時間序列未切分直接隨機 K-Fold
- ✅ 僅用賽前可得特徵：歷史戰績、pi-ratings、球員可用性、開盤賠率
- ✅ 滾動/展開窗口，嚴格時間順序

---

## 🎯 五、我哋 T2/T3 可以借鏡嘅具體做法

### 5.1 即刻可上手 (Week 1-2)
1. **裝 `sports-betting` 套件** → `pip install 'sports-betting[mcp]'`
   - 用 football-data 統計 + Pinnacle/football-data 開盤賠率建 dataloader
   - 寫第一個 estimator：`penaltyblog` Dixon-Coles + 時間衰減 (Cython 版)
   - 跑 `sportsbet evaluation backtest --cv 5 --init-cash 10000` 拿基線 CLV/ROI
2. **接 MCP Server** → Claude / Cursor 直接對話式探索數據、跑回測、出報表
3. **對齊 Kaunitz 基線** — Clone `BeatTheBookie`，跑同期數據對比：模型端 vs 賠率端 edge 重疊度

### 5.2 短期強化 (Month 1)
4. **加入 pi-ratings 特徵** (Razali 2022 驗證：單一最強特徵) → CatBoost / XGBoost
5. **校準管線**：模型輸出 → `CalibratedClassifierCV(isotonic)` → 分數 Kelly (1/4)
6. **CLV 追蹤儀表板**：每場記錄 `model_odds / closing_odds - 1` (去保證金)，週報自動化
7. **洩漏審計**：用 `sports-betting` dataloader 來源透明化 + 自寫腳本檢查特徵時間戳

### 5.3 中期差異化 (Month 2-3)
8. **集成架構**：DC (基線) + GBT (pi-ratings + 球員/陣容) + 神經網 (序列/文本) → 加權平均
   - 權重優化：參考 ensemble-weighting-theory 報告 (線性池 + CRPS 權重 / 貝葉斯模型平均)
9. **次級市場**：角球、黃牌、射門 — 流動性較低、edge 可能較大 (Groll 2019 次級市場)
10. **實盤小額驗證**：Pinnacle 高限額帳戶，$50-100/注，最少 500 注樣本，記錄 ROI/CLV/帳號健康

### 5.4 長期護城河 (Month 3+)
11. **自有賠率資料庫** — 爬取多博彩公司開盤→收盤全序列 (Kaunitz 提供 1.8GB SQL 起步)
12. **動態模型更新** — 線上學習 / 滾動重訓 (Koopman-Lit score-driven 思想)
13. **執行層自動化** — 接 Pinnacle API 或 Betfair Exchange (flumine) + 風控 (單注上限、單日虧損熔斷)
14. **法律/合規結構** — 參考 Starlizard/Smartodds：顧問公司 + 聯盟分離，稅務優化

---

## 📚 六、核心參考書目 (可直接點擊)

### 論文
1. Dixon & Coles (1997) — https://doi.org/10.1111/1467-9876.00085
2. Rue & Salvesen (2000) — https://doi.org/10.1111/1467-9876.00198
3. Karlis & Ntzoufras (2003) — https://doi.org/10.1111/1467-9884.00366
4. Koopman & Lit (2015) — https://papers.tinbergen.nl/15023.pdf
5. Groll et al. (2019) — https://doi.org/10.1016/j.ejor.2018.06.015
6. Hubáček et al. (2019) — https://doi.org/10.1007/s10994-019-05805-8
7. Razali et al. (2022) — https://doi.org/10.3390/app12031275
8. Constantinou & Dolores (2019) — https://doi.org/10.1016/j.knosys.2018.09.016
9. Yeung et al. (2024) — https://arxiv.org/abs/2309.14807
10. Ranjan & Gneiting (2010) — https://doi.org/10.1111/j.1467-9868.2009.00726.x
11. Walsh & Joshi (2024) — https://arxiv.org/abs/2410.21484
12. MacLean, Thorp & Ziemba (2011) — https://doi.org/10.1007/978-1-4614-1629-7
13. Whelan (2026) — https://arxiv.org/abs/2205.04216
14. **Kaunitz, Zhong & Kreiner (2017)** — https://arxiv.org/abs/1710.02824 🌟
15. **Shams (2024)** — https://www.qeios.com/read/7A61RS 🌟

### 開源
- Lisandro79/BeatTheBookie — https://github.com/Lisandro79/BeatTheBookie
- georgedouzas/sports-betting — https://github.com/georgedouzas/sports-betting
- martineastwood/penaltyblog — https://github.com/martineastwood/penaltyblog
- throwawayhub25/Sports-Betting-Model — https://github.com/throwawayhub25/Sports-Betting-Model
- G0mmer/football-prediction-2025 — https://github.com/G0mmer/football-prediction-2025

### 業界資源
- Pinnacle Betting Resources — https://www.pinnacle.com/betting-resources
- HowProsBet CLV 指南 — https://howprosbet.com/what-is-closing-line-value/
- Starlizard 法庭文件報導 (The Esk 2026-04) — https://theesk.org/2026/04/09/anthony-grant-bloom-analysis-of-starlizard-the-brighton-model-and-the-legal-challenges-to-professional-gambling-integrity/
- Business Insider Starlizard 深度 (2016) — https://www.businessinsider.com/inside-story-star-lizard-tony-bloom-2016-2

---

> **結語**：學術文獻給模型上限，開源框架給工程捷徑，Kaunitz/Starlizard 給現實邊界。**T2/T3 策略：`sports-betting` 框架跑走向前回測 → CLV 持續為正 → 小額實盤驗證 → 再談擴張。** 切記：模型準確 ≠ 可投注 edge；**擊敗收盤線、存活於限額下、長期正 ROI** 纔是唯一標準。