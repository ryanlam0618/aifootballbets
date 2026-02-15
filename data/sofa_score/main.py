
import os

from DrissionPage import ChromiumPage, ChromiumOptions
import csv
import datetime


def parse_api_events(data):
    """从 API 数据中提取所有比赛信息"""
    matches = []
    
    if 'events' not in data:
        return matches

    for event in data['events']:
        try:
            # 获取比赛日期时间 (使用 startTimestamp 转换为日期)
            start_timestamp = event.get('startTimestamp', '')
            if start_timestamp:
                # 将 Unix 时间戳转换为日期
                match_date = datetime.datetime.fromtimestamp(start_timestamp).strftime('%Y-%m-%d')
            else:
                match_date = ''
            
            match_info = {
                'event_id': event.get('id', ''),
                'match_date': match_date,
                'home_team': event['homeTeam']['name'],
                'away_team': event['awayTeam']['name'],
                'home_slug': event['homeTeam']['slug'],
                'away_slug': event['awayTeam']['slug'],
                'custom_id': event['customId'],
                'tournament_name': event.get('tournament', {}).get('name', ''),
                'category_name': event.get('tournament', {}).get('category', {}).get('name', '')
            }
            matches.append(match_info)
        except KeyError as e:
            print(f"跳过一场比赛，缺少字段: {e}")
            continue

    return matches



def extract_statistics(data, match_info):
    """提取统计数据"""
    if 'error' in data:
        print(f"  跳过 (404): {match_info['home_team']} vs {match_info['away_team']}")
        return None
    
    if 'statistics' not in data or not data['statistics']:
        print(f"  无统计数据: {match_info['home_team']} vs {match_info['away_team']}")
        return None
    
    # 只提取 ALL period 的数据
    all_period_data = None
    for period in data['statistics']:
        if period['period'] == 'ALL':
            all_period_data = period
            break
    
    if not all_period_data:
        return None
    
    rows = []
    target_groups = ['Match overview', 'Shots', 'Attack', 'Passes', 'Duels', 'Defending', 'Goalkeeping']
    
    for group in all_period_data['groups']:
        group_name = group['groupName']
        
        if group_name not in target_groups:
            continue
        
        for item in group['statisticsItems']:
            row = {
                'event_id': match_info['event_id'],
                'match_date': match_info['match_date'],
                'tournament_name': match_info['tournament_name'],
                'category_name': match_info['category_name'],
                'home_team': match_info['home_team'],
                'away_team': match_info['away_team'],
                'group': group_name,
                'stat_name': item['name'],
                'stat_key': item.get('key', ''),
                'home_display': item.get('home', ''),
                'away_display': item.get('away', ''),
                'home_value': item.get('homeValue', ''),
                'away_value': item.get('awayValue', ''),
                'home_total': item.get('homeTotal', ''),
                'away_total': item.get('awayTotal', ''),
                'compare_code': item.get('compareCode', ''),
                'render_type': item.get('renderType', ''),
                'statistics_type': item.get('statisticsType', ''),
                'value_type': item.get('valueType', '')
            }
            rows.append(row)
    
    return rows


def extract_shotmap(data, match_info):
    """提取球员射门数据"""
    if 'error' in data:
        print(f"  跳过 (404): {match_info['home_team']} vs {match_info['away_team']}")
        return None
    
    if 'shotmap' not in data or not data['shotmap']:
        print(f"  无射门数据: {match_info['home_team']} vs {match_info['away_team']}")
        return None
    
    rows = []
    
    for shot in data['shotmap']:
        try:
            # 获取球员信息
            player_name = shot.get('player', {}).get('name', '')
            player_id = shot.get('player', {}).get('id', '')
            
            # 获取时间（分钟）
            time_minute = shot.get('time', '')
            added_time = shot.get('addedTime', '')
            if added_time:
                time_display = f"{time_minute}+{added_time}"
            else:
                time_display = str(time_minute)
            
            # xG 和 xGOT
            xg = shot.get('xg', '')
            xgot = shot.get('xgot', '')
            
            # Outcome (结果) - shotType 字段
            outcome = shot.get('shotType', '')
            
            # Situation (情况)
            situation = shot.get('situation', '')
            
            # Shot type (射门类型) - bodyPart 字段
            shot_type = shot.get('bodyPart', '')
            
            # Goal zone (球门区域) - goalMouthLocation 字段
            goal_zone = shot.get('goalMouthLocation', '')
            
            # X, Y 坐标 (playerCoordinates - 射门球员位置)
            player_coords = shot.get('playerCoordinates', {})
            x_coord = player_coords.get('x', '') if player_coords else ''
            y_coord = player_coords.get('y', '') if player_coords else ''
            
            # 球门坐标 (goalMouthCoordinates)
            goal_coords = shot.get('goalMouthCoordinates', {})
            goal_x = goal_coords.get('x', '') if goal_coords else ''
            goal_y = goal_coords.get('y', '') if goal_coords else ''
            
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
            print(f"  解析射门数据出错: {e}")
            continue
    
    return rows


