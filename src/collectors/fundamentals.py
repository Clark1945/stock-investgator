"""三、產業/基本面層：台灣月營收、個股EPS/稅後淨利/毛利率、ISM PMI(在 fx_rates_macro 內)。

歷史資料來源說明：
- 月營收：改用 MOPS 月營收歷史彙總檔（mopsov.twse.com.tw/nas/t21/sii/t21sc03_{民國年}_{月}_0.html），
  依「民國年_月」逐月查詢即可取得任意歷史月份的全上市公司營收與年增率，可完整回補。
- EPS / 稅後淨利：改用「財務比較e點通」(mopsfin.twse.com.tw/compare/data)，單一請求即可取回
  該公司從 2013Q1 至今「單季」數字（非累計數）與官方年增率，同樣可完整回補，不受限於「僅最新一期」。
- 季營收：仍用 TWSE OpenAPI 損益表(t187ap06_L_ci)，該端點只回傳「目前最新公告一期」的
  全市場快照，無法指定歷史區間查詢，歷史序列只能隨每日/每季執行逐步累積。
- 毛利率 / 營業利益率：改用「財務比較e點通」(compareItem=GrossMargin/OperatingMargin)，
  與EPS/稅後淨利同一套機制，可回補2013Q1至今單季數字，不再用openapi自算(已從
  collect_income_statement移除，避免同一指標code出現兩種來源互相覆蓋)。
"""

from datetime import datetime
from io import StringIO

import pandas as pd

from src.collectors.base import SETTINGS, get_logger, http_get, http_post
from src.db.repo import log_run, query_company_profiles, query_indicator_codes_like, upsert_timeseries

logger = get_logger("fundamentals")

CATEGORY = "fundamentals"

MOPSFIN_HEADERS = {"Referer": "https://mopsfin.twse.com.tw/"}


def _watchlist() -> list[dict]:
    return SETTINGS.get("watchlist_electronics", [])


def _watchlist_codes() -> set[str]:
    return {item["code"] for item in _watchlist()}


# ---------------------------------------------------------------------------
# 月營收（歷史彙總檔，可回補任意月份）
# ---------------------------------------------------------------------------


def collect_monthly_revenue_history(start_date: str, end_date: str) -> int:
    """收全部上市公司（非僅觀察清單），該歷史彙總檔本來就是全市場單一檔案，不需額外請求。"""
    url_tpl = SETTINGS["twse"]["monthly_revenue_history"]
    rows = []

    for roc_year, month in _roc_year_months(start_date, end_date):
        url = url_tpl.format(roc_year=roc_year, month=month)
        resp = http_get(url, logger=logger)
        if resp is None:
            continue
        resp.encoding = "big5"
        try:
            tables = pd.read_html(StringIO(resp.text), flavor="lxml")
        except Exception as e:
            logger.warning(f"月營收歷史檔解析失敗 {roc_year}/{month}: {e}")
            continue

        year = roc_year + 1911
        report_date = f"{year}-{month:02d}-01"
        found_codes = set()
        for t in tables:
            if t.shape[1] != 11:
                continue
            for _, r in t.iterrows():
                code = str(r.iloc[0]).strip()
                name = str(r.iloc[1]).strip()
                if not code or not code[0].isdigit() or code in found_codes:
                    continue
                revenue = _to_float(r.iloc[2])
                mom = _to_float(r.iloc[5])
                yoy = _to_float(r.iloc[6])
                if revenue is not None:
                    rows.append(_row(report_date, f"monthly_revenue_{code}", f"{name}({code}) 月營收", revenue, "新台幣千元", "MOPS t21sc03"))
                if mom is not None:
                    rows.append(_row(report_date, f"monthly_revenue_mom_{code}", f"{name}({code}) 月營收月增率", mom, "%", "MOPS t21sc03"))
                if yoy is not None:
                    rows.append(_row(report_date, f"monthly_revenue_yoy_{code}", f"{name}({code}) 月營收年增率", yoy, "%", "MOPS t21sc03"))
                found_codes.add(code)
        if found_codes:
            logger.info(f"月營收歷史 {year}-{month:02d} 取得 {len(found_codes)} 家上市公司")

    n = upsert_timeseries(rows)
    logger.info(f"collect_monthly_revenue_history 寫入 {n} 筆")
    return n


