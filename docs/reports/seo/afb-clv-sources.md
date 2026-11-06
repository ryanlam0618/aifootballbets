# CLV 追蹤用賠率數據源盤點 (afb-clv-sources)

> 產出時間: 2026-10-31 | 用途: Layer 2 T5 pipeline 每日 odds 快照累積 → T10 CLV 裁決
> 格式: 純文字 + emoji 分組，每源附 link + 價錢 + 覆蓋說明

---

## 🆓 一、免費源

### 1️⃣ football-data.co.uk ⭐ 歷史回填首選
- 🔗 https://www.football-data.co.uk/data.php
- 💰 免費（CSV/Excel 直接下載）
- 📊 覆蓋：歐洲主流 25+ 聯賽（英超、西甲、德甲、意甲、法甲五大＋次級英冠/英甲等）
- ⏱️ 更新：每週更新一次（非即時）
- 📌 Closing odds：有 — 內含 Bet365、Pinnacle 等多莊收盤賠率欄位（PSCH/PSCD 等 Pinnacle 收盤欄 2019 年後加入）
- 🕰️ 歷史深度：主要聯賽由 1993 年起
- ⚠️ 限制：私人使用許可（private use only），無 API 要自己 parse；俄超等部分聯賽已停更
- 🎯 CLV 適用度：**歷史回填（backfill）最強**，但快照時點只有開盤/收盤兩點，無中途序列

### 2️⃣ the-odds-api（The Odds API）⭐ 前向快照首選（免費層）
- 🔗 https://the-odds-api.com/ | 文檔 https://the-odds-api.com/liveapi/guides/v4/
- 💰 免費層：500 credits/月；付費層由 ~$30/月起（credits 制）
- 📊 覆蓋：足球多聯賽（五大＋次級＋部分亞洲），一次請求回傳多莊即時+未來賽事賠率
- ⏱️ 更新：視乎計劃，免費層 1 req 隔 ~幾分鐘可用
- 📌 Closing odds：無原生 closing 概念 — 要自己每日 cron 快照累積，臨開賽最後一次 = 你的 closing
- 🕰️ 歷史回填：無（免費層無歷史；付費有 limited historical）
- ⚠️ 限制：credits 按請求×市場×莊家數計；500/月只夠低頻快照（例如每聯賽每日 1-2 次）
- 🎯 CLV 適用度：**T5 前向快照主力**（免費層起步，量大了升級）

### 3️⃣ OddsPortal + OddsHarvester（爬蟲方案）
- 🔗 OddsPortal: https://www.oddsportal.com/ | 爬蟲: https://github.com/jordantete/OddsHarvester
- 💰 免費（開源爬蟲，Selenium-based）
- 📊 覆蓋：全球極廣（OddsPortal 本身係最大賠率比較站，含亞洲聯賽）
- ⏱️ 更新：站內即時；爬蟲批次拉取
- 📌 Closing odds：有 — 每場有開盤→收盤完整序列（多莊、多時點）
- 🕰️ 歷史回填：**極強** — 可以補返多年歷史賠率序列
- ⚠️ 限制：無官方 API，爬蟲有 ToS 風險、結構變動會 broken、要節流（勿猛打）
- 🎯 CLV 適用度：**歷史序列回填最強**（比 football-data 更細時點），工程維護成本較高

### 4️⃣ Betfair Historical Data（交易所數據）
- 🔗 https://developer.betfair.com/ | 下載說明 https://support.developer.betfair.com/hc/en-us/articles/360000402211
- 💰 Basic 數據部分免費/平價，Advanced/Pro 按量收費
- 📊 覆蓋：全球交易所掛牌賽事
- ⏱️ 更新：歷史檔案按月/日打包
- 📌 Closing odds：有 — 時間戳記完整交易所盤口（最真實嘅 market consensus）
- ⚠️ 限制：需要 Betfair 帳戶；部分地區（含香港）交易所存取受限；檔案大
- 🎯 CLV 適用度：**驗證級**（如果買到，係最乾淨嘅 closing benchmark），但存取門檻高

### 5️⃣ Pinnacle（銳利線參考）
- ⚠️ **Pinnacle 已於 2025 關閉自家公開 API**（來源：sportsapis.dev 2026 目錄）
- 現在要 Pinnacle 數據只有三條路：① football-data.co.uk 免費 CSV 內 Pinnacle 收盤欄 ② 第三方聚合 API（見付費節） ③ 自己抓網頁（不建議）
- 🎯 CLV 適用度：Pinnacle closing 仍係 CLV benchmark 金標準，但官方程式化存取已死

---

## 💰 二、付費源

### 1️⃣ BetsAPI
- 🔗 https://betsapi.com/docs/pricing.html
- 💰 Bet365 API $150/月（3,600 req/hr）；BWin API $100/月；Soccer API 單運動包有平啲選項；試用包有（價錢遞增機制）
- 📊 覆蓋：Bet365 全盤口（Inplay + Prematch）、多莊
- 📌 Closing odds：有 prematch odds 序列，可自己累積 closing
- 🕰️ 歷史：有 finished events 數據，深度有限
- ✅ API 品質：RESTful、文檔齊、社群大；❌ 缺點：逐莊逐包計錢，多莊成本疊加快

### 2️⃣ OddsJam
- 🔗 https://oddsjam.com/subscribe
- 💰 $39–$999/月 分層訂閱（2026 評測數據；年付慳 20-30%）
- 📊 覆蓋：100+ 博彩公司，主要美國市場，足球國際盤都有
- 📌 定位：**+EV 尋寶工具為主，唔係 raw data API**（API 另議價）
- 🎯 CLV 適用度：適合想直接攞 +EV 訊號嘅玩家，唔適合自己起 pipeline 嘅團隊