def detail(match_info, all_rows):
    """获取单场比赛的统计数据"""
    event_id = match_info['event_id']
    url = f'https://www.sofascore.com/api/v1/event/{event_id}/statistics'
    
    try:
        page_tab.get(url)
        page_tab.wait(0.5)
        data = page_tab.json
        
        rows = extract_statistics(data, match_info)
        if rows:
            all_rows.extend(rows)
            print(f"  ✓ 已提取: {match_info['home_team']} vs {match_info['away_team']} ({len(rows)} 条数据)")
        
    except Exception as e:
        print(f"  ✗ 错误: {match_info['home_team']} vs {match_info['away_team']} - {e}")


def detail_shotmap(match_info, all_shot_rows):
    """获取单场比赛的射门数据"""
    event_id = match_info['event_id']
    url = f'https://www.sofascore.com/api/v1/event/{event_id}/shotmap'
    
    try:
        page_tab.get(url)
        page_tab.wait(0.5)
        data = page_tab.json
        
        rows = extract_shotmap(data, match_info)
        if rows:
            all_shot_rows.extend(rows)
            print(f"  ✓ 已提取射门: {match_info['home_team']} vs {match_info['away_team']} ({len(rows)} 条射门)")
        
    except Exception as e:
        print(f"  ✗ 射门数据错误: {match_info['home_team']} vs {match_info['away_team']} - {e}")


def save_to_csv(rows, filename):
    """保存数据到 CSV"""
    if not rows:
        print("没有数据可保存")
        return
    
    fieldnames = ['match_date', 'event_id', 'tournament_name', 'category_name', 'home_team', 'away_team', 
                  'group', 'stat_name', 'stat_key', 'home_display', 'away_display', 
                  'home_value', 'away_value', 'home_total', 'away_total', 'compare_code', 
                  'render_type', 'statistics_type', 'value_type']
    
    with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    
    print(f"\n数据已保存到: {filename}")
    print(f"共 {len(rows)} 条记录")


def save_shotmap_to_csv(rows, filename):
    """保存射门数据到 CSV"""
    if not rows:
        print("没有射门数据可保存")
        return
    
    fieldnames = ['match_date', 'event_id', 'tournament_name', 'category_name', 'home_team', 'away_team', 
                  'player_name', 'player_id', 'time_minute', 'xg', 'xgot', 'outcome', 
                  'situation', 'shot_type', 'goal_zone', 'x', 'y', 'is_home']
    
    with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    
    print(f"\n射门数据已保存到: {filename}")
    print(f"共 {len(rows)} 条射门记录")


