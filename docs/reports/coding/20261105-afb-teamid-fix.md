# 20261105 — aifootballbets team_id 修復（TEAMFIX Phase 1 完成）

## 修訂後根因（顛覆之前判斷）

之前兩個假設（「matches.team_id 分配錯誤」/「teams 表缺球會要 INSERT」）**都唔準確**。真正情況：

- **matches 表嘅 team_id 全部正確**（Sofascore 官方口徑：Liverpool=44、Arsenal=42、Man City=17、Chelsea=38…）
- **teams 表有 10 行錯標 rows**：外國球會 row 霸佔咗 EPL 球會嘅 Sofascore id（例如 id 44 寫咗 'AS Roma'，實際 Sofascore 44=Liverpool），令 JOIN 出錯名
- 唔使 INSERT 新球會、唔使 UPDATE matches — **淨係 10 行 teams 改名**就完成修復

## 修復內容（10 行 UPDATE，id 不變）

| team_id | 舊名（錯） | 新名（正確） |
|---|---|---|
| 7 | Nice | Crystal Palace |
| 17 | AC Milan | Manchester City |
| 32 | Luton Town | Ipswich Town |
| 37 | Paris Saint-Germain | West Ham United |
| 38 | Getafe | Chelsea |
| 41 | Cardiff City | Sunderland |
| 42 | Athletic Club | Arsenal |
| 43 | Montpellier | Fulham |
| 44 | AS Roma | Liverpool |
| 60 | Southampton | Bournemouth |

同步更新 slug / short_name / country_code=ENG / city / stadium；`team_type='club'`。

## 證據（三重獨立驗證）

1. **真實賽程反查**：Man Utd vs id43（2024-08-16）= 真實 Man Utd 1-0 Fulham；Brentford vs id7（2024-08-18）= Brentford vs Crystal Palace；Wolves vs id38（2024-08-25）= Wolves vs Chelsea；Man Utd vs id44（2024-09-01）= 0-3 Liverpool；Spurs vs id42（2024-09-15）= NLD 0-1 Arsenal；id17 vs id32（2024-08-24）= Man City 4-1 Ipswich。
2. **歐洲賽歷史完全吻合**：id38 = UEL 18/19 冠 + UECL 24/25 冠 + UCL 缺 16/17、18/19、23/24、24/25（Chelsea 實績）；id42 UCL 缺 17/18–22/23、同期轉打 UEL（Arsenal）；id44 UEL 15/16 入決賽 + UCL 17/18–22/23（Liverpool）；id43/id60 PL 缺 19/20–21/22（Fulham/Bournemouth 降班兩季）；id41 PL 15/16+16/17+25/26（Sunderland 降班九年後返超聯）；id32 PL 淨係 24/25+26/27（Ipswich）。
3. **球員名冊**：id7 = Wharton/Sako（Palace）；id38 = Morata/Rüdiger/Fàbregas/David Luiz/Palmer（全部效力過 Chelsea）；id44 = Lallana（Liverpool）；id37 = Aréola（West Ham）；id60 = Adam Smith（Bournemouth 隊長）；id41 = Patterson/Brobbey（Sunderland）。

## 驗證結果（修復後）

- PL 2023-24：20/20 正確英格蘭球會 ✓（Leicester 31、Sheffield Utd 15、Luton 72 名稱正確）
- PL 2024-25：20/20 正確英格蘭球會 ✓
- 2025-02-15 該輪（之前全錯亂）：Aston Villa 1-1 Ipswich、Crystal Palace 1-2 Everton、**Fulham 2-1 Nottingham Forest**、Leicester 0-2 Arsenal、Man City 4-0 Newcastle、Southampton 1-3 Bournemouth、West Ham 0-1 Brentford — 全部真實賽程 + 真實比分 ✓
- Ligue 1 / La Liga / Serie A 場次（用 1644/1661/2702 等正確 id）零受影響 ✓

## 備份（修復前已造）

- in-DB：`afb_backup_teams_20261105`（3,740 rows）、`afb_backup_matches_20261105`（52,154 rows）
- CSV：`backups/teamfix-20261105/teams.csv`、`backups/teamfix-20261105/matches.csv`

## 開放項目（未做，需後續決定）

1. **`scripts/clv_backfill.py` 已唔喺工作樹**（從未 commit，git log --all 無紀錄）— Phase 2 CLV-BACKFILL resume 前要恢復/重建此腳本。DB 側嘅阻礙（球會名缺失）已解除。
2. **teams 表垃圾重複 rows**：36554 'Arsenal'、1138371 'West Ham United'、6070/530631 'PSG'、313716/335923 'Montpellier'、47105 'Luton Town'、1923/22011 'Getafe'、2825/37966 'Athletic Club'、1974 'AS Roma' — 部分零引用（36554/1138371 確認 0 uses），屬化妝品級清理。
3. **id 3052 'Manchester City'**：117 場 UCL/UEL/UECL 引用，但名冊似 Benfica/土耳其球員混合，UCL 樣本賽程（如 2024-07-23 Lugano vs 3052）唔對應真實 Man City 賽程 — 需 ground truth 核實真正身份。
4. **players.current_team_id 局部污染**（id 40/45 名冊出現無關球員）— 另立 task。
5. **id 41 零星盃賽場次疑點**：FA Cup 部分引用 41 嘅場次名冊含 Cardiff 球員 — 數量極少，需逐場核實係咪 Cardiff 被誤標。
6. **Branch 清理完成**：用戶要求刪嘅 4 條舊 remote branch（clawbot/clawbot_v2/desktop/openclaw_v3）**已經唔存在喺 remote**（遠早於今次清理已被刪）；本地殘留 clawbot_v3（已 merge 入 main，c1769f1）已刪除本地 copy，remote copy 保留。

## 附註

- 本 task 執行前 Phase 1 舊方案（INSERT 缺失球會 + UPDATE matches.team_id）**唔再需要** — 舊判斷基於不完整嘅 EPL_CLUBS 名單。
- artifact 無任何 credential / token / chat id。
