import os
with open('src/lineup_api.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Check for _save_lineup method
if 'def _save_lineup' in content:
    print('_save_lineup EXISTS')
else:
    print('_save_lineup NOT FOUND - need to add')
    
# Check for FotMob get_lineup method
if 'def get_lineup(self, home_team' in content:
    # Find the FotMob class
    start = content.find('class FotMobLineups:')
    if start > 0:
        # Find the get_lineup in FotMob
        fotmob_section = content[start:start+3000]
        if 'def get_lineup(self, home_team' in fotmob_section:
            print('FotMob has get_lineup - need to replace with get_lineup_by_id')
        else:
            print('FotMob already using get_lineup_by_id')
