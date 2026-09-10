"""一、總經/匯率層：匯率、DXY、VIX、美債殖利率、Fed利率、外資買賣超(近似)、MSCI EM/Asia代理。"""

from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf

from src.collectors.base import SETTINGS, get_fred_api_key, get_logger, http_get, trading_date_range
from src.db.repo import log_run, upsert_timeseries

logger = get_logger("fx_rates_macro")

CATEGORY = "macro_fx"


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


def collect_yfinance_indicators(start_date: str, end_date: str) -> int:
    """匯率/DXY/VIX/MSCI 代理指標，皆來自 yfinance 歷史資料。"""
    tickers = SETTINGS["yfinance_tickers"]
    mapping = {
        "usdtwd": ("台幣兌美元匯率", tickers["usdtwd"], False),
        "usdjpy": ("美元兌日圓匯率", tickers["usdjpy"], False),
        "usdcny": ("美元兌人民幣匯率", tickers["usdcny"], False),
        "dxy": ("美元指數 DXY", tickers["dxy"], False),
        "vix": ("VIX 恐慌指數", tickers["vix"], False),
        "msci_em_proxy": ("MSCI新興市場指數代理(EEM)", tickers["eem_etf"], True),
        "msci_asia_exjp_proxy": ("MSCI亞洲不含日代理(AAXJ)", tickers["aaxj_etf"], True),
        "ewt_volume_proxy": ("外資資金流向代理(EWT成交量)", tickers["ewt_etf"], True),
        "aaxj_volume_proxy": ("外資資金流向代理(AAXJ成交量)", tickers["aaxj_etf"], True),
    }
    rows = []
    for code, (label, ticker, is_proxy) in mapping.items():
        df = _yf_history(ticker, start_date, end_date)
        if df.empty:
            logger.warning(f"{code} ({ticker}) 無資料")
            continue
        use_volume = code.endswith("_volume_proxy")
        col = "Volume" if use_volume else "Close"
        if col not in df.columns:
            continue
        for idx, val in df[col].items():
            if pd.isna(val):
                continue
            rows.append(
                {
                    "date": idx.strftime("%Y-%m-%d"),
                    "indicator_code": code,
                    "category": CATEGORY,
                    "label": label,
                    "value": float(val),
                    "unit": "股數" if use_volume else None,
                    "is_proxy": is_proxy,
                    "source": f"yfinance:{ticker}",
                }
            )
    n = upsert_timeseries(rows)
    logger.info(f"collect_yfinance_indicators 寫入 {n} 筆")
    return n


def _fred_series(series_id: str, start_date: str, end_date: str) -> pd.DataFrame:
    api_key = get_fred_api_key()
    if not api_key:
        logger.warning("未設定 FRED_API_KEY，略過 FRED 指標")
        return pd.DataFrame()
    url = "https://api.stlouisfed.org/fred/series/observations"
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "observation_start": start_date,
        "observation_end": end_date,
    }
    # api_key 透過 params 傳遞而非拼進 url 字串，避免請求失敗時把金鑰明文寫進 log 檔。
    resp = http_get(url, logger=logger, params=params)
    if resp is None:
        return pd.DataFrame()
    data = resp.json().get("observations", [])
    df = pd.DataFrame(data)
    if df.empty:
        return df
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df[["date", "value"]].dropna()


def collect_fred_indicators(start_date: str, end_date: str) -> int:
    """美債殖利率、Fed利率目標區間、ISM PMI。需要 FRED_API_KEY，缺 key 則略過並記錄。"""
    fred_cfg = SETTINGS["fred_series"]
    label_map = {
        "us_10y_yield": ("美債10年期殖利率", "%"),
        "us_2y_yield": ("美債2年期殖利率", "%"),
        "fed_rate_upper": ("Fed利率目標上緣", "%"),
        "fed_rate_lower": ("Fed利率目標下緣", "%"),
        "ism_pmi_proxy": ("製造業景氣代理指標(NY Fed Empire State調查，非ISM原始PMI)", "指數"),
    }
    all_rows = []
    series_values: dict[str, dict[str, float]] = {}
    for code, series_id in fred_cfg.items():
        df = _fred_series(series_id, start_date, end_date)
        if df.empty:
            continue
        label, unit = label_map.get(code, (code, None))
        series_values[code] = dict(zip(df["date"], df["value"]))
        for _, r in df.iterrows():
            all_rows.append(
                {
                    "date": r["date"],
                    "indicator_code": code,
                    "category": CATEGORY,
                    "label": label,
                    "value": r["value"],
                    "unit": unit,
                    "is_proxy": code == "ism_pmi_proxy",
                    "source": f"FRED:{series_id}",
                }
            )

    # 殖利率曲線利差 = 10Y - 2Y（正值代表正常，負值代表倒掛）
    if "us_10y_yield" in series_values and "us_2y_yield" in series_values:
        y10, y2 = series_values["us_10y_yield"], series_values["us_2y_yield"]
        for d in set(y10) & set(y2):
            all_rows.append(
                {
                    "date": d,
                    "indicator_code": "us_yield_curve_10y_2y",
                    "category": CATEGORY,
                    "label": "美債10Y-2Y利差(倒掛指標)",
                    "value": y10[d] - y2[d],
                    "unit": "%",
                    "is_proxy": False,
                    "source": "FRED計算",
                }
            )

    n = upsert_timeseries(all_rows)
    logger.info(f"collect_fred_indicators 寫入 {n} 筆")
    return n


def collect_foreign_flow_proxy(start_date: str, end_date: str) -> int:
    """外資累計匯入/匯出近似代理：TWSE 三大法人買賣金額統計中的外資買賣超金額。"""
    url_tmpl = SETTINGS["twse"]["institutional_investors"]
    rows = []
    for d in trading_date_range(start_date, end_date):
        date_str = d.strftime("%Y%m%d")
        url = url_tmpl.format(date=date_str)
        resp = http_get(url, logger=logger)
        if resp is None:
            continue
        try:
            resp.encoding = "utf-8-sig" if resp.encoding in (None, "ISO-8859-1") else resp.encoding
            tables = pd.read_csv(pd.io.common.StringIO(resp.text), skiprows=1, encoding="utf-8-sig")
        except Exception as e:
            logger.warning(f"外資買賣超解析失敗 {date_str}: {e}")
            continue
        try:
            row_match = tables[tables.iloc[:, 0].astype(str).str.contains("外資", na=False)]
            if row_match.empty:
                continue
            net_col = [c for c in tables.columns if "買賣差額" in str(c)]
            if not net_col:
                continue
            net_value = pd.to_numeric(
                row_match.iloc[0][net_col[0]].replace(",", ""), errors="coerce"
            )
            if pd.isna(net_value):
                continue
            rows.append(
                {
                    "date": d.strftime("%Y-%m-%d"),
                    "indicator_code": "foreign_net_buy_sell_proxy",
                    "category": CATEGORY,
                    "label": "外資買賣超金額(匯入匯出代理)",
                    "value": float(net_value),
                    "unit": "新台幣元",
                    "is_proxy": True,
                    "source": "TWSE BFI82U",
                }
            )
        except Exception as e:
            logger.warning(f"外資買賣超欄位解析失敗 {date_str}: {e}")
            continue
    n = upsert_timeseries(rows)
    logger.info(f"collect_foreign_flow_proxy 寫入 {n} 筆")
    return n


def run(start_date: str, end_date: str) -> None:
    for fn in (collect_yfinance_indicators, collect_fred_indicators, collect_foreign_flow_proxy):
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
