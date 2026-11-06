# 20261105 — SLUGFIX：OddsPortal 聯賽 slug 修正（afB-ODDSH-COVERAGE 後續）

## 結論

之前 coverage verify 報告嘅 11 個「UNSUPPORTED」**大部分係假陰性** — 根本唔係 OddsPortal 冇數據，係兩個工具層問題：

1. **CLI 白名單缺漏**：oddsharvester `SPORTS_LEAGUES_URLS_MAPPING` 冇收錄呢啲 slug，`historic` CLI 直接 reject（`Invalid league(s) for football`），probe 根本未去到 OddsPortal。
2. **Slug 前綴錯誤**：coverage_verify 用嘅 `uefa-*` / `europe-*` / `asia-*` 前綴版本唔係白名單 key；正確 key 係**無前綴**（`champions-league`、`europa-league`、`conference-league`）。
3. **Season 格式錯誤**：CSL / AFC CL / AFC Cup 係**曆年制**（用 `2023` 而非 `2023-2024`）。

## 修復內容（commit `39e709c`，已 push）

- `src/oddsharvester/utils/sport_league_constants.py`：白名單 +9 entries（england-efl-cup、japan-emperors-cup、japan-j-league-cup、australia-australia-cup、china-chinese-fa-cup、afc-champions-league-2、afc-champions-league-elite、afc-cup；全部 URL 經 HTTP 200 驗證）
- `scripts/coverage_verify.py`：SLUG_CANDIDATES 全部改用 probe-verified slugs；CALENDAR_YEAR_CUPS 加 CSL / AFC CL / ACL Two / J.League Cup

## Probe 驗證結果（links-only，`data/slugfix/`）

| Competition | Slug × Season | Links | 判定 |
|---|---|---|---|
| UCL | champions-league 2022-2023 | **161** | ✅ 支援（前綴錯誤翻案） |
| UEL | europa-league 2018-2019 | **373** | ✅ 支援（前綴錯誤翻案） |
| UECL | conference-league 2021-2022 | **255** | ✅ 支援（前綴+season 錯誤：UECL 2021 先創立） |
| EFL Cup | england-efl-cup 2020-2021 | **93** | ✅ 支援（白名單 patch） |
| Chinese Super League | china-super-league 2023 / 2024 | **244 / 245** | ✅ 支援（曆年制） |
| AFC Champions League | afc-champions-league 2022 | **140** | ✅ 支援（曆年制） |
| AFC CL Two（歷史） | afc-cup 2022（舊名） | **66** | ✅ 支援（舊名+曆年制） |
| Emperor's Cup | japan-emperors-cup 2016 | **57** | ✅ 支援（白名單 patch） |
| Australia Cup | australia-australia-cup 2022 | **34** | ✅ 支援（白名單 patch；2019 無數據） |
| Ligue 1 | france-ligue-1 2016-2017 | **390** | ✅ 復活（之前 timeout 係暫時性） |
| J.League Cup | japan-j-league-cup 2017 / 2018 | 0 / 0 | ⚠️ slug 有效、該兩季無數據 |
| Chinese FA Cup | china-chinese-fa-cup 2017 / 2024 | 0 / 0 | ⚠️ slug 有效、該兩季無數據 |
| AFC CL Elite | afc-champions-league-elite 2023 / 2024-2025 | 0 / 0 | ⚠️ slug 有效、無數據（需再查 season selector） |

## 方法

1. 抓 `oddsportal.com/sitemap/tournament.xml`（679 條 URL）做權威 slug 對照
2. `curl` HTTP status 驗證 9 個候選 URL（全部 200/301）
3. oddsharvester `historic --links-only` probes（headless browser），共 17 個 probe，產物喺 `data/slugfix/`

## 備註

- sitemap 冇列 Emperor's Cup 等盃賽 — sitemap 只列有未來賽程嘅賽事，唔代表歷史頁面唔存在（curl 200 證實）
- `playwright_manager.py` 有一段未 commit 嘅 OH_PROFILE_DIR override（CLV-BACKFILL concurrency 用，非本 task 產物，未動）
- coverage_verify `state.json` 仍記錄舊 unsupported 狀態 — 下次跑會按新 candidates 重 probe（state 需清走相關 leagues 或直接重跑）

## 下一步（Phase 2）

- coverage verify 重跑（新 slugs + 正確 season 格式）→ 補採 UCL/UEL/UECL/EFL Cup/CSL/AFC 等賠率數據
- CLV-BACKFILL resume：爬蟲產物 + `INSERT IGNORE` 冪等寫入
