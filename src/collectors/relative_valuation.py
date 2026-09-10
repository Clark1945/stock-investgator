"""二、相對評價層：台股 P/E,P/B、台積電ADR溢價、SOX/KOSPI/三星/海力士/Nasdaq/NVDA、美韓股P/E快照。"""

from datetime import date, datetime, timedelta

import pandas as pd
import yfinance as yf

from src.collectors.base import SETTINGS, get_logger, http_get, trading_date_range
from src.db.repo import log_run, upsert_timeseries

logger = get_logger("relative_valuation")

CATEGORY = "relative_valuation"


def _yf_history(ticker: str, start_date: str, end_date: str) -> pd.DataFrame:
    end_plus1 = (datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    try:
        df = yf.download(ticker, start=start_date, end=end_plus1, progress=False, auto_adjust=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df
    except Exception as e:
        logger.warning(f"yfinance 下載失敗 {ticker}: {e}")
        return pd.DataFrame()


def collect_index_benchmarks(start_date: str, end_date: str) -> int:
    """SOX、KOSPI、三星、SK海力士、Nasdaq、NVDA 收盤價序列。"""
    tickers = SETTINGS["yfinance_tickers"]
    mapping = {
        "sox_index": ("費城半導體指數 SOX", tickers["sox"]),
        "kospi_index": ("韓國 KOSPI", tickers["kospi"]),
        "samsung_price": ("三星電子股價", tickers["samsung"]),
        "sk_hynix_price": ("SK海力士股價", tickers["sk_hynix"]),
        "nasdaq_index": ("那斯達克指數", tickers["nasdaq"]),
        "nvda_price": ("輝達(NVDA)股價", tickers["nvda"]),
    }
    rows = []
    for code, (label, ticker) in mapping.items():
        df = _yf_history(ticker, start_date, end_date)
        if df.empty or "Close" not in df.columns:
            logger.warning(f"{code} ({ticker}) 無資料")
            continue
        for idx, val in df["Close"].items():
            if pd.isna(val):
                continue
            rows.append(
                {
                    "date": idx.strftime("%Y-%m-%d"),
                    "indicator_code": code,
                    "category": CATEGORY,
                    "label": label,
                    "value": float(val),
                    "unit": None,
                    "is_proxy": False,
                    "source": f"yfinance:{ticker}",
                }
            )
    n = upsert_timeseries(rows)
    logger.info(f"collect_index_benchmarks 寫入 {n} 筆")
    return n


def collect_tsm_adr_premium(start_date: str, end_date: str) -> int:
    """台積電 ADR 溢價%：1 ADR = ratio(5) 股普通股，故 ADR 合理美元價值 = ratio * (2330_TWD / FX)。
    溢價% = (TSM_USD * FX / (ratio * 2330_TWD) - 1) * 100。
    """
    tickers = SETTINGS["yfinance_tickers"]
    ratio = SETTINGS.get("tsm_adr_ratio", 5)

    tsm = _yf_history(tickers["tsm_adr"], start_date, end_date)
    tsmc_tw = _yf_history(tickers["tsmc_tw"], start_date, end_date)
    fx = _yf_history(tickers["usdtwd"], start_date, end_date)

    if tsm.empty or tsmc_tw.empty or fx.empty:
        logger.warning("台積電ADR溢價計算缺資料，略過")
        return 0

    tsm_close = tsm["Close"].rename("tsm")
    tsmc_close = tsmc_tw["Close"].rename("tsmc_tw")
    fx_close = fx["Close"].rename("fx")

    merged = pd.concat([tsm_close, tsmc_close, fx_close], axis=1).dropna()

    rows = []
    for idx, r in merged.iterrows():
        try:
            premium_pct = (r["tsm"] * r["fx"] / (ratio * r["tsmc_tw"]) - 1) * 100
        except ZeroDivisionError:
            continue
        rows.append(
            {
                "date": idx.strftime("%Y-%m-%d"),
                "indicator_code": "tsm_adr_premium_pct",
                "category": CATEGORY,
                "label": "台積電ADR相對原股溢價率",
                "value": float(premium_pct),
                "unit": "%",
                "is_proxy": False,
                "source": "計算: TSM,2330.TW,TWD=X",
            }
        )
    n = upsert_timeseries(rows)
    logger.info(f"collect_tsm_adr_premium 寫入 {n} 筆")
    return n


def collect_taiwan_pe_pb(start_date: str, end_date: str) -> int:
    """台股本益比/股價淨值比：對 TWSE BWIBBU_d(依日期查詢，全市場個股) 做簡單平均，作為大盤估值走勢近似。"""
    url_tmpl = SETTINGS["twse"]["pe_pb_yield"]
    rows = []
    for d in trading_date_range(start_date, end_date):
        date_str = d.strftime("%Y%m%d")
        url = url_tmpl.format(date=date_str)
        resp = http_get(url, logger=logger)
        if resp is None:
            continue
        try:
            df = pd.read_csv(pd.io.common.StringIO(resp.text), skiprows=1, encoding="utf-8-sig")
        except Exception as e:
            logger.warning(f"台股PE/PB解析失敗 {date_str}: {e}")
            continue
        pe_col = next((c for c in df.columns if "本益比" in str(c)), None)
        pb_col = next((c for c in df.columns if "股價淨值比" in str(c)), None)
        if pe_col is None or pb_col is None:
            continue
        pe_vals = pd.to_numeric(df[pe_col].astype(str).str.replace(",", ""), errors="coerce").dropna()
        pb_vals = pd.to_numeric(df[pb_col].astype(str).str.replace(",", ""), errors="coerce").dropna()
        pe_vals = pe_vals[pe_vals > 0]
        pb_vals = pb_vals[pb_vals > 0]
        date_iso = d.strftime("%Y-%m-%d")
        if len(pe_vals):
            rows.append(
                {
                    "date": date_iso,
                    "indicator_code": "tw_market_pe_avg",
                    "category": CATEGORY,
                    "label": "台股全市場平均本益比(簡單平均)",
                    "value": float(pe_vals.mean()),
                    "unit": "倍",
                    "is_proxy": True,
                    "source": "TWSE BWIBBU_d",
                }
            )
        if len(pb_vals):
            rows.append(
                {
                    "date": date_iso,
                    "indicator_code": "tw_market_pb_avg",
                    "category": CATEGORY,
                    "label": "台股全市場平均股價淨值比(簡單平均)",
                    "value": float(pb_vals.mean()),
                    "unit": "倍",
                    "is_proxy": True,
                    "source": "TWSE BWIBBU_d",
                }
            )
    n = upsert_timeseries(rows)
    logger.info(f"collect_taiwan_pe_pb 寫入 {n} 筆")
    return n


def collect_us_kr_pe_snapshot(_start_date: str, _end_date: str) -> int:
    """美股/韓股 P/E 快照：yfinance 只提供即時 trailingPE，無歷史，故每次執行僅寫入「今天」一筆。"""
    tickers = SETTINGS["yfinance_tickers"]
    today = date.today().strftime("%Y-%m-%d")
    mapping = {
        "us_market_pe_snapshot": ("美股大盤本益比快照(SPY)", tickers["spy_etf"]),
        "kr_market_pe_snapshot": ("韓股大盤本益比快照(EWY)", tickers["ewy_etf"]),
    }
    rows = []
    for code, (label, ticker) in mapping.items():
        try:
            info = yf.Ticker(ticker).info
            pe = info.get("trailingPE")
        except Exception as e:
            logger.warning(f"{code} ({ticker}) 快照取得失敗: {e}")
            continue
        if pe is None:
            continue
        rows.append(
            {
                "date": today,
                "indicator_code": code,
                "category": CATEGORY,
                "label": label,
                "value": float(pe),
                "unit": "倍",
                "is_proxy": True,
                "source": f"yfinance.info:{ticker}",
            }
        )
    n = upsert_timeseries(rows)
    logger.info(f"collect_us_kr_pe_snapshot 寫入 {n} 筆")
    return n


def run(start_date: str, end_date: str) -> None:
    for fn in (
        collect_index_benchmarks,
        collect_tsm_adr_premium,
        collect_taiwan_pe_pb,
        collect_us_kr_pe_snapshot,
    ):
        try:
            n = fn(start_date, end_date)
            log_run(fn.__name__, "ok", f"{n} rows")
        except Exception as e:
            logger.exception(f"{fn.__name__} 執行失敗")
            log_run(fn.__name__, "error", str(e))


if __name__ == "__main__":
    import sys

    start = sys.argv[1] if len(sys.argv) > 1 else datetime.today().strftime("%Y-%m-%d")
    end = sys.argv[2] if len(sys.argv) > 2 else start
    run(start, end)
