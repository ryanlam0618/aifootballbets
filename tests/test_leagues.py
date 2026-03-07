#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
聯賽配置測試（非互動版，適合 CI）
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data_modules import LEAGUE_OPTIONS


def validate_leagues() -> bool:
    total = len(LEAGUE_OPTIONS)
    print(f"總共添加了 {total} 個聯賽\n")

    print("=" * 60)
    print("聯賽列表:")
    print("=" * 60)

    try:
        sorted_keys = sorted(LEAGUE_OPTIONS.keys(), key=lambda x: int(x))
    except Exception:
        sorted_keys = sorted(LEAGUE_OPTIONS.keys())

    for key in sorted_keys:
        league = LEAGUE_OPTIONS[key]
        print(f"{key:>3}. {league['name']:<45} | {league['key']}")

    print("\n" + "=" * 60)
    print("分類統計:")
    print("=" * 60)

    categories = {
        "五大聯賽": ["1", "2", "3", "4", "5"],
        "歐洲杯賽": ["6", "7", "8", "9", "10", "11", "12", "13"],
        "英格蘭聯賽": ["14", "15", "16", "17", "18"],
        "其他歐洲聯賽": [str(i) for i in range(19, 40)],
        "美洲聯賽": [str(i) for i in range(40, 51)],
        "亞洲聯賽": ["51", "52", "53"],
        "大洋洲聯賽": ["54"],
        "非洲聯賽": ["55"],
        "國際賽事": [str(i) for i in range(56, 62)],
    }

    for cat_name, keys in categories.items():
        count = len([k for k in keys if k in LEAGUE_OPTIONS])
        print(f"{cat_name}: {count} 個聯賽")

    # 最基本驗證
    required = ["1", "2", "3", "4", "5"]
    missing = [k for k in required if k not in LEAGUE_OPTIONS]

    if missing:
        print(f"\n❌ 缺少必要聯賽 key: {missing}")
        return False

    print("\n✅ 驗證完成！所有核心聯賽已成功添加。")
    return True


if __name__ == "__main__":
    ok = validate_leagues()
    raise SystemExit(0 if ok else 1)
