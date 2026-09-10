"""五、短期籌碼/程式交易層：期現貨價差、台指期外資淨部位、put/call ratio、max pain、融資融券、借券賣出。

資料來源皆為 TAIFEX/TWSE 官方頁面實際使用的內部端點（經以瀏覽器實測確認格式），而非公開文件
上寫死的猜測網址：

- TAIFEX 期貨/選擇權每日行情：POST https://www.taifex.com.tw/cht/3/futDataDown 、 optDataDown
  （回應為 Big5 編碼 CSV，支援日期區間，但保守起見以「月」為單位分批請求）
- TAIFEX 三大法人-依日期：POST https://www.taifex.com.tw/cht/3/futContractsDate
  （回應為內嵌 HTML 表格的整頁 HTML，僅支援單日查詢）
- TWSE 加權指數/融資融券/借券賣出餘額：GET 各自端點，皆為 Big5 編碼 CSV，僅支援單日查詢

若官方格式再次調整導致抓不到欄位，會記錄 warning 並略過當天，不會讓整個排程中斷。
"""

from datetime import datetime
from io import StringIO

import pandas as pd

from src.collectors.base import SETTINGS, get_logger, http_get, http_post, month_chunks, trading_date_range
from src.db.repo import log_run, upsert_options_chain, upsert_timeseries

logger = get_logger("chip_positioning")

CATEGORY = "chip_positioning"


def _to_num(v) -> float | None:
    try:
        return float(str(v).replace(",", "").strip())
    except (ValueError, TypeError):
        return None


def _ts_row(date_iso: str, code: str, label: str, value, unit: str) -> dict:
    return {
        "date": date_iso,
        "indicator_code": code,
        "category": CATEGORY,
        "label": label,
        "value": value,
        "unit": unit,
        "is_proxy": False,
        "source": "TAIFEX/TWSE",
    }


def _read_twse_csv(text: str, header_row: int = 1) -> pd.DataFrame | None:
    """TWSE 的 csv 回應開頭通常有 1 行標題文字，實際表頭在第二行(header_row=1)。"""
    try:
        df = pd.read_csv(StringIO(text), skiprows=header_row, encoding="utf-8-sig")
        df = df.dropna(axis=1, how="all")
        return df if df.shape[1] > 1 else None
    except Exception:
        return None


def _find_col(df: pd.DataFrame, *keywords: str) -> str | None:
    for c in df.columns:
        cs = str(c)
        if all(k in cs for k in keywords):
            return c
    return None


# ---------------------------------------------------------------------------
# 一、期現貨價差
# ---------------------------------------------------------------------------


def _fetch_taifex_daily_csv(url: str, commodity_id: str, start_date: str, end_date: str) -> pd.DataFrame:
    frames = []
    for chunk_start, chunk_end in month_chunks(start_date, end_date):
        payload = {
            "down_type": "1",
            "commodity_id": commodity_id,
            "commodity_id2": "",
            "queryStartDate": chunk_start.strftime("%Y/%m/%d"),
            "queryEndDate": chunk_end.strftime("%Y/%m/%d"),
        }
        resp = http_post(url, payload, logger=logger)
        if resp is None:
            continue
        resp.encoding = "big5"
        if not resp.text.strip():
            continue
        try:
            # TAIFEX 匯出的 CSV 每列結尾多一個逗號，欄位數比表頭多 1，
            # 若不指定 index_col=False，pandas 會誤將第一欄當成索引，導致全部欄位錯位。
            df = pd.read_csv(StringIO(resp.text), index_col=False)
        except Exception as e:
            logger.warning(f"TAIFEX CSV 解析失敗 {commodity_id} {chunk_start}~{chunk_end}: {e}")
            continue
        frames.append(df)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def collect_futures_spot_spread(start_date: str, end_date: str) -> int:
    fut_url = SETTINGS["taifex"]["futures_daily"]
    df = _fetch_taifex_daily_csv(fut_url, "TX", start_date, end_date)
    rows = []

    fut_close_by_date: dict[str, float] = {}
    if not df.empty:
        session_col = _find_col(df, "交易時段")
        month_col = _find_col(df, "到期月份")
        close_col = _find_col(df, "收盤價")
        date_col = _find_col(df, "交易日期")
        if all([session_col, month_col, close_col, date_col]):
            df = df[df[session_col].astype(str).str.strip() == "一般"].copy()
            df[month_col] = df[month_col].astype(str).str.strip()
            df = df.sort_values(month_col)
            for d, group in df.groupby(date_col):
                close_val = _to_num(group.iloc[0][close_col])
                if close_val is not None:
                    fut_close_by_date[str(d).strip()] = close_val

    for d in trading_date_range(start_date, end_date):
        date_ymd = d.strftime("%Y%m%d")
        date_slash = d.strftime("%Y/%m/%d")
        date_iso = d.strftime("%Y-%m-%d")

        idx_resp = http_get(SETTINGS["twse"]["taiex_index"].format(date=date_ymd), logger=logger)
        if idx_resp is None:
            continue
        idx_df = _read_twse_csv(idx_resp.text)
        if idx_df is None:
            continue
        name_col = _find_col(idx_df, "指數")
        close_col2 = _find_col(idx_df, "收盤")
        if name_col is None or close_col2 is None:
            continue
        taiex_rows = idx_df[idx_df[name_col].astype(str).str.contains("加權", na=False)]
        if taiex_rows.empty:
            continue
        taiex_close = _to_num(taiex_rows.iloc[0][close_col2])
        if taiex_close is None:
            continue

        rows.append(_ts_row(date_iso, "taiex_close", "加權指數收盤", taiex_close, "點"))

        fut_close = fut_close_by_date.get(date_slash)
        if fut_close is not None:
            rows.append(_ts_row(date_iso, "tx_futures_close", "台指期近月收盤", fut_close, "點"))
            rows.append(
                _ts_row(date_iso, "futures_spot_spread", "台指期現貨價差(正價差/逆價差)", fut_close - taiex_close, "點")
            )

    n = upsert_timeseries(rows)
    logger.info(f"collect_futures_spot_spread 寫入 {n} 筆")
    return n


