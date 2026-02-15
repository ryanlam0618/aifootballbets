# 检查 API 联赛名称
from DrissionPage import ChromiumPage, ChromiumOptions

co = ChromiumOptions().headless()
co.set_browser_path(r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe')
page = ChromiumPage(co)

# 检查五大联赛日期
dates = ['2025-10-20', '2025-11-15', '2025-12-15']
all_leagues = {}

for date in dates:
    try:
        url = f'https://www.sofascore.com/api/v1/sport/football/scheduled-events/{date}'
        page.get(url)
        page.wait(1)
        data = page.json
        
        events = data.get('events', [])
        
        for e in events:
            status = e.get('status', {})
            if status.get('code') == 100:  # finished
                name = e.get('tournament', {}).get('name', '')
                category = e.get('tournament', {}).get('category', {}).get('name', '')
                if name:
                    key = (name, category)
                    all_leagues[key] = all_leagues.get(key, 0) + 1
    except Exception as ex:
        print(f'Error on {date}: {ex}')
            
print('All leagues found:')
for (name, category), count in sorted(all_leagues.items(), key=lambda x: -x[1]):
    print(f'  "{name}" ({category}): {count}')

page.quit()
