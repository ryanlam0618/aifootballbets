import sys
import os
import time
import random
from datetime import datetime, timedelta
from PyQt5.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QWidget, 
                             QLabel, QLineEdit, QPushButton, QTextEdit, QProgressBar,
                             QDateEdit, QMessageBox, QFrame, QSplitter, QCheckBox, QSpinBox)
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QDate

# 导入爬虫所需库
from DrissionPage import WebPage, ChromiumOptions
from openpyxl import Workbook, load_workbook
import re
from multiprocessing import Pool, cpu_count
import pandas as pd


class FootballCrawler:
    """足球数据爬虫类"""
    

    
    @staticmethod
    def get_chrome_path():
        """获取Chrome浏览器路径"""
        possible_paths = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            r"D:\Program Files\Google\Chrome\Application\chrome.exe",
            f"{os.getcwd()}\\images\\Chrome\\chrome.exe"
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
    def wait_with_random_delay(min_seconds=1.0, max_seconds=1.5):
        """优化后的随机延时"""
        delay = random.uniform(min_seconds, max_seconds)
        time.sleep(delay)

        # 添加随机的小暂停，更接近人类行为
        micro_pauses = random.randint(0, 3)
        for _ in range(micro_pauses):
            time.sleep(random.uniform(0.1, 0.3))

    @staticmethod
    def human_like_behavior(web_page):
        """模拟人类浏览行为"""
        # 随机滚动页面
        scroll_actions = random.randint(1, 3)
        for _ in range(scroll_actions):
            web_page.run_js('window.scrollBy(0, %d)' % random.randint(100, 500))
            time.sleep(random.uniform(0.5, 1.5))

    @staticmethod
    def create_browser_instance():
        """创建浏览器实例"""
        co = ChromiumOptions()
        chrome_path = FootballCrawler.get_chrome_path()
        co.headless(True)

        # 添加更多浏览器选项以提高稳定性
        co.auto_port(True)  # 自动选择端口
        co.no_js(False)  # 启用JS
        co.mute(True)  # 静音

        # 设置用户代理轮换
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/93.0.4577.63 Safari/537.36"
        ]
        co.set_user_agent(random.choice(user_agents))

        if chrome_path:
            co.set_browser_path(chrome_path)

        return WebPage('d', chromium_options=co)

    @staticmethod
    def get_time_period(date_obj):
        """根据日期判断所属时间段"""
        # 确保比较的对象类型一致，都使用date类型
        period1_end = datetime(2022, 10, 25).date()
        period2_end = datetime(2022, 11, 8).date()
        
        # 如果date_obj是datetime，转换为date
        if hasattr(date_obj, 'date'):
            compare_date = date_obj.date()
        else:
            compare_date = date_obj
        
        if compare_date < period1_end:
            return "period1"
        elif compare_date <= period2_end:
            return "period2"
        else:
            return "period3"

    @staticmethod
    def extract_match_data(tr_element, time_period="period3"):
        """从表格行中提取比赛数据，根据时间段采用不同的解析策略"""
        try:
            # 提取各列数据
            tds = tr_element.eles('tag:td')
            if not tds:
                return None

            # 根据时间段调用不同的解析方法
            if time_period == "period1":
                return FootballCrawler._extract_match_data_period1(tds, tr_element.attrs)
            elif time_period == "period2":
                return FootballCrawler._extract_match_data_period2(tds, tr_element.attrs)
            else:
                return FootballCrawler._extract_match_data_period3(tds, tr_element.attrs)
        except Exception as e:
            print(f"提取比赛数据时出错: {e}")
            return None
    
    @staticmethod
    def _extract_match_data_period3(tds, row_attrs):
        """20221108之后的时间段 - 固定表头结构"""
        try:
            match_id = row_attrs.get('sid', '')
            
            league = tds[0].text.strip() if len(tds) > 0 else ""
            match_time = tds[1].text.strip() if len(tds) > 1 else ""
            status = tds[2].text.strip() if len(tds) > 2 else ""
            home_team = tds[3].text.strip() if len(tds) > 3 else ""
            
            score = ""
            if len(tds) > 4:
                score_elements = tds[4].eles('tag:font')
                if len(score_elements) >= 2:
                    score = f"{score_elements[0].text}-{score_elements[1].text}"
            
            away_team = tds[5].text.strip() if len(tds) > 5 else ""
            
            half_score = ""
            if len(tds) > 6:
                half_elements = tds[6].eles('tag:font')
                if len(half_elements) >= 2:
                    half_score = f"{half_elements[0].text}-{half_elements[1].text}"
            
            asian_handicap = tds[7].text.strip() if len(tds) > 7 else ""
            goals = tds[8].text.strip() if len(tds) > 8 else ""
            
            return {
                'match_id': match_id,
                'league': league,
                'match_time': match_time,
                'status': status,
                'home_team': home_team,
                'score': score,
                'away_team': away_team,
                'half_score': half_score,
                'asian_handicap': asian_handicap,
                'goals': goals
            }
        except Exception as e:
            print(f"解析period3数据时出错: {e}")
            return None
    
    @staticmethod
    def _extract_match_data_period1(tds, row_attrs):
        """20221025之前的时间段 - 动态表头结构"""
        try:
            match_id = row_attrs.get('sid', '')
            column_indices = FootballCrawler._detect_column_indices(tds)
            
            league = tds[column_indices['league']].text.strip()
            match_time = tds[column_indices['match_time']].text.strip()
            status = tds[column_indices['status']].text.strip()
            home_team = tds[column_indices['home_team']].text.strip()
            
            score_idx = column_indices['score']
            score = ""
            if score_idx < len(tds):
                score_elements = tds[score_idx].eles('tag:font')
                if len(score_elements) >= 2:
                    score = f"{score_elements[0].text}-{score_elements[1].text}"
            
            away_team = tds[column_indices['away_team']].text.strip()
            
            half_score_idx = column_indices['half_score']
            half_score = ""
            if half_score_idx < len(tds):
                half_elements = tds[half_score_idx].eles('tag:font')
                if len(half_elements) >= 2:
                    half_score = f"{half_elements[0].text}-{half_elements[1].text}"
            
            asian_handicap = tds[column_indices['asian_handicap']].text.strip()
            goals = tds[column_indices['goals']].text.strip()
            
            return {
                'match_id': match_id,
                'league': league,
                'match_time': match_time,
                'status': status,
                'home_team': home_team,
                'score': score,
                'away_team': away_team,
                'half_score': half_score,
                'asian_handicap': asian_handicap,
                'goals': goals
            }
        except Exception as e:
            print(f"解析period1数据时出错: {e}")
            return None
    
    @staticmethod
    def _extract_match_data_period2(tds, row_attrs):
        """20221025-20221108时间段 - 动态表头结构"""
        return FootballCrawler._extract_match_data_period1(tds, row_attrs)
    
    @staticmethod
    def _detect_column_indices(tds):
        """检测表格列的索引位置"""
        indices = {}
        
        for idx, td in enumerate(tds[:10]):
            text = td.text.strip().lower()
            html = td.html.lower()
            
            if 'league' in html or idx == 0:
                indices['league'] = idx
            
            if ':' in text and ('match_time' not in indices or idx < indices['match_time']):
                indices['match_time'] = idx
            
            if text in ['完', '进行中', '未开始', '推迟']:
                indices['status'] = idx
            
            if '<font' in html and len(td.eles('tag:font')) >= 2:
                if 'score' not in indices or idx < 6:
                    indices['score'] = idx
            
            if idx > 5 and text.isdigit() and 'goals' not in indices:
                indices['goals'] = idx
        
        defaults = {
            'league': 0, 'match_time': 1, 'status': 2,
            'home_team': 3, 'score': 4, 'away_team': 5,
            'half_score': 6, 'asian_handicap': 7, 'goals': 8
        }
        
        for key, default_val in defaults.items():
            if key not in indices:
                indices[key] = default_val
        
        return indices

    @staticmethod
    def get_match_stats_from_live_page(live_page, match_data, time_period="period3"):
        """从现场分析页面获取本场技术统计数据"""
        try:
            home_stats = {'team_name': match_data['home_team'], 'is_home': True}
            away_stats = {'team_name': match_data['away_team'], 'is_home': False}
            
            # 查找技术统计区域
            stat_div = live_page.ele('css:#teamTechDiv_detail', timeout=3)
            if not stat_div:
                print(f"未找到技术统计区域")
                return home_stats, away_stats

            # 定义统计项目映射
            stat_mapping = {
                '角球': 'corner',
                '半场角球': 'half_corner',
                '黄牌': 'yellow_card',
                '红牌': 'red_card',
                '射门': 'shot',
                '射正': 'shot_on_target',
                '进攻': 'attack',
                '危险进攻': 'dangerous_attack',
                '射门不中': 'shot_off_target',
                '射门被挡': 'shot_blocked',
                '任意球': 'free_kick',
                '控球率': 'possession',
                '半场控球率': 'half_possession',
                '传球': 'pass',
                '传球成功率': 'pass_success_rate',
                '犯规': 'foul',
                '越位': 'offside',
                '头球': 'header',
                '头球成功': 'header_success',
                '救球': 'save',
                '铲球': 'tackle',
                '过人': 'dribble',
                '界外球': 'throw_in',
                '中柱': 'hit_woodwork',
                '成功抢断': 'interception',
                '阻截': 'block',
                '助攻': 'assist',
                '长传': 'long_pass',
                '成功传中': 'successful_cross'
            }

            # 根据不同时间段使用不同的解析策略
            if time_period == "period2":
                # 20221025-20221108: 使用<ul><li>列表结构
                list_items = stat_div.eles('css:#teamTechDiv li.lists')
                parsed_count = 0
                for idx, item in enumerate(list_items, 1):
                    try:
                        # 查找data div中的三个span
                        spans = item.eles('css:.data span')
                        if len(spans) >= 3:
                            home_value = spans[0].text.strip()
                            stat_name = spans[1].text.strip()
                            away_value = spans[2].text.strip()
                            
                            # print(f"  第{idx}项: {stat_name} = {home_value} vs {away_value}")
                            
                            # 查找对应的映射键（精确匹配）
                            matched = False
                            for key, mapped_key in stat_mapping.items():
                                if key == stat_name:
                                    home_stats[mapped_key] = home_value
                                    away_stats[mapped_key] = away_value
                                    matched = True
                                    parsed_count += 1
                                    # print(f"    ✓ 已记录: {key} -> {mapped_key}")
                                    break
                            
                            if not matched:
                                print(f"    ✗ 未匹配: {stat_name}")
                        else:
                            print(f"  第{idx}项: 跳过 (只有{len(spans)}个span)")
                    except Exception as e:
                        print(f"  第{idx}项: 解析错误 - {e}")
                        continue
                
                # print(f"  成功解析 {parsed_count} 项技术统计数据")
            else:
                # period1 和 period3: 使用<table>表格结构
                stat_table = stat_div.ele('tag:table', timeout=2)
                if stat_table:
                    rows = stat_table.eles('tag:tr')
                    parsed_count = 0
                    row_idx = 0
                    for row in rows:
                        row_idx += 1
                        try:
                            cells = row.eles('tag:td')
                            if len(cells) >= 5:  # 需要至少5个单元格
                                # 提取数据 (第2列是主队数值, 第3列是统计名称, 第4列是客队数值)
                                home_value = cells[1].text.strip()
                                stat_name = cells[2].text.strip()
                                away_value = cells[3].text.strip()
                                
                                # print(f"  第{row_idx}行: {stat_name} = {home_value} vs {away_value}")
                                
                                # 查找对应的映射键（精确匹配）
                                matched = False
                                for key, mapped_key in stat_mapping.items():
                                    if key == stat_name:  # 使用精确匹配，不是模糊匹配
                                        home_stats[mapped_key] = home_value
                                        away_stats[mapped_key] = away_value
                                        matched = True
                                        parsed_count += 1
                                        # print(f"    ✓ 已记录: {key} -> {mapped_key}")
                                        break
                                
                                if not matched:
                                    print(f"    ✗ 未匹配: {stat_name}")
                            else:
                                print(f"  第{row_idx}行: 跳过 (只有{len(cells)}个单元格)")
                        except Exception as e:
                            print(f"  第{row_idx}行: 解析错误 - {e}")
                            continue
                    
                    # print(f"  成功解析 {parsed_count} 项技术统计数据")
                    # print(f"  总计 {len(rows)} 行, 有效数据 {parsed_count} 项")

            return home_stats, away_stats

        except Exception as e:
            print(f"获取技术统计时出错: {e}")
            # 返回空统计数据而不是None，让程序继续运行
            return {'team_name': match_data['home_team'], 'is_home': True}, {'team_name': match_data['away_team'], 'is_home': False}

    @staticmethod
    def get_player_stats_from_page(live_page, match_data, current_date, time_period=None):
        """
        从球员统计页面获取双方球员数据
        返回: 主队和客队的球员数据列表
        """
        player_tab = None
        try:
            # 检测时间段（如果未提供参数，则根据日期自动检测）
            if time_period is None:
                time_period = FootballCrawler.get_time_period(current_date)
            browser = live_page.browser
            current_tab_id = live_page.tab_id
            
            # Period1 (20221025之前): 球员统计是一个链接，点击后打开新页面
            if time_period == "period1":
                # 查找球员统计链接
                player_link = live_page.ele('xpath://a[contains(text(), "球员统计") or contains(@href, "Count")]', timeout=5)
                if not player_link:
                    print("未找到球员统计链接")
                    return None, None
                
                print("点击球员统计按钮...")
                
                # 获取链接的href属性，如果是相对路径则转换为完整URL
                try:
                    href = player_link.attr('href') or ''
                except:
                    href = ''
                if href and not href.startswith('http'):
                    # 如果是相对路径，构建完整URL
                    if href.startswith('//'):
                        full_url = f"https:{href}"
                    else:
                        # 获取当前页面的基础URL
                        current_url = live_page.url
                        if current_url:
                            from urllib.parse import urljoin
                            full_url = urljoin(current_url, href)
                        else:
                            full_url = f"https://live.titan007.com{href}" if href.startswith('/') else f"https://live.titan007.com/{href}"
                    
                    print(f"直接访问球员统计页面: {full_url}")
                    
                    # 创建新标签页直接访问球员统计页面
                    player_tab = browser.new_tab(full_url)
                    browser.activate_tab(player_tab.tab_id)
                else:
                    # 使用JavaScript点击链接，避免元素不可见问题
                    live_page.run_js('arguments[0].click()', player_link)
                    
                    # 等待新标签页打开
                    time.sleep(2)
                    
                    # 获取最新打开的标签页
                    player_tab = browser.latest_tab
                    if not player_tab:
                        print("未能获取新打开的球员统计标签页")
                        return None, None
                    
                    # 激活标签页
                    browser.activate_tab(player_tab.tab_id)
                
                # 等待页面加载
                time.sleep(1)
                
                # 查找球员统计表格
                player_stats = {
                    'home_players': [],
                    'away_players': []
                }
                
                # 等待页面元素加载
                time.sleep(2)
                
                # Period1 特殊处理：查找 class 为 alltable 的表格
                all_tables = player_tab.eles('css:table.alltable')
                if len(all_tables) >= 2:
                    # 第一个是主队，第二个是客队
                    player_stats['home_players'] = FootballCrawler.parse_player_table(all_tables[0], match_data['home_team'])
                    player_stats['away_players'] = FootballCrawler.parse_player_table(all_tables[1], match_data['away_team'])
                    return player_stats['home_players'], player_stats['away_players']
                elif len(all_tables) == 1:
                    # 只有主队数据
                    player_stats['home_players'] = FootballCrawler.parse_player_table(all_tables[0], match_data['home_team'])
                    player_stats['away_players'] = []
                    return player_stats['home_players'], player_stats['away_players']
                
                # 如果没找到alltable表格，尝试其他方法
                player_tables = player_tab.eles('tag:table')
                if player_tables:
                    for table in player_tables:
                        table_html = table.html
                        table_text = table.text
                        
                        # 检查表格类型，根据表头判断是主队还是客队
                        if 'Home' in table_html or match_data['home_team'] in table_text:
                            player_stats['home_players'] = FootballCrawler.parse_player_table(table, match_data['home_team'])
                        elif 'Away' in table_html or match_data['away_team'] in table_text:
                            player_stats['away_players'] = FootballCrawler.parse_player_table(table, match_data['away_team'])
                
                return player_stats['home_players'], player_stats['away_players']
            
            # Period2 和 Period3: 需要点击球员统计按钮来加载数据
            else:
                print("查找球员统计按钮...")
                
                # 等待页面完全加载
                time.sleep(2)
                
                # 尝试多种方式查找球员统计按钮
                player_stat_button = None
                
                # 方法1: 直接通过ID查找
                player_stat_button = live_page.ele('css:#menu1', timeout=5)
                
                # if not player_stat_button:
                #     # 方法2: 通过文本内容查找
                #     print("尝试通过文本内容查找...")
                #     player_stat_button = live_page.ele('xpath://li[contains(text(), "球员统计")]', timeout=3)
                
                # if not player_stat_button:
                #     # 方法3: 查找整个菜单结构
                #     print("尝试查找菜单结构...")
                #     odds_menu = live_page.ele('css:#odds_menu', timeout=3)
                #     if odds_menu:
                #         print("找到odds_menu，查找其中的li元素...")
                #         menu_items = odds_menu.eles('tag:li')
                #         for item in menu_items:
                #             if '球员统计' in item.text:
                #                 player_stat_button = item
                #                 print("在odds_menu中找到球员统计按钮")
                #                 break
                
                # if not player_stat_button:
                #     # 方法4: 打印页面结构帮助调试
                #     print("页面结构调试信息:")
                #     menus = live_page.eles('tag:ul')
                #     for menu in menus:
                #         print(f"找到ul: {menu.attr('id')}")
                #         items = menu.eles('tag:li')
                #         for item in items:
                #             print(f"  - li: {item.text} (id: {item.attr('id')})")
                    
                #     print("未找到球员统计按钮")
                #     return None, None
                
                # 检查按钮是否存在且可点击（直接尝试点击）
                try:
                    print("点击球员统计按钮...")
                    
                    # 使用JavaScript点击，避免元素不可见问题
                    live_page.run_js('arguments[0].click()', player_stat_button)
                    
                    # 等待球员统计数据加载
                    time.sleep(3)
                    
                    # 查找球员统计表格
                    player_stats = {
                        'home_players': [],
                        'away_players': []
                    }
                    
                    # 尝试查找球员统计表格
                    player_tables = live_page.eles('tag:table')
                    if player_tables:
                        print(f"找到 {len(player_tables)} 个表格")
                        
                        # 检查表格属性，确定主队和客队表格
                        for table in player_tables:
                            table_html = table.html
                            table_text = table.text
                            
                            # 检查是否为混合表格（同时包含tcol和tcol2属性）
                            if 'tcol=' in table_html and 'tcol2=' in table_html:
                                print("检测到混合表格（同时包含tcol和tcol2属性）")
                                # 分别解析主队和客队数据，但只覆盖尚未找到的数据
                                home_players = FootballCrawler.parse_player_table(table, 'home')
                                away_players = FootballCrawler.parse_player_table(table, 'away')
                                
                                # 只有当对应队伍的数据尚未找到时，才覆盖
                                if not player_stats['home_players']:
                                    player_stats['home_players'] = home_players
                                if not player_stats['away_players']:
                                    player_stats['away_players'] = away_players
                                
                                print(f"主队球员数: {len(home_players)}")
                                print(f"客队球员数: {len(away_players)}")
                                print(f"当前主队球员数: {len(player_stats['home_players'])}")
                                print(f"当前客队球员数: {len(player_stats['away_players'])}")
                            
                            # 检查是否为主队表格（包含tcol属性）
                            elif 'tcol=' in table_html and 'tcol2=' not in table_html:
                                print("检测到主队表格（tcol属性）")
                                # 只有当主队数据尚未找到时，才覆盖
                                if not player_stats['home_players']:
                                    player_stats['home_players'] = FootballCrawler.parse_player_table(table, 'home')
                                    print(f"主队球员数: {len(player_stats['home_players'])}")
                            
                            # 检查是否为客队表格（包含tcol2属性）
                            elif 'tcol2=' in table_html and 'tcol=' not in table_html:
                                print("检测到客队表格（tcol2属性）")
                                # 只有当客队数据尚未找到时，才覆盖
                                if not player_stats['away_players']:
                                    player_stats['away_players'] = FootballCrawler.parse_player_table(table, 'away')
                                    print(f"客队球员数: {len(player_stats['away_players'])}")
                            
                            # 如果以上都不匹配，使用原有的逻辑
                            else:
                                # 检查表格类型，根据表头判断是主队还是客队
                                if 'Home' in table_html or match_data['home_team'] in table_text:
                                    if not player_stats['home_players']:
                                        player_stats['home_players'] = FootballCrawler.parse_player_table(table, 'home')
                                elif 'Away' in table_html or match_data['away_team'] in table_text:
                                    if not player_stats['away_players']:
                                        player_stats['away_players'] = FootballCrawler.parse_player_table(table, 'away')
                    
                    # 如果上面的方法没找到，尝试直接查找class为homeTable和awayTable的表格
                    if not player_stats['home_players']:
                        home_table = live_page.ele('css:table.homeTable, table[id*="home" i], table[class*="home" i]')
                        if home_table:
                            player_stats['home_players'] = FootballCrawler.parse_player_table(home_table, match_data['home_team'])
                    
                    if not player_stats['away_players']:
                        away_table = live_page.ele('css:table.awayTable, table[id*="away" i], table[class*="away" i]')
                        if away_table:
                            player_stats['away_players'] = FootballCrawler.parse_player_table(away_table, match_data['away_team'])
                    
                    # 如果仍没找到，尝试通用选择器
                    if not player_stats['home_players'] and not player_stats['away_players']:
                        all_tables = live_page.eles('css:table.datatable, table.playerStatsTable, table')
                        if len(all_tables) >= 2:
                            # 假设第一个是主队，第二个是客队
                            player_stats['home_players'] = FootballCrawler.parse_player_table(all_tables[0], match_data['home_team'])
                            player_stats['away_players'] = FootballCrawler.parse_player_table(all_tables[1], match_data['away_team'])
                        elif len(all_tables) == 1:
                            # 如果只有一个表格，可能包含了两队数据
                            table = all_tables[0]
                            players = FootballCrawler.parse_player_table(table, match_data['home_team'])
                            # 假设前一半是主队，后一半是客队
                            mid_point = len(players) // 2
                            player_stats['home_players'] = players[:mid_point]
                            player_stats['away_players'] = players[mid_point:]
                    
                    return player_stats['home_players'], player_stats['away_players']
                except Exception as e:
                    print(f"球员统计按钮操作出错: {e}")
                    return None, None

        except Exception as e:
            print(f"获取球员统计数据时出错: {e}")
            import traceback
            traceback.print_exc()
            
            # 出错时也要尝试关闭标签页
            if player_tab and live_page:
                try:
                    browser = live_page.browser
                    current_tab_id = live_page.tab_id
                    browser.close_tabs(player_tab.tab_id)
                    browser.activate_tab(current_tab_id)
                except Exception:
                    pass
            
            return None, None

    @staticmethod
    def parse_player_table(player_table, team_name):
        """
        解析球员数据表格
        """
        players = []
        
        try:
            # 获取所有行
            rows = player_table.eles('tag:tr')
            if len(rows) < 2:
                return players

            # 检测表头，建立列名到索引的映射
            header_row = rows[0]
            header_cells = header_row.eles('tag:th')
            column_map = {}
            
            for idx, cell in enumerate(header_cells):
                col_text = cell.text.strip()
                if col_text == '号码':
                    column_map['number'] = idx
                elif col_text == '球员':
                    column_map['player_name'] = idx
                elif col_text == '位置':
                    column_map['position'] = idx
                elif col_text == '评分':
                    column_map['rating'] = idx
                elif col_text == '关键事件':
                    column_map['key_events'] = idx
                elif col_text == '射门':
                    column_map['shots'] = idx
                elif col_text == '射正':
                    column_map['shots_on_target'] = idx
                elif col_text == '关键传球':
                    column_map['key_passes'] = idx
                elif col_text == '传球成功率':
                    column_map['pass_success_rate'] = idx
                elif col_text == '争顶成功':
                    column_map['aerial_duels_won'] = idx
                elif col_text == '身体接触':
                    column_map['physical_duels'] = idx

            # 跳过表头行，从第二行开始解析
            for row in rows[1:]:
                try:
                    # 获取所有单元格
                    cells = row.eles('tag:td')
                    if len(cells) < 5:  # 至少需要基本数据
                        continue
                    
                    # 检查该行是属于主队还是客队
                    # 通过检查第一个单元格的tcol属性来判断
                    first_cell = cells[0] if len(cells) > 0 else None
                    if not first_cell:
                        continue
                        
                    # 检查tcol或tcol2属性
                    first_cell_html = first_cell.html
                    is_home_player = 'tcol="0"' in first_cell_html
                    is_away_player = 'tcol2="0"' in first_cell_html
                    
                    # 如果该行不属于当前要解析的队伍，跳过
                    if (team_name == 'home' and not is_home_player) or (team_name == 'away' and not is_away_player):
                        continue

                    # 解析球员数据，使用列映射来提取正确的数据
                    player_data = {
                        'team_name': team_name,
                        'number': cells[column_map.get('number', 0)].text.strip() if column_map.get('number', 0) < len(cells) else '',
                        'player_name': cells[column_map.get('player_name', 1)].text.strip() if column_map.get('player_name', 1) < len(cells) else '',
                        'position': cells[column_map.get('position', 2)].text.strip() if column_map.get('position', 2) < len(cells) else '',
                        'rating': cells[column_map.get('rating', 3)].text.strip() if column_map.get('rating', 3) < len(cells) else '',
                        'key_events': cells[column_map.get('key_events', 4)].text.strip() if column_map.get('key_events', 4) < len(cells) else '',
                        'shots': cells[column_map.get('shots', 5)].text.strip() if column_map.get('shots', 5) < len(cells) else '',
                        'shots_on_target': cells[column_map.get('shots_on_target', 6)].text.strip() if column_map.get('shots_on_target', 6) < len(cells) else '',
                        'key_passes': cells[column_map.get('key_passes', 7)].text.strip() if column_map.get('key_passes', 7) < len(cells) else '',
                        'pass_success_rate': cells[column_map.get('pass_success_rate', 8)].text.strip() if column_map.get('pass_success_rate', 8) < len(cells) else '',
                        'aerial_duels_won': cells[column_map.get('aerial_duels_won', 9)].text.strip() if column_map.get('aerial_duels_won', 9) < len(cells) else '',
                        'physical_duels': cells[column_map.get('physical_duels', 10)].text.strip() if column_map.get('physical_duels', 10) < len(cells) else ''
                    }
                    
                    # 特别处理第4列（索引为4），提取title属性中的详细时间信息
                    if len(cells) > 4:
                        event_cell_html = cells[4].html  # 直接获取HTML内容
                        full_event_info = []
                        
                        # 首先获取单元格中的直接文本内容
                        direct_text = cells[4].text.strip()
                        if direct_text:
                            full_event_info.append(direct_text)
                        
                        # 然后提取所有带title属性的元素的title内容
                        if 'title=' in event_cell_html:
                            # 更精确的正则表达式，匹配title属性中的完整内容
                            title_pattern = r'title\s*=\s*"([^"]*)"'
                            titles = re.findall(title_pattern, event_cell_html, re.IGNORECASE)
                            
                            if titles:
                                full_event_info.extend(titles)
                        
                        # 合并所有事件信息
                        if full_event_info:
                            combined_events = '; '.join(full_event_info)
                            existing_events = player_data['key_events']
                            
                            # 如果既有原有事件又有新提取的事件，则合并它们
                            if existing_events and combined_events:
                                player_data['key_events'] = f"{existing_events}; {combined_events}"
                            else:
                                player_data['key_events'] = combined_events or existing_events
                    
                    # 过滤空数据，确保有球员姓名
                    if player_data['player_name'] and player_data['player_name'] not in ['', '球员', 'Player']:
                        players.append(player_data)
                        
                except Exception:
                    continue

        except Exception:
            pass
        
        return players

    @staticmethod
    def save_match_data_to_excel(match_data, current_date, home_stats, away_stats, home_players=None, away_players=None):
        """保存比赛数据到Excel文件"""
        try:
            # 生成文件名
            date_str = current_date.strftime('%Y%m%d')
            league_clean = re.sub(r'[\\/:*?"<>|]', '', match_data.get('league', ''))
            home_team_clean = re.sub(r'[\\/:*?"<>|]', '', match_data['home_team'])
            away_team_clean = re.sub(r'[\\/:*?"<>|]', '', match_data['away_team'])
            
            # 如果联赛名称不为空，则添加到文件名中
            if league_clean:
                filename = f"{date_str}_{league_clean}_{home_team_clean}_vs_{away_team_clean}.xlsx"
            else:
                filename = f"{date_str}_{home_team_clean}_vs_{away_team_clean}.xlsx"
            
            # 创建工作簿
            wb = Workbook()
            
            # 创建比赛技术统计表
            ws_match = wb.active
            ws_match.title = "比赛技术统计"
            
            # 添加比赛技术统计表头
            match_headers = [
                'Team Name', 'Corner', 'Half Corner', 'Yellow Card', 'Red Card', 'Shot', 'Shot on Target', 'Attack', 'Dangerous Attack', 
                'Shot Off Target', 'Shot Blocked', 'Free Kick', 'Possession', 'Half Possession', 'Pass', 'Pass Success Rate', 
                'Foul', 'Offside', 'Header', 'Header Success', 'Save', 'Tackle', 'Dribble', 'Throw In', 'Hit Woodwork',
                'Interception', 'Block', 'Assist', 'Long Pass', 'Successful Cross'
            ]
            ws_match.append(match_headers)
            
            # 添加主队数据
            home_row = [home_stats.get('team_name', match_data['home_team'])]
            key_mapping = {
                '角球': 'corner', '半场角球': 'half_corner', '黄牌': 'yellow_card', '红牌': 'red_card',
                '射门': 'shot', '射正': 'shot_on_target', '进攻': 'attack',
                '危险进攻': 'dangerous_attack', '射门不中': 'shot_off_target',
                '射门被挡': 'shot_blocked', '任意球': 'free_kick', '控球率': 'possession',
                '半场控球率': 'half_possession', '传球': 'pass', '传球成功率': 'pass_success_rate',
                '犯规': 'foul', '越位': 'offside', '头球': 'header', '头球成功': 'header_success',
                '救球': 'save', '铲球': 'tackle', '过人': 'dribble', '界外球': 'throw_in', '中柱': 'hit_woodwork',
                '成功抢断': 'interception', '阻截': 'block', '助攻': 'assist', '长传': 'long_pass',
                '成功传中': 'successful_cross'
            }
            
            for header in match_headers[1:]:
                key = key_mapping.get(header, header.lower().replace(' ', '_'))
                home_row.append(home_stats.get(key, ''))
            ws_match.append(home_row)
            
            # 添加客队数据
            away_row = [away_stats.get('team_name', match_data['away_team'])]
            for header in match_headers[1:]:
                key = key_mapping.get(header, header.lower().replace(' ', '_'))
                away_row.append(away_stats.get(key, ''))
            ws_match.append(away_row)
            
            # 标记主队
            ws_match.cell(row=2, column=1, value=f"主队 - {home_row[0]}")
            
            # 创建基础数据表
            ws_basic = wb.create_sheet("比赛基础数据")
            ws_basic.append([
                'Date', 'League', 'Match Time', 'Home Team', 'Full Score', 'Away Team', 'Half Score', 'Asian Handicap', 'Goals'
            ])
            
            date_str_ymd = current_date.strftime('%Y-%m-%d')
            ws_basic.append([
                date_str_ymd, match_data['league'], match_data['match_time'],
                match_data['home_team'], match_data['score'], match_data['away_team'],
                match_data['half_score'], match_data['asian_handicap'], match_data['goals']
            ])
            
            # 创建球员数据表（如果有球员数据）
            if home_players or away_players:
                ws_players = wb.create_sheet("球员数据")
                
                # 添加球员数据表头
                player_headers = [
                    'Team Name', 'Number', 'Player', 'Position', 'Rating', 'Key Events', 'Shots', 'Shots on Target', 
                    'Key Passes', 'Pass Success Rate', 'Aerial Duels Won', 'Physical Duels'
                ]
                ws_players.append(player_headers)
                
                # 构建所有球员数据列表，统一写入
                all_players = []
                
                # 添加主队球员数据
                if home_players:
                    for player in home_players:
                        # 根据team_name确定实际队伍名称
                        actual_team_name = match_data['home_team'] if player.get('team_name') == 'home' else player.get('team_name', match_data['home_team'])
                        player_row = [
                            actual_team_name,
                            player.get('number', ''),
                            player.get('player_name', ''),
                            player.get('position', ''),
                            player.get('rating', ''),
                            player.get('key_events', ''),
                            player.get('shots', ''),
                            player.get('shots_on_target', ''),
                            player.get('key_passes', ''),
                            player.get('pass_success_rate', ''),
                            player.get('aerial_duels_won', ''),
                            player.get('physical_duels', '')
                        ]
                        all_players.append(player_row)
                
                # 添加客队球员数据
                if away_players:
                    for player in away_players:
                        # 根据team_name确定实际队伍名称
                        actual_team_name = match_data['away_team'] if player.get('team_name') == 'away' else player.get('team_name', match_data['away_team'])
                        player_row = [
                            actual_team_name,
                            player.get('number', ''),
                            player.get('player_name', ''),
                            player.get('position', ''),
                            player.get('rating', ''),
                            player.get('key_events', ''),
                            player.get('shots', ''),
                            player.get('shots_on_target', ''),
                            player.get('key_passes', ''),
                            player.get('pass_success_rate', ''),
                            player.get('aerial_duels_won', ''),
                            player.get('physical_duels', '')
                        ]
                        all_players.append(player_row)
                
                # 统一写入所有球员数据
                for player_row in all_players:
                    ws_players.append(player_row)
            
            # 保存文件
            files_dir = os.path.join(os.getcwd(), "比赛球员数据")
            if not os.path.exists(files_dir):
                os.makedirs(files_dir)
            
            output_file = os.path.join(files_dir, filename)
            wb.save(output_file)
            
            return True, output_file
            
        except Exception as e:
            return False, str(e)

    @staticmethod
    def get_downloaded_matches_from_folder():
        """从比赛球员数据文件夹中读取所有已下载的比赛信息"""
        try:
            files_dir = os.path.join(os.getcwd(), "比赛球员数据")
            if not os.path.exists(files_dir):
                return {}
            
            import glob
            # 获取所有xlsx文件
            date_files = glob.glob(os.path.join(files_dir, "*.xlsx"))
            
            downloaded_matches = {}
            
            for file_path in date_files:
                try:
                    # 从文件名提取信息
                    # 格式: YYYYMMDD_联赛_主队_vs_客队.xlsx 或 YYYYMMDD_主队_vs_客队.xlsx
                    filename = os.path.basename(file_path)
                    filename_without_ext = os.path.splitext(filename)[0]
                    
                    parts = filename_without_ext.split('_')
                    if len(parts) >= 3:
                        date_str = parts[0]
                        
                        # 判断格式: 是否有联赛名称
                        if len(parts) >= 4 and 'vs' in filename_without_ext:
                            # 格式: YYYYMMDD_联赛_主队_vs_客队
                            league = parts[1]
                            home_team = parts[2]
                            away_team = parts[4] if len(parts) > 4 else parts[3]
                        else:
                            # 格式: YYYYMMDD_主队_vs_客队
                            league = ""
                            home_team = parts[1]
                            away_team = parts[3] if len(parts) > 3 else parts[2]
                        
                        # 构建日期键
                        if date_str not in downloaded_matches:
                            downloaded_matches[date_str] = []
                        
                        downloaded_matches[date_str].append({
                            'league': league,
                            'home_team': home_team,
                            'away_team': away_team,
                            'filename': filename
                        })
                except Exception as e:
                    print(f"解析文件名 {file_path} 时出错: {e}")
                    continue
            
            return downloaded_matches
            
        except Exception as e:
            print(f"读取已下载比赛信息时出错: {e}")
            return {}

    @staticmethod
    def find_match_start_index(match_rows, last_match_info):
        """在比赛行列表中找到最后一场比赛的索引位置"""
        if not last_match_info:
            return 0  # 从第一行开始
        
        for i, row in enumerate(match_rows):
            try:
                match_data = FootballCrawler.extract_match_data(row)
                if match_data:
                    # 比较主客队信息
                    if (match_data['home_team'] == last_match_info['home_team'] and
                        match_data['away_team'] == last_match_info['away_team']):
                        print(f"找到最后一场比赛在索引位置: {i}")
                        return i + 1  # 从下一场比赛开始
            except Exception as e:
                print(f"查找比赛索引时出错: {e}")
                continue
        
        print("未找到最后一场比赛，从第一行开始处理")
        return 0
    
    @staticmethod
    def find_first_undownloaded_match(match_rows, downloaded_matches, date_str):
        """找到第一个未下载的比赛的索引位置"""
        if not downloaded_matches or date_str not in downloaded_matches:
            return 0  # 没有已下载的比赛，从第一行开始
        
        downloaded_list = downloaded_matches[date_str]
        
        for i, row in enumerate(match_rows):
            try:
                match_data = FootballCrawler.extract_match_data(row)
                if not match_data:
                    continue
                
                # 检查这场比赛是否已下载
                is_downloaded = False
                for downloaded in downloaded_list:
                    if (match_data['home_team'] == downloaded['home_team'] and 
                        match_data['away_team'] == downloaded['away_team']):
                        # 如果有联赛信息，也对比一下
                        if downloaded['league'] and match_data.get('league'):
                            if match_data['league'] == downloaded['league']:
                                is_downloaded = True
                                break
                        else:
                            # 没有联赛信息，只比较球队
                            is_downloaded = True
                            break
                
                if not is_downloaded:
                    print(f"第一个未下载的比赛在索引位置: {i}")
                    return i
                    
            except Exception as e:
                print(f"检查比赛是否已下载时出错: {e}")
                continue
        
        print("所有比赛都已下载，跳过该日期")
        return len(match_rows)  # 返回比赛总数，表示全部跳过

    @staticmethod
    def apply_market_filter(web_page, execute_filter=True):
        """应用盘口筛选逻辑"""
        if not execute_filter:
            return
        
        try:
            # 1. 点击"盘口选择"按钮
            goal_select_btn = web_page.ele('xpath://a[contains(text(), "盘口选择") and @class="btn"]', timeout=5)
            if not goal_select_btn:
                goal_select_btn = web_page.ele(
                    'xpath://a[contains(@onclick, "ToggleLayer(\'goalDiv\')") and @class="btn"]', timeout=5)

            if goal_select_btn:
                goal_select_btn.click()
                print("点击盘口选择按钮")
                time.sleep(2)  # 增加等待时间，确保弹窗完全加载

                # 2. 点击"全选"按钮
                select_all_btn = web_page.ele(
                    'xpath://input[@type="button" and @value="全选" and contains(@onclick, "selectGoalData(-1,1)\")]' ,
                    timeout=5)
                if select_all_btn:
                    select_all_btn.click()
                    print("点击全选按钮")
                    time.sleep(1)  # 增加等待时间，确保所有checkbox被选中

                    # 3. 点击未开盘的checkbox
                    # 查找所有checkbox，找到value为空的checkbox（没开盘）
                    checkboxes = web_page.eles('xpath://input[@type="checkbox" and @name="checkbox"]', timeout=5)
                    if checkboxes:
                        # 查找value为空的checkbox（没开盘）
                        unchecked_box = None
                        for checkbox in checkboxes:
                            value = checkbox.attr('value')
                            if value == "":  # 空值表示没开盘
                                unchecked_box = checkbox
                                break

                        # 如果没找到空值的checkbox，使用最后一个
                        if not unchecked_box:
                            unchecked_box = checkboxes[-1]
                            print("未找到空值checkbox，使用最后一个")

                        unchecked_box.click()
                        print("点击未开盘checkbox")
                        time.sleep(0.5)

                        # 4. 点击"确定"按钮
                        confirm_btn = web_page.ele(
                            'xpath://input[@type="button" and @value="确定" and contains(@onclick, "goalDataShow")]' ,
                            timeout=5)
                        if confirm_btn:
                            confirm_btn.click()
                            print("点击确定按钮")
                            time.sleep(1)
                            print("盘口选择完成")
                        else:
                            print("未找到确定按钮")
                    else:
                        print("未找到checkbox")
                else:
                    print("未找到全选按钮")
            else:
                print("未找到盘口选择按钮")
        except Exception as e:
            print(f"执行盘口选择逻辑时出错: {e}")

    @staticmethod
    def process_single_match(web_page, match_data, current_date, time_period="period3", row_element=None):
        """处理单场比赛 - 根据时间段分发到不同的处理函数"""
        if time_period == "period1":
            return FootballCrawler._process_single_match_period1(web_page, match_data, current_date, row_element)
        elif time_period == "period2":
            return FootballCrawler._process_single_match_period2(web_page, match_data, current_date, row_element)
        else:
            return FootballCrawler._process_single_match_period3(web_page, match_data, current_date, row_element)
    
    @staticmethod
    def _check_player_stats_button(live_page):
        """检查现场分析页面是否有球员统计按钮"""
        try:
            # 查找球员统计相关的元素
            player_button_selectors = [
                'css:#playerTechDiv_detail',
                'xpath://a[contains(text(), "球员统计")]',
                'xpath://a[contains(text(), "Player Stats")]',
                'css:.player-stats-button',
                'css:#playerTechIframe',
                'css:.item.btns a.btn',
                'css:a.btn[href*="Count"]',
                'css:a.btn[href*="count"]',
                'css:a[href*="Count"]',
                'css:a[href*="count"]',
                # 添加 Period2/Period3 格式的支持
                'css:#menu1',
                'xpath://li[contains(text(), "球员统计")]',
                'css:#odds_menu li'
            ]
            
            for selector in player_button_selectors:
                try:
                    element = live_page.ele(selector, timeout=2)
                    if element:
                        # 检查元素是否包含球员统计相关文本或链接
                        text = element.text if hasattr(element, 'text') else ''
                        try:
                            href = element.attr('href') or ''
                        except:
                            href = ''
                        
                        if "球员统计" in text or "Player Stats" in text or "Count" in href or "count" in href:
                            print(f"找到球员统计按钮: {selector} - {text} - {href}")
                            return True
                except:
                    continue
            
            # 如果标准选择器没找到，尝试更通用的搜索
            buttons = live_page.eles('css:a.btn')
            for button in buttons:
                text = button.text
                try:
                    href = button.attr('href') or ''
                except:
                    href = ''
                if "球员统计" in text or "Count" in href or "count" in href:
                    print(f"找到球员统计按钮: {text} - {href}")
                    return True
            
            # 最后尝试搜索所有包含"球员统计"文本的链接
            all_links = live_page.eles('tag:a')
            for link in all_links:
                text = link.text
                try:
                    href = link.attr('href') or ''
                except:
                    href = ''
                if "球员统计" in text or "Count" in href or "count" in href:
                    print(f"找到球员统计按钮: {text} - {href}")
                    return True
            
            print("未找到球员统计按钮")
            return False
        except Exception as e:
            print(f"检查球员统计按钮时出错: {e}")
            return False
    
    @staticmethod
    def _detect_page_format(live_page):
        """检测网页的技术统计格式，返回对应的时间段"""
        try:
            # 首先检查period2特有的<ul><li>列表结构（20221025-20221108）
            listbox_div = live_page.ele('css:#teamTechDiv ul.listbox', timeout=2)
            if listbox_div:
                print("检测到网页格式: period2 (20221025-20221108) - 列表结构")
                return "period2"
            
            # 检查技术统计区域
            tech_div = live_page.ele('css:#teamTechDiv_detail', timeout=2)
            if tech_div:
                # 检查是否包含列表结构（period2）
                lists = tech_div.eles('css:li.lists')
                if lists:
                    print("检测到网页格式: period2 (20221025-20221108) - 通过列表项检测")
                    return "period2"
                
                # 检查表格结构
                tables = tech_div.eles('css:table')
                if tables:
                    # 检查每个表格的特征
                    for table in tables:
                        # 检查period1特征：表格宽度800且包含th元素
                        width = table.attr('width')
                        if width == '800':
                            # 检查是否有th元素（period1特征）
                            th_elements = table.eles('css:th')
                            if th_elements:
                                print("检测到网页格式: period1 (20221025之前) - 宽度800且有th元素")
                                return "period1"
                        
                        # 检查period3特征：标准表格结构
                        # period3表格通常有不同的结构
                        period3_th = table.ele('css:th[bgcolor="#1381be"]', timeout=1)
                        if period3_th:
                            print("检测到网页格式: period3 (20221108之后) - 标准表格结构")
                            return "period3"
            
            # 如果以上都没检测到，尝试直接检查表格结构
            # 检查period1特征：宽度800的表格
            period1_tables = live_page.eles('css:table[width="800"]')
            if period1_tables:
                for table in period1_tables:
                    th_elements = table.eles('css:th')
                    if th_elements:
                        print("检测到网页格式: period1 (20221025之前) - 通过直接表格检测")
                        return "period1"
            
            # 检查period3表格
            period3_table = live_page.ele('css:#teamTechDiv_detail table', timeout=2)
            if period3_table:
                print("检测到网页格式: period3 (20221108之后) - 通过直接表格检测")
                return "period3"
            
            # 默认使用period3
            print("未检测到特定网页格式，使用默认格式: period3")
            return "period3"
            
        except Exception as e:
            print(f"检测网页格式时出错: {e}")
            return "period3"
    
    @staticmethod
    def _process_single_match_period1(web_page, match_data, current_date, row_element=None):
        """处理period1（20221025之前）的比赛 - 通过点击比分列跳转"""
        live_tab = None
        try:
            print(f"处理period1比赛: {match_data['home_team']} vs {match_data['away_team']}")
            
            # 通过点击比分列跳转到现场分析页面
            if not row_element:
                return False
            
            # 查找比分列中的链接或可点击元素
            score_cell = None
            tds = row_element.eles('tag:td')
            column_indices = FootballCrawler._detect_column_indices(tds)
            score_idx = column_indices.get('score', 4)
            
            if score_idx < len(tds):
                score_cell = tds[score_idx]
            
            if not score_cell:
                return False
            
            # 查找可点击的链接
            link = score_cell.ele('tag:a', timeout=2)
            if not link:
                # 如果没有链接，使用JavaScript点击单元格
                web_page.run_js('arguments[0].click()', score_cell)
            else:
                # 使用JavaScript点击链接，避免元素不可见问题
                web_page.run_js('arguments[0].click()', link)
            
            # 等待新标签页打开
            time.sleep(1)
            
            # 获取当前浏览器实例
            browser = web_page.browser
            current_tab_id = web_page.tab_id
            
            # 获取最新打开的标签页
            live_tab = browser.latest_tab
            if not live_tab:
                print("未能获取新打开的标签页")
                return False
            
            # 激活标签页
            browser.activate_tab(live_tab.tab_id)
            
            # 等待页面加载
            time.sleep(1)
            
            # 检查页面是否加载成功
            page_loaded = False
            for _ in range(3):
                try:
                    page_loaded = live_tab.ele('tag:body', timeout=10)
                    if page_loaded:
                        break
                except:
                    time.sleep(2)

            if not page_loaded:
                print("页面加载失败")
                return False
            
            # 检测网页格式
            detected_period = FootballCrawler._detect_page_format(live_tab)
            print(f"检测到的网页格式: {detected_period}")
            
            # 根据检测到的格式调用相应的解析函数
            home_stats, away_stats = FootballCrawler.get_match_stats_from_live_page(live_tab, match_data, detected_period)
            
            # 检查是否有球员统计按钮
            has_player_stats = FootballCrawler._check_player_stats_button(live_tab)
            home_players, away_players = None, None
            
            if has_player_stats:
                # 获取球员统计数据
                home_players, away_players = FootballCrawler.get_player_stats_from_page(live_tab, match_data, current_date)
            
            # 保存比赛数据
            success, result = FootballCrawler.save_match_data_to_excel(
                match_data, current_date, home_stats, away_stats, home_players, away_players
            )
            
            return success
            
        except Exception as e:
            print(f"处理period1比赛时出错: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            # 关闭现场分析标签页
            if live_tab and web_page:
                try:
                    browser = web_page.browser
                    current_tab_id = web_page.tab_id
                    browser.close_tabs(live_tab.tab_id)
                    browser.activate_tab(current_tab_id)
                except Exception:
                    pass
    
    @staticmethod
    def _process_single_match_period2(web_page, match_data, current_date, row_element=None):
        """处理period2（20221025-20221108）的比赛 - 通过点击比分列跳转"""
        live_tab = None
        try:
            print(f"处理period2比赛: {match_data['home_team']} vs {match_data['away_team']}")
            
            # 通过点击比分列跳转到现场分析页面
            if not row_element:
                return False
            
            # 查找比分列中的链接或可点击元素
            score_cell = None
            tds = row_element.eles('tag:td')
            column_indices = FootballCrawler._detect_column_indices(tds)
            score_idx = column_indices.get('score', 4)
            
            if score_idx < len(tds):
                score_cell = tds[score_idx]
            
            if not score_cell:
                return False
            
            # 查找可点击的链接
            link = score_cell.ele('tag:a', timeout=2)
            if not link:
                # 如果没有链接，使用JavaScript点击单元格
                web_page.run_js('arguments[0].click()', score_cell)
            else:
                # 使用JavaScript点击链接，避免元素不可见问题
                web_page.run_js('arguments[0].click()', link)
            
            # 等待新标签页打开
            time.sleep(1)
            
            # 获取当前浏览器实例
            browser = web_page.browser
            current_tab_id = web_page.tab_id
            
            # 获取最新打开的标签页
            live_tab = browser.latest_tab
            if not live_tab:
                print("未能获取新打开的标签页")
                return False
            
            # 激活标签页
            browser.activate_tab(live_tab.tab_id)
            
            # 等待页面加载
            time.sleep(1)
            
            # 检查页面是否加载成功
            page_loaded = False
            for _ in range(3):
                try:
                    page_loaded = live_tab.ele('tag:body', timeout=10)
                    if page_loaded:
                        break
                except:
                    time.sleep(2)

            if not page_loaded:
                print("页面加载失败")
                return False
            
            # 检测网页格式
            detected_period = FootballCrawler._detect_page_format(live_tab)
            print(f"检测到的网页格式: {detected_period}")
            
            # 根据检测到的格式调用相应的解析函数
            home_stats, away_stats = FootballCrawler.get_match_stats_from_live_page(live_tab, match_data, detected_period)
            
            # 检查是否有球员统计按钮
            has_player_stats = FootballCrawler._check_player_stats_button(live_tab)
            home_players, away_players = None, None
            
            if has_player_stats:
                # 获取球员统计数据 - 使用检测到的页面格式
                home_players, away_players = FootballCrawler.get_player_stats_from_page(live_tab, match_data, current_date, detected_period)
            
            # 保存比赛数据
            success, result = FootballCrawler.save_match_data_to_excel(
                match_data, current_date, home_stats, away_stats, home_players, away_players
            )
            
            return success
            
        except Exception as e:
            print(f"处理period2比赛时出错: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            # 关闭现场分析标签页
            if live_tab and web_page:
                try:
                    browser = web_page.browser
                    current_tab_id = web_page.tab_id
                    browser.close_tabs(live_tab.tab_id)
                    browser.activate_tab(current_tab_id)
                except Exception:
                    pass
    
    @staticmethod
    def _process_single_match_period3(web_page, match_data, current_date, row_element=None):
        """处理period3（20221108之后）的比赛 - 通过点击比分列跳转"""
        live_tab = None
        try:
            print(f"处理period3比赛: {match_data['home_team']} vs {match_data['away_team']}")
            
            # 通过点击比分列跳转到现场分析页面
            if not row_element:
                return False
            
            # 查找比分列中的链接或可点击元素
            score_cell = None
            tds = row_element.eles('tag:td')
            column_indices = FootballCrawler._detect_column_indices(tds)
            score_idx = column_indices.get('score', 4)
            
            if score_idx < len(tds):
                score_cell = tds[score_idx]
            
            if not score_cell:
                return False
            
            # 查找可点击的链接
            link = score_cell.ele('tag:a', timeout=2)
            if not link:
                # 如果没有链接，使用JavaScript点击单元格
                web_page.run_js('arguments[0].click()', score_cell)
            else:
                # 使用JavaScript点击链接，避免元素不可见问题
                web_page.run_js('arguments[0].click()', link)
            
            # 等待新标签页打开
            time.sleep(1)
            
            # 获取当前浏览器实例
            browser = web_page.browser
            current_tab_id = web_page.tab_id
            
            # 获取最新打开的标签页
            live_tab = browser.latest_tab
            if not live_tab:
                print("未能获取新打开的标签页")
                return False
            
            # 激活标签页
            browser.activate_tab(live_tab.tab_id)
            
            # 等待页面加载
            time.sleep(1)
            
            # 检查页面是否加载成功
            page_loaded = False
            for _ in range(3):
                try:
                    page_loaded = live_tab.ele('tag:body', timeout=10)
                    if page_loaded:
                        break
                except:
                    time.sleep(2)

            if not page_loaded:
                print("页面加载失败")
                return False
            
            # 检测网页格式
            detected_period = FootballCrawler._detect_page_format(live_tab)
            print(f"检测到的网页格式: {detected_period}")
            
            # 根据检测到的格式调用相应的解析函数
            home_stats, away_stats = FootballCrawler.get_match_stats_from_live_page(live_tab, match_data, detected_period)
            
            # 检查是否有球员统计按钮
            has_player_stats = FootballCrawler._check_player_stats_button(live_tab)
            home_players, away_players = None, None
            
            if has_player_stats:
                # 获取球员统计数据
                home_players, away_players = FootballCrawler.get_player_stats_from_page(live_tab, match_data, current_date)
            
            # 保存比赛数据
            success, result = FootballCrawler.save_match_data_to_excel(
                match_data, current_date, home_stats, away_stats, home_players, away_players
            )
            
            return success
            
        except Exception as e:
            print(f"处理period3比赛时出错: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            # 关闭现场分析标签页
            if live_tab and web_page:
                try:
                    browser = web_page.browser
                    current_tab_id = web_page.tab_id
                    browser.close_tabs(live_tab.tab_id)
                    browser.activate_tab(current_tab_id)
                except Exception:
                    pass
            
            # 原使用match_id构建URL的代码（已注释）
            # # 使用match_id直接访问现场分析页面
            # if not match_data.get('match_id'):
            #     return False
            #     
            # live_analysis_url = f"https://live.titan007.com/detail/{match_data['match_id']}cn.htm"
            # 
            # browser = web_page.browser
            # current_tab_id = web_page.tab_id
            # live_tab = browser.new_tab(live_analysis_url)
            # browser.activate_tab(live_tab.tab_id)
            # 
            # # 等待页面加载
            # time.sleep(1)
            # 
            # # 检查页面是否加载成功
            # page_loaded = False
            # for _ in range(3):
            #     try:
            #         page_loaded = live_tab.ele('tag:body', timeout=10)
            #         if page_loaded:
            #             break
            #     except:
            #         time.sleep(2)

            # if not page_loaded:
            #     print("页面加载失败")
            #     return False
            # 
            # # 检测网页格式
            # detected_period = FootballCrawler._detect_page_format(live_tab)
            # print(f"检测到的网页格式: {detected_period}")
            # 
            # # 根据检测到的格式调用相应的解析函数
            # home_stats, away_stats = FootballCrawler.get_match_stats_from_live_page(live_tab, match_data, detected_period)
            # 
            # # 检查是否有球员统计按钮
            # has_player_stats = FootballCrawler._check_player_stats_button(live_tab)
            # home_players, away_players = None, None
            # 
            # if has_player_stats:
            #     # 获取球员统计数据
            #     home_players, away_players = FootballCrawler.get_player_stats_from_page(live_tab, match_data, current_date)
            # 
            # # 保存比赛数据
            # success, result = FootballCrawler.save_match_data_to_excel(
            #     match_data, current_date, home_stats, away_stats, home_players, away_players
            # )
            # 
            # return success

    @staticmethod
    def process_single_date(date_info):
        """处理单个日期的数据 - 多进程版本"""
        web_page = None
        logs = []
        try:
            date_obj, league_filter, use_market_filter, continue_from_last = date_info
            date_str = date_obj.strftime('%Y%m%d')
            logs.append(f"进程 {os.getpid()} 开始处理日期: {date_str}")

            # 检测时间段
            time_period = FootballCrawler.get_time_period(date_obj)
            period_names = {
                "period1": "20221025之前",
                "period2": "20221025-20221108",
                "period3": "20221108之后"
            }
            logs.append(f"进程 {os.getpid()} 检测到时间段: {period_names.get(time_period, '未知')}")

            # 随机延迟
            delay_seconds = random.uniform(1, 3)
            logs.append(f"进程 {os.getpid()} 等待 {delay_seconds:.2f} 秒后启动")
            time.sleep(delay_seconds)

            # 为每个进程创建独立的浏览器实例
            web_page = FootballCrawler.create_browser_instance()

            # 创建输出目录
            files_dir = os.path.join(os.getcwd(), "比赛球员数据")
            if not os.path.exists(files_dir):
                os.makedirs(files_dir)

            # 为每个日期创建单独的文件
            output_file = os.path.join(files_dir, f"{date_str}_比赛球员数据.xlsx")
            file_exists = os.path.exists(output_file)
            
            # 构建URL
            url = f'https://bf.titan007.com/football/Over_{date_str}.htm'
            logs.append(f"进程 {os.getpid()} 访问URL: {url}")

            # 访问页面
            web_page.get(url)
            FootballCrawler.wait_with_random_delay(0.8, 1.2)

            # 应用盘口筛选
            if use_market_filter:
                FootballCrawler.apply_market_filter(web_page, execute_filter=True)
                logs.append(f"进程 {os.getpid()} 已应用盘口筛选")
            
            # 查找比赛数据行
            match_rows = web_page.eles('xpath://tr[@height="18" and contains(@bgcolor, "#")]')
            if not match_rows:
                match_rows = web_page.eles('xpath://tr[contains(@id, "tr1_")]')
            
            # 如果启用断点续爬，获取已下载的比赛列表
            downloaded_matches = {}
            if continue_from_last:
                downloaded_matches = FootballCrawler.get_downloaded_matches_from_folder()
                if downloaded_matches:
                    logs.append(f"进程 {os.getpid()} 已读取 {len(downloaded_matches)} 个日期的已下载比赛记录")
            
            date_match_count = 0
            for idx, row in enumerate(match_rows):
                # 提取比赛数据（传入时间段参数）
                match_data = FootballCrawler.extract_match_data(row, time_period)
                if not match_data:
                    continue
                
                # 检查联赛筛选
                if league_filter and match_data.get('league', '') not in league_filter:
                    continue
                
                # 检查是否已下载（断点续传）
                if continue_from_last and date_str in downloaded_matches:
                    is_downloaded = False
                    for downloaded in downloaded_matches[date_str]:
                        if (match_data['home_team'] == downloaded['home_team'] and 
                            match_data['away_team'] == downloaded['away_team']):
                            # 如果有联赛信息，也对比一下
                            if downloaded['league'] and match_data.get('league'):
                                if match_data['league'] == downloaded['league']:
                                    is_downloaded = True
                                    break
                            else:
                                # 没有联赛信息，只比较球队
                                is_downloaded = True
                                break
                    
                    if is_downloaded:
                        logs.append(f"进程 {os.getpid()} 跳过已下载: {match_data['home_team']} vs {match_data['away_team']}")
                        continue
                
                # 处理比赛（传入时间段和行元素参数）
                success = FootballCrawler.process_single_match(web_page, match_data, date_obj, time_period, row)
                if success:
                    date_match_count += 1
                    logs.append(f"进程 {os.getpid()} 成功处理: {match_data['home_team']} vs {match_data['away_team']}")
                else:
                    logs.append(f"进程 {os.getpid()} 处理失败: {match_data['home_team']} vs {match_data['away_team']}")
                
                # 随机延时
                FootballCrawler.wait_with_random_delay(1, 2)
            
            logs.append(f"进程 {os.getpid()} 成功处理日期 {date_str}: {date_match_count} 场比赛")
            
            return date_str, True, date_match_count, logs

        except Exception as e:
            logs.append(f"进程 {os.getpid()} 处理日期时出错: {e}")
            import traceback
            logs.append(f"错误详情: {traceback.format_exc()}")
            return date_str, False, 0, logs
        finally:
            # 确保浏览器实例被正确关闭
            if web_page:
                try:
                    web_page.quit()
                    logs.append(f"进程 {os.getpid()} 浏览器实例已关闭")
                except Exception as e:
                    logs.append(f"进程 {os.getpid()} 关闭浏览器时出错: {e}")

    @staticmethod
    def merge_excel_files(date_list, output_filename):
        """合并所有日期的Excel文件"""
        try:
            files_dir = os.path.join(os.getcwd(), "比赛球员数据")
            all_data = []

            for date_obj in date_list:
                date_str = date_obj.strftime('%Y%m%d')
                file_path = os.path.join(files_dir, f"{date_str}_比赛球员数据.xlsx")
                if os.path.exists(file_path):
                    try:
                        df = pd.read_excel(file_path)
                        if not df.empty:
                            all_data.append(df)
                            print(f"成功读取文件: {file_path}")
                    except Exception as e:
                        print(f"读取文件 {file_path} 时出错: {e}")

            if all_data:
                merged_df = pd.concat(all_data, ignore_index=True)
                merged_file = os.path.join(files_dir, output_filename)
                merged_df.to_excel(merged_file, index=False)
                print(f"所有数据已合并到: {merged_file}")
            else:
                print("没有找到可合并的数据文件")

        except Exception as e:
            print(f"合并文件时出错: {e}")


class CrawlerThread(QThread):
    """爬虫线程类"""
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int, int, int)  # 当前进度，总进度，已处理比赛数
    finished_signal = pyqtSignal(bool, str)  # 是否成功，消息
    
    def __init__(self, start_date, end_date, league_filter=None, use_market_filter=True, continue_from_last=True, use_multiprocess=False, max_processes=4):
        super().__init__()
        self.start_date = start_date
        self.end_date = end_date
        self.league_filter = league_filter or []
        self.use_market_filter = use_market_filter  # 是否使用盘口筛选
        self.continue_from_last = continue_from_last  # 是否从上次中断处继续
        self.use_multiprocess = use_multiprocess  # 是否使用多进程
        self.max_processes = max_processes  # 最大进程数
        self.is_running = True
        
    def run(self):
        try:
            # 生成日期列表
            date_list = []
            current_date = self.start_date
            
            while current_date <= self.end_date:
                date_list.append(current_date)
                current_date += timedelta(days=1)
            
            self.log_signal.emit(f"开始爬取数据，共 {len(date_list)} 个日期")
            
            if self.use_multiprocess:
                # 使用多进程模式
                self.log_signal.emit(f"使用多进程模式，最多 {min(len(date_list), self.max_processes)} 个进程")
                
                # 准备参数列表
                date_params = [(date_obj, self.league_filter, self.use_market_filter, self.continue_from_last) for date_obj in date_list]
                
                # 设置并发进程数，根据实际任务数量、CPU核心数和最大限制值确定
                max_concurrent = min(len(date_list), cpu_count(), self.max_processes)
                
                # 使用进程池和imap方法，实现任务队列
                all_results = []
                
                # 设置进程池的启动方法为'spawn'，确保日志传递正确
                with Pool(processes=max_concurrent, maxtasksperchild=1) as pool:
                    # 使用imap_unordered实现任务队列，进程完成一个任务后立即取下一个
                    self.log_signal.emit(f"开始处理所有日期，保持 {max_concurrent} 个进程持续工作...")
                    
                    # 使用imap_unordered，进程完成一个任务后立即获取下一个
                    results = pool.imap_unordered(FootballCrawler.process_single_date, date_params)
                    
                    completed_count = 0
                    for result in results:
                        # 详细调试信息
                        self.log_signal.emit(f"DEBUG: 收到结果类型: {type(result)}, 长度: {len(result) if hasattr(result, '__len__') else 'N/A'}")
                        
                        if len(result) == 4:  # 包含日志信息
                            date_str, success, match_count, logs = result
                            # 输出调试信息
                            self.log_signal.emit(f"DEBUG: 收到日期 {date_str} 的结果，日志数量: {len(logs)}")
                            if logs:
                                self.log_signal.emit(f"DEBUG: 日志内容示例: {logs[:2] if len(logs) > 2 else logs}")
                            # 输出日志信息
                            for log_msg in logs:
                                self.log_signal.emit(log_msg)
                        else:  # 不包含日志信息（兼容旧的返回格式）
                            date_str, success, match_count = result
                            self.log_signal.emit(f"DEBUG: 收到日期 {date_str} 的结果（无日志格式）")
                        
                        completed_count += 1
                        all_results.append((date_str, success, match_count))

                        if success:
                            self.log_signal.emit(f"[{completed_count}/{len(date_list)}] 日期 {date_str} 处理完成: {match_count} 场比赛")
                        else:
                            self.log_signal.emit(f"[{completed_count}/{len(date_list)}] 日期 {date_str} 处理失败")

                        # 更新进度
                        progress = int((completed_count / len(date_list)) * 100)
                        self.progress_signal.emit(progress, len(date_list), sum(r[2] for r in all_results))

                # 收集结果
                success_dates = []
                total_matches = 0

                for date_str, success, match_count in all_results:
                    if success:
                        success_dates.append(date_str)
                        total_matches += match_count
                        self.log_signal.emit(f"日期 {date_str} 处理完成: {match_count} 场比赛")
                    else:
                        self.log_signal.emit(f"日期 {date_str} 处理失败")

                self.finished_signal.emit(True, f"多进程爬取完成! 成功处理 {len(success_dates)}/{len(date_list)} 个日期，总共 {total_matches} 场比赛")
            else:
                # 使用单线程模式
                success_count = 0
                total_matches = 0
                
                for i, date_obj in enumerate(date_list):
                    if not self.is_running:
                        self.log_signal.emit("爬取任务已停止")
                        return
                        
                    date_str = date_obj.strftime('%Y%m%d')
                    
                    # 检测时间段
                    time_period = FootballCrawler.get_time_period(date_obj)
                    period_names = {
                        "period1": "20221025之前",
                        "period2": "20221025-20221108",
                        "period3": "20221108之后"
                    }
                    self.log_signal.emit(f"处理日期: {date_obj.strftime('%Y-%m-%d')} ({period_names.get(time_period, '未知')})")
                    
                    # 更新进度
                    progress = int((i + 1) / len(date_list) * 100)
                    self.progress_signal.emit(progress, len(date_list), total_matches)
                    
                    # 处理单个日期
                    web_page = None
                    try:
                        # 创建浏览器实例
                        web_page = FootballCrawler.create_browser_instance()
                        
                        # 构建URL
                        url = f'https://bf.titan007.com/football/Over_{date_str}.htm'
                        self.log_signal.emit(f"访问URL: {url}")
                        
                        # 访问页面
                        web_page.get(url)
                        FootballCrawler.wait_with_random_delay(0.8, 1.2)
                        
                        # 应用盘口筛选
                        if self.use_market_filter:
                            FootballCrawler.apply_market_filter(web_page, execute_filter=True)
                            self.log_signal.emit(f"已应用盘口筛选")
                        
                        # 查找比赛数据行
                        match_rows = web_page.eles('xpath://tr[@height="18" and contains(@bgcolor, "#")]')
                        if not match_rows:
                            match_rows = web_page.eles('xpath://tr[contains(@id, "tr1_")]')
                        
                        # 如果启用断点续爬，获取已下载的比赛列表
                        downloaded_matches = {}
                        if self.continue_from_last:
                            downloaded_matches = FootballCrawler.get_downloaded_matches_from_folder()
                            if downloaded_matches:
                                self.log_signal.emit(f"已读取 {len(downloaded_matches)} 个日期的已下载比赛记录")
                        
                        date_match_count = 0
                        for idx, row in enumerate(match_rows):
                            if not self.is_running:
                                break
                            
                            # 提取比赛数据（传入时间段参数）
                            match_data = FootballCrawler.extract_match_data(row, time_period)
                            if not match_data:
                                continue
                            
                            # 在调用process_single_match之前检查联赛筛选
                            if self.league_filter and match_data.get('league', '') not in self.league_filter:
                                continue
                            
                            # 检查是否已下载（断点续传）
                            if self.continue_from_last and date_str in downloaded_matches:
                                is_downloaded = False
                                for downloaded in downloaded_matches[date_str]:
                                    if (match_data['home_team'] == downloaded['home_team'] and 
                                        match_data['away_team'] == downloaded['away_team']):
                                        # 如果有联赛信息，也对比一下
                                        if downloaded['league'] and match_data.get('league'):
                                            if match_data['league'] == downloaded['league']:
                                                is_downloaded = True
                                                break
                                        else:
                                            # 没有联赛信息，只比较球队
                                            is_downloaded = True
                                            break
                                
                                if is_downloaded:
                                    self.log_signal.emit(f"跳过已保存: {match_data['home_team']} vs {match_data['away_team']}")
                                    continue
                            
                            # 处理比赛（传入时间段和行元素参数）
                            success = FootballCrawler.process_single_match(web_page, match_data, date_obj, time_period, row)
                            if success:
                                date_match_count += 1
                                total_matches += 1
                                self.log_signal.emit(f"成功处理: {match_data['home_team']} vs {match_data['away_team']}")
                            
                            # 随机延时
                            FootballCrawler.wait_with_random_delay(1, 2)
                        
                        if date_match_count > 0:
                            success_count += 1
                            self.log_signal.emit(f"✓ 日期 {date_str} 处理完成: {date_match_count} 场比赛")
                        else:
                            self.log_signal.emit(f"日期 {date_str} 无匹配比赛")
                        
                    except Exception as e:
                        self.log_signal.emit(f"处理日期 {date_str} 时出错: {str(e)}")
                    finally:
                        # 确保浏览器实例被正确关闭
                        if web_page:
                            try:
                                web_page.quit()
                                self.log_signal.emit(f"✓ 浏览器实例已关闭")
                            except Exception as e:
                                self.log_signal.emit(f"⚠ 关闭浏览器时出错: {str(e)}")
                    
                    # 随机延时
                    time.sleep(random.uniform(2, 4))
                
                self.finished_signal.emit(True, f"爬取完成! 成功处理 {success_count}/{len(date_list)} 个日期，共 {total_matches} 场比赛")
            
        except Exception as e:
            self.finished_signal.emit(False, f"爬取过程中出错: {str(e)}")
    
    def stop(self):
        self.is_running = False


class FootballDataGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.crawler_thread = None
        self.init_ui()
        
    def init_ui(self):
        self.setWindowTitle('足球比賽球員數據爬取工具')
        self.setGeometry(100, 100, 1000, 800)
        
        # 设置现代化样式
        self.setStyleSheet("""
            QMainWindow {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                          stop: 0 #f8f9fa, stop: 1 #e9ecef);
                font-family: 'Segoe UI', 'Microsoft YaHei', Arial, sans-serif;
            }
            QGroupBox {
                font-weight: 600;
                font-size: 13px;
                border: 2px solid #dee2e6;
                border-radius: 10px;
                margin-top: 12px;
                padding-top: 12px;
                background: white;
                color: #495057;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 8px 0 8px;
                color: #495057;
            }
            QPushButton {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                          stop: 0 #6c757d, stop: 1 #495057);
                border: none;
                color: white;
                padding: 10px 20px;
                border-radius: 6px;
                font-weight: 600;
                font-size: 12px;
                min-width: 100px;
            }
            QPushButton:hover {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                          stop: 0 #5a6268, stop: 1 #343a40);
            }
            QPushButton:disabled {
                background: #adb5bd;
                color: #6c757d;
            }
            QPushButton#startButton {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                          stop: 0 #28a745, stop: 1 #20c997);
            }
            QPushButton#startButton:hover {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                          stop: 0 #218838, stop: 1 #1e9e8a);
            }
            QPushButton#stopButton {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                          stop: 0 #dc3545, stop: 1 #c82333);
            }
            QPushButton#stopButton:hover {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                          stop: 0 #c82333, stop: 1 #bd2130);
            }
            QLineEdit, QDateEdit {
                padding: 8px 12px;
                border: 2px solid #ced4da;
                border-radius: 6px;
                font-size: 13px;
                background: white;
            }
            QLineEdit:focus, QDateEdit:focus {
                border-color: #007bff;
            }
            QTextEdit {
                border: 2px solid #ced4da;
                border-radius: 6px;
                font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
                font-size: 12px;
                background: #1a1d23;
                color: #e9ecef;
                padding: 8px;
            }
            QProgressBar {
                border: 2px solid #ced4da;
                border-radius: 10px;
                text-align: center;
                background: #f8f9fa;
                height: 20px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                          stop: 0 #007bff, stop: 1 #0056b3);
                border-radius: 8px;
            }
            QLabel {
                color: #495057;
                font-size: 13px;
                font-weight: 500;
            }
            QLabel#titleLabel {
                color: #212529;
                font-size: 24px;
                font-weight: 700;
                padding: 20px 0;
            }
        """)
        
        # 创建中心部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 主布局
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)
        
        # 标题区域
        title_label = QLabel('⚽ 足球比赛球员数据爬取工具')
        title_label.setObjectName('titleLabel')
        title_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title_label)
        
        # 创建分割器
        splitter = QSplitter(Qt.Vertical)
        
        # 上部分：控制面板
        control_widget = QWidget()
        control_layout = QVBoxLayout(control_widget)
        
        # 日期范围设置
        date_frame = QFrame()
        date_layout = QHBoxLayout(date_frame)
        
        date_layout.addWidget(QLabel('📅 開始日期:'))
        self.start_date_edit = QDateEdit()
        self.start_date_edit.setDate(QDate(2020, 10, 1))
        self.start_date_edit.setCalendarPopup(True)
        date_layout.addWidget(self.start_date_edit)
        
        date_layout.addSpacing(20)
        date_layout.addWidget(QLabel('📅 結束日期:'))
        self.end_date_edit = QDateEdit()
        self.end_date_edit.setDate(QDate.currentDate())
        self.end_date_edit.setCalendarPopup(True)
        date_layout.addWidget(self.end_date_edit)
        
        date_layout.addStretch()
        control_layout.addWidget(date_frame)
        
        # 联赛筛选
        league_frame = QFrame()
        league_layout = QHBoxLayout(league_frame)
        
        league_layout.addWidget(QLabel('🏆 聯賽篩選:'))
        self.league_edit = QLineEdit()
        self.league_edit.setText('英超,西甲,意甲,德甲,法甲,日职联,韩职联,澳洲甲,澳超')
        self.league_edit.setPlaceholderText('例如: 英超,西甲,意甲 (支持逗號、空格、中文逗號等分隔符，留空則爬取所有)')
        league_layout.addWidget(self.league_edit)
        
        control_layout.addWidget(league_frame)
        
        # 选项设置
        options_frame = QFrame()
        options_layout = QHBoxLayout(options_frame)
        
        # 盤口篩選選項
        market_filter_layout = QHBoxLayout()
        market_filter_layout.addWidget(QLabel('🎯 盤口篩選:（選擇開盤的比賽）'))
        self.market_filter_checkbox = QCheckBox('啟用盤口篩選')
        self.market_filter_checkbox.setChecked(False)  # 默认启用
        market_filter_layout.addWidget(self.market_filter_checkbox)
        
        # 斷點續爬選項
        continue_layout = QHBoxLayout()
        continue_layout.addWidget(QLabel('🔄 斷點續爬:'))
        self.continue_checkbox = QCheckBox('從上次中斷處繼續')
        self.continue_checkbox.setChecked(True)  # 默认启用
        continue_layout.addWidget(self.continue_checkbox)
        
        # 多進程選項
        multiprocess_layout = QHBoxLayout()
        self.multiprocess_checkbox = QCheckBox('啟用多進程')
        self.multiprocess_checkbox.setChecked(True)  # 默認禁用
        multiprocess_layout.addWidget(self.multiprocess_checkbox)
        
        multiprocess_layout.addWidget(QLabel('進程數:'))
        self.processes_spinbox = QSpinBox()
        self.processes_spinbox.setRange(1, cpu_count())
        self.processes_spinbox.setValue(min(6, cpu_count()))
        multiprocess_layout.addWidget(self.processes_spinbox)
        
        options_layout.addLayout(market_filter_layout)
        options_layout.addLayout(continue_layout)
        options_layout.addLayout(multiprocess_layout)
        options_layout.addStretch()
        
        control_layout.addWidget(options_frame)
        
        # 控制按钮
        button_frame = QFrame()
        button_layout = QHBoxLayout(button_frame)
        
        self.start_button = QPushButton('🚀 開始爬取')
        self.start_button.setObjectName('startButton')
        self.start_button.clicked.connect(self.start_crawling)
        button_layout.addWidget(self.start_button)
        
        self.stop_button = QPushButton('⏹️ 停止爬取')
        self.stop_button.setObjectName('stopButton')
        self.stop_button.clicked.connect(self.stop_crawling)
        self.stop_button.setEnabled(False)
        button_layout.addWidget(self.stop_button)
        
        button_layout.addStretch()
        
        self.clear_log_button = QPushButton('🧹 清空日誌')
        self.clear_log_button.clicked.connect(self.clear_log)
        button_layout.addWidget(self.clear_log_button)
        
        control_layout.addWidget(button_frame)
        
        # 进度显示
        progress_frame = QFrame()
        progress_layout = QVBoxLayout(progress_frame)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        progress_layout.addWidget(self.progress_bar)
        
        self.progress_label = QLabel('准备开始...')
        self.progress_label.setAlignment(Qt.AlignCenter)
        progress_layout.addWidget(self.progress_label)
        
        control_layout.addWidget(progress_frame)
        
        splitter.addWidget(control_widget)
        
        # 下部分：日志输出
        log_widget = QWidget()
        log_layout = QVBoxLayout(log_widget)
        
        log_header = QLabel('📋 运行日志')
        log_header.setStyleSheet("font-weight: 700; font-size: 14px; color: #495057; padding: 5px;")
        log_layout.addWidget(log_header)
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMinimumHeight(350)
        log_layout.addWidget(self.log_text)
        
        splitter.addWidget(log_widget)
        
        # 设置分割器比例
        splitter.setSizes([300, 500])
        
        main_layout.addWidget(splitter)
        
        # 状态栏
        self.status_label = QLabel('就绪')
        self.statusBar().addPermanentWidget(self.status_label)
        
        # 添加欢迎信息
        self.add_log('欢迎使用足球比赛球员数据爬取工具!')
        self.add_log('=' * 60)
        self.add_log('使用说明:')
        self.add_log('1. 设置日期范围 (默认过去7天)')
        self.add_log('2. 可选: 输入联赛名称进行筛选')
        self.add_log('3. 点击"开始爬取"按钮')
        self.add_log('4. 查看运行日志了解进度')
        self.add_log('=' * 60)
        
    def start_crawling(self):
        """开始爬取"""
        # 获取输入参数
        start_date = self.start_date_edit.date().toPyDate()
        end_date = self.end_date_edit.date().toPyDate()
        
        if start_date > end_date:
            QMessageBox.warning(self, '输入错误', '开始日期不能晚于结束日期')
            return
        
        # 处理联赛筛选
        league_text = self.league_edit.text().strip()
        league_filter = []
        if league_text:
            # 支持多种分隔符：逗号、空格、中文逗号、分隔符等
            import re
            # 使用正则表达式分割多种分隔符
            leagues = re.split(r'[,，\s;；]+', league_text)
            league_filter = [league.strip() for league in leagues if league.strip()]
        
        # 获取盘口筛选和断点续爬选项
        use_market_filter = self.market_filter_checkbox.isChecked()
        continue_from_last = self.continue_checkbox.isChecked()
        use_multiprocess = self.multiprocess_checkbox.isChecked()
        max_processes = self.processes_spinbox.value()
        
        # 更新界面状态
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.progress_bar.setValue(0)
        self.progress_label.setText('开始爬取...')
        self.status_label.setText('爬取中...')
        
        # 清空日志并添加开始信息
        self.log_text.clear()
        self.add_log('🚀 开始爬取足球比赛数据')
        self.add_log(f'📅 日期范围: {start_date.strftime("%Y-%m-%d")} 到 {end_date.strftime("%Y-%m-%d")}')
        if league_filter:
            self.add_log(f'🏆 联赛筛选: {", ".join(league_filter)}')
        else:
            self.add_log('🏆 联赛筛选: 所有联赛')
        if use_multiprocess:
            self.add_log(f'⚙️ 多进程模式: 启用，进程数: {max_processes}')
        else:
            self.add_log('⚙️ 多进程模式: 禁用，单线程模式')
        self.add_log('-' * 60)
        
        # 创建并启动爬虫线程
        self.crawler_thread = CrawlerThread(start_date, end_date, league_filter, use_market_filter, continue_from_last, use_multiprocess, max_processes)
        self.crawler_thread.log_signal.connect(self.add_log)
        self.crawler_thread.progress_signal.connect(self.update_progress)
        self.crawler_thread.finished_signal.connect(self.crawling_finished)
        self.crawler_thread.start()
        
    def stop_crawling(self):
        """停止爬取"""
        if self.crawler_thread and self.crawler_thread.isRunning():
            self.add_log('正在停止爬取，请稍候...')
            self.crawler_thread.stop()
            
            # 等待线程安全停止
            if not self.crawler_thread.wait(10000):  # 10秒超时
                self.add_log('强制终止爬虫线程')
                self.crawler_thread.terminate()
                self.crawler_thread.wait(3000)
            
            self.add_log('爬取已停止')
            self.status_label.setText('已停止')
        
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.progress_label.setText('已停止')
        self.progress_bar.setValue(0)
        
    def crawling_finished(self, success, message):
        """爬取完成回调"""
        self.add_log(message)
        self.add_log('=' * 60)
        
        if success:
            self.progress_label.setText('✅ 爬取完成!')
            self.status_label.setText('爬取完成')
            QMessageBox.information(self, '完成', '数据爬取完成!\\n数据已保存到"比赛球员数据"文件夹中')
        else:
            self.progress_label.setText('❌ 爬取失败!')
            self.status_label.setText('爬取失败')
            QMessageBox.warning(self, '错误', '爬取过程中出现错误，请查看日志详情')
        
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        
    def update_progress(self, progress, total_days, total_matches):
        """更新进度"""
        self.progress_bar.setValue(progress)
        self.progress_label.setText(f'进度: {progress}% | 日期: {total_days}个 | 比赛: {total_matches}场')
        
    def add_log(self, message):
        """添加日志"""
        timestamp = datetime.now().strftime('%H:%M:%S')
        log_entry = f'[{timestamp}] {message}'
        self.log_text.append(log_entry)
        
        # 自动滚动到底部
        cursor = self.log_text.textCursor()
        cursor.movePosition(cursor.End)
        self.log_text.setTextCursor(cursor)
        
        # 更新状态栏
        self.status_label.setText(message[:40] + '...' if len(message) > 40 else message)
        
    def clear_log(self):
        """清空日志"""
        self.log_text.clear()
        self.add_log('日志已清空')
        
    def closeEvent(self, event):
        """关闭事件处理"""
        if self.crawler_thread and self.crawler_thread.isRunning():
            reply = QMessageBox.question(self, '确认退出', 
                                       '爬取任务正在进行中，确定要退出吗?',
                                       QMessageBox.Yes | QMessageBox.No,
                                       QMessageBox.No)
            
            if reply == QMessageBox.Yes:
                self.crawler_thread.stop()
                self.crawler_thread.wait(3000)
                
                # 强制关闭所有浏览器实例
                self.force_close_all_browsers()
                
                event.accept()
            else:
                event.ignore()
        else:
            # 确保关闭所有浏览器实例
            self.force_close_all_browsers()
            event.accept()
    
    def force_close_all_browsers(self):
        """强制关闭所有浏览器实例"""
        try:
            # 导入DrissionPage相关模块
            from DrissionPage import ChromiumPage
            import psutil
            import os
            
            # 查找并关闭所有Chrome/Chromium进程
            chrome_processes = []
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    if proc.info['name'] and ('chrome' in proc.info['name'].lower() or 'chromium' in proc.info['name'].lower()):
                        chrome_processes.append(proc)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            
            if chrome_processes:
                print(f"发现 {len(chrome_processes)} 个浏览器进程，正在关闭...")
                
                # 首先尝试优雅关闭
                for proc in chrome_processes:
                    try:
                        proc.terminate()
                    except:
                        pass
                
                # 等待一段时间
                import time
                time.sleep(2)
                
                # 检查是否还有进程存活，如果有则强制关闭
                remaining_processes = []
                for proc in chrome_processes:
                    try:
                        if proc.is_running():
                            remaining_processes.append(proc)
                    except:
                        pass
                
                if remaining_processes:
                    print(f"仍有 {len(remaining_processes)} 个进程存活，强制关闭...")
                    for proc in remaining_processes:
                        try:
                            proc.kill()
                        except:
                            pass
                
                print("所有浏览器进程已关闭")
            
            # 清理临时文件
            self.cleanup_temp_files()
            
        except Exception as e:
            print(f"关闭浏览器进程时出错: {e}")
    
    def cleanup_temp_files(self):
        """清理临时文件"""
        try:
            import tempfile
            import shutil
            
            # 清理DrissionPage临时目录
            temp_dir = tempfile.gettempdir()
            drission_dirs = []
            
            # 查找DrissionPage相关的临时目录
            for item in os.listdir(temp_dir):
                item_path = os.path.join(temp_dir, item)
                if os.path.isdir(item_path) and ('drission' in item.lower() or 'chromium' in item.lower()):
                    drission_dirs.append(item_path)
            
            for dir_path in drission_dirs:
                try:
                    shutil.rmtree(dir_path, ignore_errors=True)
                    print(f"已清理临时目录: {dir_path}")
                except Exception as e:
                    print(f"清理临时目录失败 {dir_path}: {e}")
                    
        except Exception as e:
            print(f"清理临时文件时出错: {e}")


def main():
    app = QApplication(sys.argv)
    
    # 设置应用程序样式
    app.setStyle('Fusion')
    
    # 创建并显示主窗口
    window = FootballDataGUI()
    window.show()
    
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()