import time
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from urllib.parse import urlparse
import subprocess

# --- WinError 6 修補 ---
def safe_del(self):
    try:
        self.quit()
    except OSError:
        pass
    except Exception:
        pass

uc.Chrome.__del__ = safe_del
# --------------------------------

def handle_cookie_consent(driver):
    """嘗試關閉 Cookie 同意視窗，避免遮擋資料"""
    try:
        cookie_locators = [
            (By.ID, "onetrust-accept-btn-handler"),
            (By.XPATH, "//button[contains(text(), 'I Accept')]"),
            (By.XPATH, "//button[contains(text(), 'Accept All')]"),
            (By.XPATH, "//button[contains(text(), 'AGREE')]")
        ]
        
        for locator in cookie_locators:
            try:
                btn = driver.find_element(*locator)
                if btn.is_displayed():
                    btn.click()
                    print("  -> [Cookie] 已自動點擊同意按鈕")
                    time.sleep(1)
                    return
            except:
                pass
    except:
        pass

def get_chrome_version():
    """自動取得系統安裝的 Chrome 版本"""
    try:
        # Windows: 從 registry 讀取 Chrome 版本
        result = subprocess.run(
            ['reg', 'query', 'HKLM\\SOFTWARE\\Google\\Chrome\\BLBeacon', '/v', 'version'],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            for line in result.stdout.split('\n'):
                if 'version' in line.lower():
                    version = line.split()[-1]
                    return int(version.split('.')[0])
    except:
        pass
    
    # 備用方法: 從 Chrome exe 取得版本
    try:
        result = subprocess.run(
            ['powershell', '-Command', '(Get-Item "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe").VersionInfo.FileVersion'],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            version = result.stdout.strip().split('.')[0]
            return int(version)
    except:
        pass
    
    return None

def get_upcoming_matches(league_url):
    options = uc.ChromeOptions()
    options.page_load_strategy = 'eager'
    options.add_argument('--start-maximized')
    options.add_argument('--disable-popup-blocking')
    options.add_argument('--headless')  # 使用新的無頭模式
    options.add_argument('--disable-gpu')
    
    match_urls = []
    
    # 解析網址路徑，例如: /football/england/premier-league
    parsed_path = urlparse(league_url).path
    if parsed_path.endswith('/'):
        parsed_path = parsed_path[:-1]

    print(f"\n啟動: {league_url}")

    # 自動檢測 Chrome 版本，若失敗則使用預設值 143
    detected_version = get_chrome_version()
    version_main = detected_version if detected_version else 143
    print(f"  -> [Chrome] 使用版本: {version_main} (偵測到: {detected_version})")

    driver = None
    try:
        driver = uc.Chrome(options=options, version_main=version_main)
        driver.get(league_url)
        
        # 1. 處理 Cookie
        handle_cookie_consent(driver)
        
        # 2. 等待資料載入
        wait = WebDriverWait(driver, 15)
        try:
            # 等待任一比賽行出現
            wait.until(EC.presence_of_element_located((By.CLASS_NAME, "eventRow")))
        except:
            print("  -> [提示] 載入較慢，嘗試滾動頁面...")

        # 3. 滾動頁面 (重要：確保所有未來的比賽都載入)
        # 這裡分段滾動，模擬真人操作並觸發 lazy loading
        for scroll in [500, 1500, 2500, "document.body.scrollHeight"]:
            if isinstance(scroll, str):
                driver.execute_script(f"window.scrollTo(0, {scroll});")
            else:
                driver.execute_script(f"window.scrollTo(0, {scroll});")
            time.sleep(1.5)

        # 4. 抓取所有符合該聯盟路徑的連結
        # 邏輯：連結必須包含該聯盟的路徑 (如 /football/england/premier-league/) 且包含 "-" (代表是對戰)
        selector = f"a[href*='{parsed_path}'][href*='-']"
        links = driver.find_elements(By.CSS_SELECTOR, selector)
        
        print(f"  -> 掃描到 {len(links)} 個潛在連結，正在去重與過濾...")

        exclude_keywords = ["/outrights/", "/standings/", "/results/", "bookmaker", "promotion"]

        for link in links:
            try:
                url = link.get_attribute("href")
                text = link.text

                # 過濾無效連結
                if not url or url == league_url: continue
                if any(k in url for k in exclude_keywords): continue
                if url in match_urls: continue

                # 確保是對戰連結 (連結文字通常會有 "-" 或 " v "，或者網址結構正確)
                # 這裡只要網址包含聯盟路徑且不再排除名單內，基本上就是比賽
                match_urls.append(url)
                # print(f"    [+] 加入: {text} -> {url}") # 若需要看詳細內容可取消註解
                
            except:
                pass
        
        print(f"  -> 共獲取 {len(match_urls)} 場比賽連結")

    except Exception as e:
        print(f"  -> 瀏覽器錯誤: {e}")
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass
    
    return match_urls

if __name__ == "__main__":
    import sys
    
    # 從命令行參數獲取聯賽，若無則使用默認值
    if len(sys.argv) >= 3:
        countries = [sys.argv[1]]
        leagues = [sys.argv[2]]
    else:
        countries = ["england"]
        leagues = ["premier-league"]
    
    all_matches = []

    for i in range(len(countries)):
        target_url = f"https://www.oddsportal.com/football/{countries[i]}/{leagues[i]}/"
        urls = get_upcoming_matches(target_url)
        all_matches.extend(urls)
        time.sleep(2) # 每個聯盟之間稍作休息

    print("\n" + "="*30)
    print(f"最終結果: {len(all_matches)} 場")
    print("="*30)
    for u in all_matches:
        print(u)
