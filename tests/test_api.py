#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API 連線測試（非互動版，適合 CI）
"""

import os
import sys
from openai import OpenAI

# 將專案根目錄添加到 sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings


def _mask_key(key: str) -> str:
    if not key:
        return "(empty)"
    if len(key) <= 8:
        return "****"
    return f"{key[:4]}****{key[-4:]}"


def test_api_connectivity() -> bool:
    print("========================================")
    print("🔗 API 連線診斷工具（CI-safe）")
    print("========================================")
    print(f"測試 Base URL: {settings.API_BASE_URL}")
    print(f"測試 API Key: {_mask_key(settings.GEMINI_API_KEY)}")
    print(f"測試 Gemini 模型: {settings.MODEL_GEMINI}")
    print("-" * 40)

    if not settings.GEMINI_API_KEY:
        print("⚠️ 跳過：GEMINI_API_KEY 未配置")
        return True

    client = OpenAI(
        base_url=settings.API_BASE_URL,
        api_key=settings.GEMINI_API_KEY,
        timeout=30,
    )

    try:
        print("🚀 發送測試請求中...", flush=True)
        response = client.chat.completions.create(
            model=settings.MODEL_GEMINI,
            messages=[{"role": "user", "content": "Hi, return the word 'Success'."}],
            max_tokens=10,
        )

        content = response.choices[0].message.content if response and response.choices else ""
        print("\n✅ 連線成功！")
        print("回傳內容:", content)
        return True

    except Exception as e:
        print("\n❌ 連線失敗！")
        print(f"錯誤訊息: {e}")
        print("\n💡 建議：")
        print("1. 檢查 .env 中 API_BASE_URL 是否正確。")
        print("2. 確認 API key、模型名稱與供應商一致。")
        return False


if __name__ == "__main__":
    ok = test_api_connectivity()
    raise SystemExit(0 if ok else 1)
