"""台股 ETF 資料：清單、日線(開高低收量)、配息(除息日/每單位配息)。

- 清單：TWSE 全市場日成交 STOCK_DAY_ALL 中代號以「00」開頭者(個股沒有 00 開頭)，含債券/槓桿/主動式等全部 ETF。
- 股價：與個股相同走 yfinance 批次下載，寫進 stock_ohlc(代號不與個股重疊，個股頁面的篩選以 company_profile 為準，不受影響)。
- 配息：TWSE 除權除息結果表 TWT49U(一次可查多年)為「已除息」資料；TWT48U_ALL 為「預告」資料。
"""

import time
from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf

from src.collectors.base import get_logger, http_get
from src.db.repo import (
    log_run,
    query_etf_profiles,
    upsert_etf_dividends,
    upsert_etf_profile,
    upsert_stock_ohlc,
)

logger = get_logger("etf")

URL_DAY_ALL = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
URL_EX_RESULT = "https://www.twse.com.tw/rwd/zh/exRight/TWT49U"
URL_EX_NOTICE = "https://openapi.twse.com.tw/v1/exchangeReport/TWT48U_ALL"
HEADERS = {"User-Agent": "Mozilla/5.0"}
BATCH_SIZE = 50
BATCH_PAUSE_SECONDS = 1.5


def _is_etf(code: str) -> bool:
    return code.startswith("00")


def _roc_to_iso(s: str) -> str | None:
    """'115年10月15日' 或 '1151015' → '2026-10-15'。"""
    s = str(s).strip()
    try:
        if "年" in s:
            y, rest = s.split("年")
            m, d = rest.replace("日", "").split("月")
        else:
            y, m, d = s[:-4], s[-4:-2], s[-2:]
        return f"{int(y) + 1911:04d}-{int(m):02d}-{int(d):02d}"
    except Exception:
        return None


def _num(v) -> float | None:
    try:
        return float(str(v).replace(",", "").strip())
    except Exception:
        return None


def collect_etf_profile(_start: str = "", _end: str = "") -> int:
    resp = http_get(URL_DAY_ALL, logger=logger, headers=HEADERS)
    if resp is None:
        return 0
    rows = [
        {"etf_code": x["Code"].strip(), "name": x.get("Name", "").strip()}
        for x in resp.json()
        if _is_etf(x.get("Code", ""))
    ]
    n = upsert_etf_profile(rows)
    logger.info(f"collect_etf_profile 寫入 {n} 筆")
    return n


def collect_etf_ohlc(start_date: str, end_date: str) -> int:
    codes = [r["etf_code"] for r in query_etf_profiles()]
    if not codes:
        logger.warning("尚無 ETF 清單，略過 ETF 股價收集")
        return 0
    end_plus1 = (datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    total_batches = (len(codes) - 1) // BATCH_SIZE + 1
    total = 0
    for i in range(0, len(codes), BATCH_SIZE):
        batch = codes[i : i + BATCH_SIZE]
        batch_no = i // BATCH_SIZE + 1
        try:
            df = yf.download([f"{c}.TW" for c in batch], start=start_date, end=end_plus1, progress=False,
                             auto_adjust=False, group_by="ticker", threads=True)
        except Exception as e:
            logger.warning(f"ETF 股價批次下載失敗 (第{batch_no}/{total_batches}批): {e}")
            continue
        rows = []
        for code in batch:
            ticker = f"{code}.TW"
            if not isinstance(df.columns, pd.MultiIndex) or ticker not in df.columns.get_level_values(0):
                continue
            sub = df[ticker]
            if sub.empty or "Close" not in sub.columns:
                continue
            for idx, r in sub.iterrows():
                if pd.isna(r.get("Close")):
                    continue
                rows.append({
                    "date": idx.strftime("%Y-%m-%d"), "stock_code": code,
                    "open": None if pd.isna(r.get("Open")) else float(r["Open"]),
                    "high": None if pd.isna(r.get("High")) else float(r["High"]),
                    "low": None if pd.isna(r.get("Low")) else float(r["Low"]),
                    "close": float(r["Close"]),
                    "volume": None if pd.isna(r.get("Volume")) else int(r["Volume"]),
                })
        total += upsert_stock_ohlc(rows)
        logger.info(f"ETF 股價批次 {batch_no}/{total_batches} 完成，累計 {total} 筆")
        time.sleep(BATCH_PAUSE_SECONDS)
    logger.info(f"collect_etf_ohlc 寫入 {total} 筆")
    return total


def collect_etf_dividends(start_date: str, end_date: str) -> int:
    """已除息資料(TWT49U，可一次查多年) + 尚未除息的預告(TWT48U_ALL)。"""
    rows = []
    resp = http_get(URL_EX_RESULT, logger=logger, headers=HEADERS,
                    params={"startDate": start_date.replace("-", ""), "endDate": end_date.replace("-", ""), "response": "json"})
    if resp is not None:
        for x in resp.json().get("data") or []:
            code = str(x[1]).strip()
            if not _is_etf(code) or str(x[6]).strip() != "息":
                continue
            d = _roc_to_iso(x[0])
            amt = _num(x[5])
            if d and amt is not None:
                rows.append({"etf_code": code, "ex_date": d, "cash_dividend": amt, "prev_close": _num(x[3]),
                             "ref_price": _num(x[4]), "status": "actual"})
    resp = http_get(URL_EX_NOTICE, logger=logger, headers=HEADERS)
    if resp is not None:
        for x in resp.json():
            code = str(x.get("Code", "")).strip()
            d, amt = _roc_to_iso(x.get("Date", "")), _num(x.get("CashDividend"))
            if _is_etf(code) and d and amt is not None and x.get("Exdividend") == "息":
                rows.append({"etf_code": code, "ex_date": d, "cash_dividend": amt, "prev_close": None,
                             "ref_price": None, "status": "announced"})
    n = upsert_etf_dividends(rows)
    logger.info(f"collect_etf_dividends 寫入 {n} 筆")
    return n


def run(start_date: str, end_date: str) -> None:
    for name, fn in (("collect_etf_profile", collect_etf_profile), ("collect_etf_ohlc", collect_etf_ohlc),
                     ("collect_etf_dividends", collect_etf_dividends)):
        try:
            n = fn(start_date, end_date)
            log_run(name, "ok", f"{n} rows")
        except Exception as e:
            logger.exception(f"{name} 執行失敗")
            log_run(name, "error", str(e))


if __name__ == "__main__":
    import sys

    start = sys.argv[1] if len(sys.argv) > 1 else datetime.today().strftime("%Y-%m-%d")
    end = sys.argv[2] if len(sys.argv) > 2 else start
    run(start, end)
