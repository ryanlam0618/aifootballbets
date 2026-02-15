#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
将Football data crawling tool的比赛球员数据转换为big_five_data格式
- 保留中文队名
- 球员数据放在球队文件夹下
- 整合为matchlog.csv文件

使用方法: python convert_all_data.py
"""

import pandas as pd
import os
import re
import glob
import sys
from datetime import datetime
from collections import defaultdict

# 路径配置
SOURCE_DIR = r"c:\Users\Ryan\Documents\data\Football data crawling tool\比赛球员数据"
TARGET_DIR = r"c:\Users\Ryan\Documents\data\big_five_data"

# 联赛到联赛名称的映射
LEAGUE_MAP = {
    '英超': 'Premier-League',
    '西甲': 'La-Liga',
    '意甲': 'Serie-A',
    '德甲': 'Bundesliga',
    '法甲': 'Ligue-1',
    '日职联': 'J-League',
    '韩K联': 'K-League',
    '澳超': 'A-League',
}

# 中文球队名到英文队名的映射
TEAM_NAME_MAP = {
    # 英超
    '利物浦': 'Liverpool',
    '阿森纳': 'Arsenal',
    '曼彻斯特城': 'Manchester City',
    '曼彻斯特联': 'Manchester Utd',
    '切尔西': 'Chelsea',
    '热刺': 'Tottenham',
    '纽卡斯尔联': 'Newcastle Utd',
    '富勒姆': 'Fulham',
    '水晶宫': 'Crystal Palace',
    '西汉姆联': 'West Ham',
    '埃弗顿': 'Everton',
    '布伦特福德': 'Brentford',
    '布莱顿': 'Brighton',
    '狼队': 'Wolves',
    '诺丁汉森林': "Nott'ham Forest",
    '阿斯顿维拉': 'Aston Villa',
    '伯恩茅斯': 'Bournemouth',
    '南安普敦': 'Southampton',
    '伊普斯维奇': 'Ipswich Town',
    '利兹联': 'Leeds United',
    '莱斯特城': 'Leicester City',
    '伯恩利': 'Burnley',
    '谢菲尔德联队': 'Sheffield Utd',
    '西布罗姆维奇': 'West Brom',
    
    # 西甲
    '巴塞罗那': 'Barcelona',
    '皇家马德里': 'Real Madrid',
    '马德里竞技': 'Atlético Madrid',
    '塞维利亚': 'Sevilla',
    '比利亚雷亚尔': 'Villarreal',
    '皇家社会': 'Real Sociedad',
    '巴伦西亚': 'Valencia',
    '毕尔巴鄂竞技': 'Athletic Club',
    '马洛卡': 'Mallorca',
    '奥萨苏纳': 'Osasuna',
    '赫塔菲': 'Getafe',
    '塞尔塔': 'Celta Vigo',
    '阿拉维斯': 'Alavés',
    '巴列卡诺': 'Rayo Vallecano',
    '拉斯帕尔马斯': 'Las Palmas',
    '贝蒂斯': 'Betis',
    '格拉那达': 'Granada',
    '莱加内斯': 'Leganés',
    '埃瓦尔': 'Eibar',
    '韦斯卡': 'Huesca',
    '巴拉多利德': 'Valladolid',
    '埃尔切': 'Elche',
    '卡迪斯': 'Cádiz',
    '西班牙人': 'Espanyol',
    '赫罗纳': 'Girona',
    
    # 意甲
    '尤文图斯': 'Juventus',
    '国际米兰': 'Inter',
    'AC米兰': 'Milan',
    '罗马': 'Roma',
    '那不勒斯': 'Napoli',
    '拉齐奥': 'Lazio',
    '亚特兰大': 'Atalanta',
    '佛罗伦萨': 'Fiorentina',
    '都灵': 'Torino',
    '博洛尼亚': 'Bologna',
    '乌迪内斯': 'Udinese',
    '萨索洛': 'Sassuolo',
    '桑普多利亚': 'Sampdoria',
    '卡利亚里': 'Cagliari',
    '热那亚': 'Genoa',
    '维罗纳': 'Hellas Verona',
    '斯佩齐亚': 'Spezia',
    '克罗托内': 'Crotone',
    '贝内文托': 'Benevento',
    '恩波利': 'Empoli',
    '蒙扎': 'Monza',
    '科莫': 'Como',
    '威尼斯': 'Venezia',
    '莱切': 'Lecce',
    '帕尔马': 'Parma',
    
    # 德甲
    '拜仁慕尼黑': 'Bayern Munich',
    '多特蒙德': 'Dortmund',
    'RB莱比锡': 'RB Leipzig',
    '勒沃库森': 'Leverkusen',
    '门兴格拉德巴赫': 'Gladbach',
    '法兰克福': 'Eint Frankfurt',
    '霍芬海姆': 'Hoffenheim',
    '沃尔夫斯堡': 'Wolfsburg',
    '弗赖堡': 'Freiburg',
    '柏林联合': 'Union Berlin',
    '柏林赫塔': 'Hertha Berlin',
    '奥格斯堡': 'Augsburg',
    '美因茨': 'Mainz 05',
    '科隆': 'Köln',
    '云达不莱梅': 'Werder Bremen',
    '沙尔克04': 'Schalke 04',
    '斯图加特': 'Stuttgart',
    '比勒菲尔德': 'Bielefeld',
    '汉诺威96': 'Hannover 96',
    '杜塞尔多夫': 'Düsseldorf',
    '海登海姆': 'Heidenheim',
    '圣保利': 'St. Pauli',
    '波鸿': 'Bochum',
    '基尔霍斯坦': 'Holstein Kiel',
    
    # 法甲
    '巴黎圣日尔曼': 'Paris S-G',
    '马赛': 'Marseille',
    '里昂': 'Lyon',
    '摩纳哥': 'Monaco',
    '里尔': 'Lille',
    '雷恩': 'Rennes',
    '尼斯': 'Nice',
    '蒙彼利埃': 'Montpellier',
    '南特': 'Nantes',
    '斯特拉斯堡': 'Strasbourg',
    '波尔多': 'Bordeaux',
    '朗斯': 'Lens',
    '圣埃蒂安': 'Saint-Étienne',
    '安格斯': 'Angers',
    '第戎': 'Dijon',
    '尼姆': 'Nîmes',
    '洛里昂': 'Lorient',
    '布雷斯特': 'Brest',
    '兰斯': 'Reims',
    '梅斯': 'Metz',
    '图卢兹': 'Toulouse',
    '勒阿弗尔': 'Le Havre',
    '欧塞尔': 'Auxerre',
    
    # 日职联
    '川崎前锋': 'Kawasaki Frontale',
    '横滨水手': 'Yokohama F. Marinos',
    '鹿岛鹿角': 'Kashima Antlers',
    '东京FC': 'FC Tokyo',
    '大阪钢巴': 'Gamba Osaka',
    '大阪樱花': 'Cerezo Osaka',
    '名古屋鲸八': 'Nagoya Grampus',
    '广岛三箭': 'Sanfrecce Hiroshima',
    '柏太阳神': 'Urawa Red Diamonds',
    '浦和红钻': 'Urawa Red Diamonds',
    '清水鼓动': 'Shimizu S-Pulse',
    '神户胜利船': 'Vissel Kobe',
    'FC东京': 'FC Tokyo',
    '湘南海洋': 'Shonan Bellmare',
    '札幌冈萨多': 'Consadole Sapporo',
    '仙台维加泰': 'Vegalta Sendai',
    '大分三神': 'Oita Trinita',
    '鸟栖沙岩': 'Sagan Tosu',
    '横滨FC': 'Yokohama FC',
    '京都不死鸟': 'Kyoto Sanga FC',
    '町田泽维亚': 'Machida Zelvia',
    '福冈黄蜂': 'Avispa Fukuoka',
    '新泻天鹅': 'Albirex Niigata',
    '冈山绿雉': 'FC Okayama',
    
    # 韩K联
    '全北现代': 'Jeonbuk Hyundai Motors',
    '蔚山现代': 'Ulsan Hyundai',
    '水原三星': 'Suwon Samsung Bluewings',
    '浦项制铁': 'Pohang Steelers',
    'FC首尔': 'FC Seoul',
    '城南足球俱乐部': 'Seongnam Ilhwa',
    '尚州尚武': 'Sangju Sangmu',
    '大邱FC': 'Daegu FC',
    '江原FC': 'Gangwon FC',
    '光州FC': 'Gwangju FC',
    '仁川联队': 'Incheon United',
    '釜山偶像': 'Busan IPark',
    
    # 澳超
    '墨尔本城': 'Melbourne City',
    '墨尔本胜利': 'Melbourne Victory',
    '悉尼FC': 'Sydney FC',
    '西部联': 'Western United',
    '珀斯光荣': 'Perth Glory',
    '阿德莱德联': 'Adelaide United',
    '布里斯班狮吼': 'Brisbane Roar',
    '中央海岸水手': 'Central Coast Mariners',
    '惠灵顿凤凰': 'Wellington Phoenix',
    '纽卡斯尔喷气机': 'Newcastle Jets',
    '西悉尼流浪者': 'Western Sydney',
}


def parse_filename(filename):
    """从文件名解析比赛信息"""
    basename = os.path.basename(filename)
    name_without_ext = os.path.splitext(basename)[0]
    
    parts = name_without_ext.split('_')
    
    if len(parts) >= 5:
        try:
            date_str = parts[0]
            date = datetime.strptime(date_str, '%Y%m%d')
            league = parts[1]
            
            vs_idx = None
            for i, part in enumerate(parts):
                if part == 'vs' or part.startswith('vs'):
                    vs_idx = i
                    break
            
            if vs_idx is not None and vs_idx >= 3:
                home_part = '_'.join(parts[2:vs_idx])
                away_part = '_'.join(parts[vs_idx+1:])
                
                home_team = re.sub(r'\[\d+\]', '', home_part).strip()
                away_team = re.sub(r'\[\d+\]', '', away_part).strip()
                
                return {
                    'date': date,
                    'league': league,
                    'home_team': home_team,
                    'away_team': away_team,
                }
        except:
            return None
    
    return None


def get_season(date):
    """根据日期获取赛季"""
    year = date.year
    month = date.month
    if month >= 8:
        return f"{year}-{year + 1}"
    else:
        return f"{year - 1}-{year}"


def extract_team_name(team_str):
    """从球队字符串提取球队名"""
    team = re.sub(r'^\[\d+\]', '', str(team_str))
    team = re.sub(r'\[\d+\]$', '', team)
    return team.strip()


def translate_team_name(team_name):
    """将中文球队名翻译为英文"""
    if team_name in TEAM_NAME_MAP:
        return TEAM_NAME_MAP[team_name]
    
    for cn_name, en_name in TEAM_NAME_MAP.items():
        if cn_name in team_name or team_name in cn_name:
            return en_name
    
    return team_name


def get_league_folder(league):
    """获取联赛对应的文件夹名称"""
    return LEAGUE_MAP.get(league, 'Other')


def process_match_stats(source_file, output_dir):
    """处理比赛技术统计，转换为matchlog格式"""
    xlsx = pd.ExcelFile(source_file)
    stats_df = pd.read_excel(xlsx, sheet_name='比赛技术统计')
    basic_df = pd.read_excel(xlsx, sheet_name='比赛基础数据')
    
    if not basic_df.empty:
        match_date = basic_df.iloc[0]['Date']
        if isinstance(match_date, str):
            try:
                match_date = datetime.strptime(match_date, '%Y-%m-%d')
            except:
                match_date = datetime.now()
    else:
        match_date = datetime.now()
    
    season = get_season(match_date)
    date_str = match_date.strftime('%Y-%m-%d')
    
    if not basic_df.empty:
        league_folder = get_league_folder(basic_df.iloc[0]['League'])
    else:
        league_folder = 'Other'
    
    # 映射列名
    column_mapping = {
        'Team Name': 'TeamName',
        'Corner': 'Corner',
        'Half Corner': 'HalfCorner',
        'Yellow Card': 'YellowCard',
        'Red Card': 'RedCard',
        'Shot': 'Shots',
        'Shot on Target': 'ShotsOnTarget',
        'Attack': 'Attacks',
        'Dangerous Attack': 'DangerousAttacks',
        'Shot Off Target': 'ShotsOffTarget',
        'Shot Blocked': 'ShotsBlocked',
        'Free Kick': 'FreeKicks',
        'Possession': 'Possession',
        'Half Possession': 'HalfPossession',
        'Pass': 'Passes',
        'Pass Success Rate': 'PassSuccessRate',
        'Foul': 'Fouls',
        'Offside': 'Offsides',
        'Header': 'Headers',
        'Header Success': 'HeadersSuccessful',
        'Save': 'Saves',
        'Tackle': 'Tackles',
        'Dribble': 'Dribbles',
        'Throw In': 'ThrowIns',
        'Hit Woodwork': 'HitWoodwork',
        'Interception': 'Interceptions',
        'Block': 'Blocks',
        'Assist': 'Assists',
        'Long Pass': 'LongPasses',
        'Successful Cross': 'SuccessfulCrosses',
    }
    
    stats_df = stats_df.rename(columns=column_mapping)
    
    for idx, row in stats_df.iterrows():
        team_name_raw = row['TeamName']
        
        if '主队' in str(team_name_raw):
            venue = 'Home'
            team_name = extract_team_name(str(team_name_raw).replace('主队 - ', ''))
        else:
            venue = 'Away'
            team_name = extract_team_name(str(team_name_raw))
        
        team_name_en = translate_team_name(team_name)
        
        # 获取对手
        other_idx = 1 - idx if len(stats_df) > 1 else 0
        opponent_row = stats_df.iloc[other_idx]
        opponent_raw = opponent_row['TeamName']
        opponent_name = extract_team_name(str(opponent_raw).replace('主队 - ', ''))
        opponent_en = translate_team_name(opponent_name)
        
        result_row = {
            'TeamName': team_name_en,
            'Date': date_str,
            'Opponent': opponent_en,
            'Venue': venue,
        }
        
        for col in ['Corner', 'HalfCorner', 'YellowCard', 'RedCard', 'Shots', 'ShotsOnTarget',
                    'Attacks', 'DangerousAttacks', 'ShotsOffTarget', 'ShotsBlocked', 'FreeKicks',
                    'Possession', 'HalfPossession', 'Passes', 'PassSuccessRate', 'Fouls', 'Offsides',
                    'Headers', 'HeadersSuccessful', 'Saves', 'Tackles', 'Dribbles', 'ThrowIns',
                    'HitWoodwork', 'Interceptions', 'Blocks', 'Assists', 'LongPasses', 'SuccessfulCrosses']:
            if col in row.index:
                result_row[col] = row[col]
        
        # 保存到对应球队的CSV
        team_dir = os.path.join(output_dir, 'match_data', league_folder, team_name_en)
        os.makedirs(team_dir, exist_ok=True)
        
        csv_file = os.path.join(team_dir, f"{team_name_en}_{season}_matchlog.csv")
        
        if os.path.exists(csv_file):
            existing_df = pd.read_csv(csv_file)
            existing_df = existing_df[~((existing_df['Date'] == date_str) & (existing_df['Opponent'] == opponent_en))]
            new_df = pd.DataFrame([result_row])
            combined_df = pd.concat([existing_df, new_df], ignore_index=True)
        else:
            combined_df = pd.DataFrame([result_row])
        
        combined_df = combined_df.sort_values('Date')
        combined_df.to_csv(csv_file, index=False, encoding='utf-8-sig')


def process_player_data(source_file, output_dir):
    """处理球员数据"""
    xlsx = pd.ExcelFile(source_file)
    basic_df = pd.read_excel(xlsx, sheet_name='比赛基础数据')
    player_df = pd.read_excel(xlsx, sheet_name='球员数据')
    
    if not basic_df.empty:
        league = basic_df.iloc[0]['League']
        match_date = basic_df.iloc[0]['Date']
        if isinstance(match_date, str):
            try:
                match_date = datetime.strptime(match_date, '%Y-%m-%d')
            except:
                match_date = datetime.now()
        opponent = extract_team_name(basic_df.iloc[0]['Away Team'])
    else:
        league = 'Other'
        match_date = datetime.now()
        opponent = ''
    
    league_folder = get_league_folder(league)
    opponent_en = translate_team_name(opponent)
    date_str = match_date.strftime('%Y-%m-%d')
    
    # 只保留球员数据sheet中的球员特定列
    player_columns = ['Number', 'Player', 'Position', 'Rating', 'Key Events', 
                      'Shots', 'Shots on Target', 'Key Passes',
                      'Pass Success Rate', 'Aerial Duels Won', 'Physical Duels']
    
    for team_name_raw, group in player_df.groupby('Team Name'):
        team_name = extract_team_name(str(team_name_raw))
        team_name_en = translate_team_name(team_name)
        
        team_dir = os.path.join(output_dir, 'match_data', league_folder, team_name_en)
        os.makedirs(team_dir, exist_ok=True)
        
        players_file = os.path.join(team_dir, f"{team_name_en}_players.csv")
        
        # 选择球员特定的列，并翻译球队名
        new_df = group[player_columns].copy()
        new_df['MatchDate'] = date_str
        new_df['Opponent'] = opponent_en
        new_df['TeamName'] = team_name_en  # 添加翻译后的球队名
        
        # 更新或合并球员数据
        if os.path.exists(players_file):
            existing_df = pd.read_csv(players_file)
            # 检查是否已存在该比赛的数据
            mask = ~((existing_df['MatchDate'] == date_str) & (existing_df['Opponent'] == opponent_en))
            existing_df = existing_df[mask]
            combined_df = pd.concat([existing_df, new_df], ignore_index=True)
        else:
            combined_df = new_df
        
        # 按日期和球员排序
        combined_df = combined_df.sort_values(['MatchDate', 'Player'])
        combined_df.to_csv(players_file, index=False, encoding='utf-8-sig')


def convert_data():
    """主转换函数"""
    print(f"源目录: {SOURCE_DIR}")
    print(f"目标目录: {TARGET_DIR}")
    print("-" * 60)
    
    files = glob.glob(os.path.join(SOURCE_DIR, '*.xlsx'))
    print(f"找到 {len(files)} 个文件需要转换\n")
    
    processed = 0
    errors = []
    unknown_teams = set()
    
    for i, file_path in enumerate(files):
        filename = os.path.basename(file_path)
        
        if (i + 1) % 100 == 0:
            print(f"进度: {i + 1}/{len(files)} ...")
        
        try:
            parsed = parse_filename(filename)
            if parsed:
                home_en = translate_team_name(parsed['home_team'])
                away_en = translate_team_name(parsed['away_team'])
                
                # 记录未知球队名
                if home_en == parsed['home_team'] and parsed['home_team'] not in TEAM_NAME_MAP:
                    unknown_teams.add(parsed['home_team'])
                if away_en == parsed['away_team'] and parsed['away_team'] not in TEAM_NAME_MAP:
                    unknown_teams.add(parsed['away_team'])
                
                process_match_stats(file_path, TARGET_DIR)
                process_player_data(file_path, TARGET_DIR)
                
                processed += 1
                
        except Exception as e:
            errors.append((filename, str(e)))
    
    print("\n" + "=" * 60)
    print(f"转换完成: {processed}/{len(files)} 个文件")
    
    if errors:
        print(f"\n错误的文件 ({len(errors)}):")
        for f, e in errors[:10]:
            print(f"  - {f}: {e}")
        if len(errors) > 10:
            print(f"  ... 还有 {len(errors) - 10} 个错误")
    
    if unknown_teams:
        print(f"\n未翻译的球队名 ({len(unknown_teams)}):")
        for team in sorted(unknown_teams)[:20]:
            print(f"  - {team}")
        if len(unknown_teams) > 20:
            print(f"  ... 还有 {len(unknown_teams) - 20} 个")


if __name__ == '__main__':
    convert_data()
