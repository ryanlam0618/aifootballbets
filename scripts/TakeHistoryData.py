import io
import sys
from typing import List
import requests
import pandas as pd

# 設定五大聯賽代碼與基礎 URL
# E0=英超, SP1=西甲, D1=德甲, I1=義甲, F1=法甲
BASE_URL = "https://www.football-data.co.uk/mmz4281/{season_code}/{league}.csv"
LEAGUES = ["E0", "SP1", "D1", "I1", "F1"]

# 設定抓取的賽季範圍 (例如 2020 代表 2020-2021 賽季)
START_YEARS = list(range(2020, 2025)) 

def season_label(start_year: int) -> str:
    """產生賽季標籤，例如 '2020-2021'"""
    return f"{start_year}-{start_year+1}"

def season_code(start_year: int) -> str:
    """轉換為網站需要的代碼，例如 2020 -> '2021'"""
    return f"{start_year % 100:02d}{(start_year + 1) % 100:02d}"

def fetch_csv_as_df(url: str) -> pd.DataFrame:
    """從 URL 下載並讀取 CSV"""
    try:
        r = requests.get(url, timeout=30)
        if r.status_code == 404:
            print(f"[WARN] 404 Not Found: {url}")
            return pd.DataFrame()
        r.raise_for_status()
        # football-data 網站通常使用 Latin-1 編碼
        content = r.content
        df = pd.read_csv(io.BytesIO(content), encoding="latin1")
        return df
    except Exception as e:
        print(f"[ERROR] Failed to fetch: {url} -> {e}", file=sys.stderr)
        return pd.DataFrame()

def ingest_league_seasons(leagues: List[str], start_years: List[int]) -> pd.DataFrame:
    frames = []
    for y in start_years:
        s_code = season_code(y)
        s_label = season_label(y)
        for lg in leagues:
            url = BASE_URL.format(season_code=s_code, league=lg)
            print(f"[INFO] Fetching {lg} {s_label} ...")
            df = fetch_csv_as_df(url)
            
            if df.empty:
                continue
            
            # 加上賽季標籤 (Season) 方便區分，但保留原始所有欄位
            df["Season"] = s_label
            frames.append(df)
            
    if not frames:
        raise RuntimeError("No data loaded. Check connectivity.")
    
    # 合併所有數據
    return pd.concat(frames, ignore_index=True, sort=False)

def clean_transform(df: pd.DataFrame) -> pd.DataFrame:
    """清理數據：處理日期格式、移除無效行"""
    if "Date" in df.columns:
        # 統一日期格式
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce", dayfirst=True)
        # 移除日期無效的行
        df = df.dropna(subset=["Date"])
    
    # 移除沒有比分數據的行 (代表比賽未進行或無效)
    if "FTHG" in df.columns and "FTAG" in df.columns:
        df = df.dropna(subset=["FTHG", "FTAG"])

    # 自動轉換常見數值欄位 (這部分會嘗試將物件轉為數字，失敗則變 NaN)
    # 這裡只列出核心數據，其他賠率欄位 Pandas 讀取時通常會自動識別為 float
    target_cols = ["FTHG", "FTAG", "HST", "AST", "HC", "AC"]
    for c in target_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
            
    return df

if __name__ == "__main__":
    # 1. 下載數據
    print("開始下載五大聯賽數據...")
    raw_df = ingest_league_seasons(LEAGUES, START_YEARS)
    print(f"[INFO] 原始數據筆數: {len(raw_df)}")

    # 2. 清理數據
    cleaned_df = clean_transform(raw_df)
    
    # 3. 不進行欄位篩選，直接輸出，以保留像 'B365H' 等所有賠率欄位
    output_path = "big_five_v2_history.csv"
    cleaned_df.to_csv(output_path, index=False, encoding="utf-8")
    
    print(f"[INFO] 成功！已儲存 {cleaned_df.shape[0]} 筆數據至 {output_path}")
    print(f"[INFO] 欄位總數: {cleaned_df.shape[1]} (包含賠率與詳細數據)")