def _roc_year_months(start_date: str, end_date: str) -> list[tuple[int, int]]:
    d0 = datetime.strptime(start_date, "%Y-%m-%d")
    d1 = min(datetime.strptime(end_date, "%Y-%m-%d"), datetime.today())
    months = []
    y, m = d0.year, d0.month
    while (y, m) <= (d1.year, d1.month):
        months.append((y - 1911, m))
        m += 1
        if m > 12:
            m = 1
            y += 1
    return months


# ---------------------------------------------------------------------------
# EPS / 稅後淨利（財務比較e點通，單一請求取回2013Q1至今單季數字+官方年增率）
# ---------------------------------------------------------------------------


def collect_quarterly_financials_history(_start_date: str, _end_date: str) -> int:
    """每日排程用：僅電子業觀察清單7家、4個欄位都要(含年增率)。"""
    companies = [(item["code"], item["name"]) for item in _watchlist()]
    metric_keys = list(SETTINGS.get("mopsfin", {}).get("metrics", {}).keys())
    return collect_quarterly_financials_bulk(companies, metric_keys)


def _all_company_list() -> list[tuple[str, str]]:
    """全上市公司(代號,簡稱)清單，取自 company_profile 表，交集月營收清單以排除非普通股代碼。"""
    name_map = {r["stock_code"]: r["name"] for r in query_company_profiles()}
    codes = query_indicator_codes_like("monthly_revenue_%")
    seen = set()
    result = []
    for c in codes:
        suffix = c[len("monthly_revenue_"):]
        if suffix.startswith("mom_") or suffix.startswith("yoy_") or suffix in seen:
            continue
        seen.add(suffix)
        name = name_map.get(suffix)
        if name:
            result.append((suffix, name))
    return sorted(result)


def collect_quarterly_financials_bulk(
    companies: list[tuple[str, str]], metric_keys: list[str], year_filter: str | None = None
) -> int:
    """全市場規模用的一般化版本：可指定公司清單、只抓哪幾個欄位、只保留哪一年。
    mopsfin 每次請求固定回傳該公司 2013Q1 至今全部歷史(不支援依日期區間查詢)，
    所以「縮短時間範圍」只會減少寫入資料庫的筆數，不會減少對外請求次數/耗時；
    這裡刻意不放進每日排程 run()，避免每天跑好幾十分鐘到數小時。
    """
    cfg = SETTINGS.get("mopsfin", {})
    url = cfg.get("compare_data_url")
    metrics: dict = cfg.get("metrics", {})
    rows = []
    total = len(companies)
    total_written = 0
    CHECKPOINT_EVERY = 50

    for i, (code, name) in enumerate(companies, 1):
        company_id = f"{code} {name}"
        for key in metric_keys:
            meta = metrics[key]
            series = _mopsfin_compare(url, company_id, meta["compare_item"])
            for date_str, value in series.items():
                if year_filter and not date_str.startswith(year_filter):
                    continue
                rows.append(
                    _row(date_str, f"{key}_{code}", f"{name}({code}) {meta['label']}", value, meta["unit"], "MOPS財務比較e點通")
                )
        if i % CHECKPOINT_EVERY == 0 or i == total:
            # 每 CHECKPOINT_EVERY 家就先寫入一次，避免長時間執行中途中斷時進度全部遺失。
            total_written += upsert_timeseries(rows)
            rows = []
            logger.info(f"季報全市場回補 {i}/{total} 家完成，累計寫入 {total_written} 筆")

    return total_written


