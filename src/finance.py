import pandas as pd
import os
from datetime import datetime
from pathlib import Path
from config import settings

def calculate_kelly_stake(prob: float, odds: float, bankroll: float) -> dict:
    if prob <= 0 or odds <= 1:
        return {"stake": 0, "pct": 0, "ev": 0}

    b = odds - 1
    q = 1 - prob
    f = (b * prob - q) / b
    f_adj = f * settings.KELLY_FRACTION
    ev = (prob * b) - (1 - prob)

    if f_adj <= 0 or ev < settings.MIN_EDGE:
        return {"stake": 0, "pct": 0, "ev": ev}

    stake = bankroll * f_adj
    return {"stake": stake, "pct": f_adj, "ev": ev}

class ExcelLogger:
    def __init__(self):
        self.filepath = settings.EXCEL_FILEPATH
        self.csv_filepath = self._derive_csv_path(self.filepath)
        self.columns = [
            "Date", "League", "Home", "Away", "Market", "Selection",
            "Odds", "Model Prob", "EV", "Kelly %", "Stake ($)",
            "Result (Win/Loss)", "Profit"
        ]
        self._init_file()

    @staticmethod
    def _derive_csv_path(xlsx_path: str) -> str:
        p = Path(xlsx_path)
        return str(p.with_suffix('.csv'))

    def _init_file(self):
        # 嘗試建立目錄與檔案
        if not os.path.exists(self.filepath):
            try:
                directory = os.path.dirname(self.filepath)
                if directory and not os.path.exists(directory):
                    os.makedirs(directory)

                df = pd.DataFrame(columns=self.columns)
                df.to_excel(self.filepath, index=False)
                self._sync_csv(df)
                print(f"[INFO] 已建立新記錄檔: {self.filepath}")
            except Exception as e:
                print(f"ERROR: 建立檔案失敗: {e}")
        else:
            print(f"[INFO] 讀取現有記錄檔: {self.filepath}")

    def log_bet(self, match_info, bet_info, stake_info):
        new_row = {
            "Date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "League": match_info.get("league"),
            "Home": match_info.get("home"),
            "Away": match_info.get("away"),
            "Market": bet_info.get("market"),
            "Selection": bet_info.get("selection"),
            "Odds": bet_info.get("odds"),
            "Model Prob": round(bet_info.get("model_probability"), 3),
            "EV": round(stake_info["ev"], 3),
            "Kelly %": f"{stake_info['pct']*100:.2f}%",
            "Stake ($)": round(stake_info["stake"], 2),
            "Result (Win/Loss)": "",
            "Profit": ""
        }

        try:
            # 使用更可靠的方式：讀取現有資料 → 附加新資料 → 寫回
            if os.path.exists(self.filepath):
                # 讀取現有資料
                df_existing = pd.read_excel(self.filepath)
                # 附加新資料
                df_combined = pd.concat([df_existing, pd.DataFrame([new_row])], ignore_index=True)
                # 寫回檔案
                df_combined.to_excel(self.filepath, index=False)
            else:
                # 如果檔案不存在，直接寫入
                df_new = pd.DataFrame([new_row])
                df_new.to_excel(self.filepath, index=False)

            self._sync_csv(df_combined if 'df_combined' in locals() else pd.DataFrame([new_row]))
            print(f"[INFO] 記錄已成功儲存至 Excel: {self.filepath}")

        except PermissionError:
            print("ERROR: 寫入失敗: 請先關閉 Excel 檔案後再試！")
        except Exception as e:
            print(f"ERROR: 寫入失敗: {e}")
            import traceback
            traceback.print_exc()

    def _sync_csv(self, df: pd.DataFrame):
        """每次寫入 Excel 後，同步輸出 CSV。"""
        try:
            df.to_csv(self.csv_filepath, index=False, encoding='utf-8-sig')
            print(f"[INFO] CSV 已同步輸出: {self.csv_filepath}")
        except Exception as e:
            print(f"[WARN] CSV 同步失敗: {e}")

    def show_stats(self):
        if not os.path.exists(self.filepath):
            return
        try:
            df = pd.read_excel(self.filepath)
            # 確保欄位存在再過濾
            if "Result (Win/Loss)" in df.columns:
                settled = df[df["Result (Win/Loss)"].notna() & (df["Result (Win/Loss)"] != "")]
                if not settled.empty:
                    wins = settled[settled["Result (Win/Loss)"].astype(str).str.upper().str.contains("W")]
                    win_rate = len(wins) / len(settled)
                    print(f"[INFO] 目前勝率: {win_rate*100:.1f}% ({len(wins)}/{len(settled)})")
        except Exception:
            pass
