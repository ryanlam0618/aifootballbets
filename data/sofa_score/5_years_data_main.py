# -*- coding: utf-8 -*-
"""
五大聯賽 + 日本J1 + 韓國K聯賽 + 澳洲A聯賽 過往五個賽季數據爬蟲
包括這些球隊參與的盃賽數據（歐冠、歐聯、足總杯等）
帶重試機制和定期保存功能
"""

import datetime
import os
import csv
import time
import json
from DrissionPage import ChromiumPage, ChromiumOptions

# 用於去重的已處理比賽ID集合
processed_event_ids = set()


# 聯賽配置
LEAGUE_CONFIG = {
    # 五大聯賽 (使用 API 實際返回的名稱 + 國家)
    'Premier League': {'country': 'England', 'id': 'PL'},
    'LaLiga': {'country': 'Spain', 'id': 'PD'},
    'Serie A': {'country': 'Italy', 'id': 'SA'},
    'Bundesliga': {'country': 'Germany', 'id': 'BL1'},
    'Ligue 1': {'country': 'France', 'id': 'FL1'},
    # 亞洲聯賽
    'J1 League': {'country': 'Japan', 'id': 'J1'},
    'K League 1': {'country': 'South Korea', 'id': 'K1'},
    'A-League Men': {'country': 'Australia', 'id': 'A-League'},
}

# 盃賽配置 (使用 API 實際返回的名稱)
CUP_CONFIG = {
    'UEFA Champions League': {'country': 'Europe', 'id': 'CL'},
    'UEFA Europa League': {'country': 'Europe', 'id': 'EL'},
    'UEFA Conference League': {'country': 'Europe', 'id': 'ECL'},
    'FA Cup': {'country': 'England', 'id': 'FAC'},
    'EFL Cup': {'country': 'England', 'id': 'ELC'},
    'Copa del Rey': {'country': 'Spain', 'id': 'CDR'},
    'Coppa Italia': {'country': 'Italy', 'id': 'CI'},
    'DFB Pokal': {'country': 'Germany', 'id': 'DFB'},  # API 返回的是 DFB Pokal
    'Coupe de France': {'country': 'France', 'id': 'CF'},
    'Community Shield': {'country': 'England', 'id': 'CS'},  # 可能的名稱
    'Supercopa de España': {'country': 'Spain', 'id': 'SC'},
    'Supercoppa Italiana': {'country': 'Italy', 'id': 'SCI'},
    'Trophée des Champions': {'country': 'France', 'id': 'TDC'},
}

# 獲取過去5個賽季
def get_season_list():
    """生成賽季列表 (2015/2016 到 2025/2026)"""
    # 固定賽季列表：從 2015/2016 賽季到 2025/2026 賽季
    seasons = [
        "2015/2016",
        "2016/2017", 
        "2017/2018",
        "2018/2019",
        "2019/2020",
        "2020/2021",
        "2021/2022",
        "2022/2023",
        "2023/2024",
        "2024/2025",
        "2025/2026",
    ]
    
    return seasons


def parse_api_events(data):
    """解析 API 返回的比賽數據"""
    if 'events' not in data:
        return []
    
    matches = []
    for event in data['events']:
        try:
            # 跳過尚未開始的比賽 (status code 100 = finished/ended)
            status = event.get('status', {})
            if status.get('code') != 100:
                continue
            
            # 獲取聯賽信息
            tournament = event.get('tournament', {})
            tournament_name = tournament.get('name', '')
            category = tournament.get('category', {})
            category_name = category.get('name', '')
            
            # 獲取球隊信息
            home_team = event.get('homeTeam', {}).get('name', '')
            away_team = event.get('awayTeam', {}).get('name', '')
            
            if not home_team or not away_team:
                continue
            
            # 獲取比賽日期時間 (使用 startTimestamp 轉換為日期)
            start_timestamp = event.get('startTimestamp', '')
            if start_timestamp:
                match_date = datetime.datetime.fromtimestamp(start_timestamp).strftime('%Y-%m-%d')
            else:
                match_date = ''
            
            match_info = {
                'event_id': event.get('id'),
                'match_date': match_date,
                'tournament_name': tournament_name,
                'category_name': category_name,
                'home_team': home_team,
                'away_team': away_team,
            }
            matches.append(match_info)
            
        except Exception as e:
            continue
    
    return matches


