#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Plan mode simulation runner (non-interactive)

目標：
1) 讀取投注記錄（Betting_Records.xlsx）
2) 用簡單指標檢查系統風險點
3) 輸出報告到 reports/plan_mode_report.md

備註：
- 這是「模擬與審核」工具，不會觸發真實下注。
- 依賴 app.py test 先寫入至少一條記錄。
"""

from __future__ import annotations

import os
from pathlib import Path
from datetime import datetime
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "reports"
REPORT_DIR.mkdir(parents=True, exist_ok=True)

EXCEL_PATH = ROOT / "Betting_Records.xlsx"
REPORT_PATH = REPORT_DIR / "plan_mode_report.md"


def _safe_float(x, default=0.0):
    try:
        return float(x)
    except Exception:
        return default


def build_report() -> str:
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    if not EXCEL_PATH.exists():
        return (
            f"# Plan Mode Report\n\n"
            f"Generated: {now}\n\n"
            f"- Status: NO_DATA\n"
            f"- Reason: Betting_Records.xlsx 不存在，請先跑 `AUTO_MODE=1 python app.py test`。\n"
        )

    df = pd.read_excel(EXCEL_PATH)
    n = len(df)

    if n == 0:
        return (
            f"# Plan Mode Report\n\n"
            f"Generated: {now}\n\n"
            f"- Status: EMPTY_DATA\n"
            f"- Reason: Betting_Records.xlsx 沒有任何記錄。\n"
        )

    # 基礎欄位防呆
    for col in ["EV", "Stake ($)", "Model Prob", "Odds", "Result (Win/Loss)", "Profit"]:
        if col not in df.columns:
            df[col] = None

    ev_values = df["EV"].apply(_safe_float)
    stake_values = df["Stake ($)"].apply(_safe_float)

    avg_ev = ev_values.mean() if len(ev_values) else 0.0
    positive_ev_ratio = (ev_values > 0).mean() if len(ev_values) else 0.0
    zero_stake_ratio = (stake_values <= 0).mean() if len(stake_values) else 0.0

    # 已結算記錄統計
    settled = df[df["Result (Win/Loss)"].notna() & (df["Result (Win/Loss)"].astype(str).str.strip() != "")]
    settled_n = len(settled)

    if settled_n > 0:
        win_n = settled[settled["Result (Win/Loss)"].astype(str).str.upper().str.contains("W")].shape[0]
        win_rate = win_n / settled_n
    else:
        win_rate = None

    # 問題發現（規則）
    findings = []

    if zero_stake_ratio > 0.8:
        findings.append("大部分建議 stake=0，策略偏保守或 edge 門檻過高。")

    if avg_ev < 0:
        findings.append("平均 EV < 0，可能存在市場匹配或概率估計偏差。")

    if positive_ev_ratio < 0.3:
        findings.append("正 EV 比例偏低，建議檢查賠率匹配邏輯與模型置信度。")

    if settled_n == 0:
        findings.append("尚未有已結算注單，暫時無法評估真實勝率與 ROI。")

    if win_rate is not None and win_rate < 0.45:
        findings.append("已結算勝率偏低，需審查選項生成與風險控制參數。")

    if not findings:
        findings.append("暫未發現高風險結構問題；建議繼續累積樣本觀察。")

    # 建議行動
    actions = [
        "保持 AUTO_MODE 執行，避免人工輸入造成流程偏差。",
        "每 20 筆記錄回顧一次 EV 分布與 stake 分布。",
        "有 API key 後，切換到真實賠率來源再做下一輪回測。",
    ]

    lines = [
        "# Plan Mode Report",
        "",
        f"Generated: {now}",
        "",
        "## Summary",
        f"- Total records: {n}",
        f"- Avg EV: {avg_ev:.4f}",
        f"- Positive EV ratio: {positive_ev_ratio:.2%}",
        f"- Zero-stake ratio: {zero_stake_ratio:.2%}",
        f"- Settled bets: {settled_n}",
    ]

    if win_rate is None:
        lines.append("- Win rate (settled): N/A")
    else:
        lines.append(f"- Win rate (settled): {win_rate:.2%}")

    lines.extend([
        "",
        "## Findings",
    ])
    for f in findings:
        lines.append(f"- {f}")

    lines.extend([
        "",
        "## Suggested actions",
    ])
    for a in actions:
        lines.append(f"- {a}")

    lines.append("")
    return "\n".join(lines)


def main():
    report = build_report()
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(f"[OK] report generated: {REPORT_PATH}")


if __name__ == "__main__":
    main()
