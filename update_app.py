"""
app.py Update Script
Updates app.py to:
1. Use Gemini API + The Odds API for team name matching
2. Change lineup fetching to: local files -> Fotmob ID input -> remove API-Football
3. Delete hardcoded team mappings
"""

import re

# Read the original app.py
with open('c:/Users/Ryan/python/.vscode/fb_ai_bets/app.py', 'r', encoding='utf-8') as f:
    content = f.read()

# ============================================
# 1. UPDATE IMPORTS - Add The Odds API loader
# ============================================
old_imports = '''try:
    from config import settings
    # 匯入 LEAGUE_OPTIONS
    from src.data_modules import HistoryRepo, RealOddsFetcher, OddsPoint, LEAGUE_OPTIONS
    from src.llm_clients import llm
    from src.finance import calculate_kelly_stake, ExcelLogger
    from src.math_models import PoissonModel, MonteCarloSimulator, DixonColesModel
    from src.math_models_v2 import OptimizedDixonColes, MonteCarloSimulator as MCSim_v2
    # 導入 v3 數學模型改進
    from src.math_models_v3 import (
        NegativeBinomialModel,           # 負二項分布進球模型
        DynamicKEloSystem,              # 動態K因子 Elo
        MonteCarloSimulatorV3,          # 蒙地卡羅模擬 V3
        ConfidenceKelly                 # 信心度 Kelly
    )
    # 導入高級模型
    from src.advanced_models import (
        ExponentialDecayXGForecaster,   # 指數衰減 xG
        BayesianGoalModel,              # 貝葉斯進球模型
        TeamFormLSTM,                  # LSTM 時序模型
        BettingRLAgent                  # RL 投注策略
    )
    from src.injury_api import InjuryDataAggregator, get_injury_report
    from src.lineup_api import LineupAggregator, get_lineup
    from src.team_name_matcher import match_teams, get_team_info
except ImportError as e:
    print(f"模組載入失敗: {e}", flush=True)
    sys.exit(1)'''

new_imports = '''try:
    from config import settings
    # 匯入 LEAGUE_OPTIONS
    from src.data_modules import HistoryRepo, RealOddsFetcher, OddsPoint, LEAGUE_OPTIONS
    from src.llm_clients import llm
    from src.finance import calculate_kelly_stake, ExcelLogger
    from src.math_models import PoissonModel, MonteCarloSimulator, DixonColesModel
    from src.math_models_v2 import OptimizedDixonColes, MonteCarloSimulator as MCSim_v2
    # 導入 v3 數學模型改進
    from src.math_models_v3 import (
        NegativeBinomialModel,           # 負二項分布進球模型
        DynamicKEloSystem,              # 動態K因子 Elo
        MonteCarloSimulatorV3,          # 蒙地卡羅模擬 V3
        ConfidenceKelly                 # 信心度 Kelly
    )
    # 導入高級模型
    from src.advanced_models import (
        ExponentialDecayXGForecaster,   # 指數衰減 xG
        BayesianGoalModel,              # 貝葉斯進球模型
        TeamFormLSTM,                  # LSTM 時序模型
        BettingRLAgent                  # RL 投注策略
    )
    from src.injury_api import InjuryDataAggregator, get_injury_report
    # Import The Odds API team loader
    from scripts.fetch_odds_teams import load_teams_from_file, search_team, LEAGUE_KEYS
except ImportError as e:
    print(f"模組載入失敗: {e}", flush=True)
    sys.exit(1)

# Load The Odds API team data at module level
ODDS_TEAMS_DATA = None
try:
    ODDS_TEAMS_DATA = load_teams_from_file()
except:
    pass'''

content = content.replace(old_imports, new_imports)

# ============================================
# 2. ADD GEMINI TEAM MATCHING FUNCTION
# ============================================
# Add after the imports section, before find_lineup_file