def extract_statistics(data, match_info):
    """提取比賽統計數據"""
    if 'error' in data:
        return []
    
    if 'statistics' not in data or not data['statistics']:
        return []
    
    # 只提取 ALL period 的数据（与 main.py 一致）
    all_period_data = None
    for period in data['statistics']:
        if period['period'] == 'ALL':
            all_period_data = period
            break
    
    if not all_period_data:
        return []
    
    rows = []
    target_groups = ['Match overview', 'Shots', 'Attack', 'Passes', 'Duels', 'Defending', 'Goalkeeping']
    
    for group in all_period_data.get('groups', []):
        group_name = group.get('groupName', '')
        
        if group_name not in target_groups:
            continue
        
        for item in group.get('statisticsItems', []):
            stat_name = item.get('name', '')
            stat_key = item.get('key', '')
            home_value = item.get('homeValue', '')
            away_value = item.get('awayValue', '')
            home_display = item.get('home', '')
            away_display = item.get('away', '')
            
            row = {
                'event_id': match_info['event_id'],
                'match_date': match_info['match_date'],
                'tournament_name': match_info['tournament_name'],
                'category_name': match_info['category_name'],
                'home_team': match_info['home_team'],
                'away_team': match_info['away_team'],
                'group': group_name,
                'stat_name': stat_name,
                'stat_key': stat_key,
                'home_display': home_display,
                'away_display': away_display,
                'home_value': home_value,
                'away_value': away_value,
            }
            rows.append(row)
    
    return rows


def extract_shotmap(data, match_info):
    """提取球員射門數據"""
    if 'error' in data:
        return []
    
    if 'shotmap' not in data or not data['shotmap']:
        return []
    
    rows = []
    
    for shot in data['shotmap']:
        try:
            player_name = shot.get('player', {}).get('name', '')
            player_id = shot.get('player', {}).get('id', '')
            
            time_minute = shot.get('time', '')
            added_time = shot.get('addedTime', '')
            if added_time:
                time_display = f"{time_minute}+{added_time}"
            else:
                time_display = str(time_minute)
            
            xg = shot.get('xg', '')
            xgot = shot.get('xgot', '')
            outcome = shot.get('shotType', '')
            situation = shot.get('situation', '')
            shot_type = shot.get('bodyPart', '')
            goal_zone = shot.get('goalMouthLocation', '')
            
            # X, Y 坐標
            player_coords = shot.get('playerCoordinates', {})
            x_coord = player_coords.get('x', '') if player_coords else ''
            y_coord = player_coords.get('y', '') if player_coords else ''
            
            row = {
                'event_id': match_info['event_id'],
                'match_date': match_info['match_date'],
                'tournament_name': match_info['tournament_name'],
                'category_name': match_info['category_name'],
                'home_team': match_info['home_team'],
                'away_team': match_info['away_team'],
                'player_name': player_name,
                'player_id': player_id,
                'time_minute': time_display,
                'xg': round(xg, 2) if xg else '',
                'xgot': round(xgot, 2) if xgot else '-',
                'outcome': outcome,
                'situation': situation,
                'shot_type': shot_type,
                'goal_zone': goal_zone if goal_zone else '-',
                'x': round(x_coord, 2) if x_coord else '',
                'y': round(y_coord, 2) if y_coord else '',
                'is_home': shot.get('isHome', '')
            }
            rows.append(row)
            
        except Exception as e:
            continue
    
    return rows


