"""
Remove fuzzy matching code from app.py - Direct approach
"""

with open('c:/Users/Ryan/python/.vscode/fb_ai_bets/app.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Remove HAS_FUZZY import section
content = content.replace('''try:
                from fuzzywuzzy import fuzz, process
                HAS_FUZZY = True
            except ImportError:
                HAS_FUZZY = False
''', '')

# Remove ALIAS_MAP definition (find the start and end markers)
start_marker = '# 常見縮寫/別名映射 (提高匹配準確率)'
end_marker = '"stade rennais" : "Stade Rennais",'

start_idx = content.find(start_marker)
if start_idx != -1:
    # Find the end of ALIAS_MAP
    end_idx = content.find(end_marker, start_idx)
    if end_idx != -1:
        # Find the closing brace
        brace_idx = content.find('}', end_idx)
        if brace_idx != -1:
            # Remove from start marker to closing brace
            content = content[:start_idx] + content[brace_idx+1:]

# Remove fuzzy_match_team function
start_marker2 = 'def fuzzy_match_team(input_name, team_list, threshold=60):'
start_idx2 = content.find(start_marker2)
if start_idx2 != -1:
    # Find the end of function (next non-indented line or blank line)
    lines = content[start_idx2:].split('\n')
    for i, line in enumerate(lines[1:], 1):
        if line and not line.startswith(' '):
            content = content[:start_idx2] + content[start_idx2 + sum(len(l)+1 for l in lines[:i]):]
            break

with open('c:/Users/Ryan/python/.vscode/fb_ai_bets/app.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Done')