# ---------------------------------------------------------------------------
# 二、台指期外資淨部位
# ---------------------------------------------------------------------------


def _col_contains(col, *keywords: str) -> bool:
    joined = "".join(str(x) for x in (col if isinstance(col, tuple) else (col,)) if not str(x).startswith("Unnamed"))
    return all(k in joined for k in keywords)


def collect_foreign_futures_position(start_date: str, end_date: str) -> int:
    url = SETTINGS["taifex"]["futures_institutional"]
    rows = []
    for d in trading_date_range(start_date, end_date):
        payload = {"queryDate": d.strftime("%Y/%m/%d"), "commodityId": "", "queryType": "1", "button": "送出查詢"}
        resp = http_post(url, payload, logger=logger)
        if resp is None:
            continue
        try:
            tables = pd.read_html(StringIO(resp.text))
        except Exception as e:
            logger.warning(f"三大法人期貨表格解析失敗 {d}: {e}")
            continue
        target = next((t for t in tables if t.shape[1] >= 12 and t.shape[0] >= 3), None)
        if target is None:
            continue
        try:
            name_col = next(c for c in target.columns if _col_contains(c, "商品", "名稱"))
            identity_col = next(c for c in target.columns if _col_contains(c, "身份"))
            value_col = next(c for c in target.columns if _col_contains(c, "未平倉", "多空淨額", "口數"))
        except StopIteration:
            logger.warning(f"三大法人期貨欄位比對失敗 {d}")
            continue
        mask = target[name_col].astype(str).str.contains("臺股期貨", na=False) & target[identity_col].astype(
            str
        ).str.contains("外資", na=False)
        match = target[mask]
        if match.empty:
            continue
        net_val = _to_num(match.iloc[0][value_col])
        if net_val is None:
            continue
        rows.append(
            _ts_row(d.strftime("%Y-%m-%d"), "foreign_futures_net_position", "台指期外資淨部位(多空未平倉口數)", net_val, "口")
        )
    n = upsert_timeseries(rows)
    logger.info(f"collect_foreign_futures_position 寫入 {n} 筆")
    return n


# ---------------------------------------------------------------------------
# 三、Put/Call Ratio 與 Max Pain
# ---------------------------------------------------------------------------


def _max_pain(strikes: list[float], call_oi: list[float], put_oi: list[float]) -> float | None:
    if not strikes:
        return None
    best_strike, best_loss = None, None
    for s in strikes:
        loss = 0.0
        for k, c_oi, p_oi in zip(strikes, call_oi, put_oi):
            if s > k:
                loss += (s - k) * (c_oi or 0)
            if s < k:
                loss += (k - s) * (p_oi or 0)
        if best_loss is None or loss < best_loss:
            best_loss, best_strike = loss, s
    return best_strike