def _mopsfin_compare(url: str, company_id: str, compare_item: str) -> dict[str, float]:
    payload = {
        "compareItem": compare_item,
        "quarter": "true",
        "ylabel": "",
        "ys": "0",
        "revenue": "true",
        "bcodeAvg": "true",
        "companyAvg": "true",
        "qnumber": "",
        "companyId": company_id,
    }
    resp = http_post(url, data=payload, logger=logger, headers=MOPSFIN_HEADERS)
    if resp is None:
        return {}
    try:
        data = resp.json()
    except Exception as e:
        logger.warning(f"mopsfin解析失敗 {compare_item} {company_id}: {e}")
        return {}

    xaxis = data.get("xaxisList", [])
    graph_data = data.get("graphData", [])
    if not xaxis or not graph_data:
        return {}

    # graphData[0] 固定是目標公司自己的序列，其餘為「公司平均數」「產業平均」等對照序列。
    target = graph_data[0].get("data", [])
    result = {}
    for point in target:
        if not point or point[0] is None or point[1] is None:
            continue
        idx = int(point[0])
        if idx >= len(xaxis):
            continue
        result[_quarter_to_date(xaxis[idx])] = float(point[1])
    return result


def _quarter_to_date(q_label: str) -> str:
    year = int(q_label[:4])
    season = int(q_label[-1])
    month = {1: 3, 2: 6, 3: 9, 4: 12}[season]
    return f"{year}-{month:02d}-28"


# ---------------------------------------------------------------------------
# 季營收（TWSE OpenAPI，僅最新一期快照）
# ---------------------------------------------------------------------------


def collect_income_statement(_start_date: str, _end_date: str) -> int:
    url = SETTINGS["twse"]["income_statement"]
    resp = http_get(url, logger=logger)
    if resp is None:
        return 0
    try:
        data = resp.json()
    except Exception as e:
        logger.warning(f"損益表 JSON 解析失敗: {e}")
        return 0

    watchlist = _watchlist_codes()
    rows = []
    for item in data:
        code = str(item.get("公司代號", "")).strip()
        if code not in watchlist:
            continue
        period = str(item.get("出表日期") or item.get("資料年季") or "").strip()
        report_date = _guess_report_date(item, period)
        if report_date is None:
            continue
        name = item.get("公司名稱", code)

        revenue = _to_float(item.get("營業收入"))
        if revenue is not None:
            rows.append(_row(report_date, f"revenue_{code}", f"{name}({code}) 營業收入", revenue, "新台幣千元", "TWSE t187ap06_L_ci"))

    n = upsert_timeseries(rows)
    logger.info(f"collect_income_statement 寫入 {n} 筆")
    return n


def _row(date_str: str, code: str, label: str, value: float, unit: str, source: str) -> dict:
    return {
        "date": date_str,
        "indicator_code": code,
        "category": CATEGORY,
        "label": label,
        "value": value,
        "unit": unit,
        "is_proxy": False,
        "source": source,
    }


def _guess_report_date(item: dict, period: str) -> str | None:
    # 優先用資料年季（例如 "115年第2季"或 "11502"）換算成該季最後一天
    year_field = item.get("年度") or item.get("資料年度")
    season_field = item.get("季別") or item.get("資料季別")
    try:
        if year_field and season_field:
            roc_year = int(str(year_field).strip())
            season = int(str(season_field).strip())
            year = roc_year + 1911
            season_end_month = {1: 3, 2: 6, 3: 9, 4: 12}.get(season)
            if season_end_month:
                return f"{year}-{season_end_month:02d}-28"
    except (ValueError, TypeError):
        pass
    return datetime.today().strftime("%Y-%m-%d") if period else None


def _to_float(v) -> float | None:
    if v is None:
        return None
    try:
        return float(str(v).replace(",", "").strip())
    except ValueError:
        return None


def run(start_date: str, end_date: str) -> None:
    for fn in (collect_monthly_revenue_history, collect_quarterly_financials_history, collect_income_statement):
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
