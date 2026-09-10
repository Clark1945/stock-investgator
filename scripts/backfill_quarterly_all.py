"""一次性腳本：全上市公司 EPS + 稅後淨利（不含年增率），僅保留2026年資料。

不納入每日排程，因為 mopsfin 財務比較e點通不支援依日期查詢，全市場規模(~992家)
跑一次要價1小時以上。用法：
    python scripts/backfill_quarterly_all.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.collectors.fundamentals import _all_company_list, collect_quarterly_financials_bulk

if __name__ == "__main__":
    companies = _all_company_list()
    print(f"=== 開始全市場季報回補(EPS+稅後淨利, 僅2026年)，共 {len(companies)} 家 ===", flush=True)
    n = collect_quarterly_financials_bulk(companies, ["eps", "net_income"], year_filter="2026")
    print(f"=== 完成，寫入 {n} 筆 ===", flush=True)
