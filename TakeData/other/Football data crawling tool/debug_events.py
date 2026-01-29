#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
調試球員事件提取 - 查找所有球員事件
"""

import sys
import os
import time
import re
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
    print("調試球員事件提取...")
    
    co = ChromiumOptions()
    chrome_path = get_chrome_path()
    co.headless(False)
    co.auto_port(True)
    co.mute(True)
    if chrome_path:
        co.set_browser_path(chrome_path)
    
    page = WebPage('d', chromium_options=co)
    
    try:
        match_id = "2261882"
        url = f"https://live.titan007.com/detail/{match_id}cn.htm"
        print(f"打開: {url}")
        
        page.get(url)
        time.sleep(5)
        
        print(f"\n頁面標題: {page.title}")
        
        # 查找所有 play 元素
        play_elements = page.eles('xpath://div[@class="plays"]//div[@class="play"]')
        print(f"\n找到 {len(play_elements)} 個 play 元素")
        
        # 收集所有事件圖片
        all_events = {}
        
        for i, play in enumerate(play_elements):
            play_text = play.text
            play_html = play.html
            
            # 獲取球員名字
            name_elem = play.ele('css:div.name')
            player_name = name_elem.text.strip() if name_elem else "未知"
            
            # 獲取球員號碼
            number_elem = play.ele('css:i')
            player_number = number_elem.text.strip() if number_elem else ""
            
            # 查找 playerTech div
            tech_div = play.ele('xpath:.//div[starts-with(@id, "playerTech_")]')
            if tech_div:
                tech_imgs = tech_div.eles('tag:img')
                
                for img in tech_imgs:
                    src = img.attr('src') or ''
                    alt = img.attr('alt') or ''
                    
                    # 提取圖片文件名
                    filename = src.split('/')[-1] if src else ''
                    
                    if filename:
                        if filename not in all_events:
                            all_events[filename] = []
                        
                        all_events[filename].append({
                            'player': player_name,
                            'number': player_number,
                            'time': alt
                        })
        
        # 打印所有事件圖片
        print(f"\n=== 所有事件圖片 ===")
        for filename, events in sorted(all_events.items()):
            print(f"\n{filename} ({len(events)} 次):")
            for event in events:
                print(f"  - {event['player']} ({event['number']}): {event['time']}")
        
        # 打印球員詳細事件
        print(f"\n=== 球員事件詳情 ===")
        for i, play in enumerate(play_elements):
            play_text = play.text
            
            # 只打印有事件的球員
            tech_div = play.ele('xpath:.//div[starts-with(@id, "playerTech_")]')
            if tech_div:
                tech_imgs = tech_div.eles('tag:img')
                if tech_imgs:
                    name_elem = play.ele('css:div.name')
                    player_name = name_elem.text.strip() if name_elem else "未知"
                    
                    print(f"\n{player_name}:")
                    for img in tech_imgs:
                        src = img.attr('src') or ''
                        alt = img.attr('alt') or ''
                        print(f"  {src.split('/')[-1]} - {alt}")
        
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
