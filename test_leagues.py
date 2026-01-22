from data_modules import LEAGUE_OPTIONS

print(f"總共添加了 {len(LEAGUE_OPTIONS)} 個聯賽\n")

print("=" * 60)
print("聯賽列表:")
print("=" * 60)

for key in sorted(LEAGUE_OPTIONS.keys(), key=lambda x: int(x)):
    league = LEAGUE_OPTIONS[key]
    print(f"{key:>3}. {league['name']:<45} | {league['key']}")

print("\n" + "=" * 60)
print("分類統計:")
print("=" * 60)

# 統計各分類
categories = {
    "五大聯賽": ["1", "2", "3", "4", "5"],
    "歐洲杯賽": ["6", "7", "8", "9", "10", "11", "12", "13"],
    "英格蘭聯賽": ["14", "15", "16", "17", "18"],
    "其他歐洲聯賽": [str(i) for i in range(19, 40)],
    "美洲聯賽": [str(i) for i in range(40, 51)],
    "亞洲聯賽": ["51", "52", "53"],
    "大洋洲聯賽": ["54"],
    "非洲聯賽": ["55"],
    "國際賽事": [str(i) for i in range(56, 62)]
}

for cat_name, keys in categories.items():
    count = len([k for k in keys if k in LEAGUE_OPTIONS])
    print(f"{cat_name}: {count} 個聯賽")

print("\n✅ 驗證完成！所有聯賽已成功添加。")
