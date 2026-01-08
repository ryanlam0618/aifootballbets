import os
import time
import subprocess
import shutil

# ================= 設定區 =================

# 1. 網址清單
LINKS = [
    "https://www.oddsportal.com/football/england/premier-league/bournemouth-tottenham-Ovaio0L0/",
    "https://www.oddsportal.com/football/england/premier-league/brentford-sunderland-W42aqvjD/",
    "https://www.oddsportal.com/football/england/premier-league/crystal-palace-aston-villa-r1HIlZRh/",
    "https://www.oddsportal.com/football/england/premier-league/everton-wolves-vTARnDd5/",
    "https://www.oddsportal.com/football/england/premier-league/fulham-chelsea-Ct9ZpiRH/",
    "https://www.oddsportal.com/football/england/premier-league/manchester-city-brighton-882rqVeU/",
    "https://www.oddsportal.com/football/england/premier-league/burnley-manchester-united-AZ3Bject/",
    "https://www.oddsportal.com/football/england/premier-league/newcastle-utd-leeds-d4sh3Ytn/",
    "https://www.oddsportal.com/football/england/premier-league/arsenal-liverpool-SC5rmMjl/",
    "https://www.oddsportal.com/football/england/premier-league/manchester-united-manchester-city-Q5AqCTPG/"
]

# 2. 設定檔案路徑 (請依需求修改使用者名稱)
BASE_PATH = r"c:\Users\Ryan\python\.vscode\fb_ai_bets\data"
BASE_PATH2 = r"c:\Users\Ryan\python\.vscode\fb_ai_bets\OddsHarvester"
FINAL_FILE = os.path.join(BASE_PATH, "odds_1.csv")
TEMP_FILE = os.path.join(BASE_PATH, "temp_scrape.csv")

# 3. 設定 Markets (長字串)
MARKETS = "1x2,btts,double_chance,dnb,over_under_2,over_under_2_25,over_under_2_5,over_under_2_75,over_under_3,over_under_3_25,over_under_3_5,over_under_3_75,over_under_4,asian_handicap_-2_5,asian_handicap_-2_25,asian_handicap_-2,asian_handicap_-1_75,asian_handicap_-1_5,asian_handicap_-1_25,asian_handicap_-1,asian_handicap_-0_75,asian_handicap_-0_5,asian_handicap_-0_25,asian_handicap_0,asian_handicap_+0_25,asian_handicap_+0_5,asian_handicap_+0_75,asian_handicap_+1,asian_handicap_+1_25,asian_handicap_+1_5,asian_handicap_+1_75,asian_handicap_+2"

# ================= 主程式 =================

def ensure_directory(path):
    if not os.path.exists(path):
        os.makedirs(path)

def append_csv(source, destination):
    """
    將 source 的內容追加到 destination。
    如果 destination 已存在，則跳過 source 的第一行 (標題)。
    """
    if not os.path.exists(source):
        return False
    
    # 如果目標檔案不存在，直接移動 (保留標題)
    if not os.path.exists(destination):
        shutil.move(source, destination)
        return True
    
    # 如果目標檔案已存在，讀取 source 並追加 (跳過標題)
    with open(source, 'r', encoding='utf-8') as f_src:
        lines = f_src.readlines()
    
    # 確保有數據 (大於 1 行代表有標題+數據)
    if len(lines) > 1:
        with open(destination, 'a', encoding='utf-8') as f_dest:
            # lines[1:] 代表從第二行開始寫入 (跳過 header)
            f_dest.writelines(lines[1:])
    
    # 刪除暫存檔
    os.remove(source)
    return True

def main():
    ensure_directory(BASE_PATH)
    print(f"[*] 最終存檔位置: {FINAL_FILE}")

    for index, link in enumerate(LINKS):
        print("-" * 60)
        print(f"正在執行第 ({index + 1}/{len(LINKS)}) 筆任務...")
        print(f"目標網址: {link}")

        # 1. 清理舊的暫存檔
        if os.path.exists(TEMP_FILE):
            os.remove(TEMP_FILE)

        # 2. 組合指令 (使用 subprocess list 格式，避免空格問題)
        # 注意：移除了 --headless
        cmd = [ "cd", BASE_PATH2 ]
        
        cmd2 = [
            "python", "-m", "uv", "run", "python", "src/main.py", "scrape_upcoming",
            "--sport", "football",
            "--match_links", link,
            "--format", "csv",
            "--markets", MARKETS,
            "--scrape_odds_history",
            "--file_path", TEMP_FILE,
            "--concurrency_tasks", "5"
        ]

        try:
            # 執行爬蟲
            subprocess.run(cmd)
            subprocess.run(cmd2, check=True)

            # 3. 處理檔案合併 (Append)
            if os.path.exists(TEMP_FILE):
                append_csv(TEMP_FILE, FINAL_FILE)
                print(f"[OK] 數據已追加至: {FINAL_FILE}")
            else:
                print("[Error] 抓取失敗，未生成暫存檔。")

        except subprocess.CalledProcessError as e:
            print(f"[Error] 執行過程發生錯誤: {e}")
        except Exception as e:
            print(f"[Error] 未知錯誤: {e}")

        # 4. 休息機制
        print("休息 10 秒以防封鎖...")
        time.sleep(10)

    print("-" * 60)
    print("所有任務完成！")

if __name__ == "__main__":
    main()