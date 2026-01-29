#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
A-League Data Crawler - 調試版 v3
檢查頁面結構和連結
"""

import sys
import os
import time
import random
import re
from datetime import datetime
from DrissionPage import WebPage, ChromiumOptions


class DebugCrawler:
    def __init__(self):
        pass
    
    @staticmethod
    def get_chrome_path():
        possible_paths = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        ]
        for path in possible_paths:
            if os.path.exists(path):
                return path
        return None
    
    @staticmethod
    def create_browser_instance():
        co = ChromiumOptions()
        chrome_path = DebugCrawler.get_chrome_path()
        co.headless(False)
        co.auto_port(True)
        co.mute(True)
        if chrome_path:
            co.set_browser_path(chrome_path)
        return WebPage('d', chromium_options=co)
    
    def find_detail_links(self, page):
        """查找頁面中所有可能的比賽詳情連結"""
        print("\n查找比賽詳情連結...")
        
        links = page.eles('tag:a')
        print(f"找到 {len(links)} 個連結")
        
        detail_links = []
        for link in links:
            href = link.attrs.get('href', '')
            text = link.text.strip()[:50] if link.text else ""
            
            # 檢查是否與澳職相關
            if 'detail' in href.lower() or '澳洲' in text or 'A-League' in text.upper():
                detail_links.append({
                    'href': href,
                    'text': text
                })
                print(f"  可能相關連結: {text[:30]} -> {href[:80]}")
        
        return detail_links
    
    def find_match_urls(self, page, date_str):
        """嘗試找到澳職比賽的 URL"""
        print(f"\n分析頁面結構...")
        
        # 方法1: 查找帶有數字的 href
        all_links = page.eles('tag:a')
        print(f"總共 {len(all_links)} 個連結")
        
        # 方法2: 查找 td 中包含 onclick 的元素
        tds = page.eles('tag:td')
        for td in tds:
            onclick = td.attrs.get('onclick', '')
            if onclick:
                # 查找各種 JavaScript 調用
                patterns = [
                    (r"openDetail\(['\"]?(\d+)", 'openDetail'),
                    (r"goDetail\(['\"]?(\d+)", 'goDetail'),
                    (r"showDetail\(['\"]?(\d+)", 'showDetail'),
                    (r"viewMatch\(['\"]?(\d+)", 'viewMatch'),
                ]
                for pattern, name in patterns:
                    match = re.search(pattern, onclick)
                    if match:
                        print(f"  找到 {name}: {match.group(1)}")
        
        # 方法3: 檢查頁面中所有的 script
        scripts = page.eles('tag:script')
        for script in scripts:
            script_text = script.text if script.text else ""
            if 'detail' in script_text.lower():
                # 查找數字 ID
                matches = re.findall(r'["\']?(\d{6,})["\']?', script_text)
                if matches:
                    print(f"  Script 中的數字: {matches[:5]}")
        
        # 方法4: 直接構造 URL 測試
        print(f"\n測試可能的 URL 格式...")
        
        # 嘗試不同的 URL 模式
        test_ids = ['12', '49', '273', '2261882']  # 從頁面中找到的數字
        for test_id in test_ids:
            url = f"https://live.titan007.com/detail/{test_id}cn.htm"
            print(f"  測試: {url}")
            # 不實際打開，只是打印
        
        return []
    
    def analyze_page_structure(self, page):
        """分析頁面結構"""
        print("\n頁面結構分析:")
        
        # 查找表格
        tables = page.eles('tag:table')
        print(f"表格數量: {len(tables)}")
        
        # 查找 iframe
        iframes = page.eles('tag:iframe')
        print(f"iframe 數量: {len(iframes)}")
        for iframe in iframes[:3]:
            src = iframe.attr('src', '')[:100]
            print(f"  iframe src: {src}")
        
        # 查找 form
        forms = page.eles('tag:form')
        print(f"表單數量: {len(forms)}")
        for form in forms[:3]:
            action = form.attrs.get('action', '')
            method = form.attrs.get('method', '')
            print(f"  form: action={action}, method={method}")
        
        # 查找帶有 onclick 的元素
        elements_with_onclick = page.eles('xpath://*[@onclick]')
        print(f"帶有 onclick 的元素: {len(elements_with_onclick)}")
        
        # 查找澳職相關的 onclick
        for elem in elements_with_onclick[:10]:
            onclick = elem.attrs.get('onclick', '')
            if 'Detail' in onclick or 'detail' in onclick or 'go' in onclick.lower():
                text = elem.text.strip()[:30] if elem.text else ""
                print(f"  {text[:30]}: {onclick[:100]}")
    
    def run(self):
        """運行調試"""
        print("開始調試...")
        
        web_page = None
        try:
            web_page = self.create_browser_instance()
            
            date_str = "20221111"
            url = f'https://bf.titan007.com/football/Over_{date_str}.htm'
            print(f"打開: {url}")
            
            web_page.get(url)
            time.sleep(3)
            
            print(f"頁面標題: {web_page.title}")
            print(f"URL: {web_page.url}")
            
            # 分析頁面結構
            self.analyze_page_structure(web_page)
            
            # 查找連結
            self.find_detail_links(web_page)
            
            # 找澳職行
            all_rows = web_page.eles('xpath://tr[@height="18"]')
            print(f"\n\n找到 {len(all_rows)} 行")
            
            for row in all_rows:
                tds = row.eles('tag:td')
                if len(tds) > 0:
                    league = tds[0].text.strip()
                    if '澳洲' in league:
                        print(f"\n\n找到澳職行!")
                        print(f"  tr id: {row.attrs.get('id', 'none')}")
                        print(f"  tr name: {row.attrs.get('name', 'none')}")
                        print(f"  tr infoid: {row.attrs.get('infoid', 'none')}")
                        
                        # 檢查每個 td 的 onclick
                        for i, td in enumerate(tds):
                            onclick = td.attrs.get('onclick', '')
                            if onclick:
                                print(f"  TD[{i}] onclick: {onclick[:80]}")
                            
                            # 檢查 td 內的所有子元素
                            children = td.eles('xpath:.//*')
                            for child in children:
                                child_onclick = child.attrs.get('onclick', '')
                                if child_onclick and ('Detail' in child_onclick or 'detail' in child_onclick):
                                    print(f"    子元素 onclick: {child_onclick[:80]}")
                        
                        # 打印完整 HTML
                        print(f"\n  行 HTML:")
                        print(f"  {row.html[:500]}...")
                        
                        break
            
            # 測試手動輸入 URL
            print(f"\n\n{'='*70}")
            print("測試 URL 格式...")
            print(f"{'='*70}")
            
            # 問用戶
            print("\n請在瀏覽器中手動訪問澳職比賽，然後把 URL 發給我")
            print("例如: https://live.titan007.com/detail/xxxxcn.htm")
            
            input("\n按 Enter 退出...")
            
        except Exception as e:
            print(f"錯誤: {e}")
            import traceback
            traceback.print_exc()
        finally:
            if web_page:
                try:
                    web_page.quit()
                except:
                    pass


if __name__ == '__main__':
    crawler = DebugCrawler()
    crawler.run()
