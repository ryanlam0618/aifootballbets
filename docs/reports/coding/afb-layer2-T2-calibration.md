🧪 LAYER 2 T2 — 校準 + 選注邏輯 + per-league HA + 盃賽降權（before/after 對比）
任務：afb-layer2-T2-calibration
日期：2026-10-30 ｜ 執行：Forge（coding agent）
Repo：aifootballbets @ main，commit 23c6256（已 push origin/main ✓）
基線：T1 backtest（ead6fac）

═══════════════════════════════
⚡ 誠實總結（先講結論）
═══════════════════════════════

1️⃣ ①校準：temperature scaling 係唯一有實際改善嘅組件 — test 期 log-loss 1.0448 → 1.0381（−0.0067）。isotonic 喺呢個數據上過擬合（1.0662，更差），唔建議用。
2️⃣ ②選注：**所有變體 ROI 都係負數**（raw −4.1%~−0.3%、校準後 −4.6%~−4.0%）— 校準後都冇市場 edge。即係話：唔好攞呢個模型嘅概率去真金落注。
3️⃣ ③per-league HA：24 個聯賽各自 HA（shrink 200），整體 log-loss 1.0379 → 1.0369 — 邊際改善，唔係答案。焦點聯賽（A-League/J1/AFC CL Two）改善極微。
4️⃣ ④盃賽降權：冇益 — cups_excluded 1.0417（+0.004 更差）、cups×0.5 1.0418（+0.004 更差）。盃賽數據都有資訊價值，剷走反而傷。
5️⃣ 最大嘅真發現係③入面：**盃賽嘅主場優勢遠高於聯賽**（Emperor's Cup +0.518、EFL Cup +0.409、Coppa Italia +0.388 vs 聯賽約 +0.25）— 呢個係可以落去 T3 嘅方向。

═══════════════════════════════
① 校準（as-of 零洩漏：calib 窗 7,804 場 → 2024-12-07；test 窗 7,805 場）
═══════════════════════════════

方法（三種，全部 stdlib 實現）：
• Isotonic（PAVA per-class + trio renormalise）
• Temperature scaling（3-class logit/T，NLL fit；T>1 攤平）
• Grouped temperature（cup / league / continental 三組各自 T）

Test 期結果（n=7,805）：
• before（raw）：ll=1.0448
• after isotonic：ll=1.0662 ❌ 更差（過擬合）
• after temperature：ll=**1.0381** ✅ 改善 −0.0067
• after grouped temperature：ll=1.0394（跟 plain temp 差唔多，無額外益處）

溫度效應細看：極端桶確實被攤平 — 例如 [0.8–0.9) 桶校準前 pred 0.837/real 0.659，校準後該桶重新組成，log-loss 改善主要嚟自高概率端收斂。中段（0.2–0.5）本來已經校準得好好，溫度對佢哋影響細。

Fit 出嚟嘅 T > 1（模型確認過度自信）— 同 T1 校準桶發現一致。

═══════════════════════════════
② 選注邏輯：edge vs de-vig market（test 期 3,818 場有賠率子集）
═══════════════════════════════

方法：edge = 模型概率（raw / temperature 校準後）− 市場 de-vig 概率；edge ≥ 門檻先落注；flat stake 1 注；用市場平均小數賠率結算。

閾值 0.03：raw 3,365 注 ROI −4.10% ｜ temp 3,330 注 ROI −4.01%
閾值 0.05：raw 2,972 注 ROI −3.37% ｜ temp 2,856 注 ROI −3.85%
閾值 0.10：raw 2,058 注 ROI −0.34% ｜ temp 1,888 注 ROI −4.64%

誠實結論：**冇一個變體、冇一個閾值係正 ROI。** 校準減少咗注數（溫度攤平令高 edge 注更少）但冇扭轉負期望。th=0.10 raw −0.34% 係最接近打和，但嗰個係 raw（未校準）模型 — 冇理由信佢可以維持。

Edge bucket 分佈（after_temperature）都記錄咗喺報告 JSON。

═══════════════════════════════
③ Per-league home advantage（24 聯賽，shrink 200 場等效）
═══════════════════════════════

整體 log-loss：1.0379 → 1.0369（−0.001，邊際）

