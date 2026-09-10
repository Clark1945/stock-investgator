"""三大法人（外資/投信/自營商）個股買賣超日報，涵蓋全部上市普通股。

資料源為 TWSE 三大法人買賣超日報(T86)，全市場單一JSON檔案，依日期查詢即可
回補任意歷史交易日，不像法說會/季報EPS那樣需要逐股個別請求，回補成本低。
範圍限定跟月營收/個股分析頁一致的普通股清單(~992家)，排除ETF、權證等。
"""

from datetime import datetime

from src.collectors.base import SETTINGS, get_logger, http_get, trading_date_range
from src.db.repo import log_run, query_indicator_codes_like, upsert_timeseries

logger = get_logger("institutional_flow")

CATEGORY = "institutional_flow"

# T86 回應 data 陣列的欄位索引
IDX_FOREIGN_NET = 4  # 外陸資買賣超股數(不含外資自營商)
IDX_TRUST_NET = 10  # 投信買賣超股數
IDX_DEALER_NET = 11  # 自營商買賣超股數(合計)
IDX_TOTAL_NET = 18  # 三大法人買賣超股數


def _to_num(v) -> float | None:
    try:
        return float(str(v).replace(",", "").strip())
    except (ValueError, TypeError):
        return None


def _common_stock_codes() -> set[str]:
    codes = query_indicator_codes_like("monthly_revenue_%")
    result = set()
    for c in codes:
        suffix = c[len("monthly_revenue_"):]
        if suffix.startswith("mom_") or suffix.startswith("yoy_"):
            continue
        result.add(suffix)
    return result


def _row(date_str: str, code: str, label: str, value: float, unit: str) -> dict:
    return {
        "date": date_str,
        "indicator_code": code,
        "category": CATEGORY,
        "label": label,
        "value": value,
        "unit": unit,
        "is_proxy": False,
        "source": "TWSE T86",
    }


def collect_institutional_flow_daily(start_date: str, end_date: str) -> int:
    url_tpl = SETTINGS["twse"]["institutional_flow_daily"]
    valid_codes = _common_stock_codes()
    if not valid_codes:
        logger.warning("目前資料庫尚無 monthly_revenue_* 清單，無法過濾普通股範圍，略過")
        return 0

    rows = []
    for d in trading_date_range(start_date, end_date):
        date_str = d.strftime("%Y%m%d")
        url = url_tpl.format(date=date_str)
        resp = http_get(url, logger=logger)
        if resp is None:
            continue
        try:
            data = resp.json()
        except Exception as e:
            logger.warning(f"三大法人買賣超解析失敗 {date_str}: {e}")
            continue

        items = data.get("data") or []
        if not items:
            continue

        date_iso = d.strftime("%Y-%m-%d")
        found = 0
        for item in items:
            code = str(item[0]).strip()
            if code not in valid_codes:
                continue
            name = str(item[1]).strip()

            foreign_net = _to_num(item[IDX_FOREIGN_NET])
            trust_net = _to_num(item[IDX_TRUST_NET])
            dealer_net = _to_num(item[IDX_DEALER_NET])
            total_net = _to_num(item[IDX_TOTAL_NET])

            if foreign_net is not None:
                rows.append(_row(date_iso, f"foreign_net_{code}", f"{name}({code}) 外資買賣超", foreign_net, "股"))
            if trust_net is not None:
                rows.append(_row(date_iso, f"trust_net_{code}", f"{name}({code}) 投信買賣超", trust_net, "股"))
            if dealer_net is not None:
                rows.append(_row(date_iso, f"dealer_net_{code}", f"{name}({code}) 自營商買賣超", dealer_net, "股"))
            if total_net is not None:
                rows.append(_row(date_iso, f"institutional_net_{code}", f"{name}({code}) 三大法人買賣超", total_net, "股"))
            found += 1
        if found:
            logger.info(f"三大法人買賣超 {date_iso} 取得 {found} 檔普通股")

    n = upsert_timeseries(rows)
    logger.info(f"collect_institutional_flow_daily 寫入 {n} 筆")
    return n


def run(start_date: str, end_date: str) -> None:
    try:
        n = collect_institutional_flow_daily(start_date, end_date)
        log_run("collect_institutional_flow_daily", "ok", f"{n} rows")
    except Exception as e:
        logger.exception("collect_institutional_flow_daily 執行失敗")
        log_run("collect_institutional_flow_daily", "error", str(e))


if __name__ == "__main__":
    import sys

    start = sys.argv[1] if len(sys.argv) > 1 else datetime.today().strftime("%Y-%m-%d")
    end = sys.argv[2] if len(sys.argv) > 2 else start
    run(start, end)
