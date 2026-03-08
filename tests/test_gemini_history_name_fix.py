#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
只測試：Gemini 返回後是否能正確落到 history name（非 null）
"""

import sys
from pathlib import Path
import importlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def run_test():
    app = importlib.import_module("app")

    # 模擬歷史庫只有 canonical 名稱
    historical_names = [
        "Tottenham Hotspur",
        "Arsenal",
        "Manchester United",
        "Gamba Osaka",
        "V-Varen Nagasaki",
    ]

    original_fetch = app.llm.fetch_data_helper

    class DummyLLM:
        calls = 0

        @staticmethod
        def fetch_data_helper(_prompt: str):
            DummyLLM.calls += 1
            # 1) 測試別名 -> canonical
            if DummyLLM.calls == 1:
                return '{"home": "Tottenham", "away": "Arsenal", "confidence": "high"}'
            # 2) 測試 null -> fallback
            return '{"home": "null", "away": null, "confidence": "high"}'

    try:
        app.llm.fetch_data_helper = DummyLLM.fetch_data_helper

        r1 = app.match_with_gemini("Tottenham", "Arsenal", historical_names, "Premier League")
        print("CASE1", r1)

        ok1 = (
            r1.get("home") == "Tottenham Hotspur"
            and r1.get("away") == "Arsenal"
            and r1.get("confidence") in {"high", "medium", "low"}
            and not app._is_invalid_team_name(r1.get("home"))
            and not app._is_invalid_team_name(r1.get("away"))
        )

        r2 = app.match_with_gemini("Gamba Osaka", "V-Varen Nagasaki", historical_names, "J League")
        print("CASE2", r2)

        ok2 = (
            r2.get("home") == "Gamba Osaka"
            and r2.get("away") == "V-Varen Nagasaki"
            and r2.get("confidence") == "low"
            and not app._is_invalid_team_name(r2.get("home"))
            and not app._is_invalid_team_name(r2.get("away"))
        )

        if ok1 and ok2:
            print("TEST_PASS")
            return 0

        print("TEST_FAIL")
        return 1

    finally:
        app.llm.fetch_data_helper = original_fetch


if __name__ == "__main__":
    raise SystemExit(run_test())