def detail(match_info, all_rows):
    """獲取單場比賽的詳細統計數據"""
    event_id = match_info['event_id']
    url = f'https://www.sofascore.com/api/v1/event/{event_id}/statistics'
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            page_tab.get(url)
            page_tab.wait(0.5)
            data = page_tab.json
            
            rows = extract_statistics(data, match_info)
            if rows:
                all_rows.extend(rows)
                print(f"    统计: {len(rows)} 條")  # 添加调试输出
            else:
                print(f"    无统计或提取失败")  # 添加调试输出
            return True  # 成功
            
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(2)  # 等待2秒後重試
                continue
            else:
                # 最後一次嘗試失敗，嘗試重新連接瀏覽器
                try:
                    reconnect_browser()
                except:
                    pass
    return False


def detail_shotmap(match_info, all_shot_rows):
    """獲取單場比賽的射門數據"""
    event_id = match_info['event_id']
    url = f'https://www.sofascore.com/api/v1/event/{event_id}/shotmap'
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            page_tab.get(url)
            page_tab.wait(0.5)
            data = page_tab.json
            
            rows = extract_shotmap(data, match_info)
            if rows:
                all_shot_rows.extend(rows)
                print(f"    射门: {len(rows)} 條")  # 添加调试输出
            return True  # 成功
            
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(2)  # 等待2秒後重試
                continue
            else:
                # 最後一次嘗試失敗，嘗試重新連接瀏覽器
                try:
                    reconnect_browser()
                except:
                    pass
    return False


