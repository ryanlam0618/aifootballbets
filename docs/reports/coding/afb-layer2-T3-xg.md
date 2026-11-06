⚽ LAYER 2 afb-T3 — 自建 xG 工序（T3a-d：訓練 / 校準 / 填值 / Rolling）
任務：afb-layer2-T3-xg
日期：2026-10-31 ｜ 執行：Forge（coding agent）
Repo：aifootballbets @ main，commits 0bddc1c + ba6ac74（已 push origin/main ✓）

═══════════════════════════════
⚡ 總結（含數據現實修正）
═══════════════════════════════

1️⃣ T3a 自建 xG 模型完成：XGBoost pearson_r **0.870** / MAE 0.0416 vs 官方 xG（LR 對照 0.754 — XGBoost 大勝）。訓練集係 **45,686** shots（official xG + 座標齊備）— ⚠️ dispatch 假設嘅 261,440 係「有 official xG 嘅全部 rows」，但其中约 21.6 萬行冇座標，唔可以訓練座標模型。如實修正範圍。
2️⃣ T3b isotonic 校準完成：對齊官方尺度（calibration slice chronological，零洩漏）；校準後 MAE 0.0420（尺度對齊目的達成，MAE 本身冇改善係預期）。
3️⃣ T3c 填值完成：**41,647** 個「有座標冇官方 xG」嘅 shots 已填校準值 + xg_source='calibrated'；261,476 個官方值標記 xg_source='official'。安全措施：afb_shotmap_xg_backup 表 + xg IS NULL guard（官方值永不覆寫）。
4️⃣ T3d rolling 完成：afb_team_rolling_xg 表 **21,194 team-match rows / 752 隊**（last-10 as-of，嚴格只用賽前數據）。
5️⃣ 誠實覆蓋報告：表級 xG 覆蓋 34.1% → **39.55%**（填後）— **「near 100%」達唔到**：463,365 shots（60.5%）既冇座標又冇官方 xG，唔可填。rolling 覆蓋 21,194 / ~94K team-matches ≈ 22.5%。原因：SofaScore 舊季數據有 xG 冇座標、部分連 xG 都冇。

═══════════════════════════════
🔧 實現細節
═══════════════════════════════

• models/shot_xg.py
  – shot_features()：SofaScore 百分比座標 → 米制距離 + 角度（兩門柱 law of cosines）+ shot_type/situation/body_part one-hot
  – train_shot_xg()：chronological 切分 train(70%)/calib(15%)/test(15%)（唔洗牌 — 時序漂移）；XGBoost（300 trees, depth 6, lr 0.08, hist）+ LinearRegression 對照
  – T3b：isotonic（PAVA）fit 喺 calibration slice（pred → official）
• scripts/build_xg.py（T3a-d orchestration）
  – 安全序列：backup 表 → ALTER ADD xg_source（INFORMATION_SCHEMA 檢查，冪等）→ 官方標記（batched 50K，xg_source IS NULL guard）→ 填值（batched 5K，xg IS NULL guard）→ rolling（DELETE/CREATE — appdb_rw 冇 DROP，修咗一個 DROP 被拒 bug）
  – 驗證查詢：coverage + by_source 全記錄

═══════════════════════════════
📊 實測數字
═══════════════════════════════

T3a 模型質素（held-out test 6,852 shots，官方 xG 均值 0.114）：
• XGBoost raw：MAE 0.04163 / RMSE 0.07484 / pearson_r 0.86938
• 校準後：MAE 0.04203 / pearson_r 0.86806（尺度對齊）
• LR 對照：MAE 0.06349 / pearson_r 0.75372（XGBoost 全面勝出）

T3b isotonic：PAVA breakpoints（pred → official 尺度映射）

T3c 填值（DB 實寫）：
• xg_source 欄：ALTER ADD ✓（INFORMATION_SCHEMA 驗證）
• official 標記：261,476 rows ✓
• calibrated 填值：41,647 rows ✓（IS NULL guard，冪等重跑驗證）

T3d rolling（afb_team_rolling_xg）：
• 21,194 team-match rows / 752 隊 / last-10 as-of
• 覆蓋率 22.5%（team-match 層級）— 誠實修正：「near 100%」只適用於座標可用年代

覆蓋率（全表 766,488 shots）：
• 官方 xG：261,476（34.11%）→ 填後 303,123（**39.55%**）
• xg_source 分佈：official 261,476 / calibrated 41,647 / NULL（無 xG 亦無座標）463,365

═══════════════════════════════
⚠️ 誠實限制（dispatch 假設 vs 數據現實）
═══════════════════════════════

1️⃣ 訓練集 45,686 ≠ 261,440：dispatch 嘅數字係全表 official-xG rows，但 21.6 萬行冇座標（舊季 SofaScore 比xG唔比座標）— 座標模型只可以用有座標嘅 45,686。
2️⃣ 「59% → near 100%」未達成：真實覆蓋 34.1% → 39.55%（shot 級）。463K shots 冇座標冇 xG — 需要額外數據源（例：接 StatsBomb/OpenShotmap 式座標數據）先可以再提升。
3️⃣ Rolling 22.5% team-match 覆蓋：同上原因。滾動值對「有 xG 嘅年代」有效；跨年代比較有系統性低估（無 xG shots 計 0）。
4️⃣ 重跑 retrain 循環性 caveat：正式填值用嘅係第一個乾淨模型（official-only 訓練，r 0.870）；pipeline 重跑時 retrain 會包含自家 calibrated 值（r 0.940 虛高）— 已記錄，正式再訓練應鎖定官方-only 訓練集。
5️⃣ 過程修三個 bug：shotmap 座標欄位係 player_x/player_y（唔係 x/y）、float32 JSON 序列化、verification query 喺 skip-write 模式查唔存在嘅欄。

═══════════════════════════════
✅ 驗證
═══════════════════════════════

• pytest 全套：121 passed / 1 failed（唯一 fail 係既有 test_paper_repro_7d；121 baseline 保持 ✓）
• 實跑：dry-run（skip-db-write）驗證 + 正式全量 run（backup/ALTER/mark/fill/rolling 全鏈路 + 驗證查詢）
• 冪等重跑實證：mark/fill 守衛令第二次 run 正確 no-op
• Commits 0bddc1c + ba6ac74 已 push origin/main ✓

═══════════════════════════════
🧭 對 T6 / 後續嘅建議
═══════════════════════════════

1️⃣ Rolling xG 特徵已可食：afb_team_rolling_xg（rolling_xg_for/against, n_history）— T6 ML view 可以 JOIN
2️⃣ 覆蓋率再提升路線：接外部座標數據源（StatsBomb open / Understat 爬蟲）— 需 Kris 拍板
3️⃣ xg_source 語義文件：xg IS NOT NULL 時先有意義（official=官方值 / calibrated=自建填值）；backfill 新 INSERT 預設 NULL，需補標記（low priority）
4️⃣ Rolling 對 xg 缺失 shots 計 0 嘅系統性低估 — 跨年代比較要注意（同年代相對排名無影響）

═══════════════════════════════
📎 產出清單
═══════════════════════════════

• Commits 0bddc1c + ba6ac74（已 push）：models/shot_xg.py、scripts/build_xg.py
• DB：match_shotmap 加 xg_source 欄、41,647 填值、afb_shotmap_xg_backup 備份表、afb_team_rolling_xg 21,194 行
• 報告：reports/backtest_xg_report.json + .md
• 本 artifact：subagent_results/afb-layer2-T3-xg.md（+ .json）
