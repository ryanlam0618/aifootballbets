"""
SofaScore 首发阵容爬虫
用于获取足球比赛的首发阵容数据
"""

import os
import json
import time
import datetime
from DrissionPage import ChromiumPage, ChromiumOptions


class SofaScoreLineupHarvester:
    def __init__(self):
        """初始化爬虫"""
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9,zh-TW;q=0.8,zh;q=0.7",
            "Referer": "https://www.sofascore.com/",
        }

    def parse_match_events(self, data):
        """解析比赛列表数据"""
        matches = []

        if 'events' not in data:
            return matches

        for event in data['events']:
            try:
                start_timestamp = event.get('startTimestamp', '')
                if start_timestamp:
                    match_date = datetime.datetime.fromtimestamp(start_timestamp).strftime('%Y-%m-%d')
                    match_time = datetime.datetime.fromtimestamp(start_timestamp).strftime('%H:%M')
                else:
                    match_date = ''
                    match_time = ''

                match_info = {
                    'event_id': event.get('id', ''),
                    'match_date': match_date,
                    'match_time': match_time,
                    'home_team': event['homeTeam']['name'],
                    'away_team': event['awayTeam']['name'],
                    'home_team_id': event['homeTeam'].get('id', ''),
                    'away_team_id': event['awayTeam'].get('id', ''),
                    'tournament_name': event.get('tournament', {}).get('name', ''),
                    'category_name': event.get('tournament', {}).get('category', {}).get('name', '')
                }
                matches.append(match_info)
            except KeyError as e:
                print(f"  跳过一场比赛，缺少字段: {e}")
                continue

        return matches

    def extract_lineup(self, data, match_info):
        """从 API 数据中提取首发阵容"""
        if 'error' in data:
            print(f"  [X] Lineup not available (404): {match_info['home_team']} vs {match_info['away_team']}")
            return None

        # 新的 API 格式: {"confirmed": true, "home": {...}, "away": {...}}
        if 'home' not in data or 'away' not in data:
            # 旧的 API 格式: {"lineups": [...]}
            return self._extract_lineup_old_format(data, match_info)

        result = {
            'event_id': match_info['event_id'],
            'match_date': match_info['match_date'],
            'match_time': match_info['match_time'],
            'tournament_name': match_info['tournament_name'],
            'category_name': match_info['category_name'],
            'home_team': match_info['home_team'],
            'away_team': match_info['away_team'],
            'home_formation': data.get('home', {}).get('formation', ''),
            'away_formation': data.get('away', {}).get('formation', ''),
            'home_coach': '',
            'away_coach': '',
            'home_starters': [],
            'away_starters': [],
            'home_substitutes': [],
            'away_substitutes': [],
            'home_missing_players': [],
            'away_missing_players': []
        }

        # 解析伤停信息 - 主队
        home_missing = data.get('home', {}).get('missingPlayers', [])
        for mp in home_missing:
            player = mp.get('player', {})
            missing_data = {
                'name': player.get('name', ''),
                'position': player.get('position', ''),
                'type': mp.get('type', ''),  # missing / doubtful
                'description': mp.get('description', ''),
                'expected_end_date': mp.get('expectedEndDate', '')
            }
            result['home_missing_players'].append(missing_data)

        # 解析伤停信息 - 客队
        away_missing = data.get('away', {}).get('missingPlayers', [])
        for mp in away_missing:
            player = mp.get('player', {})
            missing_data = {
                'name': player.get('name', ''),
                'position': player.get('position', ''),
                'type': mp.get('type', ''),  # missing / doubtful
                'description': mp.get('description', ''),
                'expected_end_date': mp.get('expectedEndDate', '')
            }
            result['away_missing_players'].append(missing_data)

        # 解析主队
        home_players = data.get('home', {}).get('players', [])
        for player in home_players:
            player_info = player.get('player', {})
            player_data = {
                'id': player_info.get('id', ''),
                'name': player_info.get('name', ''),
                'number': player.get('shirtNumber', ''),
                'position': player.get('position', ''),
                'rating': player.get('avgRating', '')
            }
            if player.get('substitute', False):
                result['home_substitutes'].append(player_data)
            else:
                result['home_starters'].append(player_data)

        # 解析客队
        away_players = data.get('away', {}).get('players', [])
        for player in away_players:
            player_info = player.get('player', {})
            player_data = {
                'id': player_info.get('id', ''),
                'name': player_info.get('name', ''),
                'number': player.get('shirtNumber', ''),
                'position': player.get('position', ''),
                'rating': player.get('avgRating', '')
            }
            if player.get('substitute', False):
                result['away_substitutes'].append(player_data)
            else:
                result['away_starters'].append(player_data)

        if not result['home_starters'] and not result['away_starters']:
            return None

        return result

    def _extract_lineup_old_format(self, data, match_info):
        """旧版 API 格式解析 (lineups 数组)"""
        if 'lineups' not in data or not data['lineups']:
            print(f"  [X] No lineup data: {match_info['home_team']} vs {match_info['away_team']}")
            return None

        lineups = data['lineups']
        result = {
            'event_id': match_info['event_id'],
            'match_date': match_info['match_date'],
            'match_time': match_info['match_time'],
            'tournament_name': match_info['tournament_name'],
            'category_name': match_info['category_name'],
            'home_team': match_info['home_team'],
            'away_team': match_info['away_team'],
            'home_formation': '',
            'away_formation': '',
            'home_coach': '',
            'away_coach': '',
            'home_starters': [],
            'away_starters': [],
            'home_substitutes': [],
            'away_substitutes': [],
            'home_missing_players': [],
            'away_missing_players': []
        }

        # 解析每队的阵容
        for team_lineup in lineups:
            team = team_lineup.get('team', {})
            team_name = team.get('name', '')
            is_home = team_lineup.get('isHome', False)

            # 提取阵型
            formation = team_lineup.get('formation', {}).get('name', '')
            if is_home:
                result['home_formation'] = formation
            else:
                result['away_formation'] = formation

            # 提取教练
            coach_info = team_lineup.get('coach', {})
            coach_name = coach_info.get('player', {}).get('name', '') if coach_info else ''
            if is_home:
                result['home_coach'] = coach_name
            else:
                result['away_coach'] = coach_name

            # 提取首发球员
            starters = team_lineup.get('starters', [])
            for player in starters:
                player_info = player.get('player', {})
                player_data = {
                    'id': player_info.get('id', ''),
                    'name': player_info.get('name', ''),
                    'number': player.get('shirtNumber', ''),
                    'position': player.get('position', ''),
                    'rating': player.get('rating', '')
                }
                if is_home:
                    result['home_starters'].append(player_data)
                else:
                    result['away_starters'].append(player_data)

            # 提取替补球员
            substitutes = team_lineup.get('substitutes', [])
            for player in substitutes:
                player_info = player.get('player', {})
                player_data = {
                    'id': player_info.get('id', ''),
                    'name': player_info.get('name', ''),
                    'number': player.get('shirtNumber', ''),
                    'position': player.get('position', ''),
                    'rating': player.get('rating', '')
                }
                if is_home:
                    result['home_substitutes'].append(player_data)
                else:
                    result['away_substitutes'].append(player_data)

        # 只有当有首发球员时才返回
        if not result['home_starters'] and not result['away_starters']:
            return None

        return result

    def fetch_lineup(self, page_tab, match_info):
        """获取单场比赛的阵容数据"""
        event_id = match_info['event_id']
        url = f'https://www.sofascore.com/api/v1/event/{event_id}/lineups'

        try:
            page_tab.get(url)
            page_tab.wait(0.5)
            data = page_tab.json

            lineup = self.extract_lineup(data, match_info)
            if lineup:
                print(f"  [OK] 已提取阵容: {match_info['home_team']} vs {match_info['away_team']}")
                print(f"    主队: {lineup['home_formation']} ({len(lineup['home_starters'])}人首发, {len(lineup['home_substitutes'])}人替补)")
                print(f"    客队: {lineup['away_formation']} ({len(lineup['away_starters'])}人首发, {len(lineup['away_substitutes'])}人替补)")
            return lineup

        except Exception as e:
            print(f"  [X] 阵容数据错误: {match_info['home_team']} vs {match_info['away_team']} - {e}")
            return None

    def get_match_list_by_date(self, page, date):
        """获取指定日期的比赛列表"""
        url = f"https://www.sofascore.com/api/v1/sport/football/scheduled-events/{date}"

        try:
            page.get(url)
            page.wait(1)
            data = page.json

            matches = self.parse_match_events(data)
            return matches

        except Exception as e:
            print(f"获取比赛列表失败: {e}")
            return []

    def save_lineup_to_json(self, lineup, save_folder):
        """保存阵容数据到 JSON 文件"""
        if not lineup:
            return None

        home_name = lineup['home_team']
        away_name = lineup['away_team']

        # 创建安全的文件名
        safe_home = home_name.replace(" ", "_").replace("/", "-")
        safe_away = away_name.replace(" ", "_").replace("/", "-")

        filename = f"lineup_{safe_home}_vs_{safe_away}_{lineup['match_date']}.json"
        full_path = os.path.join(save_folder, filename)

        with open(full_path, 'w', encoding='utf-8') as f:
            json.dump(lineup, f, ensure_ascii=False, indent=4)

        return full_path

    def run(self, start_date, end_date=None, league_filter=None, save_folder=None, interval=60):
        """
        运行爬虫获取阵容数据

        Args:
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)，默认与开始日期相同
            league_filter: 联赛筛选列表，如 [('Premier League', 'England'), ('La Liga', 'Spain')]
            save_folder: 保存文件夹路径
            interval: 监控模式下的检查间隔（秒）
        """
        # 处理日期范围
        if end_date is None:
            end_date = start_date

        start_dt = datetime.datetime.strptime(start_date, '%Y-%m-%d')
        end_dt = datetime.datetime.strptime(end_date, '%Y-%m-%d')

        date_range = []
        current_dt = start_dt
        while current_dt <= end_dt:
            date_range.append(current_dt.strftime('%Y-%m-%d'))
            current_dt += datetime.timedelta(days=1)

        print(f"日期范围: {start_date} ~ {end_date} (共 {len(date_range)} 天)")

        # 设置保存文件夹
        if save_folder is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            save_folder = os.path.join(base_dir, '..', 'data', 'lineup')

        if not os.path.exists(save_folder):
            os.makedirs(save_folder)
            print(f"📁 已创建文件夹: {save_folder}")

        # 初始化浏览器
        co = ChromiumOptions().headless()
        co.set_browser_path(r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe')
        page = ChromiumPage(co)
        page_tab = page.new_tab()

        all_lineups = []

        # 遍历每一天
        for date in date_range:
            print(f"\n{'=' * 50}")
            print(f"正在获取 {date} 的比赛列表...")
            print(f"{'=' * 50}")

            matches = self.get_match_list_by_date(page, date)

            # 应用联赛筛选
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

                # 获取阵容数据
                lineup = self.fetch_lineup(page_tab, match_info)

                if lineup:
                    # 保存到文件
                    saved_path = self.save_lineup_to_json(lineup, save_folder)
                    if saved_path:
                        print(f"  💾 已保存: {saved_path}")
                    all_lineups.append(lineup)
                else:
                    # 如果是监控模式（interval > 0），等待并重试
                    if interval > 0:
                        print(f"  [WAIT] 阵容尚未公布，{interval}秒后重试...")
                        page_tab.wait(interval)
                        lineup = self.fetch_lineup(page_tab, match_info)
                        if lineup:
                            saved_path = self.save_lineup_to_json(lineup, save_folder)
                            if saved_path:
                                print(f"  💾 已保存: {saved_path}")
                            all_lineups.append(lineup)

                page_tab.wait(0.5)

        # 关闭浏览器
        try:
            page_tab.close()
        except:
            pass
        try:
            page.quit()
        except:
            pass

        print(f"\n{'=' * 50}")
        print(f"完成！共获取 {len(all_lineups)} 场比赛的阵容数据")
        print(f"数据保存位置: {save_folder}")
        print(f"{'=' * 50}")

        return all_lineups

    @staticmethod
    def get_lineup_by_event_id(event_id, save_folder=None):
        """
        通过 event_id 获取单场比赛的阵容

        Args:
            event_id: SofaScore 比赛 ID
            save_folder: 保存文件夹路径

        Returns:
            lineup 数据字典 或 None
        """
        if save_folder is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            save_folder = os.path.join(base_dir, '..', 'data', 'lineup')

        if not os.path.exists(save_folder):
            os.makedirs(save_folder)

        co = ChromiumOptions().headless()
        co.set_browser_path(r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe')
        page = ChromiumPage(co)
        page_tab = page.new_tab()

        url = f'https://www.sofascore.com/api/v1/event/{event_id}/lineups'
        url_info = f'https://www.sofascore.com/api/v1/event/{event_id}'

        try:
            # 获取比赛基本信息
            page.get(url_info)
            page.wait(1)
            data = page.json

            match_info = {
                'event_id': event_id,
                'match_date': '',
                'match_time': '',
                'home_team': '',
                'away_team': '',
                'tournament_name': '',
                'category_name': ''
            }

            if 'event' in data:
                event = data['event']
                start_timestamp = event.get('startTimestamp', '')
                if start_timestamp:
                    match_info['match_date'] = datetime.datetime.fromtimestamp(start_timestamp).strftime('%Y-%m-%d')
                    match_info['match_time'] = datetime.datetime.fromtimestamp(start_timestamp).strftime('%H:%M')

                match_info['home_team'] = event.get('homeTeam', {}).get('name', '')
                match_info['away_team'] = event.get('awayTeam', {}).get('name', '')
                match_info['tournament_name'] = event.get('tournament', {}).get('name', '')
                match_info['category_name'] = event.get('tournament', {}).get('category', {}).get('name', '')

            # 获取阵容数据
            page_tab.get(url)
            page_tab.wait(0.5)
            lineup_data = page_tab.json

            harvester = SofaScoreLineupHarvester()
            lineup = harvester.extract_lineup(lineup_data, match_info)

            if lineup:
                saved_path = harvester.save_lineup_to_json(lineup, save_folder)
                print(f"✅ 阵容已获取并保存: {saved_path}")
                return lineup
            else:
                print("[ERR] 无法获取阵容数据")
                return None

        except Exception as e:
            print(f"[ERR] 错误: {e}")
            return None

        finally:
            try:
                page_tab.close()
            except:
                pass
            try:
                page.quit()
            except:
                pass


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
    }

    choice = input('请输入选项（默认 0）: ').strip()

    if not choice or choice == '0':
        return None

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
    """验证并获取日期输入"""
    print("\n请输入日期范围（格式：yyyy-MM-dd 或 yyyy-MM-dd~yyyy-MM-dd）")
    print("示例：2026-02-12（单天）或 2026-02-10~2026-02-12（范围）")
    date_input = input('不填默认查询当天的数据: ').strip()

    if not date_input:
        date = datetime.datetime.now().strftime('%Y-%m-%d')
        return date, date

    if '~' in date_input:
        parts = date_input.split('~')
        if len(parts) != 2:
            print(f"日期范围格式错误：{date_input}")
            return validate_date_input()

        start_date = parts[0].strip()
        end_date = parts[1].strip()

        try:
            datetime.datetime.strptime(start_date, '%Y-%m-%d')
            datetime.datetime.strptime(end_date, '%Y-%m-%d')
            return start_date, end_date
        except ValueError as e:
            print(f"日期格式错误: {e}")
            return validate_date_input()
    else:
        try:
            validated_date = datetime.datetime.strptime(date_input, '%Y-%m-%d')
            date_str = validated_date.strftime('%Y-%m-%d')
            return date_str, date_str
        except ValueError:
            print(f"输入的日期格式错误：{date_input}")
            return validate_date_input()


if __name__ == '__main__':
    print("=" * 60)
    print("⚽ SofaScore 首发阵容爬虫")
    print("=" * 60)

    # 获取日期
    start_date, end_date = validate_date_input()

    # 获取联赛筛选
    league_filter = get_league_filter()

    # 运行爬虫
    print("\n🚀 开始获取阵容数据...")
    harvester = SofaScoreLineupHarvester()

    # 设置保存路径
    save_folder = r"C:\Users\Ryan\python\.vscode\fb_ai_bets\data\lineup"

    # 执行获取
    harvester.run(start_date, end_date, league_filter, save_folder)