def collect_options_putcall_maxpain(start_date: str, end_date: str) -> int:
    url = SETTINGS["taifex"]["options_daily"]
    df = _fetch_taifex_daily_csv(url, "TXO", start_date, end_date)
    if df.empty:
        logger.info("collect_options_putcall_maxpain 無資料")
        return 0

    session_col = _find_col(df, "交易時段")
    cp_col = _find_col(df, "買賣權")
    strike_col = _find_col(df, "履約價")
    volume_col = _find_col(df, "成交量")
    oi_col = _find_col(df, "未沖銷")
    date_col = _find_col(df, "交易日期")
    if not all([session_col, cp_col, strike_col, date_col]):
        logger.warning("選擇權欄位比對失敗，略過")
        return 0

    df = df[df[session_col].astype(str).str.strip() == "一般"].copy()

    ts_rows = []
    for d, group in df.groupby(date_col):
        chain: dict[float, dict] = {}
        call_vol_total, put_vol_total = 0.0, 0.0
        for _, r in group.iterrows():
            strike = _to_num(r.get(strike_col))
            if strike is None:
                continue
            cp = str(r.get(cp_col, "")).strip()
            vol = _to_num(r.get(volume_col)) or 0 if volume_col else 0
            oi = _to_num(r.get(oi_col)) or 0 if oi_col else 0
            entry = chain.setdefault(strike, {"call_oi": 0, "put_oi": 0, "call_volume": 0, "put_volume": 0})
            if "買" in cp:
                entry["call_oi"] += oi
                entry["call_volume"] += vol
                call_vol_total += vol
            else:
                entry["put_oi"] += oi
                entry["put_volume"] += vol
                put_vol_total += vol

        if not chain:
            continue

        date_iso = str(d).strip().replace("/", "-")
        chain_rows = [{"date": date_iso, "strike": k, **v} for k, v in chain.items()]
        upsert_options_chain(chain_rows)

        if call_vol_total:
            ts_rows.append(_ts_row(date_iso, "put_call_ratio", "選擇權 Put/Call Ratio", put_vol_total / call_vol_total, "比率"))

        strikes = list(chain.keys())
        mp = _max_pain(strikes, [chain[k]["call_oi"] for k in strikes], [chain[k]["put_oi"] for k in strikes])
        if mp is not None:
            ts_rows.append(_ts_row(date_iso, "options_max_pain", "選擇權最大痛點(Max Pain)", mp, "點"))

    n = upsert_timeseries(ts_rows)
    logger.info(f"collect_options_putcall_maxpain 寫入 {n} 筆 timeseries")
    return n


# ---------------------------------------------------------------------------
# 四、融資融券餘額
# ---------------------------------------------------------------------------


def collect_margin_trading(start_date: str, end_date: str) -> int:
    url_tmpl = SETTINGS["twse"]["margin_trading"]
    rows = []
    for d in trading_date_range(start_date, end_date):
        date_ymd = d.strftime("%Y%m%d")
        resp = http_get(url_tmpl.format(date=date_ymd), logger=logger)
        if resp is None:
            continue
        df = _read_twse_csv(resp.text)
        if df is None:
            continue
        try:
            item_col = df.columns[0]
            balance_col = _find_col(df, "今日餘額")
            if balance_col is None:
                continue
            margin_row = df[df[item_col].astype(str).str.contains("融資", na=False) & ~df[item_col].astype(str).str.contains("金額", na=False)]
            short_row = df[df[item_col].astype(str).str.contains("融券", na=False)]
            margin_val = _to_num(margin_row.iloc[0][balance_col]) if not margin_row.empty else None
            short_val = _to_num(short_row.iloc[0][balance_col]) if not short_row.empty else None
        except Exception as e:
            logger.warning(f"融資融券解析失敗 {date_ymd}: {e}")
            continue
        date_iso = d.strftime("%Y-%m-%d")
        if margin_val is not None:
            rows.append(_ts_row(date_iso, "margin_balance", "融資餘額", margin_val, "張"))
        if short_val is not None:
            rows.append(_ts_row(date_iso, "short_margin_balance", "融券餘額", short_val, "張"))
    n = upsert_timeseries(rows)
    logger.info(f"collect_margin_trading 寫入 {n} 筆")
    return n


# ---------------------------------------------------------------------------
# 五、借券賣出餘額
# ---------------------------------------------------------------------------


def collect_securities_lending(start_date: str, end_date: str) -> int:
    url_tmpl = SETTINGS["twse"]["securities_lending"]
    rows = []
    for d in trading_date_range(start_date, end_date):
        date_ymd = d.strftime("%Y%m%d")
        resp = http_get(url_tmpl.format(date=date_ymd), logger=logger)
        if resp is None:
            continue
        df = _read_twse_csv(resp.text, header_row=2)
        if df is None:
            continue
        balance_col = _find_col(df, "當日餘額")
        name_col = _find_col(df, "名稱")
        if balance_col is None or name_col is None:
            continue
        # CSV 本身已內含「合計」列，直接取用即可，避免與逐股加總重複計算。
        total_row = df[df[name_col].astype(str).str.strip() == "合計"]
        if total_row.empty:
            continue
        total = _to_num(total_row.iloc[0][balance_col])
        if total is None:
            continue
        rows.append(
            _ts_row(d.strftime("%Y-%m-%d"), "securities_lending_balance", "借券賣出餘額(全市場合計)", total, "股")
        )
    n = upsert_timeseries(rows)
    logger.info(f"collect_securities_lending 寫入 {n} 筆")
    return n


def run(start_date: str, end_date: str) -> None:
    for fn in (
        collect_futures_spot_spread,
        collect_foreign_futures_position,
        collect_options_putcall_maxpain,
        collect_margin_trading,
        collect_securities_lending,
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