gemini_matching_code = '''
# ============================================
# Gemini API Team Matching Functions
# ============================================
def get_gemini_team_match(user_team_name, league_key):
    """
    Use Gemini API to match user input team name to The Odds API team names
    Returns: dict with 'matched_name', 'odds_name', 'confidence'
    """
    if not ODDS_TEAMS_DATA or league_key not in ODDS_TEAMS_DATA:
        return {'matched_name': user_team_name, 'confidence': 0}
    
    teams_info = ODDS_TEAMS_DATA.get(league_key, {}).get('teams', {})
    odds_team_names = list(teams_info.keys())
    
    if not odds_team_names:
        return {'matched_name': user_team_name, 'confidence': 0}
    
    # Try exact/partial match first
    for name in odds_team_names:
        if user_team_name.lower() in name.lower() or name.lower() in user_team_name.lower():
            return {
                'matched_name': name,
                'odds_name': name,
                'confidence': 1.0
            }
    
    # Use Gemini API for fuzzy matching
    if settings.GEMINI_API_KEY:
        prompt = f"""Match this football team name to the closest name in the list:
        
User input: "{user_team_name}"
Available names: {odds_team_names[:30]}

Return ONLY the best matching name from the list, or the original input if no good match."""
        
        try:
            response = llm.generate(prompt, max_tokens=100)
            # Extract team name from response
            for name in odds_team_names:
                if name.lower() in response.lower():
                    return {
                        'matched_name': name,
                        'odds_name': name,
                        'confidence': 0.9
                    }
        except Exception as e:
            print(f"   [GEMINI] API error: {str(e)[:50]}")
    
    # Fallback: return original
    return {'matched_name': user_team_name, 'confidence': 0}


def get_odds_team_info(league_key, team_name):
    """Get team info from The Odds API data"""
    if not ODDS_TEAMS_DATA:
        return None
    
    teams_info = ODDS_TEAMS_DATA.get(league_key, {}).get('teams', {})
    return teams_info.get(team_name)

'''

# Insert before find_lineup_file function
content = content.replace(
    'def find_lineup_file(home_team, away_team, data_folder="data"):',
    gemini_matching_code + '\ndef find_lineup_file(home_team, away_team, data_folder="data"):'
)

# ============================================
# 3. UPDATE TEAM MATCHING SECTION (Lines ~162-200)
# ============================================
old_team_matching = '''    # ========== [整合] 使用 Gemini API 智能匹配球隊名稱 ==========
    print(f"\\n🔗 [1.1/4] 正在整合 The Odds API 與 API-Football 數據...", flush=True)
    print(f"   原始輸入: {home} vs {away}")

    # 使用 team_name_matcher 整合兩個 API 的 ID
    match_result = match_teams(home, away)

    # 獲取標準化後的隊名
    odds_home = home  # 預設使用輸入
    odds_away = away
    api_home = home   # 預設使用輸入
    api_away = away

    # 解析配對結果
    if match_result.get('home', {}).get('matched'):
        api_home = match_result['home'].get('api_name', home)
        odds_home = match_result['home'].get('odds_name', home)
        api_home_id = match_result['home'].get('api_football_id')
        print(f"   [主隊] The Odds API: {odds_home} | API-Football ID: {api_home_id} ({api_home})")
    else:
        api_home_id = None
        print(f"   [主隊] ⚠️ 無法自動配對，使用原始名稱: {home}")

    if match_result.get('away', {}).get('matched'):
        api_away = match_result['away'].get('api_name', away)
        odds_away = match_result['away'].get('odds_name', away)
        api_away_id = match_result['away'].get('api_football_id')
        print(f"   [客隊] The Odds API: {odds_away} | API-Football ID: {api_away_id} ({api_away})")
    else:
        api_away_id = None
        print(f"   [客隊] ⚠️ 無法自動配對，使用原始名稱: {away}")

    # 檢查是否需要 Gemini 進一步匹配
    if not match_result.get('home', {}).get('matched') or not match_result.get('away', {}).get('matched'):
        print(f"   💡 提示: 如需更精確的匹配，請確認球隊名稱拼寫正確。")

    # 使用 API-Football ID 進行後續操作
    home_team_id = api_home_id if api_home_id else match_result.get('home', {}).get('api_football_id')
    away_team_id = api_away_id if api_away_id else match_result.get('away', {}).get('api_football_id')'''

new_team_matching = '''    # ========== [整合] 使用 Gemini API + The Odds API 智能匹配球隊名稱 ==========
    print(f"\\n🔗 [1.1/4] 正在整合 The Odds API 與 Gemini API 數據...", flush=True)
    print(f"   原始輸入: {home} vs {away}")

    # 使用 Gemini API 匹配 The Odds API 的球隊名稱
    home_match = get_gemini_team_match(home, league_key)
    away_match = get_gemini_team_match(away, league_key)

    odds_home = home_match.get('matched_name', home)
    odds_away = away_match.get('matched_name', away)
    
    # 獲取 The Odds API 球隊信息
    home_odds_info = get_odds_team_info(league_key, odds_home)
    away_odds_info = get_odds_team_info(league_key, odds_away)

    print(f"   [主隊] The Odds API: {odds_home} (confidence: {home_match.get('confidence', 0):.0%})")
    print(f"   [客隊] The Odds API: {odds_away} (confidence: {away_match.get('confidence', 0):.0%})")

    # 歷史數據庫使用的名稱（嘗試找到最接近的）
    db_home = odds_home
    db_away = odds_away'''

content = content.replace(old_team_matching, new_team_matching)

