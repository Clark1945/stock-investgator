"""上市公司基本資料（產業別）。用於「個股分析」頁面的產業別篩選下拉選單。

資料源為 TWSE OpenAPI 公司基本資料(t187ap03_L)，一次請求即可取得全部上市公司，
但「產業別」欄位只有代碼(如 "24")，需自行對照 TWSE 公版產業分類表轉成中文名稱。
這份分類表是公開且穩定的靜態資料，不太會變動。
"""

from datetime import datetime

from src.collectors.base import SETTINGS, get_logger, http_get
from src.db.repo import log_run, upsert_company_profile

logger = get_logger("company_profile")

# TWSE 公版產業別代碼對照表(上市/上櫃通用)。
INDUSTRY_CODE_MAP = {
    "01": "水泥工業",
    "02": "食品工業",
    "03": "塑膠工業",
    "04": "紡織纖維",
    "05": "電機機械",
    "06": "電器電纜",
    "07": "化學生技醫療",
    "08": "玻璃陶瓷",
    "09": "造紙工業",
    "10": "鋼鐵工業",
    "11": "橡膠工業",
    "12": "汽車工業",
    "13": "電子工業",
    "14": "建材營造業",
    "15": "航運業",
    "16": "觀光餐旅業",
    "17": "金融保險業",
    "18": "貿易百貨業",
    "19": "綜合企業",
    "20": "其他業",
    "21": "化學工業",
    "22": "生技醫療業",
    "23": "油電燃氣業",
    "24": "半導體業",
    "25": "電腦及週邊設備業",
    "26": "光電業",
    "27": "通信網路業",
    "28": "電子零組件業",
    "29": "電子通路業",
    "30": "資訊服務業",
    "31": "其他電子業",
    "32": "文化創意業",
    "33": "農業科技業",
    "34": "電子商務業",
    "35": "綠能環保業",
    "36": "數位雲端業",
    "37": "運動休閒業",
    "38": "居家生活業",
    "80": "管理股票",
    "91": "存託憑證",
}


def collect_company_profile(_start_date: str, _end_date: str) -> int:
    url = SETTINGS["twse"]["company_profile"]
    resp = http_get(url, logger=logger)
    if resp is None:
        return 0
    try:
        data = resp.json()
    except Exception as e:
        logger.warning(f"公司基本資料 JSON 解析失敗: {e}")
        return 0

    rows = []
    for item in data:
        code = str(item.get("公司代號", "")).strip()
        name = item.get("公司簡稱") or item.get("公司名稱", code)
        industry_code = str(item.get("產業別", "")).strip()
        if not code:
            continue
        rows.append(
            {
                "stock_code": code,
                "name": name,
                "industry_code": industry_code or None,
                "industry_name": INDUSTRY_CODE_MAP.get(industry_code, industry_code or None),
            }
        )
    n = upsert_company_profile(rows)
    logger.info(f"collect_company_profile 寫入 {n} 筆")
    return n


def run(start_date: str, end_date: str) -> None:
    try:
        n = collect_company_profile(start_date, end_date)
        log_run("collect_company_profile", "ok", f"{n} rows")
    except Exception as e:
        logger.exception("collect_company_profile 執行失敗")
        log_run("collect_company_profile", "error", str(e))


if __name__ == "__main__":
    import sys

    start = sys.argv[1] if len(sys.argv) > 1 else datetime.today().strftime("%Y-%m-%d")
    end = sys.argv[2] if len(sys.argv) > 2 else start
    run(start, end)
