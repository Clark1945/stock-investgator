"""個股分析頁面用的日線 K 線資料（開高低收+成交量），涵蓋全部上市公司。

股票代號清單直接取自資料庫裡 fundamentals.collect_monthly_revenue_history 已收集的
全上市公司名單（monthly_revenue_* 指標），不需要另外維護一份清單。yfinance 支援一次
傳入一批股票代號批次下載（threads=True 內建平行處理），比 MOPS 財務比較e點通那種
「一檔一次請求」快很多，因此不像 fundamentals.py 的季報一樣需要限制在觀察清單內。
"""

import time
from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf

from src.collectors.base import SETTINGS, get_logger
from src.db.repo import log_run, query_indicator_codes_like, upsert_stock_ohlc

logger = get_logger("stock_ohlc")

BATCH_SIZE = 50
BATCH_PAUSE_SECONDS = 1.5


def _all_listed_codes() -> list[str]:
    codes = query_indicator_codes_like("monthly_revenue_%")
    result = set()
    for c in codes:
        suffix = c[len("monthly_revenue_"):]
        if suffix.startswith("mom_") or suffix.startswith("yoy_"):
            continue
        result.add(suffix)
    # 保底：確保觀察清單7家一定在內，即使月營收清單當下抓取不到也不遺漏。
    result.update(item["code"] for item in SETTINGS.get("watchlist_electronics", []))
    return sorted(result)


def collect_daily_ohlc(start_date: str, end_date: str) -> int:
    codes = _all_listed_codes()
    if not codes:
        logger.warning("目前資料庫尚無任何個股代號清單（monthly_revenue_*），略過OHLC收集")
        return 0

    end_plus1 = (datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    rows = []
    total_batches = (len(codes) - 1) // BATCH_SIZE + 1

    for i in range(0, len(codes), BATCH_SIZE):
        batch = codes[i : i + BATCH_SIZE]
        tickers = [f"{c}.TW" for c in batch]
        batch_no = i // BATCH_SIZE + 1
        try:
            df = yf.download(
                tickers,
                start=start_date,
                end=end_plus1,
                progress=False,
                auto_adjust=False,
                group_by="ticker",
                threads=True,
            )
        except Exception as e:
            logger.warning(f"OHLC 批次下載失敗 (第{batch_no}/{total_batches}批): {e}")
            continue

        for code in batch:
            ticker = f"{code}.TW"
            if isinstance(df.columns, pd.MultiIndex):
                if ticker not in df.columns.get_level_values(0):
                    continue
                sub = df[ticker]
            else:
                sub = df if len(batch) == 1 else pd.DataFrame()
            if sub.empty or "Close" not in sub.columns:
                continue
            for idx, r in sub.iterrows():
                if pd.isna(r.get("Close")):
                    continue
                rows.append(
                    {
                        "date": idx.strftime("%Y-%m-%d"),
                        "stock_code": code,
                        "open": float(r["Open"]) if not pd.isna(r.get("Open")) else None,
                        "high": float(r["High"]) if not pd.isna(r.get("High")) else None,
                        "low": float(r["Low"]) if not pd.isna(r.get("Low")) else None,
                        "close": float(r["Close"]),
                        "volume": int(r["Volume"]) if not pd.isna(r.get("Volume")) else None,
                    }
                )
        logger.info(f"OHLC 批次 {batch_no}/{total_batches} 完成，累計 {len(rows)} 筆")
        time.sleep(BATCH_PAUSE_SECONDS)

    n = upsert_stock_ohlc(rows)
    logger.info(f"collect_daily_ohlc 寫入 {n} 筆")
    return n


def run(start_date: str, end_date: str) -> None:
    try:
        n = collect_daily_ohlc(start_date, end_date)
        log_run("collect_daily_ohlc", "ok", f"{n} rows")
    except Exception as e:
        logger.exception("collect_daily_ohlc 執行失敗")
        log_run("collect_daily_ohlc", "error", str(e))


if __name__ == "__main__":
    import sys

    start = sys.argv[1] if len(sys.argv) > 1 else datetime.today().strftime("%Y-%m-%d")
    end = sys.argv[2] if len(sys.argv) > 2 else start
    run(start, end)
