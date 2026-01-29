#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
調試球員數據提取 - 找到正確的選擇器
"""

import sys
import os
import time
import re
from datetime import datetime
from DrissionPage import WebPage, ChromiumOptions


def get_chrome_path():
    possible_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    for path in possible_paths:
        if os.path.exists(path):
            return path
    return None


def main():
    print("調試球員數據提取...")
    
    co = ChromiumOptions()
    chrome_path = get_chrome_path()
    co.headless(False)
    co.auto_port(True)
    co.mute(True)
    if chrome_path:
        co.set_browser_path(chrome_path)
    
    page = WebPage('d', chromium_options=co)
    
    try:
        # 打開澳職比賽頁面
        match_id = "2261882"
        url = f"https://live.titan007.com/detail/{match_id}cn.htm"
        print(f"打開: {url}")
        
        page.get(url)
        time.sleep(5)
        
        print(f"\n頁面標題: {page.title}")
        
        # 1. 查找 content div
        print("\n=== 查找 content div ===")
        content_div = page.ele('xpath://div[@class="content"]')
        if content_div:
            print("找到 content div")
            content_html = content_div.html
            print(f"content HTML 長度: {len(content_html)}")
            
            # 打印 content 的前 3000 字符
            print(f"\ncontent HTML (前3000字符):")
            print(content_html[:3000])
        
        # 2. 查找 matchBox2
        print("\n\n=== 查找 matchBox2 ===")
        matchbox = page.ele('xpath://div[@id="matchBox2"]')
        if matchbox:
            print("找到 matchBox2")
            matchbox_html = matchbox.html
            print(f"\nmatchBox2 HTML (前3000字符):")
            print(matchbox_html[:3000])
        
        # 3. 直接查找所有 playBox
        print("\n\n=== 查找所有 playBox ===")
        play_boxes = page.eles('xpath://div[@class="playBox"]')
        print(f"找到 {len(play_boxes)} 個 playBox")
        
        for i, box in enumerate(play_boxes[:3]):
            box_html = box.html
            print(f"\nplayBox[{i}] HTML:")
            print(box_html[:500])
        
        # 4. 查找所有 class="home" 或 class="guest" 的 div
        print("\n\n=== 查找 home/guest div ===")
        home_divs = page.eles('xpath://div[@class="home"]')
        guest_divs = page.eles('xpath://div[@class="guest"]')
        
        print(f"找到 {len(home_divs)} 個 home div")
        print(f"找到 {len(guest_divs)} 個 guest div")
        
        if home_divs:
            print(f"\nhome div HTML (前1500字符):")
            print(home_divs[0].html[:1500])
        
        if guest_divs:
            print(f"\nguest div HTML (前1500字符):")
            print(guest_divs[0].html[:1500])
        
        # 5. 查找 class 包含 "plays" 的元素
        print("\n\n=== 查找包含 plays 的元素 ===")
        plays_elements = page.eles('xpath://*[contains(@class, "plays")]')
        print(f"找到 {len(plays_elements)} 個包含 'plays' 的元素")
        
        for i, elem in enumerate(plays_elements[:3]):
            print(f"\nplays[{i}] class: {elem.attrs.get('class', 'no class')}")
            print(f"  HTML (前300字符): {elem.html[:300]}")
        
        input("\n按 Enter 退出...")
        
    except Exception as e:
        print(f"錯誤: {e}")
        import traceback
        traceback.print_exc()
    finally:
        try:
            page.quit()
        except:
            pass


if __name__ == '__main__':
    main()