### 3️⃣ OddsPapi
- 🔗 https://oddspapi.io/
- 💰 免費計劃（基礎功能+歷史數據）→ 客製化付費
- 📊 覆蓋：300+ 莊家
- 📌 Closing odds：有 closing + 公眾投注百分比；歷史收盤線有 backfill 數據庫（260 萬+ lines 級別，按運動）
- 🎯 CLV 適用度：中間檔選擇，免費層可試水溫

### 4️⃣ odds-api.io
- 🔗 https://odds-api.io/
- 💰 訂閱制（官網有免費試用；具體按量）
- 📊 覆蓋：450+ 莊家，pre-match + live + 歷史統一 JSON
- 📌 Closing odds：有 history 端點（含收盤）
- ✅ REST + WebSocket，工程整合容易

### 5️⃣ TheRundown
- 🔗 https://therundown.io/
- 💰 訂閱制（plans 內含 opening/closing lines 歷史）
- 📊 覆蓋：主流美式+國際盤
- 📌 Closing odds：計劃內含 open/close 歷史窗口
- ⚠️ 主要美國市場導向，足球次級聯賽覆蓋待確認

### 6️⃣ Owls Insight / theoddsapi.com 等新興聚合
- 🔗 https://owlsinsight.com/docs | https://theoddsapi.com/faq
- 💰 訂閱制
- 📌 賣點：Pinnacle-anchored edge detection、closing line snapshots、歷史赔率檔案庫
- 🎯 CLV 適用度：專為 CLV/edge 場景設計嘅新興源，值得索取報價

---

## 🎯 三、推薦組合

### 方案 A：慳錢方案（$0–30/月）🟢 建議 T5 起步用
1. **歷史回填**：football-data.co.uk CSV（開盤+收盤兩點，22+ 聯賽，1993 起）→ 一次過補齊歷史 CLV 基線
2. **歷史序列**（如需要多時點）：OddsHarvester 批次爬 OddsPortal（節流：每請求隔 3-5 秒，僅一次性回填）
3. **前向快照**：the-odds-api 免費層 500 credits/月 → 每日 1 次 cron 拍五大聯賽快照（credits 用喺臨場 2-4 小時嗰下最值）
4. **Closing 補捉**：開賽前 30 分鐘再拍一次 = 我哋自己定義嘅 closing
- 📏 成本：$0；瓶頸：快照時點稀疏（每日 1-2 個）、無亞洲細聯賽

### 方案 B：全面方案（~$100–200/月）🔵 T5 成熟後升級
1. **前向快照主力**：the-odds-api 付費層（$30-50/月）或 odds-api.io（多莊+WebSocket）→ 每小時快照
2. **Bet365 深度盤口**：BetsAPI Bet365 包 $150/月（如需要細分市場：角球/黃牌/入球球員）
3. **銳利線驗證**：Pinnacle 收盤經聚合 API 攞（Owls Insight / theoddsapi.com 報價）
4. **Exchange benchmark**（可選）：Betfair Historical Data 買基本包驗證 closing 準確度
- 📏 成本：$180-250/月；覆蓋：五大+次級+亞洲主流，多時點序列完整

### 📌 對 T5/T10 pipeline 嘅具體建議
1. **CLV 定義要鎖死**：closing = 開賽前最後一次快照（方案 A 自訂）或聚合源官方 closing 欄（方案 B）
2. **去保證金**：收盤賠率要先 de-vig（如 overround normalize）先計 CLV，參考 howprosbet 方法
3. **快照 schema**：每場至少存 {match_id, bookmaker, market, odds, snapshot_ts, is_closing} 四欄，方便 T10 重算
4. **亞洲聯賽缺口**：免費源覆蓋弱，若 T5 目標含亞洲盤，方案 B 嘅 odds-api.io/BetsAPI 係必要升級
5. **爬蟲風險**：OddsPortal 爬蟲僅作一次性回填，日常 pipeline 唔好依賴（結構變動即斷）

---

## 📚 來源清單
1. football-data.co.uk — https://www.football-data.co.uk/data.php（2026-10 查證）
2. The Odds API — https://the-odds-api.com/ + V4 docs（免費 500 credits/月，Reddit r/algobetting 2024-10-30 佐證）
3. OddsHarvester — https://github.com/jordantete/OddsHarvester
4. Betfair Historical Data — https://support.developer.betfair.com/hc/en-us/articles/360000402211
5. BetsAPI 定價 — https://betsapi.com/docs/pricing.html（Bet365 $150/mo；Reddit 2026-04-30 佐證）
6. OddsJam 定價 — https://oddsjam.com/subscribe（$39-999/mo，mrsupertips 2026 評測）
7. OddsPapi — https://oddspapi.io/（300+ 莊，免費層有）
8. odds-api.io — https://odds-api.io/（450+ 莊）
9. TheRundown 條款 — https://therundown.io/terms-and-privacy（2026-09-08：open/close 歷史含於計劃）
10. Pinnacle API 狀態 — https://sportsapis.dev/（2026 目錄：Pinnacle 2025 關閉公開 API）
11. Owls Insight — https://owlsinsight.com/docs（歷史 closing lines backfill）
12. sportsdatastack 對 football-data 評述 — https://sportsdatastack.com/tools/football-data-co-uk/（2026-10-18）

> **結語**：起步用方案 A（$0）：football-data 補歷史 + the-odds-api 免費層拍前向快照；T5 跑順、T10 要多時點序列先升方案 B。核心原則：**closing 賠率係 CLV 嘅北極星，快照時點密度決定 T10 裁決嘅可信度。**