# 检查 API 联赛名称
from DrissionPage import ChromiumPage, ChromiumOptions

co = ChromiumOptions().headless()
co.set_browser_path(r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe')
page = ChromiumPage(co)

# 检查欧冠和杯赛日期
dates = ['2024-12-10', '2024-05-15', '2024-01-17', '2024-02-21', '2023-05-03']
all_cups = set()

for date in dates:
    try:
        url = f'https://www.sofascore.com/api/v1/sport/football/scheduled-events/{date}'
        page.get(url)
        page.wait(1)
        data = page.json
        
        events = data.get('events', [])
        
        # 过滤杯赛相关的
        for e in events:
            status = e.get('status', {})
            if status.get('code') == 100:  # finished
                name = e.get('tournament', {}).get('name', '')
                # 查找欧洲杯赛和主要国家杯赛
                if name and any(x in name.lower() for x in ['champions', 'europa', 'conference', 'fa cup', 'copa', 'dfb', 'coppa', 'trophee', 'supercoppa', 'supercopa', 'community']):
                    all_cups.add(name)
    except Exception as ex:
        print(f'Error on {date}: {ex}')
            
print('Cup tournaments found:')
for t in sorted(all_cups):
    print(f'  "{t}"')
page.quit()
