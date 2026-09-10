"""歷史回補：從 config/settings.yaml 的 backfill_start_date 到今天，跑一次全部 collector。

用法:
    python -m src.backfill
    python -m src.backfill 2026-01-01 2026-06-30   # 也可自訂區間
"""

import sys
from datetime import datetime

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
from src.collectors.base import SETTINGS, get_logger
from src.db.schema import init_db

logger = get_logger("backfill")

COLLECTORS = [
    fx_rates_macro,
    relative_valuation,
    fundamentals,
    passive_flows,
    chip_positioning,
    stock_ohlc,
    company_profile,
    announcements,
    institutional_flow,  # 依賴 fundamentals 已寫入的 monthly_revenue_* 清單來過濾普通股，需排在其後
]


def main() -> None:
    init_db()
    start_date = sys.argv[1] if len(sys.argv) > 1 else SETTINGS["backfill_start_date"]
    end_date = sys.argv[2] if len(sys.argv) > 2 else datetime.today().strftime("%Y-%m-%d")

    logger.info(f"===== 開始歷史回補: {start_date} ~ {end_date} =====")
    for module in COLLECTORS:
        name = module.__name__
        logger.info(f"--- 執行 {name} ---")
        try:
            module.run(start_date, end_date)
        except Exception:
            logger.exception(f"{name} 整體執行發生未預期例外，跳過")
    logger.info("===== 歷史回補結束，詳見 logs/ 內各 collector 的成功/失敗紀錄 =====")


if __name__ == "__main__":
    main()
