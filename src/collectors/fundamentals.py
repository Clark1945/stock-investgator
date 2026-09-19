"""三、產業/基本面層：台灣月營收、個股EPS/稅後淨利/毛利率、ISM PMI(在 fx_rates_macro 內)。

歷史資料來源說明：
- 月營收：改用 MOPS 月營收歷史彙總檔（mopsov.twse.com.tw/nas/t21/sii/t21sc03_{民國年}_{月}_0.html），
  依「民國年_月」逐月查詢即可取得任意歷史月份的全上市公司營收與年增率，可完整回補。
- EPS / 稅後淨利 / 毛利率 / 營業利益率 / 營業收入 / 營業毛利 / 營業利益：皆改用「財務比較e點通」
  (mopsfin.twse.com.tw/compare/data，compareItem分別為EPS/NetProfit/GrossMargin/OperatingMargin/
  Revenue/GrossProfit/OperatingIncome)，單一請求即可取回該公司從2013Q1至今「單季」數字（非累計數），
  同樣可完整回補，不受限於「僅最新一期」。原本用TWSE OpenAPI損益表(t187ap06_L_ci)自算/擷取這些
  欄位的collect_income_statement已移除，避免同一指標code出現兩種來源互相覆蓋；營業成本則由
  「營業收入-營業毛利」在Dashboard端反推顯示，不另外存成獨立指標。
- 業外收入、稅前淨利、營業費用：mopsfin的損益趨勢工具沒有提供這幾項的單季歷史數字，
  目前無現成資料源，暫不收集。
"""

import time
from datetime import datetime
from io import StringIO

import pandas as pd

from src.collectors.base import SETTINGS, get_logger, http_get, http_post
from src.db.repo import (
    log_run,
    query_company_profiles,
    query_indicator_codes_like,
    query_indicator_codes_since,
    upsert_timeseries,
)

logger = get_logger("fundamentals")

CATEGORY = "fundamentals"

MOPSFIN_HEADERS = {"Referer": "https://mopsfin.twse.com.tw/"}


def _watchlist() -> list[dict]:
    return SETTINGS.get("watchlist_electronics", [])


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
    companies: list[tuple[str, str]],
    metric_keys: list[str],
    year_filter: str | None = None,
    min_date: str | None = None,
    skip_existing: bool = False,
) -> int:
    """全市場規模用的一般化版本：可指定公司清單、只抓哪幾個欄位、只保留哪一年(year_filter)
    或某日期起(min_date，格式YYYY-MM-DD，可涵蓋多年)。
    mopsfin 每次請求固定回傳該公司 2013Q1 至今全部歷史(不支援依日期區間查詢)，
    所以「縮短時間範圍」只會減少寫入資料庫的筆數，不會減少對外請求次數/耗時；
    這裡刻意不放進每日排程 run()，避免每天跑好幾十分鐘到數小時。

    請求失敗(斷網/逾時等)的公司+指標會記錄下來，主迴圈跑完後冷卻60秒再重試一輪，
    仍失敗的會列在log裡；skip_existing=True 則會略過「min_date之後已經有資料」的公司+指標，
    用來在不重跑全部的情況下補洞(僅限補洞用，日常更新要保持False才會抓到新公告的季度)。
    """
    cfg = SETTINGS.get("mopsfin", {})
    url = cfg.get("compare_data_url")
    metrics: dict = cfg.get("metrics", {})
    rows = []
    total = len(companies)
    total_written = 0
    CHECKPOINT_EVERY = 50

    existing: set[str] = set()
    if skip_existing:
        for key in metric_keys:
            existing |= query_indicator_codes_since(f"{key}_%", min_date or "0000-01-01")

    def _fetch(code: str, name: str, key: str) -> list[dict] | None:
        meta = metrics[key]
        series = _mopsfin_compare(url, f"{code} {name}", meta["compare_item"])
        if series is None:
            return None
        out = []
        for date_str, value in series.items():
            if year_filter and not date_str.startswith(year_filter):
                continue
            if min_date and date_str < min_date:
                continue
            out.append(_row(date_str, f"{key}_{code}", f"{name}({code}) {meta['label']}", value, meta["unit"], "MOPS財務比較e點通"))
        return out

    failed: list[tuple[str, str, str]] = []
    for i, (code, name) in enumerate(companies, 1):
        for key in metric_keys:
            if f"{key}_{code}" in existing:
                continue
            got = _fetch(code, name, key)
            if got is None:
                failed.append((code, name, key))
            else:
                rows.extend(got)
        if i % CHECKPOINT_EVERY == 0 or i == total:
            # 每 CHECKPOINT_EVERY 家就先寫入一次，避免長時間執行中途中斷時進度全部遺失。
            total_written += upsert_timeseries(rows)
            rows = []
            logger.info(f"季報全市場回補 {i}/{total} 家完成，累計寫入 {total_written} 筆")

    if failed:
        logger.warning(f"季報全市場回補有 {len(failed)} 筆請求失敗(多半是網路/DNS中斷)，冷卻60秒後重試一輪")
        time.sleep(60)
        still_failed = []
        for code, name, key in failed:
            got = _fetch(code, name, key)
            if got is None:
                still_failed.append((code, name, key))
            else:
                rows.extend(got)
        total_written += upsert_timeseries(rows)
        if still_failed:
            detail = ", ".join(f"{c}:{k}" for c, _, k in still_failed[:50])
            logger.error(f"重試後仍有 {len(still_failed)} 筆失敗，網路恢復後請用 --only-missing 補跑。前50筆: {detail}")
        else:
            logger.info(f"重試一輪後全部補齊，累計寫入 {total_written} 筆")

    return total_written


def _mopsfin_compare(url: str, company_id: str, compare_item: str) -> dict[str, float] | None:
    """成功回傳單季序列(該公司沒有此科目時為空dict)；請求或解析失敗回傳None，讓呼叫端能區分
    「真的沒資料」與「這次沒抓到」。"""
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
        return None
    try:
        data = resp.json()
    except Exception as e:
        logger.warning(f"mopsfin解析失敗 {compare_item} {company_id}: {e}")
        return None

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


def _to_float(v) -> float | None:
    if v is None:
        return None
    try:
        return float(str(v).replace(",", "").strip())
    except ValueError:
        return None


def run(start_date: str, end_date: str) -> None:
    for fn in (collect_monthly_revenue_history, collect_quarterly_financials_history):
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
