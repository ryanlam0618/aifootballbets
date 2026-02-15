"""
Remove fuzzy matching code from app.py - Comprehensive approach
"""

with open('c:/Users/Ryan/python/.vscode/fb_ai_bets/app.py', 'r', encoding='utf-8') as f:
    content = f.read()

lines = content.split('\n')

# Find and remove problematic sections
new_lines = []
skip_until = None
skip_has_fuzzy = False

for i, line in enumerate(lines):
    # Skip HAS_FUZZY section
    if 'from fuzzywuzzy import fuzz, process' in line:
        skip_has_fuzzy = True
        continue
    if skip_has_fuzzy:
        if 'HAS_FUZZY = False' in line:
            skip_has_fuzzy = False
        continue
    
    # Skip ALIAS_MAP definition
    if 'ALIAS_MAP = {' in line:
        skip_until = '}'
        continue
    if skip_until:
        if line == skip_until:
            skip_until = None
        continue
    
    # Skip fuzzy_match_team function
    if 'def fuzzy_match_team(' in line:
        # Skip until a line that doesn't start with whitespace or is empty
        new_lines.append(line)  # Add the function definition first
        continue
    
    new_lines.append(line)

# Now we need to handle the function body - it spans multiple lines
# Let me do a different approach - find the problematic sections and remove them
new_content = '\n'.join(new_lines)

# Find and remove the function by looking for patterns
import re

# Remove the fuzzy_match_team function
pattern = r'def fuzzy_match_team\(input_name, team_list, threshold=60\):.*?return input_name\s*# fallback\s*'
new_content = re.sub(pattern, '', new_content, flags=re.DOTALL)

with open('c:/Users/Ryan/python/.vscode/fb_ai_bets/app.py', 'w', encoding='utf-8') as f:
    f.write(new_content)

print('Done')