# ============================================
# 4. UPDATE LINEUP FETCHING (Lines ~210-220)
# ============================================
old_lineup_fetching = '''    # 2.5 讀取/獲取陣容數據
    print(f"\\n👕 [1.2/4] 正在獲取陣容數據...", flush=True)

    # 首先嘗試讀取本地陣容檔案 (使用用戶輸入的原始名稱)
    lineup_data = find_lineup_file(home, away)

    if lineup_data:
        print(f"   [本地] 找到陣容檔案: {lineup_data['home_team']['name']} vs {lineup_data['away_team']['name']}")
        print(f"      主隊陣容: {len(lineup_data['home_team']['starters'])} 人 | 客隊陣容: {len(lineup_data['away_team']['starters'])} 人")
    else:
        # 本地沒有，嘗試從 API 獲取 (使用 API-Football 標準化後的隊名)
        print(f"   [API] 未找到本地檔案，嘗試 API 獲取...")
        lineup_aggregator = LineupAggregator()
        lineup_data = lineup_aggregator.get_lineup(api_home, api_away)'''

new_lineup_fetching = '''    # ========== [1.2/4] 讀取/獲取陣容數據 ==========
    print(f"\\n👕 [1.2/4] 正在獲取陣容數據...", flush=True)

    # 首先嘗試讀取本地陣容檔案
    lineup_data = find_lineup_file(home, away)

    if lineup_data:
        print(f"   [LOCAL] 找到陣容檔案: {lineup_data['home_team']['name']} vs {lineup_data['away_team']['name']}")
        print(f"      主隊陣容: {len(lineup_data['home_team']['starters'])} 人 | 客隊陣容: {len(lineup_data['away_team']['starters'])} 人")
    else:
        # 本地沒有，詢問 Fotmob ID
        print(f"   [LOCAL] 未找到本地檔案")
        fotmob_id = input("   請輸入 Fotmob Match ID (輸入 n 跳過): ").strip()
        
        if fotmob_id.lower() != 'n' and fotmob_id:
            try:
                from src.fotmob_api import get_lineup_by_match_id
                lineup_data = get_lineup_by_match_id(fotmob_id)
                if lineup_data:
                    print(f"   [FOTMOB] 成功獲取陣容: {lineup_data['home_team']['name']} vs {lineup_data['away_team']['name']}")
            except Exception as e:
                print(f"   [FOTMOB] 獲取失敗: {str(e)[:50]}")
        
        if not lineup_data:
            print(f"   [INFO] 無陣容數據，使用佔位數據")
            lineup_data = {
                'home_team': {'name': home, 'starters': [], 'bench': []},
                'away_team': {'name': away, 'starters': [], 'bench': []}
            }'''

content = content.replace(old_lineup_fetching, new_lineup_fetching)

# ============================================
# 5. REMOVE HARDCODED ALIAS_MAP
# ============================================
# Find and remove the ALIAS_MAP definition (around lines 356-530)
alias_map_pattern = r'            # 常見縮寫/別名映射 \(提高匹配準確率\)\s+ALIAS_MAP = \{[^}]+\}[^}]+\}'

# This is complex, let's just remove the entire section by finding its boundaries
# We'll replace the section that contains ALIAS_MAP

# Find ALIAS_MAP section start
alias_start = content.find('            # 常見縮寫/別名映射 (提高匹配準確率)')
if alias_start != -1:
    # Find where this section ends - look for the function closing or next major section
    # The section ends when we find an empty line followed by a new major code block
    
    # Find the next occurrence of "def " after the alias map
    next_def = content.find('\n            def ', alias_start)
    if next_def != -1:
        # Also find where fuzzy_match_team function ends
        func_end = content.find('\n\n            # 使用模糊匹配', alias_start)
        if func_end != -1 and func_end < next_def:
            # Remove from alias_start to func_end
            content = content[:alias_start] + content[func_end:]

# ============================================
# 6. UPDATE REFERENCES TO api_home/api_away
# ============================================
# Replace references to use odds_home/odds_away or db_home/db_away

# Replace historical data references
content = content.replace('repo.get_match_context(home, away, league_name)', 
                         'repo.get_match_context(db_home, db_away, league_name)')
content = content.replace('repo.get_lineup_prediction(home, away)',
                         'repo.get_lineup_prediction(db_home, db_away)')

# Write the modified content
with open('c:/Users/Ryan/python/.vscode/fb_ai_bets/app.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("app.py updated successfully!")
print("\\nChanges made:")
print("1. Added Gemini API + The Odds API team matching")
print("2. Changed lineup fetching: local files -> Fotmob ID input")
print("3. Removed hardcoded ALIAS_MAP")
print("4. Updated historical data references")
