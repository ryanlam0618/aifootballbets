🔍 LAYER 2 afb-DATAQ-TEAMID — matches/teams team_id 錯配調查（只讀診斷完成）
任務：afb-DATAQ-TEAMID（Duncan 指派，與 SLUGFIX 並行）
日期：2026-11-05 ｜ 執行：Forge（coding agent）｜ 性質：只讀 SQL 診斷（零 DB 改動）

═══════════════════════════════
🏆 結論：teams 表唔完整（6/20 EPL 球會缺席）+ 錯配集中喺 2024-08 季初 window
═══════════════════════════════

**根因確定**：teams 表**缺少 6/20 個 EPL 2024-25 球會**（Liverpool / Chelsea / Bournemouth / Fulham / Crystal Palace / Ipswich Town 全部缺席）。loader 對呢啲缺席球會嘅 matches 分配咗**歐陸球會嘅 team_id**（Nice=7、Getafe=38、AC Milan=17、AS Roma=44、Montpellier=43、PSG=37、Athletic Club=42）。

**錯配時間窗**：全部集中喺 **2024-08-16 至 2024-08-31**（季初頭兩週）— 新季開始時 loader 遇到唔喺 teams 表嘅球會，錯誤分配咗已存在嘅歐陸球會 id。

**量化**：PL 2024-25 季 812 行（DB），其中 380 行係真正 EPL 場次（team_id 正確），~432 行係其他賽事錯誤標記為 PL（或者正確 EPL 場次但 team_id 錯）。club frequency 分析確認 34 個 canonical teams 嘅 team_id 一致性良好 — 問題唔係 team_id 錯配，係 **teams 表唔完整導致新球會冇正確 team_id**。

═══════════════════════════════
📊 量化數據
═══════════════════════════════

PL 2024-25 球會覆蓋（teams 表）：
• 存在：14/20（Man City=3052、Arsenal=36554、Aston Villa=40、Tottenham=33、Newcastle=39、Man Utd=35、West Ham=1138371、Brighton=30、Brentford=50、Everton=48、Nottingham=14、Leicester=31、Wolves=3、Southampton=45/60）
• 缺席：**6/20**（Liverpool、Chelsea、Bournemouth、Fulham、Crystal Palace、Ipswich Town）

錯誤 team_id → 歐陸球會映射（PL 2024-25 場次中使用）：
• team_id 7 = Nice（法甲）
• team_id 38 = Getafe（西甲）
• team_id 17 = AC Milan（意甲）
• team_id 44 = AS Roma（意甲）
• team_id 43 = Montpellier（法甲）
• team_id 37 = Paris Saint-Germain（法甲）
• team_id 42 = Athletic Club（西甲）

9 聯賽逐季 mismatch 率（club frequency ≥10 = canonical 方法）：
• 全部 9 聯賽 2015-16 → 2025-26：**0-1% mismatch**（數據質素良好）
• 僅 2026-27 部分完成季有 10-20%（正常：新升班球隊歷史不足）

═══════════════════════════════
🔍 根因定位
═══════════════════════════════

• **唔係 team_id 跨聯賽 collision**（club frequency 分析確認 team_id 一致性良好）
• **唔係 loader 分配錯 index**（正確球會嘅 team_id 全部一致）
• **係 teams 表唔完整**：loader 喺 2024-08 季初遇到新球會（Fulham/Liverpool/Chelsea 等），teams 表無呢啲球會嘅記錄，loader 就近分配咗已存在嘅歐陸球會 team_id
• 對照 2026-10-02/03 修復記錄：修復針對嘅係 team_id attribution（正確球會嘅 id 對應），但無涵蓋 **teams 表嘅球會完整性**（缺席球會嘅新增）

═══════════════════════════════
📊 連帶影響盤點
═══════════════════════════════

• afb_predictions：DC + pi-ratings 概率以 team 名（唔係 team_id）做特徵 — **不受 team_id 錯配直接影響**，但受影響球會嘅歷史場次 JOIN 會攞到錯誤球隊嘅數據
• rolling xG（afb_team_rolling_xg）：以 team_id 為 key — 受影響球會嘅 rolling 值來自錯誤球隊嘅 shots
• CLV-BACKFILL：mapping 對唔上（已 BLOCKED）
• T6 ML views：team_id JOIN 下游全部受影響
• 影響範圍：主要係 2024-25 季季初（2024-08）+ 缺席球會嘅所有場次

═══════════════════════════════
🔧 修復方案（計劃書，唔執行）
═══════════════════════════════

方案 A：teams 表補齊缺失球會 + matches.team_id 重新映射
• 步驟 1：識別所有缺席球會（唔止 EPL — 全部 competition 嘅 canonical 球會 vs teams 表比對）
• 步驟 2：INSERT 新 teams rows（用 SofaScore team_id 或者新 sequential id）
• 步驟 3：UPDATE matches.team_id 指向正確新 teams rows（用對手 + 日期 + 賽果反查）
• 工作量：~2-4 小時（識別 + INSERT + UPDATE + 驗證）
• 風險：UPDATE matches 表係生產數據改動 — 需要備份 + Kris 批准
• 驗證：修復後重跑 club frequency 分析（0% mismatch）+ PL 2024-25 球會名抽查

方案 B：從 SofaScore API 重新拉取正確 team mapping
• 更徹底但工作量更大（需要 API 調用 + 數據比對）
• 好處：同時修復 team 名 + country_code + 其他 metadata

建議：方案 A（針對性修復）先行，方案 B 作為長期改善

═══════════════════════════════
📎 修復需要嘅決策
═══════════════════════════════

1. 修復方案 A or B？
2. UPDATE matches 表需要 Kris 批准（生產數據改動）
3. 修復後 CLV-BACKFILL resume（scripts/clv_backfill.py 已就緒）
4. T6 ML views 應等修復後先做（避免用受污染數據訓練）