焦點聯賽（Duncan 點名）：
• A-League Men（n=517）：ll 1.0934 → 1.0908（微改善）、hit 0.4004 → 0.3985
• J1 League（n=1,037）：ll 1.0913 → 1.0891（微改善）、hit 0.4253 → 0.4147
• AFC Champions League Two（n=406）：ll 1.1966 → 1.1950（幾乎無變）
• K League 1（n=570）：ll 1.1168 → 1.1123（微改善）
• Chinese Super League（n=633）：ll 1.0277 → 1.0307（微惡化）

最大贏家全部係盃賽：Emperor's Cup ll −0.058（n=237）、Coppa Italia −0.031、Australia Cup −0.006；最大輸家：Chinese FA Cup +0.044、Coupe de France +0.025、J.League Cup +0.017。

🆕 真發現：**盃賽 HA 系統性高過聯賽** — Emperor's Cup +0.518、EFL Cup +0.409、Coppa Italia +0.388、Chinese FA Cup +0.384、Coupe de France +0.375（聯賽約 +0.25 pooled）。可能反映：低輪次強弱懸殊對戰 + 主場抽籤結構。呢個對 T3（盃賽專門建模）係有價值嘅訊號。

═══════════════════════════════
④ 盃賽降權（整體 val log-loss）
═══════════════════════════════

• baseline：1.0379
• cups_excluded（10 個國內盃賽全剔除）：1.0417（**+0.0038 更差**）
• cups_weight_0_5（盃賽半權）：1.0418（**+0.0039 更差**）

誠實結論：降權/剔除冇好處。盃賽場次（約 6,600 場，12.7%）有佢哋自己嘅資訊價值（尤其配合③嘅 per-league HA 之後），整體剷走反而令聯賽隊伍參數估計更差。呢條路線可以收檔。

═══════════════════════════════
✅ 驗證
═══════════════════════════════

• pytest 全套：111 passed / 1 failed（唯一 fail 係既有 test_paper_repro_7d；baseline 99 保持 ✓，新增 12 個 T2 測試全綠）
  – PAVA 單調性 + 完美數據恢復
  – temperature T=1 恆等、T>1 攤平、過度自信數據上 NLL 必改善
  – grouped fit（cup/league）
  – flat-stake ROI 數學（已知案例）、threshold 過濾、edge bucket（含 fp 精度防護）
  – per-league HA：兩聯賽合成數據分別收斂、shrink 方向正確、global 落喺中間
  – league_weights 降權方向 + gauge fix
• 實跑：T2 全流程（4 個 holdout fits + 校準 + 市場子集查詢 + 模擬）約 15 分鐘
• Commit 23c6256 已 push origin/main ✓

═══════════════════════════════
🧭 對 T3 嘅建議
═══════════════════════════════

1️⃣ 盃賽專門建模：per-league HA 已證明盃賽 HA 顯著更高 — 下一步可以盃賽/聯賽分開 fit 攻防參數，或者加「盃賽輪次」特徵
2️⃣ 校準採用 temperature（放棄 isotonic）— 每季 as-of 重 fit（成本極低，單參數）
3️⃣ 市場 edge 路線重估：模型概率單獨無 edge — 結合方向應該係「模型 vs 市場分歧大嘅場先有訊號」（agree rate 0.40 即六成分歧場），或者直接用 market prior + model residual 做 blend
4️⃣ CLV 追蹤啟動：需要 closing odds 時間序列（Layer 1 嘅 afb_odds_snapshots 要開始累積）
5️⃣ 弱聯賽（A-League 0.40、AFC CL Two 0.41）單獨診斷：係數據質素定係真係不可預測

═══════════════════════════════
📎 產出清單
═══════════════════════════════

• Commit 23c6256（已 push）：models/calibration.py、models/dc_model.py（additive）、scripts/backtest_t2.py、scripts/backtest_dc.py（league 帶入 + 分數賠率解析 + isfinite 防護）、tests/test_t2_calibration.py
• 報告：reports/backtest_dc_t2_report.txt→md + .json（①②③④ 各自貢獻齊）
• 本 artifact：subagent_results/afb-layer2-T2-calibration.md（+ .json）
