"""ETF 歷史回補：清單 + 近 3 年日線 + 近 3 年配息。

用法:
    python scripts/backfill_etf.py            # 預設回補 3 年
    python scripts/backfill_etf.py 5          # 回補 5 年
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.collectors import etf
from src.db.schema import init_db

if __name__ == "__main__":
    init_db()
    years = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    end = datetime.today().strftime("%Y-%m-%d")
    start = (datetime.today() - timedelta(days=365 * years + 5)).strftime("%Y-%m-%d")
    etf.run(start, end)
