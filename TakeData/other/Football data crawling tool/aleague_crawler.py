#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
A-League Data Crawler - 修復版
爬取澳職(A-League)比賽數據
"""

import sys
import os
import time
import json
import csv
import random
import re
from datetime import datetime, timedelta
from DrissionPage import WebPage, ChromiumOptions


class ALeagueCrawler:
    """澳職數據爬蟲類"""
    
    def __init__(self, output_dir="aleague_data_output"):
        self.output_dir = output_dir
        self.team_data = []
        self.player_count = 0
        
        os.makedirs(output_dir, exist_ok=True)
        os.makedirs(os.path.join(output_dir, "players"), exist_ok=True)
        os.makedirs(os.path.join(output_dir, "teams"), exist_ok=True)
    
    @staticmethod
    def get_chrome_path():
        possible_paths = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            r"D:\Program Files\Google\Chrome\Application\chrome.exe",
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                return path
        
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe")
            path = winreg.QueryValue(key, None)
            winreg.CloseKey(key)
            if os.path.exists(path):
                return path
        except:
            pass
        
        return None
    
    @staticmethod
    def wait_with_random_delay(min_seconds=0.8, max_seconds=1.5):
        delay = random.uniform(min_seconds, max_seconds)
        time.sleep(delay)
    
    @staticmethod
    def create_browser_instance(headless=True):
        co = ChromiumOptions()
        chrome_path = ALeagueCrawler.get_chrome_path()
        co.headless(headless)
        co.auto_port(True)
        co.mute(True)
        
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        ]
        co.set_user_agent(random.choice(user_agents))
        
        if chrome_path:
            co.set_browser_path(chrome_path)
        
        return WebPage('d', chromium_options=co)
    
    def extract_match_data(self, tr_element):
        """從表格行中提取比賽數據"""
        try:
            # 初始化 match_id
            match_id = ""
            
            tds = tr_element.eles('tag:td')
            
            if len(tds) < 10:
                return None
            
            # 聯賽信息
            league = tds[0].text.strip() if len(tds) > 0 else ""
            
            # 擴展澳職關鍵詞
            if '澳洲' not in league and 'A-League' not in league.upper() and '澳超' not in league:
                return None
            
            # 比賽時間
            match_time = tds[1].text.strip() if len(tds) > 1 else ""
            
            # 比賽狀態
            status = tds[2].text.strip() if len(tds) > 2 else ""
            
            # 主隊信息 (可能包含排名如 [3]阿德莱德联)
            home_team_raw = tds[3].text.strip() if len(tds) > 3 else ""
            home_team = re.sub(r'\[.*?\]', '', home_team_raw).strip()
            
            # 比分信息 - 從 onclick 提取 match_id
            score = ""
            if len(tds) > 4:
                score_td = tds[4]
                score_text = score_td.text.strip()
                if score_text:
                    font_elements = score_td.eles('tag:font')
                    if len(font_elements) >= 2:
                        score = f"{font_elements[0].text.strip()}-{font_elements[1].text.strip()}"
                    elif '-' in score_text:
                        score = score_text
                
                # 從 onclick 提取 match_id (格式: showgoallist(2261882))
                onclick = score_td.attrs.get('onclick', '')
                if onclick:
                    id_match = re.search(r'showgoallist\((\d+)\)', onclick)
                    if id_match:
                        match_id = id_match.group(1)
            
            # 客隊信息
            away_team_raw = tds[5].text.strip() if len(tds) > 5 else ""
            away_team = re.sub(r'\[.*?\]', '', away_team_raw).strip()
            
            # 半場比分
            half_score = ""
            if len(tds) > 6:
                half_text = tds[6].text.strip()
                font_elements = tds[6].eles('tag:font')
                if len(font_elements) >= 2:
                    half_score = f"{font_elements[0].text.strip()}-{font_elements[1].text.strip()}"
                elif '-' in half_text:
                    half_score = half_text
            
            # 檢查比分是否存在且有效
            if not score or '-' not in score:
                return None
            
            # 解析比分數字
            try:
                parts = score.split('-')
                home_goals = int(parts[0].strip())
                away_goals = int(parts[1].strip())
            except:
                return None
            
            # 如果沒有 match_id，生成一個
            if not match_id:
                match_id = f"{home_team}_{away_team}_{match_time}"
            
            return {
                'match_id': match_id,
                'league': league,
                'match_time': match_time,
                'status': status,
                'home_team': home_team,
                'score': score,
                'away_team': away_team,
                'half_score': half_score
            }
            
        except Exception as e:
            print(f"  提取錯誤: {e}")
            return None
    
    def get_match_stats_from_page(self, page, match_data):
        """從比賽頁面獲取技術統計數據"""
        try:
            stat_selectors = [
                'css:#teamTechDiv_detail',
                'xpath://div[contains(@class, "stat")]',
                'css:.stat-content',
                'css:.match-stats'
            ]
            
            stat_div = None
            for selector in stat_selectors:
                stat_div = page.ele(selector, timeout=3)
                if stat_div:
                    break
            
            if not stat_div:
                return None, None
            
            stat_mapping = {
                '角球': 'Corners',
                '黃牌': 'Yellow_Cards',
                '紅牌': 'Red_Cards',
                '射門': 'Shots',
                '射正': 'Shots_on_Target',
                '進攻': 'Attacks',
                '危險進攻': 'Dangerous_Attacks',
                '任意球': 'Free_Kicks',
                '控球率': 'Possession',
                '犯規': 'Fouls',
                '越位': 'Offsides',
                '頭球': 'Headers',
                '頭球成功': 'Headers_Won',
                '救球': 'Saves',
                '鏟球': 'Tackles',
                '過人': 'Dribbles',
                '界外球': 'Throw_Ins',
                '搶斷': 'Interceptions',
                '阻截': 'Blocks',
                '助攻': 'Assists'
            }
            
            home_stats = {'team_name': match_data['home_team'], 'is_home': True}
            away_stats = {'team_name': match_data['away_team'], 'is_home': False}
            
            page_text = stat_div.text
            
            for cn_name, en_name in stat_mapping.items():
                pattern1 = rf'(\d+\.?\d*%?)\s*{re.escape(cn_name)}\s*(\d+\.?\d*%?)'
                pattern2 = rf'(\d+)\s*{re.escape(cn_name)}\s*(\d+)'
                
                match1 = re.search(pattern1, page_text)
                match2 = re.search(pattern2, page_text)
                
                if match1:
                    home_stats[en_name] = match1.group(1).rstrip('%')
                    away_stats[en_name] = match1.group(2).rstrip('%')
                elif match2:
                    home_stats[en_name] = match2.group(1)
                    away_stats[en_name] = match2.group(2)
            
            return home_stats, away_stats
            
        except Exception as e:
            print(f"獲取統計數據錯誤: {e}")
            return None, None
    
    def get_player_data_from_page(self, page, match_data):
        """從頁面獲取球員數據"""
        try:
            home_players = []
            away_players = []
            
            # 直接從頁面解析球員數據
            print(f"    從頁面解析球員數據...")
            home_players, away_players = self._parse_player_from_page(page, match_data)
            
            return home_players, away_players
            
        except Exception as e:
            print(f"獲取球員數據錯誤: {e}")
            return [], []
    
    def _parse_player_from_page(self, page, match_data):
        """直接從頁面解析球員數據"""
        home_players = []
        away_players = []
        
        try:
            home_team = match_data['home_team']
            away_team = match_data['away_team']
            
            # 事件類型對應表 (圖片文件名 -> 事件類型)
            # 根據實際數據分析:
            # 12.png = 進球 (goal)
            # 3.png = 助攻 (assist)
            # 5.png = 換人 (substitution)
            # 1.png = 黃牌 (yellow card)
            # 7.png = 紅牌 (red card)
            event_types = {
                '12.png': 'goal',       # 進球
                '3.png': 'assist',      # 助攻
                '5.png': 'substitution', # 換人
                '1.png': 'yellow',      # 黃牌
                '7.png': 'red',         # 紅牌
            }
            
            # 查找 plays div
            plays_div = page.ele('xpath://div[@id="matchBox2"]/div[@class="plays"]')
            if not plays_div:
                plays_div = page.ele('xpath://div[@class="plays"]')
            
            if plays_div:
                # 獲取 plays 裡面的所有子元素
                children = plays_div.eles('xpath:./div')
                
                # 遍歷子元素，識別主隊和客隊區域
                for child in children:
                    child_class = child.attrs.get('class', '')
                    child_html = child.html
                    
                    # 檢查是否是主隊區域
                    if 'home' in child_class:
                        print(f"    找到主隊區域")
                        # 查找所有球員 (包括 playBox 和 play)
                        play_boxes = child.eles('css:div.playBox')
                        play_elements = child.eles('css:div.play')
                        
                        all_play_elements = play_boxes + play_elements
                        print(f"    主隊找到 {len(all_play_elements)} 個球員區塊")
                        
                        for play_elem in all_play_elements:
                            player = self._extract_player_from_play_elem(play_elem, home_team, True, event_types)
                            if player and player.get('name'):
                                home_players.append(player)
                    
                    # 檢查是否是客隊區域
                    elif 'guest' in child_class:
                        print(f"    找到客隊區域")
                        # 查找所有球員 (包括 playBox 和 play)
                        play_boxes = child.eles('css:div.playBox')
                        play_elements = child.eles('css:div.play')
                        
                        all_play_elements = play_boxes + play_elements
                        print(f"    客隊找到 {len(all_play_elements)} 個球員區塊")
                        
                        for play_elem in all_play_elements:
                            player = self._extract_player_from_play_elem(play_elem, away_team, False, event_types)
                            if player and player.get('name'):
                                away_players.append(player)
            
            # 打印調試信息
            if home_players:
                print(f"    主隊球員: {[p.get('name') for p in home_players]}")
            if away_players:
                print(f"    客隊球員: {[p.get('name') for p in away_players]}")
            
            return home_players, away_players
            
        except Exception as e:
            print(f"    解析頁面球員錯誤: {e}")
            import traceback
            traceback.print_exc()
            return [], []
    
    def _extract_player_from_box(self, box, team_name, is_home, event_types):
        """從 playBox 元素提取球員信息"""
        try:
            # playBox 結構: <div class="playBox"><div class="play"><span>...</span><div id="playerTech_xxx">...</div></div></div>
            play_elem = box.ele('css:div.play')
            if not play_elem:
                return None
            
            return self._extract_player_from_play_elem(play_elem, team_name, is_home, event_types)
            
        except Exception as e:
            print(f"    提取球員錯誤: {e}")
            return None
    
    def _extract_player_from_play_elem(self, play_elem, team_name, is_home, event_types):
        """從 play 元素提取球員信息"""
        try:
            player = {
                'team': team_name,
                'is_home': is_home,
                'number': '',
                'name': '',
                'full_name': '',
                'position': '',
                'rating': '',
                'key_events': '',
                'goals': '0',
                'assists': '0',
                'yellow_cards': '0',
                'red_cards': '0',
                'substituted_in': '0',
                'substituted_out': '0',
                'motm': '0',
                'shots': '0',
                'shots_on_target': '0',
                'key_passes': '0',
                'pass_accuracy': '0',
                'aerial_duels_won': '0',
                'physical_duels': '0'
            }
            
            # 提取球員號碼 - 在 <i> 標籤中
            number_elem = play_elem.ele('css:i')
            if number_elem:
                player['number'] = number_elem.text.strip()
            
            # 提取球員名字 - 在 <div class="name"> 中的 <a> 標籤
            name_elem = play_elem.ele('css:div.name')
            if name_elem:
                name_link = name_elem.ele('tag:a')
                if name_link:
                    player['name'] = name_link.text.strip()
            
            # 提取球員完整信息 - 在 <ul> 標籤中
            ul_elem = play_elem.ele('tag:ul')
            if ul_elem:
                ul_text = ul_elem.text
                # 提取完整姓名
                name_match = re.search(r'姓名：([^\n]+)', ul_text)
                if name_match:
                    player['full_name'] = name_match.group(1).strip()
                    # 如果沒有簡短名字，使用完整名字
                    if not player['name']:
                        player['name'] = player['full_name']
            
            # 提取球員事件 - 在 <div id="playerTech_xxx"> 中的 <img> 標籤
            events_div = play_elem.ele('xpath:.//div[starts-with(@id, "playerTech_")]')
            if events_div:
                event_imgs = events_div.eles('tag:img')
                events = []
                
                for img in event_imgs:
                    src = img.attr('src') or ''
                    alt = img.attr('alt') or ''
                    title = img.attr('title') or ''
                    
                    # 從文件名判斷事件類型
                    event_type = None
                    for filename, etype in event_types.items():
                        if filename in src:
                            event_type = etype
                            break
                    
                    # 從 alt/title 提取時間
                    time_match = re.search(r"(\d+'\+?\d*)", alt or title)
                    event_time = time_match.group(1) if time_match else ''
                    
                    if event_type:
                        # 記錄事件
                        event_str = f"{event_time}"
                        events.append(event_str)
                        
                        # 更新計數
                        if event_type == 'goal':
                            player['goals'] = str(int(player['goals']) + 1)
                        elif event_type == 'assist':
                            player['assists'] = str(int(player['assists']) + 1)
                        elif event_type == 'yellow':
                            player['yellow_cards'] = str(int(player['yellow_cards']) + 1)
                        elif event_type == 'red':
                            player['red_cards'] = str(int(player['red_cards']) + 1)
                        elif event_type == 'substitution':
                            # 換人事件 - 根據時間推斷換上/換下
                            # 如果是替補球員有換人事件，可能是換上
                            # 如果是首發球員有換人事件，可能是換下
                            # 簡單處理：同時設置換上和換下標記
                            player['substituted_in'] = '1'
                            player['substituted_out'] = '1'
                
                player['key_events'] = ' '.join(events)
            
            # 如果沒有提取到球員名字，返回 None
            if not player.get('name'):
                return None
            
            return player
            
        except Exception as e:
            print(f"    提取球員錯誤: {e}")
            return None
    
    def parse_player_table(self, table, team_name, is_home):
        """解析球員表格數據"""
        players = []
        
        try:
            rows = table.eles('tag:tr')
            if len(rows) < 2:
                return players
            
            for row in rows[1:]:
                try:
                    cells = row.eles('tag:td')
                    if len(cells) < 5:
                        continue
                    
                    player = {
                        'team': team_name,
                        'is_home': is_home,
                        'number': cells[0].text.strip() if len(cells) > 0 else '',
                        'name': cells[1].text.strip() if len(cells) > 1 else '',
                        'position': cells[2].text.strip() if len(cells) > 2 else '',
                        'rating': cells[3].text.strip() if len(cells) > 3 else '',
                        'key_events': cells[4].text.strip() if len(cells) > 4 else ''
                    }
                    
                    key_events = player['key_events']
                    player['goals'] = '1' if '⚽' in key_events or '进球' in key_events else '0'
                    player['assists'] = '1' if '🔵' in key_events or '助攻' in key_events else '0'
                    player['yellow_cards'] = '1' if '🟨' in key_events or '黃牌' in key_events else '0'
                    player['substituted_in'] = '1' if '⬆️' in key_events or '换上' in key_events else '0'
                    player['substituted_out'] = '1' if '⬇️' in key_events or '换下' in key_events else '0'
                    player['motm'] = '1' if '⭐' in key_events or '全场最佳' in key_events else '0'
                    
                    if len(cells) > 5:
                        player['shots'] = cells[5].text.strip() if cells[5].text.strip() else '0'
                    else:
                        player['shots'] = '0'
                    
                    if len(cells) > 6:
                        player['shots_on_target'] = cells[6].text.strip() if cells[6].text.strip() else '0'
                    else:
                        player['shots_on_target'] = '0'
                    
                    if len(cells) > 7:
                        player['key_passes'] = cells[7].text.strip() if cells[7].text.strip() else '0'
                    else:
                        player['key_passes'] = '0'
                    
                    if len(cells) > 8:
                        pass_rate = cells[8].text.strip()
                        if pass_rate and pass_rate not in ['0%', '']:
                            player['pass_accuracy'] = pass_rate.rstrip('%')
                        else:
                            player['pass_accuracy'] = '0'
                    else:
                        player['pass_accuracy'] = '0'
                    
                    if len(cells) > 9:
                        player['aerial_duels_won'] = cells[9].text.strip() if cells[9].text.strip() else '0'
                    else:
                        player['aerial_duels_won'] = '0'
                    
                    if len(cells) > 10:
                        player['physical_duels'] = cells[10].text.strip() if cells[10].text.strip() else '0'
                    else:
                        player['physical_duels'] = '0'
                    
                    if not player['name'] or player['name'] in ['', '球員', 'Player']:
                        continue
                    
                    players.append(player)
                    
                except Exception:
                    continue
        
        except Exception:
            pass
        
        return players
    
    def save_player_to_json(self, player, match_info):
        """將球員數據保存為JSON文件"""
        try:
            player_json = {
                'match_info': {
                    'date': match_info['date'],
                    'home_team': match_info['home_team'],
                    'away_team': match_info['away_team'],
                    'score': match_info['score'],
                    'season': match_info.get('season', '')
                },
                'player_info': {
                    'name': player.get('full_name', player.get('name', '')),
                    'team': player.get('team', ''),
                    'number': player.get('number', ''),
                    'position': player.get('position', ''),
                    'rating': player.get('rating', ''),
                    'is_home': player.get('is_home', True)
                },
                'regular': {
                    'number': player.get('number', ''),
                    'position': player.get('position', ''),
                    'rating': player.get('rating', ''),
                    'key_events': player.get('key_events', ''),
                    'minutes_played': self._estimate_minutes(player),
                    'is_motm': player.get('motm', '0'),
                    'substituted_in': player.get('substituted_in', '0'),
                    'substituted_out': player.get('substituted_out', '0')
                },
                'attacking': {
                    'goals': player.get('goals', '0'),
                    'assists': player.get('assists', '0'),
                    'shots': player.get('shots', '0'),
                    'shots_on_target': player.get('shots_on_target', '0'),
                    'key_passes': player.get('key_passes', '0'),
                    'big_chances_missed': '0',
                    'shots_from_set_pieces': '0',
                    'goals_from_open_play': player.get('goals', '0'),
                    'penalties_scored': '0',
                    'hit_woodwork': '0'
                },
                'defensive': {
                    'tackles': '0',
                    'interceptions': '0',
                    'clearances': '0',
                    'headed_clearances': '0',
                    'blocks': '0',
                    'aerial_duels_won': player.get('aerial_duels_won', '0'),
                    'aerial_duels_lost': '0',
                    'duels_won': player.get('physical_duels', '0'),
                    'duels_lost': '0',
                    'fouls_committed': '0',
                    'fouls_drawn': '0',
                    'yellow_cards': player.get('yellow_cards', '0'),
                    'red_cards': player.get('red_cards', '0'),
                    'own_goals': '0',
                    'errors_leading_to_goal': '0'
                },
                'passing': {
                    'passes': '0',
                    'passes_completed': '0',
                    'pass_accuracy': player.get('pass_accuracy', '0'),
                    'key_passes': player.get('key_passes', '0'),
                    'crosses': '0',
                    'crosses_completed': '0',
                    'through_balls': '0',
                    'through_balls_completed': '0',
                    'long_passes': '0',
                    'long_passes_completed': '0',
                    'short_passes': '0',
                    'short_passes_completed': '0',
                    'backward_passes': '0',
                    'assists': player.get('assists', '0'),
                    'second_assists': '0',
                    'chances_created': player.get('key_passes', '0')
                }
            }
            
            safe_name = self._safe_filename(player.get('name', 'unknown'))
            safe_team = self._safe_filename(player.get('team', 'unknown'))
            date_str = match_info['date'].replace('-', '')
            
            filename = f"{safe_name}_{safe_team}_{date_str}.json"
            filepath = os.path.join(self.output_dir, "players", filename)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(player_json, f, ensure_ascii=False, indent=2)
            
            self.player_count += 1
            return True
            
        except Exception as e:
            print(f"保存球員JSON錯誤: {e}")
            return False
    
    def _safe_filename(self, name):
        if not name:
            return 'unknown'
        return ''.join(c if c.isalnum() or c in ' -_' else '_' for c in str(name))
    
    def _estimate_minutes(self, player):
        key_events = player.get('key_events', '')
        
        if '⬇️' in key_events or '换下' in key_events:
            time_match = re.search(r"(\d+)'", key_events)
            if time_match:
                return time_match.group(1)
        
        if '⬆️' in key_events or '换上' in key_events:
            time_match = re.search(r"(\d+)'", key_events)
            if time_match:
                return str(90 - int(time_match.group(1)))
        
        return '90'
    
    def save_team_data_to_csv(self):
        """保存球隊數據到CSV"""
        try:
            self.team_data.sort(key=lambda x: x.get('match_date', ''))
            
            csv_path = os.path.join(self.output_dir, "teams", "aleague_matches.csv")
            
            headers = [
                'Div', 'Date', 'Time', 'HomeTeam', 'AwayTeam',
                'FTHG', 'FTAG', 'FTR',
                'HTHG', 'HTAG', 'HTR',
                'Referee',
                'HS', 'AS',
                'HST', 'AST',
                'HF', 'AF',
                'HC', 'AC',
                'HY', 'AY',
                'HR', 'AR',
                'Season'
            ]
            
            with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=headers)
                writer.writeheader()
                
                for match in self.team_data:
                    row = {
                        'Div': match.get('league', 'A-League'),
                        'Date': match.get('match_date', ''),
                        'Time': match.get('match_time', ''),
                        'HomeTeam': match.get('home_team', ''),
                        'AwayTeam': match.get('away_team', ''),
                        'FTHG': match.get('home_goals', 0),
                        'FTAG': match.get('away_goals', 0),
                        'FTR': match.get('result', ''),
                        'HTHG': match.get('home_half_goals', 0),
                        'HTAG': match.get('away_half_goals', 0),
                        'HTR': match.get('half_result', ''),
                        'Referee': match.get('referee', ''),
                        'HS': match.get('home_shots', ''),
                        'AS': match.get('away_shots', ''),
                        'HST': match.get('home_shots_on_target', ''),
                        'AST': match.get('away_shots_on_target', ''),
                        'HF': match.get('home_fouls', ''),
                        'AF': match.get('away_fouls', ''),
                        'HC': match.get('home_corners', ''),
                        'AC': match.get('away_corners', ''),
                        'HY': match.get('home_yellow_cards', ''),
                        'AY': match.get('away_yellow_cards', ''),
                        'HR': match.get('home_red_cards', ''),
                        'AR': match.get('away_red_cards', ''),
                        'Season': match.get('season', '')
                    }
                    writer.writerow(row)
            
            print(f"\n球隊數據已保存至: {csv_path}")
            return True
            
        except Exception as e:
            print(f"保存球隊CSV錯誤: {e}")
            return False
    
    def process_match(self, page, match_data, match_date):
        """處理單場比賽"""
        live_tab = None
        try:
            if not match_data.get('match_id'):
                print(f"    警告: 沒有比賽ID，跳過 {match_data['home_team']} vs {match_data['away_team']}")
                return False
            
            detail_url = f"https://live.titan007.com/detail/{match_data['match_id']}cn.htm"
            print(f"  >>> 正在處理: {match_data['home_team']} vs {match_data['away_team']} (ID: {match_data['match_id']})")
            
            browser = page.browser
            current_tab_id = page.tab_id
            live_tab = browser.new_tab(detail_url)
            browser.activate_tab(live_tab.tab_id)
            
            time.sleep(2)
            
            if not live_tab.ele('tag:body', timeout=10):
                print(f"    頁面加載失敗")
                return False
            
            home_stats, away_stats = self.get_match_stats_from_page(live_tab, match_data)
            
            # 解析比分
            score_parts = match_data['score'].split('-')
            home_goals = int(score_parts[0]) if len(score_parts) > 0 and score_parts[0].isdigit() else 0
            away_goals = int(score_parts[1]) if len(score_parts) > 1 and score_parts[1].isdigit() else 0
            
            half_score_parts = match_data['half_score'].split('-')
            home_half_goals = int(half_score_parts[0]) if len(half_score_parts) > 0 and half_score_parts[0].isdigit() else 0
            away_half_goals = int(half_score_parts[1]) if len(half_score_parts) > 1 and half_score_parts[1].isdigit() else 0
            
            result = 'D' if home_goals == away_goals else ('H' if home_goals > away_goals else 'A')
            half_result = 'D' if home_half_goals == away_half_goals else ('H' if home_half_goals > away_half_goals else 'A')
            
            match_info = {
                'date': match_date.strftime('%Y-%m-%d'),
                'home_team': match_data['home_team'],
                'away_team': match_data['away_team'],
                'score': match_data['score'],
                'season': self.get_season(match_date)
            }
            
            team_record = {
                'league': 'A-League',
                'match_date': match_date.strftime('%Y-%m-%d'),
                'match_time': match_data['match_time'],
                'home_team': match_data['home_team'],
                'away_team': match_data['away_team'],
                'home_goals': home_goals,
                'away_goals': away_goals,
                'result': result,
                'home_half_goals': home_half_goals,
                'away_half_goals': away_half_goals,
                'half_result': half_result,
                'home_shots': home_stats.get('Shots', '') if home_stats else '',
                'away_shots': away_stats.get('Shots', '') if away_stats else '',
                'home_shots_on_target': home_stats.get('Shots_on_Target', '') if home_stats else '',
                'away_shots_on_target': away_stats.get('Shots_on_Target', '') if away_stats else '',
                'home_fouls': home_stats.get('Fouls', '') if home_stats else '',
                'away_fouls': away_stats.get('Fouls', '') if away_stats else '',
                'home_corners': home_stats.get('Corners', '') if home_stats else '',
                'away_corners': away_stats.get('Corners', '') if away_stats else '',
                'home_yellow_cards': home_stats.get('Yellow_Cards', '') if home_stats else '',
                'away_yellow_cards': away_stats.get('Yellow_Cards', '') if away_stats else '',
                'home_red_cards': home_stats.get('Red_Cards', '') if home_stats else '',
                'away_red_cards': away_stats.get('Red_Cards', '') if away_stats else '',
                'season': self.get_season(match_date)
            }
            
            self.team_data.append(team_record)
            
            home_players, away_players = self.get_player_data_from_page(live_tab, match_info)
            
            for player in home_players:
                self.save_player_to_json(player, match_info)
            
            for player in away_players:
                self.save_player_to_json(player, match_info)
            
            print(f"    完成: {match_data['score']} | 球員: {len(home_players) + len(away_players)}人")
            return True
            
        except Exception as e:
            print(f"處理比賽錯誤: {e}")
            return False
        finally:
            if live_tab:
                try:
                    browser = page.browser
                    browser.close_tabs(live_tab.tab_id)
                    browser.activate_tab(current_tab_id)
                except:
                    pass
    
    def get_season(self, date):
        year = date.year
        month = date.month
            
        if month >= 10:
            return f"{year}-{year + 1}"
        else:
            return f"{year - 1}-{year}"
    
    def crawl(self, start_date, end_date):
        """執行爬取"""
        print(f"開始爬取澳職數據: {start_date.strftime('%Y-%m-%d')} 至 {end_date.strftime('%Y-%m-%d')}")
        
        date_list = []
        current_date = start_date
        
        while current_date <= end_date:
            date_list.append(current_date)
            current_date += timedelta(days=1)
        
        print(f"共 {len(date_list)} 個日期\n")
        
        web_page = None
        
        try:
            web_page = self.create_browser_instance()
            
            for i, date_obj in enumerate(date_list):
                date_str = date_obj.strftime('%Y%m%d')
                print(f"[{i+1}/{len(date_list)}] 日期: {date_obj.strftime('%Y-%m-%d')}")
                
                try:
                    url = f'https://bf.titan007.com/football/Over_{date_str}.htm'
                    web_page.get(url)
                    self.wait_with_random_delay()
                    
                    match_rows = web_page.eles('xpath://tr[@height="18" and contains(@bgcolor, "#")]')
                    if not match_rows:
                        match_rows = web_page.eles('xpath://tr[contains(@id, "tr1_")]')
                    
                    print(f"  找到 {len(match_rows)} 行數據")
                    
                    match_count = 0
                    for row in match_rows:
                        match_data = self.extract_match_data(row)
                        if match_data:
                            success = self.process_match(web_page, match_data, date_obj)
                            if success:
                                match_count += 1
                            self.wait_with_random_delay(0.5, 1.0)
                    
                    print(f"  完成 {match_count} 場澳職比賽\n")
                    
                except Exception as e:
                    print(f"  處理日期 {date_str} 錯誤: {e}\n")
                
                time.sleep(random.uniform(1, 2))
            
        except Exception as e:
            print(f"爬取過程錯誤: {e}")
        finally:
            if web_page:
                try:
                    web_page.quit()
                except:
                    pass
        
        print("保存數據...")
        self.save_team_data_to_csv()
        
        print(f"\n{'='*60}")
        print(f"爬取完成!")
        print(f"球隊數據: {len(self.team_data)} 場比賽")
        print(f"球員數據: {self.player_count} 個球員文件")
        print(f"數據保存在: {self.output_dir}")
        print(f"{'='*60}")


def main():
    """主函數"""
    start_date = datetime(2022, 11, 8)
    end_date = datetime(2025, 1, 24)
    
    crawler = ALeagueCrawler(output_dir="aleague_data_output")
    crawler.crawl(start_date, end_date)


if __name__ == '__main__':
    main()
