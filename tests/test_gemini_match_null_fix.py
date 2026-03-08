#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
只測試 Gemini 名稱匹配 null 修復

測試目標：
1) 當 LLM 返回 null/None/空字串時，match_with_gemini 必須 fallback 到原始輸入
2) confidence 需歸一化（非法值 -> low）
3) 不能把 "null" 當成有效球隊名傳下游
"""

import importlib
import os
import sys
from pathlib import Path

# 把專案根目錄加入 import 路徑
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def run_test():
    app = importlib.import_module("app")

    historical_names = [
        "Gamba Osaka",
        "V-Varen Nagasaki",
        "Tottenham Hotspur",
        "Manchester United",
    ]

    # 保存原始 helper
    original_fetch = app.llm.fetch_data_helper

    class DummyLLM:
        @staticmethod
        def fetch_data_helper(_prompt: str):
            # 模擬有問題的 Gemini 回覆
            return '{"home": "null", "away": null, "confidence": "weird"}'

    try:
        # monkeypatch
        app.llm.fetch_data_helper = DummyLLM.fetch_data_helper

        result = app.match_with_gemini(
            "Gamba Osaka",
            "V-Varen Nagasaki",
            historical_names,
            league_context="J League (Japan)",
        )

        ok_home = result.get("home") == "Gamba Osaka"
        ok_away = result.get("away") == "V-Varen Nagasaki"
        ok_conf = result.get("confidence") == "low"

        print("RESULT:", result)
        print("CHECK home fallback:", ok_home)
        print("CHECK away fallback:", ok_away)
        print("CHECK confidence normalize:", ok_conf)

        if ok_home and ok_away and ok_conf:
            print("TEST_PASS")
            return 0
        else:
            print("TEST_FAIL")
            return 1

    finally:
        # 還原
        app.llm.fetch_data_helper = original_fetch


if __name__ == "__main__":
    raise SystemExit(run_test())