def start(start_date, end_date, league_filter=None):

    # 生成日期范围
    start_dt = datetime.datetime.strptime(start_date, '%Y-%m-%d')
    end_dt = datetime.datetime.strptime(end_date, '%Y-%m-%d')
    
    date_range = []
    current_dt = start_dt
    while current_dt <= end_dt:
        date_range.append(current_dt.strftime('%Y-%m-%d'))
        current_dt += datetime.timedelta(days=1)
    
    print(f"日期范围: {start_date} ~ {end_date} (共 {len(date_range)} 天)")
    
    # 累计所有数据
    all_rows = []
    all_shot_rows = []
    
    # 遍历每一天
    for date in date_range:
        print(f"\n{'='*50}")
        print(f"正在获取 {date} 的比赛列表...")
        print(f"{'='*50}")
        
        url = f"https://www.sofascore.com/api/v1/sport/football/scheduled-events/{date}"
        
        page.get(url)
        page.wait(1)
        data = page.json

        matches = parse_api_events(data)
        
        # 如果有联赛筛选，则过滤比赛
        if league_filter:
            filtered_matches = []
            for match in matches:
                tournament_name = match.get('tournament_name', '')
                category_name = match.get('category_name', '')
                for league_name, league_country in league_filter:
                    if league_name == tournament_name:
                        if not league_country or league_country == category_name:
                            filtered_matches.append(match)
                            break
            matches = filtered_matches
        
        print(f"找到 {len(matches)} 场比赛")
        if league_filter:
            print(f"（已筛选 {len(matches)} 场比赛）\n")
        else:
            print()
        
        for i, match_info in enumerate(matches, 1):
            print(f"[{i}/{len(matches)}] 处理: {match_info['home_team']} vs {match_info['away_team']}")
            
            # 提取统计数据
            detail(match_info, all_rows)
            
            # 提取射门数据
            detail_shotmap(match_info, all_shot_rows)
            
            page_tab.wait(0.5)
    
    # 保存统计数据到 CSV
    # 使用脚本所在目录作为基础路径
    base_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(base_dir)
    
    # 生成文件名
    date_str = start_date if start_date == end_date else f"{start_date}_to_{end_date}"
    
    # 如果有联赛筛选，添加联赛标识
    if league_filter:
        league_str = "_".join([name.replace(" ", "") for name, _ in league_filter])
        league_str = league_str[:30]  # 限制长度
        stats_filename = os.path.join(data_dir, f"football_statistics_{date_str}_{league_str}.csv")
        shotmap_filename = os.path.join(data_dir, f"football_shotmap_{date_str}_{league_str}.csv")
    else:
        stats_filename = os.path.join(data_dir, f"football_statistics_{date_str}.csv")
        shotmap_filename = os.path.join(data_dir, f"football_shotmap_{date_str}.csv")
    
    save_to_csv(all_rows, stats_filename)
    save_shotmap_to_csv(all_shot_rows, shotmap_filename)


def get_league_filter():
    """获取用户想要筛选的联赛列表"""
    print("\n请选择要筛选的联赛（输入编号，多个用逗号分隔，如：1,3,5）")
    print("  0 - 不筛选，获取所有联赛")
    print("  1 - Premier League (英格兰)")
    print("  2 - La Liga (西班牙)")
    print("  3 - Serie A (意大利)")
    print("  4 - Bundesliga (德国)")
    print("  5 - Ligue 1 (法国)")
    print("  6 - Champions League (欧冠)")
    print("  7 - Europa League (欧联)")
    print("  8 - Premier League Russia (俄罗斯)")
    print("  9 - Serie A (巴西)")
    print(" 10 - Serie A (阿根廷)")
    print(" 11 - Major League Soccer (美国)")
    print(" 12 - Championship (英冠)")
    print(" 13 - Primeira Liga (葡萄牙)")
    print(" 14 - Eredivisie (荷兰)")
    print(" 15 - Pro League (沙特)")
    print(" 16 - Chinese Super League (中国)")
    print(" 17 - K League 1 (韩国)")
    print(" 18 - J1 League (日本)")
    print(" 19 - A-League (澳洲)")
    print(" 20 - Indian Super League (印度)")
    print(" 21 - MLS (美国)")
    print(" 22 - Liga MX (墨西哥)")
    print(" 23 - Copa Libertadores (南美)")
    print(" 24 - Turkish Super Lig (土耳其)")
    print(" 25 - Belgian Pro League (比利时)")
    print(" 26 - Scottish Premiership (苏超)")
    print(" 27 - Super Lig (土耳其)")
    print("输入 'all' 获取所有联赛列表")
    
    league_map = {
        '1': ('Premier League', 'England'),
        '2': ('La Liga', 'Spain'),
        '3': ('Serie A', 'Italy'),
        '4': ('Bundesliga', 'Germany'),
        '5': ('Ligue 1', 'France'),
        '6': ('UEFA Champions League', ''),
        '7': ('UEFA Europa League', ''),
        '8': ('Premier League', 'Russia'),
        '9': ('Serie A', 'Brazil'),
        '10': ('Liga Profesional Argentina', 'Argentina'),
        '11': ('Major League Soccer', 'USA'),
        '12': ('Championship', 'England'),
        '13': ('Primeira Liga', 'Portugal'),
        '14': ('Eredivisie', 'Netherlands'),
        '15': ('Pro League', 'Saudi Arabia'),
        '16': ('Chinese Super League', 'China'),
        '17': ('K League 1', 'South Korea'),
        '18': ('J1 League', 'Japan'),
        '19': ('A-League', 'Australia'),
        '20': ('Indian Super League', 'India'),
        '21': ('MLS', 'USA'),
        '22': ('Liga MX', 'Mexico'),
        '23': ('Copa Libertadores', ''),
        '24': ('Süper Lig', 'Turkey'),
        '25': ('Belgian Pro League', 'Belgium'),
        '26': ('Scottish Premiership', 'Scotland'),
    }
    
    choice = input('请输入选项（默认 0）:').strip()
    
    if not choice or choice == '0':
        return None  # 不筛选
    
    if choice.lower() == 'all':
        # 显示所有可用联赛
        print("\n可用联赛列表：")
        for k, v in league_map.items():
            country = f" ({v[1]})" if v[1] else ""
            print(f"  {k} - {v[0]}{country}")
        return get_league_filter()
    
    # 解析用户选择的联赛
    selected = []
    for item in choice.split(','):
        item = item.strip()
        if item in league_map:
            selected.append(league_map[item])
    
    if not selected:
        print("未选择任何联赛，将获取所有比赛")
        return None
    
    print(f"已选择 {len(selected)} 个联赛")
    return selected


