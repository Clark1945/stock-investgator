"""四、被動資金驅動層。

EWT/AAXJ 資金流向代理(成交量)已在 fx_rates_macro.collect_yfinance_indicators 中一併寫入
(indicator_code: ewt_volume_proxy / aaxj_volume_proxy)，Dashboard 的「被動資金」頁會直接
引用這兩個 indicator_code，不在此重複抓取。

台灣50成分股名單、MSCI/FTSE 成分股權重調整公告：實測後確認官方網站皆為前端渲染頁面或無
穩定結構化端點，因此改由 Dashboard「人工輸入」頁記錄（category='passive_flows'），本檔案
目前無自動化 collector，保留 run() 作為統一介面以維持與其他四層一致的呼叫方式。
"""

from datetime import datetime

from src.collectors.base import get_logger
from src.db.repo import log_run

logger = get_logger("passive_flows")


def run(start_date: str, end_date: str) -> None:
    logger.info(
        "passive_flows 目前無自動化資料源；台灣50成分股與MSCI/FTSE公告請至 Dashboard「人工輸入」頁登記。"
    )
    log_run("passive_flows.run", "ok", "無自動化來源，僅依賴人工輸入頁")


if __name__ == "__main__":
    import sys

    start = sys.argv[1] if len(sys.argv) > 1 else datetime.today().strftime("%Y-%m-%d")
    end = sys.argv[2] if len(sys.argv) > 2 else start
    run(start, end)
