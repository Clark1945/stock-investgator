"""全上市公司季損益表金額(營業收入/營業毛利/營業利益，僅保留2025年起資料)。

跟 backfill_margins_all.py 同樣的全市場規模腳本，不納入每日排程(mopsfin不支援依
日期查詢，每家都要單獨請求，全市場一次要價1小時以上)。既是首次回補、也是之後
的「重新整理」腳本——mopsfin每次都回傳全部歷史，重跑一次就會把新公告的季度一併
補進來，可設定成排程定期執行(建議每週一次，季報只有每季公告，不需要天天跑)。
用法：
    python scripts/backfill_income_statement_all.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.collectors.fundamentals import _all_company_list, collect_quarterly_financials_bulk

MIN_DATE = "2025-01-01"

if __name__ == "__main__":
    companies = _all_company_list()
    print(f"=== 開始全市場損益表回補(營業收入/營業毛利/營業利益，{MIN_DATE}起)，共 {len(companies)} 家 ===", flush=True)
    n = collect_quarterly_financials_bulk(companies, ["revenue", "gross_profit", "operating_income"], min_date=MIN_DATE)
    print(f"=== 完成，寫入 {n} 筆 ===", flush=True)
