"""CLI 輔助函式（從 app.py 抽離第一步，不改核心策略邏輯）"""

import re
from typing import Dict, Tuple


def parse_match_input(match_input: str) -> Tuple[str, str]:
    """解析 'Home vs Away' / 'Home v Away' 輸入。"""
    if re.search(r"\s+vs\.?\s+", match_input, re.IGNORECASE) or " v " in match_input:
        parts = re.split(r"\s+vs\.?\s+|\s+v\s+", match_input, flags=re.IGNORECASE)
        if len(parts) >= 2:
            return parts[0].strip(), parts[1].strip()
    raise ValueError("match format invalid")


def choose_league(league_idx: str, league_options: Dict[str, Dict[str, str]]) -> Tuple[str, Dict[str, str]]:
    """選擇聯賽，輸入無效時 fallback 到 key='1'。"""
    if league_idx not in league_options:
        print("⚠️ 輸入無效，預設使用 Premier League")
        league_idx = "1"
    return league_idx, league_options[league_idx]
