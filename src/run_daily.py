"""每日排程入口：由 Windows 工作排程器定時呼叫。

會重跑「最近 N 天」而非只有今天，用意是：
1. 若前幾天因機器關機/網路問題漏跑，這次會自動補上。
2. TWSE/TAIFEX 部分資料偶有延遲或事後修正，重跑近期資料可覆蓋掉舊值(upsert)。

用法:
    python -m src.run_daily            # 預設回看 5 天
    python -m src.run_daily 10         # 回看 10 天
"""

import sys
from datetime import datetime, timedelta

from src.collectors import (
    announcements,
    chip_positioning,
    company_profile,
    fundamentals,
    fx_rates_macro,
    institutional_flow,
    passive_flows,
    relative_valuation,
    stock_ohlc,
)
from src.collectors.base import get_logger
from src.db.schema import init_db

logger = get_logger("run_daily")

COLLECTORS = [
    fx_rates_macro,
    relative_valuation,
    fundamentals,
    passive_flows,
    chip_positioning,
    stock_ohlc,
    company_profile,
    announcements,
    institutional_flow,
]

DEFAULT_LOOKBACK_DAYS = 5


def main() -> None:
    init_db()
    lookback = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_LOOKBACK_DAYS
    end_date = datetime.today().strftime("%Y-%m-%d")
    start_date = (datetime.today() - timedelta(days=lookback)).strftime("%Y-%m-%d")

    logger.info(f"===== 每日更新開始: {start_date} ~ {end_date} =====")
    for module in COLLECTORS:
        name = module.__name__
        try:
            module.run(start_date, end_date)
        except Exception:
            logger.exception(f"{name} 整體執行發生未預期例外，跳過")
    logger.info("===== 每日更新結束 =====")


if __name__ == "__main__":
    main()