def reconnect_browser():
    """重新連接瀏覽器"""
    global page, page_tab
    print("  嘗試重新連接瀏覽器...")
    try:
        page_tab.close()
    except:
        pass
    try:
        page.quit()
    except:
        pass
    
    # 重新初始化瀏覽器
    co = ChromiumOptions().headless()
    co.set_browser_path(r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe')
    page = ChromiumPage(co)
    page_tab = page.new_tab()
    time.sleep(2)
    print("  瀏覽器重新連接成功")


def save_to_csv(rows, filename):
    """保存數據到 CSV"""
    if not rows:
        return
    
    fieldnames = ['match_date', 'event_id', 'tournament_name', 'category_name', 'home_team', 'away_team', 
                  'group', 'stat_name', 'stat_key', 'home_display', 'away_display', 
                  'home_value', 'away_value']
    
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def save_shotmap_to_csv(rows, filename):
    """保存射門數據到 CSV"""
    if not rows:
        return
    
    fieldnames = ['match_date', 'event_id', 'tournament_name', 'category_name', 'home_team', 'away_team', 
                  'player_name', 'player_id', 'time_minute', 'xg', 'xgot', 'outcome', 
                  'situation', 'shot_type', 'goal_zone', 'x', 'y', 'is_home']
    
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def get_season_dates(season_str):
    """根據賽季字符串獲取開始和結束日期"""
    # 賽季格式: 2021/2022
    start_year = int(season_str.split('/')[0])
    end_year = start_year + 1
    
    # 賽季通常是從8月到次年5月
    start_date = f"{start_year}-08-01"
    end_date = f"{end_year}-05-31"
    
    # 特殊處理：如果結束日期超過 2026-02-17，則使用 2026-02-17
    if end_date > "2026-02-17":
        end_date = "2026-02-17"
    
    return start_date, end_date


def crawl_league(league_name, season_str, all_rows, all_shot_rows, data_dir):
    """爬取特定聯賽某賽季的數據"""
    start_date, end_date = get_season_dates(season_str)
    
    print(f"\n{'='*60}")
    print(f"正在爬取: {league_name} - {season_str}")
    print(f"日期範圍: {start_date} ~ {end_date}")
    print(f"{'='*60}")
    
    # 創建該聯賽獨立的臨時數據列表
    league_rows = []
    league_shot_rows = []
    
    # 生成日期範圍
    start_dt = datetime.datetime.strptime(start_date, '%Y-%m-%d')
    end_dt = datetime.datetime.strptime(end_date, '%Y-%m-%d')
    
    date_range = []
    current_dt = start_dt
    while current_dt <= end_dt:
        date_range.append(current_dt.strftime('%Y-%m-%d'))
        current_dt += datetime.timedelta(days=1)
    
    save_interval = 30  # 每30天保存一次
    
    # 遍歷每一天
    for i, date in enumerate(date_range):
        print(f"正在獲取 {date} 的比賽列表...")
        
        url = f"https://www.sofascore.com/api/v1/sport/football/scheduled-events/{date}"
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                page.get(url)
                page.wait(1)
                data = page.json
                
                matches = parse_api_events(data)
                
                # 過濾指定聯賽（同時匹配聯賽名稱和國家）
                target_country = LEAGUE_CONFIG[league_name]['country']
                league_matches = [m for m in matches 
                                 if m['tournament_name'] == league_name 
                                 and m['category_name'] == target_country]
                
                print(f"  {date}: 找到 {len(league_matches)} 場 {league_name} 比賽")
                
                for match_info in league_matches:
                    # 去重：跳過已處理過的比賽
                    event_id = match_info['event_id']
                    if event_id in processed_event_ids:
                        continue
                    processed_event_ids.add(event_id)
                    
                    detail(match_info, league_rows)
                    detail_shotmap(match_info, league_shot_rows)
                    page_tab.wait(0.3)
                
                break  # 成功，退出重試循環
                
            except Exception as e:
                print(f"  錯誤: {e}")
                if attempt < max_retries - 1:
                    time.sleep(3)
                    try:
                        reconnect_browser()
                    except:
                        pass
                else:
                    # 嘗試重新連接瀏覽器
                    try:
                        reconnect_browser()
                    except:
                        pass
        
        # 每30天保存一次進度
        if (i + 1) % save_interval == 0:
            temp_stats_file = os.path.join(data_dir, f"temp_stats_{league_name}_{season_str}.csv")
            temp_shot_file = os.path.join(data_dir, f"temp_shot_{league_name}_{season_str}.csv")
            save_to_csv(league_rows, temp_stats_file)
            save_shotmap_to_csv(league_shot_rows, temp_shot_file)
            print(f"  [進度保存] 已保存 {len(league_rows)} 條統計數據")
    
    # 爬取完成後，將數據添加到總列表
    all_rows.extend(league_rows)
    all_shot_rows.extend(league_shot_rows)
    
    # 最終保存
    temp_stats_file = os.path.join(data_dir, f"temp_stats_{league_name}_{season_str}.csv")
    temp_shot_file = os.path.join(data_dir, f"temp_shot_{league_name}_{season_str}.csv")
    save_to_csv(league_rows, temp_stats_file)
    save_shotmap_to_csv(league_shot_rows, temp_shot_file)
    print(f"  [{league_name}] 已保存 {len(league_rows)} 條統計數據，{len(league_shot_rows)} 條射門數據")


def get_all_teams(all_matches):
    """從所有比賽中提取所有球隊"""
    teams = set()
    for match in all_matches:
        teams.add(match['home_team'])
        teams.add(match['away_team'])
    return list(teams)


def crawl_cups_for_teams(teams, season_str, all_rows, all_shot_rows):
    """爬取特定球隊在某賽季參與的盃賽"""
    start_date, end_date = get_season_dates(season_str)
    
    print(f"\n{'='*60}")
    print(f"正在爬取盃賽數據 - {season_str}")
    print(f"{'='*60}")
    
    # 生成日期範圍
    start_dt = datetime.datetime.strptime(start_date, '%Y-%m-%d')
    end_dt = datetime.datetime.strptime(end_date, '%Y-%m-%d')
    
    date_range = []
    current_dt = start_dt
    while current_dt <= end_dt:
        date_range.append(current_dt.strftime('%Y-%m-%d'))
        current_dt += datetime.timedelta(days=1)
    
    # 遍歷每一天，檢查盃賽
    for date in date_range:
        url = f"https://www.sofascore.com/api/v1/sport/football/scheduled-events/{date}"
        
        try:
            page.get(url)
            page.wait(0.8)
            data = page.json
            
            matches = parse_api_events(data)
            
            # 過濾盃賽
            for match in matches:
                tournament_name = match['tournament_name']
                home_team = match['home_team']
                away_team = match['away_team']
                
                # 檢查是否是盃賽並且包含我們的球隊
                is_cup = tournament_name in CUP_CONFIG
                has_our_team = home_team in teams or away_team in teams
                
                if is_cup and has_our_team:
                    print(f"  盃賽: {home_team} vs {away_team} ({tournament_name})")
                    
                    # 去重：跳過已處理過的比賽
                    event_id = match['event_id']
                    if event_id in processed_event_ids:
                        continue
                    processed_event_ids.add(event_id)
                    
                    detail(match, all_rows)
                    detail_shotmap(match, all_shot_rows)
                    page_tab.wait(0.3)
                    
        except Exception as e:
            continue


def start():
    """主程序"""
    # 清空已處理記錄，確保每次運行都是完整的
    global processed_event_ids
    processed_event_ids = set()
    
    seasons = get_season_list()
    print(f"將爬取以下賽季的數據: {seasons}")
    
    # 目標聯賽列表
    target_leagues = list(LEAGUE_CONFIG.keys())
    print(f"目標聯賽: {target_leagues}")
    
    # 數據存儲目錄
    base_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(base_dir, '5_years_data')
    os.makedirs(data_dir, exist_ok=True)
    
    all_stats_rows = []
    all_shot_rows = []
    
    # 記錄所有爬取過的比賽（用於提取球隊）
    all_matches = []
    
    # 遍歷每個賽季
    for season in seasons:
        print(f"\n{'#'*70}")
        print(f"# 處理賽季: {season}")
        print(f"{'#'*70}")
        
        season_stats = []
        season_shots = []
        
        # 爬取每個聯賽
        for league_name in target_leagues:
            crawl_league(league_name, season, season_stats, season_shots, data_dir)
        
        # 收集該賽季所有球隊
        teams = get_all_teams(season_stats)
        print(f"\n賽季 {season} 共 {len(teams)} 支球隊")
        
        # 爬取盃賽數據
        if teams:
            crawl_cups_for_teams(teams, season, season_stats, season_shots)
        
        # 保存該賽季數據
        if season_stats:
            stats_file = os.path.join(data_dir, f"statistics_{season}.csv")
            save_to_csv(season_stats, stats_file)
            print(f"統計數據已保存: {stats_file} ({len(season_stats)} 條)")
        
        if season_shots:
            shot_file = os.path.join(data_dir, f"shotmap_{season}.csv")
            save_shotmap_to_csv(season_shots, shot_file)
            print(f"射門數據已保存: {shot_file} ({len(season_shots)} 條)")
        
        # 累加到總數據
        all_stats_rows.extend(season_stats)
        all_shot_rows.extend(season_shots)
    
    # 保存全部數據
    if all_stats_rows:
        all_stats_file = os.path.join(data_dir, "all_statistics.csv")
        save_to_csv(all_stats_rows, all_stats_file)
        print(f"\n全部統計數據已保存: {all_stats_file} ({len(all_stats_rows)} 條)")
    
    if all_shot_rows:
        all_shot_file = os.path.join(data_dir, "all_shotmap.csv")
        save_shotmap_to_csv(all_shot_rows, all_shot_file)
        print(f"全部射門數據已保存: {all_shot_file} ({len(all_shot_rows)} 條)")


if __name__ == '__main__':
    print("五大聯賽 + J1 + K League + A-League 過往五個賽季數據爬蟲")
    
    
    # 初始化瀏覽器
    co = ChromiumOptions().headless()
    co.set_browser_path(r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe')
    page = ChromiumPage(co)
    page_tab = page.new_tab()
    
    try:
        start()
    finally:
        # 關閉瀏覽器
        try:
            page_tab.close()
        except:
            pass
        try:
            page.quit()
        except:
            pass
    
    print("\n完成！")
