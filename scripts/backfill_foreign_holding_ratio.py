"""一次性腳本：全市場普通股「外資及陸資持股比率」歷史回補。

不透過 institutional_flow.run()（那個會連同已經回補過的三大法人買賣超T86一起重跑，
浪費時間），改成只呼叫這支新指標自己的收集函式，從設定檔的回補起始日跑到今天。
用法：
    python scripts/backfill_foreign_holding_ratio.py
"""

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.collectors.base import SETTINGS
from src.collectors.institutional_flow import collect_foreign_holding_ratio_daily

if __name__ == "__main__":
    start_date = SETTINGS["backfill_start_date"]
    end_date = datetime.today().strftime("%Y-%m-%d")
    print(f"=== 開始回補外資及陸資持股比率 {start_date} ~ {end_date} ===", flush=True)
    n = collect_foreign_holding_ratio_daily(start_date, end_date)
    print(f"=== 完成，寫入 {n} 筆 ===", flush=True)
