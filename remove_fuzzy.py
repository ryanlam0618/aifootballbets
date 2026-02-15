"""
Remove fuzzy matching code from app.py
"""
import re

with open('c:/Users/Ryan/python/.vscode/fb_ai_bets/app.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Remove HAS_FUZZY import section
content = re.sub(
    r'try:\s*from fuzzywuzzy import fuzz, process\s*HAS_FUZZY = True\s*except ImportError:\s*HAS_FUZZY = False\s*',
    '',
    content
)

# Remove ALIAS_MAP definition
content = re.sub(
    r'# 常見縮寫/別名映射.*?"stade rennais" : "Stade Rennais",\s*\}\s*',
    '',
    content,
    flags=re.DOTALL
)

# Remove fuzzy_match_team function
content = re.sub(
    r'def fuzzy_match_team\(input_name, team_list, threshold=60\):.*?return input_name\s*# fallback\s*',
    '',
    content,
    flags=re.DOTALL
)

with open('c:/Users/Ryan/python/.vscode/fb_ai_bets/app.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Done')
