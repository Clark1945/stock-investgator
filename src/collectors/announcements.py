"""重大訊息公告(全上市公司)、法人說明會(電子業觀察清單7家)。

- 重大訊息：TWSE OpenAPI(t187ap04_L)只回傳「當天」全部上市公司的公告，無歷史查詢，
  因此只能從執行當下開始，隨每日排程逐日累積，無法回補過去。
- 法人說明會：MOPS 網頁版用「兩段式簽章網址」機制(先跟 redirectToOld 換一次性網址，
  再 GET 該網址取實際內容)，屬於「一家公司一次請求」，故先限縮在觀察清單7家。
  簡報PDF不解析內容，只組出可直接下載的連結。
"""

import json
from datetime import datetime
from io import StringIO

import pandas as pd

from src.collectors.base import SETTINGS, get_logger, http_get, http_post
from src.db.repo import (
    log_run,
    upsert_investor_conferences,
    upsert_material_announcements,
)

logger = get_logger("announcements")

MOPS_HEADERS = {"Referer": "https://mops.twse.com.tw/mops/", "Origin": "https://mops.twse.com.tw"}


def _watchlist() -> list[dict]:
    return SETTINGS.get("watchlist_electronics", [])


def _roc_to_western(roc_str: str) -> str | None:
    roc_str = str(roc_str).strip()
    if len(roc_str) < 5:
        return None
    try:
        year = int(roc_str[:3]) + 1911
        month = int(roc_str[3:5])
        day = int(roc_str[5:7]) if len(roc_str) >= 7 else 1
        return f"{year}-{month:02d}-{day:02d}"
    except ValueError:
        return None


def _fmt_time(t: str) -> str:
    t = str(t).strip().zfill(6)
    return f"{t[0:2]}:{t[2:4]}:{t[4:6]}"


# ---------------------------------------------------------------------------
# 重大訊息公告（全上市公司，僅當天，逐日累積）
# ---------------------------------------------------------------------------


def collect_material_announcements(_start_date: str, _end_date: str) -> int:
    url = SETTINGS["twse"]["material_announcements"]
    resp = http_get(url, logger=logger)
    if resp is None:
        return 0
    try:
        data = resp.json()
    except Exception as e:
        logger.warning(f"重大訊息 JSON 解析失敗: {e}")
        return 0

    rows = []
    for item in data:
        code = str(item.get("公司代號", "")).strip()
        if not code:
            continue
        date_str = _roc_to_western(item.get("發言日期", ""))
        if date_str is None:
            continue
        time_str = _fmt_time(item.get("發言時間", "000000"))
        subject = (item.get("主旨") or item.get("主旨 ") or "").strip()
        detail = (item.get("說明") or "").strip()
        rows.append(
            {
                "stock_code": code,
                "company_name": item.get("公司名稱", code),
                "date": date_str,
                "time": time_str,
                "subject": subject,
                "detail": detail,
            }
        )
    n = upsert_material_announcements(rows)
    logger.info(f"collect_material_announcements 寫入 {n} 筆")
    return n


# ---------------------------------------------------------------------------
# 法人說明會（僅觀察清單7家，逐家用兩段式簽章網址查詢當年度）
# ---------------------------------------------------------------------------


def collect_investor_conferences(_start_date: str, _end_date: str) -> int:
    cfg = SETTINGS.get("investor_conference", {})
    roc_year = str(datetime.today().year - 1911)
    rows = []

    for item in _watchlist():
        code, name = item["code"], item["name"]
        table = _fetch_investor_conference_table(cfg, code, roc_year)
        if table is None or table.empty:
            continue
        for _, r in table.iterrows():
            event_date = _slash_roc_to_western(r.get(("召開法人說明會日期", "召開法人說明會日期")))
            if event_date is None:
                continue
            pdf_zh = r.get(("法人說明會簡報內容", "中文檔案"))
            pdf_en = r.get(("法人說明會簡報內容", "英文檔案"))
            rows.append(
                {
                    "stock_code": code,
                    "company_name": name,
                    "event_date": event_date,
                    "event_time": str(r.get(("召開法人說明會時間", "召開法人說明會時間")) or ""),
                    "location": str(r.get(("召開法人說明會地點", "召開法人說明會地點")) or ""),
                    "summary": str(r.get(("法人說明會擇要訊息", "法人說明會擇要訊息")) or ""),
                    "pdf_zh_url": _pdf_url(cfg, pdf_zh),
                    "pdf_en_url": _pdf_url(cfg, pdf_en),
                    "ir_url": str(r.get(("公司網站是否提供法人說明會相關資訊", "公司網站是否提供法人說明會相關資訊")) or ""),
                    "video_info": str(r.get(("影音連結資訊", "影音連結資訊")) or ""),
                }
            )

    n = upsert_investor_conferences(rows)
    logger.info(f"collect_investor_conferences 寫入 {n} 筆")
    return n


def _fetch_investor_conference_table(cfg: dict, code: str, roc_year: str):
    payload = {
        "apiName": cfg.get("api_name"),
        "parameters": {
            "year": roc_year,
            "co_id": code,
            "TYPEK": "sii",
            "month": "",
            "encodeURIComponent": 1,
            "step": 1,
            "firstin": 1,
            "off": 1,
        },
    }
    resp = http_post(
        cfg.get("redirect_url"),
        data=json.dumps(payload),
        logger=logger,
        headers={**MOPS_HEADERS, "Content-Type": "application/json"},
    )
    if resp is None:
        return None
    try:
        signed_url = resp.json()["result"]["url"]
    except Exception as e:
        logger.warning(f"法說會簽章網址解析失敗 {code}: {e}")
        return None

    resp2 = http_get(signed_url, logger=logger, headers=MOPS_HEADERS)
    if resp2 is None:
        return None
    resp2.encoding = "utf-8"
    try:
        tables = pd.read_html(StringIO(resp2.text), flavor="lxml")
    except Exception:
        return None
    return tables[0] if tables else None


def _slash_roc_to_western(v) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    parts = s.split("/")
    if len(parts) != 3:
        return None
    try:
        year = int(parts[0]) + 1911
        return f"{year}-{int(parts[1]):02d}-{int(parts[2]):02d}"
    except ValueError:
        return None


def _pdf_url(cfg: dict, filename) -> str | None:
    if not filename or not isinstance(filename, str) or not filename.strip():
        return None
    filename = filename.strip()
    base = cfg.get("file_download_url")
    return f"{base}?step=9&filePath=/home/html/nas/STR/&fileName={filename}&functionName=t100sb02_1"


def run(start_date: str, end_date: str) -> None:
    for fn in (collect_material_announcements, collect_investor_conferences):
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
