import os
with open('src/lineup_api.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Check if manual input exists
if 'input(' in content:
    print('MANUAL_INPUT_EXISTS')
else:
    print('NEED_TO_ADD_MANUAL_INPUT')