def validate_date_input():

    print("请输入日期范围（格式：yyyy-MM-dd 或 yyyy-MM-dd~yyyy-MM-dd）")
    print("示例：2026-02-12（单天）或 2026-02-10~2026-02-12（范围）")
    date_input = input('不填默认查询当天的数据:').strip()

    if not date_input:
        # 默认当天
        date = datetime.datetime.now().strftime('%Y-%m-%d')
        return date, date
    
    # 检查是否包含范围分隔符 ~
    if '~' in date_input:
        parts = date_input.split('~')
        if len(parts) != 2:
            print(f"日期范围格式错误：{date_input}，请使用 yyyy-MM-dd~yyyy-MM-dd 格式")
            return validate_date_input()
        
        start_date = parts[0].strip()
        end_date = parts[1].strip()
        
        # 验证开始日期
        try:
            datetime.datetime.strptime(start_date, '%Y-%m-%d')
        except ValueError:
            print(f"开始日期格式错误：{start_date}，请使用 yyyy-MM-dd 格式")
            return validate_date_input()
        
        # 验证结束日期
        try:
            datetime.datetime.strptime(end_date, '%Y-%m-%d')
        except ValueError:
            print(f"结束日期格式错误：{end_date}，请使用 yyyy-MM-dd 格式")
            return validate_date_input()
        
        return start_date, end_date
    else:
        # 单个日期
        try:
            validated_date = datetime.datetime.strptime(date_input, '%Y-%m-%d')
            date_str = validated_date.strftime('%Y-%m-%d')
            return date_str, date_str
        except ValueError:
            print(f"输入的日期格式错误：{date_input}，请严格按照 yyyy-MM-dd 格式输入（例如：2026-02-12）")
            return validate_date_input()

if __name__ == '__main__':

    # 先获取日期
    start_date, end_date = validate_date_input()
    
    # 初始化浏览器
    co = ChromiumOptions().headless()
    co.set_browser_path(r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe')
    page = ChromiumPage(co)
    page_tab = page.new_tab()
    
    # 获取联赛筛选条件
    league_filter = get_league_filter()
    
    # 执行爬取
    start(start_date, end_date, league_filter)

    # 关闭浏览器
    try:
        page_tab.close()
    except:
        pass
    try:
        page.quit()
    except:
        pass

